"""Build a data-generator book of positions where one side is clearly better.

    python harness/nnue/conv_book.py CORPUS.bin --out data/conv_book.epd \
        [--want 30000] [--low 150] [--high 450] [--min-pieces 12] [--nodes 20000] [--workers 6]

On lichess machete let three winning positions against weaker bots drift into
draws (+3.11, +2.27 and +1.54 by Stockfish 19): it held the advantage and made
quiet, aimless moves until it was gone. The network learns conversion from
games in which an advantage is converted, and a book that starts games from
advantages makes the generator play exactly those. Positions are sampled from
a corpus whose labels say one side is --low to --high centipawns better, with
at least --min-pieces pieces (conversion is a middlegame skill as much as an
endgame one), and kept when Stockfish at --nodes agrees, as gen_book.py does.
Castling rights and en passant are not in the records; positions are set up
without them.
"""
import argparse
import multiprocessing
import os
import random
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_book  # noqa: E402  (score_chunk: the Stockfish filter)
from reference import RECORD  # noqa: E402

KINDS = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]


def board_of(row):
    board = chess.Board(None)
    for k in range(int(row["count"])):
        code = int(row["pieces"][k])
        board.set_piece_at(int(row["squares"][k]), chess.Piece(KINDS[code % 6], chess.WHITE if code < 6 else chess.BLACK))
    board.turn = chess.WHITE if int(row["stm"]) == 0 else chess.BLACK
    return board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--out", required=True)
    parser.add_argument("--want", type=int, default=30000)
    parser.add_argument("--low", type=int, default=150)
    parser.add_argument("--high", type=int, default=450)
    parser.add_argument("--min-pieces", type=int, default=12)
    parser.add_argument("--nodes", type=int, default=20000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--first-cpu", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    rows = np.memmap(args.corpus, dtype=RECORD, mode="r")
    score = np.abs(rows["score"].astype(np.int32))
    picked = np.flatnonzero((score >= args.low) & (score <= args.high) & (rows["count"] >= args.min_pieces))
    rng = np.random.default_rng(args.seed)
    rng.shuffle(picked)
    candidates, seen = [], set()
    for i in picked[: args.want * 3]:
        board = board_of(rows[i])
        if not board.is_valid() or board.is_check():
            continue
        fen = board.fen()
        if fen not in seen:
            seen.add(fen)
            candidates.append((fen, "conversion"))
    print("{:,} records with a {}-{} cp edge and {}+ pieces; {:,} candidates".format(
        len(picked), args.low, args.high, args.min_pieces, len(candidates)), flush=True)

    chunks = [candidates[k::args.workers] for k in range(args.workers)]
    with multiprocessing.Pool(args.workers) as pool:
        scored = pool.map(gen_book.score_chunk, [(c, args.nodes, args.first_cpu + k) for k, c in enumerate(chunks)])
    kept = [fen for chunk in scored for fen, _, cp in chunk if cp is not None and args.low <= abs(cp) <= args.high]
    random.Random(args.seed).shuffle(kept)
    kept = kept[: args.want]
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# {:,} positions where one side is {}-{} cp better, written by harness/nnue/conv_book.py\n".format(
            len(kept), args.low, args.high))
        handle.write("# from {}, kept if Stockfish at {:,} nodes agrees; {}+ pieces\n".format(
            os.path.basename(args.corpus), args.nodes, args.min_pieces))
        for fen in kept:
            handle.write(fen + "\n")
    print("kept {:,} -> {}".format(len(kept), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
