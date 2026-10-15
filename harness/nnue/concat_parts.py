"""Concatenate gen.exe shard parts into one RECORD corpus.

    python harness/nnue/concat_parts.py E:/machete/corpora/x1_handicap960_tb.bin
    # reads x1_handicap960_tb.bin.00.part .. and writes x1_handicap960_tb.bin
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", help="path without .NN.part suffix")
    parser.add_argument("--out", default="", help="defaults to the prefix itself")
    args = parser.parse_args()
    parts = sorted(glob.glob(args.prefix + ".*.part"))
    if not parts:
        raise SystemExit("no parts matching " + args.prefix + ".*.part")
    out = args.out or args.prefix
    total = sum(os.path.getsize(p) for p in parts)
    if total % RECORD.itemsize:
        raise SystemExit("parts are not a whole number of records")
    print("{:,} parts, {:,} records -> {}".format(
        len(parts), total // RECORD.itemsize, out))
    with open(out, "wb") as dest:
        for path in parts:
            with open(path, "rb") as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dest.write(chunk)
            print("  ", os.path.basename(path), os.path.getsize(path) // RECORD.itemsize)
    print("wrote", out, os.path.getsize(out) // RECORD.itemsize)
    return 0


if __name__ == "__main__":
    sys.exit(main())
