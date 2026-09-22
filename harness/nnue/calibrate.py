"""Score evaluations against what actually happened.

    python harness/nnue/calibrate.py data/goldset.json --engine ENGINE --net NET

Every position in the gold set carries a measured result - the score strong
engines actually achieved from it over thirty games - and every engine's
opinion of the same position. That makes two questions arithmetic rather than
argument: how many centipawns each engine means by "winning", and whose
opinion best predicts the result.

The first question has to be answered before engines can be mixed as teachers.
An evaluation is turned into a win probability by `sigmoid(cp / K)`, and K is
not the same for every engine: one reports -1035 where another reports -738
for the same position. Fitting K per engine on measured outcomes puts them on
one scale, and the fitted value is the constant the data generator needs.

The second question is the one worth having a gold set for. Comparing engines
by their published rating says which plays better; comparing them here says
whose evaluation is closest to the truth, which is a different thing and the
one that matters when choosing whose opinion to train on.

Machete's own network is scored the same way, on positions it has never seen
and against a target no evaluation function produced.
"""

import argparse
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as engines


def probability(cp, scale):
    return 1.0 / (1.0 + math.exp(-cp / scale))


def fit_scale(pairs):
    """The K that best turns this engine's centipawns into observed outcomes."""
    best, best_error = None, None
    scale = 40.0
    while scale <= 1200.0:
        error = sum((probability(cp, scale) - outcome) ** 2 for cp, outcome in pairs)
        if best_error is None or error < best_error:
            best, best_error = scale, error
        scale += 5.0
    return best, math.sqrt(best_error / len(pairs))


def report(rows, label):
    print()
    print("{:<12} {:>7} {:>9} {:>9} {:>8}".format(label, "scale", "rmse", "mae", "sign"))
    for name, scale, rmse, mae, sign, n in rows:
        print("{:<12} {:>7.0f} {:>9.3f} {:>9.3f} {:>7.0f}% ".format(
            name, scale, rmse, mae, 100.0 * sign))


def machete_evals(engine, net, fens):
    """Ask the engine for its network's score on each position."""
    out = []
    for fen in fens:
        result = subprocess.check_output(
            [os.path.abspath(engine), "nnue", os.path.abspath(net)] + fen.split())
        out.append(int(result.decode("ascii").strip()))
    return out


def measure(name, scores, outcomes):
    pairs = [(cp, out) for cp, out in zip(scores, outcomes) if cp is not None]
    scale, rmse = fit_scale(pairs)
    mae = sum(abs(probability(cp, scale) - out) for cp, out in pairs) / len(pairs)
    # how often the evaluation at least points the right way, ignoring near-draws
    decisive = [(cp, out) for cp, out in pairs if abs(out - 0.5) > 0.15]
    sign = sum(1 for cp, out in decisive if (cp > 0) == (out > 0.5)) / max(1, len(decisive))
    return (name, scale, rmse, mae, sign, len(pairs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("goldset")
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default="net/machete.nnue")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    with open(args.goldset) as handle:
        data = json.load(handle)
    positions = [p for p in data["positions"] if p["games"]]
    names = data["panel"]

    fitted = {}
    for kind in ("contested", "control", "all"):
        chosen = [p for p in positions if kind == "all" or p["kind"] == kind]
        outcomes = [p["measured_score"] for p in chosen]
        rows = []
        for name in names:
            scores = [p["verdicts"].get(name, {}).get("cp") for p in chosen]
            rows.append(measure(name, scores, outcomes))
        if os.path.exists(args.net) and os.path.exists(args.engine):
            ours = machete_evals(args.engine, args.net, [p["fen"] for p in chosen])
            rows.append(measure("machete", ours, outcomes))
        rows.sort(key=lambda r: r[2])
        report(rows, "{} ({})".format(kind, len(chosen)))
        if kind == "all":
            fitted = {r[0]: r[1] for r in rows}

    print()
    print("a coin flip on every position would score rmse 0.500 and mae 0.500;")
    print("predicting the set's own average scores about 0.30.")

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"scales": fitted}, handle, indent=1)
        print("\nfitted scales -> {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
