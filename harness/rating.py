"""Ratings on an external scale, from games against engines whose ratings are
published.

    python harness/rating.py GAMES.pgn [more.pgn ...] \
        --anchor "Rybka 2.3.2a=2996" --anchor "Spike 1.4=2792" ... \
        [--bootstrap 2000] [--check-anchors]

Every engine named as an anchor keeps its published rating. Every other
engine in the games gets the rating that makes its expected score equal its
actual score against everyone it played - the maximum-likelihood fit of the
Elo model with a draw counted as half a point, solved jointly when unrated
engines also played each other. This is the same estimator Ordo and BayesElo
reduce to with the anchors fixed and no draw model, and it is not the
harness's own head-to-head formula: the scale comes from the anchors'
published ratings, not from any machete version.

The 95% interval is a bootstrap over games, so it reflects both how many
games there are and how much each anchor's games agree with the others'.
--check-anchors also fits each anchor as if it were unrated, against the
rest, which says whether the published ratings hold on this machine and
clock; a wide disagreement there is the honest limit of the calibration.
"""

import argparse
import collections
import math
import random
import sys

import chess.pgn


# ratings are kept within this range: an engine that lost every game in a
# bootstrap resample would otherwise run off to minus infinity
LOWEST, HIGHEST = 1000.0, 4500.0


def expected(ra, rb):
    return 1.0 / (1.0 + 10.0 ** (max(-3000.0, min(3000.0, rb - ra)) / 400.0))


def read_games(paths):
    """(white, black, white's score) per game, from the PGN headers."""
    games = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            while True:
                headers = chess.pgn.read_headers(handle)
                if headers is None:
                    break
                result = headers.get("Result", "*")
                score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}.get(result)
                if score is None:
                    continue
                games.append((headers.get("White", "?"), headers.get("Black", "?"), score))
    return games


def fit(games, anchors, iterations=200):
    """Ratings for every engine: anchors as given, the rest by maximum
    likelihood. Each unrated engine's rating moves until its expected score
    matches its actual score; the unrated engines' games with each other are
    part of that, so the fit is iterated to a joint solution."""
    played = collections.defaultdict(list)
    for white, black, score in games:
        played[white].append((black, score))
        played[black].append((white, 1.0 - score))
    ratings = dict(anchors)
    unrated = [name for name in played if name not in anchors]
    for name in unrated:
        ratings[name] = 2500.0
    for _ in range(iterations):
        largest = 0.0
        for name in unrated:
            actual = sum(s for _, s in played[name])
            # Newton's step on the log-likelihood in this one rating
            for _ in range(20):
                exp = [expected(ratings[name], ratings[opp]) for opp, _ in played[name]]
                gradient = actual - sum(exp)
                curvature = sum(e * (1.0 - e) for e in exp) * math.log(10) / 400.0
                if curvature <= 0:
                    break
                step = gradient / curvature
                if step > 200: step = 200.0
                if step < -200: step = -200.0
                ratings[name] = max(LOWEST, min(HIGHEST, ratings[name] + step))
                if abs(step) < 0.01 or ratings[name] in (LOWEST, HIGHEST):
                    break
            largest = max(largest, abs(step))
        if largest < 0.01:
            break
    return ratings, unrated, played


def summarise(games, anchors, bootstrap, seed):
    ratings, unrated, played = fit(games, anchors)
    rng = random.Random(seed)
    samples = collections.defaultdict(list)
    for _ in range(bootstrap):
        resample = [games[rng.randrange(len(games))] for _ in games]
        r, _, _ = fit(resample, anchors, iterations=60)
        for name in unrated:
            if name in r:
                samples[name].append(r[name])
    rows = []
    for name in sorted(unrated, key=lambda n: -ratings[n]):
        s = sorted(samples[name])
        lo = s[int(0.025 * len(s))] if s else float("nan")
        hi = s[int(0.975 * len(s)) - 1] if s else float("nan")
        n = len(played[name])
        pts = sum(sc for _, sc in played[name])
        rows.append((name, ratings[name], lo, hi, n, pts))
    return ratings, rows, played


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pgn", nargs="+")
    parser.add_argument("--anchor", action="append", default=[], help="NAME=RATING, the name as the PGN has it")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--check-anchors", action="store_true",
                        help="also fit each anchor as if unrated, against the others")
    args = parser.parse_args()
    anchors = {}
    for item in args.anchor:
        name, rating = item.rsplit("=", 1)
        anchors[name] = float(rating)
    games = read_games(args.pgn)
    if not games:
        print("no decided games in", args.pgn)
        return 1
    names = set()
    for w, b, _ in games:
        names.add(w); names.add(b)
    missing = [n for n in anchors if n not in names]
    if missing:
        print("anchors with no games:", ", ".join(missing))
    print("{} games, {} engines, {} anchors".format(len(games), len(names), len(anchors) - len(missing)))
    ratings, rows, played = summarise(games, anchors, args.bootstrap, args.seed)
    print("\n{:<22} {:>7} {:>16} {:>6} {:>7}".format("engine", "rating", "95% interval", "games", "score"))
    for name, r, lo, hi, n, pts in rows:
        print("{:<22} {:>7.0f} {:>7.0f} - {:<7.0f} {:>6} {:>6.1%}".format(name, r, lo, hi, n, pts / n))
    print("\nper opponent:")
    for name, r, lo, hi, n, pts in rows:
        by = collections.defaultdict(lambda: [0.0, 0])
        for opp, sc in played[name]:
            by[opp][0] += sc; by[opp][1] += 1
        for opp in sorted(by, key=lambda o: -ratings.get(o, 0)):
            p, k = by[opp]
            exp = expected(r, ratings[opp])
            print("  {:<20} vs {:<20} {:>3} games  score {:>5.1%}  expected {:>5.1%}  diff {:+.1%}".format(
                name, opp, k, p / k, exp, p / k - exp))
    if args.check_anchors:
        print("\nanchors refitted one at a time against the rest (list rating -> fitted):")
        for name in sorted(anchors, key=lambda n: -anchors[n]):
            if name not in names:
                continue
            others = {k: v for k, v in anchors.items() if k != name}
            r, _, _ = fit(games, others)
            n = len(played[name])
            print("  {:<22} {:>5.0f} -> {:>5.0f}  ({:+.0f}, {} games)".format(name, anchors[name], r[name], r[name] - anchors[name], n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
