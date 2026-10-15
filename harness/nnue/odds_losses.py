"""Where the odds-trained net loses: Stockfish grades every move it played.

    py -3.7 harness/nnue/odds_losses.py data/games_match.pgn --side odds_sf \
        --against v036,c33 --nodes 200000 --workers 8 --out E:/machete/claude/odds_losses.json

For each of the side's moves, Stockfish scores the position before the move
(its best line) and after the move it played, both from the side's point of
view. A drop of --blunder centipawns or more is a blunder. Each blunder is
tagged with what the game shows next:

  phase      opening (< 16 men moved off... ply < 30), middlegame, endgame
             by men on the board
  balance    material before the move, side minus opponent, in pawns
  lost       material the side is down six plies later relative to before,
             in pawns (what the blunder actually cost on the board)
  kind       hang      - lost material without compensation within 6 plies
             king      - mated or a mating attack (SF mate score after)
             positional- drop without material moving

The blunder positions are written as FENs, side to move = the side, so a
generator can seed games from them.
"""

import argparse
import collections
import json
import multiprocessing
import os
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
CLAMP = 3000


def material(board, colour):
    return sum(VALUES.get(p.piece_type, 0) * (1 if p.color == colour else -1)
               for p in board.piece_map().values())


def men(board):
    return len(board.piece_map())


def pov(score, colour):
    s = score.pov(colour)
    if s.is_mate():
        return CLAMP if s.mate() > 0 else -CLAMP
    return max(-CLAMP, min(CLAMP, s.score()))


def games_of(path, side, against):
    out = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            w, b = game.headers.get("White"), game.headers.get("Black")
            if side not in (w, b):
                continue
            other = b if w == side else w
            if other not in against:
                continue
            colour = chess.WHITE if w == side else chess.BLACK
            result = game.headers.get("Result")
            lost = (result == "0-1" and colour == chess.WHITE) or (result == "1-0" and colour == chess.BLACK)
            if not lost:
                continue
            out.append((str(game), colour))
    return out


def grade(job):
    text, colour, nodes, threshold = job
    import io
    game = chess.pgn.read_game(io.StringIO(text))
    engine = panel.open_engine("Stockfish", 64)
    try:
        board = game.board()
        moves = list(game.mainline_moves())
        limit = chess.engine.Limit(nodes=nodes)
        rows = []
        first = None
        for i, move in enumerate(moves):
            if board.turn != colour:
                board.push(move)
                continue
            before = pov(engine.analyse(board, limit)["score"], colour)
            fen = board.fen()
            mat_before = material(board, colour)
            n_men = men(board)
            ply = board.ply()
            board.push(move)
            after = pov(engine.analyse(board, limit)["score"], colour)
            drop = before - after
            if drop >= threshold and before > -600:
                # material six plies on in the actual game
                probe = board.copy()
                for m in moves[i + 1:i + 7]:
                    probe.push(m)
                lost_pawns = mat_before - material(probe, colour)
                if after <= -CLAMP + 1:
                    kind = "king"
                elif lost_pawns >= 2:
                    kind = "hang"
                else:
                    kind = "positional"
                phase = "opening" if ply < 30 else ("endgame" if n_men <= 12 else "middlegame")
                row = {"fen": fen, "move": move.uci(), "before": before, "after": after,
                       "drop": drop, "ply": ply, "men": n_men, "balance": mat_before,
                       "lost": lost_pawns, "kind": kind, "phase": phase}
                rows.append(row)
                if first is None:
                    first = row
        return {"first": first, "blunders": rows, "plies": len(moves)}
    finally:
        panel.quiet_quit(engine)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--side", default="odds_sf")
    parser.add_argument("--against", default="v036,c33")
    parser.add_argument("--nodes", type=int, default=200000)
    parser.add_argument("--blunder", type=int, default=150)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    games = games_of(args.pgn, args.side, set(args.against.split(",")))
    print("{} lost games for {}".format(len(games), args.side))
    jobs = [(t, c, args.nodes, args.blunder) for t, c in games]
    with multiprocessing.Pool(args.workers) as pool:
        results = pool.map(grade, jobs)

    firsts = [r["first"] for r in results if r["first"]]
    every = [b for r in results for b in r["blunders"]]
    print("games with a blunder: {}/{}".format(len(firsts), len(results)))
    print("blunders in all: {}  (per game {:.1f})".format(len(every), len(every) / max(1, len(results))))

    def table(rows, key):
        c = collections.Counter(r[key] for r in rows)
        return ", ".join("{} {}".format(k, v) for k, v in c.most_common())

    for label, rows in (("first blunder", firsts), ("every blunder", every)):
        print("\n" + label)
        print("  kind   :", table(rows, "kind"))
        print("  phase  :", table(rows, "phase"))
        bal = collections.Counter("even" if abs(r["balance"]) <= 1 else ("up" if r["balance"] > 1 else "down")
                                  for r in rows)
        print("  balance:", ", ".join("{} {}".format(k, v) for k, v in bal.most_common()))
        if rows:
            plies = sorted(r["ply"] for r in rows)
            print("  ply    : median {}  p25 {}  p75 {}".format(
                plies[len(plies) // 2], plies[len(plies) // 4], plies[3 * len(plies) // 4]))
            lost = sorted(r["lost"] for r in rows)
            print("  pawns lost after 6 plies: median {}".format(lost[len(lost) // 2]))

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"firsts": firsts, "every": every}, handle, indent=1)
        print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
