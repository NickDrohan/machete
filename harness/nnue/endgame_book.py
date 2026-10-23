"""A data-generation book of endings just above the tablebases, from LAION's engine games.

    python harness/nnue/endgame_book.py --laion E:/chess-data/laion-chess --out book.epd
        [--files 1] [--games 300000] [--low 9] [--high 14] [--seed 1] [--exclude test.epd]

On lichess the bot's online tablebase plays every position of 8 men or fewer perfectly; the endings it
still has to find its own way through are the ones just above that: two or three pieces and a handful of
pawns, where a plan can run for forty moves (the owner, 2026-10-22). Each game contributes the position
where its men first number --high or fewer (and at least --low), when it is not in check and the side to
move has a legal move. Generate from this book with "convert", so the games are played out to the end
and the moves that turn the plan into a result are in the data.
"""
import argparse
import glob
import os
import random
import sys

import chess
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--laion", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--files", type=int, default=1)
    parser.add_argument("--games", type=int, default=300000, help="games read from each file (one holds about 2M)")
    parser.add_argument("--low", type=int, default=9)
    parser.add_argument("--high", type=int, default=14)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--exclude", default="")
    args = parser.parse_args()

    skip = set()
    if args.exclude:
        for line in open(args.exclude, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                skip.add(" ".join(line.split()[:4]))
    found = {}
    for path in sorted(glob.glob(os.path.join(args.laion, "*.parquet")))[:args.files]:
        moves = pq.read_table(path, columns=["Moves"]).column("Moves")
        for k in range(min(len(moves), args.games)):
            board = chess.Board()
            for u in moves[k].as_py():
                board.push(chess.Move.from_uci(u))
                men = chess.popcount(board.occupied)
                if men < args.low:
                    break
                if men <= args.high:
                    if not board.is_check() and not board.is_game_over():
                        epd = " ".join(board.fen().split()[:4])
                        if epd not in skip:
                            found[epd] = board.fen()
                    break
        del moves
        print("%s: %d positions so far" % (os.path.basename(path), len(found)), flush=True)
    lines = list(found.values())
    random.Random(args.seed).shuffle(lines)
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# endings of %d to %d men, the first such position of each LAION self-play game\n" % (args.low, args.high))
        for fen in lines:
            out.write(fen + "\n")
    print("%d positions -> %s" % (len(lines), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
