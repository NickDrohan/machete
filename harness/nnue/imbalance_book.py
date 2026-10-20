"""A book of classical positions where one side is really but not decisively better, from real games.

    python harness/nnue/imbalance_book.py OUT.epd CORPUS.bin [CORPUS.bin ...] [--per-band 10000] [--min-men 20] [--seed 1]

Deep self-play from balanced openings is a narrow diet: at 15,000 nodes two positions in three come
from drawn games and score within half a pawn of zero, and a network trained on it alone lost about
400 Elo to one trained on 500-node games, which are full of decided positions (2026-10-17). Played
from these starts instead, the same deep search has an advantage to convert or defend.

Positions are taken from the training corpora (engine games from many openings), not made by removing
pieces: the imbalance is one that real play reaches, material or not. Each is still a game with play
left (at least --min-men men), and the corpus label puts one side ahead by 100 to 700 centipawns, the
same number from each of four bands (100-200, 200-350, 350-500, 500-700); 700 is gen's ceiling for an
"odds" book. Duplicates are dropped.
"""
import argparse
import collections
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD  # noqa: E402
from rook_book import fen  # noqa: E402

BANDS = ((100, 200), (200, 350), (350, 500), (500, 701))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("corpora", nargs="+")
    parser.add_argument("--per-band", type=int, default=10000)
    parser.add_argument("--min-men", type=int, default=20)
    parser.add_argument("--scan", type=int, default=30000000, help="records read from each corpus at most")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = np.random.RandomState(args.seed)

    maps = [np.memmap(p, dtype=RECORD, mode="r") for p in args.corpora]
    pools = collections.defaultdict(list)
    for ci, rows in enumerate(maps):
        n = min(len(rows), args.scan)
        for start in range(0, n, 2000000):
            chunk = np.asarray(rows[start:min(n, start + 2000000)])
            s = np.abs(chunk["score"].astype(np.int32))
            alive = chunk["count"] >= args.min_men
            for b, (lo, hi) in enumerate(BANDS):
                hit = np.nonzero(alive & (s >= lo) & (s < hi))[0]
                if len(hit) > 3 * args.per_band // max(1, len(args.corpora)):
                    hit = rng.choice(hit, 3 * args.per_band // max(1, len(args.corpora)), replace=False)
                pools[b].extend((ci, int(i) + start) for i in hit)
        print("scanned", args.corpora[ci], n, flush=True)

    kept, seen = [], set()
    for b in range(len(BANDS)):
        pool = pools[b]
        got = 0
        for j in rng.permutation(len(pool)):
            if got >= args.per_band:
                break
            ci, i = pool[j]
            board = fen(maps[ci][i])
            if not board.is_valid() or board.is_game_over():
                continue
            key = board.board_fen() + (" w" if board.turn else " b")
            if key in seen:
                continue
            seen.add(key)
            kept.append((board.fen(), b))
            got += 1
        print("band {}-{}: {} of {} candidates".format(BANDS[b][0], BANDS[b][1] - 1, got, len(pool)), flush=True)

    order = rng.permutation(len(kept))
    with open(args.out, "w") as out:
        out.write("# classical positions one side leads by 100-700 cp, from real games, {} men or more: imbalance_book.py seed {}\n".format(
            args.min_men, args.seed))
        out.write("# {} positions; by band {}: {}\n".format(len(kept), [(lo, hi - 1) for lo, hi in BANDS],
                                                          dict(collections.Counter(k[1] for k in kept))))
        for j in order:
            out.write(kept[j][0] + "\n")
    print("wrote", args.out, len(kept))


if __name__ == "__main__":
    main()
