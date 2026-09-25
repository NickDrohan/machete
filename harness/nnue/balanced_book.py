"""Pick balanced starting positions for a match that is meant to be fair.

    python harness/nnue/balanced_book.py data/book.epd harness/books/balanced_200.epd --count 200

A match between two engines should be decided by the engines, not by the
openings. Four random plies decided two games outright - 1. f3 e5 2. g4 Qh4#
twice - and more often hand one side a position that is lost before either
engine has thought. So a showcase match starts from positions that people
actually reached in real games, which Stockfish rates as level.

Each candidate is scored by Stockfish at a fixed node count rather than a fixed
time, so the result does not depend on how busy the machine is, and kept only
if the side to move is within `--window` centipawns of equal. One position per
pawn structure is kept, so the book is not two hundred versions of the same
opening. Every position is played twice in a match, once with each engine on
each side, so whatever small edge a position does carry cancels out.
"""

import argparse
import os
import random
import sys
import time

import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel


def pawn_structure(board):
    return (int(board.pieces(chess.PAWN, chess.WHITE)),
            int(board.pieces(chess.PAWN, chess.BLACK)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--window", type=int, default=50, help="centipawns from level")
    parser.add_argument("--nodes", type=int, default=300000)
    parser.add_argument("--seed", type=int, default=20)
    args = parser.parse_args()

    with open(args.source) as handle:
        candidates = [line.strip() for line in handle if line.strip()]
    random.Random(args.seed).shuffle(candidates)

    judge = panel.open_engine("Stockfish", 64)
    kept, seen, looked, started = [], set(), 0, time.time()
    try:
        for fen in candidates:
            if len(kept) >= args.count:
                break
            board = chess.Board(fen)
            if not board.is_valid() or board.is_game_over():
                continue
            structure = pawn_structure(board)
            if structure in seen:
                continue
            looked += 1
            score = judge.analyse(board, chess.engine.Limit(nodes=args.nodes))["score"].relative
            if score.is_mate() or abs(score.score()) > args.window:
                continue
            seen.add(structure)
            kept.append((fen, score.score()))
            if len(kept) % 25 == 0:
                print("{} kept of {} looked at".format(len(kept), looked))
                sys.stdout.flush()
    finally:
        panel.quiet_quit(judge)

    folder = os.path.dirname(os.path.abspath(args.out))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(args.out, "w", newline="\n") as handle:
        handle.write("# {} balanced starting positions, from {}\n".format(len(kept), args.source))
        handle.write("# kept if Stockfish at {:,} nodes puts the side to move within {} cp of level;\n"
                     .format(args.nodes, args.window))
        handle.write("# one position per pawn structure. Written by harness/nnue/balanced_book.py\n")
        for fen, _ in kept:
            handle.write(fen + "\n")
    scores = [s for _, s in kept]
    print("\n{} positions written to {} ({} looked at, {:.0f} s)".format(
        len(kept), args.out, looked, time.time() - started))
    if scores:
        print("Stockfish scores for the side to move: mean {:+.1f}, range {:+d} to {:+d}".format(
            sum(scores) / float(len(scores)), min(scores), max(scores)))
    return 0 if len(kept) >= args.count else 1


if __name__ == "__main__":
    sys.exit(main())
