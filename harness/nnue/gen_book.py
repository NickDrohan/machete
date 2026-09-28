"""Build the opening book the data generator starts its games from.

    python harness/nnue/gen_book.py --pgn 8moves_v3.pgn --epd noob_3moves.epd \
        --epd-sample 8000 --out data/book.epd [--nodes 20000] [--margin 60] [--workers 6]

Every game the generator plays begins at a book position, so the book sets
which openings the network ever learns. Until 2026-09-28 the Raspberry Pi
farm used the 200-position match book (push.py fell back to it when
data/book.epd was missing), and the older 15,875-position book was 90% 1.e4
structures; machete undervalued 1.c4 by about 10 cp against Stockfish 19.

Sources are Stockfish's opening books (github.com/official-stockfish/books,
CC0): 8moves_v3 is 34,700 eight-move openings whose first moves match
engine practice (1.e4 37%, 1.d4 36%, 1.c4 12%, 1.Nf3 12%), and noob_3moves
every sensible three-move start, sampled for earlier and rarer structures.
A position is kept when a teacher at `--nodes` puts the side to move within
`--margin` centipawns of level, so no game starts decided. Positions are
written one full FEN per line, as gen.py reads them; the mix of first moves
is in the header, so it can be audited.
"""
import argparse
import collections
import multiprocessing
import os
import random
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def teacher_path():
    import panel
    return panel.path_of("Stockfish")


def score_chunk(args):
    fens, nodes, cpu = args
    try:
        import psutil
        psutil.Process().cpu_affinity([cpu])
    except Exception:
        pass
    path = teacher_path()
    engine = chess.engine.SimpleEngine.popen_uci(path, cwd=os.path.dirname(path))
    engine.configure({k: v for k, v in (("Threads", 1), ("Hash", 16)) if k in engine.options})
    out = []
    for fen, family in fens:
        info = engine.analyse(chess.Board(fen), chess.engine.Limit(nodes=nodes))
        out.append((fen, family, info["score"].relative.score(mate_score=10000) if "score" in info else None))
    engine.quit()
    return out


def from_pgn(path):
    positions = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            first = None
            for move in game.mainline_moves():
                if first is None:
                    first = board.san(move)
                board.push(move)
            if first and not board.is_game_over():
                positions.append((board.fen(), "1." + first))
    return positions


def from_epd(path, sample, seed):
    lines = [l.strip() for l in open(path, encoding="utf-8", errors="replace") if l.strip() and not l.startswith("#")]
    random.Random(seed).shuffle(lines)
    positions = []
    for line in lines[:sample]:
        fields = line.split(";")[0].split()
        board = chess.Board(" ".join(fields[:4]) + " 0 1")
        if not board.is_game_over():
            positions.append((board.fen(), "3-move start"))
    return positions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pgn", action="append", default=[])
    parser.add_argument("--epd", action="append", default=[])
    parser.add_argument("--epd-sample", type=int, default=8000)
    parser.add_argument("--out", required=True)
    parser.add_argument("--nodes", type=int, default=20000)
    parser.add_argument("--margin", type=int, default=60)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--first-cpu", type=int, default=18)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    positions = []
    for path in args.pgn:
        positions += from_pgn(path)
    for path in args.epd:
        positions += from_epd(path, args.epd_sample, args.seed)
    unique = list({fen: (fen, family) for fen, family in positions}.values())
    print("{:,} candidate positions ({:,} after removing repeats)".format(len(positions), len(unique)))
    sys.stdout.flush()

    chunks = [unique[i::args.workers] for i in range(args.workers)]
    with multiprocessing.Pool(args.workers) as pool:
        scored = pool.map(score_chunk, [(c, args.nodes, args.first_cpu + k) for k, c in enumerate(chunks)])
    kept = [(fen, fam, s) for chunk in scored for fen, fam, s in chunk if s is not None and abs(s) <= args.margin]
    random.Random(args.seed).shuffle(kept)

    families = collections.Counter(fam if fam == "3-move start" else fam.split()[0] for _, fam, _ in kept)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# {:,} starting positions for the data generator, written by harness/nnue/gen_book.py\n".format(len(kept)))
        handle.write("# from Stockfish's CC0 opening books ({}), kept if Stockfish at {:,} nodes puts\n".format(
            ", ".join(os.path.basename(p) for p in args.pgn + args.epd), args.nodes))
        handle.write("# the side to move within {} cp of level; first moves: {}\n".format(
            args.margin, ", ".join("{} {:.1f}%".format(f, 100.0 * n / len(kept)) for f, n in families.most_common(6))))
        for fen, fam, s in kept:
            handle.write(fen + "\n")
    print("kept {:,} of {:,} within {} cp".format(len(kept), len(unique), args.margin))
    for fam, n in families.most_common(10):
        print("  {:6.1f}%  {}".format(100.0 * n / len(kept), fam))
    return 0


if __name__ == "__main__":
    sys.exit(main())
