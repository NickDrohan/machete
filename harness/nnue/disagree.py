"""Find what a stronger engine sees in our games that we do not.

    python harness/nnue/disagree.py data/games_koivisto.pgn \
        --engine ENGINE --net NET --judge Koivisto --show 10

A blunder profile says how much was lost and roughly what kind of move lost it.
This asks a narrower question: at the moment our evaluation and a stronger
one part company, what is on the board?

Every position our engine moved from is scored twice - once by our network,
once by the judge - and the gap between them is the disagreement. The biggest
gaps are where our evaluation is confidently wrong, which is exactly the set a
retrained network needs and the set no amount of extra search will fix.

Each disagreement is then described by things a material-and-squares
evaluation cannot see, so the output says not just "we were wrong here" but
"we were wrong here, and these positions have a pattern": material balance
against the judge's verdict, whether our side has the safer king, whether
pieces are developed, whether a passed pawn is running, how open the position
is. The material-versus-verdict split is the one that matters most - a
position where we are a piece up and lost is the purest example of an
evaluation that counts wood.
"""

import argparse
import collections
import os
import sys

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import engine as engines
import panel

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
          chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def material(board, colour):
    return sum(VALUES[p] * len(board.pieces(p, colour)) for p in VALUES)


def king_ring_pressure(board, colour):
    """How many enemy pieces attack the squares around a king."""
    square = board.king(colour)
    if square is None:
        return 0
    ring = chess.SquareSet(chess.BB_KING_ATTACKS[square])
    return sum(1 for s in ring if board.is_attacked_by(not colour, s))


def describe(board):
    """Features a material-and-squares evaluation is blind to."""
    us = board.turn
    them = not us
    out = {}
    out["material"] = material(board, us) - material(board, them)
    out["king pressure"] = (king_ring_pressure(board, us)
                            - king_ring_pressure(board, them))
    out["mobility"] = len(list(board.legal_moves))
    back_rank_us = chess.BB_RANK_1 if us == chess.WHITE else chess.BB_RANK_8
    minors = list(board.pieces(chess.KNIGHT, us)) + list(board.pieces(chess.BISHOP, us))
    out["undeveloped"] = sum(1 for s in minors if chess.BB_SQUARES[s] & back_rank_us)
    passers = 0
    for colour, sign in ((us, 1), (them, -1)):
        for square in board.pieces(chess.PAWN, colour):
            file = chess.square_file(square)
            ahead = range(chess.square_rank(square) + 1, 8) if colour == chess.WHITE \
                else range(0, chess.square_rank(square))
            blocked = False
            for rank in ahead:
                for adj in (file - 1, file, file + 1):
                    if 0 <= adj <= 7:
                        piece = board.piece_at(chess.square(adj, rank))
                        if piece and piece.piece_type == chess.PAWN and piece.color != colour:
                            blocked = True
            if not blocked:
                passers += sign
    out["passed pawns"] = passers
    out["pieces"] = len(board.piece_map())
    return out


def our_eval(engine, net, fen):
    import subprocess
    result = subprocess.check_output([engine, "nnue", net] + fen.split())
    return int(result.decode("ascii").strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default="net/machete.nnue")
    parser.add_argument("--judge", default="Koivisto")
    parser.add_argument("--nodes", type=int, default=400000)
    parser.add_argument("--player", default="machete")
    parser.add_argument("--max-games", type=int, default=30)
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    judge = panel.open_engine(args.judge)
    engine = os.path.abspath(args.engine)
    net = os.path.abspath(args.net)

    found = []
    scanned = 0
    try:
        with open(args.pgn) as handle:
            for _ in range(args.max_games):
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                white = args.player.lower() in game.headers.get("White", "").lower()
                black = args.player.lower() in game.headers.get("Black", "").lower()
                if not (white or black):
                    continue
                ours = chess.WHITE if white else chess.BLACK
                board = game.board()
                for move in game.mainline_moves():
                    if board.turn != ours or board.is_game_over():
                        board.push(move)
                        continue
                    fen = board.fen()
                    info = judge.analyse(board, chess.engine.Limit(nodes=args.nodes))
                    theirs = info["score"].pov(board.turn).score(mate_score=10000)
                    mine = our_eval(engine, net, fen)
                    found.append((abs(mine - theirs), mine, theirs, fen, describe(board)))
                    scanned += 1
                    sys.stdout.write("\r{} positions".format(scanned))
                    sys.stdout.flush()
                    board.push(move)
    finally:
        panel.quiet_quit(judge)

    if not found:
        print("\nno positions found for {}".format(args.player))
        return 1
    found.sort(reverse=True, key=lambda row: row[0])
    worst = found[:max(args.show, len(found) // 5)]

    print("\n\n{} positions scanned, median disagreement {} cp".format(
        scanned, sorted(r[0] for r in found)[len(found) // 2]))

    print("\nthe {} worst disagreements, and what is on the board:".format(args.show))
    for gap, mine, theirs, fen, feats in worst[:args.show]:
        print("  we say {:+5}  {} says {:+5}  (off by {})".format(mine, args.judge, theirs, gap))
        print("     material {:+4}  king pressure {:+3}  passers {:+2}  undeveloped {}  pieces {}"
              .format(feats["material"], feats["king pressure"], feats["passed pawns"],
                      feats["undeveloped"], feats["pieces"]))
        print("     {}".format(fen))

    # what separates the worst disagreements from the rest
    rest = found[len(worst):]
    print("\nworst fifth vs the rest, average of each feature:")
    print("  {:<16} {:>10} {:>10}".format("", "worst", "rest"))
    for key in ("material", "king pressure", "passed pawns", "undeveloped", "mobility", "pieces"):
        a = sum(r[4][key] for r in worst) / max(1, len(worst))
        b = sum(r[4][key] for r in rest) / max(1, len(rest))
        print("  {:<16} {:>10.2f} {:>10.2f}".format(key, a, b))

    # the sharpest question: do we count material and call it an evaluation?
    deceived = [r for r in worst if r[4]["material"] >= 300 and r[2] <= -100]
    deceived += [r for r in worst if r[4]["material"] <= -300 and r[2] >= 100]
    print("\n{} of the {} worst are positions where material points one way and "
          "{} says the other".format(len(deceived), len(worst), args.judge))
    return 0


if __name__ == "__main__":
    sys.exit(main())
