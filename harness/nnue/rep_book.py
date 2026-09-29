"""Build a data-generator book from master-level games in machete's repertoire.

    python harness/nnue/rep_book.py --pgn TCEC-everything-compet-traditional.pgn \
        --out data/rep_book.epd [--per-game 3] [--nodes 20000] [--margin 80] [--workers 4]

The network learns only the positions its training games pass through, so to
play the author's openings well (repertoire.txt) it needs games that start in
them. A game counts as one of a system's when it reaches a position of that
system's lines at ply 4 or later - after 1.e4 e5 2.Nf3 Nc6 for the Marshall,
1.d4 Nf6 2.c4 e6 for the Nimzo-Indian - so each system brings the territory
around its lines, not only the lines. From each such game, --per-game
positions are sampled between the plies where it matched and move 20, and
kept when Stockfish at --nodes puts the side to move within --margin
centipawns of level, as gen_book.py does. The lines' own positions are added.

TCEC games are engine games at long time controls: their structures are
sound. Their scores are not used - every kept position is only a starting
point, and gen.py's teacher labels everything that follows.
"""
import argparse
import collections
import multiprocessing
import os
import random
import sys

import chess
import chess.pgn

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
sys.path.insert(0, os.path.dirname(here))

import gen_book  # noqa: E402  (score_chunk: the same Stockfish filter)
import repgen    # noqa: E402  (read_lines: repertoire.txt, checked)

MATCH_FROM = 4
LAST_PLY = 40


def repertoire_positions(path):
    """Every position along every line (both sides' moves), by EPD, with the
    systems reaching it, and each line's own positions at MATCH_FROM or later."""
    systems_of = collections.defaultdict(set)
    own = []
    for side, system, moves in repgen.read_lines(path):
        board = chess.Board()
        for ply, uci in enumerate(moves, 1):
            board.push_uci(uci)
            systems_of[board.epd()].add(system)
            if ply >= MATCH_FROM and not board.is_check():
                own.append((board.fen(), system))
    return systems_of, own


def from_games(path, systems_of, per_game, seed):
    rng = random.Random(seed)
    picked, games, matched = [], 0, collections.Counter()
    with open(path, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            games += 1
            if games % 5000 == 0:
                print("  {:,} games read, {:,} in the repertoire".format(games, sum(matched.values())), flush=True)
            if game.headers.get("Variant", "Standard").lower() not in ("standard", ""):
                continue
            board = game.board()
            if board.fen() != chess.STARTING_FEN:
                continue
            system, at, trail = None, 0, []
            for ply, move in enumerate(game.mainline_moves(), 1):
                if ply > LAST_PLY:
                    break
                board.push(move)
                trail.append(board.fen())
                found = systems_of.get(board.epd())
                if found and ply >= MATCH_FROM:
                    system, at = sorted(found)[0], ply
            if system is None:
                continue
            matched[system] += 1
            window = [(k + 1, fen) for k, fen in enumerate(trail) if k + 1 > at]
            window = [(p, fen) for p, fen in window if not chess.Board(fen).is_check()]
            for _, fen in rng.sample(window, min(per_game, len(window))):
                picked.append((fen, system))
    return picked, games, matched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pgn", required=True)
    parser.add_argument("--repertoire", default="repertoire.txt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-game", type=int, default=3)
    parser.add_argument("--nodes", type=int, default=20000)
    parser.add_argument("--margin", type=int, default=80)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--first-cpu", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    systems_of, own = repertoire_positions(args.repertoire)
    picked, games, matched = from_games(args.pgn, systems_of, args.per_game, args.seed)
    print("{:,} games, {:,} in the repertoire: {}".format(
        games, sum(matched.values()), ", ".join("{} {:,}".format(s, n) for s, n in matched.most_common())))
    unique = list({fen: (fen, s) for fen, s in picked + own}.values())
    print("{:,} candidate positions ({:,} from the lines themselves)".format(len(unique), len(own)), flush=True)

    chunks = [unique[i::args.workers] for i in range(args.workers)]
    with multiprocessing.Pool(args.workers) as pool:
        scored = pool.map(gen_book.score_chunk, [(c, args.nodes, args.first_cpu + k) for k, c in enumerate(chunks)])
    kept = [(fen, s) for chunk in scored for fen, s, cp in chunk if cp is not None and abs(cp) <= args.margin]
    random.Random(args.seed).shuffle(kept)
    by_system = collections.Counter(s for _, s in kept)

    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# {:,} starting positions in machete's repertoire, written by harness/nnue/rep_book.py\n".format(len(kept)))
        handle.write("# from {} ({:,} games) and repertoire.txt, kept if Stockfish at {:,} nodes is within {} cp\n".format(
            os.path.basename(args.pgn), games, args.nodes, args.margin))
        handle.write("# systems: {}\n".format(", ".join("{} {:,}".format(s, n) for s, n in by_system.most_common())))
        for fen, _ in kept:
            handle.write(fen + "\n")
    print("kept {:,} of {:,} within {} cp -> {}".format(len(kept), len(unique), args.margin, args.out))
    for s, n in by_system.most_common():
        print("  {:6.1f}%  {}".format(100.0 * n / len(kept), s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
