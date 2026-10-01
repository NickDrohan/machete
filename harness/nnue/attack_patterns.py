"""What the attack suite's winning moves are: their motifs, and the openings they come from.

    python harness/nnue/attack_patterns.py PGN [PGN ...] --progress data/attack_suite.epd.progress.jsonl

Reads attack_suite.py's progress file (so it works while the suite is still
being built) and classifies every suite move - the winner's only good move in
an engine miniature - by what it does:

  sacrifice     the moved piece can be taken by something worth less, or is
                left en prise with nothing defending it: material given for time
  check         gives check
  king zone     lands within two squares of the enemy king
  pawn storm    a pawn advancing on the enemy king's file or a neighbour
  rook lift     a rook moving up its file to the third or fourth rank
  capture       takes something
  quiet         none of the above

A move can be several. The openings are the games' ECO families, to see which
systems the attacks come from - for the repertoire, and for the attack book.
"""
import argparse
import collections
import json
import os
import sys

import chess
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attack_suite  # noqa: E402

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def motifs(board, move):
    out = []
    mover = board.turn
    piece = board.piece_at(move.from_square)
    enemy_king = board.king(not mover)
    after = board.copy()
    after.push(move)
    to = move.to_square
    attackers = after.attackers(not mover, to)
    defenders = after.attackers(mover, to)
    cheapest = min((VALUE[after.piece_at(s).piece_type] for s in attackers), default=None)
    gained = VALUE[board.piece_at(to).piece_type] if board.piece_at(to) else 0
    if piece.piece_type != chess.KING and cheapest is not None and (
            (cheapest < VALUE[piece.piece_type] and VALUE[piece.piece_type] > gained) or (not defenders and VALUE[piece.piece_type] > gained)):
        out.append("sacrifice")
    if after.is_check():
        out.append("check")
    if enemy_king is not None and chess.square_distance(to, enemy_king) <= 2:
        out.append("king zone")
    if piece.piece_type == chess.PAWN and enemy_king is not None and abs(chess.square_file(to) - chess.square_file(enemy_king)) <= 1 \
            and not board.is_capture(move):
        out.append("pawn storm")
    if piece.piece_type == chess.ROOK and chess.square_file(move.from_square) == chess.square_file(to):
        rank = chess.square_rank(to) if mover == chess.WHITE else 7 - chess.square_rank(to)
        if rank in (2, 3):
            out.append("rook lift")
    if board.is_capture(move):
        out.append("capture")
    if not out:
        out.append("quiet")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn", nargs="+")
    parser.add_argument("--progress", required=True)
    parser.add_argument("--min-plies", type=int, default=40)
    parser.add_argument("--max-plies", type=int, default=100)
    args = parser.parse_args()

    done = {}
    for line in open(args.progress, encoding="utf-8"):
        row = json.loads(line)
        if "suite" in row:
            done[row["key"]] = row
    # the games again, for their openings (attack_suite keys them by order)
    eco_of, opening_of = {}, {}
    for k, path in enumerate(args.pgn):
        with open(path, encoding="utf-8", errors="replace") as handle:
            n = 0
            while True:
                try:
                    game = chess.pgn.read_game(handle)
                except Exception:
                    continue
                if game is None:
                    break
                result = game.headers.get("Result")
                if result not in ("1-0", "0-1") or game.board().fen() != chess.STARTING_FEN:
                    continue
                if game.headers.get("Variant", "Standard").lower() not in ("standard", ""):
                    continue
                plies = len(list(game.mainline_moves()))
                if args.min_plies <= plies < args.max_plies:
                    key = "%d:%d" % (k, n)
                    eco_of[key] = game.headers.get("ECO", "?")
                    opening_of[key] = game.headers.get("Opening", "?")
                    n += 1

    counts, combos, by_eco, by_family = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    total = 0
    for key, row in done.items():
        eco = eco_of.get(key, "?")
        if row["suite"]:
            by_eco[eco[:2] if eco != "?" else "?"] += len(row["suite"])
            by_family[opening_of.get(key, "?").split(":")[0]] += len(row["suite"])
        for fen, san, s1, margin, name, ply in row["suite"]:
            board = chess.Board(fen)
            found = motifs(board, board.parse_san(san))
            total += 1
            for m in found:
                counts[m] += 1
            combos[" + ".join(found)] += 1
    print("%d games analysed, %d attack moves" % (len(done), total))
    print("\nmotifs (a move can have several):")
    for m, n in counts.most_common():
        print("  %5.1f%%  %s" % (100.0 * n / max(1, total), m))
    print("\ncommonest combinations:")
    for c, n in combos.most_common(10):
        print("  %4d  %s" % (n, c))
    print("\nopenings the attacks come from (ECO families, then names):")
    for e, n in by_eco.most_common(10):
        print("  %4d  %s" % (n, e))
    for f, n in by_family.most_common(12):
        print("  %4d  %s" % (n, f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
