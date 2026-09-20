"""Differential perft: compare mate's `divide` against python-chess.

    python harness/perft_diff.py ENGINE --fen FEN --depth N     one position
    python harness/perft_diff.py ENGINE --random 300 --depth 3  random positions

Random positions come from random legal games (seeded, so failures reproduce).
On a mismatch the first differing root move is descended into until the exact
position and move that disagree are found. Exit status is 0 only if every
position agrees.

Requires python-chess; on this machine that is the Python 3.7 install.
"""

import argparse
import os
import random
import subprocess
import sys

import chess


def reference_divide(board, depth):
    counts = {}
    for move in board.legal_moves:
        board.push(move)
        counts[move.uci()] = perft(board, depth - 1)
        board.pop()
    return counts


def perft(board, depth):
    if depth == 0:
        return 1
    if depth == 1:
        return board.legal_moves.count()
    total = 0
    for move in board.legal_moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


def engine_divide(engine, fen, depth):
    out = subprocess.run([engine, "divide", str(depth)] + fen.split(),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, check=False)
    if out.returncode != 0:
        raise RuntimeError("engine failed on {}: {}".format(fen, out.stderr.strip()))
    counts = {}
    for line in out.stdout.splitlines():
        move, count = line.split()
        if move != "total":
            counts[move] = int(count)
    return counts


def locate(engine, board, depth):
    """Descend until the disagreement is at depth 1; return a description."""
    ours = engine_divide(engine, board.fen(), depth)
    theirs = reference_divide(board, depth)
    extra = sorted(set(ours) - set(theirs))
    missing = sorted(set(theirs) - set(ours))
    if extra or missing:
        return "{}\n  illegal moves generated: {}\n  legal moves missed: {}".format(
            board.fen(), extra or "none", missing or "none")
    for move, count in sorted(ours.items()):
        if count != theirs[move]:
            board.push(chess.Move.from_uci(move))
            try:
                return locate(engine, board, depth - 1)
            finally:
                board.pop()
    return None


def random_position(rng):
    board = chess.Board()
    for _ in range(rng.randint(4, 80)):
        moves = list(board.legal_moves)
        if not moves:
            break
        board.push(rng.choice(moves))
    if board.is_game_over():
        board.pop()
    return board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--fen")
    parser.add_argument("--random", type=int, default=0)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    args.engine = os.path.abspath(args.engine)

    boards = []
    if args.fen:
        boards.append(chess.Board(args.fen))
    rng = random.Random(args.seed)
    boards.extend(random_position(rng) for _ in range(args.random))
    if not boards:
        parser.error("give --fen or --random")

    for n, board in enumerate(boards, 1):
        problem = locate(args.engine, board, args.depth)
        if problem:
            print("mismatch in position {} of {}:\n  {}".format(n, len(boards), problem))
            return 1
    print("{} position(s) agree with python-chess at depth {}".format(len(boards), args.depth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
