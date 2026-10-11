"""A data-generation book of one opening's positions from the LAION games.

    python harness/nnue/laion_book.py --laion E:/chess-data/laion-chess --index E:/chess-data/laion-index
        --name "Sicilian Defense: Kalashnikov" --side-lines "e4 c5 Nf3 Nc6" --out book.epd
        [--files 10] [--ply 18] [--share 0.3] [--exclude test.epd]

The main lines are the games the index names --name, at --ply. The side
lines are games that begin with --side-lines' moves and are named something
else (what the opponent can choose instead), --share of the book. Positions
in --exclude (a test book) are left out, so a network trained on games from
this book can still be measured on that one. No engine filter: the generator
plays every position out, and a lopsided one teaches conversion.
"""
import argparse
import glob
import os
import random
import sys

import chess
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--laion", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--side-lines", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--files", type=int, default=10)
    parser.add_argument("--ply", type=int, default=18)
    parser.add_argument("--share", type=float, default=0.3)
    parser.add_argument("--exclude", default="")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    b = chess.Board()
    prefix = []
    for san in args.side_lines.split():
        m = b.parse_san(san)
        prefix.append(m.uci())
        b.push(m)
    main_ids, side_ids = set(), set()
    for line in open(os.path.join(args.index, "openings.tsv"), encoding="utf-8"):
        i, _, name, uci = line.rstrip("\n").split("\t")
        if name.startswith(args.name):
            main_ids.add(int(i))
        elif uci.split()[:len(prefix)] == prefix:
            side_ids.add(int(i))
    skip = set()
    if args.exclude:
        for line in open(args.exclude, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                skip.add(" ".join(line.split()[:4]))

    found = {"main": {}, "side": {}}
    for idx in sorted(glob.glob(os.path.join(args.index, "*.idx.parquet")))[:args.files]:
        t = pq.read_table(idx, columns=["row", "opening", "plies"])
        long_enough = pc.greater_equal(t.column("plies"), args.ply + 20)
        data = None
        for key, ids in (("main", main_ids), ("side", side_ids)):
            mask = pc.and_(pc.is_in(t.column("opening"), value_set=pa.array(sorted(ids), type=pa.int32())), long_enough)
            rows = t.filter(mask).column("row").to_pylist()
            if key == "side":
                rows = rows[:max(1, int(len(found["main"]) * 2))]  # the side lines need far fewer games
            if not rows:
                continue
            if data is None:
                data = pq.read_table(os.path.join(args.laion, os.path.basename(idx).replace(".idx", "")), columns=["Moves"]).column("Moves")
            for moves in data.take(pa.array(rows, type=pa.int64())).to_pylist():
                board = chess.Board()
                for u in moves[:args.ply]:
                    board.push(chess.Move.from_uci(u))
                epd = " ".join(board.fen().split()[:4])
                if epd not in skip:
                    found[key][epd] = board.fen()
        print("%s: %d main, %d side-line positions so far" % (os.path.basename(idx), len(found["main"]), len(found["side"])), flush=True)

    rng = random.Random(args.seed)
    main = list(found["main"].values())
    side = list(found["side"].values())
    rng.shuffle(side)
    side = side[:int(round(len(main) * args.share / (1 - args.share)))]
    lines = main + side
    rng.shuffle(lines)
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# %s: %d main-line and %d side-line positions at ply %d from LAION self-play\n" % (args.name, len(main), len(side), args.ply))
        for fen in lines:
            out.write(fen + "\n")
    print("%d positions -> %s" % (len(lines), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
