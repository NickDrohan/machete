"""Play mate against a local Ollama model, and write the game as PGN.

    python harness/vs_llm.py ENGINE --model qwen3.8:27b --movetime 200

The engine plays one colour and the model the other. The model is asked for a
move in UCI notation and given the position as FEN plus the move list; an
unparseable or illegal answer is retried, and a model that cannot produce a
legal move after --retries forfeits, which is how the existing llmchess
tournament scores it too.

Only models served from localhost are used. A ":cloud" model would send the
position to a third party, so it is refused.
"""

import argparse
import os
import re
import sys
import time

import chess

import engine as engines
import chess.engine
import chess.pgn
import requests

OLLAMA = "http://localhost:11434/api/generate"
UCI_MOVE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b")


def ask_model(model, board, temperature, timeout):
    moves = " ".join(m.uci() for m in board.move_stack) or "(none yet)"
    legal = " ".join(sorted(m.uci() for m in board.legal_moves))
    prompt = (
        "You are playing chess as {}. Reply with exactly one move in UCI "
        "notation (for example e2e4 or e7e8q) and nothing else.\n\n"
        "Position (FEN): {}\n"
        "Moves so far: {}\n"
        "Legal moves: {}\n\n"
        "Your move:"
    ).format("White" if board.turn == chess.WHITE else "Black",
             board.fen(), moves, legal)
    response = requests.post(OLLAMA, json={
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }, timeout=timeout)
    response.raise_for_status()
    return response.json().get("response", "")


def model_move(model, board, retries, temperature, timeout):
    for attempt in range(retries):
        try:
            text = ask_model(model, board, temperature + 0.2 * attempt, timeout)
        except requests.RequestException as problem:
            # a loading or busy server answers 500 for a while; that is not a forfeit
            print("  model request failed (attempt {}): {}".format(attempt + 1, problem))
            time.sleep(5)
            continue
        for candidate in UCI_MOVE.findall(text):
            try:
                move = chess.Move.from_uci(candidate)
            except ValueError:
                continue
            if move in board.legal_moves:
                return move
        print("  model gave no legal move (attempt {}): {!r}".format(attempt + 1, text.strip()[:80]))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--model", default="qwen3.8:27b")
    parser.add_argument("--movetime", type=int, default=200, help="engine milliseconds per move")
    parser.add_argument("--engine-white", action="store_true")
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.3)
    # a large model can take minutes to load before its first token
    parser.add_argument("--model-timeout", type=int, default=900, help="seconds per model reply")
    parser.add_argument("--pgn", help="write the game here")
    args = parser.parse_args()

    if args.model.endswith(":cloud"):
        sys.stderr.write("refusing {}: a cloud model would send the position off this machine\n"
                         .format(args.model))
        return 2

    engine = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
    board = chess.Board()
    limit = chess.engine.Limit(time=args.movetime / 1000.0)
    forfeit = None
    try:
        while not board.is_game_over(claim_draw=True) and board.ply() < args.max_plies:
            engine_turn = (board.turn == chess.WHITE) == args.engine_white
            if engine_turn:
                move = engine.play(board, limit).move
                who = "machete"
            else:
                move = model_move(args.model, board, args.retries, args.temperature,
                                  args.model_timeout)
                who = args.model
                if move is None:
                    forfeit = who
                    break
            print("{:3d}. {} plays {}".format(board.fullmove_number, who, move.uci()))
            board.push(move)
    finally:
        engines.shutdown(engine)

    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "mate vs {}".format(args.model)
    game.headers["White"] = "machete" if args.engine_white else args.model
    game.headers["Black"] = args.model if args.engine_white else "machete"
    if forfeit:
        game.headers["Result"] = "1-0" if forfeit != "machete" and not args.engine_white else "0-1"
        game.headers["Termination"] = "{} could not produce a legal move".format(forfeit)
        print("{} forfeits: no legal move after {} attempts".format(forfeit, args.retries))
    else:
        print("result: {}".format(board.result(claim_draw=True)))

    if args.pgn:
        with open(args.pgn, "w") as handle:
            handle.write(str(game) + "\n")
        print("wrote {}".format(args.pgn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
