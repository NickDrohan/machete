"""Play engine-vs-engine matches through python-chess and report the result.

    python harness/match.py ENGINE_A [ENGINE_B] --games 20 --movetime 100
    python harness/match.py NEW OLD --sprt 0 10 --games 2000

With one engine it plays itself, which is the protocol soak test: any illegal
move, crash, hang or protocol error fails the run. With two it measures the
difference between them and prints an Elo estimate with an error bar.

Colours alternate, and each opening is played twice, once from each side, so a
lucky opening cannot decide the match.

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

import chess
import chess.engine


def random_opening(rng, plies):
    board = chess.Board()
    for _ in range(plies):
        moves = list(board.legal_moves)
        if not moves or board.is_game_over():
            break
        board.push(rng.choice(moves))
    return board.move_stack[:]


def play(white, black, opening, movetime, max_plies):
    """Play one game; returns '1-0', '0-1', '1/2-1/2'."""
    board = chess.Board()
    for move in opening:
        board.push(move)
    limit = chess.engine.Limit(time=movetime / 1000.0)
    while not board.is_game_over(claim_draw=True):
        if board.ply() >= max_plies:
            return "1/2-1/2"
        engine = white if board.turn == chess.WHITE else black
        result = engine.play(board, limit)
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError("illegal move {} in {}".format(result.move, board.fen()))
        board.push(result.move)
    return board.result(claim_draw=True)


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_a")
    parser.add_argument("engine_b", nargs="?")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--movetime", type=int, default=100, help="milliseconds per move")
    parser.add_argument("--opening-plies", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
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
    rng = random.Random(args.seed)

    a = chess.engine.SimpleEngine.popen_uci(path_a)
    b = chess.engine.SimpleEngine.popen_uci(path_b)
    for engine, options in ((a, args.option_a), (b, args.option_b)):
        for setting in options:
            name, _, value = setting.partition("=")
            engine.configure({name: int(value) if value.isdigit() else value})
    wins = draws = losses = 0
    verdict = None
    upper = lower = None
    if args.sprt:
        upper = math.log((1.0 - args.beta) / args.alpha)
        lower = math.log(args.beta / (1.0 - args.alpha))
    try:
        for pair in range((args.games + 1) // 2):
            opening = random_opening(rng, args.opening_plies)
            for a_is_white in (True, False):
                white, black = (a, b) if a_is_white else (b, a)
                outcome = play(white, black, opening, args.movetime, args.max_plies)
                if outcome == "1/2-1/2":
                    draws += 1
                elif (outcome == "1-0") == a_is_white:
                    wins += 1
                else:
                    losses += 1
                if args.sprt:
                    llr = log_likelihood_ratio(wins, draws, losses, args.sprt[0], args.sprt[1])
                    played = wins + draws + losses
                    if played < args.sprt_min_games:
                        llr = 0.0
                    if played % 20 == 0:
                        print("  {} games, LLR {:+.2f} (bounds {:+.2f} .. {:+.2f})".format(
                            played, llr, lower, upper))
                        sys.stdout.flush()
                    if llr >= upper:
                        verdict = "accepted H1: the change is worth at least {:.0f} Elo".format(args.sprt[1])
                    elif llr <= lower:
                        verdict = "accepted H0: the change is worth at most {:.0f} Elo".format(args.sprt[0])
                if verdict or wins + draws + losses >= args.games:
                    break
            if verdict or wins + draws + losses >= args.games:
                break
    finally:
        a.quit()
        b.quit()

    games = wins + draws + losses
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
