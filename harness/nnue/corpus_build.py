"""Profile and rebuild the training corpus without changing its coverage.

C34 added more of the same broad-book games and was worth nothing, and C35's
opening slice did not move general play. The pile C33 actually trained on
(about 364M rows) was never checked for two defects that are already
documented and never raced:

  duplicates   the same position written by several generators. A repeated
               row is extra weight on a position the net has already seen,
               which is not new coverage.
  sign bias    in-check positions are not written, and the losing side is in
               check more often, so the corpus leans positive. rebalance.py
               describes the lean; no network has been trained on the fix.

This tool measures both, then writes one row per position. Rows whose
teachers disagree by more than --conflict centipawns are dropped rather than
averaged: a contradictory label is noise. Among the copies that agree, a
Stockfish label (engine 0) is kept over the others, and a Stockfish 19 farm
row (engines 0-4, source order) is kept over a theoden row (engine 10) only
when the Stockfish row is the one that agrees; the preference is applied
inside an agreeing group.

    python harness/nnue/corpus_build.py profile SOURCE[@N] ...
    python harness/nnue/corpus_build.py build --out rebuilt.bin SOURCE[@N] ...

`--sample N` reads the first N rows of each source. That is a survey, not the
corpus: the build always reads every row it is given.
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

# piece 0..11, square 0..63. Fixed seed so a profile and a later build hash
# the same way if anyone compares them; the hash is not stored in the corpus.
_RNG = np.random.RandomState(20261003)
def _u64(rng, shape):
    """62-bit keys. RandomState.randint cannot draw a full uint64."""
    lo = rng.randint(0, 2 ** 31 - 1, size=shape).astype(np.uint64)
    hi = rng.randint(0, 2 ** 31 - 1, size=shape).astype(np.uint64)
    return (hi << np.uint64(32)) | lo


ZOBRIST = _u64(_RNG, (12, 64))
STM_KEY = _u64(_RNG, ())

EDGES = [0, 25, 50, 100, 200, 400, 700, 1200, 2000, 10001]
STOCKFISH = 0
CHUNK = 1 << 20
INDEX = np.dtype([
    ("h", "<u8"),
    ("score", "<i2"),
    ("engine", "u1"),
    ("src", "u1"),
    ("index", "<u4"),
])


def open_source(spec):
    """`path` or `path@N` (the first N records), matching train.py."""
    path, take = spec, ""
    if "@" in os.path.basename(spec):
        path, take = spec.rsplit("@", 1)
    data = np.memmap(path, dtype=RECORD, mode="r")
    take = int(take) if take else len(data)
    if take > len(data):
        raise SystemExit("{} holds {:,} records, not {:,}".format(path, len(data), take))
    return path, data, take


def position_hash(rows):
    """Identity of a stored position: pieces, squares and side to move.

    Castling rights and en passant are not in the record, so two positions
    that differ only there collide. That is a property of the file format.
    """
    count = rows["count"].astype(np.int64)
    pieces = np.minimum(rows["pieces"], 11)
    squares = np.minimum(rows["squares"], 63)
    keys = ZOBRIST[pieces, squares]
    live = np.arange(32, dtype=np.int64)[None, :] < count[:, None]
    keys = np.where(live, keys, np.uint64(0))
    digest = np.bitwise_xor.reduce(keys, axis=1)
    to_move = rows["stm"] == 1
    digest = np.where(to_move, np.bitwise_xor(digest, STM_KEY), digest)
    return digest


def band_stats(scores):
    scores = scores.astype(np.int32)
    n = len(scores)
    if n == 0:
        return "empty"
    abs_s = np.abs(scores)
    return "n {:,}  mean {:+.1f}  >+400 {:.1f}%  <-400 {:.1f}%  |s|<=150 {:.1f}%".format(
        n, float(scores.mean()),
        100.0 * np.count_nonzero(scores > 400) / n,
        100.0 * np.count_nonzero(scores < -400) / n,
        100.0 * np.count_nonzero(abs_s <= 150) / n)


def scan(sources, sample):
    """One index row per record. `sample` caps each source at its first N."""
    counts = []
    for path, data, take in sources:
        counts.append(min(take, sample) if sample else take)
    total = sum(counts)
    table = np.empty(total, dtype=INDEX)
    at = 0
    started = time.time()
    print("{:>10}  {:>12}  {}".format("rows", "unique-in", "source"))
    for src, ((path, data, take), n) in enumerate(zip(sources, counts)):
        hashes = []
        scores = []
        for first in range(0, n, CHUNK):
            rows = np.asarray(data[first:min(n, first + CHUNK)])
            end = at + len(rows)
            table["h"][at:end] = position_hash(rows)
            table["score"][at:end] = rows["score"]
            table["engine"][at:end] = rows["engine"]
            table["src"][at:end] = src
            table["index"][at:end] = np.arange(first, first + len(rows), dtype=np.uint32)
            hashes.append(table["h"][at:end])
            scores.append(rows["score"].astype(np.int32))
            at = end
        own = np.unique(np.concatenate(hashes)).size if hashes else 0
        print("{:>10,}  {:>12,}  {}  {}".format(
            n, own, os.path.basename(path), band_stats(np.concatenate(scores))))
        rate = at / max(1e-9, time.time() - started)
        print("    {:,} rows so far, {:,.0f}/s".format(at, rate))
    return table[:at]


def summarise(table, conflict_cp):
    """Duplicate rate, label conflicts, and what a deduped file would hold."""
    order = np.argsort(table["h"], kind="mergesort")
    h = table["h"][order]
    score = table["score"][order].astype(np.int32)
    engine = table["engine"][order]
    # group boundaries where the hash changes
    change = np.flatnonzero(h[1:] != h[:-1]) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [len(h)]))
    size = ends - starts
    groups = len(starts)
    dup_rows = int(np.count_nonzero(size > 1))
    print("\n{:,} rows, {:,} distinct positions ({:.2f}% duplicate rows)".format(
        len(table), groups, 100.0 * (1.0 - groups / max(1, len(table)))))
    print("positions with more than one row: {:,}".format(dup_rows))

    # a group conflicts when its scores span more than conflict_cp
    # compute per-group min/max without a python loop over 300M: reduceat
    min_s = np.minimum.reduceat(score, starts)
    max_s = np.maximum.reduceat(score, starts)
    conflict = (max_s - min_s) > conflict_cp
    print("positions whose labels span more than {} cp: {:,} ({:.2f}%)".format(
        conflict_cp, int(np.count_nonzero(conflict)),
        100.0 * np.count_nonzero(conflict) / max(1, groups)))

    # preference inside an agreeing group: Stockfish (engine 0), else the
    # first row of the group (stable by source order, because mergesort is
    # stable and rows were appended in source order)
    agree = np.flatnonzero(~conflict)
    # representative: first index of each agreeing group, replaced when a
    # later Stockfish row exists
    keep_pos = starts[agree].copy()
    sf = engine == STOCKFISH
    # for each agreeing group, the last Stockfish row if any — searchsorted
    # style via a cummax of "sf row index or -1"
    sf_idx = np.where(sf, np.arange(len(h)), -1)
    last_sf = np.maximum.reduceat(sf_idx, starts)
    has_sf = last_sf[agree] >= 0
    keep_pos[has_sf] = last_sf[agree][has_sf]
    print("agreeing positions: {:,}; of those, {:,} take a Stockfish label".format(
        len(agree), int(np.count_nonzero(has_sf))))
    print("kept before rebalance: {:,}".format(len(keep_pos)))
    print("kept scores: {}".format(band_stats(score[keep_pos])))
    return order, keep_pos


def rebalance_mask(scores, seed):
    """The same band-wise sign match as rebalance.py, returned as a mask."""
    scores = scores.astype(np.int32)
    rng = np.random.RandomState(seed)
    keep = np.zeros(len(scores), dtype=bool)
    print("\n{:>12} {:>12} {:>12} {:>10}".format("band", "positive", "negative", "kept each"))
    for low, high in zip(EDGES, EDGES[1:]):
        pos = np.flatnonzero((scores >= low) & (scores < high))
        neg = np.flatnonzero((scores <= -low) & (scores > -high))
        if low == 0:
            keep[np.flatnonzero(scores == 0)] = True
        take = min(len(pos), len(neg))
        if take:
            keep[rng.choice(pos, take, replace=False)] = True
            keep[rng.choice(neg, take, replace=False)] = True
        print("{:>12} {:>12,} {:>12,} {:>10,}".format(
            "{}-{}".format(low, high if high < 10000 else "max"), len(pos), len(neg), take))
    return keep


def write_kept(sources, table, order, positions, out_path):
    """Write `positions` (indexes into the sorted table) in source order."""
    chosen = order[positions]
    src = table["src"][chosen]
    index = table["index"][chosen]
    # gather per source so each memmap is read sequentially
    by_src = []
    n = 0
    for s in range(len(sources)):
        sel = np.flatnonzero(src == s)
        by_src.append(index[sel])
        n += len(sel)
    out = np.memmap(out_path, dtype=RECORD, mode="w+", shape=(n,))
    at = 0
    for s, rows_at in enumerate(by_src):
        data = sources[s][1]
        order_in = np.argsort(rows_at, kind="mergesort")
        rows_at = rows_at[order_in]
        for first in range(0, len(rows_at), CHUNK):
            pick = rows_at[first:first + CHUNK]
            # a sorted index is not yet a slice; copy in order
            out[at:at + len(pick)] = data[pick]
            at += len(pick)
        print("wrote {:,} from {}".format(len(rows_at), os.path.basename(sources[s][0])))
    out.flush()
    print("wrote {:,} positions to {}".format(n, out_path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("profile", "build"))
    parser.add_argument("sources", nargs="+", help="PATH or PATH@N, in training order")
    parser.add_argument("--sample", type=int, default=0,
                        help="profile only: first N rows of each source")
    parser.add_argument("--conflict", type=int, default=50,
                        help="drop a position whose copies disagree by more than this")
    parser.add_argument("--out", help="build: the corpus to write")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--no-rebalance", action="store_true")
    args = parser.parse_args()
    if args.command == "build" and not args.out:
        raise SystemExit("build needs --out")
    if args.command == "build" and args.sample:
        raise SystemExit("a sample is a survey; build reads every row")

    sources = [open_source(spec) for spec in args.sources]
    table = scan(sources, args.sample)
    order, keep_pos = summarise(table, args.conflict)
    if args.command == "profile":
        return 0

    scores = table["score"][order][keep_pos].astype(np.int32)
    if args.no_rebalance:
        chosen = keep_pos
    else:
        mask = rebalance_mask(scores, args.seed)
        chosen = keep_pos[mask]
        print("\nrebalanced: {:,}  {}".format(len(chosen), band_stats(scores[mask])))
    write_kept(sources, table, order, chosen, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
