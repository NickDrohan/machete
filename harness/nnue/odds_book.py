"""Starting positions with one piece removed, for an odds training run.

    python harness/nnue/odds_book.py --out odds.epd

LeelaKnightOdds and LeelaRookOdds play only these positions, with a network
that has seen the piece missing. The book is the four knight odds and the
four rook odds, both colours. A missing queen is not here: the generator's
odds gate still refuses a start that far from equal.

Castling rights follow the rooks that remain. Knights do not affect them.
"""

import argparse

# piece, square, fen after removing it, side who is down
LINES = [
    ("N", "b1", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/R1BQKBNR w KQkq - 0 1"),
    ("N", "g1", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"),
    ("N", "b8", "r1bqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
    ("N", "g8", "rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
    ("R", "a1", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/1NBQKBNR w Kkq - 0 1"),
    ("R", "h1", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1 w Qkq - 0 1"),
    ("R", "a8", "1nbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQk - 0 1"),
    ("R", "h8", "rnbqkbn1/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQq - 0 1"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# knight and rook odds. gen odds  (opening gate 700)\n")
        for kind, square, fen in LINES:
            handle.write(fen + "\n")
    print("{} positions -> {}".format(len(LINES), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
