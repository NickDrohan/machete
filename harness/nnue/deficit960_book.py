"""Chess960 starts where one side is at a real disadvantage, in many shapes.

    python harness/nnue/deficit960_book.py --out E:/machete/books/deficit960.epd [--count 40000]
        [--workers 8] [--nodes 30000] [--plies 4] [--castle 0.5] [--seed 1]

The owner's rule for this corpus: every game starts with one side worse off,
and what the disadvantage looks like is not fixed. The first handicap book
(one side a clean knight, bishop or two-three pawns down) starts about four
pawns down and only gets worse, so over half of its labels are pinned at lost
or won and the network learns little from them (ODDS-LOSSES: flattened piece
values). The compensated book (gap960) makes real trades but keeps only the
starts Stockfish calls balanced, so there is no disadvantage left.

This book sits between them. A start is one of the 960 back ranks with a
trade applied: one side gives up some material, the other gives up less (or
nothing). The menu is wide on purpose - a pawn or two, a minor for pawns, the
exchange with or without a pawn back, a rook for pawns, the queen for a rook
and a minor, for a knight, a bishop and pawns, for two minors, two minors for
a rook, the bishop pair for a knight and a pawn - and a few random moves are
played. Stockfish then says how much worse the worse side is, and the start is
kept only if that is a real but not decisive deficit:

    slight   60 to 120 centipawns
    clear   120 to 200
    heavy   200 to 350

in equal thirds, so the games are fights the worse side can still make
something of, and the labels stay on the sloped part of sigmoid(cp/150). Who
is worse is whoever Stockfish says, not who the menu intended: a queen for
two rooks can come out either way, and both are fine.

--castle of the starts use one of the 18 back ranks with the king on e and
rooks on a and h, with ordinary castling rights for the rooks still there
(the engine has no 960 castling); the rest are any of the 960 with none.
What each start is (the trade, the worse side, the deficit) is written beside
the book as a .tsv.
"""
import argparse
import collections
import multiprocessing
import os
import random
import sys

import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

P, N, B, R, Q = chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN
MINOR = "minor"  # a knight or a bishop, drawn at random
# (name, what the giving side loses, what the other side loses)
MENU = [
    ("pawn", [P], []),
    ("two_pawns", [P, P], []),
    ("three_pawns", [P, P, P], []),
    ("minor_for_pawn", [MINOR], [P]),
    ("minor_for_two_pawns", [MINOR], [P, P]),
    ("minor_for_three_pawns", [MINOR], [P, P, P]),
    ("minor", [MINOR], []),
    ("exchange", [R], [MINOR]),
    ("exchange_for_pawn", [R], [MINOR, P]),
    ("exchange_for_two_pawns", [R], [MINOR, P, P]),
    ("rook_for_three_pawns", [R], [P, P, P]),
    ("rook_for_four_pawns", [R], [P, P, P, P]),
    ("queen_for_rook_minor", [Q], [R, MINOR]),
    ("queen_for_rook_minor_pawn", [Q], [R, MINOR, P]),
    ("queen_for_two_rooks", [Q], [R, R]),
    ("queen_for_knight_bishop_pawns", [Q], [N, B, P, P]),
    ("queen_for_two_minors_pawn", [Q], [MINOR, MINOR, P]),
    ("queen_for_three_minors", [Q], [MINOR, MINOR, MINOR]),
    ("two_minors_for_rook", [MINOR, MINOR], [R]),
    ("two_minors_for_rook_pawn", [MINOR, MINOR], [R, P]),
    ("two_minors_for_rook_two_pawns", [MINOR, MINOR], [R, P, P]),
    ("bishop_pair_for_knight_pawn", [B, B], [B, N, P]),
    ("knight_for_bishop", [N], [B]),
    ("rook_minor_for_queen_pawn", [R, MINOR], [Q, P]),
]
BANDS = (("slight", 60, 120), ("clear", 120, 200), ("heavy", 200, 350))
CASTLE_IDS = [n for n in range(960) if (lambda b: b.piece_at(chess.E1) == chess.Piece(chess.KING, True)
                                        and b.piece_at(chess.A1) == chess.Piece(chess.ROOK, True)
                                        and b.piece_at(chess.H1) == chess.Piece(chess.ROOK, True))(chess.Board.from_chess960_pos(n))]


def remove(rng, board, side, kinds):
    for kind in kinds:
        if kind == MINOR:
            kind = rng.choice([N, B])
            if not board.pieces(kind, side):
                kind = B if kind == N else N
        squares = list(board.pieces(kind, side))
        if not squares:
            return False
        board.remove_piece_at(rng.choice(squares))
    return True


def candidate(rng, plies, castle_share):
    """A start with a trade applied and a few random moves played, or None."""
    castle = rng.random() < castle_share
    board = chess.Board.from_chess960_pos(rng.choice(CASTLE_IDS) if castle else rng.randrange(960))
    name, give, pay = rng.choice(MENU)
    giver = rng.choice([chess.WHITE, chess.BLACK])
    if not remove(rng, board, giver, give) or not remove(rng, board, not giver, pay):
        return None
    rights = ""
    if castle:  # ordinary rights, for the rooks that are still at home
        for side, rank, letters in ((chess.WHITE, 0, "KQ"), (chess.BLACK, 7, "kq")):
            if board.piece_at(chess.square(7, rank)) == chess.Piece(R, side):
                rights += letters[0]
            if board.piece_at(chess.square(0, rank)) == chess.Piece(R, side):
                rights += letters[1]
    board = chess.Board(board.board_fen() + " w " + (rights or "-") + " - 0 1")
    if not board.is_valid():
        return None
    for _ in range(plies):
        moves = [m for m in board.legal_moves if not board.is_capture(m)]
        if not moves:
            return None
        board.push(rng.choice(moves))
    if board.is_game_over() or board.is_check():
        return None
    return name, chess.Board(board.fen())


def worker(args):
    seed, want, plies, castle_share, nodes = args
    rng = random.Random(seed)
    sf = panel.open_engine("Stockfish", 32)
    limit = chess.engine.Limit(nodes=nodes)
    kept = {band[0]: [] for band in BANDS}
    tried = collections.Counter()
    while any(len(v) < want for v in kept.values()):
        got = candidate(rng, plies, castle_share)
        if got is None:
            continue
        name, board = got
        tried["scored"] += 1
        score = sf.analyse(board, limit)["score"].white().score(mate_score=5000)
        deficit = abs(score)
        for band, lo, hi in BANDS:
            if lo <= deficit < hi and len(kept[band]) < want:
                worse = "white" if score < 0 else "black"
                kept[band].append((board.fen(), name, deficit, worse, band, bool(board.castling_rights)))
                break
    panel.quiet_quit(sf)
    return [x for v in kept.values() for x in v], tried["scored"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--count", type=int, default=40000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--nodes", type=int, default=30000)
    parser.add_argument("--plies", type=int, default=4)
    parser.add_argument("--castle", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    per = -(-args.count // (args.workers * len(BANDS)))
    with multiprocessing.Pool(args.workers) as pool:
        parts = pool.map(worker, [(args.seed * 1000 + k, per, args.plies, args.castle, args.nodes) for k in range(args.workers)])
    rows = [x for part, _ in parts for x in part]
    scored = sum(n for _, n in parts)
    seen, unique = set(), []
    for row in rows:
        key = " ".join(row[0].split()[:4])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    random.Random(args.seed).shuffle(unique)
    kinds = collections.Counter(r[1] for r in unique)
    bands = collections.Counter(r[4] for r in unique)
    sides = collections.Counter(r[3] for r in unique)
    castles = collections.Counter("castling" if r[5] else "no castling" for r in unique)
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# Chess960 starts with one side at a real disadvantage, harness/nnue/deficit960_book.py\n")
        out.write("# %d positions, plies %d, castle share %s, Stockfish at %d nodes, seed %d; %d candidates scored\n" % (
            len(unique), args.plies, args.castle, args.nodes, args.seed, scored))
        out.write("# deficit of the worse side: %s\n# worse side: %s\n# castling: %s\n# trades: %s\n" % (
            dict(bands), dict(sides), dict(castles), dict(kinds.most_common())))
        for fen, _, _, _, _, _ in unique:
            out.write(fen + "\n")
    # what each start is, beside the book, so the book itself is positions only
    with open(os.path.splitext(args.out)[0] + ".tsv", "w", encoding="utf-8", newline="\n") as notes:
        notes.write("fen\ttrade\tworse\tdeficit_cp\tband\tcastling\n")
        for fen, name, deficit, worse, band, castle in unique:
            notes.write("%s\t%s\t%s\t%d\t%s\t%d\n" % (fen, name, worse, deficit, band, castle))
    print("%d positions (%d candidates scored) -> %s" % (len(unique), scored, args.out))
    print("deficit:", dict(bands), "| worse side:", dict(sides), "| castling:", dict(castles))
    for k, v in kinds.most_common():
        print("  %-32s %5d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
