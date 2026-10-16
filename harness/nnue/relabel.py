"""The same positions with a label from a different search budget.

    python harness/nnue/relabel.py IN.bin OUT.bin --nodes 1500 [--workers 16] [--limit 0]

The label-depth sweep found 10M positions from 500-node games training a
stronger network than 10M from 1,500-node games (D500 against D1500, +79 +/-
29). A generated set differs from another in two things at once: which
positions are in it (the teacher plays the games at the label's budget, and a
shallow teacher's games are more decisive and less level) and how deep the
score on each is. This separates them: it keeps IN's positions, results and
order, and replaces every score with Stockfish's at --nodes.

Stockfish is asked position after position in file order with its hash kept,
as the generator's own teacher is within a game. The record holds no castling
rights or en passant square, so the board searched has neither; mate scores
are written as +/-CLAMP. A set relabelled at its own budget therefore differs
a little from the original, which is why the comparison is made between
relabelled sets and not between a relabelled set and an original.

Each worker takes a contiguous slice and records how far it has got, so a
stopped run resumes. Runs below normal priority.
"""
import argparse
import multiprocessing
import os
import sys
import time

import chess
import chess.engine
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "rl"))
import panel  # noqa: E402
import panel_label  # noqa: E402  (below_normal, lower, finish)
from reference import RECORD  # noqa: E402

CLAMP = 2000
STEP = 2000  # positions between flushes and progress marks


def board_of(row):
    board = chess.Board(None)
    for i in range(row["count"]):
        code = int(row["pieces"][i])
        board.set_piece_at(int(row["squares"][i]), chess.Piece(code % 6 + 1, code < 6))
    board.turn = bool(row["stm"] == 0)
    return board


def worker(wid, source, dest, start, count, nodes, done):
    panel_label.below_normal()
    mark = "%s.%02d.at" % (dest, wid)
    at = int(open(mark).read()) if os.path.exists(mark) else 0
    data = np.memmap(source, dtype=RECORD, mode="r", offset=start * RECORD.itemsize, shape=(count,))
    out = np.memmap(dest, dtype=RECORD, mode="r+", offset=start * RECORD.itemsize, shape=(count,))
    engine = panel_label.lower(panel.open_engine("Stockfish", 32))
    limit = chess.engine.Limit(nodes=nodes)
    done.put((wid, at))
    for i in range(at, count):
        row = data[i]
        out[i] = row
        board = board_of(row)
        if board.is_valid() and not board.is_game_over():
            try:
                score = engine.analyse(board, limit)["score"].pov(board.turn)
            except Exception:  # a dead engine: start another and keep this position's old label
                engine = panel_label.lower(panel.open_engine("Stockfish", 32))
                score = None
            if score is not None:
                cp = (CLAMP if score.mate() > 0 else -CLAMP) if score.is_mate() else max(-CLAMP, min(CLAMP, score.score()))
                out[i]["score"] = cp
        if (i + 1) % STEP == 0 or i + 1 == count:
            out.flush()
            open(mark, "w").write(str(i + 1))
            done.put((wid, i + 1))
    panel.quiet_quit(engine)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("dest")
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0, help="only the first N positions (checks)")
    args = parser.parse_args()
    panel_label.below_normal()
    total = os.path.getsize(args.source) // RECORD.itemsize
    if args.limit:
        total = min(total, args.limit)
    if not os.path.exists(args.dest + ".part"):
        with open(args.dest + ".part", "wb") as f:
            f.truncate(total * RECORD.itemsize)
    per = -(-total // args.workers)
    slices = [(k, k * per, min(per, total - k * per)) for k in range(args.workers) if k * per < total]
    done = multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, args=(k, args.source, args.dest + ".part", s, c, args.nodes, done)) for k, s, c in slices]
    for p in pool:
        p.start()
    progress, began, last = {}, time.time(), time.time()
    first = None
    while any(p.is_alive() for p in pool) or not done.empty():
        try:
            wid, n = done.get(timeout=5)
            progress[wid] = n
        except Exception:
            continue
        got = sum(progress.values())
        if first is None and len(progress) == len(slices):
            first = got
        if time.time() - last > 60 and first is not None:
            last = time.time()
            print("%s  %d of %d  %.0f a second" % (time.strftime("%H:%M"), got, total, (got - first) / max(1, time.time() - began)), flush=True)
    panel_label.finish(pool)
    if sum(progress.values()) != total:
        raise SystemExit("stopped at %d of %d: run again to resume" % (sum(progress.values()), total))
    os.replace(args.dest + ".part", args.dest)
    for k, _, _ in slices:
        os.remove("%s.part.%02d.at" % (args.dest, k))
    print("%d positions relabelled at %d nodes -> %s (%.0f min)" % (total, args.nodes, args.dest, (time.time() - began) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
