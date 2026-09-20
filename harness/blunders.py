"""Find out how machete actually loses, rather than guessing.

    python harness/blunders.py games.pgn --engine STOCKFISH --depth 12

Walks every game, asks a strong engine what each position was worth before and
after machete's move, and reports the moves that threw material or position
away. Each one is bucketed by game phase and by what kind of mistake it was,
so the ranked output says where the Elo is going.

The buckets are deliberately crude - a ranked list of "most of the loss is
here" is what directs work; a finer taxonomy would be a research project of
its own.
"""

import argparse
import collections
import os
import sys

import chess
import chess.engine
import chess.pgn

BLUNDER = 150      # centipawns lost in one move to count as a blunder
MISTAKE = 60       # ... and to count as a mistake


def phase_of(board):
    """Opening, middlegame or endgame, by the usual material count."""
    weights = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}
    total = sum(weights[p] * len(board.pieces(p, c))
                for p in weights for c in (chess.WHITE, chess.BLACK))
    if total >= 20:
        return "opening"
    if total >= 8:
        return "middlegame"
    return "endgame"


def kind_of(board, move, drop):
    """A crude label for what went wrong."""
    mover = board.piece_at(move.from_square)
    if board.is_capture(move):
        return "bad capture"
    after = board.copy()
    after.push(move)
    if after.is_check():
        return "unsound check"
    # did the move leave the piece it moved hanging?
    if after.attackers(not board.turn, move.to_square) and \
            not after.attackers(board.turn, move.to_square):
        return "hangs the piece it moved"
    # did it leave something else hanging?
    for square in chess.SQUARES:
        piece = after.piece_at(square)
        if piece and piece.color == board.turn and square != move.to_square:
            if after.attackers(not board.turn, square) and not after.attackers(board.turn, square):
                return "leaves a piece hanging"
    if mover and mover.piece_type == chess.PAWN:
        return "pawn move"
    return "positional drift"


def score_of(info, pov):
    score = info["score"].pov(pov)
    if score.is_mate():
        return 2000 if score.mate() > 0 else -2000
    return max(-2000, min(2000, score.score()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--engine", required=True, help="a strong engine to judge with")
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--player", default="machete", help="whose moves to judge")
    parser.add_argument("--max-games", type=int, default=40)
    parser.add_argument("--show", type=int, default=12, help="worst N moves to print")
    args = parser.parse_args()

    judge = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
    limit = chess.engine.Limit(depth=args.depth)

    by_phase = collections.Counter()
    by_kind = collections.Counter()
    loss_by_phase = collections.Counter()
    loss_by_kind = collections.Counter()
    worst = []
    moves_judged = 0
    games_read = 0

    try:
        with open(args.pgn) as handle:
            while games_read < args.max_games:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                games_read += 1
                white = args.player.lower() in game.headers.get("White", "").lower()
                black = args.player.lower() in game.headers.get("Black", "").lower()
                if not (white or black):
                    continue
                ours = chess.WHITE if white else chess.BLACK
                board = game.board()
                for move in game.mainline_moves():
                    if board.turn != ours:
                        board.push(move)
                        continue
                    before = score_of(judge.analyse(board, limit), ours)
                    played = board.copy()
                    played.push(move)
                    if played.is_game_over():
                        board.push(move)
                        continue
                    after = score_of(judge.analyse(played, limit), ours)
                    drop = before - after
                    moves_judged += 1
                    if drop >= MISTAKE:
                        phase = phase_of(board)
                        kind = kind_of(board, move, drop)
                        label = "blunder" if drop >= BLUNDER else "mistake"
                        by_phase[(phase, label)] += 1
                        by_kind[kind] += 1
                        loss_by_phase[phase] += drop
                        loss_by_kind[kind] += drop
                        worst.append((drop, board.fen(), board.san(move), phase, kind))
                    board.push(move)
                    sys.stdout.write("\r{} games, {} moves judged".format(games_read, moves_judged))
                    sys.stdout.flush()
    finally:
        judge.quit()

    print("\n")
    print("judged {} moves over {} games".format(moves_judged, games_read))
    if not moves_judged:
        return 1

    print("\nwhere the centipawns go, by phase:")
    for phase in ("opening", "middlegame", "endgame"):
        blunders = by_phase[(phase, "blunder")]
        mistakes = by_phase[(phase, "mistake")]
        print("  {:<12} {:>4} blunders  {:>4} mistakes  {:>7} cp lost".format(
            phase, blunders, mistakes, loss_by_phase[phase]))

    print("\nby kind of mistake:")
    for kind, count in by_kind.most_common():
        print("  {:<28} {:>4} moves  {:>7} cp".format(kind, count, loss_by_kind[kind]))

    print("\nworst {} moves:".format(args.show))
    for drop, fen, san, phase, kind in sorted(worst, reverse=True)[:args.show]:
        print("  -{:>4} cp  {:<8} {:<28} {}".format(drop, san, kind, fen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
