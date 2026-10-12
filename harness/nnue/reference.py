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

import os
import argparse
import struct
import sys

import numpy as np

MAGIC = b"MCHNNUE3"
# Piece roles (MACHETE_PIECE_ROLES=1), the owner's per-piece inputs: a side's two knights get an input channel
# each, and so do its two rooks; the bishops share one (the square's colour says which bishop it is) and so do the
# pawns (the square says which file). Which knight is which is read off the position, never remembered: the one
# nearer the a-file as that side reads the board (then the lower rank) is the first, every other the second.
# Channels a side: pawn 0, knight 1 and 2, bishop 3, rook 4 and 5, queen 6, king 7; the opponent's are 8 higher.
ROLES = os.environ.get("MACHETE_PIECE_ROLES", "0") == "1"
CHANNEL = (0, 1, 3, 4, 6, 7)   # by kind: pawn, knight, bishop, rook, queen, king
INPUTS = 1024 if ROLES else 768   # per king zone
# king zones per side; the file holds KING_BUCKETS * INPUTS rows. 8 is what the released engine is built for.
# MACHETE_KING_ZONES=16 or 32 makes this module (and train.py, which reads it) describe a network with more:
# 16 splits every rank in two, 32 is one zone for each square the mirrored king can stand on.
KING_BUCKETS = int(os.environ.get("MACHETE_KING_ZONES", "8"))
assert KING_BUCKETS in (8, 16, 32), "MACHETE_KING_ZONES must be 8, 16 or 32"

# Layers by the kind of position in place of king zones (MACHETE_LAYERS), the owner's design of 2026-10-12: which
# set of inputs a side reads is chosen by the phase of the game and its pawns, not by where its king stands, so a
# king that walks the board in an endgame reads the same layer all the way. The endgame begins when the queens
# are off. Still mirrored left-right by the king's file. KING_BUCKETS is then the number of layers.
#   phase3:  0 opening (queens on, 28 or more men)   1 middlegame (queens on)   2 endgame (no queens)
#   struct6: 0 opening   1 middlegame, open centre (at most one pawn left on the d- and e-files)
#            2 middlegame, closed centre (a white and a black pawn head to head on the d- or e-file)
#            3 middlegame, otherwise   4 endgame and the side reading has a passed pawn   5 endgame, it has none
LAYERS = os.environ.get("MACHETE_LAYERS", "")
assert LAYERS in ("", "phase3", "struct6"), "MACHETE_LAYERS must be phase3 or struct6"
if LAYERS:
    KING_BUCKETS = 3 if LAYERS == "phase3" else 6
OPENING_MEN = 28
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
    e-h, and the king's square then falls in one of KING_BUCKETS zones. Eight:

        rank 1: a-b 0, c-d 1      rank 2: a-b 2, c-d 3
        ranks 3-4: a-b 4, c-d 5   ranks 5-8: a-b 6, c-d 7

    Sixteen: every rank, a-b and c-d (rank * 2 + half). Thirty-two: every
    square of files a-d (rank * 4 + file).
    """
    rel = king ^ 56 if perspective == BLACK else king
    mirror = 1 if rel & 7 >= 4 else 0
    if mirror:
        rel ^= 7
    rank = rel >> 3
    if KING_BUCKETS == 32:
        return (rank * 4 + (rel & 7)) * 2 + mirror
    zone = 1 if rel & 7 >= 2 else 0
    if KING_BUCKETS == 16:
        return (rank * 2 + zone) * 2 + mirror
    if rank == 1:
        zone += 2
    elif rank in (2, 3):
        zone += 4
    elif rank >= 4:
        zone += 6
    return zone * 2 + mirror


# orient() for every (perspective, king square), for the vectorised paths
ORIENT = np.array([[orient(side, square) for square in range(64)] for side in (WHITE, BLACK)])


def has_passer(colour, pieces):
    """Does `colour` have a pawn with no enemy pawn ahead of it on its own or a neighbouring file?"""
    enemy = [(q & 7, q >> 3) for c, k, q in pieces if k == 0 and c != colour]
    for c, k, q in pieces:
        if k == 0 and c == colour:
            f, r = q & 7, q >> 3
            if not any(abs(ef - f) <= 1 and (er > r if colour == WHITE else er < r) for ef, er in enemy):
                return True
    return False


def layer_of(perspective, pieces):
    """The layer `perspective` reads in a position, a list of (colour, kind, square). See LAYERS."""
    if any(kind == 4 for _, kind, _ in pieces):
        if len(pieces) >= OPENING_MEN:
            return 0
        if LAYERS == "phase3":
            return 1
        white = {q for c, k, q in pieces if k == 0 and c == WHITE and q & 7 in (3, 4)}
        black = {q for c, k, q in pieces if k == 0 and c == BLACK and q & 7 in (3, 4)}
        if any(q + 8 in black for q in white):
            return 2
        return 1 if len(white) + len(black) <= 1 else 3
    if LAYERS == "phase3":
        return 2
    return 4 if has_passer(perspective, pieces) else 5


def feature_index(perspective, colour, kind, square, king, second=False, layer=None):
    """Where (colour, kind, square) lands in the inputs, seen from one side
    whose own king stands on `king`.

    From black's perspective the board is turned around: colours swap so that
    "my pieces" always occupy the first 384 of a zone's inputs, and squares flip
    vertically so that "my back rank" is always rank 1. Then the board is
    mirrored if that side's king is on files e-h, and the zone picks which
    block of 768 inputs is read.
    """
    o = orient(perspective, king)
    if LAYERS:
        o = layer * 2 + (o & 1)
    if perspective == BLACK:
        colour = colour ^ 1
        square = square ^ 56
    if o & 1:
        square ^= 7
    if ROLES:
        return (o >> 1) * INPUTS + (colour * 8 + CHANNEL[kind] + (1 if second else 0)) * 64 + square
    return (o >> 1) * INPUTS + (colour * 6 + kind) * 64 + square


def role_key(perspective, square, king):
    """Where a piece stands as `perspective` reads the board, file first: the smaller key is the first of a pair."""
    o = orient(perspective, king)
    if perspective == BLACK:
        square = square ^ 56
    if o & 1:
        square ^= 7
    return (square & 7) * 8 + (square >> 3)


def seconds(perspective, pieces, king):
    """For each (colour, kind, square) of `pieces`: is it a second knight or rook, as `perspective` reads the board?"""
    if not ROLES:
        return [False] * len(pieces)
    first = {}
    for colour, kind, square in pieces:
        if kind in (1, 3):
            key = role_key(perspective, square, king)
            first[(colour, kind)] = min(first.get((colour, kind), 64), key)
    return [kind in (1, 3) and role_key(perspective, square, king) != first[(colour, kind)] for colour, kind, square in pieces]


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
    if LAYERS:
        lw, lb = layers_of(pieces, squares, live, counts)
        ow = lw[:, None] * 2 + (ow & 1)
        ob = lb[:, None] * 2 + (ob & 1)

    white_squares = squares ^ ((ow & 1) * 7)
    black_squares = squares ^ 56 ^ ((ob & 1) * 7)
    white_rows, black_rows = pieces, (pieces + 6) % 12
    if ROLES:
        channel = np.array(CHANNEL)
        rows_of = []
        for seen, mine in ((white_squares, pieces < 6), (black_squares, pieces >= 6)):
            key = (seen & 7) * 8 + (seen >> 3)
            second = np.zeros_like(pieces, dtype=bool)
            for code in (1, 3, 7, 9):   # each colour's knights and rooks
                group = live & (pieces == code)
                first = np.where(group, key, 64).min(axis=1, keepdims=True)
                second |= group & (key != first)
            rows_of.append(np.where(mine, 0, 8) + channel[pieces % 6] + second)
        white_rows, black_rows = rows_of
    white = (ow >> 1) * INPUTS + white_rows * 64 + white_squares
    black = (ob >> 1) * INPUTS + black_rows * 64 + black_squares

    black_to_move = (rows["stm"] == 1)[:, None]
    us = np.where(black_to_move, black, white)
    them = np.where(black_to_move, white, black)
    pad = KING_BUCKETS * INPUTS
    return np.where(live, us, pad), np.where(live, them, pad)


# squares ahead of a pawn on its own and the neighbouring files, as bitboards: FRONT[colour][square]
def _front(colour, square):
    f, r = square & 7, square >> 3
    ranks = range(r + 1, 8) if colour == WHITE else range(0, r)
    return sum(1 << (rr * 8 + ff) for rr in ranks for ff in (f - 1, f, f + 1) if 0 <= ff < 8)


FRONT = np.array([[_front(colour, square) for square in range(64)] for colour in (WHITE, BLACK)], dtype=np.uint64)
CENTRE_FILES = np.uint64(sum(1 << (r * 8 + f) for r in range(8) for f in (3, 4)))


def layers_of(pieces, squares, live, counts):
    """layer_of for a batch: (white's layer, black's layer) for arrays of piece codes and squares."""
    queens = (live & ((pieces == 4) | (pieces == 10))).any(axis=1)
    one = np.uint64(1)
    bit = one << squares.astype(np.uint64)
    wp, bp = live & (pieces == 0), live & (pieces == 6)
    white = np.bitwise_or.reduce(np.where(wp, bit, np.uint64(0)), axis=1)
    black = np.bitwise_or.reduce(np.where(bp, bit, np.uint64(0)), axis=1)
    middle = np.full(len(pieces), 1)
    if LAYERS == "struct6":
        centre = ((wp | bp) & np.isin(squares & 7, (3, 4))).sum(axis=1)
        locked = ((white << np.uint64(8)) & black & CENTRE_FILES) != 0
        middle = np.where(locked, 2, np.where(centre <= 1, 1, 3))
    with_queens = np.where(counts >= OPENING_MEN, 0, middle)
    if LAYERS == "phase3":
        end = np.full(len(pieces), 2)
        return np.where(queens, with_queens, end), np.where(queens, with_queens, end)
    white_passer = (wp & ((FRONT[WHITE][squares] & black[:, None]) == 0)).any(axis=1)
    black_passer = (bp & ((FRONT[BLACK][squares] & white[:, None]) == 0)).any(axis=1)
    return np.where(queens, with_queens, np.where(white_passer, 4, 5)), np.where(queens, with_queens, np.where(black_passer, 4, 5))


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
    for perspective in (WHITE, BLACK):
        second = seconds(perspective, pieces, kings[perspective])
        layer = layer_of(perspective, pieces) if LAYERS else None
        for (colour, kind, square), two in zip(pieces, second):
            acc[perspective] += net["feature_weights"][
                feature_index(perspective, colour, kind, square, kings[perspective], two, layer)]
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
