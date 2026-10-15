"""How far a 1,500-node label sits from a longer search of the same position.

The generator's node budget has never been swept (ASSUMPTIONS.md). Deeper
labels lost when they replaced positions (C10, C11, C15), which does not say
whether the same position, searched longer, would teach a different target.
Castling and en passant are absent from the record, so both searches here
see the same reconstructed board and the difference is the budget alone.

    python harness/nnue/label_depth.py CORPUS.bin --net c33.nnue --sample 600
"""

import argparse
import os
import subprocess
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference
from fit_scale import board_of
from reference import RECORD

SHALLOW = 1500
DEEP = 16000


class Uci:
    """One engine process. ucinewgame between the two budgets, so the longer
    search does not inherit the shorter one's table and the shorter one does
    not return the longer one's score."""

    def __init__(self, path):
        self.proc = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            cwd=os.path.dirname(path))
        self._send("uci")
        self._until("uciok")
        self._send("setoption name Threads value 1")
        self._send("setoption name Hash value 64")
        self._send("isready")
        self._until("readyok")

    def _send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _until(self, token):
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SystemExit("engine closed waiting for " + token)
            lines.append(line.rstrip("\n"))
            if line.startswith(token):
                return lines

    def score(self, board, nodes):
        self._send("ucinewgame")
        self._send("isready")
        self._until("readyok")
        self._send("position fen " + board.fen())
        self._send("go nodes " + str(nodes))
        lines = self._until("bestmove")
        cp = None
        for line in reversed(lines):
            if " score mate " in line:
                mate = int(line.split(" score mate ")[1].split()[0])
                return 10000 if mate > 0 else -10000
            if " score cp " in line:
                cp = int(line.split(" score cp ")[1].split()[0])
                break
        if cp is None:
            raise SystemExit("no score from " + board.fen())
        return cp

    def close(self):
        self._send("quit")
        self.proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--net", default="")
    parser.add_argument("--sample", type=int, default=600)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--band", type=int, default=400,
                        help="only positions whose stored label is inside this")
    args = parser.parse_args()

    data = np.memmap(args.corpus, dtype=RECORD, mode="r")
    rng = np.random.RandomState(args.seed)
    # reservoir over the file so the sample is not the prefix
    want = []
    seen = 0
    step = max(1, len(data) // (args.sample * 40))
    for i in range(0, len(data), step):
        if abs(int(data[i]["score"])) > args.band:
            continue
        seen += 1
        if len(want) < args.sample:
            want.append(i)
        else:
            j = rng.randint(0, seen)
            if j < args.sample:
                want[j] = i
    print("{} positions from {} inside +/-{} cp".format(
        len(want), os.path.basename(args.corpus), args.band))

    net = reference.load(args.net) if args.net else None
    engine = Uci(args.engine)

    rows = []
    for n, i in enumerate(want):
        board = board_of(data[i])
        if not board.is_valid() or board.is_game_over():
            continue
        shallow = engine.score(board, SHALLOW)
        deep = engine.score(board, DEEP)
        stored = int(data[i]["score"])
        net_cp = None
        if net is not None:
            pieces = reference.pieces_of(board)
            side = reference.WHITE if board.turn == chess.WHITE else reference.BLACK
            net_cp = reference.forward(net, reference.accumulate(net, pieces), side, len(pieces))
        rows.append((stored, shallow, deep, net_cp))
        if (n + 1) % 50 == 0:
            print("  scored {}".format(n + 1), flush=True)
    engine.close()

    stored = np.array([r[0] for r in rows])
    shallow = np.array([r[1] for r in rows])
    deep = np.array([r[2] for r in rows])
    gap = deep - shallow

    def report(name, a, b):
        d = a.astype(np.float64) - b.astype(np.float64)
        print("{}  n {:,}  mae {:.1f} cp  median |d| {:.0f}  p90 {:.0f}  corr {:.3f}".format(
            name, len(d), np.mean(np.abs(d)), np.median(np.abs(d)),
            np.percentile(np.abs(d), 90), np.corrcoef(a, b)[0, 1]))

    print()
    report("deep {} vs shallow {}".format(DEEP, SHALLOW), deep, shallow)
    report("shallow vs stored label", shallow, stored)
    report("deep vs stored label", deep, stored)
    close = np.abs(shallow) <= 200
    if np.count_nonzero(close) > 20:
        report("deep vs shallow, |shallow|<=200", deep[close], shallow[close])
    print("deep and shallow differ by >50 cp: {:.1f}%   >100 cp: {:.1f}%".format(
        100.0 * np.mean(np.abs(gap) > 50), 100.0 * np.mean(np.abs(gap) > 100)))
    if net is not None:
        net_cp = np.array([r[3] for r in rows])
        report("C33 net vs deep", net_cp, deep)
        report("C33 net vs shallow", net_cp, shallow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
