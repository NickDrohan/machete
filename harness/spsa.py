"""Tune machete's search constants by SPSA, in bounded, resumable chunks.

    python harness/spsa.py ENGINE --net NET --state STATE.json [--minutes 80]
        [--tc 5+0.05] [--concurrency 10] [--iterations 20000] [--watch 8801]

Every tunable the engine offers (U-01: `option name ... type spin`) is tuned
together. Each step draws a random sign for every parameter, sets one engine
to theta + c*delta and another to theta - c*delta, and plays them a pair of
games from one opening, one with each colour. The pair's result (-2..+2 for
the plus side) moves every parameter by a * result * delta / c. c and a shrink
over the run on the usual schedule (gamma 0.101, alpha 0.602, A = 10% of the
planned iterations), set so that each parameter's final perturbation is
c_end = its range / 20 and its final learning rate r_end = 0.002 (the values
fishtest uses by default).

A chunk runs for --minutes and saves STATE; the next chunk resumes from it, so
one long tune is a series of bounded jobs. STATE also keeps theta every 100
steps, so the path can be read afterwards. The result is only a candidate:
it must beat the untuned values in an SPRT before it becomes the defaults.
"""

import argparse
import json
import math
import os
import random
import sys
import threading
import time

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import match
import wall

ALPHA, GAMMA = 0.602, 0.101
R_END = 0.002


def spin_options(path, net):
    """{name: (default, low, high)} for every tunable spin option the engine offers."""
    engine = chess.engine.SimpleEngine.popen_uci(path, cwd=os.path.dirname(path))
    found = {}
    for name, option in engine.options.items():
        if option.type == "spin" and name not in ("Hash", "Threads", "MultiPV"):
            found[name] = (option.default, option.min, option.max)
    engine.quit()
    return found


class Tuner(object):
    def __init__(self, args, options):
        self.args = args
        self.lock = threading.Lock()
        if os.path.exists(args.state):
            self.state = json.load(open(args.state))
        else:
            self.state = {"theta": {n: float(v[0]) for n, v in options.items()},
                          "start": {n: v[0] for n, v in options.items()},
                          "k": 0, "planned": args.iterations, "wins": 0, "draws": 0, "losses": 0,
                          "path": []}
        self.options = options
        n = self.state["planned"]
        self.A = 0.1 * n
        self.c = {}
        self.a = {}
        for name, (default, low, high) in options.items():
            c_end = max(1.0, (high - low) / 20.0)
            self.c[name] = c_end * n ** GAMMA
            self.a[name] = R_END * c_end ** 2 * (self.A + n) ** ALPHA

    def draw_step(self, rng):
        """The perturbed values for one pair of games, and what the update needs."""
        with self.lock:
            k = self.state["k"]
            self.state["k"] = k + 1
            theta = dict(self.state["theta"])
        plus, minus, delta, ck = {}, {}, {}, {}
        for name, (default, low, high) in self.options.items():
            ck[name] = self.c[name] / (k + 1) ** GAMMA
            delta[name] = rng.choice((-1, 1))
            plus[name] = int(round(min(high, max(low, theta[name] + ck[name] * delta[name]))))
            minus[name] = int(round(min(high, max(low, theta[name] - ck[name] * delta[name]))))
        return k, plus, minus, delta, ck

    def update(self, k, delta, ck, result, wdl):
        with self.lock:
            for name, (default, low, high) in self.options.items():
                ak = self.a[name] / (self.A + k + 1) ** ALPHA
                step = ak * result * delta[name] / ck[name]
                self.state["theta"][name] = min(high, max(low, self.state["theta"][name] + step))
            self.state["wins"] += wdl[0]
            self.state["draws"] += wdl[1]
            self.state["losses"] += wdl[2]
            done = self.state["k"]
            if done % 100 == 0:
                self.state["path"].append({"k": done, "theta": {n: round(v, 2) for n, v in self.state["theta"].items()}})

    def save(self):
        with self.lock:
            tmp = self.args.state + ".tmp"
            with open(tmp, "w") as handle:
                json.dump(self.state, handle, indent=1)
            os.replace(tmp, self.args.state)


def configure(engine, values):
    engine.configure({name: value for name, value in values.items()})


def worker(slot, tuner, args, book, deadline, live, rng):
    net = {"EvalFile": args.net} if args.net else {}
    plus = chess.engine.SimpleEngine.popen_uci(args.engine, cwd=os.path.dirname(args.engine))
    minus = chess.engine.SimpleEngine.popen_uci(args.engine, cwd=os.path.dirname(args.engine))
    for engine in (plus, minus):
        engine.configure(dict({"Threads": 1}, **net))
    base, inc = match.parse_tc(args.tc)
    clock = (base, inc, 100)
    try:
        while time.time() < deadline:
            k, up, down, delta, ck = tuner.draw_step(rng)
            configure(plus, up)
            configure(minus, down)
            opening = rng.choice(book)
            points = 0.0
            wdl = [0, 0, 0]
            for plus_white in (True, False):
                white, black = (plus, minus) if plus_white else (minus, plus)

                def report(board, result, _w=plus_white):
                    if live is not None:
                        live.set_board(slot, board, "theta+" if _w else "theta-", "theta-" if _w else "theta+", result)

                outcome = match.play(white, black, opening, None, 400, report, None, clock)[0]
                if outcome == "1/2-1/2" or outcome == "*":
                    wdl[1] += 1
                elif (outcome == "1-0") == plus_white:
                    wdl[0] += 1
                    points += 1.0
                else:
                    wdl[2] += 1
                    points -= 1.0
            tuner.update(k, delta, ck, points, wdl)
    finally:
        for engine in (plus, minus):
            try:
                engine.quit()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--net", default="")
    parser.add_argument("--state", required=True)
    parser.add_argument("--minutes", type=float, default=80)
    parser.add_argument("--tc", default="5+0.05")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=20000, help="planned steps over the whole tune")
    parser.add_argument("--book", default=os.path.join(HERE, "books", "balanced_200.epd"))
    parser.add_argument("--watch", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    args.engine = os.path.abspath(args.engine)

    options = spin_options(args.engine, args.net)
    tuner = Tuner(args, options)
    book = match.load_book(args.book)
    live = None
    if args.watch:
        live = wall.Live(args.concurrency, title="SPSA", columns=("side", "games", "W", "D", "L", "score", "Elo"))
        live.say("SPSA tune of {} constants".format(len(options)), "step {}".format(tuner.state["k"]))
        wall.start(live, args.watch, "the tune")
    deadline = time.time() + args.minutes * 60
    seed = args.seed or int(time.time())
    threads = [threading.Thread(target=worker, args=(i, tuner, args, book, deadline, live, random.Random(seed + i)))
               for i in range(args.concurrency)]
    for t in threads:
        t.daemon = True
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(30)
        tuner.save()
        s = tuner.state
        if live is not None:
            live.say("SPSA tune of {} constants".format(len(options)),
                     "step {} of {}; plus side +{} ={} -{}".format(s["k"], s["planned"], s["wins"], s["draws"], s["losses"]))
    tuner.save()
    s = tuner.state
    print("steps {} of {}; games {} (plus +{} ={} -{})".format(
        s["k"], s["planned"], 2 * s["k"], s["wins"], s["draws"], s["losses"]))
    for name in sorted(s["theta"]):
        print("  {:12} start {:>6}  now {:9.2f}".format(name, s["start"][name], s["theta"][name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
