"""Check that the engine's network evaluation matches the reference, exactly.

    python harness/nnue/agree.py ENGINE NET --positions 300

Two implementations of the same integer arithmetic should never differ by one
centipawn, so this compares them for equality rather than closeness. The
positions come from random games, which is the cheapest way to reach lopsided
material, promotions and bare kings - the shapes where a quantized network
saturates and an implementation that clips or overflows differently shows it.
"""

import argparse
import os
import random
import subprocess
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference


def positions(count, seed):
    """Random-game positions, plus the start position and a few bare endings."""
    yield chess.Board()
    yield chess.Board("8/8/8/4k3/8/8/4K3/8 w - - 0 1")
    yield chess.Board("8/P7/8/8/8/8/7p/K6k w - - 0 1")
    rng = random.Random(seed)
    made = 0
    while made < count:
        board = chess.Board()
        for _ in range(rng.randint(1, 120)):
            moves = list(board.legal_moves)
            if not moves:
                break
            board.push(rng.choice(moves))
            if rng.random() < 0.12:
                yield board.copy()
                made += 1
                if made >= count:
                    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("net")
    parser.add_argument("--positions", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    net = reference.load(args.net)
    engine = os.path.abspath(args.engine)
    net_path = os.path.abspath(args.net)

    checked = 0
    for board in positions(args.positions, args.seed):
        fen = board.fen()
        expected = reference.forward(
            net, reference.accumulate(net, reference.pieces_of(board)),
            reference.WHITE if board.turn == chess.WHITE else reference.BLACK)
        out = subprocess.check_output([engine, "nnue", net_path] + fen.split())
        got = int(out.decode("ascii").strip())
        if got != expected:
            print("MISMATCH at {}".format(fen))
            print("  reference {}  engine {}".format(expected, got))
            return 1
        checked += 1
        sys.stdout.write("\r{} positions agree".format(checked))
        sys.stdout.flush()
    print("\n{} positions: the engine and the reference agree exactly".format(checked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
