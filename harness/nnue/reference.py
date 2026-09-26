"""The definition of machete's network file, and an independent way to read it.

This module is the reference the Mach implementation is checked against. It is
deliberately the slow, obvious version: numpy arrays, integer arithmetic spelled
out, no fused anything. When `src/nnue.mach` and this file disagree, this file is
right by construction and the engine is wrong.

The network is a perspective net:

    KING_BUCKETS x 768 inputs -> HIDDEN (per perspective, shared weights)
    concat[side-to-move, other side] = 2 * HIDDEN -> 1, through one of BUCKETS
    output layers chosen by the number of pieces on the board

Each side reads the 768 inputs of its own king's zone (see orient): the
board is mirrored left-right to put that king on files a-d, and its square
then picks one of KING_BUCKETS zones.

The engine fixes HIDDEN at compile time and refuses a file of another width;
this reader takes the width from the file, so one reference serves every
build.

A feature is (colour relative to the perspective, piece kind, square relative to
the perspective). Seen from black, colours swap and squares flip vertically, so
one set of weights serves both sides and the network never has to learn "white
is the one moving up the board" twice.

Everything is stored quantized. Hidden values live on a scale where QA == 1.0
and output weights on a scale where QB == 1.0, so the dot product comes out on
QA*QB and one divide at the end turns it into centipawns.

    python reference.py random out.nnue --seed 1     # a random net, for gates
    python reference.py eval net.nnue "FEN"          # centipawns, side to move
    python reference.py dump net.nnue                # header fields
"""

import argparse
import struct
import sys

import numpy as np

MAGIC = b"MCHNNUE3"
INPUTS = 768       # per king zone
KING_BUCKETS = 8   # king zones per side; the file holds KING_BUCKETS * INPUTS rows
HIDDEN = 256       # the width a new file gets unless told otherwise
BUCKETS = 8        # output layers, by (pieces - 2) // 4
QA = 255           # hidden-layer scale: a clipped-relu output of 1.0 is QA
QB = 64            # output-weight scale
SCALE = 400        # network output of 1.0 is SCALE centipawns; see set_scale
HEADER = 32

WHITE, BLACK = 0, 1

# one generated position on disk: the pieces on the board, whose turn it is,
# what the search thought, and how the game ended. 70 bytes. It lives here
# rather than in gen.py so that the trainer, which runs on a Python without
# python-chess, can read it without dragging a chess library in.
RECORD = np.dtype([
    ("stm", "u1"),          # 0 white to move, 1 black
    ("count", "u1"),        # pieces on the board
    ("pieces", "u1", 32),   # colour * 6 + kind, as the engine codes them
    ("squares", "u1", 32),
    ("score", "i2"),        # centipawns, from the side to move
    ("result", "u1"),       # 0 side to move lost, 1 drew, 2 won
    ("engine", "u1"),       # which teacher scored it; their centipawn scales differ
])


def set_scale(value):
    """Change the centipawn scale the next save() will record.

    The scale decides how a teacher's centipawns become a training target, and
    so what the network is pushed hardest to get right: a small scale makes the
    sigmoid steep and concentrates capacity near equality, a large one flattens
    it and spends capacity on positions already decided. Fitting it against
    measured outcomes gave 150 for Stockfish, not the 400 used here originally.
    """
    global SCALE
    SCALE = int(value)


def orient(perspective, king):
    """How one side reads the board with its own king on `king`.

    Returns zone * 2 + mirror. Seen from that side (black's view flipped
    vertically), the board is mirrored left-right when the king is on files
    e-h, and the king's square then falls in one of eight zones:

        rank 1: a-b 0, c-d 1      rank 2: a-b 2, c-d 3
        ranks 3-4: a-b 4, c-d 5   ranks 5-8: a-b 6, c-d 7
    """
    rel = king ^ 56 if perspective == BLACK else king
    mirror = 1 if rel & 7 >= 4 else 0
    if mirror:
        rel ^= 7
    rank = rel >> 3
    zone = 1 if rel & 7 >= 2 else 0
    if rank == 1:
        zone += 2
    elif rank in (2, 3):
        zone += 4
    elif rank >= 4:
        zone += 6
    return zone * 2 + mirror


# orient() for every (perspective, king square), for the vectorised paths
ORIENT = np.array([[orient(side, square) for square in range(64)] for side in (WHITE, BLACK)])


def feature_index(perspective, colour, kind, square, king):
    """Where (colour, kind, square) lands in the inputs, seen from one side
    whose own king stands on `king`.

    From black's perspective the board is turned around: colours swap so that
    "my pieces" always occupy the first 384 of a zone's inputs, and squares flip
    vertically so that "my back rank" is always rank 1. Then the board is
    mirrored if that side's king is on files e-h, and the zone picks which
    block of 768 inputs is read.
    """
    o = orient(perspective, king)
    if perspective == BLACK:
        colour = colour ^ 1
        square = square ^ 56
    if o & 1:
        square ^= 7
    return (o >> 1) * INPUTS + (colour * 6 + kind) * 64 + square


def feature_indices(rows):
    """Both perspectives for a batch of records, padded to 32 features each.

    The stored piece code is already colour * 6 + kind, so white's view is just
    code * 64 + square. Black's view swaps the colour and flips the square.
    """
    pieces = rows["pieces"].astype(np.int64)
    squares = rows["squares"].astype(np.int64)
    counts = rows["count"].astype(np.int64)
    live = np.arange(32)[None, :] < counts[:, None]

    # each side's king, found among the live slots (code 5 white, 11 black)
    kings = []
    for code in (5, 11):
        slot = np.argmax(live & (pieces == code), axis=1)
        kings.append(np.take_along_axis(squares, slot[:, None], axis=1)[:, 0])
    ow = ORIENT[WHITE][kings[0]][:, None]
    ob = ORIENT[BLACK][kings[1]][:, None]

    white = (ow >> 1) * INPUTS + pieces * 64 + (squares ^ ((ow & 1) * 7))
    black = (ob >> 1) * INPUTS + ((pieces + 6) % 12) * 64 + (squares ^ 56 ^ ((ob & 1) * 7))

    black_to_move = (rows["stm"] == 1)[:, None]
    us = np.where(black_to_move, black, white)
    them = np.where(black_to_move, white, black)
    pad = KING_BUCKETS * INPUTS
    return np.where(live, us, pad), np.where(live, them, pad)


def bucket(pieces):
    """Which output layer a position with `pieces` pieces (kings included) uses."""
    return min(BUCKETS - 1, max(0, (pieces - 2) // 4))


def save(path, feature_weights, feature_bias, output_weights, output_bias):
    """Write the file the engine reads.

    Header (32 bytes): magic, then u32 inputs, hidden, qa, qb, scale, buckets.
    Body: feature weights [inputs][hidden] i16, feature bias [hidden] i16,
    output weights [buckets][2 * hidden] i16, output bias [buckets] i32.
    """
    hidden = feature_weights.shape[1]
    assert feature_weights.shape == (KING_BUCKETS * INPUTS, hidden)
    assert feature_bias.shape == (hidden,)
    assert output_weights.shape == (BUCKETS, 2 * hidden)
    assert len(output_bias) == BUCKETS
    header = MAGIC + struct.pack("<IIiiiI", KING_BUCKETS * INPUTS, hidden, QA, QB, SCALE, BUCKETS)
    assert len(header) <= HEADER
    header = header + b"\0" * (HEADER - len(header))
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(feature_weights.astype("<i2").tobytes())
        handle.write(feature_bias.astype("<i2").tobytes())
        handle.write(output_weights.astype("<i2").tobytes())
        handle.write(np.asarray(output_bias, dtype=np.int64).astype("<i4").tobytes())


def load(path):
    with open(path, "rb") as handle:
        blob = handle.read()
    if blob[:8] != MAGIC:
        raise ValueError("not a machete network of this format: bad magic")
    inputs, hidden, qa, qb, scale, buckets = struct.unpack("<IIiiiI", blob[8:32])
    if (inputs, buckets) != (KING_BUCKETS * INPUTS, BUCKETS):
        raise ValueError("network has {} inputs and {} buckets, this reader {} and {}".format(
            inputs, buckets, KING_BUCKETS * INPUTS, BUCKETS))
    at = HEADER
    count = inputs * hidden
    feature_weights = np.frombuffer(blob, "<i2", count, at).reshape(inputs, hidden)
    at = at + count * 2
    feature_bias = np.frombuffer(blob, "<i2", hidden, at)
    at = at + hidden * 2
    output_weights = np.frombuffer(blob, "<i2", buckets * 2 * hidden, at).reshape(buckets, 2 * hidden)
    at = at + buckets * 2 * hidden * 2
    output_bias = np.frombuffer(blob, "<i4", buckets, at)
    at = at + buckets * 4
    if at != len(blob):
        raise ValueError("network file is {} bytes, its header says {}".format(len(blob), at))
    return {"feature_weights": feature_weights.astype(np.int32),
            "feature_bias": feature_bias.astype(np.int32),
            "output_weights": output_weights.astype(np.int32),
            "output_bias": [int(b) for b in output_bias],
            "hidden": hidden, "qa": qa, "qb": qb, "scale": scale}


def accumulate(net, pieces):
    """Both perspectives, from scratch. `pieces` is a list of (colour, kind, square)."""
    kings = {colour: square for colour, kind, square in pieces if kind == 5}
    acc = np.stack([net["feature_bias"].copy(), net["feature_bias"].copy()])
    for colour, kind, square in pieces:
        for perspective in (WHITE, BLACK):
            acc[perspective] += net["feature_weights"][
                feature_index(perspective, colour, kind, square, kings[perspective])]
    return acc


def forward(net, acc, side_to_move, pieces):
    """Centipawns from the side to move's point of view, integer arithmetic only."""
    qa, qb, scale, hidden = net["qa"], net["qb"], net["scale"], net["hidden"]
    layer = bucket(pieces)
    weights = net["output_weights"][layer]
    ours = np.clip(acc[side_to_move], 0, qa)
    theirs = np.clip(acc[side_to_move ^ 1], 0, qa)
    total = int(np.dot(ours, weights[:hidden]))
    total += int(np.dot(theirs, weights[hidden:]))
    # truncate toward zero, which is what Mach's `/` does and what Python's
    # `//` does not: floor division would round a negative score the wrong way
    # and put the two implementations one centipawn apart.
    numerator = (total + net["output_bias"][layer]) * scale
    denominator = qa * qb
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def pieces_of(board):
    """python-chess board -> the (colour, kind, square) list accumulate() wants."""
    import chess
    out = []
    for square, piece in board.piece_map().items():
        colour = WHITE if piece.color == chess.WHITE else BLACK
        out.append((colour, piece.piece_type - 1, square))
    return out


def evaluate_fen(net, fen):
    import chess
    board = chess.Board(fen)
    side = WHITE if board.turn == chess.WHITE else BLACK
    pieces = pieces_of(board)
    return forward(net, accumulate(net, pieces), side, len(pieces))


def random_net(seed, hidden=HIDDEN):
    """A net with no training in it, for checking that two implementations agree.

    The weights are spread across most of the int16 range on purpose: a net of
    small numbers would let an implementation that truncates or overflows still
    look correct.
    """
    rng = np.random.RandomState(seed)
    feature_weights = rng.randint(-96, 97, size=(KING_BUCKETS * INPUTS, hidden)).astype(np.int16)
    feature_bias = rng.randint(-QA, QA + 1, size=hidden).astype(np.int16)
    output_weights = rng.randint(-QB, QB + 1, size=(BUCKETS, 2 * hidden)).astype(np.int16)
    output_bias = [int(b) for b in rng.randint(-QA * QB, QA * QB, size=BUCKETS)]
    return feature_weights, feature_bias, output_weights, output_bias


def extreme_net(sign, hidden=HIDDEN):
    """The arithmetic worst case, for a gate rather than for play.

    Every activation clipped to QA, every output weight at the quantization
    limit, the bias near the int32 extreme. The dot product then reaches
    512 * QA * 127 = 16,581,120, and multiplying that by SCALE exceeds int32 by
    16%. The engine survives it only because the sum is widened to 64 bits
    before the multiply, and nothing else in the suite would notice if that
    widening were removed.

    Feature weights of 8 are chosen so a full 32-piece board sums to 256 and
    clips to 255: the maximum an activation can contribute.
    """
    feature_weights = np.full((KING_BUCKETS * INPUTS, hidden), 8, dtype=np.int16)
    feature_bias = np.zeros(hidden, dtype=np.int16)
    output_weights = np.full((BUCKETS, 2 * hidden), sign * 127, dtype=np.int16)
    return feature_weights, feature_bias, output_weights, [sign * 2000000000] * BUCKETS


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    make = sub.add_parser("random")
    make.add_argument("out")
    make.add_argument("--seed", type=int, default=1)
    make.add_argument("--hidden", type=int, default=HIDDEN)
    worst = sub.add_parser("extreme")
    worst.add_argument("out")
    worst.add_argument("--sign", type=int, default=1)
    worst.add_argument("--hidden", type=int, default=HIDDEN)
    one = sub.add_parser("eval")
    one.add_argument("net")
    one.add_argument("fen")
    show = sub.add_parser("dump")
    show.add_argument("net")
    args = parser.parse_args()

    if args.command == "random":
        save(args.out, *random_net(args.seed, args.hidden))
        print("wrote {} ({}x{}, seed {})".format(args.out, INPUTS, args.hidden, args.seed))
    elif args.command == "extreme":
        save(args.out, *extreme_net(1 if args.sign >= 0 else -1, args.hidden))
        print("wrote {} (arithmetic worst case, sign {})".format(args.out, args.sign))
    elif args.command == "eval":
        print(evaluate_fen(load(args.net), args.fen))
    elif args.command == "dump":
        net = load(args.net)
        print("inputs {} hidden {} buckets {} qa {} qb {} scale {}".format(
            INPUTS, net["hidden"], BUCKETS, net["qa"], net["qb"], net["scale"]))
        print("output bias {}".format(net["output_bias"]))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
