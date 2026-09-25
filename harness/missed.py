"""Where machete had a win and let it go.

    python harness/missed.py data/games_ladder4.pgn --result draw --out data/missed

harness/audit.py looks for errors: moves that made machete's position worse.
A drawn game can have none of those and still be a failure - machete was
winning at some point and never found the way through. This looks for that.

Every machete move is judged by Stockfish at a fixed node count. A missed
opportunity is a position where Stockfish's best move keeps machete at least
WINNING centipawns ahead and machete's move gives up at least SLIP of it. For
each one, machete searches the position again at --deep: if it then finds a
move as good as Stockfish's, the win was there for its evaluation and the
search did not reach it; if not, the network did not see it at all.
"""

import argparse
import json
import os
import sys

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import engine as engines
import panel

WINNING = 150
SLIP = 80
NEAR_BEST = 30
MATE = 3000


def value(info, colour):
    return info["score"].pov(colour).score(mate_score=MATE)


def how_it_ended(board):
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient material"
    if board.can_claim_threefold_repetition():
        return "repetition"
    if board.halfmove_clock >= 100:
        return "fifty moves"
    return "other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--player", default="machete")
    parser.add_argument("--result", choices=("draw", "loss", "any"), default="draw")
    parser.add_argument("--opponent", default="", help="only games against a name containing this")
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--judge-nodes", type=int, default=200000)
    parser.add_argument("--deep", type=int, default=16)
    parser.add_argument("--out", default="data/missed")
    args = parser.parse_args()

    judge = panel.open_engine("Stockfish", 128)
    ours = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
    ours.configure({"EvalFile": os.path.abspath(args.net)})
    judge_limit = chess.engine.Limit(nodes=args.judge_nodes)
    missed = []
    games = []
    try:
        with open(args.pgn, encoding="utf-8", errors="replace") as handle:
            number = 0
            while True:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                white, black = game.headers["White"], game.headers["Black"]
                if args.player not in (white, black) or args.opponent not in white + black:
                    continue
                number += 1
                colour = chess.WHITE if white == args.player else chess.BLACK
                result = game.headers["Result"]
                kind = "draw" if result == "1/2-1/2" else (
                    "win" if (result == "1-0") == (colour == chess.WHITE) else "loss")
                if args.result != "any" and kind != args.result:
                    continue
                opponent = black if colour == chess.WHITE else white
                board = game.board()
                peak = (-MATE, 0)
                chances = []
                for move in game.mainline_moves():
                    if board.turn == colour:
                        info = judge.analyse(board, judge_limit)
                        best_value = value(info, colour)
                        if best_value > peak[0]:
                            peak = (best_value, board.fullmove_number)
                        best = info.get("pv", [None])[0]
                        if best_value >= WINNING and best is not None and move != best:
                            after = board.copy()
                            after.push(move)
                            played_value = value(judge.analyse(after, judge_limit), colour) \
                                if not after.is_game_over() else 0
                            if best_value - played_value >= SLIP:
                                deep = ours.play(board, chess.engine.Limit(depth=args.deep)).move
                                probe = board.copy()
                                probe.push(deep)
                                deep_value = value(judge.analyse(probe, judge_limit), colour)
                                chances.append({
                                    "game": number, "opponent": opponent, "move": board.fullmove_number,
                                    "fen": board.fen(), "played": board.san(move), "best": board.san(best),
                                    "deep": board.san(deep), "best_value": best_value,
                                    "played_value": played_value, "deep_value": deep_value,
                                    "cause": "search" if best_value - deep_value <= NEAR_BEST else "evaluation"})
                    board.push(move)
                ended = how_it_ended(board)
                games.append({"game": number, "opponent": opponent, "colour": "W" if colour else "B",
                              "plies": board.ply(), "ended": ended, "peak": peak[0],
                              "peak_move": peak[1], "chances": len(chances)})
                missed.extend(chances)
                print("game {:>2} vs {:<14} {} {:>3} plies, {:<21} peak {:+5d} at move {:>3}, {} missed".format(
                    number, opponent, "W" if colour else "B", board.ply(), ended, peak[0], peak[1],
                    len(chances)))
                for c in chances:
                    print("    move {:>3}: played {:<7} ({:+5d})  best {:<7} ({:+5d})  depth {}: {:<7} ({:+5d}) -> {}".format(
                        c["move"], c["played"], c["played_value"], c["best"], c["best_value"],
                        args.deep, c["deep"], c["deep_value"], c["cause"]))
                sys.stdout.flush()
    finally:
        engines.shutdown(judge)
        engines.shutdown(ours)

    with open(args.out + ".json", "w") as handle:
        json.dump({"games": games, "missed": missed}, handle, indent=1)
    with open(args.out + ".epd", "w", newline="\n") as handle:
        handle.write("# positions where machete was winning and let it go\n")
        for c in missed:
            handle.write(c["fen"] + "\n")
    search = sum(1 for c in missed if c["cause"] == "search")
    print("\n{} games, {} missed chances: {} found at depth {} (search), {} not (evaluation)".format(
        len(games), len(missed), search, args.deep, len(missed) - search))
    return 0


if __name__ == "__main__":
    sys.exit(main())
