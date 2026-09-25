"""Make a corpus symmetric about equality.

    python harness/nnue/rebalance.py data/train2_noseer.bin --out data/train2_even.bin

Our generated corpus leans positive: mean score +135, 22.5% of positions past
+400 against 17.9% past -400. The cause is a filter of our own - positions
where the side to move is in check are skipped, and the losing side is in check
far more often, so bad positions are deleted at a higher rate than good ones.

A network trained on that learns the lean as a constant offset. Measured
against outcomes from 9,000 played games, machete's mean signed error is +0.048
where Stockfish sits at +0.012: it reads a queen up as +605 and a queen down as
only -252, and in one real game evaluated a position it was down 1600 cp of
material at -66. An engine that does not know how badly it is losing makes bad
pruning decisions, because every margin is measured against that evaluation.

The fix here is resampling rather than regeneration. Scores are bucketed by
magnitude, and within each bucket the over-represented sign is thinned to match
the other. That costs positions but changes no labels, which is the safer of
the two ways to correct a distribution.

Note what this does NOT fix: the missing positions are still missing. If the
losing side's in-check positions carry knowledge, resampling cannot recover it,
only stop it skewing what remains. Removing the in-check filter is the deeper
repair and needs a regeneration run to test.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

EDGES = [0, 25, 50, 100, 200, 400, 700, 1200, 2000, 10001]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    source = np.memmap(args.data, dtype=RECORD, mode="r")
    scores = np.array(source["score"], dtype=np.int32)
    total = len(scores)
    print("{:,} positions, mean {:+.0f}".format(total, scores.mean()))

    rng = np.random.RandomState(args.seed)
    keep = np.zeros(total, dtype=bool)

    print("\n{:>12} {:>12} {:>12} {:>10}".format("band", "positive", "negative", "kept each"))
    for low, high in zip(EDGES, EDGES[1:]):
        pos = np.flatnonzero((scores >= low) & (scores < high))
        neg = np.flatnonzero((scores <= -low) & (scores > -high))
        if low == 0:
            # the innermost band straddles zero; exact zeros are already neutral
            zero = np.flatnonzero(scores == 0)
            keep[zero] = True
        take = min(len(pos), len(neg))
        if take:
            keep[rng.choice(pos, take, replace=False)] = True
            keep[rng.choice(neg, take, replace=False)] = True
        print("{:>12} {:>12,} {:>12,} {:>10,}".format(
            "{}-{}".format(low, high if high < 10000 else "max"), len(pos), len(neg), take))

    kept = np.flatnonzero(keep)
    out = np.memmap(args.out, dtype=RECORD, mode="w+", shape=(len(kept),))
    step = 2000000
    for i in range(0, len(kept), step):
        out[i:i + step] = source[kept[i:i + step]]
    out.flush()

    after = np.array(out["score"], dtype=np.int32)
    print("\n{:,} kept ({:.1f}%), mean {:+.1f}".format(
        len(kept), 100.0 * len(kept) / total, after.mean()))
    print("past +400: {:.2f}%   past -400: {:.2f}%".format(
        100.0 * (after > 400).mean(), 100.0 * (after < -400).mean()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
