"""What a larger transposition table buys: the same search time, how deep and how many nodes.

    python harness/hash_depth.py ENGINE NET [--threads 8] [--seconds 15] [--hash 128 2048] [--positions 16]

A table too small for the search keeps overwriting entries it still needs, so
the search repeats work. This runs each position for a fixed time at each
table size and reports the depth reached, the nodes searched and their rate.
It is a proxy, cheap enough to run before a match: more depth in the same
time is strength, but only a match says how much.

Positions are taken evenly from harness/books/balanced_200.epd. With several
threads a search is not repeatable, so read the averages, not single lines.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def search(engine, net, fen, threads, megabytes, seconds):
    text = "\n".join(["uci", "setoption name Threads value %d" % threads, "setoption name Hash value %d" % megabytes,
                      "setoption name EvalFile value %s" % net, "setoption name Repertoire value 0", "isready",
                      "position fen " + fen, "go movetime %d" % (seconds * 1000), ""])
    p = subprocess.Popen([engine], stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
    p.stdin.write(text)
    p.stdin.flush()
    last = None
    for line in p.stdout:
        if line.startswith("info") and " depth " in line and " nodes " in line:
            last = line.split()
        if line.startswith("bestmove"):
            break
    p.stdin.write("quit\n")
    p.stdin.flush()
    p.wait()
    field = lambda name: int(last[last.index(name) + 1])
    return field("depth"), field("nodes"), field("time")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("net")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--hash", type=int, nargs="+", default=[128, 2048])
    parser.add_argument("--positions", type=int, default=16)
    args = parser.parse_args()
    engine, net = os.path.abspath(args.engine), os.path.abspath(args.net)
    book = [l.strip() for l in open(os.path.join(HERE, "books", "balanced_200.epd")) if l.strip() and not l.startswith("#")]
    fens = book[::max(1, len(book) // args.positions)][:args.positions]
    totals = {h: [0, 0, 0] for h in args.hash}
    deeper = {h: 0 for h in args.hash}
    for n, fen in enumerate(fens):
        row = []
        for h in args.hash:
            depth, nodes, ms = search(engine, net, fen + " 0 1" if len(fen.split()) == 4 else fen, args.threads, h, args.seconds)
            totals[h][0] += depth
            totals[h][1] += nodes
            totals[h][2] += ms
            row.append((h, depth, nodes))
        best = max(d for _, d, _ in row)
        for h, d, _ in row:
            deeper[h] += d == best and sum(1 for _, x, _ in row if x == best) == 1
        print("%2d  " % (n + 1) + "   ".join("%5d MB: depth %2d, %5.1fM nodes" % (h, d, nd / 1e6) for h, d, nd in row), flush=True)
    print()
    for h in args.hash:
        d, nodes, ms = totals[h]
        print("%5d MB: mean depth %.2f, %.2fM nodes a second, deepest alone on %d of %d positions" % (
            h, d / len(fens), nodes / max(1, ms) / 1000, deeper[h], len(fens)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
