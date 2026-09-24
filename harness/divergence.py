"""Where two builds choose different moves, and which choice was better.

    python harness/divergence.py OLD NEW GAMES.pgn [--depth 10] [--workers 4]

An SPRT measures a change by playing games, and for a change that only acts in
rare positions most of those games are the same game played twice: 2820 games
of the mate fix gave -6.6 +/- 9.5 Elo and still had not decided. This measures
the change where it acts. Both builds search the same positions at a fixed
depth - deterministic, with an empty hash each time - and every position where
their moves differ is judged by Stockfish: what each move is worth, from the
mover's side.

--only-mates keeps the work proportionate for the mate fix: at a fixed depth
the two builds can only differ where the old one saw a mate score, because
that is the only place its search stopped differently. The old build searches
every position; the new one only those.
"""

import argparse
import multiprocessing
import os
import random
import sys

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import engine as engines
import panel

MATE_CP = 3000


def open_machete(binary, net):
    e = chess.engine.SimpleEngine.popen_uci(binary)
    e.configure({"EvalFile": net})
    engines.pin(e, 64)
    return e


def value(info, colour):
    return info["score"].pov(colour).score(mate_score=MATE_CP)


def compare(job):
    """One chunk of positions: returns the divergent ones, judged."""
    fens, old_path, new_path, net, depth, only_mates, judge_nodes = job
    old = open_machete(old_path, net)
    new = open_machete(new_path, net)
    judge = None
    found = []
    searched = 0
    try:
        for fen in fens:
            board = chess.Board(fen)
            limit = chess.engine.Limit(depth=depth)
            a = old.analyse(board, limit, game=object())
            if only_mates and not a["score"].is_mate():
                continue
            searched += 1
            b = new.analyse(board, limit, game=object())
            move_a, move_b = a["pv"][0], b["pv"][0]
            if move_a == move_b:
                continue
            if judge is None:
                judge = panel.open_engine("Stockfish", 64)
            worth = {}
            for name, move in (("old", move_a), ("new", move_b)):
                after = board.copy()
                after.push(move)
                if after.is_checkmate():
                    worth[name] = MATE_CP
                elif after.is_game_over():
                    worth[name] = 0
                else:
                    worth[name] = -value(judge.analyse(after, chess.engine.Limit(nodes=judge_nodes)),
                                         after.turn)
            found.append({"fen": fen, "old": board.san(move_a), "new": board.san(move_b),
                          "old_score": value(a, board.turn), "new_score": value(b, board.turn),
                          "old_worth": worth["old"], "new_worth": worth["new"]})
    finally:
        for e in (old, new, judge):
            engines.shutdown(e)
    return searched, found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("pgn")
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--positions", type=int, default=40000)
    parser.add_argument("--only-mates", action="store_true")
    parser.add_argument("--judge-nodes", type=int, default=300000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    fens = []
    with open(args.pgn, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            for move in game.mainline_moves():
                fens.append(board.fen())
                board.push(move)
    random.Random(args.seed).shuffle(fens)
    fens = fens[:args.positions]
    chunks = [fens[i::args.workers * 8] for i in range(args.workers * 8)]
    jobs = [(c, os.path.abspath(args.old), os.path.abspath(args.new), os.path.abspath(args.net),
             args.depth, args.only_mates, args.judge_nodes) for c in chunks]
    print("{} positions, depth {}{}".format(len(fens), args.depth,
                                            ", new build only where the old saw a mate" if args.only_mates else ""))
    sys.stdout.flush()

    searched = 0
    found = []
    with multiprocessing.Pool(args.workers) as pool:
        for done, (n, rows) in enumerate(pool.imap_unordered(compare, jobs), 1):
            searched += n
            found.extend(rows)
            sys.stdout.write("\r{} of {} chunks, {} searched by both, {} differ".format(
                done, len(jobs), searched, len(found)))
            sys.stdout.flush()

    better = [r for r in found if r["new_worth"] > r["old_worth"] + 20]
    worse = [r for r in found if r["new_worth"] < r["old_worth"] - 20]
    print("\n\n{} positions searched by both builds; the moves differ in {}".format(searched, len(found)))
    print("  new build's move better by 20+ cp: {}".format(len(better)))
    print("  new build's move worse by 20+ cp:  {}".format(len(worse)))
    print("  within 20 cp either way:           {}".format(len(found) - len(better) - len(worse)))
    for title, rows in (("worst for the new build", sorted(worse, key=lambda r: r["new_worth"] - r["old_worth"])),
                        ("best for the new build", sorted(better, key=lambda r: r["old_worth"] - r["new_worth"]))):
        if rows:
            print("\n{}:".format(title))
            for r in rows[:8]:
                print("  old {:<7} ({:+5d})  new {:<7} ({:+5d})   {}".format(
                    r["old"], r["old_worth"], r["new"], r["new_worth"], r["fen"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
