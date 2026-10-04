"""Deep forced mates, built backwards from random checkmates.

    python harness/nnue/mate_retro.py --out E:/machete/mates/retro.jsonl [--target 24] [--beam 6]
        [--tries 40] [--base-nodes 300000] [--max-nodes 40000000] [--seeds 0] [--seed 1]

One seed at a time:

  1. A random checkmate. Pieces are scattered at random (from three men to a
     full board), and a position is kept when it is legal and the side to
     move can give mate; that mating move is played. The side that is mated
     is the defender, the other the attacker.
  2. A reverse search from it. A position's predecessors are found by taking
     back a move (including taking back captures and promotions; castling
     and en passant are not taken back). Level d holds positions with a
     forced mate in d plies; level d+1 is built from their predecessors.
  3. Every predecessor is proved by Stockfish before it is kept. Taking back
     an attacker's move always leaves a forced mate (that move is one), but
     maybe a shorter one exists. Taking back a defender's move leaves a
     forced mate only if every other defender move also loses, which only a
     search can tell. So a predecessor of a mate in d is kept when Stockfish
     reports a forced mate in exactly d+1 plies; otherwise it is dropped.

The breadth is capped (--beam positions a level, --tries predecessors tried
for each), so this is a sampled reverse search, not the whole tree: the whole
tree at 24 plies is far beyond any machine. Defender predecessors with the
fewest legal moves are tried first, since those are the likeliest to be
forced. The node budget for a proof grows with the distance.

Every proved position is appended to --out as one JSON line: the FEN, the
mate distance in plies, the attacker, the first move and line Stockfish
gives, the nodes of the proof, the seed's checkmate and its parent. A mate
score from Stockfish is a proof that the mate exists in at most that many
moves; that no shorter one exists is as sure as its search to that budget.

Runs until stopped (or --seeds seeds), resumable: it only appends.
"""
import argparse
import json
import os
import random
import sys
import time

import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

# a normal army: taking back captures and promotions never makes more than this,
# so no position has three queens or nine pawns
LIMIT = {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}


def random_mate(rng):
    """A random legal position in which the side to move is checkmated."""
    while True:
        men = rng.choice([3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32])
        board = chess.Board(None)
        squares = rng.sample(range(64), men)
        board.set_piece_at(squares[0], chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(squares[1], chess.Piece(chess.KING, chess.BLACK))
        count = {chess.WHITE: dict.fromkeys(LIMIT, 0), chess.BLACK: dict.fromkeys(LIMIT, 0)}
        ok = True
        for sq in squares[2:]:
            colour = rng.choice([chess.WHITE, chess.BLACK])
            kind = rng.choices([chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN], weights=[8, 2, 2, 2, 1])[0]
            if kind == chess.PAWN and chess.square_rank(sq) in (0, 7):
                kind = rng.choice([chess.KNIGHT, chess.BISHOP, chess.ROOK])
            if count[colour][kind] >= LIMIT[kind] or sum(count[colour].values()) >= 15:
                ok = False
                break
            count[colour][kind] += 1
            board.set_piece_at(sq, chess.Piece(kind, colour))
        if not ok:
            continue
        board.turn = rng.choice([chess.WHITE, chess.BLACK])
        if not board.is_valid() or board.is_game_over():
            continue
        mates = []
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                mates.append(move)
            board.pop()
        if mates:
            board.push(rng.choice(mates))
            return chess.Board(board.fen())  # no move stack: a position, not a game


def predecessors(board):
    """Positions from which one legal move by the side not to move reaches `board`."""
    mover = not board.turn
    other = board.turn
    out = []
    occupied = board.occupied
    counts = {k: len(board.pieces(k, other)) for k in LIMIT}
    men = sum(counts.values())
    for to in chess.SquareSet(board.occupied_co[mover]):
        piece = board.piece_at(to)
        kinds = [(piece.piece_type, False)]
        last = 7 if mover == chess.WHITE else 0
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) and chess.square_rank(to) == last:
            if len(board.pieces(chess.PAWN, mover)) < LIMIT[chess.PAWN]:
                kinds.append((chess.PAWN, True))  # the piece was promoted on this move
        for was, promoted in kinds:
            froms = []  # (from square, the move was a capture)
            if was == chess.PAWN:
                step = -8 if mover == chess.WHITE else 8
                f = to + step
                if 0 <= f < 64 and not occupied & chess.BB_SQUARES[f] and chess.square_rank(f) not in (0, 7):
                    froms.append((f, False))
                    start = 1 if mover == chess.WHITE else 6
                    f2 = f + step
                    if not promoted and 0 <= f2 < 64 and chess.square_rank(f2) == start and not occupied & chess.BB_SQUARES[f2]:
                        froms.append((f2, False))
                for df in (-1, 1):
                    file = chess.square_file(to) + df
                    f = to + step + df
                    if 0 <= file < 8 and 0 <= f < 64 and chess.square_file(f) == file and not occupied & chess.BB_SQUARES[f] \
                            and chess.square_rank(f) not in (0, 7):
                        froms.append((f, True))
            else:
                reach = chess.SquareSet(board.attacks_mask(to) & ~occupied)
                for f in reach:
                    froms.append((f, False))
                    froms.append((f, True))
            for f, capture in froms:
                victims = [None]
                if capture:
                    victims = [k for k in LIMIT if counts[k] < LIMIT[k] and men < 15
                               and not (k == chess.PAWN and chess.square_rank(to) in (0, 7))]
                elif was == chess.PAWN and chess.square_file(f) != chess.square_file(to):
                    continue
                for victim in victims:
                    if capture and victim is None:
                        continue
                    prev = board.copy(stack=False)
                    prev.remove_piece_at(to)
                    prev.set_piece_at(f, chess.Piece(was, mover))
                    if victim:
                        prev.set_piece_at(to, chess.Piece(victim, other))
                    prev.turn = mover
                    prev.castling_rights = chess.BB_EMPTY
                    prev.ep_square = None
                    prev.halfmove_clock = 0
                    if not prev.is_valid():
                        continue
                    move = chess.Move(f, to, promotion=piece.piece_type if promoted else None)
                    if move not in prev.legal_moves:
                        continue
                    prev.push(move)
                    same = prev.board_fen() == board.board_fen()
                    prev.pop()
                    if same:
                        out.append(chess.Board(prev.fen()))
    return out


def plies_of(score, board):
    """The forced mate's length in plies for the position, or None; and who mates."""
    pov = score.pov(board.turn)
    if not pov.is_mate():
        return None, None
    n = pov.mate()
    if n > 0:
        return 2 * n - 1, board.turn
    return -2 * n, not board.turn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--target", type=int, default=24, help="stop growing a seed at this many plies")
    parser.add_argument("--beam", type=int, default=6, help="positions kept per level")
    parser.add_argument("--tries", type=int, default=40, help="predecessors proved per position")
    parser.add_argument("--base-nodes", type=int, default=300000)
    parser.add_argument("--max-nodes", type=int, default=40000000)
    parser.add_argument("--seeds", type=int, default=0, help="0 runs until stopped")
    parser.add_argument("--seed", type=int, default=0, help="0 seeds from the clock")
    parser.add_argument("--hash", type=int, default=512)
    args = parser.parse_args()
    rng = random.Random(args.seed or time.time_ns())
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sf = panel.open_engine("Stockfish", args.hash)
    done = 0
    while not args.seeds or done < args.seeds:
        done += 1
        mate = random_mate(rng)
        attacker = not mate.turn
        seed_id = "%x" % rng.getrandbits(48)
        level = [mate]
        best = 0
        started = time.time()
        kept_total = 0
        for d in range(0, args.target):
            nodes = min(args.max_nodes, int(args.base_nodes * 1.32 ** d))
            found = {}
            for position in level:
                cands = predecessors(position)
                rng.shuffle(cands)
                # when the defender is to move in the predecessor: fewest legal moves first
                cands.sort(key=lambda b: b.legal_moves.count() if b.turn != attacker else 0)
                proved = 0
                for prev in cands[:args.tries]:
                    key = prev.epd()
                    if key in found:
                        continue
                    info = sf.analyse(prev, chess.engine.Limit(nodes=nodes))
                    plies, who = plies_of(info["score"], prev)
                    if plies != d + 1 or who != attacker:
                        continue
                    pv = info.get("pv", [])
                    found[key] = prev
                    proved += 1
                    with open(args.out, "a", encoding="utf-8") as out:
                        out.write(json.dumps(dict(
                            fen=prev.fen(), plies=plies, attacker="white" if attacker else "black",
                            move=prev.san(pv[0]) if pv else None, pv=prev.variation_san(pv) if pv else None,
                            nodes=info.get("nodes"), depth=info.get("depth"), men=len(prev.piece_map()),
                            seed=seed_id, mate=mate.fen(), parent=position.fen(), teacher="Stockfish 19")) + "\n")
                    kept_total += 1
                    if len(found) >= args.beam * 3:
                        break
                if len(found) >= args.beam * 3:
                    break
            if not found:
                break
            best = d + 1
            level = rng.sample(list(found.values()), min(args.beam, len(found)))
        print("%s seed %s: %2d men, grew to %2d plies, %3d positions, %.0f s" % (
            time.strftime("%m-%d %H:%M"), seed_id, len(mate.piece_map()), best, kept_total, time.time() - started), flush=True)
    panel.quiet_quit(sf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
