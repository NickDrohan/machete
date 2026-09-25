"""Compare two builds' speed on the bench, interleaved, on a machine that may be busy.

    python harness/bench_ab.py OLD.exe NEW.exe [--rounds 10]

Node rates move by up to 79% with whatever else the machine is doing, so two
builds measured one after the other compare their surroundings as much as
themselves. This runs them alternately - old, new, old, new - so both see the
same load, and refuses to compare at all unless both searched the identical
tree: a speed comparison between different trees measures nothing.

It reports the median and the best of each. The best is the run least
disturbed by anything else, which makes it the fairest estimate of what the
code can do; the median says how the two compare under the load as it was.
"""

import argparse
import os
import re
import statistics
import subprocess
import sys


def bench(path):
    done = subprocess.run([path, "bench"], capture_output=True, text=True)
    out = done.stdout + done.stderr         # the node rate goes to stderr
    nodes = re.search(r"nodes (\d+)", out)
    rate = re.search(r"(\d+) nodes/s", out)
    if not nodes or not rate:
        raise SystemExit("no bench line from {}:\n{}".format(path, out))
    return int(nodes.group(1)), int(rate.group(1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    args.old, args.new = os.path.abspath(args.old), os.path.abspath(args.new)

    rates = {args.old: [], args.new: []}
    trees = {}
    for _ in range(args.rounds):
        for path in (args.old, args.new):
            nodes, rate = bench(path)
            trees.setdefault(path, set()).add(nodes)
            rates[path].append(rate)

    if len(trees[args.old]) != 1 or trees[args.old] != trees[args.new]:
        print("the two builds searched different trees: {} and {}".format(
            sorted(trees[args.old]), sorted(trees[args.new])))
        print("a speed comparison between different trees measures nothing")
        return 1

    print("identical tree: {} nodes".format(trees[args.old].pop()))
    print("{:<12}{:>12}{:>12}".format("", "median", "best"))
    for label, path in (("old", args.old), ("new", args.new)):
        print("{:<12}{:>12,}{:>12,}".format(label, int(statistics.median(rates[path])), max(rates[path])))
    median = statistics.median(rates[args.new]) / statistics.median(rates[args.old]) - 1
    best = max(rates[args.new]) / float(max(rates[args.old])) - 1
    print("new against old: median {:+.1%}, best {:+.1%}".format(median, best))
    return 0


if __name__ == "__main__":
    sys.exit(main())
