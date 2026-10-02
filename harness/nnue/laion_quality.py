"""How good are the games of laion/strategic_game_chess?

    python harness/nnue/laion_quality.py E:/chess-data/laion-chess --index E:/chess-data/laion-index
        [--games 150] [--plies 16] [--nodes 100000] [--reference TCEC.pgn] [--workers 4]

Three measurements:

  1. from the index (every indexed file): results, lengths, opening families;
  2. from one raw file: how games end, exact duplicates, and how many distinct
     openings there are at 8, 12, 16 and 24 plies (the dataset adds "initial
     moves" for diversity; this shows how deep that reaches);
  3. the play itself: for a sample of games, Stockfish 19 at --nodes scores
     the position before and after --plies random moves per game (after move
     10, and only while the game is undecided, within 300 cp), and the loss of
     each move is what the mover gave up. The same is done for --reference,
     a PGN of games whose quality is known (TCEC), so the numbers have a scale.
"""
import argparse
import collections
import glob
import multiprocessing
import os
import random
import statistics
import sys

import chess
import chess.engine
import chess.pgn
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

ARGS = None


def from_index(folder):
    names = {}
    for line in open(os.path.join(folder, "openings.tsv"), encoding="utf-8"):
        i, _, name, _ = line.rstrip("\n").split("\t")
        names[int(i)] = name.split(":")[0]
    res, fam, plies_hist, n, files = collections.Counter(), collections.Counter(), collections.Counter(), 0, 0
    for f in sorted(glob.glob(os.path.join(folder, "*.idx.parquet"))):
        t = pq.read_table(f)
        files += 1
        n += t.num_rows
        for v, c in zip(*[x.to_pylist() for x in t.column("result").value_counts().flatten()]):
            res[v] += c
        for v, c in zip(*[x.to_pylist() for x in t.column("opening").value_counts().flatten()]):
            fam[names.get(v, "?")] += c
        for v, c in zip(*[x.to_pylist() for x in t.column("plies").value_counts().flatten()]):
            plies_hist[min(v // 40 * 40, 400)] += c
    print("1. the index: %d files, %s games" % (files, format(n, ",")))
    print("   White wins %.1f%%, draws %.1f%%, Black wins %.1f%% (White scores %.1f%%)" % (
        100.0 * res[2] / n, 100.0 * res[1] / n, 100.0 * res[0] / n, 100.0 * (res[2] + res[1] / 2.0) / n))
    print("   length in plies: " + ", ".join("%d-%d %.0f%%" % (k, k + 39, 100.0 * plies_hist[k] / n) if k < 400 else "400+ %.0f%%" % (100.0 * plies_hist[k] / n) for k in sorted(plies_hist)))
    print("   openings: " + ", ".join("%s %.1f%%" % (k, 100.0 * c / n) for k, c in fam.most_common(12)))


def from_raw(path):
    t = pq.read_table(path)
    n = t.num_rows
    term = collections.Counter(t.column("Termination").to_pylist())
    print("2. %s: %s games" % (os.path.basename(path), format(n, ",")))
    print("   endings: " + ", ".join("%s %.1f%%" % (str(k).replace("Termination.", ""), 100.0 * c / n) for k, c in term.most_common()))
    import pyarrow.compute as pc
    moves = t.column("Moves").combine_chunks()
    whole = pc.binary_join(moves, " ")
    print("   exact duplicate games: %s" % format(n - pc.count_distinct(whole).as_py(), ","))
    for k in (8, 12, 16, 24):
        d = pc.count_distinct(pc.binary_join(pc.list_slice(moves, 0, k), " ")).as_py()
        print("   distinct openings at ply %2d: %s (%.1f games each)" % (k, format(d, ","), n / d))
    return [m.as_py() for m in moves.take(pa.array(random.Random(1).sample(range(n), ARGS.games), type=pa.int64()))]


def init(args):
    global ARGS, SF
    ARGS = args
    SF = panel.open_engine("Stockfish", 64)


def losses(moves):
    """Centipawns each sampled move gave up, from the mover's side."""
    rng = random.Random(len(moves))
    b = chess.Board()
    boards = []
    for u in moves:
        m = chess.Move.from_uci(u) if isinstance(u, str) else u
        boards.append((b.copy(), m))
        b.push(m)
    picks = [i for i in range(20, len(boards))]
    rng.shuffle(picks)
    out = []
    for i in picks:
        if len(out) >= ARGS.plies:
            break
        board, move = boards[i]
        before = SF.analyse(board, chess.engine.Limit(nodes=ARGS.nodes))["score"].pov(board.turn).score(mate_score=3000)
        if abs(before) > 300:
            continue
        after_board = board.copy()
        after_board.push(move)
        if after_board.is_game_over():
            continue
        after = SF.analyse(after_board, chess.engine.Limit(nodes=ARGS.nodes))["score"].pov(board.turn).score(mate_score=3000)
        out.append(max(0, before - after))
    return out


def report(label, pool, games):
    flat = [x for g in pool.map(losses, games, chunksize=2) for x in g]
    flat.sort()
    n = len(flat)
    print("   %-22s %5d moves: mean loss %5.1f cp, median %d; moves losing 50+ cp %.1f%%, 100+ %.1f%%, 300+ %.2f%%" % (
        label, n, statistics.mean(flat), flat[n // 2], 100.0 * sum(x >= 50 for x in flat) / n,
        100.0 * sum(x >= 100 for x in flat) / n, 100.0 * sum(x >= 300 for x in flat) / n))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--index", required=True)
    parser.add_argument("--games", type=int, default=150)
    parser.add_argument("--plies", type=int, default=16)
    parser.add_argument("--nodes", type=int, default=100000)
    parser.add_argument("--reference", default="")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()
    global ARGS
    ARGS = args
    if not args.skip_index:
        from_index(args.index)
    sample = from_raw(sorted(glob.glob(os.path.join(args.data, "*.parquet")))[0])
    print("3. the play, by Stockfish 19 at %d nodes (undecided positions after move 10):" % args.nodes)
    with multiprocessing.Pool(args.workers, initializer=init, initargs=(args,)) as pool:
        report("LAION self-play", pool, sample)
        if args.reference:
            ref = []
            with open(args.reference, encoding="utf-8", errors="replace") as h:
                while len(ref) < args.games:
                    g = chess.pgn.read_game(h)
                    if g is None:
                        break
                    if "FEN" not in g.headers:
                        ref.append(list(g.mainline_moves()))
            report(os.path.basename(args.reference)[:22], pool, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
