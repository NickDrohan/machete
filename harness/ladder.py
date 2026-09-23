"""Estimate machete's rating against engines of known strength.

    python harness/ladder.py ENGINE --games 40 --movetime 200 --concurrency 8

Everything else in this repo measures machete against itself, which says
whether a change helped but never how strong the engine actually is. This
plays it against published engines and anchors the answer to their ratings.

The opponents live in a local Arena installation; --arena points elsewhere.
Their ratings are approximate CCRL 40/15 figures, so the number this prints is
"about this strong on the CCRL scale at this time control", not a FIDE rating.
Games run concurrently, one engine pair per worker, since a 24-core machine
would otherwise spend an afternoon playing one game at a time.
"""

import argparse
import json
import math
import os
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import chess
import chess.engine
import chess.pgn

import arena
import engine as engines
import match
import wall
from wall import Live

DEFAULT_ARENA = arena.ROOT

# (folder-relative path, name, approximate CCRL 40/15 rating)
OPPONENTS = [
    ("Engines/AnMon/AnMon_5.75.exe", "AnMon 5.75", 2400),
    ("Engines/SOS/SOS-51_Arena.exe", "SOS 5.1", 2500),
    ("Engines/Ruffian/Ruffian_105.exe", "Ruffian 1.0.5", 2570),
    ("Engines/Hermann/Hermann28_64.exe", "Hermann 2.8", 2600),
    ("Engines/Spike/Spike1.4.exe", "Spike 1.4", 2950),
    ("Engines/Rybka/Rybkav2.3.2a.mp.x64.exe", "Rybka 2.3.2a", 3050),
    ("Engines/Koi/Koivisto_9.0-windows-sse2-pgo.exe", "Koivisto 9.0", 3300),
    ("Engines/Plenty/PlentyChess-7.0.0-windows-ssse3.exe", "PlentyChess 7", 3400),
    ("Engines/Caissa/caissa-1.23-x64-sse2.exe", "Caissa 1.23", 3450),
    ("Engines/berserk/berserk-13-ssse3.exe", "Berserk 13", 3500),
]


LIVE = None


def elo_from_score(score):
    if score <= 0.0:
        return -800.0
    if score >= 1.0:
        return 800.0
    return -400.0 * math.log10(1.0 / score - 1.0)


def interval(score, games):
    """Half-width of a 95% interval on the Elo difference."""
    if games == 0 or score <= 0.0 or score >= 1.0:
        return float("inf")
    sigma = math.sqrt(score * (1.0 - score) / games)
    lo = max(1e-6, score - 1.96 * sigma)
    hi = min(1 - 1e-6, score + 1.96 * sigma)
    return (elo_from_score(hi) - elo_from_score(lo)) / 2.0


def combine(usable):
    """Pool the pairings, and refuse to claim more precision than they support.

    Inverse-variance weighting assumes the estimates differ only by chance. Ask
    five engines how strong one opponent is and they often disagree by far more
    than their own error bars permit - published ratings come from a different
    time control than the one being played, and that bias does not cancel.
    Pooling regardless divides the margin by roughly the root of the pairing
    count and prints a confident number the data never supported.

    So the scatter is measured against what the error bars predicted. When it
    is larger, the margin is scaled by the square root of that ratio, which is
    the usual treatment for mutually inconsistent measurements of one quantity.
    A ladder whose pairings genuinely agree is unaffected.
    """
    weights = [1.0 / (m * m) for _, m, _ in usable]
    total = sum(weights)
    pooled = sum(e * w for (e, _, _), w in zip(usable, weights)) / total
    margin = math.sqrt(1.0 / total)
    if len(usable) < 2:
        return pooled, margin, 1.0
    # the margins are 95% half-widths, so they are 1.96 standard errors. Pooling
    # is linear in whatever unit they are quoted in and does not care, but the
    # scatter test compares against a chi-square and does: leaving it out makes
    # every set of estimates look four times more consistent than it is.
    scatter = sum(w * 1.96 * 1.96 * (e - pooled) ** 2
                  for (e, _, _), w in zip(usable, weights))
    consistency = math.sqrt(scatter / (len(usable) - 1))
    if consistency > 1.0:
        margin = margin * consistency
    return pooled, margin, max(1.0, consistency)


class Tally(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.wins = 0
        self.draws = 0
        self.losses = 0
        # seconds each side spent per move, from the clock readings
        self.thinking = {"machete": [], "opponent": []}

    def add(self, outcome, machete_white):
        with self.lock:
            if outcome == "1/2-1/2":
                self.draws += 1
            elif (outcome == "1-0") == machete_white:
                self.wins += 1
            else:
                self.losses += 1

    def games(self):
        return self.wins + self.draws + self.losses

    def add_clocks(self, clocks, first_white, machete_white, clock):
        """Time each side spent per move, from the harness's clock readings."""
        if not clocks or clock is None:
            return
        left = {True: float(clock[0]), False: float(clock[0])}
        side = first_white
        with self.lock:
            for after in clocks:
                spent = (left[side] + clock[1] - after) / 1000.0
                who = "machete" if side == machete_white else "opponent"
                self.thinking[who].append(max(0.0, spent))
                left[side] = after
                side = not side

    def median_thinking(self, who):
        values = sorted(self.thinking[who])
        return values[len(values) // 2] if values else 0.0

    def score(self):
        return (self.wins + 0.5 * self.draws) / max(1, self.games())


def run_pairing(machete_path, opponent_path, games, movetime, max_plies, concurrency, seed,
                opponent_name="", pgn_path=None, options=(), clock=None, startpos=False):
    """Play `games` games, `concurrency` at a time, alternating colours."""
    tally = Tally()
    jobs = list(range(games))
    index = [0]
    index_lock = threading.Lock()
    errors = []

    def worker(worker_id):
        try:
            machete = chess.engine.SimpleEngine.popen_uci(machete_path, timeout=20)
            for setting in options:
                name, _, value = setting.partition("=")
                machete.configure({name: int(value) if value.isdigit() else value})
            # started in its own folder: several of these engines read a
            # config file from the working directory and, when it is missing,
            # answer with blank lines rather than saying so. python-chess then
            # asserts on every one of them and the pairing produces nothing.
            opponent = chess.engine.SimpleEngine.popen_uci(
                opponent_path, timeout=20, cwd=os.path.dirname(opponent_path))
            # both sides on one thread and a fixed hash: a rating that depends
            # on an engine's defaults is not a rating of the engine
            engines.pin(machete)
            if engines.pin(opponent) is None and worker_id == 0:
                errors.append("note: {} has no thread option; single-threaded by "
                              "assumption".format(opponent_name))
        except Exception as problem:
            errors.append("could not start engines: {}".format(problem))
            return
        rng = random.Random(seed + worker_id * 7919)
        try:
            while True:
                with index_lock:
                    if index[0] >= len(jobs):
                        return
                    game_number = jobs[index[0]]
                    index[0] += 1
                machete_white = game_number % 2 == 0
                if startpos:
                    book = chess.STARTING_FEN
                else:
                    book = match.random_opening(rng, 4)
                white, black = (machete, opponent) if machete_white else (opponent, machete)
                report = None
                if LIVE is not None:
                    def report(board, result, _s=worker_id, _w=machete_white):
                        LIVE.set_board(_s, board,
                                       "machete" if _w else opponent_name,
                                       opponent_name if _w else "machete", result)
                limit = chess.engine.Limit(time=movetime / 1000.0)
                try:
                    outcome, final_board, how, clocks = match.play(
                        white, black, book, limit, max_plies, report, None, clock)
                except Exception as problem:
                    errors.append("{}: {}".format(type(problem).__name__, problem))
                    return
                tally.add(outcome, machete_white)
                tally.add_clocks(clocks, match.opening_board(book).turn, machete_white, clock)
                if pgn_path:
                    wall.save_game(pgn_path, final_board,
                                   "machete" if machete_white else opponent_name,
                                   opponent_name if machete_white else "machete",
                                   "machete ladder vs {}".format(opponent_name), outcome,
                                   headers={"TimeControl": "{:g}+{:g}".format(clock[0] / 1000.0, clock[1] / 1000.0)
                                            if clock else "movetime {} ms".format(movetime),
                                            "Termination": how},
                                   clocks=clocks)
        finally:
            for side in (machete, opponent):
                engines.shutdown(side)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return tally, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--arena", default=DEFAULT_ARENA)
    parser.add_argument("--games", type=int, default=40, help="games per opponent")
    parser.add_argument("--movetime", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-plies", type=int, default=250)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-rating", type=int, default=3600,
                        help="skip opponents rated above this")
    parser.add_argument("--stop-below", type=float, default=0.05,
                        help="stop climbing once the score drops under this")
    parser.add_argument("--pgn", default="data/games_ladder.pgn",
                        help="append every game here; empty string turns it off")
    parser.add_argument("--option", action="append", default=[],
                        help="UCI option for machete as Name=Value; repeatable")
    parser.add_argument("--tc", default="", help="a real clock in seconds, BASE+INCREMENT")
    parser.add_argument("--startpos", action="store_true",
                        help="every game from the standard starting position; the clock's "
                             "timing noise is what varies them")
    parser.add_argument("--min-rating", type=int, default=0,
                        help="skip opponents rated below this")
    parser.add_argument("--linger", type=int, default=600,
                        help="seconds to keep the wall up after finishing")
    parser.add_argument("--watch", type=int, default=8760,
                        help="port for the live wall; 0 turns it off")
    args = parser.parse_args()

    machete_path = os.path.abspath(args.engine)
    estimates = []
    clock = None
    if args.tc:
        base, increment = match.parse_tc(args.tc)
        clock = (base, increment, 100)
    conditions = "{} on the clock".format(args.tc) if clock else "{} ms a move".format(args.movetime)
    if args.startpos:
        conditions += ", from the starting position"

    global LIVE
    if args.watch:
        LIVE = Live(args.concurrency, title="machete rating ladder")
        wall.start(LIVE, args.watch, "the ladder")

    print("machete rating ladder: {} games each at {}, {} at a time".format(
        args.games, conditions, args.concurrency))
    print("{:<16} {:>4} {:>4} {:>4} {:>7} {:>16}".format("opponent", "W", "D", "L", "score", "implied rating"))
    sys.stdout.flush()

    for relative, name, rating in OPPONENTS:
        if rating > args.max_rating or rating < args.min_rating:
            continue
        path = os.path.join(args.arena, relative.replace("/", os.sep))
        if not os.path.exists(path):
            print("{:<16} (not found)".format(name))
            continue
        if LIVE is not None:
            LIVE.say("playing {} ({} Elo)".format(name, rating),
                     "{} games at {}".format(args.games, conditions))
        tally, errors = run_pairing(machete_path, path, args.games, args.movetime,
                                    args.max_plies, args.concurrency, args.seed, name,
                                    args.pgn or None, args.option, clock, args.startpos)
        for note in [e for e in errors if e.startswith("note:")]:
            print("{:<16} {}".format(name, note))
        errors = [e for e in errors if not e.startswith("note:")]
        if tally.games() == 0:
            print("{:<16} no games: {}".format(name, errors[:1]))
            continue
        score = tally.score()
        implied = rating + elo_from_score(score)
        margin = interval(score, tally.games())
        estimates.append((implied, margin, tally.games(), name))
        if LIVE is not None:
            with LIVE.lock:
                LIVE.finished.append([name, rating, tally.wins, tally.draws, tally.losses,
                                      "{:.3f}".format(score), "{:.0f}".format(implied)])
        margin_text = "+/- {:.0f}".format(margin) if margin != float("inf") else "one-sided"
        print("{:<16} {:>4} {:>4} {:>4} {:>7.3f} {:>10.0f} {}".format(
            name, tally.wins, tally.draws, tally.losses, score, implied, margin_text))
        if clock:
            ours, theirs = tally.median_thinking("machete"), tally.median_thinking("opponent")
            flag = ""
            if ours > 0 and theirs < 0.25 * ours:
                flag = "  <- the opponent is not using its clock; this pairing is suspect"
            print("{:<16} median thinking per move: machete {:.2f} s, opponent {:.2f} s{}".format(
                "", ours, theirs, flag))
        sys.stdout.flush()
        if score < args.stop_below:
            print("(scoring under {:.0%}; stopping the climb here)".format(args.stop_below))
            break

    # combine the pairings that carry information, weighted by their precision
    usable = [(e, m, g) for e, m, g, _ in estimates if m != float("inf") and m < 400]
    if usable:
        pooled, pooled_margin, consistency = combine(usable)
        if consistency > 1.0:
            print("\nthe pairings disagree by more than their own error bars allow "
                  "(chi2/dof {:.1f}), so the".format(consistency * consistency))
            print("margin below is widened {:.1f}x to say so. The opponent ratings are CCRL "
                  "40/15 and".format(consistency))
            print("this match is at {}, which is the usual reason.".format(conditions))
        print("\nmachete is about {:.0f} Elo (+/- {:.0f}) on the CCRL scale at {}".format(
            pooled, pooled_margin, conditions))
        if LIVE is not None:
            LIVE.say("machete is about {:.0f} Elo (+/- {:.0f})".format(pooled, pooled_margin),
                     "on the CCRL scale at {}".format(conditions))
            # a finished ladder used to keep its wall up for ever, so it never
            # exited on its own; it now lingers for a while and then goes
            print("the wall stays up for {} s".format(args.linger))
            try:
                time.sleep(args.linger)
            except KeyboardInterrupt:
                pass
    else:
        print("\nno pairing was close enough to estimate a rating; adjust --max-rating")
    return 0


if __name__ == "__main__":
    sys.exit(main())
