"""Books of real positions for each Black system against 1.e4, for measuring
which one machete plays best.

    python harness/nnue/system_books.py PGN [PGN ...] --out DIR [--per 300] [--anti 0.3]
    python harness/nnue/system_books.py --laion E:/chess-data/laion-chess --index E:/chess-data/laion-index --out DIR

With --laion, the games are the LAION Stockfish self-play games the index
(laion_index.py) names; every system then has thousands of games, where TCEC
had one Marshall and 32 Sveshnikovs.

Every game of the PGNs (TCEC: strong engines, real theory) is named by the
lichess opening table at the deepest named position of its first 24 plies.
A system takes its games by name; the position after ply 18 (Black has made
nine moves) goes in its book when Stockfish 19 at 300k nodes rates it within
120 cp of level, so a game starts from a fight rather than a decided position.

The opponent chooses the anti-Sicilians, and which ones it can choose depends
on Black's second move, so each Sicilian book is topped up to --anti of its
size with games that left the Open Sicilian (no ...cxd4 by ply 8) after the
same second move: 2...d6 for the Najdorf and the Dragon, 2...Nc6 for the
Sveshnikov and the Classical, 2...e6 for the Taimanov and the Kan. The share
is exact: a system short of main-line positions gets a smaller book, never
more side lines.
"""
import argparse
import collections
import glob
import os
import random
import re
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

SYSTEMS = {
    "najdorf": (("Sicilian Defense: Najdorf",), "d6"),
    "dragon": (("Sicilian Defense: Dragon",), "d6"),
    "sveshnikov": (("Sicilian Defense: Lasker-Pelikan",), "Nc6"),
    "kalashnikov": (("Sicilian Defense: Kalashnikov",), "Nc6"),
    "classical": (("Sicilian Defense: Classical", "Sicilian Defense: Richter-Rauzer"), "Nc6"),
    "taimanov": (("Sicilian Defense: Taimanov",), "e6"),
    "kan": (("Sicilian Defense: Kan",), "e6"),
    "marshall": (("Ruy Lopez: Marshall",), "e5"),
}
PLY = 18
# every Marshall is the same position at ply 18 (9.exd5 Nxd5 is forced), so its
# positions come from ply 28, after White has chosen how to meet the gambit
PLIES = {"marshall": 28}
# Black's moves to the Marshall gambit. A 1.e4 e5 game whose first departure
# from this line is White's (an anti-Marshall, the Italian, the Scotch, 2.Nc3)
# goes in the Marshall book's side-line pool, as an anti-Sicilian does in a
# Sicilian's; one where Black departs first is not this repertoire.
MARSHALL = "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 O-O c3 d5".split()


def opening_table(folder):
    names = {}
    for f in glob.glob(os.path.join(folder, "*.tsv")):
        for line in open(f, encoding="utf-8").read().splitlines()[1:]:
            _, name, pgn = line.split("\t")
            b = chess.Board()
            for tok in pgn.split():
                if not re.match(r"^\d+\.", tok):
                    b.push_san(tok)
            names[b.epd()] = name
    return names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn", nargs="*")
    parser.add_argument("--laion", default="")
    parser.add_argument("--index", default="")
    parser.add_argument("--per-system-games", type=int, default=20000,
                        help="LAION games read per system (and per anti-Sicilian pool)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--openings", default="E:/machete/sources/lichess-openings")
    parser.add_argument("--per", type=int, default=300)
    parser.add_argument("--anti", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--only", default="sicilian,marshall", help="which books to write: sicilian, marshall or both")
    parser.add_argument("--systems", default="", help="comma-separated systems to write; all by default")
    args = parser.parse_args()
    names = opening_table(args.openings)

    found = collections.defaultdict(dict)  # system or anti-<move> -> epd -> fen

    def put(key, fen):
        if fen:
            found[key][" ".join(fen.split()[:4])] = fen

    def take(sans, fens, name):
        """fens: the position after every ply played, by ply."""
        for system, (prefixes, _) in SYSTEMS.items():
            if system != "marshall" and name.startswith(prefixes):
                put(system, fens.get(PLIES.get(system, PLY)))
        if sans[:2] == ["e4", "c5"] and len(sans) > 3 and "cxd4" not in sans[:8]:
            put("anti-" + sans[3], fens.get(PLY))
        if sans[:2] == ["e4", "e5"]:
            off = next((i for i, (a, b) in enumerate(zip(sans, MARSHALL)) if a != b), None)
            if off is None and len(sans) >= len(MARSHALL):
                put("marshall", fens.get(PLIES["marshall"]))
            elif off is not None and off % 2 == 0:
                put("anti-e5", fens.get(PLIES["marshall"]))

    if args.laion:
        import pyarrow.parquet as pq
        names_by_id = {}
        for line in open(os.path.join(args.index, "openings.tsv"), encoding="utf-8"):
            i, _, name, _ = line.rstrip("\n").split("\t")
            names_by_id[int(i)] = name
        lines_by_id = {}
        for line in open(os.path.join(args.index, "openings.tsv"), encoding="utf-8"):
            i, _, _, uci = line.rstrip("\n").split("\t")
            lines_by_id[int(i)] = uci
        wanted = {i for i, n in names_by_id.items()
                  if (n.startswith("Sicilian") and "sicilian" in args.only)
                  or (lines_by_id[i].startswith("e2e4 e7e5") and "marshall" in args.only)}
        per = collections.Counter()
        for idx in sorted(glob.glob(os.path.join(args.index, "*.idx.parquet"))):
            t = pq.read_table(idx, columns=["row", "opening"]).to_pydict()
            rows = [(r, o) for r, o in zip(t["row"], t["opening"]) if o in wanted]
            if not rows:
                continue
            data = pq.read_table(os.path.join(args.laion, os.path.basename(idx).replace(".idx", "")), columns=["Moves"])
            moves = data.column("Moves")
            for r, o in rows:
                name = names_by_id[o]
                key = next((k for k, (ps, _) in SYSTEMS.items() if name.startswith(ps)), None) or \
                    ("e5" if lines_by_id[o].startswith("e2e4 e7e5") else "sicilian-other")
                if per[key] >= args.per_system_games:
                    continue
                per[key] += 1
                b, sans, fens = chess.Board(), [], {}
                for u in moves[r].as_py()[:max(PLY, *PLIES.values())]:
                    m = chess.Move.from_uci(u)
                    sans.append(b.san(m))
                    b.push(m)
                    fens[len(sans)] = b.fen()
                take(sans, fens, name)
            keys = (["e5", "marshall"] if "marshall" in args.only else []) + \
                ([k for k in SYSTEMS if k != "marshall"] + ["sicilian-other"] if "sicilian" in args.only else [])
            if all(per[k] >= args.per_system_games for k in keys):
                break
    for path in args.pgn:
        with open(path, encoding="utf-8", errors="replace") as handle:
            while True:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                if "FEN" in game.headers or "Variant" in game.headers:
                    continue
                b, sans, name, fens = chess.Board(), [], "?", {}
                for i, m in enumerate(game.mainline_moves()):
                    if i >= max(24, *PLIES.values()):
                        break
                    sans.append(b.san(m))
                    b.push(m)
                    name = names.get(b.epd(), name)
                    fens[len(sans)] = b.fen()
                take(sans, fens, name)
    for k in sorted(found):
        print("%-14s %5d distinct positions" % (k, len(found[k])))

    rng = random.Random(args.seed)
    sf = panel.open_engine("Stockfish", 64)

    def level(fens, want):
        rng.shuffle(fens)
        kept = []
        for fen in fens:
            if len(kept) >= want:
                break
            s = sf.analyse(chess.Board(fen), chess.engine.Limit(nodes=300000))["score"].pov(chess.BLACK).score(mate_score=3000)
            if abs(s) <= 120:
                kept.append(fen)
        return kept

    os.makedirs(args.out, exist_ok=True)
    for system, (_, second) in SYSTEMS.items():
        if ("marshall" if system == "marshall" else "sicilian") not in args.only:
            continue
        if args.systems and system not in args.systems.split(","):
            continue
        main_n = args.per if second is None else int(round(args.per * (1 - args.anti)))
        book = level(list(found[system].values()), main_n)
        anti_n = int(round(len(book) * args.anti / (1 - args.anti))) if second else 0
        anti = level(list(found.get("anti-" + second, {}).values()), anti_n) if second else []
        lines = book + anti
        rng.shuffle(lines)
        with open(os.path.join(args.out, system + ".epd"), "w", encoding="utf-8") as out:
            out.write("# %s: %d main-line and %d side-line positions at ply %d from %s, within 120 cp at 300k nodes\n"
                      % (system, len(book), len(anti), PLIES.get(system, PLY), "LAION self-play" if args.laion else ", ".join(os.path.basename(p) for p in args.pgn)))
            for fen in lines:
                out.write(fen + "\n")
        print("%-11s %3d main + %3d anti -> %s" % (system, len(book), len(anti), os.path.join(args.out, system + ".epd")))
    panel.quiet_quit(sf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
