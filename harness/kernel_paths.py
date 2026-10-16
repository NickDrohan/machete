"""The SSE2 and the AVX2 kernels must search the same tree, and how fast each is.

    python harness/kernel_paths.py ENGINE NET [--depth 13]

The network's inner loops are hand-written assembly in src/kernels.mach, in
two widths; one binary carries both and picks at start-up. Unit tests hold
each kernel to its portable loop. This is the same claim from the outside:
the engine is run on a few positions to a fixed depth with the UCI option
Avx2 on and then off, and the two runs must report the same node count, score
and best move for every position. Integer arithmetic is exact at either
width, so any difference is a kernel that computes something else.

It also prints each path's speed and their ratio. That is not checked - it
depends on the machine and what else is running - but it is the number to
look at after anything rewrites the assembly (a compiler upgrade that changes
inline assembly's syntax, say): the same tree at half the speed is a kernel
that fell back to something slow.

Exit status 1 on any difference. A CPU without AVX2 has one path and nothing
to compare: that is said, and is not a failure.
"""
import argparse
import os
import subprocess
import sys

FENS = [
    "startpos",
    "fen r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "fen r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
    "fen 8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
]


def run(engine, net, avx2, depth):
    """[(nodes, score, bestmove)] for FENS, the accumulator the engine says it used, and nodes a second."""
    # one engine process a position: nothing has to wait for one search before sending the next
    results, label, nodes, ms = [], "?", 0, 0
    for fen in FENS:
        text = "\n".join(["uci", "setoption name Avx2 value %s" % ("true" if avx2 else "false"), "setoption name EvalFile value %s" % net,
                          "isready", "position " + fen, "go depth %d" % depth, ""])
        p = subprocess.Popen([engine], stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
        p.stdin.write(text)
        p.stdin.flush()
        last, best = None, None
        for line in p.stdout:
            line = line.strip()
            if line.startswith("info string network loaded"):
                label = line.split(",")[-1].strip().split()[0]
            if line.startswith("info") and " nodes " in line and " score " in line:
                last = line.split()
            if line.startswith("bestmove"):
                best = line.split()[1]
                break
        p.stdin.write("quit\n")
        p.stdin.flush()
        p.wait()
        at = last.index("score")
        results.append((int(last[last.index("nodes") + 1]), " ".join(last[at + 1:at + 3]), best))
        nodes += int(last[last.index("nodes") + 1])
        ms += int(last[last.index("time") + 1])
    return results, label, 1000.0 * nodes / max(1, ms)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("net")
    parser.add_argument("--depth", type=int, default=13)
    args = parser.parse_args()
    args.engine, args.net = os.path.abspath(args.engine), os.path.abspath(args.net)
    wide, wide_label, wide_nps = run(args.engine, args.net, True, args.depth)
    narrow, narrow_label, narrow_nps = run(args.engine, args.net, False, args.depth)
    if wide_label != "AVX2":
        print("this CPU runs the %s kernels only: nothing to compare" % wide_label)
        return 0
    if narrow_label != "SSE2":
        print("Avx2 false still ran the %s kernels" % narrow_label)
        return 1
    bad = 0
    for fen, a, b in zip(FENS, wide, narrow):
        if a != b:
            bad += 1
            print("DIFFERENT at %s\n  AVX2 %s\n  SSE2 %s" % (fen, a, b))
    print("%d positions to depth %d: %s" % (len(FENS), args.depth, "the two kernel paths search the same tree" if not bad else "%d differ" % bad))
    print("AVX2 %.0f nodes a second, SSE2 %.0f: AVX2 is %.2f times as fast" % (wide_nps, narrow_nps, wide_nps / max(1.0, narrow_nps)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
