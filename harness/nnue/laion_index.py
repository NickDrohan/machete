"""Index laion/strategic_game_chess: each game's opening, result and length.

    python harness/nnue/laion_index.py E:/chess-data/laion-chess --out E:/chess-data/laion-index [--workers 4]

The dataset is 3.2 billion Stockfish self-play games in 1,599 parquet files,
each game a list of UCI moves. Replaying them is out of the question, so the
index is built in bulk with pyarrow: a game's opening is the longest line of
the lichess opening table (as UCI moves) that its first moves match, found by
joining the first k moves of every game into one string, for k from 24 down
to 1, and looking those strings up in the table's lines of length k. Move
orders count, not transpositions; at 3.2 billion games that is the price of
seconds per file instead of hours.

Writes, per input file, OUT/<name>.idx.parquet: row (the game's row in its
file), opening (index into OUT/openings.tsv, -1 for none), result (2 white
won, 1 draw, 0 black won), plies. A file whose index exists is skipped, so
the indexer can run as the download lands and pick up where it stopped.
"""
import argparse
import glob
import multiprocessing
import os
import re
import sys

import chess
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

DEPTH = 24
TABLE = None


def opening_lines(folder):
    """[(eco, name, [uci moves])] from the lichess opening table."""
    out = []
    for f in sorted(glob.glob(os.path.join(folder, "*.tsv"))):
        for line in open(f, encoding="utf-8").read().splitlines()[1:]:
            eco, name, pgn = line.split("\t")
            b, moves = chess.Board(), []
            for tok in pgn.split():
                if not re.match(r"^\d+\.", tok):
                    m = b.parse_san(tok)
                    moves.append(m.uci())
                    b.push(m)
            if len(moves) <= DEPTH:
                out.append((eco, name, moves))
    return out


def init(lines):
    global TABLE
    TABLE = {}
    for i, (_, _, moves) in enumerate(lines):
        TABLE.setdefault(len(moves), {})[" ".join(moves)] = i


def index_file(job):
    path, out = job
    if os.path.exists(out):
        return path, -1
    pf = pq.ParquetFile(path)
    parts = []
    base = 0
    for g in range(pf.num_row_groups):
        t = pf.read_row_group(g, columns=["Moves", "Result"])
        moves = t.column("Moves").combine_chunks()
        n = len(moves)
        opening = pa.array([-1] * n, type=pa.int32())
        done = pa.array([False] * n)
        for k in range(DEPTH, 0, -1):
            if k not in TABLE:
                continue
            keys = pa.array(list(TABLE[k].keys()))
            ids = pa.array(list(TABLE[k].values()), type=pa.int32())
            joined = pc.binary_join(pc.list_slice(moves, 0, k), " ")
            # a game shorter than k plies joins to fewer moves and cannot match a k-move line
            at = pc.index_in(joined, value_set=keys)
            hit = pc.and_(pc.is_valid(at), pc.invert(done))
            opening = pc.if_else(hit, pc.take(ids, pc.fill_null(at, 0)), opening)
            done = pc.or_(done, hit)
        result = pc.if_else(pc.equal(t.column("Result"), "1-0"), 2, pc.if_else(pc.equal(t.column("Result"), "0-1"), 0, 1))
        parts.append(pa.table({
            "row": pa.array(range(base, base + n), type=pa.int32()),
            "opening": opening,
            "result": pc.cast(result, pa.int8()),
            "plies": pc.cast(pc.list_value_length(moves), pa.int16()),
        }))
        base += n
    pq.write_table(pa.concat_tables(parts), out + ".tmp", compression="zstd")
    os.replace(out + ".tmp", out)
    return path, base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--openings", default="E:/machete/sources/lichess-openings")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--manifest", default="", help="only files whose size matches this manifest (complete downloads)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    lines = opening_lines(args.openings)
    with open(os.path.join(args.out, "openings.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for i, (eco, name, moves) in enumerate(lines):
            f.write("%d\t%s\t%s\t%s\n" % (i, eco, name, " ".join(moves)))
    sizes = {}
    if args.manifest:
        for line in open(args.manifest, encoding="utf-8"):
            p, s = line.rstrip("\r\n").split("\t")
            sizes[p] = int(s)
    jobs = []
    for path in sorted(glob.glob(os.path.join(args.data, "*.parquet"))):
        name = os.path.basename(path)
        if sizes and os.path.getsize(path) != sizes.get(name):
            continue
        jobs.append((path, os.path.join(args.out, name.replace(".parquet", ".idx.parquet"))))
    with multiprocessing.Pool(args.workers, initializer=init, initargs=(lines,)) as pool:
        for path, n in pool.imap_unordered(index_file, jobs):
            if n >= 0:
                print("%s %d games" % (os.path.basename(path), n), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
