"""Create a 30M uniform control sample from C33 sources.

    python harness/nnue/make_control.py --out E:/machete/corpora/x0_control_30m.bin --size 30000000 --seed 7
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

C33_SOURCES = [
    "E:/machete/corpora/train4_eg.bin@63583333",
    "E:/machete/corpora/gen5.bin",
    "E:/machete/claude/data/theoden_quiet.bin",
    "E:/machete/corpora/pi_gen1.bin",
    "E:/machete/claude/data/theoden_b0.bin",
    "E:/machete/claude/data/theoden_b1.bin",
    "E:/machete/claude/data/theoden_b2.bin",
    "E:/machete/claude/data/theoden_b3.bin",
    "E:/machete/claude/data/theoden_b4.bin",
    "E:/machete/claude/data/theoden_b5.bin",
    "E:/machete/claude/data/theoden_b6.bin",
    "E:/machete/claude/data/theoden_b7.bin",
    "E:/machete/corpora/pi_gen2_sf19.bin",
    "E:/machete/corpora/rep_gen1_sf19.bin",
    "E:/machete/corpora/rep_gen2_sf19.bin",
    "E:/machete/corpora/pi_gen3_pi01_sf19.bin",
    "E:/machete/corpora/pi_gen3_pi02_sf19.bin",
    "E:/machete/corpora/pi_gen4_pi01_snap1.bin",
]


def open_source(spec):
    path, take = spec, ""
    if "@" in os.path.basename(spec):
        path, take = spec.rsplit("@", 1)
    data = np.memmap(path, dtype=RECORD, mode="r")
    take = int(take) if take else len(data)
    return path, data, take


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="E:/machete/corpora/x0_control_30m.bin")
    parser.add_argument("--size", type=int, default=30000000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    sources = [open_source(s) for s in C33_SOURCES]
    total_avail = sum(take for _, _, take in sources)
    print("C33 total available: {:,} positions across {} files".format(total_avail, len(sources)))

    rng = np.random.RandomState(args.seed)

    # Compute proportional shares
    shares = []
    accum = 0
    for i, (path, data, take) in enumerate(sources):
        if i == len(sources) - 1:
            share = args.size - accum
        else:
            share = int(round(args.size * (take / total_avail)))
            accum += share
        shares.append(share)

    print("Target total: {:,}".format(sum(shares)))

    out = np.memmap(args.out, dtype=RECORD, mode="w+", shape=(args.size,))
    at = 0
    CHUNK = 1 << 20

    for (path, data, take), share in zip(sources, shares):
        print("Sampling {:,} / {:,} from {}...".format(share, take, os.path.basename(path)))
        idx = np.sort(rng.choice(take, size=share, replace=False))
        # copy in chunks
        for start in range(0, share, CHUNK):
            end = min(share, start + CHUNK)
            chunk_idx = idx[start:end]
            out[at + start:at + end] = data[chunk_idx]
        at += share

    out.flush()
    print("Successfully wrote {:,} records ({:.2f} GB) to {}".format(
        args.size, args.size * RECORD.itemsize / 1e9, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
