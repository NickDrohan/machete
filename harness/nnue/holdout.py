"""Score networks on positions none of them trained on.

    python harness/nnue/holdout.py CORPUS.bin NET.nnue [NET2.nnue ...] [--sample 100000]

The trainer's own validation split comes from the same corpora the network
learns from, so it says how well the network fits its data, not how well it
generalises. This takes an independent corpus (the Pi farm's positions, say,
which no network here has seen), runs the reference forward pass on a fixed
sample, and reports each network's loss against the trainer's target - the
mean squared gap between sigmoid(eval / SCALE) and sigmoid(label / SCALE),
the same quantity train.py prints - and its plain mean absolute error in
centipawns. A lower holdout loss is evidence of a better evaluation; games
decide strength.

The forward pass is the integer reference (reference.py), so what is scored
is exactly what the engine computes.
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference
from reference import RECORD


def sample(corpus, count, seed):
    records = np.fromfile(corpus, dtype=RECORD)
    rng = np.random.RandomState(seed)
    return records[rng.choice(len(records), size=min(count, len(records)), replace=False)]


def score(net, rows):
    scale = float(reference.SCALE)
    target = 1.0 / (1.0 + np.exp(-rows["score"].astype(np.float64) / scale))
    evals = np.empty(len(rows), dtype=np.float64)
    for i, row in enumerate(rows):
        # the reference takes (colour, kind, square); a record stores colour * 6 + kind
        pieces = [(int(row["pieces"][k]) // 6, int(row["pieces"][k]) % 6, int(row["squares"][k]))
                  for k in range(int(row["count"]))]
        acc = reference.accumulate(net, pieces)
        evals[i] = reference.forward(net, acc, int(row["stm"]), len(pieces))
    pred = 1.0 / (1.0 + np.exp(-evals / scale))
    return float(np.mean((pred - target) ** 2)), float(np.mean(np.abs(evals - rows["score"])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("nets", nargs="+")
    parser.add_argument("--sample", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rows = sample(args.corpus, args.sample, args.seed)
    print("{} positions from {}".format(len(rows), args.corpus))
    print("{:<40} {:>10} {:>12} {:>8}".format("network", "loss", "mean |err|", "seconds"))
    for path in args.nets:
        net = reference.load(path)
        started = time.time()
        loss, mae = score(net, rows)
        print("{:<40} {:>10.5f} {:>9.1f} cp {:>8.0f}".format(os.path.basename(path), loss, mae, time.time() - started))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
