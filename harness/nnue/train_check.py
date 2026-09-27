"""train.py builds features and targets on the device; they must be the reference's.

    python harness/nnue/train_check.py [--device cpu|cuda] [--records 200000]

reference.feature_indices is what agree.py already holds the engine to, so the
device path is checked against it exactly, on random records of every legal
shape: either side to move, 0 to 32 pieces on distinct squares, every piece
code and square. The device packs a record and lists its pieces in square
order, the reference in slot order; the network sums them, so each position's
features are compared as a set. The targets are checked against the same
formula in numpy, within float rounding.
"""

import argparse
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference
import train
from reference import RECORD


def random_records(count, seed):
    rng = np.random.RandomState(seed)
    rows = np.zeros(count, dtype=RECORD)
    rows["stm"] = rng.randint(0, 2, count)
    # one king a side in the first two slots, as every real position has;
    # everything else any other piece
    rows["count"] = rng.randint(2, 33, count)
    others = np.array([0, 1, 2, 3, 4, 6, 7, 8, 9, 10])
    rows["pieces"] = others[rng.randint(0, len(others), (count, 32))]
    rows["pieces"][:, 0] = 5
    rows["pieces"][:, 1] = 11
    rows["squares"] = np.argsort(rng.rand(count, 64), axis=1)[:, :32]
    rows["score"] = rng.randint(-32000, 32001, count)
    rows["result"] = rng.randint(0, 3, count)
    return rows


def numpy_targets(rows):
    score = rows["score"].astype(np.float64)
    result = rows["result"].astype(np.float64) / 2.0
    return train.LAMBDA / (1.0 + np.exp(-score / train.SCALE)) + (1.0 - train.LAMBDA) * result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--records", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=5)
    args = parser.parse_args()

    rows = random_records(args.records, args.seed)

    # the vectorised reference against the one-piece-at-a-time definition
    # the engine is held to (reference.feature_index, via agree.py)
    us_ref, them_ref = reference.feature_indices(rows[:2000])
    for r, row in enumerate(rows[:2000]):
        pieces = [(int(c) // 6, int(c) % 6, int(q))
                  for c, q in zip(row["pieces"][:row["count"]], row["squares"][:row["count"]])]
        kings = {colour: square for colour, kind, square in pieces if kind == 5}
        for side, got in ((row["stm"], us_ref[r]), (row["stm"] ^ 1, them_ref[r])):
            want = sorted(reference.feature_index(side, colour, kind, square, kings[side])
                          for colour, kind, square in pieces)
            if sorted(got[got != reference.KING_BUCKETS * reference.INPUTS].tolist()) != want:
                raise SystemExit("reference.feature_indices disagrees with feature_index on record {}".format(r))
    corpus = train.Corpus([(rows, len(rows))], args.device)
    order = np.random.RandomState(args.seed).permutation(len(rows))
    index = np.sort(order[:len(rows) // 2])

    us, them, bucket = corpus.features(torch.from_numpy(index).to(args.device))
    us, them = np.sort(us.cpu().numpy(), axis=1), np.sort(them.cpu().numpy(), axis=1)
    want_us, want_them = (np.sort(side, axis=1) for side in reference.feature_indices(rows[index]))
    if not (np.array_equal(us, want_us) and np.array_equal(them, want_them)):
        bad = np.nonzero((us != want_us).any(axis=1) | (them != want_them).any(axis=1))[0]
        raise SystemExit("features differ from the reference on {} of {} records".format(
            len(bad), len(index)))

    want_bucket = np.array([reference.bucket(int(c)) for c in rows["count"][index]])
    if not np.array_equal(bucket.cpu().numpy(), want_bucket):
        raise SystemExit("output buckets differ from the reference on {} records".format(
            int((bucket.cpu().numpy() != want_bucket).sum())))

    got = corpus.targets(torch.from_numpy(index).to(args.device)).cpu().numpy()
    worst = np.abs(got - numpy_targets(rows[index])).max()
    if worst > 1e-6:
        raise SystemExit("targets differ from the reference by up to {:.2e}".format(worst))

    print("{:,} records on {}: features and buckets exact, targets within {:.1e}".format(
        len(index), args.device, worst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
