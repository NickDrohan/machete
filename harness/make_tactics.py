"""Generate a tactics fixture of positions with a verified forced mate.

    python harness/make_tactics.py --mate-in 2 --count 12 > fixtures/mate2.epd

Positions come from random legal games. Each candidate is proved exhaustively
with python-chess: there must be a forced mate in exactly N for the side to
move, and the mating first move must be unique, so "the engine found a
different good move" can never be the reason a gate fails.

Output is one position per line: FEN;bm=<uci>;mate=<n>
"""

import argparse
import random
import sys

import chess


def mates_in(board, n):
    """Moves that force mate in exactly n for the side to move."""
    found = []
    for move in board.legal_moves:
        board.push(move)
        try:
            if n == 1:
                if board.is_checkmate():
                    found.append(move)
            elif not board.is_game_over() and defender_cannot_escape(board, n):
                found.append(move)
        finally:
            board.pop()
    return found


def defender_cannot_escape(board, n):
    """After the attacker's move, every defence must allow mate in n-1."""
    for reply in board.legal_moves:
        board.push(reply)
        try:
            if board.is_game_over():
                return False
            if not mates_in(board, n - 1):
                return False
        finally:
            board.pop()
    return True


def shorter_mate_exists(board, n):
    return any(mates_in(board, k) for k in range(1, n))


def mated_game(rng, max_plies=220):
    """A random game that ended in checkmate, or None."""
    board = chess.Board()
    for _ in range(max_plies):
        moves = list(board.legal_moves)
        if not moves:
            break
        # prefer checks and captures, so random play reaches mates far more often
        forcing = [m for m in moves if board.is_capture(m) or board.gives_check(m)]
        pick = forcing if forcing and rng.random() < 0.7 else moves
        board.push(rng.choice(pick))
        if board.is_game_over():
            break
    if board.is_checkmate():
        return board
    return None


def candidate(rng, mate_in):
    """A position `2*mate_in - 1` plies before a random game's checkmate."""
    board = mated_game(rng)
    if board is None:
        return None
    for _ in range(2 * mate_in - 1):
        if not board.move_stack:
            return None
        board.pop()
    return board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mate-in", type=int, default=2)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--tries", type=int, default=20000)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    written = 0
    for _ in range(args.tries):
        if written >= args.count:
            break
        board = candidate(rng, args.mate_in)
        if board is None or board.is_game_over() or board.is_check():
            continue
        if shorter_mate_exists(board, args.mate_in):
            continue
        movers = mates_in(board, args.mate_in)
        if len(movers) != 1:
            continue
        print("{};bm={};mate={}".format(board.fen(), movers[0].uci(), args.mate_in))
        written += 1

    if written < args.count:
        sys.stderr.write("only found {} of {} positions\n".format(written, args.count))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
