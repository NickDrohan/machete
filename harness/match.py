"""Play engine-vs-engine matches through python-chess and report the result.

    python harness/match.py ENGINE_A [ENGINE_B] --games 20 --movetime 100
    python harness/match.py NEW OLD --sprt 0 10 --games 2000

With one engine it plays itself, which is the protocol soak test: any illegal
move, crash, hang or protocol error fails the run. With two it measures the
difference between them and prints an Elo estimate with an error bar.

Colours alternate, and each opening is played twice, once from each side, so a
lucky opening cannot decide the match.

`--concurrency N` plays N games at once, which is the difference between a
decisive match and an overnight one: 700 games at 300 ms a move is nine hours
in one process and under an hour in twelve. Each worker owns its own pair of
engines, and each opening's seed comes from its pair number rather than from a
shared generator, so the openings played are the same whatever order the
workers happen to finish in.

`--sprt elo0 elo1` runs a sequential test instead of a fixed number of games:
after every game it asks whether the evidence already favours "the change is
worth less than elo0" or "more than elo1", and stops as soon as one of them is
established. A fixed 300-game match resolves about +/-40 Elo, which cannot
settle a 25 Elo change; the sequential test spends games only until the answer
is clear, and reports which hypothesis won.
"""

import argparse
import math
import os
import random
import sys
import threading
import time

import chess
import chess.engine

import wall
import adjudicate
import engine as engines


def random_opening(rng, plies):
    """A few random moves from the start, never ones that finish the game.

    Four random plies can be 1. f3 e5 2. g4 Qh4#. That happened, twice, and
    the rating ladder scored both as wins for an engine that had not yet made
    a move. A walk that ends the game is thrown away and drawn again.
    """
    for _ in range(100):
        board = chess.Board()
        for _ in range(plies):
            moves = list(board.legal_moves)
            if not moves:
                break
            board.push(rng.choice(moves))
        if not board.is_game_over(claim_draw=True):
            return board.move_stack[:]
    raise RuntimeError("no playable random opening in 100 tries")


def load_book(path):
    """Starting positions, one FEN or EPD per line."""
    positions = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                chess.Board(line)
            except ValueError:
                line = chess.Board.from_epd(line)[0].fen()
            positions.append(line)
    if not positions:
        raise SystemExit("no positions in {}".format(path))
    return positions


def opening_board(opening):
    """The starting board for an opening given as moves or as a FEN."""
    if isinstance(opening, str):
        return chess.Board(opening)
    board = chess.Board()
    for move in opening:
        board.push(move)
    return board


def parse_tc(text):
    """'300+3' -> (300000, 3000): base and increment in milliseconds."""
    base, _, increment = text.partition("+")
    return int(float(base) * 1000), int(float(increment or 0) * 1000)


def play(white, black, opening, limit, max_plies, report=None, judge=None, clock=None):
    """Play one game. Returns (result, final board, how it ended, clocks).

    `clock` is (base_ms, increment_ms, margin_ms) for a real clock, or None to
    give each move `limit`. On a clock the harness keeps time the way a GUI
    does: a move's wall time is charged to the side that made it, then the
    increment is added, and a side whose clock falls more than `margin_ms`
    below zero loses on time - unless the opponent has too little material to
    mate, which the rules score as a draw. The margin absorbs the pipe and
    Python overhead, which is charged to both sides alike.

    `max_plies` of 0 means no cap: the game ends only by the rules.

    Each game is its own `game` to python-chess, so every engine is sent
    `ucinewgame` and starts with an empty hash, as it would in a GUI.
    """
    board = opening_board(opening)
    game_id = object()
    if judge:
        judge.reset()
    if report:
        report(board, None)
    remaining = None
    if clock:
        remaining = {chess.WHITE: float(clock[0]), chess.BLACK: float(clock[0])}
    clocks = []

    def finish(outcome, how):
        if report:
            report(board, outcome)
        return outcome, board, how, clocks

    while not board.is_game_over(claim_draw=True):
        if max_plies and board.ply() >= max_plies:
            return finish("1/2-1/2", "ply cap")
        side = board.turn
        engine = white if side == chess.WHITE else black
        if clock:
            increment = clock[1] / 1000.0
            move_limit = chess.engine.Limit(
                white_clock=max(0.0, remaining[chess.WHITE]) / 1000.0,
                black_clock=max(0.0, remaining[chess.BLACK]) / 1000.0,
                white_inc=increment, black_inc=increment)
        else:
            move_limit = limit
        want_score = judge is not None and judge.enabled
        started = time.monotonic()
        if want_score:
            result = engine.play(board, move_limit, info=chess.engine.INFO_SCORE, game=game_id)
        else:
            result = engine.play(board, move_limit, game=game_id)
        spent = (time.monotonic() - started) * 1000.0
        if clock:
            remaining[side] -= spent
            if remaining[side] < -clock[2]:
                if board.has_insufficient_material(not side):
                    return finish("1/2-1/2", "time forfeit, opponent cannot mate")
                return finish("0-1" if side == chess.WHITE else "1-0", "time forfeit")
            remaining[side] = max(0.0, remaining[side]) + clock[1]
        if want_score:
            verdict = judge.observe(board, side == chess.WHITE,
                                    adjudicate.score_of(result.info, side == chess.WHITE))
            if verdict is not None:
                return finish(verdict, "adjudication")
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError("illegal move {} in {}".format(result.move, board.fen()))
        board.push(result.move)
        clocks.append(remaining[side] if clock else None)
        if report:
            report(board, None)
    return finish(board.result(claim_draw=True), "normal")


def elo_to_score(elo):
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def log_likelihood_ratio(wins, draws, losses, elo0, elo1):
    """LLR for H1 (elo >= elo1) against H0 (elo <= elo0), trinomial model.

    The usual Fishtest approximation: the score's per-game variance is taken
    from the observed win/draw/loss split, and the ratio is the normal-model
    LLR at the two hypothesised scores.
    """
    games = wins + draws + losses
    if games == 0:
        return 0.0
    if wins == 0 or losses == 0:
        # with no loss (or no win) yet the variance estimate collapses and the
        # ratio explodes: 1-0-0 would "prove" anything. Report no evidence.
        return 0.0
    p_w, p_d, p_l = wins / games, draws / games, losses / games
    score = p_w + p_d / 2.0
    variance = (p_w * (1.0 - score) ** 2 + p_d * (0.5 - score) ** 2
                + p_l * (0.0 - score) ** 2)
    if variance <= 0:
        return 0.0
    score0, score1 = elo_to_score(elo0), elo_to_score(elo1)
    return (games * (score1 - score0) * (2.0 * score - score0 - score1)
            / (2.0 * variance))


def elo_difference(score, games):
    """Elo difference and a 95% interval, from a match score in [0, 1]."""
    if score <= 0.0:
        return float("-inf"), 0.0
    if score >= 1.0:
        return float("inf"), 0.0
    elo = -400.0 * math.log10(1.0 / score - 1.0)
    # standard error of the mean score, propagated through the Elo curve
    sigma = math.sqrt(score * (1.0 - score) / games)
    lo = max(1e-6, score - 1.96 * sigma)
    hi = min(1 - 1e-6, score + 1.96 * sigma)
    span = (-400.0 * math.log10(1.0 / hi - 1.0)) - (-400.0 * math.log10(1.0 / lo - 1.0))
    return elo, span / 2.0


class Tally(object):
    """The running score, and the sequential test's verdict once it has one."""

    def __init__(self, args, lower, upper, live=None):
        self.lock = threading.Lock()
        self.wins = self.draws = self.losses = 0
        self.verdict = None
        self.args = args
        self.lower = lower
        self.upper = upper
        self.live = live

    def publish(self, played, llr):
        """Put the running score on the wall, from A's side and from B's.

        A match that shows eleven boards and an empty table makes the watcher
        wait until the process exits to learn anything. Both rows are shown
        because "who is winning" is the question, and reading it off one row's
        losses column is work the page can do instead.
        """
        if self.live is None:
            return
        rows = []
        for name, w, d, l in ((self.args.label_a, self.wins, self.draws, self.losses),
                              (self.args.label_b, self.losses, self.draws, self.wins)):
            score = (w + 0.5 * d) / played
            elo, margin = elo_difference(score, played)
            if elo == float("inf"):
                shown = "won every game"
            elif elo == float("-inf"):
                shown = "lost every game"
            else:
                shown = "{:+.0f} +/- {:.0f}".format(elo, margin)
            rows.append([name, played, w, d, l, "{:.3f}".format(score), shown])
        progress = "{} of {} games".format(played, self.args.games)
        if self.args.sprt:
            progress += "   LLR {:+.2f}  (H0 {:+.2f} .. H1 {:+.2f})".format(
                llr, self.lower, self.upper)
        if self.verdict:
            progress += "   " + self.verdict
        with self.live.lock:
            self.live.finished = rows
        self.live.say("{} vs {}".format(self.args.label_a, self.args.label_b), progress)

    def record(self, outcome, a_is_white):
        """Add one game and re-run the sequential test. True means keep going."""
        with self.lock:
            if outcome == "1/2-1/2":
                self.draws += 1
            elif (outcome == "1-0") == a_is_white:
                self.wins += 1
            else:
                self.losses += 1
            played = self.wins + self.draws + self.losses
            llr = 0.0
            if self.args.sprt:
                llr = log_likelihood_ratio(self.wins, self.draws, self.losses,
                                           self.args.sprt[0], self.args.sprt[1])
                if played < self.args.sprt_min_games:
                    llr = 0.0
                if played % 20 == 0:
                    print("  {} games, LLR {:+.2f} (bounds {:+.2f} .. {:+.2f})".format(
                        played, llr, self.lower, self.upper))
                    sys.stdout.flush()
                if llr >= self.upper:
                    self.verdict = "accepted H1: the change is worth at least {:.0f} Elo".format(
                        self.args.sprt[1])
                elif llr <= self.lower:
                    self.verdict = "accepted H0: the change is worth at most {:.0f} Elo".format(
                        self.args.sprt[0])
            self.publish(played, llr)
            return self.verdict is None and played < self.args.games


def limit_from(args):
    """What each side is given per move.

    `--depth` exists to separate two questions that a timed match answers
    together: whether an evaluation is better, and whether it is fast enough to
    pay for itself. A slower evaluation loses Elo to its own cost at equal
    time; at equal depth that cost is not charged, so what is left is the
    evaluation. Neither number alone decides anything - a change has to win on
    time to be worth shipping - but knowing which of the two is failing says
    what to work on next.
    """
    if args.depth:
        return chess.engine.Limit(depth=args.depth)
    return chess.engine.Limit(time=args.movetime / 1000.0)


def clock_from(args):
    """(base_ms, increment_ms, margin_ms) when --tc was given, else None."""
    if not args.tc:
        return None
    base, increment = parse_tc(args.tc)
    return base, increment, args.margin


def open_engine(path, options):
    # started in its own folder: several engines read a config file from the
    # working directory, and without it answer with blank lines
    engine = chess.engine.SimpleEngine.popen_uci(path, cwd=os.path.dirname(path) or None)
    for setting in options:
        name, _, value = setting.partition("=")
        engine.configure({name: int(value) if value.isdigit() else value})
    return engine


def worker(args, paths, tally, pairs, failures, live=None, slot=0):
    """Play whole pairs of games until the tally says to stop."""
    try:
        a = open_engine(paths[0], args.option_a)
        b = open_engine(paths[1], args.option_b)
    except Exception as problem:
        failures.append("could not start engines: {}: {}".format(
            type(problem).__name__, problem))
        return
    try:
        while True:
            with pairs["lock"]:
                if pairs["next"] * 2 >= args.games or tally.verdict:
                    return
                pair = pairs["next"]
                pairs["next"] += 1
            # seeded by pair number, not by draw order, so concurrency does not
            # change which openings get played
            if args.openings:
                opening = args.openings[pair % len(args.openings)]
            else:
                opening = random_opening(random.Random(args.seed * 1000003 + pair),
                                         args.opening_plies)
            for a_is_white in (True, False):
                white, black = (a, b) if a_is_white else (b, a)
                report = None
                if live is not None:
                    def report(board, result, _s=slot, _w=a_is_white):
                        live.set_board(_s, board,
                                       args.label_a if _w else args.label_b,
                                       args.label_b if _w else args.label_a, result)
                try:
                    outcome, final, how, clocks = play(
                        white, black, opening, limit_from(args), args.max_plies, report,
                        adjudicate.from_arguments(args), clock_from(args))
                except Exception as problem:
                    failures.append("{}: {}".format(type(problem).__name__, problem))
                    return
                round_number = pair * 2 + (1 if a_is_white else 2)
                wall.save_game(args.pgn, final,
                               args.label_a if a_is_white else args.label_b,
                               args.label_b if a_is_white else args.label_a,
                               "{} vs {}".format(args.label_a, args.label_b), outcome,
                               headers={"Round": str(round_number),
                                        "TimeControl": args.tc if args.tc
                                        else "movetime {} ms".format(args.movetime),
                                        "Termination": how},
                               clocks=clocks)
                if how.startswith("time forfeit"):
                    loser_is_a = (final.turn == chess.WHITE) == a_is_white
                    print("  time forfeit by {} in round {}".format(
                        args.label_a if loser_is_a else args.label_b, round_number))
                    sys.stdout.flush()
                if not tally.record(outcome, a_is_white):
                    return
    finally:
        for side in (a, b):
            engines.shutdown(side)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_a")
    parser.add_argument("engine_b", nargs="?")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--movetime", type=int, default=100, help="milliseconds per move")
    parser.add_argument("--depth", type=int, default=0,
                        help="fixed depth per move instead of a time budget")
    parser.add_argument("--tc", default="",
                        help="a real clock in seconds, BASE+INCREMENT, e.g. 300+3")
    parser.add_argument("--margin", type=int, default=100,
                        help="ms a clock may fall below zero before it loses on time")
    parser.add_argument("--book", default="",
                        help="starting positions, one FEN or EPD a line; each one is "
                             "played twice with colours reversed")
    parser.add_argument("--opening-plies", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=300, help="0 for no cap")
    parser.add_argument("--name-a", default="")
    parser.add_argument("--name-b", default="")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1,
                        help="games in flight at once; each one is a pair of engine processes")
    parser.add_argument("--watch", type=int, default=8761,
                        help="port for the live board wall; 0 turns it off")
    parser.add_argument("--pgn", default="data/games_match.pgn",
                        help="append every game here; empty string turns it off")
    adjudicate.add_arguments(parser)
    parser.add_argument("--option-a", action="append", default=[],
                        help="UCI option for engine A as Name=Value; repeatable")
    parser.add_argument("--option-b", action="append", default=[],
                        help="UCI option for engine B as Name=Value; repeatable")
    parser.add_argument("--sprt", nargs=2, type=float, metavar=("ELO0", "ELO1"),
                        help="sequential test: stop once elo<=ELO0 or elo>=ELO1 is established")
    parser.add_argument("--sprt-min-games", type=int, default=40,
                        help="games to play before the sequential test may stop")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    args = parser.parse_args()

    path_a = os.path.abspath(args.engine_a)
    path_b = os.path.abspath(args.engine_b) if args.engine_b else path_a

    upper = lower = None
    if args.sprt:
        upper = math.log((1.0 - args.beta) / args.alpha)
        lower = math.log(args.beta / (1.0 - args.alpha))

    pairs = {"next": 0, "lock": threading.Lock()}
    failures = []
    # Name each side by whatever actually differs. Usually that is the network,
    # but an A/B of two builds carries the same network on both sides, and two
    # boards both labelled "machete" tell the watcher nothing.
    def net_label(options):
        for setting in options:
            if setting.startswith("EvalFile="):
                return os.path.splitext(os.path.basename(setting[9:]))[0]
        return ""
    def binary_label(path):
        return os.path.splitext(os.path.basename(path))[0]
    nets = (net_label(args.option_a), net_label(args.option_b))
    if nets[0] and nets[1] and nets[0] != nets[1]:
        args.label_a, args.label_b = nets
    else:
        args.label_a, args.label_b = binary_label(path_a), binary_label(path_b)
        if args.label_a == args.label_b:
            args.label_a += " (A)"
            args.label_b += " (B)"
    args.label_a = args.name_a or args.label_a
    args.label_b = args.name_b or args.label_b
    args.openings = load_book(args.book) if args.book else None
    if args.openings and args.games > 2 * len(args.openings):
        print("note: {} games from {} openings, so openings repeat".format(
            args.games, len(args.openings)))

    live = None
    if args.watch:
        live = wall.Live(max(1, args.concurrency),
                         title="{} vs {}".format(args.label_a, args.label_b),
                         columns=("side", "games", "W", "D", "L", "score", "Elo"))
        live.say("{} vs {}".format(args.label_a, args.label_b), "{} games at {}".format(
            args.games, "depth {}".format(args.depth) if args.depth
            else "{} on the clock".format(args.tc) if args.tc
            else "{} ms a move".format(args.movetime)))
        wall.start(live, args.watch, "the match")
    tally = Tally(args, lower, upper, live)
    threads = [threading.Thread(target=worker,
                                args=(args, (path_a, path_b), tally, pairs, failures,
                                      live, slot))
               for slot in range(max(1, args.concurrency))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        # stderr, so that check.sh's gate shows why a match failed
        sys.stderr.write("match failed: {}\n".format(failures[0]))
        return 1

    wins, draws, losses = tally.wins, tally.draws, tally.losses
    verdict = tally.verdict
    games = wins + draws + losses
    if games == 0:
        sys.stderr.write("no games were played\n")
        return 1
    score = (wins + 0.5 * draws) / games
    print("games {} wins {} draws {} losses {}".format(games, wins, draws, losses))
    print("score {:.3f}".format(score))
    if args.sprt:
        llr = log_likelihood_ratio(wins, draws, losses, args.sprt[0], args.sprt[1])
        print("llr {:+.2f}".format(llr))
        print(verdict or "inconclusive: ran out of games before either bound")
    if args.engine_b:
        elo, margin = elo_difference(score, games)
        if math.isinf(elo):
            print("elo {} (one side won every game)".format("+inf" if elo > 0 else "-inf"))
        else:
            print("elo {:+.0f} +/- {:.0f}".format(elo, margin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
