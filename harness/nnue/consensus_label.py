"""Relabel a RECORD corpus with a strong-engine panel, deepening on divergence.

The generator's labels are one teacher at 1,500 nodes. This keeps the boards
and game results, and replaces each score with a panel consensus:

  1. Stockfish, PlentyChess, Reckless, Obsidian and Caissa each search the
     position at --nodes (default 1,500). These five track deep evaluations
     best among the Arena field (RESULTS.tsv LABEL-01 / D-07).
  2. Scores are pooled in win-probability space (sigmoid(cp/150)), so no
     single engine's centipawn scale dominates, then mapped back to cp.
  3. If the panel's win-prob range exceeds the gap equivalent to --diverge
     centipawns around equality, Stockfish searches again at --deep, then
     --deeper. If the panel still will not meet, deep Stockfish is the
     resolving vote.

    python harness/nnue/consensus_label.py IN.bin OUT.bin --workers 8

Engine id 12 marks a consensus label (10 = theoden, 11 = Leela).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from multiprocessing import Process, Queue

import chess
import chess.engine
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_scale import board_of
from reference import RECORD
import panel

# LABEL-01 / D-07 panel: the teachers that track deep eval. Berserk and
# Alexandria are deliberately left out.
TEACHERS = ("Stockfish", "PlentyChess", "Reckless", "Obsidian", "Caissa")
CONSENSUS_ENGINE_ID = 12
SCALE = 150.0
CLAMP = 2000


def to_wp(cp: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(cp) / SCALE))


def from_wp(p: float) -> int:
    p = min(1.0 - 1e-6, max(1e-6, float(p)))
    return int(round(SCALE * math.log(p / (1.0 - p))))


def diverge_wp(diverge_cp: int) -> float:
    """Win-prob gap equivalent to diverge_cp around equality."""
    return to_wp(diverge_cp) - 0.5


def score_of(info, turn) -> int:
    score = info["score"].pov(turn)
    if score.is_mate():
        return CLAMP if score.mate() > 0 else -CLAMP
    return max(-CLAMP, min(CLAMP, int(score.score())))


def analyse(engine, board, nodes: int) -> int:
    info = engine.analyse(board, chess.engine.Limit(nodes=nodes))
    return score_of(info, board.turn)


def consensus_cp(scores: list[int]) -> tuple[int, float]:
    """Return (median_cp_via_wp, wp_range)."""
    wps = [to_wp(s) for s in scores]
    return from_wp(float(np.median(wps))), max(wps) - min(wps)


def label_one(engines: dict, board, nodes: int, diverge: float,
              deep: int, deeper: int) -> tuple[int, float, bool]:
    """Return (cp, wp_range_after, deepened).

    Panel scores are pooled in win-probability space. A raw centipawn range
    across engines is mostly scale noise (LABEL-01); WP spread is the real
    disagreement. When that spread exceeds `diverge`, Stockfish deepens and,
    if the panel still disagrees, its deep score is the resolving vote.
    """
    scores = {name: analyse(engines[name], board, nodes) for name in TEACHERS}
    cp, spread = consensus_cp(list(scores.values()))
    deepened = False
    if spread > diverge:
        deepened = True
        scores["Stockfish"] = analyse(engines["Stockfish"], board, deep)
        cp, spread = consensus_cp(list(scores.values()))
        if spread > diverge:
            scores["Stockfish"] = analyse(engines["Stockfish"], board, deeper)
            cp, spread = consensus_cp(list(scores.values()))
            if spread > diverge:
                # deep Stockfish is the adjudicator when the panel will not meet
                cp = scores["Stockfish"]
                spread = 0.0
    return max(-CLAMP, min(CLAMP, cp)), spread, deepened


def worker(wid: int, in_path: str, out_path: str, start: int, count: int,
           nodes: int, diverge: float, deep: int, deeper: int,
           hash_mb: int, status: Queue) -> None:
    engines = {}
    try:
        for name in TEACHERS:
            engines[name] = panel.open_engine(name, hash_mb)
        data = np.memmap(in_path, dtype=RECORD, mode="r")
        out = np.memmap(out_path, dtype=RECORD, mode="r+",
                        offset=start * RECORD.itemsize, shape=(count,))
        deepened_n = 0
        t0 = time.time()
        for i in range(count):
            row = data[start + i]
            out[i] = row
            board = board_of(row)
            if board.is_valid() and not board.is_game_over():
                cp, _spread, deepened = label_one(
                    engines, board, nodes, diverge, deep, deeper)
                out[i]["score"] = cp
                out[i]["engine"] = CONSENSUS_ENGINE_ID
                if deepened:
                    deepened_n += 1
            if (i + 1) % 50 == 0 or i + 1 == count:
                rate = (i + 1) / max(1e-6, time.time() - t0)
                status.put((wid, i + 1, count, deepened_n, rate))
        out.flush()
    except Exception as exc:
        status.put((wid, -1, count, 0, 0.0, str(exc)))
        raise
    finally:
        for engine in engines.values():
            panel.quiet_quit(engine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("dest")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--nodes", type=int, default=1500)
    parser.add_argument("--diverge", type=int, default=50,
                        help="cp gap (around equality, in win-prob space) that "
                             "triggers a deeper Stockfish search")
    parser.add_argument("--deep", type=int, default=16000)
    parser.add_argument("--deeper", type=int, default=48000)
    parser.add_argument("--hash", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0,
                        help="relabel only the first N records (0 = all)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--force", action="store_true",
                        help="recopy dest even if it already exists")
    args = parser.parse_args()

    src_size = os.path.getsize(args.source)
    if src_size % RECORD.itemsize:
        raise SystemExit("source length is not a whole number of records")
    total = src_size // RECORD.itemsize
    start = args.offset
    count = total - start if args.limit <= 0 else min(args.limit, total - start)
    if count <= 0:
        raise SystemExit("nothing to label")
    wp_gate = diverge_wp(args.diverge)
    print("panel {}  nodes {}  diverge {}cp (wp {:.4f})  deep {}/{}".format(
        ",".join(TEACHERS), args.nodes, args.diverge, wp_gate, args.deep, args.deeper))

    # copy the slice first so workers only overwrite scores in place
    if (not args.force and os.path.exists(args.dest)
            and os.path.getsize(args.dest) == count * RECORD.itemsize):
        print("reusing existing dest of {:,} records".format(count))
    else:
        print("copying {:,} records to {}".format(count, args.dest))
        data = np.memmap(args.source, dtype=RECORD, mode="r")
        out = np.memmap(args.dest, dtype=RECORD, mode="w+", shape=(count,))
        out[:] = data[start:start + count]
        out.flush()
        del out, data

    workers = min(args.workers, count)
    chunk = (count + workers - 1) // workers
    status: Queue = Queue()
    procs = []
    for wid in range(workers):
        w_start = start + wid * chunk
        w_count = min(chunk, start + count - w_start)
        if w_count <= 0:
            continue
        # dest holds only the slice [offset:offset+count]; workers rewrite
        # scores in place on that file so they never touch the live generator.
        local_start = w_start - start
        p = Process(target=worker, args=(
            wid, args.dest, args.dest, local_start, w_count,
            args.nodes, wp_gate, args.deep, args.deeper, args.hash, status))
        p.start()
        procs.append(p)

    done = [0] * len(procs)
    deepened = [0] * len(procs)
    rates = [0.0] * len(procs)
    alive = len(procs)
    t0 = time.time()
    while alive:
        msg = status.get()
        if len(msg) == 6:
            wid, _, _, _, _, err = msg
            print("\nworker {} failed: {}".format(wid, err))
            for p in procs:
                p.terminate()
            return 1
        wid, finished, total_w, deep_n, rate = msg
        done[wid] = finished
        deepened[wid] = deep_n
        rates[wid] = rate
        if finished >= total_w:
            alive -= 1
        elapsed = time.time() - t0
        print("\r{:,}/{:,}  deepened {:,}  {:,.1f}/s wall  workers {:,.1f}/s   ".format(
            sum(done), count, sum(deepened), sum(done) / max(1e-6, elapsed),
            sum(rates)), end="")
        sys.stdout.flush()
    for p in procs:
        p.join()
        if p.exitcode:
            raise SystemExit("worker exited {}".format(p.exitcode))
    print("\nfinished {}  deepened {} ({:.1f}%)".format(
        args.dest, sum(deepened), 100.0 * sum(deepened) / max(1, count)))
    return 0


if __name__ == "__main__":
    # Windows spawn needs the guard; workers import this module.
    sys.exit(main())
