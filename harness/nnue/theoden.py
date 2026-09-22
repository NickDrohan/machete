"""Convert the theoden8 NNUE corpus into our record format.

    python harness/nnue/theoden.py E:/chess-data/evaluations.parquet \
        --out data/theoden_evals.bin --limit 40000000

466 million positions: 354M from Lichess game analysis at depth 18-22 and
several million nodes each, 100M tablebase endgames and 11M puzzle positions,
the latter two re-scored uniformly at Stockfish 16 depth 12 with 5-man Syzygy.
The search behind those labels is four orders of magnitude deeper than the
1500 nodes our own generator can afford.

Positions arrive in a compressed encoding, not as FEN. The format is from
dummy_chess/FEN.hpp and is reimplemented here rather than built:

    byte 0        flags: bit 0 black to move, bit 1 chess960, bit 2 crazyhouse
    bytes 1..n-7  board nibbles, piece index into "KQRBNPkqrbnp", with 0xC
                  followed by a count-1 nibble for a run of empty squares,
                  0xF as padding
    last 6 bytes  castling, castling, en passant, halfmove clock, fullmove x2

Two things about the labels matter more than the volume:

**They are from White's point of view.** Ours are from the side to move's.
Getting that backwards would train the network on the negation of the truth for
every position with Black to move, which is half of them, and the result would
look like a network that had learned nothing rather than like a bug.

**They are on their own centipawn scale.** A label's scale is set by the engine
and search that produced it, and mixing scales silently was worth -68 Elo here
when we did it by accident. This writes its own engine id so the scale can be
fitted separately against the gold set, exactly as the five local teachers are.
"""

import argparse
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

PIECES = "KQRBNPkqrbnp"   # from dummy_chess FEN.hpp; not the order the assert string uses
NIB_EMPTY = 0xC
CLAMP = 10000

# our five local teachers occupy 0..4; this corpus is its own source and gets
# its own id so its centipawn scale can be fitted separately
THEODEN_ENGINE_ID = 10


def decompress(blob):
    """The compressed encoding back to (board string, black_to_move).

    The board string is 64 characters in FEN reading order, a8 first, with a
    space for an empty square.
    """
    if len(blob) < 8:
        return None, False
    flags = blob[0]
    if flags & 4:          # crazyhouse carries 13 extra metadata bytes
        return None, False
    board_end = len(blob) - 6
    nibs = []
    for byte in blob[1:board_end]:
        nibs.append((byte >> 4) & 0xF)
        nibs.append(byte & 0xF)

    board = []
    i = 0
    while i < len(nibs) and len(board) < 64:
        n = nibs[i]
        if n == NIB_EMPTY and i + 1 < len(nibs):
            board.extend(" " * (nibs[i + 1] + 1))
            i += 2
        elif n < 12:
            board.append(PIECES[n])
            i += 1
        elif n == 0xF:
            break
        else:
            i += 1
    if len(board) != 64:
        return None, False
    return "".join(board), bool(flags & 1)


def to_record(board_string, black_to_move, score_white):
    """One position in our format, with the score turned to the mover's view."""
    row = np.zeros(1, dtype=RECORD)[0]
    row["engine"] = THEODEN_ENGINE_ID
    count = 0
    for index, char in enumerate(board_string):
        if char == " ":
            continue
        if count >= 32:
            return None
        colour = 0 if char.isupper() else 1
        kind = "PNBRQK".index(char.upper())
        # the board string reads a8 first; our squares count a1 first
        rank = 7 - (index // 8)
        square = rank * 8 + (index % 8)
        row["pieces"][count] = colour * 6 + kind
        row["squares"][count] = square
        count += 1
    if count < 2:
        return None
    row["count"] = count
    row["stm"] = 1 if black_to_move else 0
    score = -score_white if black_to_move else score_white
    row["score"] = max(-CLAMP, min(CLAMP, int(score)))
    row["result"] = 1          # unused: the target no longer blends a result
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=40000000)
    parser.add_argument("--min-depth", type=int, default=0,
                        help="skip labels shallower than this")
    parser.add_argument("--max-cp", type=int, default=0,
                        help="skip positions past this, 0 for no limit")
    parser.add_argument("--verify", type=int, default=2000,
                        help="decoded positions to check against python-chess")
    args = parser.parse_args()

    import pyarrow.parquet as pq
    source = pq.ParquetFile(args.parquet)
    print("{:,} rows in {}".format(source.metadata.num_rows, args.parquet))

    written = 0
    rejected = 0
    checked = 0
    bad = 0
    buffer = []
    with open(args.out, "wb") as handle:
        for batch in source.iter_batches(batch_size=200000,
                                         columns=["fen", "score", "depth"]):
            data = batch.to_pydict()
            for blob, score, depth in zip(data["fen"], data["score"], data["depth"]):
                if written >= args.limit:
                    break
                if args.min_depth and depth < args.min_depth:
                    continue
                if args.max_cp and abs(int(score)) > args.max_cp:
                    continue
                board_string, black = decompress(bytes(blob))
                if board_string is None:
                    rejected += 1
                    continue
                row = to_record(board_string, black, int(score))
                if row is None:
                    rejected += 1
                    continue
                # an independent check that the decode means what we think
                if checked < args.verify:
                    fen_board = []
                    for rank in range(8):
                        run = 0
                        line = ""
                        for file in range(8):
                            c = board_string[rank * 8 + file]
                            if c == " ":
                                run += 1
                            else:
                                if run:
                                    line += str(run)
                                    run = 0
                                line += c
                        if run:
                            line += str(run)
                        fen_board.append(line)
                    fen = "/".join(fen_board) + (" b" if black else " w") + " - - 0 1"
                    try:
                        if not chess.Board(fen).is_valid():
                            bad += 1
                    except Exception:
                        bad += 1
                    checked += 1
                buffer.append(row)
                written += 1
                if len(buffer) >= 100000:
                    handle.write(np.array(buffer, dtype=RECORD).tobytes())
                    buffer = []
                    sys.stdout.write("\r{:,} written, {:,} rejected".format(written, rejected))
                    sys.stdout.flush()
            if written >= args.limit:
                break
        if buffer:
            handle.write(np.array(buffer, dtype=RECORD).tobytes())

    print("\n{:,} positions written to {}, {:,} rejected".format(written, args.out, rejected))
    print("{} of {} decoded positions were illegal".format(bad, checked))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
