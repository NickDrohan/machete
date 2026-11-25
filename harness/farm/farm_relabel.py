#!/usr/bin/env python3
"""Score a generated chunk's close positions again, deeper the closer they are (the owner, 2026-11-07).

    python3 farm_relabel.py IN.bin OUT.bin STOCKFISH WORKERS

Standard library only, for the farm. A record whose 15k-node label is within CLOSE cp of level is searched again at
nodes(|label|) = DEEPEST * (SHALLOWEST / DEEPEST) ** (|label| / CLOSE): 200k nodes at level, 60k at two pawns,
logarithmic between. Decided positions keep their label. Records are gen.py's 70 bytes; the score is from the side
to move, as Stockfish's is.
"""
import multiprocessing as mp
import struct
import subprocess
import sys

REC = 70
CLOSE, SHALLOWEST, DEEPEST = 200, 60000, 200000
LETTERS = "PNBRQKpnbrqk"


def nodes_for(cp):
    return int(round(DEEPEST * (SHALLOWEST / DEEPEST) ** (min(abs(cp), CLOSE) / CLOSE)))


def fen_of(rec):
    stm, count = rec[0], rec[1]
    board = [None] * 64
    for i in range(count):
        board[rec[34 + i]] = LETTERS[rec[2 + i]]
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for f in range(8):
            p = board[rank * 8 + f]
            if p is None:
                empty += 1
            else:
                row += (str(empty) if empty else "") + p
                empty = 0
        rows.append(row + (str(empty) if empty else ""))
    return "/".join(rows) + (" w" if stm == 0 else " b") + " - - 0 1"


class Engine:
    def __init__(self, path):
        self.p = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.send("uci")
        self.wait("uciok")
        self.send("setoption name Threads value 1")
        self.send("setoption name Hash value 32")
        self.send("isready")
        self.wait("readyok")

    def send(self, line):
        self.p.stdin.write(line + "\n")

    def wait(self, word):
        for line in self.p.stdout:
            if line.startswith(word):
                return line

    def score(self, fen, nodes):
        self.send("ucinewgame")
        self.send("position fen " + fen)
        self.send("go nodes %d" % nodes)
        last = None
        for line in self.p.stdout:
            if " score " in line:
                last = line.split()
            if line.startswith("bestmove"):
                break
        i = last.index("score")
        if last[i + 1] == "mate":
            return 10000 if int(last[i + 2]) > 0 else -10000
        return max(-10000, min(10000, int(last[i + 2])))


def work(job):
    path, chunk = job
    e = Engine(path)
    out = bytearray(chunk)
    deep = 0
    for k in range(0, len(chunk), REC):
        rec = chunk[k:k + REC]
        cp = struct.unpack_from("<h", rec, 66)[0]
        if abs(cp) < CLOSE:
            struct.pack_into("<h", out, k + 66, e.score(fen_of(rec), nodes_for(cp)))
            deep += 1
    e.send("quit")
    return bytes(out), deep


def main():
    src, dst, engine, workers = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    data = open(src, "rb").read()
    n = len(data) // REC
    step = (n + workers * 8 - 1) // (workers * 8)
    jobs = [(engine, data[i * REC:(i + step) * REC]) for i in range(0, n, step)]
    with mp.Pool(workers) as pool, open(dst + ".tmp", "wb") as f:
        deep = 0
        for chunk, d in pool.imap(work, jobs):
            f.write(chunk)
            deep += d
    import os
    os.replace(dst + ".tmp", dst)
    print("%s: %d positions, %d scored again deeper" % (dst, n, deep))


if __name__ == "__main__":
    main()
