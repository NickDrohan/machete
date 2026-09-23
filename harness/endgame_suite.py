"""Can the engine finish a won game?

    python harness/endgame_suite.py ENGINE [--net NET] [--movetime 500]

Elo hides this. A draw from a won position costs half a point exactly like a
draw from an equal one, and in self-play both sides share the defect, so a
match between two versions of this engine scores it as no difference at all.
It took watching a game to notice.

So this is a gate rather than a measurement: each position is an elementary
forced win, the engine plays both sides, and anything that does not end in
mate is a failure with a name. It exits non-zero when fewer than `--require`
of them convert, which is what makes it usable from check.sh.

The current state, at 500 ms a move: KQ v K converts in 15 plies and KR v K in
59, but **KQ v KN and KBB v K both draw by the fifty-move rule**. The pattern
is that it converts wins that are reachable inside the search horizon and
fails wins that need a plan with no material change - driving a king to a
corner, or winning a piece before mating. Nothing in the evaluation rewards
either, so the search has no gradient to climb: the network scores KQ v K at
+551 and does not move it between depth 4 and depth 14.

`--plies` is the other half of the report. Converting KR v K in 59 plies when
the optimum is 31 is not a pass in any meaningful sense, it is a near miss, and
a change that takes it to 40 is progress that a pass/fail count would hide.
"""

import argparse
import os
import sys

import chess
import chess.engine

import engine as engines

# (fen, name, optimal plies to mate with best play) - the optimum is the
# published worst case for that material from a random legal position, so a
# conversion well above it is technique that is working but badly.
POSITIONS = [
    ("8/8/8/8/2k5/8/8/KQ6 w - - 0 1",      "KQ v K",     20),
    ("8/8/8/4k3/8/8/8/KQ6 w - - 0 1",      "KQ v K (2)", 20),
    ("8/8/8/8/2k5/8/8/KR6 w - - 0 1",      "KR v K",     32),
    ("8/8/8/4k3/8/8/8/KR6 w - - 0 1",      "KR v K (2)", 32),
    ("8/8/8/8/8/2k5/8/KBB5 w - - 0 1",     "KBB v K",    38),
    ("8/8/8/3k4/8/8/8/KBB5 w - - 0 1",     "KBB v K (2)",38),
    ("8/8/8/8/2kn4/8/8/KQ6 w - - 0 1",     "KQ v KN",    40),
    ("8/8/8/8/2kb4/8/8/KQ6 w - - 0 1",     "KQ v KB",    40),
    ("8/8/8/8/2kr4/8/8/KQ6 w - - 0 1",     "KQ v KR",    60),
    ("8/8/8/8/2kn4/8/8/KR6 w - - 0 1",     "KR v KN",    60),
    ("3R4/8/8/2k5/8/8/4K3/8 w - - 0 1",    "KR v K (game)", 32),
    ("8/8/8/8/8/2k5/8/KBN5 w - - 0 1",     "KBN v K",    66),
]


def convert(engine, fen, limit, cap):
    """Play a position out against itself. Returns (mated, plies, why)."""
    board = chess.Board(fen)
    winner = board.turn
    plies = 0
    while not board.is_game_over(claim_draw=True) and plies < cap:
        result = engine.play(board, limit)
        if result.move is None or result.move not in board.legal_moves:
            return False, plies, "illegal move"
        board.push(result.move)
        plies += 1
    if board.is_checkmate():
        return board.turn != winner, plies, "mate"
    if plies >= cap:
        return False, plies, "no mate in {} plies".format(cap)
    if board.can_claim_fifty_moves():
        return False, plies, "fifty-move rule"
    if board.is_stalemate():
        return False, plies, "stalemate"
    return False, plies, board.result(claim_draw=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", nargs="?", default=engines.MACHETE)
    parser.add_argument("--net", default="")
    parser.add_argument("--movetime", type=int, default=500)
    parser.add_argument("--cap", type=int, default=160, help="give up after this many plies")
    parser.add_argument("--require", type=int, default=0,
                        help="exit non-zero below this many conversions")
    args = parser.parse_args()

    options = []
    if args.net:
        options.append("EvalFile=" + os.path.abspath(args.net))
    try:
        engine = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
        for setting in options:
            name, _, value = setting.partition("=")
            engine.configure({name: value})
    except Exception as problem:
        print("could not start {}: {}".format(args.engine, problem))
        return 1

    limit = chess.engine.Limit(time=args.movetime / 1000.0)
    print("{:<16}{:>8}{:>9}{:>10}   {}".format("position", "optimum", "plies", "ratio", "result"))
    won = 0
    total_excess = 0
    try:
        for fen, name, optimum in POSITIONS:
            mated, plies, why = convert(engine, fen, limit, args.cap)
            won += 1 if mated else 0
            if mated:
                total_excess += max(0, plies - optimum)
            print("{:<16}{:>8}{:>9}{:>10}   {}".format(
                name, optimum, plies,
                "{:.1f}x".format(float(plies) / optimum) if mated else "-",
                "mate" if mated else "FAILED: " + why))
    finally:
        engines.shutdown(engine)

    print("\n{} of {} converted at {} ms a move".format(won, len(POSITIONS), args.movetime))
    if won:
        print("{} plies spent beyond the optimum across the wins".format(total_excess))
    if args.require and won < args.require:
        print("below the required {}".format(args.require))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
