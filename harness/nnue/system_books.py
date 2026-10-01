"""Books of real positions for each Black system against 1.e4, for measuring
which one machete plays best.

    python harness/nnue/system_books.py PGN [PGN ...] --out DIR [--per 300] [--anti 0.3]

Every game of the PGNs (TCEC: strong engines, real theory) is named by the
lichess opening table at the deepest named position of its first 24 plies.
A system takes its games by name; the position after ply 18 (Black has made
nine moves) goes in its book when Stockfish 19 at 300k nodes rates it within
120 cp of level, so a game starts from a fight rather than a decided position.

The opponent chooses the anti-Sicilians, and which ones it can choose depends
on Black's second move, so each Sicilian book is topped up to --anti of its
size with games that left the Open Sicilian (no ...cxd4 by ply 8) after the
same second move: 2...d6 for the Najdorf and the Dragon, 2...Nc6 for the
Sveshnikov and the Classical, 2...e6 for the Taimanov and the Kan.
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
    "classical": (("Sicilian Defense: Classical", "Sicilian Defense: Richter-Rauzer"), "Nc6"),
    "taimanov": (("Sicilian Defense: Taimanov",), "e6"),
    "kan": (("Sicilian Defense: Kan",), "e6"),
    "marshall": (("Ruy Lopez: Marshall",), None),
}
PLY = 18


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
    parser.add_argument("pgn", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--openings", default="E:/machete/sources/lichess-openings")
    parser.add_argument("--per", type=int, default=300)
    parser.add_argument("--anti", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    names = opening_table(args.openings)

    found = collections.defaultdict(dict)  # system or anti-<move> -> epd -> fen
    for path in args.pgn:
        with open(path, encoding="utf-8", errors="replace") as handle:
            while True:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                if "FEN" in game.headers or "Variant" in game.headers:
                    continue
                b, sans, name, at = chess.Board(), [], "?", None
                for i, m in enumerate(game.mainline_moves()):
                    if i >= max(24, PLY):
                        break
                    sans.append(b.san(m))
                    b.push(m)
                    name = names.get(b.epd(), name)
                    if i + 1 == PLY:
                        at = b.fen()
                if at is None:
                    continue
                for system, (prefixes, _) in SYSTEMS.items():
                    if name.startswith(prefixes):
                        found[system][" ".join(at.split()[:4])] = at
                if sans[:2] == ["e4", "c5"] and len(sans) > 3 and "cxd4" not in sans[:8]:
                    found["anti-" + sans[3]][" ".join(at.split()[:4])] = at
    for k in sorted(found):
        print("%-14s %5d distinct positions at ply %d" % (k, len(found[k]), PLY))

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
        main_n = args.per if second is None else int(round(args.per * (1 - args.anti)))
        book = level(list(found[system].values()), main_n)
        anti = level(list(found.get("anti-" + second, {}).values()), args.per - len(book)) if second else []
        lines = book + anti
        rng.shuffle(lines)
        with open(os.path.join(args.out, system + ".epd"), "w", encoding="utf-8") as out:
            out.write("# %s: %d main-line and %d anti-Sicilian positions at ply %d from %s, within 120 cp at 300k nodes\n"
                      % (system, len(book), len(anti), PLY, ", ".join(os.path.basename(p) for p in args.pgn)))
            for fen in lines:
                out.write(fen + "\n")
        print("%-11s %3d main + %3d anti -> %s" % (system, len(book), len(anti), os.path.join(args.out, system + ".epd")))
    panel.quiet_quit(sf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
