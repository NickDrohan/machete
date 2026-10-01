"""How many of an EPD suite's best moves an engine finds, by motif.

    python harness/nnue/suite_score.py SUITE.epd ENGINE [--option K=V]... [--nodes 200000]
        [--workers 8] [--name X] [--out results.json]

Every `bm` position is searched to a fixed node count (the same work for
every engine, independent of machine load); the position counts as found
when the engine's best move is the suite's. The motifs are attack_patterns.py's
(sacrifice, check, king zone, pawn storm, rook lift, capture, quiet), so a
change can be seen to help quiet build-up moves or only captures.
"""
import argparse
import collections
import json
import multiprocessing
import os
import sys

import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attack_patterns import motifs  # noqa: E402

ARGS = None


def read(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.strip() or line.startswith("#") or " bm " not in line:
            continue
        fields = line.split()
        board = chess.Board(" ".join(fields[:4]) + " 0 1")
        bm = line.split(" bm ")[1].split(";")[0].split()
        out.append((board.fen(), [board.parse_san(m).uci() for m in bm]))
    return out


def init(args):
    global ARGS, ENGINE
    ARGS = args
    ENGINE = chess.engine.SimpleEngine.popen_uci(args.engine, cwd=os.path.dirname(args.engine) or None)
    options = dict(o.split("=", 1) for o in args.option)
    options.setdefault("Threads", 1)
    ENGINE.configure(options)


def solve(item):
    fen, best = item
    board = chess.Board(fen)
    played = ENGINE.play(board, chess.engine.Limit(nodes=ARGS.nodes)).move
    return fen, best, played.uci() if played else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite")
    parser.add_argument("engine")
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--nodes", type=int, default=200000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--name", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    args.engine = os.path.abspath(args.engine)
    items = read(args.suite)
    with multiprocessing.Pool(args.workers, initializer=init, initargs=(args,)) as pool:
        done = pool.map(solve, items, chunksize=8)
    total, found = collections.Counter(), collections.Counter()
    for fen, best, played in done:
        board = chess.Board(fen)
        kinds = motifs(board, chess.Move.from_uci(best[0])) or ["quiet"]
        hit = played in best
        for k in ["all"] + list(kinds):
            total[k] += 1
            found[k] += hit
    name = args.name or os.path.basename(args.engine)
    print("%s: %d of %d found (%.1f%%) at %d nodes" % (name, found["all"], total["all"], 100.0 * found["all"] / total["all"], args.nodes))
    for k in sorted(total, key=lambda k: -total[k]):
        if k != "all":
            print("  %-11s %5d positions  %5.1f%% found" % (k, total[k], 100.0 * found[k] / total[k]))
    if args.out:
        json.dump(dict(name=name, nodes=args.nodes, total=total, found=found,
                       positions=[dict(fen=f, best=b, played=p) for f, b, p in done]), open(args.out, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
