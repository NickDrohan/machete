"""Build an opening book out of games that were actually played.

    python harness/nnue/book.py --out data/book.epd \
        --pgn "C:/.../arena_3.5.1/Tournaments" --pgn "D:/.../ViennaStomp_2025.pgn"

Self-play from the initial position visits the same handful of structures
forever, and self-play from random moves visits nonsense. Real games from a
varied archive sit in between: they reach positions someone chose to play, over
a far wider range of openings than any one engine would pick for itself.

Gambit archives are worth more here than their game count suggests. A gambit is
material given up for compensation, which is the one thing a material-and-
squares evaluation cannot see, so those positions carry the knowledge the
network most needs and the hand-written evaluation most lacks.

Positions are taken a few moves in, deduplicated, and kept only if both sides
still have real material - an archive contains plenty of games that were
already decided by move ten, and those teach nothing.
"""

import argparse
import collections
import os
import random
import sys

import chess
import chess.pgn


def pgn_files(paths):
    for entry in paths:
        if os.path.isdir(entry):
            for root, _, names in os.walk(entry):
                for name in names:
                    if name.lower().endswith(".pgn"):
                        yield os.path.join(root, name)
        elif entry.lower().endswith(".pgn"):
            yield entry


def harvest(path, plies, per_game, seen, rng, material):
    out = []
    with open(path, errors="ignore") as handle:
        while True:
            try:
                game = chess.pgn.read_game(handle)
            except Exception:
                break
            if game is None:
                break
            board = game.board()
            taken = 0
            for index, move in enumerate(game.mainline_moves()):
                board.push(move)
                if index + 1 < plies[0]:
                    continue
                if index + 1 > plies[1] or taken >= per_game:
                    break
                if rng.random() > 0.5:
                    continue
                if len(board.piece_map()) < material:
                    break
                key = board.board_fen() + (" w" if board.turn else " b")
                if key in seen:
                    continue
                seen.add(key)
                out.append(board.fen())
                taken += 1
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pgn", action="append", required=True,
                        help="a .pgn file or a directory of them; repeatable")
    parser.add_argument("--out", default="data/book.epd")
    parser.add_argument("--min-ply", type=int, default=8)
    parser.add_argument("--max-ply", type=int, default=24)
    parser.add_argument("--per-game", type=int, default=2)
    parser.add_argument("--min-pieces", type=int, default=24)
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    seen = set()
    positions = []
    sources = collections.Counter()
    for path in pgn_files(args.pgn):
        found = harvest(path, (args.min_ply, args.max_ply), args.per_game,
                        seen, rng, args.min_pieces)
        positions.extend(found)
        sources[os.path.basename(os.path.dirname(path)) or "."] += len(found)
        sys.stdout.write("\r{:,} positions from {} files".format(
            len(positions), len(sources)))
        sys.stdout.flush()
        if len(positions) >= args.limit:
            break

    rng.shuffle(positions)
    positions = positions[:args.limit]
    directory = os.path.dirname(os.path.abspath(args.out))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(args.out, "w") as handle:
        for fen in positions:
            handle.write(fen + "\n")
    print("\n{:,} unique opening positions -> {}".format(len(positions), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
