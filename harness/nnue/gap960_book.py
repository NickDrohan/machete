"""Piece-down Chess960 starts aimed at what the odds net got wrong (ODDS-LOSSES).

    python harness/nnue/gap960_book.py --out E:/machete/books/gap960.epd --count 40000

The odds net (CORPUS-X1, 100% one-side-a-knight-down Chess960, castling '-')
lost 79 of 80 to 0.3.6. Its losses show three gaps:

  - piece values flattened: it scores a knight +789 and a queen +1034 in normal
    chess (C33: +456, +1200). In X1 a minor up already labels 0.92 and a queen
    up 0.995, so sigmoid(cp/150) leaves almost no signal between them.
  - balanced middlegames: 112 of its 147 blunders came at even material, and
    60% of the lost games were below -100 before the first big blunder. Only
    ~7% of X1 is material-even.
  - castling: X1 never castled. It castled in 55% of games where it could,
    0.3.6 in 89%, and 37 blunders were refuted by a king attack.

So every start here is still Chess960 with one side a piece (or the queen, or
the exchange) down, but the other side pays for it, so the material - and so
the label - stays inside the band where sigmoid(cp/150) still has a slope.
The generator's default opening gate (|eval| <= 150, no "odds") keeps only
those that really are balanced.

Imbalances (side A gives the first, side B the second):
  minor_for_pawns   N or B          for 2-3 pawns
  exchange          R               for N or B (+ 0-1 pawn)
  queen_for_pieces  Q               for R + minor, or R + R
  rook_for_minors   N + B / B + B   for R (+ 0-1 pawn)
  minor_swap        N               for B (piece down each, unbalanced pair)

--castle SHARE of starts use one of the 18 back ranks with the king on e and
rooks on a and h, so ordinary KQkq castling is legal (the engine has no 960
castling); the rest are any of the 960 with castling '-'.
"""

import argparse
import collections
import random
import sys

import chess

CASTLE_IDS = []
for _n in range(960):
    _b = chess.Board.from_chess960_pos(_n)
    if (_b.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
            and _b.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE)
            and _b.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE)):
        CASTLE_IDS.append(_n)

IMBALANCES = ("minor_for_pawns", "exchange", "queen_for_pieces", "rook_for_minors", "minor_swap")


def take(rng, board, side, kind, count=1):
    squares = list(board.pieces(kind, side))
    if len(squares) < count:
        return False
    for sq in rng.sample(squares, count):
        board.remove_piece_at(sq)
    return True


def take_pawns(rng, board, side, count):
    return take(rng, board, side, chess.PAWN, count)


def minor(rng):
    return rng.choice([chess.KNIGHT, chess.BISHOP])


def apply(rng, board, kind, a):
    b = not a
    if kind == "minor_for_pawns":
        return take(rng, board, a, minor(rng)) and take_pawns(rng, board, b, rng.choice([2, 3]))
    if kind == "exchange":
        return (take(rng, board, a, chess.ROOK) and take(rng, board, b, minor(rng))
                and take_pawns(rng, board, b, rng.choice([0, 1])))
    if kind == "queen_for_pieces":
        if not take(rng, board, a, chess.QUEEN):
            return False
        if rng.random() < 0.5:
            return take(rng, board, b, chess.ROOK) and take(rng, board, b, minor(rng))
        return take(rng, board, b, chess.ROOK, 2)
    if kind == "rook_for_minors":
        pair = rng.choice([(chess.KNIGHT, chess.BISHOP), (chess.BISHOP, chess.BISHOP), (chess.KNIGHT, chess.KNIGHT)])
        ok = all(take(rng, board, a, p) for p in pair)
        return ok and take(rng, board, b, chess.ROOK) and take_pawns(rng, board, b, rng.choice([0, 1]))
    if kind == "minor_swap":
        return take(rng, board, a, chess.KNIGHT) and take(rng, board, b, chess.BISHOP)
    raise ValueError(kind)


def make_position(rng, plies, castle_share):
    castle = rng.random() < castle_share
    board = chess.Board.from_chess960_pos(rng.choice(CASTLE_IDS) if castle else rng.randint(0, 959))
    board.chess960 = False
    kind = rng.choice(IMBALANCES)
    side = rng.choice([chess.WHITE, chess.BLACK])
    if not apply(rng, board, kind, side):
        return None
    board.castling_rights = board.clean_castling_rights() if castle else chess.BB_EMPTY
    for _ in range(plies):
        legal = list(board.legal_moves)
        if not legal or board.is_game_over():
            return None
        board.push(rng.choice(legal))
    if board.is_game_over() or not board.is_valid():
        return None
    board.castling_rights = board.clean_castling_rights()
    return board.fen(), kind, castle


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--count", type=int, default=40000)
    parser.add_argument("--plies", type=int, default=4)
    parser.add_argument("--castle", type=float, default=0.5, help="share of starts with KQkq castling")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    seen, positions = set(), []
    kinds, castles = collections.Counter(), collections.Counter()
    attempts = 0
    while len(positions) < args.count and attempts < args.count * 20:
        attempts += 1
        made = make_position(rng, args.plies, args.castle)
        if made is None or made[0] in seen:
            continue
        fen, kind, castle = made
        seen.add(fen)
        positions.append(fen)
        kinds[kind] += 1
        castles["castling" if castle else "no castling"] += 1

    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# piece-down Chess960 with compensation, harness/nnue/gap960_book.py\n")
        out.write("# {} positions, plies {}, castle share {}, seed {}\n".format(
            len(positions), args.plies, args.castle, args.seed))
        out.write("# imbalances: {}\n# castling: {}\n".format(dict(kinds), dict(castles)))
        for fen in positions:
            out.write(fen + "\n")
    print("wrote {} positions to {}".format(len(positions), args.out))
    print("imbalances:", dict(kinds))
    print("castling:", dict(castles), " castle-legal back ranks:", len(CASTLE_IDS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
