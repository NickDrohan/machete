"""Test books of the positions after given opening moves, from the LAION games.

    python harness/nnue/laion_prefix_book.py --laion E:/chess-data/laion-chess --out DIR
        --line "g6=e4 c5 Nf3 Nc6 Bb5 g6" --line "e6=e4 c5 Nf3 Nc6 Bb5 e6" ...
        [--files 6] [--ply 20] [--per 300] [--window 120] [--nodes 100000]

For each --line NAME=MOVES, the games that begin with exactly those moves, at
--ply; kept when Stockfish 19 at --nodes rates the position within --window
centipawns of level, so a test starts from a fight. One book per line,
DIR/NAME.epd, of --per positions: for measuring which reply an engine plays
best from, when the name of the opening does not tell the replies apart.
"""
import argparse
import glob
import os
import random
import sys

import chess
import chess.engine
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--laion", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--line", action="append", required=True)
    parser.add_argument("--files", type=int, default=6)
    parser.add_argument("--ply", type=int, default=20)
    parser.add_argument("--per", type=int, default=300)
    parser.add_argument("--window", type=int, default=120)
    parser.add_argument("--nodes", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    lines = {}
    for spec in args.line:
        name, moves = spec.split("=", 1)
        b = chess.Board()
        uci = []
        for san in moves.split():
            m = b.parse_san(san)
            uci.append(m.uci())
            b.push(m)
        lines[name] = uci
    found = {name: {} for name in lines}
    for path in sorted(glob.glob(os.path.join(args.laion, "*.parquet")))[:args.files]:
        moves = pq.read_table(path, columns=["Moves"]).column("Moves").combine_chunks()
        long_enough = pc.greater_equal(pc.list_value_length(moves), args.ply + 20)
        for name, uci in lines.items():
            if len(found[name]) >= args.per * 6:
                continue
            start = pc.binary_join(pc.list_slice(moves, 0, len(uci)), " ")
            games = moves.filter(pc.and_(pc.equal(start, " ".join(uci)), long_enough))
            for game in games.to_pylist():
                b = chess.Board()
                for u in game[:args.ply]:
                    b.push(chess.Move.from_uci(u))
                found[name][" ".join(b.fen().split()[:4])] = b.fen()
        print("%s: %s" % (os.path.basename(path), ", ".join("%s %d" % (n, len(f)) for n, f in found.items())), flush=True)

    rng = random.Random(args.seed)
    sf = panel.open_engine("Stockfish", 64)
    os.makedirs(args.out, exist_ok=True)
    for name, positions in found.items():
        fens = list(positions.values())
        rng.shuffle(fens)
        kept = []
        for fen in fens:
            if len(kept) >= args.per:
                break
            s = sf.analyse(chess.Board(fen), chess.engine.Limit(nodes=args.nodes))["score"].white().score(mate_score=3000)
            if abs(s) <= args.window:
                kept.append(fen)
        with open(os.path.join(args.out, name + ".epd"), "w", encoding="utf-8", newline="\n") as out:
            out.write("# %s: %d positions at ply %d after %s, from LAION self-play, within %d cp at %d nodes\n" % (
                name, len(kept), args.ply, " ".join(lines[name]), args.window, args.nodes))
            for fen in kept:
                out.write(fen + "\n")
        print("%-10s %d of %d distinct positions kept -> %s" % (name, len(kept), len(fens), os.path.join(args.out, name + ".epd")))
    panel.quiet_quit(sf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
