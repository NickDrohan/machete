"""Which of two builds searches faster, on a machine that is not quiet.

    python harness/speed_ab.py A.exe B.exe --net NET [--nodes 1500000] [--rounds 6]

Both builds search the same positions to the same node count with the same
network, alternating A B B A so that a load that comes and goes lands on both
sides alike, and the ratio of their times is reported per round and overall.
A node-limited search on one thread is deterministic, so the two builds do
identical work whenever their search code is identical; the script says so
when their node counts and best moves differ, since then the comparison is
of different trees and says nothing about speed alone.
"""

import argparse
import statistics
import sys
import time

import chess
import chess.engine
import psutil

FENS = [
    chess.STARTING_FEN,
    "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R2QKB1R w KQ - 0 9",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/5pk1/6p1/3R4/5P2/6P1/r5PK/8 w - - 0 40",
    "2r2rk1/pp1bqppp/2n1pn2/3p4/3P4/2PBPN2/PP1N1PPP/R2Q1RK1 w - - 0 12",
]


def run(path, net, nodes, options=()):
    """CPU seconds the engine spent on the searches, and what it found.

    CPU time, not wall time: on a machine running other jobs, wall time also
    counts the moments the engine waited for a core, which is noise here.
    """
    engine = chess.engine.SimpleEngine.popen_uci(path)
    settings = {"EvalFile": net}
    for option in options:
        name, _, value = option.partition("=")
        settings[name] = {"true": True, "false": False}.get(value, value)
    engine.configure(settings)
    process = psutil.Process(engine.transport.get_pid())
    before = sum(process.cpu_times()[:2])
    trees = []
    for fen in FENS:
        info = engine.analyse(chess.Board(fen), chess.engine.Limit(nodes=nodes), game=object())
        trees.append((info.get("nodes"), info["pv"][0].uci()))
    used = sum(process.cpu_times()[:2]) - before
    engine.quit()
    return used, trees


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--net", required=True)
    parser.add_argument("--nodes", type=int, default=1500000)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--option-a", action="append", default=[], help="UCI option for A as Name=Value")
    parser.add_argument("--option-b", action="append", default=[], help="UCI option for B as Name=Value")
    args = parser.parse_args()

    ratios, same = [], True
    # sides, not paths: A and B may be one binary with different options
    sides = {"A": (args.a, args.option_a), "B": (args.b, args.option_b)}
    for round_ in range(args.rounds):
        times = {"A": [], "B": []}
        trees = {}
        for side in ("A", "B", "B", "A"):
            path, options = sides[side]
            elapsed, tree = run(path, args.net, args.nodes, options)
            times[side].append(elapsed)
            trees[side] = tree
        same = same and trees["A"] == trees["B"]
        ratio = sum(times["A"]) / sum(times["B"])
        ratios.append(ratio)
        print("round {}: A {:.2f}s  B {:.2f}s  A/B {:.3f}".format(
            round_ + 1, sum(times["A"]) / 2, sum(times["B"]) / 2, ratio))
        sys.stdout.flush()
    print("B is {:.1%} faster than A (median ratio {:.3f}, spread {:.3f}-{:.3f})".format(
        statistics.median(ratios) - 1, statistics.median(ratios), min(ratios), max(ratios)))
    if not same:
        print("note: the builds searched different trees, so this is not a pure speed comparison")
    return 0


if __name__ == "__main__":
    sys.exit(main())
