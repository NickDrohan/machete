"""The neutral referee for machete-against-machete finals (see COMPETITION.md).

    python harness/referee.py --a cursor=E:/machete/competition/cursor \
        --b claude=E:/machete/competition/claude \
        --tc 10+0.1 --games 400 --concurrency 8 --out E:/machete/competition/final-stc.json

Each side is a folder holding machete.exe and machete.nnue, loaded the way a
GUI loads it: the engine finds its network beside itself, and is given no
options except one thread and a 128 MB hash (harness/engine.py pin). Openings
come from harness/books/balanced_200.epd, each played twice with colours
reversed, on a real clock.

What a match driver for self-tests does not need and a final does:

- **A failure loses the game, it does not end the match.** A crash, an
  illegal move, or a move that overruns its clock by more than WATCHDOG_S is a
  loss for the side that was to move; the engine is restarted for the next
  game. python-chess applies no timeout to a clock-limited search, so without
  the watchdog one hung engine would stall the final for ever.
- **Pentanomial statistics.** Games are paired on the same opening with
  colours reversed, so the two results of a pair are correlated; the pair
  (0, 1/2, 1, 3/2 or 2 points) is the independent unit. The trinomial figure
  is printed beside it for comparison.
- **Resumable.** The result of every finished pair is written to --out at
  once; run the same command again and it carries on from the next pair.

This file is frozen at the competition's fork (tag referee-v1). The final is
played from that tag, never from either side's branch.
"""

import argparse
import json
import math
import os
import sys
import threading
import time

import chess
import chess.engine

import engine as engines
import match
import wall

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "books", "balanced_200.epd")
WATCHDOG_S = 10.0
HASH_MB = 128


class Forfeit(Exception):
    def __init__(self, color, why):
        Exception.__init__(self, why)
        self.color = color
        self.why = why


class Player(object):
    """One side's engine, restarted after any failure, with a watchdog on every move."""

    def __init__(self, name, folder):
        self.name = name
        self.path = os.path.join(folder, "machete.exe")
        for needed in (self.path, os.path.join(folder, "machete.nnue")):
            if not os.path.isfile(needed):
                raise SystemExit("{}: {} is missing".format(name, needed))
        self.engine = None

    def start(self):
        if self.engine is None:
            # a list is a command line, which test_referee.py uses for a stub engine
            cwd = os.path.dirname(self.path) if isinstance(self.path, str) else None
            self.engine = chess.engine.SimpleEngine.popen_uci(self.path, cwd=cwd)
            if engines.pin(self.engine, HASH_MB) is None:
                raise SystemExit("{} has no Threads option".format(self.name))
        return self

    def stop(self):
        engines.shutdown(self.engine)
        self.engine = None

    def play(self, board, limit, **kwargs):
        mover = board.turn
        budget = None
        if limit.white_clock is not None:
            remaining = limit.white_clock if mover == chess.WHITE else limit.black_clock
            budget = remaining + WATCHDOG_S
        timer = None
        fired = []
        if budget is not None:
            pid = self.engine.transport.get_pid()

            def kill():
                fired.append(True)
                try:
                    import psutil
                    psutil.Process(pid).kill()
                except Exception:
                    os.system("taskkill /PID {} /F >NUL 2>&1".format(pid))
            timer = threading.Timer(budget, kill)
            timer.daemon = True
            timer.start()
        try:
            return self.engine.play(board, limit, **kwargs)
        except Exception as problem:
            self.stop()
            why = "hung past its clock" if fired else "{}: {}".format(type(problem).__name__, problem)
            raise Forfeit(mover, "{} {}".format(self.name, why))
        finally:
            if timer:
                timer.cancel()


def play_game(white, black, opening, clock, report=None):
    """(result, board, how). Any failure is a loss for the side that was to move."""
    try:
        result, board, how, _ = match.play(white.start(), black.start(), opening, None, 0,
                                           report=report, clock=clock)
        return result, board, how
    except Forfeit as f:
        return ("0-1" if f.color == chess.WHITE else "1-0"), None, "forfeit: " + f.why
    except RuntimeError as problem:
        # match.play's illegal-move report carries the position, whose side to move made it
        text = str(problem)
        if text.startswith("illegal move"):
            side_field = text.split(" in ", 1)[1].split()[1]
            loser = white if side_field == "w" else black
            loser.stop()
            return ("0-1" if side_field == "w" else "1-0"), None, "forfeit: {} {}".format(loser.name, text)
        raise


# ---------------------------------------------------------------- statistics

def score_to_elo(score):
    score = min(max(score, 1e-9), 1 - 1e-9)
    return -400.0 * math.log10(1.0 / score - 1.0)


def pentanomial(pair_points):
    """Elo and 95% interval from per-pair points (each 0, 0.5, 1, 1.5 or 2)."""
    n = len(pair_points)
    counts = [sum(1 for p in pair_points if abs(p - k / 2.0) < 1e-9) for k in range(5)]
    if n == 0:
        return counts, 0.5, 0.0, 0.0
    mean = sum(pair_points) / (2.0 * n)
    var = sum((p / 2.0 - mean) ** 2 for p in pair_points) / n
    half = 1.96 * math.sqrt(var / n)
    elo = score_to_elo(mean)
    margin = (score_to_elo(mean + half) - score_to_elo(mean - half)) / 2.0
    return counts, mean, elo, margin


def trinomial(game_points):
    n = len(game_points)
    if n == 0:
        return 0.5, 0.0, 0.0
    mean = sum(game_points) / float(n)
    var = sum((p - mean) ** 2 for p in game_points) / n
    half = 1.96 * math.sqrt(var / n)
    return mean, score_to_elo(mean), (score_to_elo(mean + half) - score_to_elo(mean - half)) / 2.0


def report(state, name_a, name_b):
    pairs = [p for p in state["pairs"] if p is not None]
    points = [p["a_points"] for p in pairs]
    games = [g for p in pairs for g in p["a_games"]]
    w = sum(1 for g in games if g == 1.0)
    d = sum(1 for g in games if g == 0.5)
    lines = ["{} vs {}: {} games, {} pairs".format(name_a, name_b, len(games), len(pairs)),
             "{} W-D-L {}-{}-{}".format(name_a, w, d, len(games) - w - d)]
    counts, mean, elo, margin = pentanomial(points)
    lines.append("pentanomial [0, 1/2, 1, 3/2, 2]: {}".format(counts))
    lines.append("score {:.4f}  elo {:+.1f} +/- {:.1f} (pentanomial, 95%)".format(mean, elo, margin))
    t_mean, t_elo, t_margin = trinomial(games)
    lines.append("elo {:+.1f} +/- {:.1f} (trinomial, for comparison)".format(t_elo, t_margin))
    forfeits = [g for p in pairs for g in p.get("notes", []) if g.startswith("forfeit")]
    lines.append("forfeits: {}".format(len(forfeits)))
    for f in forfeits[:10]:
        lines.append("  " + f)
    return "\n".join(lines)


# ---------------------------------------------------------------- the match

def pool(paths):
    """`referee.py pool A.json B.json ...`: every match's pairs together, as one result."""
    states = []
    for path in paths:
        with open(path) as f:
            states.append(json.load(f))
    names = {(s["a"], s["b"]) for s in states}
    if len(names) != 1:
        raise SystemExit("these files are not the same two engines: {}".format(sorted(names)))
    name_a, name_b = names.pop()
    for s in states:
        print(report(s, name_a, name_b).splitlines()[3] + "  ({})".format(s["tc"]))
    pooled = {"pairs": [p for s in states for p in s["pairs"] if p is not None]}
    print("pooled over {}:".format(", ".join(s["tc"] for s in states)))
    print(report(pooled, name_a, name_b))
    counts, mean, elo, margin = pentanomial([p["a_points"] for p in pooled["pairs"]])
    if mean == 0.5:
        print("result: level")
    else:
        winner = name_a if mean > 0.5 else name_b
        doubt = "" if abs(elo) > margin else " (the 95% interval contains zero)"
        print("result: {} wins{}".format(winner, doubt))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "pool":
        return pool(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--a", required=True, help="NAME=FOLDER holding machete.exe and machete.nnue")
    parser.add_argument("--b", required=True, help="NAME=FOLDER")
    parser.add_argument("--tc", required=True, help="BASE+INCREMENT in seconds, e.g. 10+0.1")
    parser.add_argument("--games", type=int, required=True, help="an even number")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--book", default=BOOK)
    parser.add_argument("--margin", type=int, default=100, help="ms a clock may overrun before loss")
    parser.add_argument("--out", required=True, help="JSON results file; rerun to resume")
    parser.add_argument("--pgn", default="", help="PGN of every game (default: beside --out)")
    parser.add_argument("--watch", type=int, default=8780, help="live board port; 0 for none")
    args = parser.parse_args()

    name_a, folder_a = args.a.split("=", 1)
    name_b, folder_b = args.b.split("=", 1)
    if args.games % 2:
        raise SystemExit("--games must be even: games are played in colour-reversed pairs")
    book = match.load_book(args.book)
    base, increment = match.parse_tc(args.tc)
    clock = (base, increment, args.margin)
    pgn = args.pgn or os.path.splitext(args.out)[0] + ".pgn"
    npairs = args.games // 2

    state = {"a": name_a, "b": name_b, "tc": args.tc, "book": os.path.basename(args.book),
             "pairs": [None] * npairs}
    if os.path.exists(args.out):
        with open(args.out) as f:
            old = json.load(f)
        if (old["a"], old["b"], old["tc"]) != (name_a, name_b, args.tc):
            raise SystemExit("{} belongs to a different match".format(args.out))
        for i, p in enumerate(old["pairs"][:npairs]):
            state["pairs"][i] = p
        print("resuming: {} of {} pairs already played".format(
            sum(1 for p in state["pairs"] if p is not None), npairs))
    lock = threading.Lock()
    todo = [i for i in range(npairs) if state["pairs"][i] is None]

    live = None
    if args.watch:
        live = wall.Live(max(1, args.concurrency), title="{} vs {} ({})".format(name_a, name_b, args.tc),
                         columns=("side", "games", "W", "D", "L", "score", "Elo"))
        wall.start(live, args.watch, "the final")

    def save():
        temp = args.out + ".tmp"
        with open(temp, "w") as f:
            json.dump(state, f, indent=1)
        os.replace(temp, args.out)

    def worker(slot):
        a, b = Player(name_a, folder_a), Player(name_b, folder_b)
        try:
            while True:
                with lock:
                    if not todo:
                        return
                    i = todo.pop(0)
                opening = book[i % len(book)]
                a_games, notes = [], []
                for a_white in (True, False):
                    white, black = (a, b) if a_white else (b, a)
                    show = None
                    if live is not None:
                        def show(board, result, _w=white.name, _b=black.name):
                            live.set_board(slot, board, _w, _b, result)
                    result, board, how = play_game(white, black, opening, clock, show)
                    a_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
                    if not a_white:
                        a_score = 1.0 - a_score
                    a_games.append(a_score)
                    notes.append(how)
                    if board is not None:
                        wall.save_game(pgn, board, white.name, black.name,
                                       "{} vs {}".format(name_a, name_b), result,
                                       headers={"Round": str(2 * i + (1 if a_white else 2)),
                                                "TimeControl": args.tc, "Termination": how})
                with lock:
                    state["pairs"][i] = {"opening": i % len(book), "a_games": a_games,
                                         "a_points": sum(a_games), "notes": notes}
                    save()
                    done = sum(1 for p in state["pairs"] if p is not None)
                    if done % 10 == 0 or done == npairs:
                        print(report(state, name_a, name_b).splitlines()[3], "- {} pairs".format(done))
                        sys.stdout.flush()
        finally:
            a.stop()
            b.stop()

    threads = [threading.Thread(target=worker, args=(s,)) for s in range(max(1, args.concurrency))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(report(state, name_a, name_b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
