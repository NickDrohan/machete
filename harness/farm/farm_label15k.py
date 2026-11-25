#!/usr/bin/env python3
"""Label a chunk of unlabelled positions at 15,000 nodes (the practical corpus, 2026-11-18).

    python3 farm_label15k.py IN.bin.raw0 OUT.bin.raw STOCKFISH WORKERS

Standard library only, for the farm. Every record gets Stockfish's score at NODES nodes, from the side to move, as
the generators' 15k chunks do; the PC's relabel loop then searches the close ones deeper (farm_relabel.py). Writes
OUT and OUT.done when finished.
"""
import multiprocessing as mp
import struct
import subprocess
import sys

REC = 70
NODES = 15000
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
        struct.pack_into("<h", out, k + 66, e.score(fen_of(rec), NODES))
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
    open(dst + ".done", "w").close()
    print("%s: %d positions labelled at %d nodes" % (dst, n, NODES))


if __name__ == "__main__":
    main()
