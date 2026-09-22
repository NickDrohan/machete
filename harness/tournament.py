"""Race networks against each other, all-play-all, and rank them.

    python harness/tournament.py ENGINE --nets E:/machete/nets --games 150 --movetime 200

Built for one question: which slice of our training data makes the strongest
engine? `harness/nnue/subset.py` cuts equal-sized slices along the axes we
suspect matter, one network is trained on each, and this plays them all against
each other. A round robin is the efficient shape here - every game informs two
ratings at once, where a gauntlet against a fixed anchor spends half its games
re-measuring the anchor.

Two things are held fixed so that the data is the only variable:

  * **The same openings for everyone.** Opening `n` is opening `n` in every
    pairing, played twice with colours reversed. Two networks that never meet
    still face the same positions, so the ratings are comparable through
    opponents they have in common rather than only through the games they
    played.
  * **Fresh engine processes per block.** The networks differ only in the
    `EvalFile` option, which the engine will reload on request - but the
    transposition table would then still hold scores from the previous
    network. Each block of games starts new processes instead, which is also
    exactly how every Elo figure recorded so far was measured.

Ratings come from a Bradley-Terry fit: the rating vector under which each
network's expected score equals the score it actually got, anchored so the
field averages zero. The cross-table is printed too, because a fit is a summary
and a summary can hide a network that beats one opponent and loses to the rest.
"""

import argparse
import itertools
import json
import math
import os
import random
import sys
import threading
import time

import chess
import chess.engine

import wall
import match


# No rating outside this range is meaningful here, and a network that has not
# yet lost a game has no finite rating at all - the fit would chase it upwards
# for ever and overflow. The bracket is what stops it; the margin then comes
# back infinite, which is the honest answer until a loss arrives.
RATING_LIMIT = 2000.0


def expected(rating_a, rating_b):
    gap = rating_b - rating_a
    if gap > 4000.0:
        return 0.0
    if gap < -4000.0:
        return 1.0
    return 1.0 / (1.0 + 10.0 ** (gap / 400.0))


def fit_ratings(names, scores, counts, rounds=500):
    """Ratings whose expected scores match the observed ones (Bradley-Terry)."""
    ratings = [0.0] * len(names)
    for _ in range(rounds):
        moved = 0.0
        for i in range(len(names)):
            if sum(counts[i]) == 0:
                continue
            low, high = -RATING_LIMIT, RATING_LIMIT
            for _ in range(60):
                middle = (low + high) / 2.0
                predicted = sum(counts[i][j] * expected(middle, ratings[j])
                                for j in range(len(names)) if j != i)
                if predicted < scores[i]:
                    low = middle
                else:
                    high = middle
            new = (low + high) / 2.0
            moved = max(moved, abs(new - ratings[i]))
            ratings[i] = new
        centre = sum(ratings) / len(ratings)
        ratings = [r - centre for r in ratings]
        if moved < 0.01:
            break
    return ratings


def margins(names, ratings, counts, wins, draws, losses):
    """A 95% half-width per rating, from the score's variance and the slope.

    The slope is how much a rating has to move to shift the expected score by
    one point; dividing the total score's standard error by it converts one
    into the other. Draws count as half a point and carry a quarter of a win's
    variance, which is why a drawish pairing resolves a rating faster than its
    game count alone suggests.
    """
    out = []
    for i in range(len(names)):
        played = wins[i] + draws[i] + losses[i]
        if played < 2:
            out.append(float("inf"))
            continue
        if abs(ratings[i]) > RATING_LIMIT - 1.0:
            out.append(float("inf"))       # no losses yet, or no wins: unbounded
            continue
        mean = (wins[i] + 0.5 * draws[i]) / played
        second = (wins[i] + 0.25 * draws[i]) / played
        variance = max(second - mean * mean, 1e-9)
        standard_error = math.sqrt(variance * played)        # of the total score
        slope = sum(counts[i][j] * expected(ratings[i], ratings[j])
                    * (1.0 - expected(ratings[i], ratings[j]))
                    for j in range(len(names)) if j != i) * math.log(10.0) / 400.0
        out.append(1.96 * standard_error / slope if slope > 1e-9 else float("inf"))
    return out


class Table(object):
    """Every pairing's running score, and the standings drawn from them."""

    def __init__(self, names, live=None):
        self.names = names
        self.lock = threading.Lock()
        self.wins = [[0] * len(names) for _ in names]      # wins[i][j]: i beat j
        self.draws = [[0] * len(names) for _ in names]
        self.played = 0
        self.live = live

    def record(self, i, j, outcome, i_is_white):
        with self.lock:
            self.played += 1
            if outcome == "1/2-1/2":
                self.draws[i][j] += 1
                self.draws[j][i] += 1
            elif (outcome == "1-0") == i_is_white:
                self.wins[i][j] += 1
            else:
                self.wins[j][i] += 1

    def totals(self):
        n = len(self.names)
        with self.lock:
            counts = [[0 if i == j else
                       self.wins[i][j] + self.wins[j][i] + self.draws[i][j]
                       for j in range(n)] for i in range(n)]
            wins = [sum(self.wins[i]) for i in range(n)]
            draws = [sum(self.draws[i]) for i in range(n)]
            losses = [sum(self.wins[j][i] for j in range(n)) for i in range(n)]
        scores = [wins[i] + 0.5 * draws[i] for i in range(n)]
        return counts, wins, draws, losses, scores

    def standings(self):
        counts, wins, draws, losses, scores = self.totals()
        ratings = fit_ratings(self.names, scores, counts)
        bars = margins(self.names, ratings, counts, wins, draws, losses)
        rows = sorted(zip(self.names, ratings, bars, wins, draws, losses),
                      key=lambda row: -row[1])
        return rows, counts

    def refresh(self):
        if self.live is None:
            return
        rows, _ = self.standings()
        table = []
        for name, rating, bar, w, d, l in rows:
            games = w + d + l
            table.append([name, games, w, d, l,
                          "{:.3f}".format((w + 0.5 * d) / games) if games else "-",
                          "{:+.0f} +/- {:.0f}".format(rating, bar)
                          if bar != float("inf") else "{:+.0f}".format(rating)])
        with self.live.lock:
            self.live.finished = table


def play_block(args, paths, table, i, j, first_pair, pairs, live, slot):
    """`pairs` opening pairs of games between networks i and j."""
    a = b = None
    try:
        a = match.open_engine(args.engine, ["EvalFile=" + paths[i]])
        b = match.open_engine(args.engine, ["EvalFile=" + paths[j]])
    except Exception as problem:
        return "could not start engines: {}".format(problem)
    name_i, name_j = table.names[i], table.names[j]
    try:
        for index in range(first_pair, first_pair + pairs):
            # seeded by opening number alone: opening n is the same position in
            # every pairing, so networks that never meet still face it
            opening = match.random_opening(
                random.Random(args.seed * 1000003 + index), args.opening_plies)
            for i_is_white in (True, False):
                white, black = (a, b) if i_is_white else (b, a)
                white_name = name_i if i_is_white else name_j
                black_name = name_j if i_is_white else name_i
                report = None
                if live is not None:
                    def report(board, result, _s=slot, _w=white_name, _b=black_name):
                        live.set_board(_s, board, _w, _b, result)
                outcome, final = match.play(white, black, opening,
                                            match.limit_from(args), args.max_plies,
                                            report)
                wall.save_game(args.pgn, final, white_name, black_name,
                               "subset tournament", outcome)
                table.record(i, j, outcome, i_is_white)
                table.refresh()
    except Exception as problem:
        return "{} vs {}: {}".format(name_i, name_j, problem)
    finally:
        for engine in (a, b):
            if engine is None:
                continue
            try:
                engine.quit()
            except Exception:
                pass
    return None


def collect(args):
    """The networks to race, as (name, absolute path) pairs."""
    entries = []
    for setting in args.net:
        name, _, path = setting.partition("=")
        entries.append((name, os.path.abspath(path)))
    if not entries and args.nets:
        for filename in sorted(os.listdir(args.nets)):
            if filename.endswith(".nnue"):
                entries.append((os.path.splitext(filename)[0],
                                os.path.abspath(os.path.join(args.nets, filename))))
    if len(entries) < 2:
        raise SystemExit("need at least two networks")
    for _, path in entries:
        if not os.path.exists(path):
            raise SystemExit("no such network: {}".format(path))
    return entries


def report(table, names, per_pairing):
    rows, counts = table.standings()
    print("\n{:<10}{:>7}{:>6}{:>6}{:>6}{:>9}{:>16}".format(
        "network", "games", "W", "D", "L", "score", "Elo"))
    for name, rating, bar, w, d, l in rows:
        games = w + d + l
        print("{:<10}{:>7}{:>6}{:>6}{:>6}{:>9.3f}{:>11}{:+.0f} +/- {:.0f}".format(
            name, games, w, d, l, (w + 0.5 * d) / max(1, games), "", rating, bar))

    print("\ncross-table, row's score against column, out of {} games".format(
        per_pairing * 2))
    print("{:<10}".format("") + "".join("{:>10}".format(n[:9]) for n in names))
    for i, name in enumerate(names):
        line = "{:<10}".format(name)
        for j in range(len(names)):
            if i == j:
                line += "{:>10}".format("-")
            else:
                games = counts[i][j]
                point = table.wins[i][j] + 0.5 * table.draws[i][j]
                line += "{:>10}".format("{:.3f}".format(point / games) if games else "-")
        print(line)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--nets", default="", help="directory of .nnue files")
    parser.add_argument("--net", action="append", default=[],
                        help="name=path, repeatable; overrides --nets")
    parser.add_argument("--games", type=int, default=150, help="per pairing")
    parser.add_argument("--block", type=int, default=10, help="game pairs per task")
    parser.add_argument("--movetime", type=int, default=200)
    parser.add_argument("--depth", type=int, default=0)
    parser.add_argument("--opening-plies", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=11)
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--watch", type=int, default=8770)
    parser.add_argument("--pgn", default="data/games_tournament.pgn")
    parser.add_argument("--out", default="data/tournament.json")
    args = parser.parse_args()

    args.engine = os.path.abspath(args.engine)
    entries = collect(args)
    names = [name for name, _ in entries]
    paths = [path for _, path in entries]
    pairings = list(itertools.combinations(range(len(names)), 2))
    per_pairing = max(1, args.games // 2)              # opening pairs
    total = len(pairings) * per_pairing * 2
    print("{} networks, {} pairings, {} games at {}".format(
        len(names), len(pairings), total,
        "depth {}".format(args.depth) if args.depth
        else "{} ms a move".format(args.movetime)))

    live = None
    if args.watch:
        live = wall.Live(max(1, args.concurrency), title="machete subset tournament",
                         columns=("network", "games", "W", "D", "L", "score", "Elo"))
        live.say("all-play-all on equal slices of the corpus",
                 "{} games".format(total))
        wall.start(live, args.watch, "the tournament")

    table = Table(names, live)
    tasks = []
    for i, j in pairings:
        for start in range(0, per_pairing, args.block):
            tasks.append((i, j, start, min(args.block, per_pairing - start)))
    random.Random(args.seed).shuffle(tasks)            # spread pairings over time
    cursor = {"next": 0, "lock": threading.Lock()}
    failures = []
    started = time.time()

    def run(slot):
        while True:
            with cursor["lock"]:
                if cursor["next"] >= len(tasks) or failures:
                    return
                i, j, first, pairs = tasks[cursor["next"]]
                cursor["next"] += 1
                done = cursor["next"]
            problem = play_block(args, paths, table, i, j, first, pairs, live, slot)
            if problem:
                failures.append(problem)
                return
            elapsed = time.time() - started
            progress = "{}/{} games, {:.1f}h left".format(
                table.played, total, elapsed / done * (len(tasks) - done) / 3600.0)
            if live is not None:
                live.say("all-play-all on equal slices of the corpus", progress)
            print("  " + progress)
            sys.stdout.flush()

    threads = [threading.Thread(target=run, args=(slot,))
               for slot in range(max(1, args.concurrency))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        print("tournament failed: {}".format(failures[0]))
        return 1

    rows = report(table, names, per_pairing)
    with open(args.out, "w") as handle:
        json.dump({"names": names, "paths": paths,
                   "wins": table.wins, "draws": table.draws,
                   "ratings": dict((row[0], row[1]) for row in rows),
                   "margins": dict((row[0], row[2]) for row in rows),
                   "movetime": args.movetime, "games": total}, handle, indent=1)
    print("\n{:.1f} hours, written to {}".format(
        (time.time() - started) / 3600.0, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
