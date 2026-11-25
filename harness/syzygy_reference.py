"""The reference answers src/syzygy.mach is held to: python-chess's WDL and DTZ for random positions of 3-5 men.

    python harness/syzygy_reference.py TABLES_DIR OUT.txt [--n 25000] [--seed 1] [--ep 3600]

Writes one line per position: FEN, then python-chess's probe_wdl and probe_dtz for the side to move, separated by
';'. Positions are random legal placements of 3 to 5 men with no castling rights (the tables hold none); --ep of them
are made by a pawn's double step, so an en passant capture may be legal. `tbcheck` (src/tools/tbcheck.mach) reads
the file and compares machete's probes, so python-chess is the oracle and the comparison is Mach.
"""
import argparse
import random

import chess
import chess.syzygy

PIECES = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]


def random_position(rng, men):
    """A legal position: two kings and men - 2 others, no pawn on a back rank, the side not to move not in check."""
    while True:
        b = chess.Board(None)
        b.clear()
        squares = rng.sample(range(64), men)
        b.set_piece_at(squares[0], chess.Piece(chess.KING, chess.WHITE))
        b.set_piece_at(squares[1], chess.Piece(chess.KING, chess.BLACK))
        ok = True
        for sq in squares[2:]:
            kind = rng.choice(PIECES)
            if kind == chess.PAWN and chess.square_rank(sq) in (0, 7):
                ok = False
                break
            b.set_piece_at(sq, chess.Piece(kind, rng.choice((chess.WHITE, chess.BLACK))))
        if not ok:
            continue
        b.turn = rng.choice((chess.WHITE, chess.BLACK))
        b.halfmove_clock = rng.randrange(0, 60)
        if b.is_valid():
            return b


def with_en_passant(rng, men):
    """A position just after a pawn's double step with an enemy pawn beside it, so an en passant capture is legal:
    4 or 5 men (two of them those pawns), the rest placed at random."""
    while True:
        mover = rng.choice((chess.WHITE, chess.BLACK))
        rank = 3 if mover == chess.WHITE else 4
        file = rng.randrange(8)
        beside = file + rng.choice((-1, 1))
        if not 0 <= beside < 8:
            continue
        b = chess.Board(None)
        b.clear()
        sq, cap = chess.square(file, rank), chess.square(beside, rank)
        b.set_piece_at(sq, chess.Piece(chess.PAWN, mover))
        b.set_piece_at(cap, chess.Piece(chess.PAWN, not mover))
        free = [s for s in range(64) if s not in (sq, cap)]
        rest = rng.sample(free, max(men, 4) - 2)
        b.set_piece_at(rest[0], chess.Piece(chess.KING, chess.WHITE))
        b.set_piece_at(rest[1], chess.Piece(chess.KING, chess.BLACK))
        ok = True
        for s in rest[2:]:
            kind = rng.choice(PIECES)
            if kind == chess.PAWN and chess.square_rank(s) in (0, 7):
                ok = False
                break
            b.set_piece_at(s, chess.Piece(kind, rng.choice((chess.WHITE, chess.BLACK))))
        behind = sq - 8 if mover == chess.WHITE else sq + 8
        start = sq - 16 if mover == chess.WHITE else sq + 16
        if not ok or b.piece_at(behind) or b.piece_at(start):
            continue
        b.turn = not mover
        b.ep_square = behind
        b.halfmove_clock = 0
        if b.is_valid() and b.has_legal_en_passant():
            return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tables")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=25000)
    ap.add_argument("--ep", type=int, default=3600)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    written = 0
    with chess.syzygy.open_tablebase(args.tables) as tb, open(args.out, "w", newline="\n") as out:
        while written < args.n:
            men = rng.choice((3, 4, 5))
            b = with_en_passant(rng, men) if written < args.ep else random_position(rng, men)
            try:
                wdl = tb.probe_wdl(b)
                dtz = tb.probe_dtz(b)
            except (KeyError, chess.syzygy.MissingTableError):
                continue
            out.write("%s;%d;%d\n" % (b.fen(), wdl, dtz))
            written += 1
    print("%s: %d positions (%d with en passant possible)" % (args.out, written, min(args.ep, args.n)))


if __name__ == "__main__":
    main()
