"""Can machete finish a won ending? A gate on the whole engine, not the search.

    python harness/conversion.py [--engine BIN] [--seconds 1.0]

Unit tests search one position once. A real game searches a hundred positions
in a row with one transposition table, and that is where ladder 4 drew queen
and bishop against a bare king: from move 106 machete reported mate in 19-30
at depth 1-7, took the table's word for it, stopped searching, and played the
table's move until the fifty-move rule ended the game. Given any one of those
positions cold, it found mate in three at depth four.

Two checks. First, fixtures/unproven_mate.pgn - that game - is replayed from
move 103 through one engine, and machete must never stop searching on a mate
it has not searched to its length. A mate found shallower than its length is
fine - checks extend - but ending the search there, with time left, is the bug.
The old engine did it on 50 moves of that game, at depth 1 to 7.

Second, each position below is played out as a game: machete with one engine
instance and no `ucinewgame` between moves, a Stockfish defender, a real
fifty-move rule. Each is played --trials times, because machete moves on a
clock and one game is one sample; an ending passes if two thirds of its games
end in mate. The length of every game is printed, so a slow conversion is
visible before it becomes a draw.
"""

import argparse
import os
import sys
import time

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import engine as engines
import panel

POSITIONS = [
    # ladder 4, Rybka game 20, move 127: drawn by the fifty-move rule
    ("KQB v K, from ladder 4", "8/8/5K2/4B3/8/8/3Q4/5k2 w - - 0 1"),
    # the same game at move 106, where the table first claimed a long mate
    ("KQB v K, ladder 4 move 106", "5Q2/8/5K2/4B3/8/5k2/8/8 w - - 0 1"),
    ("KQ v K", "8/8/8/4k3/8/8/8/3QK3 w - - 0 1"),
    ("KR v K", "8/8/8/4k3/8/8/8/R3K3 w - - 0 1"),
    ("KQ v KN", "8/8/3n4/4k3/8/8/8/3QK3 w - - 0 1"),
]

# won endings machete cannot yet finish in fifty moves, before or after the fix
# above: reported every run, not failed on. They are the network's to learn -
# the next corpus's mate-distance labels - and move up to POSITIONS once won.
TARGETS = [
    ("KQ v KR", "8/8/3r4/4k3/8/8/8/3QK3 w - - 0 1"),
    ("KBB v K", "8/8/8/4k3/8/8/8/2B1KB2 w - - 0 1"),
]


REPLAY = os.path.join(os.path.dirname(HERE), "fixtures", "unproven_mate.pgn")
REPLAY_FROM = 103


def unproven_claims(ours, seconds):
    """Machete's moves in the fixture game where it reported a mate it had not searched."""
    with open(REPLAY) as handle:
        game = chess.pgn.read_game(handle)
    board = game.board()
    colour = chess.WHITE if game.headers["White"] == "machete" else chess.BLACK
    session = object()
    claims = []
    for move in game.mainline_moves():
        if board.turn == colour and board.fullmove_number >= REPLAY_FROM:
            began = time.monotonic()
            info = ours.analyse(board, chess.engine.Limit(time=seconds), game=session)
            spent = time.monotonic() - began
            mate = info["score"].pov(colour).mate()
            # the time rule stops only after two thirds of the budget; the bug
            # stopped at once. Wall time, not the info line's: that is when the
            # last finished iteration printed, and the next may run to the end.
            stopped_early = spent < seconds / 3
            if mate is not None and mate > 0 and info.get("depth", 0) < 2 * mate - 1 and stopped_early:
                claims.append("move {}: mate in {} at depth {}".format(
                    board.fullmove_number, mate, info.get("depth")))
        board.push(move)
    return claims


def play_out(ours, defender, fen, seconds, defender_nodes):
    board = chess.Board(fen)
    game = object()
    while not board.is_game_over(claim_draw=True):
        if board.turn == chess.WHITE:
            move = ours.play(board, chess.engine.Limit(time=seconds), game=game).move
        else:
            move = defender.play(board, chess.engine.Limit(nodes=defender_nodes)).move
        board.push(move)
    return board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--seconds", type=float, default=1.0, help="machete's time per move")
    parser.add_argument("--trials", type=int, default=3,
                        help="games per ending; an ending passes if at least two thirds are mated")
    parser.add_argument("--defender-nodes", type=int, default=200000)
    args = parser.parse_args()

    ours = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
    ours.configure({"EvalFile": os.path.abspath(args.net)})
    engines.pin(ours)
    defender = panel.open_engine("Stockfish", 64)
    failed = 0
    try:
        claims = unproven_claims(ours, args.seconds)
        print("replay of {}: {}".format(os.path.basename(REPLAY),
              "every mate claim searched to its length" if not claims else
              "FAIL, {} unproven mate claims, first {}".format(len(claims), claims[0])))
        failed += 1 if claims else 0
        # each ending is played --trials times: machete moves on a clock, so
        # one game is one draw from a distribution - network A converted
        # KQ v KN in 18, 35 and 52 moves on three runs of the same build
        need = (2 * args.trials + 2) // 3
        for name, fen, required in [p + (True,) for p in POSITIONS] + [p + (False,) for p in TARGETS]:
            lengths = []
            for _ in range(args.trials):
                board = play_out(ours, defender, fen, args.seconds, args.defender_nodes)
                mated = board.is_checkmate() and board.turn == chess.BLACK
                lengths.append((board.ply() + 1) // 2 if mated else None)
            won = sum(1 for n in lengths if n is not None)
            verdict = "ok" if won >= need else ("FAIL" if required else "not yet")
            failed += 1 if required and won < need else 0
            print("{:<28} {:<7} {}/{} mated   moves {}".format(
                name, verdict, won, args.trials,
                " ".join(str(n) if n is not None else "draw" for n in lengths)))
            sys.stdout.flush()
    finally:
        engines.shutdown(ours)
        engines.shutdown(defender)
    print("{} check(s) failed".format(failed) if failed else "all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
