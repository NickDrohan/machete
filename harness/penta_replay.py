"""Replay finished matches' LLR under the trinomial and the pentanomial model.

    python harness/penta_replay.py MATCH.pgn NAME_A [--elo0 0 --elo1 10]

match.py (and arena) score an SPRT game by game: the trinomial model, which
takes every game as independent. But each opening is played twice with
colours reversed, and those two games are negatively correlated - whichever
side the opening favours changes hands - so a pair's average is less noisy
than two independent games. The pentanomial model (Fishtest's) scores pairs:
0, 0.5, 1, 1.5 or 2 points for A, and its LLR uses the variance of the pair
averages. This replays a finished match's games in order and prints, for both
models, how many games each took to cross a bound and which one.

The formula for both is the normal approximation match.py already uses,
n (s1 - s0) (2 mu - s0 - s1) / (2 var), with n and var per game for the
trinomial model and per pair for the pentanomial one.
"""
import argparse
import math
import sys

import chess.pgn


def score(elo):
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def llr(results, s0, s1):
    """results: a list of scores in [0, 1], one per trial; the normal-model LLR."""
    n = len(results)
    if n < 2:
        return 0.0
    mu = sum(results) / n
    var = sum((x - mu) ** 2 for x in results) / n
    if var <= 0:
        return 0.0
    return n * (s1 - s0) * (2 * mu - s0 - s1) / (2 * var)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("name_a")
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=10.0)
    args = parser.parse_args()
    s0, s1 = score(args.elo0), score(args.elo1)
    upper, lower = math.log(0.95 / 0.05), math.log(0.05 / 0.95)

    games = []
    with open(args.pgn, encoding="utf-8", errors="replace") as handle:
        while True:
            g = chess.pgn.read_game(handle)
            if g is None:
                break
            r = g.headers["Result"]
            a_white = args.name_a in g.headers["White"]
            pts = 0.5 if r == "1/2-1/2" else (1.0 if (r == "1-0") == a_white else 0.0)
            fen = " ".join(g.board().fen().split()[:4])
            games.append((fen, a_white, pts))
    # pair games of the same opening with A on opposite sides, in order
    open_pairs, pairs, per_game = {}, [], []
    tri_cross = penta_cross = None
    for k, (fen, a_white, pts) in enumerate(games, 1):
        per_game.append(pts)
        waiting = open_pairs.setdefault(fen, {True: [], False: []})
        other = waiting[not a_white]
        if other:
            pairs.append((other.pop(0) + pts) / 2.0)
        else:
            waiting[a_white].append(pts)
        if k >= 40 and tri_cross is None:
            t = llr(per_game, s0, s1)
            if t >= upper or t <= lower:
                tri_cross = (k, "H1" if t >= upper else "H0", t)
        if len(pairs) >= 20 and penta_cross is None:
            p = llr(pairs, s0, s1)
            if p >= upper or p <= lower:
                penta_cross = (k, "H1" if p >= upper else "H0", p)
    t_final, p_final = llr(per_game, s0, s1), llr(pairs, s0, s1)
    var_game = sum((x - sum(per_game) / len(per_game)) ** 2 for x in per_game) / len(per_game)
    mp = sum(pairs) / len(pairs)
    var_pair = sum((x - mp) ** 2 for x in pairs) / len(pairs)
    print("%s: %d games, %d complete pairs, score %.3f" % (args.pgn.split("/")[-1], len(games), len(pairs), sum(per_game) / len(per_game)))
    print("  per-game variance %.4f; pair-average variance %.4f (independent games would give %.4f)"
          % (var_game, var_pair, var_game / 2))
    print("  final LLR: trinomial %+.2f, pentanomial %+.2f" % (t_final, p_final))
    print("  crossed a bound: trinomial %s; pentanomial %s" % (
        "at game %d (%s)" % tri_cross[:2] if tri_cross else "never",
        "at game %d (%s)" % penta_cross[:2] if penta_cross else "never"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
