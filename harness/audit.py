"""Find machete's mistakes that better training data could fix.

    python harness/audit.py GAMES.pgn --player machete --deep 14 --out data/audit

harness/blunders.py says where the centipawns go. This asks the question that
decides what to do about them. A mistake has one of two causes, and only one of
them is a training problem:

  search      machete misjudged the position at the depth it had, but given
              more depth it finds a good move. The evaluation was right enough;
              the tree was too shallow or pruned the answer away. That is fixed
              in src/search.mach, not with data.
  evaluation  even searched much deeper, machete still prefers the bad move.
              The network values the resulting position wrongly, and no amount
              of search fixes a wrong leaf. That is what training data fixes.

So every move is judged by Stockfish at a fixed node count (the same verdict
however busy the machine is), and every mistake is searched again by machete
itself at --deep, far past what it had in the game. The evaluation mistakes are
then grouped by what the positions have in common - phase, material, who was
winning, king safety, passed pawns - and ranked by the centipawns they cost.

Their positions are written to OUT.epd. gen.py starts 40% of its games from a
book, so that file can point the next corpus at exactly the places the network
is blind.

The groupings are deliberately coarse. They are for deciding where the next
data should come from, not a taxonomy of chess.
"""

import argparse
import collections
import json
import os
import sys

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import blunders
import engine as engines
import panel

MISTAKE = blunders.MISTAKE
NEAR_BEST = 30       # a move within this of Stockfish's best counts as finding it
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def material(board, colour):
    return sum(VALUES[k] * len(board.pieces(k, colour)) for k in VALUES)


def signature(board, ours):
    """'RB v RBN, pawns -1' - our pieces, then theirs, and the pawn difference.

    Pieces are listed but pawns only counted, so positions that differ by a
    pawn's placement land in the same group; listing every pawn made every
    position its own group and the ranking said nothing.
    """
    def side(colour):
        return "".join(chess.piece_symbol(k).upper() * len(board.pieces(k, colour))
                       for k in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)) or "K"
    pawns = len(board.pieces(chess.PAWN, ours)) - len(board.pieces(chess.PAWN, not ours))
    return "{} v {}, pawns {:+d}".format(side(ours), side(not ours), pawns)


def passed_pawns(board, colour):
    count = 0
    for square in board.pieces(chess.PAWN, colour):
        file, rank = chess.square_file(square), chess.square_rank(square)
        ahead = range(rank + 1, 8) if colour == chess.WHITE else range(0, rank)
        blocked = False
        for f in (file - 1, file, file + 1):
            if 0 <= f <= 7 and any(board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, not colour)
                                    for r in ahead):
                blocked = True
                break
        count += 0 if blocked else 1
    return count


def king_pressure(board, colour):
    """Enemy attacks on the squares around this side's king."""
    king = board.king(colour)
    if king is None:
        return 0
    return sum(len(board.attackers(not colour, sq)) for sq in chess.SquareSet(chess.BB_KING_ATTACKS[king]))


def band(score):
    if score >= 200:
        return "winning"
    if score <= -200:
        return "losing"
    return "level"


def features(board, ours, before):
    diff = material(board, ours) - material(board, not ours)
    return {
        "phase": blunders.phase_of(board),
        "standing": band(before),
        "material": "ahead" if diff >= 2 else ("behind" if diff <= -2 else "even"),
        "signature": signature(board, ours),
        "our king under pressure": "yes" if king_pressure(board, ours) >= 6 else "no",
        "passed pawns (ours-theirs)": "{}-{}".format(passed_pawns(board, ours), passed_pawns(board, not ours)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn", nargs="+")
    parser.add_argument("--player", default="machete", help="whose moves to judge (exact name)")
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--judge-nodes", type=int, default=300000)
    parser.add_argument("--deep", type=int, default=14, help="depth for machete's second look")
    parser.add_argument("--max-games", type=int, default=0)
    parser.add_argument("--out", default="data/audit")
    args = parser.parse_args()

    judge = panel.open_engine("Stockfish", 128)
    ours_engine = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.engine))
    ours_engine.configure({"EvalFile": os.path.abspath(args.net)})
    judge_limit = chess.engine.Limit(nodes=args.judge_nodes)
    deep_limit = chess.engine.Limit(depth=args.deep)

    mistakes = []
    games = judged = 0
    results = collections.Counter()
    try:
        for path in args.pgn:
            with open(path, encoding="utf-8", errors="replace") as handle:
                while not args.max_games or games < args.max_games:
                    game = chess.pgn.read_game(handle)
                    if game is None:
                        break
                    white = game.headers.get("White") == args.player
                    black = game.headers.get("Black") == args.player
                    if white == black:
                        continue
                    games += 1
                    ours = chess.WHITE if white else chess.BLACK
                    result = game.headers.get("Result", "*")
                    results["won" if result == ("1-0" if white else "0-1")
                            else "drew" if result == "1/2-1/2" else "lost"] += 1
                    board = game.board()
                    for move in game.mainline_moves():
                        if board.turn != ours:
                            board.push(move)
                            continue
                        info = judge.analyse(board, judge_limit)
                        before = blunders.score_of(info, ours)
                        best = info.get("pv", [None])[0]
                        after_board = board.copy()
                        after_board.push(move)
                        if after_board.is_game_over():
                            board.push(move)
                            continue
                        after = blunders.score_of(judge.analyse(after_board, judge_limit), ours)
                        drop = before - after
                        judged += 1
                        if drop >= MISTAKE and move != best:
                            deep = ours_engine.play(board, deep_limit, info=chess.engine.INFO_SCORE)
                            second = deep.move
                            if second == move:
                                cause = "evaluation"
                            elif second == best:
                                cause = "search"
                            else:
                                probe = board.copy()
                                probe.push(second)
                                value = blunders.score_of(judge.analyse(probe, judge_limit), ours)
                                cause = "search" if before - value <= NEAR_BEST else "evaluation"
                            entry = {"fen": board.fen(), "played": board.san(move),
                                     "best": board.san(best) if best else "?",
                                     "deep": board.san(second), "drop": drop, "before": before,
                                     "cause": cause, "kind": blunders.kind_of(board, move, drop),
                                     "game": "{} - {}".format(game.headers.get("White"), game.headers.get("Black"))}
                            entry.update(features(board, ours, before))
                            mistakes.append(entry)
                        board.push(move)
                        sys.stdout.write("\r{} games, {} moves judged, {} mistakes".format(
                            games, judged, len(mistakes)))
                        sys.stdout.flush()
    finally:
        engines.shutdown(judge)
        engines.shutdown(ours_engine)

    print("\n\n{} games ({} won, {} drawn, {} lost), {} of machete's moves judged".format(
        games, results["won"], results["drew"], results["lost"], judged))
    if not mistakes:
        print("no mistakes of {} cp or more".format(MISTAKE))
        return 0

    by_cause = collections.Counter()
    for m in mistakes:
        by_cause[m["cause"]] += m["drop"]
    total = sum(by_cause.values())
    print("\n{} mistakes of {}+ cp, {} cp lost in all:".format(len(mistakes), MISTAKE, total))
    for cause in ("evaluation", "search"):
        count = sum(1 for m in mistakes if m["cause"] == cause)
        print("  {:<11} {:>4} mistakes  {:>7} cp  ({:.0%})".format(
            cause, count, by_cause[cause], by_cause[cause] / float(total)))

    blind = [m for m in mistakes if m["cause"] == "evaluation"]
    for key in ("phase", "standing", "material", "our king under pressure", "passed pawns (ours-theirs)", "kind", "signature"):
        groups = collections.Counter()
        counts = collections.Counter()
        for m in blind:
            groups[m[key]] += m["drop"]
            counts[m[key]] += 1
        print("\nevaluation mistakes by {}:".format(key))
        for value, lost in groups.most_common(8):
            print("  {:<22} {:>4} mistakes  {:>7} cp".format(value, counts[value], lost))

    print("\nworst evaluation mistakes:")
    for m in sorted(blind, key=lambda m: -m["drop"])[:10]:
        print("  -{:>4} cp  played {:<7} best {:<7} deep {:<7} {:<10} {}".format(
            m["drop"], m["played"], m["best"], m["deep"], m["signature"], m["fen"]))

    folder = os.path.dirname(os.path.abspath(args.out))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(args.out + ".json", "w") as handle:
        json.dump(mistakes, handle, indent=1)
    with open(args.out + ".epd", "w", newline="\n") as handle:
        handle.write("# positions where machete's evaluation, not its search, chose a losing move\n")
        for m in blind:
            handle.write(m["fen"] + "\n")
    print("\n{} evaluation blind spots written to {}.epd, every mistake to {}.json".format(
        len(blind), args.out, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
