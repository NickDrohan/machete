"""train.py builds features and targets on the device; they must be the reference's.

    python harness/nnue/train_check.py [--device cpu|cuda] [--records 200000]

reference.feature_indices is what agree.py already holds the engine to, so the
device path is checked against it exactly, on random records of every legal
shape: either side to move, 0 to 32 pieces, every piece code and square. The
targets are checked against the same formula in numpy, within float rounding.
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
    rows["count"] = rng.randint(0, 33, count)
    rows["pieces"] = rng.randint(0, 12, (count, 32))
    rows["squares"] = rng.randint(0, 64, (count, 32))
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
    corpus = train.Corpus(rows, args.device)
    order = np.random.RandomState(args.seed).permutation(len(rows))
    index = np.sort(order[:len(rows) // 2])

    us, them = corpus.features(torch.from_numpy(index).to(args.device))
    want_us, want_them = reference.feature_indices(rows[index])
    if not (np.array_equal(us.cpu().numpy(), want_us) and np.array_equal(them.cpu().numpy(), want_them)):
        bad = np.nonzero((us.cpu().numpy() != want_us).any(axis=1))[0]
        raise SystemExit("features differ from the reference on {} of {} records".format(
            len(bad), len(index)))

    got = corpus.targets(torch.from_numpy(index).to(args.device)).cpu().numpy()
    worst = np.abs(got - numpy_targets(rows[index])).max()
    if worst > 1e-6:
        raise SystemExit("targets differ from the reference by up to {:.2e}".format(worst))

    print("{:,} records on {}: features exact, targets within {:.1e}".format(
        len(index), args.device, worst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
