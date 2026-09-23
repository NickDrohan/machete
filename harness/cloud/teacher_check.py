"""Prove a teacher built on another machine is the teacher we have been using.

    python harness/cloud/teacher_check.py record  harness/cloud/teacher_scores.json
    python harness/cloud/teacher_check.py compare harness/cloud/teacher_scores.json

Our corpus is labelled by five engines. A cloud machine cannot run the Windows
builds, so four of the five are rebuilt from source there, at the same release
tags. A rebuilt engine is only the same teacher if it scores positions the same
way - and HIST-06 is the reminder of what labels from a different source cost:
159 Elo.

So `record` runs each teacher here, on fixed positions at a fixed node count,
and writes their scores. `compare` runs the teachers the panel names on another
machine the same way and reports, per teacher, how many scores match exactly.
A node-limited search of the same code and the same network is deterministic,
so a correct build matches every one; a teacher that does not is excluded from
generation rather than trusted.

Exits 0 when every teacher matches, 1 when any does not, and prints the names
that do on the last line, for the bootstrap to use.
"""

import json
import os
import sys

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "nnue"))
import panel

TEACHERS = ["Stockfish", "Berserk", "Alexandria", "Obsidian", "Caissa"]
NODES = 20000
# a spread of phases, taken from the opening book and from known test suites
POSITIONS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R2QKB1R w KQ - 0 9",
    "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 1 5",
    "8/5pk1/6p1/3R4/1r5P/6P1/5PK1/8 w - - 0 40",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
    "2r3k1/pp3ppp/4p3/3pP3/3P4/P4N2/1P3PPP/2R3K1 b - - 0 25",
    "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
    "r1b1kb1r/pp1n1ppp/2p1pn2/q7/2BP4/2N1PN2/PP3PPP/R2QK2R w KQkq - 2 8",
]


def scores_of(name):
    engine = panel.open_engine(name, 64)
    try:
        out = []
        for fen in POSITIONS:
            info = engine.analyse(chess.Board(fen), chess.engine.Limit(nodes=NODES))
            score = info["score"].relative
            out.append(["mate", score.mate()] if score.is_mate() else ["cp", score.score()])
        return out
    finally:
        panel.quiet_quit(engine)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("record", "compare"):
        print(__doc__)
        return 2
    mode, path = sys.argv[1], sys.argv[2]
    if mode == "record":
        table = {name: scores_of(name) for name in TEACHERS}
        with open(path, "w") as handle:
            json.dump({"nodes": NODES, "positions": POSITIONS, "scores": table}, handle, indent=1)
        print("recorded {} teachers on {} positions at {} nodes".format(len(table), len(POSITIONS), NODES))
        return 0

    with open(path) as handle:
        reference = json.load(handle)
    good = []
    for name in TEACHERS:
        try:
            mine = scores_of(name)
        except Exception as problem:
            print("{:<11} could not run: {}: {}".format(name, type(problem).__name__, problem))
            continue
        want = reference["scores"][name]
        same = sum(1 for a, b in zip(mine, want) if list(a) == list(b))
        verdict = "identical" if same == len(want) else "DIFFERENT - excluded"
        print("{:<11} {}/{} scores match  {}".format(name, same, len(want), verdict))
        if same == len(want):
            good.append(name)
    print(",".join(good))
    return 0 if len(good) == len(TEACHERS) else 1


if __name__ == "__main__":
    sys.exit(main())
