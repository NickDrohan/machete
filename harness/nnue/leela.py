"""Leela training data, in Stockfish's binpack format, as our records.

    python harness/nnue/leela.py FILE.binpack[.zst] --check 200000
    python harness/nnue/leela.py FILE.binpack[.zst] --out E:/machete/corpora/leela.bin \
        --positions 60000000 --workers 4

Stockfish's networks are trained on Leela Chess Zero's self-play, converted to
binpack by linrock (huggingface.co/datasets/linrock). The positions come from
Leela's games; the scores from Leela's search, with 2-7 piece endings corrected
from tablebases. Leela's data is under the Open Database License: a network
trained on it and published must say so.

Binpack is Tomasz Sobczyk's format (nnue-pytorch, data_loader/cpp/lib/
binpack.h, MIT licence). This is a reading of it in Python, following that
file line for line where it matters:

  file    chunks: "BINP", u32 size (little-endian), then that many bytes
  chunk   a run of games. Each game is a 32-byte stem - the first position,
          its move, score, ply, result and fifty-move counter - then a
          big-endian u16 count of the moves that follow, then those moves
          bit-packed: which of our pieces moved (an index among the side to
          move's pieces), which of its destinations (an index among its
          pseudo-legal ones), and the score as a variable-length delta
  score   Stockfish internal units, 208 to a pawn, from the side to move
  result  +1, 0, -1 from the side to move

A move index is only meaningful against the exact destination set the writer
computed, so one misread bit desynchronises everything after it. That makes
the moves self-checking: every decoded move must be legal, and every chunk must
be consumed exactly. --check does both and reports what the data looks like;
conversion runs the same checks and stops on the first failure.

The scores are not. A flipped bit inside a score's delta changes that score and
nothing else (shown on nnue-pytorch's sample: one flip moved one score from
-956 to -1085, every move still legal). Their integrity comes from the file:
the sha256 its host publishes, checked after download, and zstd's own frame
checksum.
"""

import argparse
import itertools
import multiprocessing
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

ENGINE_ID = 11           # our records' teacher id: 10 is theoden, 11 is Leela
INTERNAL_PAWN = 208      # Stockfish internal units per pawn, as binpack.h converts them
CLAMP = 10000
STEM = 32


def unsigned_to_signed(r):
    r = ((r << 15) | (r >> 1)) & 0xFFFF
    if r & 0x8000:
        r ^= 0x7FFF
    return r - 0x10000 if r & 0x8000 else r


def int16(x):
    return ((x + 0x8000) & 0xFFFF) - 0x8000


def used_bits_safe(value):
    return 0 if value == 0 else (value - 1).bit_length()


def nth_set_bit(bits, n):
    for _ in range(n):
        bits &= bits - 1
    return (bits & -bits).bit_length() - 1


class Bits(object):
    """binpack.h's PackedMoveScoreListReader: bits read from the top of each byte."""

    def __init__(self, data, offset):
        self.data = data
        self.offset = offset
        self.left = 8

    def take(self, count):
        if count == 0:
            return 0
        if self.left == 0:
            self.offset += 1
            self.left = 8
        byte = (self.data[self.offset] << (8 - self.left)) & 0xFF
        bits = byte >> (8 - count)
        if count > self.left:
            spill = count - self.left
            bits |= self.data[self.offset + 1] >> (8 - spill)
            self.left += 8
            self.offset += 1
        self.left -= count
        return bits

    def vle16(self, block=4):
        mask = (1 << block) - 1
        value, shift = 0, 0
        while True:
            part = self.take(block + 1)
            value |= (part & mask) << shift
            if not part >> block:
                return value & 0xFFFF
            shift += block

    def end(self):
        return self.offset + (1 if self.left != 8 else 0)


def read_stem(stem):
    """The first position of a game, its move, score, ply and result."""
    occupied = int.from_bytes(stem[0:8], "big")
    board = chess.Board(None)
    board.castling_rights = chess.BB_EMPTY
    turn = chess.WHITE
    ep = None
    index = 0
    squares = occupied
    while squares:
        square = (squares & -squares).bit_length() - 1
        squares &= squares - 1
        nibble = (stem[8 + index // 2] >> (4 * (index % 2))) & 0xF
        index += 1
        if nibble < 12:
            board.set_piece_at(square, chess.Piece((nibble >> 1) + 1, not (nibble & 1)))
        elif nibble == 12:
            white = chess.square_rank(square) == 3
            board.set_piece_at(square, chess.Piece(chess.PAWN, white))
            ep = square - 8 if white else square + 8
        elif nibble == 13:
            board.set_piece_at(square, chess.Piece(chess.ROOK, chess.WHITE))
            board.castling_rights |= chess.BB_SQUARES[square]
        elif nibble == 14:
            board.set_piece_at(square, chess.Piece(chess.ROOK, chess.BLACK))
            board.castling_rights |= chess.BB_SQUARES[square]
        else:
            board.set_piece_at(square, chess.Piece(chess.KING, chess.BLACK))
            turn = chess.BLACK
    board.turn = turn
    board.ep_square = ep

    packed = (stem[24] << 8) | stem[25]
    kind, source, target = packed >> 14, (packed >> 8) & 63, (packed >> 2) & 63
    if kind == 1:
        move = chess.Move(source, target, (packed & 3) + chess.KNIGHT)
    elif kind == 2:
        # binpack castles as king-takes-own-rook; python-chess moves the king two files
        file = 6 if chess.square_file(target) == 7 else 2
        move = chess.Move(source, chess.square(file, chess.square_rank(source)))
    else:
        move = chess.Move(source, target)
    score = unsigned_to_signed((stem[26] << 8) | stem[27])
    ply_result = (stem[28] << 8) | stem[29]
    board.halfmove_clock = (stem[30] << 8) | stem[31]
    board.fullmove_number = (ply_result & 0x3FFF) // 2 + 1
    return board, move, score, unsigned_to_signed(ply_result >> 14)


def next_move(board, bits):
    """binpack.h's nextMoveScore, less the score."""
    us = board.turn
    ours = board.occupied_co[us]
    theirs = board.occupied_co[not us]
    occupied = ours | theirs
    source = nth_set_bit(ours, bits.take(used_bits_safe(bin(ours).count("1"))))
    kind = board.piece_type_at(source)
    if kind == chess.PAWN:
        forward = 8 if us == chess.WHITE else -8
        targets = theirs
        if board.ep_square is not None and board.has_legal_en_passant():
            targets |= chess.BB_SQUARES[board.ep_square]
        destinations = chess.BB_PAWN_ATTACKS[us][source] & targets
        ahead = source + forward
        if not occupied & chess.BB_SQUARES[ahead]:
            destinations |= chess.BB_SQUARES[ahead]
            if chess.square_rank(source) == (1 if us == chess.WHITE else 6) \
                    and not occupied & chess.BB_SQUARES[ahead + forward]:
                destinations |= chess.BB_SQUARES[ahead + forward]
        count = bin(destinations).count("1")
        if chess.square_rank(source) == (6 if us == chess.WHITE else 1):
            index = bits.take(used_bits_safe(count * 4))
            return chess.Move(source, nth_set_bit(destinations, index // 4), chess.KNIGHT + index % 4)
        return chess.Move(source, nth_set_bit(destinations, bits.take(used_bits_safe(count))))
    if kind == chess.KING:
        rights = board.castling_rights & (chess.BB_RANK_1 if us == chess.WHITE else chess.BB_RANK_8)
        attacks = chess.BB_KING_ATTACKS[source] & ~ours
        size = bin(attacks).count("1")
        index = bits.take(used_bits_safe(size + bin(rights).count("1")))
        if index >= size:
            long_side = index == size and rights & (chess.BB_A1 | chess.BB_A8)
            file = 2 if long_side else 6
            return chess.Move(source, chess.square(file, chess.square_rank(source)))
        return chess.Move(source, nth_set_bit(attacks, index))
    attacks = board.attacks_mask(source) & ~ours
    return chess.Move(source, nth_set_bit(attacks, bits.take(used_bits_safe(bin(attacks).count("1")))))


def games(chunk):
    """Every position in a chunk: (board before the move, move, score, result)."""
    offset = 0
    size = len(chunk)
    while offset + STEM + 2 <= size:
        board, move, score, result = read_stem(chunk[offset:offset + STEM])
        offset += STEM
        plies = (chunk[offset] << 8) | chunk[offset + 1]
        offset += 2
        if move not in board.legal_moves:
            raise ValueError("illegal stem move {} in {}".format(move.uci(), board.fen()))
        yield board, move, score, result
        if plies:
            bits = Bits(chunk, offset)
            last = int16(-score)
            for _ in range(plies):
                board.push(move)
                result = -result
                move = next_move(board, bits)
                score = int16(last + unsigned_to_signed(bits.vle16()))
                last = int16(-score)
                if move not in board.legal_moves:
                    raise ValueError("illegal move {} in {}".format(move.uci(), board.fen()))
                yield board, move, score, result
            offset = bits.end()
    if offset != size:
        raise ValueError("chunk not consumed exactly: {} of {} bytes".format(offset, size))


def chunks(path):
    """The raw chunks of a binpack, compressed with zstd or not."""
    handle = open(path, "rb")
    if path.endswith(".zst"):
        import zstandard
        stream = zstandard.ZstdDecompressor().stream_reader(handle, read_size=1 << 22)
    else:
        stream = handle
    try:
        while True:
            header = read_exactly(stream, 8)
            if not header:
                return
            if header[:4] != b"BINP":
                raise ValueError("not a binpack chunk header: {!r}".format(header[:4]))
            size = int.from_bytes(header[4:8], "little")
            yield read_exactly(stream, size)
    finally:
        stream.close()


def read_exactly(stream, size):
    parts = []
    while size:
        part = stream.read(size)
        if not part:
            if parts:
                raise ValueError("file ends inside a chunk")
            return b""
        parts.append(part)
        size -= len(part)
    return b"".join(parts)


def record(board, score, result):
    row = np.zeros(1, dtype=RECORD)[0]
    row["engine"] = ENGINE_ID
    row["stm"] = 0 if board.turn == chess.WHITE else 1
    items = list(board.piece_map().items())
    row["count"] = len(items)
    for slot, (square, piece) in enumerate(items):
        row["pieces"][slot] = (0 if piece.color == chess.WHITE else 1) * 6 + piece.piece_type - 1
        row["squares"][slot] = square
    row["score"] = max(-CLAMP, min(CLAMP, int(round(score * 100.0 / INTERNAL_PAWN))))
    row["result"] = result + 1
    return row


def convert_chunk(chunk):
    """One chunk as records, positions in check left out as our generator does."""
    rows = [record(b, s, r) for b, _, s, r in games(chunk) if not b.is_check()]
    return np.array(rows, dtype=RECORD).tobytes() if rows else b""


def check(path, limit):
    """Decode, verify, and describe the data without writing anything."""
    seen = in_check = 0
    results = {-1: 0, 0: 0, 1: 0}
    scores = []
    first = None
    for chunk in chunks(path):
        for board, move, score, result in games(chunk):
            if first is None:
                first = (board.fen(), move.uci(), score, result)
            seen += 1
            in_check += board.is_check()
            results[result] += 1
            if len(scores) < 200000:
                scores.append(score)
            if seen >= limit:
                break
        if seen >= limit:
            break
    s = np.array(scores) * 100.0 / INTERNAL_PAWN
    print("{:,} positions decoded, every move legal, every chunk consumed exactly".format(seen))
    print("first: {} {} score {} result {}".format(*first))
    print("results from the side to move: won {:.1%}  drew {:.1%}  lost {:.1%}".format(
        results[1] / seen, results[0] / seen, results[-1] / seen))
    print("in check: {:.1%} (left out on conversion)".format(in_check / seen))
    print("scores in pawns: median |s| {:.2f}, 90th {:.2f}, beyond 4: {:.1%}".format(
        np.median(abs(s)) / 100, np.percentile(abs(s), 90) / 100, float((abs(s) > 400).mean())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binpack")
    parser.add_argument("--check", type=int, default=0, help="decode and verify this many positions, write nothing")
    parser.add_argument("--out", default="")
    parser.add_argument("--positions", type=int, default=60000000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    if args.check:
        check(args.binpack, args.check)
        return 0
    if not args.out:
        parser.error("--out is required to convert")

    # batches, not pool.imap: imap's feeder thread reads its whole input as fast
    # as it can, which here would be the whole decompressed file, into memory
    written = 0
    source = chunks(args.binpack)
    with open(args.out, "wb") as out, multiprocessing.Pool(args.workers) as pool:
        while written < args.positions:
            batch = list(itertools.islice(source, args.workers * 2))
            if not batch:
                break
            for blob in pool.map(convert_chunk, batch):
                take = min(len(blob) // RECORD.itemsize, args.positions - written)
                out.write(blob[:take * RECORD.itemsize])
                written += take
            sys.stdout.write("\r{:,} positions written".format(written))
            sys.stdout.flush()
    print("\n{:,} positions written to {}".format(written, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
