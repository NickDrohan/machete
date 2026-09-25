"""Does machete gain or lose ground as the clock lengthens?

    python harness/scaling.py ENGINE --net NET --games 60 --out data/scaling.json

Our rating is measured at 200 ms a move against opponents whose published
ratings come from 40 moves in 15 minutes. If machete's relative strength falls
as time is added, that rating is inflated on the scale it is quoted on, and the
error compounds: every comparison anchored to it inherits the bias.

There is already a hint of it. Against Spike 1.4, machete scored 0.512 over 40
games at 200 ms and 0.375 over 40 games at 800 ms. Both samples carry about
+/- 0.15, so they overlap and prove nothing. This runs the same opponents
across a wider spread of budgets with enough games to separate the cases.

The mechanism, if it is real, is that an evaluation advantage saturates with
depth while search weaknesses compound with it: more time lets the opponent
find things our pruning discards. That would redirect work from the network to
the search, which is the opposite of where the last several days went.

Every cell is written as it completes, so an interrupted run is still evidence.
"""

import argparse
import itertools
import json
import os
import subprocess
import sys
import time

import arena

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = arena.ENGINES

# opponents near or above our level: below it, scores saturate and say nothing
OPPONENTS = [
    ("Spike 1.4", r"Spike\Spike1.4.exe"),
    ("Hermann 2.8", r"Hermann\Hermann28_64.exe"),
    ("Ruffian 1.0.5", r"Ruffian\Ruffian_105.exe"),
]


def run_cell(engine, net, opponent_path, movetime, games, concurrency, seed):
    """One opponent at one time control. Returns the score for machete."""
    command = [sys.executable, os.path.join(HERE, "match.py"),
               os.path.abspath(engine), opponent_path,
               "--games", str(games), "--movetime", str(movetime),
               "--concurrency", str(concurrency), "--seed", str(seed),
               "--watch", "0", "--pgn", ""]
    if net:
        command += ["--option-a", "EvalFile=" + os.path.abspath(net)]
    out = subprocess.run(command, capture_output=True, text=True).stdout
    wins = draws = losses = 0
    for line in out.splitlines():
        if line.startswith("games "):
            parts = line.split()
            wins, draws, losses = int(parts[3]), int(parts[5]), int(parts[7])
    played = wins + draws + losses
    if not played:
        return None
    return {"wins": wins, "draws": draws, "losses": losses, "games": played,
            "score": (wins + 0.5 * draws) / played}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--net", default="")
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--movetimes", default="200,800,3200")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--out", default="data/scaling.json")
    parser.add_argument("--seed", type=int, default=31)
    args = parser.parse_args()

    budgets = [int(t) for t in args.movetimes.split(",")]
    cells = []
    started = time.time()

    # longest budgets last: an interrupted run then still has the cheap cells
    for movetime, (name, relative) in itertools.product(budgets, OPPONENTS):
        path = os.path.join(ARENA, relative)
        if not os.path.exists(path):
            print("{:<16} {:>6} ms  engine not found".format(name, movetime))
            continue
        print("{:<16} {:>6} ms  playing {} games...".format(name, movetime, args.games),
              end=" ", flush=True)
        result = run_cell(args.engine, args.net, path, movetime,
                          args.games, args.concurrency, args.seed)
        if result is None:
            print("no games")
            continue
        result.update({"opponent": name, "movetime": movetime})
        cells.append(result)
        print("score {:.3f}  ({}-{}-{})".format(
            result["score"], result["wins"], result["draws"], result["losses"]))
        with open(args.out, "w") as handle:
            json.dump({"cells": cells, "engine": args.engine, "net": args.net}, handle, indent=1)

    print("\n{:<16}".format("opponent") + "".join("{:>10}".format(str(t) + "ms") for t in budgets))
    for name, _ in OPPONENTS:
        row = "{:<16}".format(name)
        for movetime in budgets:
            hit = [c for c in cells if c["opponent"] == name and c["movetime"] == movetime]
            row += "{:>10}".format("{:.3f}".format(hit[0]["score"]) if hit else "-")
        print(row)
    print("\n{:.1f} hours".format((time.time() - started) / 3600.0))
    print("a score that falls as the budget rises means the rating quoted at "
          "200 ms is optimistic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
