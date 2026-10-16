"""Classical opening positions with one side about a knight down.

    python harness/nnue/knight_down_book.py --out E:/machete/books/knight_down.epd
        [--book E:/machete/books/book_v2.epd] [--workers 12] [--nodes 20000] [--seed 1]

The owner's corpus (2026-10-09): train exclusively on classical positions
played from a material disadvantage of about a knight. Each position of the
classical book (book_v2: 38,414 balanced openings) has one minor piece taken
off one side: the side at random, a knight three times in four and a bishop
otherwise, whichever of that kind at random. Stockfish then says how far down
that side is, and the start is kept if the answer is between LOW and HIGH
centipawns - about a knight, not a piece that happened to be the only
defender of something and not one that cost nothing.

The generator needs its `odds` argument with this book (opening gate 700 cp).
What each start is goes beside the book as a .tsv.
"""
import argparse
import collections
import multiprocessing
import os
import random
import sys

import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

LOW, HIGH = 250, 700  # 700 is the generator's own gate for an odds book; Stockfish puts a knight in the opening near 600


def worker(args):
    lines, seed, nodes = args
    rng = random.Random(seed)
    sf = panel.open_engine("Stockfish", 32)
    limit = chess.engine.Limit(nodes=nodes)
    kept, tried = [], 0
    for line in lines:
        board = chess.Board(line)
        side = rng.choice([chess.WHITE, chess.BLACK])
        kind = chess.KNIGHT if rng.random() < 0.75 else chess.BISHOP
        squares = list(board.pieces(kind, side)) or list(board.pieces(chess.BISHOP if kind == chess.KNIGHT else chess.KNIGHT, side))
        if not squares:
            continue
        square = rng.choice(squares)
        kind = board.piece_type_at(square)
        board.remove_piece_at(square)
        board = chess.Board(board.fen())
        if not board.is_valid() or board.is_check() or board.is_game_over():
            continue
        tried += 1
        score = sf.analyse(board, limit)["score"].pov(side).score(mate_score=5000)
        if LOW <= -score <= HIGH:
            kept.append((" ".join(board.fen().split()[:4]), "white" if side else "black", chess.piece_name(kind), chess.square_name(square), -score))
    panel.quiet_quit(sf)
    return kept, tried


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--book", default="E:/machete/books/book_v2.epd")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--nodes", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    lines = [l.strip() for l in open(args.book, encoding="utf-8") if l.strip() and not l.startswith("#")]
    with multiprocessing.Pool(args.workers) as pool:
        parts = pool.map(worker, [(lines[k::args.workers], args.seed * 1000 + k, args.nodes) for k in range(args.workers)])
    rows = [r for part, _ in parts for r in part]
    tried = sum(n for _, n in parts)
    random.Random(args.seed).shuffle(rows)
    sides = collections.Counter(r[1] for r in rows)
    kinds = collections.Counter(r[2] for r in rows)
    mean = sum(r[4] for r in rows) / max(1, len(rows))
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# classical openings with one side about a knight down, harness/nnue/knight_down_book.py. gen odds  (opening gate 700)\n")
        out.write("# %d positions of %d tried from %s; Stockfish at %d nodes puts the side down by %d to %d cp (mean %d); seed %d\n" % (
            len(rows), tried, os.path.basename(args.book), args.nodes, LOW, HIGH, mean, args.seed))
        out.write("# side down: %s; piece taken: %s\n" % (dict(sides), dict(kinds)))
        for r in rows:
            out.write(r[0] + "\n")
    with open(os.path.splitext(args.out)[0] + ".tsv", "w", encoding="utf-8", newline="\n") as notes:
        notes.write("fen\tside_down\tpiece\tsquare\tdeficit_cp\n")
        for r in rows:
            notes.write("%s\t%s\t%s\t%s\t%d\n" % r)
    print("%d positions kept of %d tried (%.0f%%), mean deficit %d cp -> %s" % (len(rows), tried, 100 * len(rows) / max(1, tried), mean, args.out))
    print("side down:", dict(sides), "| piece:", dict(kinds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
