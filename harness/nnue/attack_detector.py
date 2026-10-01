"""Can a cheap test tell an attacking position from an ordinary one?

    python harness/nnue/attack_detector.py --suite E:/machete/books/attack_suite.epd \
        --corpus E:/machete/corpora/pi_gen3_pi01_sf19.bin [--sample 20000]

The attack data hurt when it was mixed into every position (C31, -18 against
C30), so the plan is to apply it only where an attack is on the board: in the
search (attack moves searched deeper) or in the network (an output used only
there). Both need a detector the engine can afford at every node. This scores
three candidates on the attack suite (the winner to move, the move that kept
the attack) against ordinary positions from a training corpus, and prints how
often each fires on both at a range of thresholds.

  pressure  the side to move's pieces attacking the enemy king zone (the king's
            square, its neighbours, and the three squares in front of those),
            weighted queen 4, rook 3, minor 2, pawn 1
  shield    the defender's own pawns in front of its king: fewer is weaker
  files     open or half-open files (for the attacker) on and beside the king
  danger    pressure + 2 * files - shield, the combined score
"""
import argparse
import os
import random
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD  # noqa: E402

WEIGHT = {chess.QUEEN: 4, chess.ROOK: 3, chess.BISHOP: 2, chess.KNIGHT: 2, chess.PAWN: 1, chess.KING: 0}


def zone(king, defender):
    sq = set()
    for f in range(chess.square_file(king) - 1, chess.square_file(king) + 2):
        for r in range(chess.square_rank(king) - 1, chess.square_rank(king) + 2):
            if 0 <= f < 8 and 0 <= r < 8:
                sq.add(chess.square(f, r))
    step = 1 if defender == chess.WHITE else -1
    for s in list(sq):
        r = chess.square_rank(s) + 2 * step
        if 0 <= r < 8:
            sq.add(chess.square(chess.square_file(s), r))
    return sq


def features(board):
    me = board.turn
    them = not me
    king = board.king(them)
    if king is None:
        return 0, 0, 0
    z = zone(king, them)
    pressure = 0
    for s in z:
        for a in board.attackers(me, s):
            pressure += WEIGHT[board.piece_type_at(a)]
    step = 1 if them == chess.WHITE else -1
    shield, files = 0, 0
    for f in range(max(0, chess.square_file(king) - 1), min(8, chess.square_file(king) + 2)):
        for d in (1, 2):
            r = chess.square_rank(king) + d * step
            if 0 <= r < 8 and board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, them):
                shield += 1
        mine = any(board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, me) for r in range(8))
        if not mine:
            files += 1
    return pressure, shield, files


def from_record(rec):
    b = chess.Board(None)
    for i in range(rec["count"]):
        code = int(rec["pieces"][i])
        colour = chess.WHITE if code < 6 else chess.BLACK
        b.set_piece_at(int(rec["squares"][i]), chess.Piece(code % 6 + 1, colour))
    b.turn = chess.WHITE if rec["stm"] == 0 else chess.BLACK
    return b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    suite = []
    for line in open(args.suite, encoding="utf-8"):
        if line.strip() and not line.startswith("#"):
            suite.append(chess.Board(" ".join(line.split()[:4]) + " 0 1"))
    data = np.memmap(args.corpus, dtype=RECORD, mode="r")
    rng = random.Random(args.seed)
    normal = []
    while len(normal) < args.sample:
        rec = data[rng.randrange(len(data))]
        if rec["count"] >= 20:  # the suite's positions are middlegames
            b = from_record(rec)
            if b.is_valid():
                normal.append(b)

    rows = {}
    for name, boards in (("suite", suite), ("normal", normal)):
        f = np.array([features(b) for b in boards])
        rows[name] = dict(pressure=f[:, 0], shield=f[:, 1], files=f[:, 2], danger=f[:, 0] + 2 * f[:, 2] - f[:, 1])
    print("%d attack-suite positions, %d ordinary middlegame positions" % (len(suite), len(normal)))
    for key in ("pressure", "danger"):
        print("\n%s: fires at >= T on the suite / on ordinary positions" % key)
        for t in range(2, 26, 2):
            s = (rows["suite"][key] >= t).mean()
            n = (rows["normal"][key] >= t).mean()
            print("  T=%2d   suite %5.1f%%   ordinary %5.1f%%   ratio %.1f" % (t, 100 * s, 100 * n, s / max(n, 1e-9)))
    for key in ("shield", "files"):
        print("%s: suite mean %.2f, ordinary mean %.2f" % (key, rows["suite"][key].mean(), rows["normal"][key].mean()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
