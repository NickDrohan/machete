"""Which engines label best at our budget, against deep evaluations.

    python harness/nnue/label_check.py DEEP.bin NAME=PATH [NAME=PATH ...] [--sample 3000] [--nodes 1500]

LABEL-01 (2026-09-24) asked this against a round robin's depth-20+
evaluations, a set not kept. This asks it against any corpus whose labels
come from a deep search - theoden8's, Stockfish 16 at depth 18-22 - so a new
engine version can be checked before it labels anything: each engine scores
the same sample at the generator's node budget, and its win probabilities are
correlated with the deep label's. The deep labels are Stockfish's, so
Stockfish versions are flattered; the comparison that matters is each engine
against its own previous version.
"""
import argparse
import math
import os
import sys

import chess
import chess.engine
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_scale import board_of
from reference import RECORD

SCALE = 150.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("deep")
    parser.add_argument("engines", nargs="+", help="NAME=PATH")
    parser.add_argument("--sample", type=int, default=3000)
    parser.add_argument("--nodes", type=int, default=1500)
    args = parser.parse_args()
    records = np.fromfile(args.deep, dtype=RECORD, count=2_000_000)
    rows = records[np.random.RandomState(5).choice(len(records), args.sample, replace=False)]
    boards, deep = [], []
    for row in rows:
        b = board_of(row)
        if b.is_valid() and not b.is_game_over():
            boards.append(b)
            deep.append(1 / (1 + math.exp(-max(-2000, min(2000, int(row["score"]))) / SCALE)))
    deep = np.array(deep)
    print("{} positions, {} nodes each".format(len(boards), args.nodes))
    for spec in args.engines:
        name, path = spec.split("=", 1)
        e = chess.engine.SimpleEngine.popen_uci(path, cwd=os.path.dirname(path))
        e.configure({k: v for k, v in (("Threads", 1), ("Hash", 16)) if k in e.options})
        got = []
        for b in boards:
            info = e.analyse(b, chess.engine.Limit(nodes=args.nodes))
            s = info["score"].relative.score(mate_score=10000) if "score" in info else 0
            got.append(1 / (1 + math.exp(-max(-2000, min(2000, s)) / SCALE)))
        e.quit()
        got = np.array(got)
        print("  {:<18} correlation {:.3f}   rms gap {:.4f}".format(name, np.corrcoef(got, deep)[0, 1], math.sqrt(np.mean((got - deep) ** 2))))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
