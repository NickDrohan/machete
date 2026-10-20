"""A book of rook endgames taken from real games: the starts for a training set about rook play.

    python harness/nnue/rook_book.py OUT.epd CORPUS.bin [CORPUS.bin ...] [--per-cell 1000] [--scan 30000000] [--seed 1]

The lichess bot's missed wins since 1 October were all rook positions, and the
moves that let them go were rook placement and activity (lichess_endgames.py).
Positions here are picked out of the training corpora, so their pawn
structures are ones real games reach, by family:

  rr      rook against rook                 rn    rook against knight
  rb      rook against bishop               rm_r  rook and a minor against rook
  rm_rm   rook and a minor each             rr_rr two rooks each
  rr_rm   two rooks against rook and minor  r_p   rook against pawns only

no queens anywhere and at least one pawn on the board. Each family is spread
over five bands of the corpus label (|score| from the side to move: 0-60,
60-150, 150-300, 300-500, 500-700), the same number from each cell where the
corpora have them, because a book of only level positions teaches nothing
about what winning looks like (ASSUMPTIONS.md, the slice tournament). 700 is
gen.exe's ceiling for an "odds" book. Duplicates are dropped.
"""
import argparse
import collections
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD  # noqa: E402

P, N, B, R, Q, K = range(6)
BANDS = ((0, 60), (60, 150), (150, 300), (300, 500), (500, 700))
FAMILIES = ("rr", "rn", "rb", "rm_r", "rm_rm", "rr_rr", "rr_rm", "r_p")


def counts(rows):
    """Per record, per colour, how many of each kind: shape (n, 2, 6)."""
    live = np.arange(32)[None, :] < rows["count"][:, None]
    pieces = rows["pieces"]
    out = np.zeros((len(rows), 2, 6), dtype=np.int16)
    for colour in (0, 1):
        for kind in range(6):
            out[:, colour, kind] = ((pieces == colour * 6 + kind) & live).sum(axis=1)
    return out


def family(c):
    """The family of each record (index into FAMILIES), or -1, from counts (n, 2, 6)."""
    rook, minor = c[:, :, R], c[:, :, N] + c[:, :, B]
    pawns = c[:, :, P].sum(axis=1)
    fam = np.full(len(c), -1, dtype=np.int8)
    ok = (c[:, :, Q].sum(axis=1) == 0) & (pawns > 0)
    w, b = 0, 1
    for a, d in ((w, b), (b, w)):
        only = lambda s, r, n, bb: (rook[:, s] == r) & (c[:, s, N] == n) & (c[:, s, B] == bb)
        bare = (rook[:, d] == 0) & (minor[:, d] == 0)
        fam[ok & only(a, 1, 0, 0) & only(d, 0, 1, 0)] = FAMILIES.index("rn")
        fam[ok & only(a, 1, 0, 0) & only(d, 0, 0, 1)] = FAMILIES.index("rb")
        fam[ok & (rook[:, a] == 1) & (minor[:, a] == 1) & (rook[:, d] == 1) & (minor[:, d] == 0)] = FAMILIES.index("rm_r")
        fam[ok & (rook[:, a] == 2) & (minor[:, a] == 0) & (rook[:, d] == 1) & (minor[:, d] == 1)] = FAMILIES.index("rr_rm")
        fam[ok & (rook[:, a] == 1) & (minor[:, a] == 0) & bare] = FAMILIES.index("r_p")
    fam[ok & (rook[:, 0] == 1) & (rook[:, 1] == 1) & (minor.sum(axis=1) == 0)] = FAMILIES.index("rr")
    fam[ok & (rook[:, 0] == 1) & (rook[:, 1] == 1) & (minor[:, 0] == 1) & (minor[:, 1] == 1)] = FAMILIES.index("rm_rm")
    fam[ok & (rook[:, 0] == 2) & (rook[:, 1] == 2) & (minor.sum(axis=1) == 0)] = FAMILIES.index("rr_rr")
    return fam


def band(score):
    s = np.abs(score.astype(np.int32))
    out = np.full(len(s), -1, dtype=np.int8)
    for i, (lo, hi) in enumerate(BANDS):
        out[(s >= lo) & (s < hi)] = i
    return out


def fen(row):
    board = chess.Board(None)
    for k in range(row["count"]):
        code = int(row["pieces"][k])
        board.set_piece_at(int(row["squares"][k]), chess.Piece(code % 6 + 1, chess.WHITE if code < 6 else chess.BLACK))
    board.turn = chess.WHITE if row["stm"] == 0 else chess.BLACK
    board.castling_rights = 0
    return board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("corpora", nargs="+")
    parser.add_argument("--per-cell", type=int, default=1000)
    parser.add_argument("--scan", type=int, default=30000000, help="records read from each corpus at most")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = np.random.RandomState(args.seed)

    # every candidate's (corpus, index) by cell, then a sample from each cell
    cells = collections.defaultdict(list)
    for ci, path in enumerate(args.corpora):
        rows = np.memmap(path, dtype=RECORD, mode="r")
        n = min(len(rows), args.scan)
        for start in range(0, n, 2000000):
            chunk = np.asarray(rows[start:min(n, start + 2000000)])
            fam, bnd = family(counts(chunk)), band(chunk["score"])
            for f in range(len(FAMILIES)):
                for b in range(len(BANDS)):
                    hit = np.nonzero((fam == f) & (bnd == b))[0]
                    if len(hit) > 3 * args.per_cell:
                        # a sample per chunk keeps memory bounded and still draws from every part of the corpus
                        hit = rng.choice(hit, 3 * args.per_cell, replace=False)
                    if len(hit):
                        cells[(f, b)].append((ci, hit + start))
        print("scanned", path, n, flush=True)

    maps = [np.memmap(path, dtype=RECORD, mode="r") for path in args.corpora]
    kept, seen, table = [], set(), collections.Counter()
    for f in range(len(FAMILIES)):
        for b in range(len(BANDS)):
            parts = cells.get((f, b), [])
            pool = [(ci, i) for ci, idx in parts for i in idx]
            order = rng.permutation(len(pool))
            for j in order:
                if table[(f, b)] >= args.per_cell:
                    break
                ci, i = pool[j]
                row = maps[ci][i]
                board = fen(row)
                if not board.is_valid() or board.is_game_over():
                    continue
                key = board.board_fen() + (" w" if board.turn else " b")
                if key in seen:
                    continue
                seen.add(key)
                kept.append((board.fen(), FAMILIES[f], b))
                table[(f, b)] += 1
            print("{:6} band {}-{}: {} of {} candidates".format(FAMILIES[f], BANDS[b][0], BANDS[b][1], table[(f, b)], len(pool)), flush=True)

    order = rng.permutation(len(kept))
    with open(args.out, "w") as out:
        out.write("# rook endgames from real games, harness/nnue/rook_book.py, seed {}\n".format(args.seed))
        out.write("# {} positions; per family: {}\n".format(len(kept), dict(collections.Counter(k[1] for k in kept))))
        out.write("# |score| bands {}: {}\n".format(BANDS, dict(collections.Counter(k[2] for k in kept))))
        for j in order:
            out.write(kept[j][0] + "\n")
    print("wrote", args.out, len(kept))


if __name__ == "__main__":
    main()
