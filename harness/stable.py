"""A round robin of the stable's strong engines, kept as data.

    python harness/stable.py --tc 180+2 --pairs 4 --concurrency 10

machete learns from these engines and is measured against them, so their games
are worth having for their own sake: every move comes with what the engine
playing it thought, at its own depth, on a real clock. harness/shadow.py then
puts machete's view of each position beside theirs.

Each pairing plays `--pairs` openings from the balanced book, each with colours
reversed. Openings are not shared between pairings: pairing k takes the next
`--pairs` positions, so the round robin covers as many different positions as
it has games, and the ratings come from the Bradley-Terry fit rather than from
common openings. Every engine is pinned to one thread, a fixed hash and no
book of its own, and started fresh for every game.

machete watches every game: each worker keeps one machete that, between moves
and off the players' clocks, gives its quick eval and a depth-10 search of
every position. The live wall draws both players' own evals and machete's as a
chart under each board, and the PGN keeps machete's view as `[%machete quick,
searched, move, depth]` beside each move's `[%eval]`.
"""

import argparse
import itertools
import json
import os
import sys
import threading
import traceback

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import engine as engines
import match
import panel
import wall
from tournament import fit_ratings

MATE_CP = 3000
FIELD = "Stockfish,Berserk,Alexandria,Obsidian,Caissa,PlentyChess,Dragon,Reckless,Koivisto,BlackMarlin"


def open_observer(args):
    """machete, watching: it plays no move, only says what it thinks."""
    observer = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.machete))
    observer.configure({"EvalFile": os.path.abspath(args.net)})
    engines.pin(observer, 64)
    return observer


def observe(observer, board, depth, session):
    """machete's snap judgement (depth 1) and its searched choice, from White's side.

    Depth, not nodes: machete does not implement `go nodes`, and would search
    until stopped.
    """
    quick = observer.analyse(board, chess.engine.Limit(depth=1), game=session)
    deep = observer.analyse(board, chess.engine.Limit(depth=depth), game=session)
    return {"quick": quick["score"].white().score(mate_score=MATE_CP),
            "search": deep["score"].white().score(mate_score=MATE_CP),
            "move": deep["pv"][0].uci(), "depth": deep.get("depth")}


def view_tag(view):
    return "[%machete {},{},{},{}]".format(view["quick"], view["search"], view["move"], view["depth"])


def chart_lines(white_name, black_name, start, said, views):
    """The live chart: each player's own eval on its own moves, and machete's."""
    white_points, black_points = [], []
    for k, verdict in enumerate(said):
        if verdict is None:
            continue
        cp = verdict["cp"] if verdict["mate"] is None else (MATE_CP if verdict["mate"] > 0 else -MATE_CP)
        white_to_move = (start.turn == chess.WHITE) == (k % 2 == 0)
        (white_points if white_to_move else black_points).append([k, cp])
    return [{"name": white_name, "points": white_points},
            {"name": black_name, "points": black_points},
            {"name": "machete", "points": [[k, v["search"]] for k, v in enumerate(views)]}]


class Standings(object):
    def __init__(self, names):
        self.lock = threading.Lock()
        self.names = names
        n = len(names)
        self.points = [[0.0] * n for _ in range(n)]
        self.counts = [[0] * n for _ in range(n)]
        self.results = []

    def add(self, white, black, outcome, how):
        i, j = self.names.index(white), self.names.index(black)
        point = {"1-0": 1.0, "0-1": 0.0}.get(outcome, 0.5)
        with self.lock:
            self.points[i][j] += point
            self.points[j][i] += 1.0 - point
            self.counts[i][j] += 1
            self.counts[j][i] += 1
            self.results.append({"white": white, "black": black, "result": outcome, "how": how})

    def table(self):
        with self.lock:
            scores = [sum(row) for row in self.points]
            games = [sum(row) for row in self.counts]
            ratings = fit_ratings(self.names, scores, self.counts) if sum(games) else [0.0] * len(self.names)
            rows = sorted(zip(self.names, games, scores, ratings), key=lambda r: -r[3])
            return [[name, played, "{:g}".format(score),
                     "{:.1%}".format(score / played) if played else "-", "{:+.0f}".format(rating)]
                    for name, played, score, rating in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engines", default=FIELD, help="panel names, comma separated")
    parser.add_argument("--tc", default="180+2", help="BASE+INCREMENT in seconds")
    parser.add_argument("--pairs", type=int, default=4, help="openings per pairing, each played both ways")
    parser.add_argument("--book", default=os.path.join(HERE, "books", "balanced_200.epd"))
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--hash", type=int, default=128)
    parser.add_argument("--pgn", default="data/games_stable.pgn")
    parser.add_argument("--out", default="data/stable.json")
    parser.add_argument("--watch", type=int, default=8780)
    parser.add_argument("--machete", default=engines.MACHETE, help="the observer's binary")
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--observe-depth", type=int, default=10)
    args = parser.parse_args()

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    book = match.load_book(args.book)
    base, increment = match.parse_tc(args.tc)
    clock = (base, increment, 100)
    pairings = list(itertools.combinations(names, 2))
    # opening j of every pairing before opening j+1 of any, so every engine
    # is playing from the start rather than one pairing at a time
    tasks = []
    for j in range(args.pairs):
        for k, (a, b) in enumerate(pairings):
            opening = book[(k * args.pairs + j) % len(book)]
            tasks.append((a, b, opening))
            tasks.append((b, a, opening))

    # resume: a game already in the PGN - same players, same opening - is
    # counted, not played again
    standings = Standings(names)
    if os.path.exists(args.pgn):
        played = set()
        with open(args.pgn, encoding="utf-8", errors="replace") as handle:
            while True:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                white, black = game.headers["White"], game.headers["Black"]
                if white in names and black in names:
                    played.add((white, black, game.headers.get("FEN", chess.STARTING_FEN)))
                    standings.add(white, black, game.headers["Result"],
                                  game.headers.get("Termination", ""))
        tasks = [t for t in tasks if (t[0], t[1], t[2]) not in played]
        print("resuming: {} games already in {}".format(len(played), args.pgn))
    total = len(tasks) + len(standings.results)
    live = wall.Live(args.concurrency, title="stable round robin",
                     columns=("engine", "games", "points", "score", "Bradley-Terry"))
    if args.watch:
        wall.start(live, args.watch, "the round robin")
    live.say("{} engines, {} games at {}".format(len(names), total, args.tc),
             "{} of {} played".format(len(standings.results), total))
    live.finished = standings.table()
    print("{} engines, {} pairings, {} games at {}, {} at a time".format(
        len(names), len(pairings), total, args.tc, args.concurrency))
    sys.stdout.flush()

    index = [0]
    lock = threading.Lock()
    errors = []

    def worker(slot):
        observer = None
        try:
            observer = open_observer(args)
        except Exception as problem:
            errors.append("observer: {}: {}".format(type(problem).__name__, problem))
            return
        while True:
            with lock:
                if index[0] >= len(tasks):
                    engines.shutdown(observer)
                    return
                white_name, black_name, opening = tasks[index[0]]
                index[0] += 1
            white = black = None
            try:
                white = panel.open_engine(white_name, args.hash)
                black = panel.open_engine(black_name, args.hash)
                for side in (white, black):
                    engines.pin(side, args.hash)

                said = []
                views = []
                session = object()
                start = match.opening_board(opening)

                def report(board, result, _w=white_name, _b=black_name):
                    # machete's view of every position the players move from;
                    # outside the players' clocks, so it costs them nothing
                    if result is None and not board.is_game_over():
                        views.append(observe(observer, board, args.observe_depth, session))
                    live.set_board(slot, board, _w, _b, result,
                                   lines=chart_lines(_w, _b, start, said, views))

                outcome, final, how, clocks = match.play(
                    white, black, opening, None, 0, report, None, clock, record=said)
                standings.add(white_name, black_name, outcome, how)
                wall.save_game(args.pgn, final, white_name, black_name, "stable round robin",
                               outcome, headers={"TimeControl": args.tc, "Termination": how},
                               clocks=clocks, evals=said, notes=[view_tag(v) for v in views[:len(said)]])
                with lock:
                    done = len(standings.results)
                live.finished = standings.table()
                live.say("{} engines, {} games at {}".format(len(names), total, args.tc),
                         "{} of {} played".format(done, total))
                print("{:>4}/{} {:<12} {:<12} {:<7} {}".format(
                    done, total, white_name, black_name, outcome, how))
                sys.stdout.flush()
            except Exception as problem:
                errors.append("{} v {}: {}: {}".format(white_name, black_name,
                                                        type(problem).__name__, problem))
                traceback.print_exc()
            finally:
                engines.shutdown(white)
                engines.shutdown(black)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print("\n{:<12} {:>5} {:>7} {:>7} {:>14}".format("engine", "games", "points", "score", "Bradley-Terry"))
    for row in standings.table():
        print("{:<12} {:>5} {:>7} {:>7} {:>14}".format(*row))
    for problem in errors:
        print("error:", problem)
    with open(args.out, "w") as handle:
        json.dump({"engines": names, "tc": args.tc, "results": standings.results,
                   "errors": errors}, handle, indent=1)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
