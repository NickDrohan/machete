"""Check that generated records mean what the trainer thinks they mean.

    python harness/nnue/verify.py data/train.bin --sample 20000

A record is a packed board: a piece count, two parallel arrays, a side to move
and a score. Nothing about it is self-describing, so a wrong offset or a
swapped index produces a file that loads cleanly, trains smoothly and teaches
the network a game that is not chess. The only symptom is an engine that plays
worse than it should, months later, for no visible reason.

So each sampled record is decoded back into a position and checked against
python-chess: the pieces have to form a legal board, the counts have to agree,
and the feature indices the trainer computes have to name the same squares the
board actually has. The last of those is the real test - it exercises the same
`feature_indices` the trainer uses rather than a reimplementation of it, so a
bug in the perspective flip cannot hide behind a matching reimplementation.

That only proves the file is self-consistent, though. A generator that encoded
every position with the colours swapped would write records the decoder reads
back exactly as the generator meant them, and nothing above would notice. So
--roundtrip drives the generator's own encoder with boards python-chess built
and checks the position survives the trip. That is the check with an outside
witness, and it is the one worth running before a long generation run.
"""

import argparse
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD, INPUTS, feature_index, WHITE, BLACK


def decode(row):
    """The record as a python-chess board."""
    board = chess.Board(None)
    for i in range(int(row["count"])):
        code = int(row["pieces"][i])
        square = int(row["squares"][i])
        board.set_piece_at(square, chess.Piece(code % 6 + 1,
                                               chess.WHITE if code < 6 else chess.BLACK))
    board.turn = chess.WHITE if int(row["stm"]) == 0 else chess.BLACK
    return board


def trainer_indices(row):
    """What the trainer will feed the network for this record.

    Imported from the module the trainer uses rather than rewritten, so that a
    bug there is caught here instead of being reproduced faithfully in both.
    """
    import reference
    batch = np.zeros(1, dtype=RECORD)
    batch[0] = row
    us, them = reference.feature_indices(batch)
    return us[0], them[0]


def check(row):
    """Return a complaint, or None if the record is sound."""
    count = int(row["count"])
    if count < 2 or count > 32:
        return "piece count {}".format(count)
    for i in range(count):
        if int(row["pieces"][i]) > 11:
            return "piece code {}".format(int(row["pieces"][i]))
        if int(row["squares"][i]) > 63:
            return "square {}".format(int(row["squares"][i]))
    if len(set(int(row["squares"][i]) for i in range(count))) != count:
        return "two pieces on one square"

    board = decode(row)
    if len(board.piece_map()) != count:
        return "decoded {} pieces, record says {}".format(len(board.piece_map()), count)
    if not board.is_valid():
        return "illegal position: {}".format(board.status())

    # the trainer's own feature indices must name the pieces actually present
    us, them = trainer_indices(row)
    side = WHITE if board.turn == chess.WHITE else BLACK
    expected_us, expected_them = set(), set()
    for square, piece in board.piece_map().items():
        colour = WHITE if piece.color == chess.WHITE else BLACK
        kind = piece.piece_type - 1
        expected_us.add(feature_index(side, colour, kind, square))
        expected_them.add(feature_index(side ^ 1, colour, kind, square))
    got_us = set(int(v) for v in us if int(v) != INPUTS)
    got_them = set(int(v) for v in them if int(v) != INPUTS)
    if got_us != expected_us:
        return "side-to-move features disagree with the board"
    if got_them != expected_them:
        return "opponent features disagree with the board"
    if int(row["result"]) > 2:
        return "result {}".format(int(row["result"]))
    return None


def roundtrip(count, seed):
    """Encode boards python-chess made, decode them, and demand they match."""
    import random
    import gen
    rng = random.Random(seed)
    for n in range(count):
        board = chess.Board()
        for _ in range(rng.randint(0, 80)):
            moves = list(board.legal_moves)
            if not moves:
                break
            board.push(rng.choice(moves))
        if board.is_game_over():
            continue
        row = gen.encode(board, 12, 1)
        back = decode(row)
        if back.piece_map() != board.piece_map():
            return "position {} did not survive encoding: {}".format(n, board.fen())
        if back.turn != board.turn:
            return "side to move flipped: {}".format(board.fen())
        problem = check(row)
        if problem:
            return "encoded position rejected: {} ({})".format(problem, board.fen())
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", nargs="?")
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--show", type=int, default=5)
    parser.add_argument("--roundtrip", type=int, default=0,
                        help="drive the generator's encoder with this many boards")
    args = parser.parse_args()

    if args.roundtrip:
        problem = roundtrip(args.roundtrip, args.seed)
        if problem:
            print("ROUNDTRIP FAILED: {}".format(problem))
            return 1
        print("{} positions survive encode and decode intact".format(args.roundtrip))
        if not args.data:
            return 0

    data = np.memmap(args.data, dtype=RECORD, mode="r")
    rng = np.random.RandomState(args.seed)
    picks = rng.choice(len(data), min(args.sample, len(data)), replace=False)

    complaints = []
    for n, index in enumerate(picks):
        problem = check(data[index])
        if problem:
            complaints.append((int(index), problem))
            if len(complaints) >= args.show:
                break
        if n % 500 == 0:
            sys.stdout.write("\r{}/{} checked".format(n, len(picks)))
            sys.stdout.flush()

    print("\r{:,} of {:,} records checked".format(len(picks), len(data)))
    if complaints:
        for index, problem in complaints:
            print("  record {}: {}".format(index, problem))
        return 1
    print("every sampled record decodes to a legal position whose features match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
