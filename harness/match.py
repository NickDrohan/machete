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

import chess
import chess.engine

import wall
import adjudicate


def random_opening(rng, plies):
    board = chess.Board()
    for _ in range(plies):
        moves = list(board.legal_moves)
        if not moves or board.is_game_over():
            break
        board.push(rng.choice(moves))
    return board.move_stack[:]


def play(white, black, opening, limit, max_plies, report=None, judge=None):
    """Play one game; returns '1-0', '0-1', '1/2-1/2'."""
    board = chess.Board()
    for move in opening:
        board.push(move)
    if judge:
        judge.reset()
    if report:
        report(board, None)
    while not board.is_game_over(claim_draw=True):
        if board.ply() >= max_plies:
            if report:
                report(board, "1/2-1/2")
            return "1/2-1/2", board
        engine = white if board.turn == chess.WHITE else black
        white_to_move = board.turn == chess.WHITE
        if judge and judge.enabled:
            result = engine.play(board, limit, info=chess.engine.INFO_SCORE)
            verdict = judge.observe(board, white_to_move,
                                    adjudicate.score_of(result.info, white_to_move))
            if verdict is not None:
                if report:
                    report(board, verdict)
                return verdict, board
        else:
            result = engine.play(board, limit)
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError("illegal move {} in {}".format(result.move, board.fen()))
        board.push(result.move)
        if report:
            report(board, None)
    outcome = board.result(claim_draw=True)
    if report:
        report(board, outcome)
    return outcome, board


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

    def __init__(self, args, lower, upper):
        self.lock = threading.Lock()
        self.wins = self.draws = self.losses = 0
        self.verdict = None
        self.args = args
        self.lower = lower
        self.upper = upper

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


def open_engine(path, options):
    engine = chess.engine.SimpleEngine.popen_uci(path)
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
        failures.append("could not start engines: {}".format(problem))
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
                    outcome, final = play(white, black, opening, limit_from(args),
                                          args.max_plies, report,
                                          adjudicate.from_arguments(args))
                except Exception as problem:
                    failures.append(str(problem))
                    return
                wall.save_game(args.pgn, final,
                               args.label_a if a_is_white else args.label_b,
                               args.label_b if a_is_white else args.label_a,
                               "{} vs {}".format(args.label_a, args.label_b), outcome)
                if not tally.record(outcome, a_is_white):
                    return
    finally:
        for engine in (a, b):
            try:
                engine.quit()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_a")
    parser.add_argument("engine_b", nargs="?")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--movetime", type=int, default=100, help="milliseconds per move")
    parser.add_argument("--depth", type=int, default=0,
                        help="fixed depth per move instead of a time budget")
    parser.add_argument("--opening-plies", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=300)
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

    tally = Tally(args, lower, upper)
    pairs = {"next": 0, "lock": threading.Lock()}
    failures = []
    # name each side by its network file, which is usually the only difference
    def side_label(options, engine_path):
        for setting in options:
            if setting.startswith("EvalFile="):
                return os.path.splitext(os.path.basename(setting[9:]))[0]
        return os.path.splitext(os.path.basename(engine_path))[0]
    args.label_a = side_label(args.option_a, path_a)
    args.label_b = side_label(args.option_b, path_b)

    live = None
    if args.watch:
        live = wall.Live(max(1, args.concurrency))
        live.say("{} vs {}".format(args.label_a, args.label_b), "{} games at {}".format(
            args.games, "depth {}".format(args.depth) if args.depth
            else "{} ms a move".format(args.movetime)))
        wall.start(live, args.watch, "the match")
    threads = [threading.Thread(target=worker,
                                args=(args, (path_a, path_b), tally, pairs, failures,
                                      live, slot))
               for slot in range(max(1, args.concurrency))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        print("match failed: {}".format(failures[0]))
        return 1

    wins, draws, losses = tally.wins, tally.draws, tally.losses
    verdict = tally.verdict
    games = wins + draws + losses
    if games == 0:
        print("no games were played")
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
