"""Rank openings by result over the whole LAION index.

    python harness/nnue/laion_rank.py E:/chess-data/laion-index [--prefix "Sicilian Defense"] [--min 200000]
        [--group 1]

Equal-strength Stockfish self-play, 3.2 billion games: an opening's score is
the opening's, not an opponent's. Prints, per opening name (cut after --group
commas-or-colons levels), the games, White's wins, draws, Black's wins,
Black's score and the decisive share (games that are not drawn: an opening
that draws a lot cannot be used to beat a weaker opponent).
"""
import argparse
import collections
import glob
import os
import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--min", type=int, default=200000)
    parser.add_argument("--group", type=int, default=1, help="name parts kept after the family (split on ': ' and ', ')")
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args()
    key = {}
    for line in open(os.path.join(args.index, "openings.tsv"), encoding="utf-8"):
        i, _, name, _ = line.rstrip("\n").split("\t")
        parts = name.replace(": ", "|").replace(", ", "|").split("|")
        key[int(i)] = ": ".join(parts[:1 + args.group])
    tally = collections.defaultdict(lambda: [0, 0, 0])
    for f in sorted(glob.glob(os.path.join(args.index, "*.idx.parquet"))):
        t = pq.read_table(f, columns=["opening", "result"])
        # one number per (opening, result) pair
        combined = pc.add(pc.multiply(pc.cast(t.column("opening"), pa.int64()), 3), pc.cast(t.column("result"), pa.int64()))
        vc = combined.value_counts()
        for v, c in zip(vc.field(0).to_pylist(), vc.field(1).to_pylist()):
            tally[key.get(v // 3, "?")][v % 3] += c
    rows = []
    for name, (b, d, w) in tally.items():
        n = b + d + w
        if n >= args.min and name.startswith(args.prefix):
            rows.append((100.0 * (b + d / 2.0) / n, name, n, w, d, b))
    total = sum(sum(v) for v in tally.values())
    print("%s games in the index" % format(total, ","))
    print("%-52s %12s %7s %7s %7s %8s %9s" % ("opening", "games", "White", "draw", "Black", "Black %", "decisive"))
    for score, name, n, w, d, b in sorted(rows, reverse=True)[:args.top]:
        print("%-52s %12s %6.1f%% %6.1f%% %6.1f%% %7.1f%% %8.1f%%" % (name[:52], format(n, ","), 100.0 * w / n, 100.0 * d / n, 100.0 * b / n, score, 100.0 * (w + b) / n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
