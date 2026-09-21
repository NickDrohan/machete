"""Settle contested positions by playing them, and record what actually happens.

    python harness/nnue/goldset.py data/contested.json --out data/goldset.json \
        --games 30 --movetime 200 --concurrency 6

Every position here is one that strong engines judged differently. Asking a
stronger engine only produces another opinion, so instead the position is
played out repeatedly and the result is counted. What comes back is a win rate
measured rather than asserted.

Two rules keep that honest:

- **The panel rotates.** If one engine played every game, the "empirical" win
  rate would be that engine's play wearing a disguise, which is the bias the
  whole exercise exists to escape.
- **Pairings are symmetric.** Each engine pair plays each position an equal
  number of times from each side, so a stronger member cannot tilt a position's
  measured value. A pairing that cannot be balanced is not played at all.

The output is a validation set the engine has never trained on, with a target
that came from results instead of from an evaluation function. It answers two
questions nothing else here can: whether our network ranks hard positions
correctly, and which of these engines actually predicts outcomes best.

Results are written after every position, so an interrupted run keeps what it
has finished.
"""

import argparse
import itertools
import json
import os
import random
import sys
import threading
import time

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import panel
import wall


def play(white, black, board, limit, max_plies, report=None):
    """One game from a given position. Returns the result, white's point of view."""
    board = board.copy()
    if report:
        report(board, None)
    while not board.is_game_over(claim_draw=True):
        if board.ply() >= max_plies:
            if report:
                report(board, "1/2-1/2")
            return "1/2-1/2", board
        engine = white if board.turn == chess.WHITE else black
        result = engine.play(board, limit)
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError("illegal move {}".format(result.move))
        board.push(result.move)
        if report:
            report(board, None)
    outcome = board.result(claim_draw=True)
    if report:
        report(board, outcome)
    return outcome, board


def schedule(names, games):
    """Balanced pairings: every ordered pair appears as often as every other.

    Ordered, so each unordered pair plays both ways round an equal number of
    times. The list is truncated to a whole number of cycles rather than to
    `games` exactly, because a partial cycle would give some engine an extra
    turn with the white pieces and quietly bias the position.
    """
    ordered = [(a, b) for a, b in itertools.permutations(names, 2)]
    cycles = max(1, games // len(ordered))
    return (ordered * cycles)[:cycles * len(ordered)]


class Work(object):
    def __init__(self, positions, games, names):
        self.lock = threading.Lock()
        self.jobs = []
        for index, entry in enumerate(positions):
            for white, black in schedule(names, games):
                self.jobs.append((index, white, black))
        self.next = 0
        self.results = [{"white": 0, "draw": 0, "black": 0} for _ in positions]

    def take(self):
        with self.lock:
            if self.next >= len(self.jobs):
                return None
            job = self.jobs[self.next]
            self.next += 1
            return job

    def record(self, index, outcome):
        with self.lock:
            key = {"1-0": "white", "0-1": "black"}.get(outcome, "draw")
            self.results[index][key] += 1


def worker(work, boards, args, failures, live=None, slot=0):
    engines = {}
    try:
        while True:
            job = work.take()
            if job is None:
                return
            index, white_name, black_name = job
            for name in (white_name, black_name):
                if name not in engines:
                    engines[name] = panel.open_engine(name, args.hash)
            report = None
            if live is not None:
                def report(board, result, _s=slot, _w=white_name, _b=black_name):
                    live.set_board(_s, board, _w, _b, result)
            try:
                outcome, final = play(engines[white_name], engines[black_name],
                                      boards[index], chess.engine.Limit(time=args.movetime / 1000.0),
                                      args.max_plies, report)
            except Exception as problem:
                failures.append("{}: {}".format(type(problem).__name__, problem))
                return
            wall.save_game(args.pgn, final, white_name, black_name,
                           "gold set position {}".format(index), outcome)
            work.record(index, outcome)
    finally:
        for engine in engines.values():
            panel.quiet_quit(engine)


def score_of(counts, turn):
    """Expected score for the side to move, from the tallied results."""
    total = counts["white"] + counts["draw"] + counts["black"]
    if total == 0:
        return None, 0
    wins = counts["white"] if turn == chess.WHITE else counts["black"]
    return (wins + 0.5 * counts["draw"]) / total, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("contested")
    parser.add_argument("--out", default="data/goldset.json")
    parser.add_argument("--games", type=int, default=30, help="games per position")
    parser.add_argument("--movetime", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--max-plies", type=int, default=250)
    parser.add_argument("--hash", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0, help="cap positions, 0 for all")
    parser.add_argument("--watch", type=int, default=8762,
                        help="port for the live board wall; 0 turns it off")
    parser.add_argument("--pgn", default="data/games_goldset.pgn",
                        help="append every game here; empty string turns it off")
    args = parser.parse_args()

    with open(args.contested) as handle:
        payload = json.load(handle)
    entries = payload["contested"] + payload["controls"]
    for entry in payload["contested"]:
        entry["kind"] = "contested"
    for entry in payload["controls"]:
        entry["kind"] = "control"
    if args.limit:
        entries = entries[:args.limit]
    boards = [chess.Board(e["fen"]) for e in entries]
    names = payload["panel"]

    work = Work(entries, args.games, names)
    print("{} positions, {} games each, {} in flight: {:,} games".format(
        len(entries), len(work.jobs) // max(1, len(entries)), args.concurrency,
        len(work.jobs)))
    sys.stdout.flush()

    failures = []
    live = None
    if args.watch:
        live = wall.Live(args.concurrency)
        live.say("settling {} contested positions".format(len(entries)),
                 "{} games each at {} ms".format(args.games, args.movetime))
        wall.start(live, args.watch, "the gold set")
    started = time.time()
    threads = [threading.Thread(target=worker, args=(work, boards, args, failures, live, slot))
               for slot in range(args.concurrency)]
    for thread in threads:
        thread.start()

    while any(t.is_alive() for t in threads):
        time.sleep(15.0)
        with work.lock:
            done = work.next
        rate = done / max(1e-9, time.time() - started)
        left = (len(work.jobs) - done) / max(1e-9, rate)
        sys.stdout.write("\r{:,}/{:,} games  {:.0f}/min  {:.1f}h left    ".format(
            done, len(work.jobs), rate * 60, left / 3600.0))
        sys.stdout.flush()
        save(args.out, entries, work, payload)

    for thread in threads:
        thread.join()
    save(args.out, entries, work, payload)
    print("\nwrote {} ({:.1f}h)".format(args.out, (time.time() - started) / 3600.0))
    if failures:
        print("{} worker failures, first: {}".format(len(failures), failures[0]))
    return 0


def save(path, entries, work, payload):
    out = []
    for index, entry in enumerate(entries):
        counts = work.results[index]
        board = chess.Board(entry["fen"])
        score, played = score_of(counts, board.turn)
        out.append({"fen": entry["fen"], "kind": entry.get("kind", "contested"),
                    "split": entry.get("split"), "verdicts": entry.get("verdicts"),
                    "results": counts, "games": played,
                    "measured_score": score})
    with open(path, "w") as handle:
        json.dump({"panel": payload["panel"], "positions": out}, handle, indent=1)


if __name__ == "__main__":
    sys.exit(main())
