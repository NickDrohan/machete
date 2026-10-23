"""Does the network under-value passed pawns once the queens are off?

    MACHETE_LAYERS=phase3 python harness/nnue/passer_bias.py CORPUS.bin NET.nnue [--sample 200000]

Takes queenless positions from a corpus the network did not train on and compares the network's
evaluation with the label (Stockfish's search score, side to move's view), grouped by how far the side to
move's most advanced passed pawn has got and how far the opponent's has. A network that under-values
passers reads low (negative error) as its own passer advances and high as the opponent's does; one that
judges them right shows no trend. Errors are in centipawns, network minus label, labels clipped to +/-1500
so won positions do not swamp the means.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference
from reference import RECORD

PAWN, QUEEN = 0, 4


def best_passer(colour, pawns_by_colour):
    """The relative rank (1-6, 0 for none) of colour's most advanced passed pawn."""
    best = 0
    for sq in pawns_by_colour[colour]:
        f, r = sq & 7, sq >> 3
        ahead = [(s & 7, s >> 3) for s in pawns_by_colour[1 - colour]]
        if colour == 0:
            blocked = any(abs(ef - f) <= 1 and er > r for ef, er in ahead)
            rel = r
        else:
            blocked = any(abs(ef - f) <= 1 and er < r for ef, er in ahead)
            rel = 7 - r
        if not blocked and rel > best:
            best = rel
    return best


PASSER_NET = [0, 0, 0, 0, 5, 25, 40, 0]  # src/eval.mach


def passer_sum(colour, pawns_by_colour):
    total = 0
    for sq in pawns_by_colour[colour]:
        f, r = sq & 7, sq >> 3
        ahead = [(s & 7, s >> 3) for s in pawns_by_colour[1 - colour]]
        blocked = any(abs(ef - f) <= 1 and (er > r if colour == 0 else er < r) for ef, er in ahead)
        if not blocked:
            total += PASSER_NET[r if colour == 0 else 7 - r]
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("net")
    ap.add_argument("--sample", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bonus", type=int, default=0, help="percent of the engine's PASSER_NET added, as PasserBonus does")
    args = ap.parse_args()
    records = np.fromfile(args.corpus, dtype=RECORD)
    rng = np.random.RandomState(args.seed)
    rows = records[rng.choice(len(records), size=min(args.sample, len(records)), replace=False)]
    net = reference.load(args.net)
    cells = {}
    used = 0
    for row in rows:
        n = int(row["count"])
        pieces = [(int(row["pieces"][k]) // 6, int(row["pieces"][k]) % 6, int(row["squares"][k])) for k in range(n)]
        if any(kind == QUEEN for _, kind, _ in pieces):
            continue
        stm = int(row["stm"])
        pawns = {0: [s for c, k, s in pieces if c == 0 and k == PAWN], 1: [s for c, k, s in pieces if c == 1 and k == PAWN]}
        us, them = best_passer(stm, pawns), best_passer(1 - stm, pawns)
        ev = reference.forward(net, reference.accumulate(net, pieces), stm, n)
        if args.bonus:
            ev += (passer_sum(stm, pawns) - passer_sum(1 - stm, pawns)) * args.bonus // 100
        label = max(-1500, min(1500, int(row["score"])))
        ev = max(-1500, min(1500, ev))
        cells.setdefault((us, them), []).append(ev - label)
        used += 1
    print("%d queenless positions of %d sampled; error = network - label (cp), side to move's view" % (used, len(rows)))
    print("rows: side to move's best passed pawn (relative rank, 0 none); columns: the opponent's")
    print("        " + "".join("%10d" % t for t in range(7)))
    for u in range(7):
        line = "%5d   " % u
        for t in range(7):
            v = cells.get((u, t), [])
            line += "%10s" % ("%+.0f/%d" % (np.mean(v), len(v)) if len(v) >= 200 else ".")
        print(line)
    print("\nby the side to move's passer alone:")
    for u in range(7):
        v = [x for (a, b), xs in cells.items() if a == u for x in xs]
        if len(v) >= 200:
            print("  rank %d: %+6.1f cp  (n=%d)" % (u, np.mean(v), len(v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
