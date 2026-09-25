"""Concatenate training corpora into one file.

    python harness/nnue/join.py base.bin supplement.bin out.bin

Every corpus here is a flat array of fixed-size records, so joining them is
concatenation and nothing more. This exists so that the step is written down
and checked rather than done with `cat` and hoped for: a file whose length is
not a whole number of records would be silently accepted by the trainer, which
memory-maps it and would read the tail as garbage.

The proportions are reported because they matter. A supplement that is 7% of
the result is a nudge; one that is 60% is a different corpus wearing the same
name, and the endgame supplement in particular is deliberately drawn from a
distribution the engine almost never sees in ordinary play.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

CHUNK = 1 << 22


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("out")
    parser.add_argument("--limit", type=int, default=0,
                        help="keep at most this many records from each input")
    args = parser.parse_args()

    size = RECORD.itemsize
    for path in args.inputs:
        if not os.path.exists(path):
            raise SystemExit("no such corpus: {}".format(path))
        length = os.path.getsize(path)
        if length % size:
            raise SystemExit("{} is {} bytes, not a whole number of {}-byte "
                             "records".format(path, length, size))

    folder = os.path.dirname(os.path.abspath(args.out))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    counts = []
    with open(args.out, "wb") as destination:
        for path in args.inputs:
            data = np.memmap(path, dtype=RECORD, mode="r")
            keep = len(data) if not args.limit else min(len(data), args.limit)
            for start in range(0, keep, CHUNK):
                destination.write(data[start:min(start + CHUNK, keep)].tobytes())
            counts.append((path, keep))
            del data

    total = sum(k for _, k in counts)
    print("{:,} positions written to {}".format(total, args.out))
    for path, keep in counts:
        print("  {:>14,}  {:5.1f}%  {}".format(keep, 100.0 * keep / max(1, total), path))

    written = os.path.getsize(args.out)
    if written != total * size:
        raise SystemExit("wrote {} bytes, expected {}".format(written, total * size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
