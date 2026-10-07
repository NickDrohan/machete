"""Moves our network wants and should not: the temptation ledger and the chunk to forget them with.

    python harness/rl/temptations.py run    --dir E:/machete/rl-classical [--workers 6] [--limit 0]
    python harness/rl/temptations.py test   --dir E:/machete/rl-classical --net NAME=PATH [--net ...]
    python harness/rl/temptations.py report --dir E:/machete/rl-classical

The owner's principle: learning is forgetting the moves you should not make.
A temptation is a move that is all three of

  wanted   among the network's own top three (schemas.py's rank.jsonl: the move
           it played and its two best others), scored by it within CLOSE
           centipawns of its favourite, and not the panel's best move: the
           third-best of a forced recapture is in the top three and wanted by nobody;
  wrong    the panel scores the position after it at least LOSS centipawns
           below the position after the best move;
  rosy     the network's own score for it is at least LOSS centipawns above the
           panel's: it does not see what is wrong with it.

So a weak move the network knew was weak is not a temptation, and neither is
one it rated a little too well. Checking costs a panel search of two more
positions, so Stockfish alone looks first and the whole panel is asked only
when Stockfish already sees LOSS centipawns between the two moves.

Each temptation is tagged with what made it attractive, from the board alone
(TAGS below), and written to temptations.jsonl. One in ten, by a hash of the
position, is held out as the temptation test and never trained on. The rest
go to forget.bin in the trainer's record format, two records each: the
position after the tempting move and the position after the best move, both
with the panel's score. `test` asks a network for its first instinct (depth 1)
on the held-out positions and counts how often it still takes the bait.
`report` prints the ledger by tag and appends it to temptation_density.tsv.
"""
import argparse
import collections
import hashlib
import json
import multiprocessing
import os
import sys
import time

import chess
import chess.engine
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "nnue"))
import attack_detector  # noqa: E402
import gen  # noqa: E402  (encode, RECORD)
import instinct  # noqa: E402
import panel  # noqa: E402
import panel_label  # noqa: E402
import schemas  # noqa: E402

LOSS = 80
CLOSE = 50
NODES = 100000
TAGS = ("wins material", "check", "king attack", "pawn advance", "early queen", "trade", "king walk", "undeveloped", "quiet")
VALUE = schemas.VALUE


def held_out(fen):
    return hashlib.sha1(panel_label.position_key(fen).encode()).digest()[0] % 10 == 0


def tags_of(board, move):
    """What could make this move look good, read off the board."""
    tags = []
    piece = board.piece_type_at(move.from_square)
    if board.is_capture(move):
        victim = board.piece_type_at(move.to_square) or chess.PAWN
        if VALUE[victim - 1] > VALUE[piece - 1] or not board.is_attacked_by(not board.turn, move.to_square):
            tags.append("wins material")
        elif abs(VALUE[victim - 1] - VALUE[piece - 1]) <= 30:
            tags.append("trade")
    if board.gives_check(move):
        tags.append("check")
    else:
        board.push(move)
        mine = schemas.flipped(board)
        board.pop()
        if mine is not None and attack_detector.features(mine)[0] > attack_detector.features(board)[0]:
            tags.append("king attack")  # more pressure on their king than before the move
    if piece == chess.PAWN and not board.is_capture(move):
        tags.append("pawn advance")
    if piece == chess.QUEEN and board.fullmove_number <= 12:
        tags.append("early queen")
    if piece == chess.KING and not board.is_castling(move) and chess.popcount(board.occupied) >= 14:
        tags.append("king walk")
    home = chess.BB_RANK_1 if board.turn else chess.BB_RANK_8
    minors = (board.knights | board.bishops) & board.occupied_co[board.turn] & home
    if board.fullmove_number <= 15 and chess.popcount(minors) >= 2 and not (chess.BB_SQUARES[move.from_square] & minors) and not board.is_castling(move):
        tags.append("undeveloped")
    return tags or ["quiet"]


def child_score(engine, board, move, limit):
    """The score of the position after move, from the side that moved; None if the engine fails."""
    board.push(move)
    try:
        if board.is_checkmate():
            return panel_label.CLAMP
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        return -panel_label.score_of(engine.analyse(board, limit), board.turn)
    except Exception:
        return None
    finally:
        board.pop()


def panel_child(engines, board, move, limit):
    board.push(move)
    try:
        if board.is_checkmate():
            return panel_label.CLAMP
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        scores = []
        for name in panel_label.TEACHERS:
            answer = panel_label.ask(engines, name, board, limit)
            if answer:
                scores.append(-answer[1])
        return panel_label.pooled(scores) if len(scores) >= panel_label.AGREE + 1 else None
    finally:
        board.pop()


def worker(tasks, results):
    panel_label.below_normal()
    engines = {}
    limit = chess.engine.Limit(nodes=NODES)
    while True:
        task = tasks.get()
        if task is None:
            break
        board = chess.Board(task["fen"])
        best = chess.Move.from_uci(task["best"])
        found = []
        if "Stockfish" not in engines:
            engines["Stockfish"] = panel.open_engine("Stockfish", 32)
        sf_best = child_score(engines["Stockfish"], board, best, limit)
        panel_best = None
        for uci, own in task["wanted"]:
            move = chess.Move.from_uci(uci)
            sf = child_score(engines["Stockfish"], board, move, limit)
            if sf is None or sf_best is None or sf_best - sf < LOSS:
                continue
            if panel_best is None:
                panel_best = panel_child(engines, board, best, limit)
            verdict = panel_child(engines, board, move, limit)
            if panel_best is None or verdict is None:
                continue
            if panel_best - verdict >= LOSS and own - verdict >= LOSS:
                found.append(dict(fen=task["fen"], move=uci, best=task["best"], own=own, panel=verdict, panel_best=panel_best,
                                  played=uci == task["move"], tags=tags_of(board, move), test=held_out(task["fen"]),
                                  men=chess.popcount(board.occupied)))
        results.put(dict(fen=task["fen"], found=found, checked=len(task["wanted"])))
    for engine in engines.values():
        panel.quiet_quit(engine)


def record(board, move, mover_score):
    """The position after move with the panel's score, as the trainer reads it (from the side to move)."""
    board.push(move)
    row = gen.encode(board, int(max(-2000, min(2000, -mover_score))), 1)
    board.pop()
    return row


def run(args):
    panel_label.below_normal()
    checked_path = os.path.join(args.dir, "temptations_checked.txt")
    checked = set(open(checked_path, encoding="utf-8").read().split("\n")) if os.path.exists(checked_path) else set()
    todo = []
    rank_path = os.path.join(args.dir, "rank.jsonl")
    for line in open(rank_path, encoding="utf-8") if os.path.exists(rank_path) else []:
        r = json.loads(line)
        key = panel_label.position_key(r["fen"])
        if key in checked:
            continue
        own = dict(r["rank"])
        own.update(r["scores"])
        favourite = max(own.values())
        wanted = [(m, own[m]) for m in r["top"] if m != r["best"] and m in own and abs(own[m]) < 1500 and own[m] >= favourite - CLOSE]
        if wanted:
            todo.append(dict(fen=r["fen"], best=r["best"], move=r["move"], wanted=wanted))
        else:
            checked.add(key)
    if args.limit:
        todo = todo[:args.limit]
    print("%d positions with a wanted move that is not the best move" % len(todo), flush=True)
    tasks, results = multiprocessing.Queue(), multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, args=(tasks, results), daemon=True) for _ in range(args.workers)]
    for p in pool:
        p.start()
    for t in todo:
        tasks.put(t)
    for _ in pool:
        tasks.put(None)
    with open(os.path.join(args.dir, "temptations.jsonl"), "a", encoding="utf-8") as ledger, \
            open(os.path.join(args.dir, "forget.bin"), "ab") as chunk:
        for _ in todo:
            out = results.get()
            checked.add(panel_label.position_key(out["fen"]))
            for t in out["found"]:
                ledger.write(json.dumps(t) + "\n")
                if not t["test"]:
                    board = chess.Board(t["fen"])
                    rows = [record(board, chess.Move.from_uci(t["move"]), t["panel"]),
                            record(board, chess.Move.from_uci(t["best"]), t["panel_best"])]
                    chunk.write(np.array(rows, dtype=gen.RECORD).tobytes())
    open(checked_path, "w", encoding="utf-8").write("\n".join(sorted(checked)))
    report(args)


def load(args):
    path = os.path.join(args.dir, "temptations.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []


def report(args):
    rows = load(args)
    checked_path = os.path.join(args.dir, "temptations_checked.txt")
    checked = len(open(checked_path, encoding="utf-8").read().split("\n")) if os.path.exists(checked_path) else 0
    if not rows:
        print("no temptations yet (%d positions checked)" % checked)
        return
    positions = len({panel_label.position_key(r["fen"]) for r in rows})
    by_tag = collections.Counter(t for r in rows for t in r["tags"])
    played = sum(r["played"] for r in rows)
    lines = ["%d positions checked; %d temptations in %d of them (%.1f%%); %d were the move actually played" % (
        checked, len(rows), positions, 100 * positions / max(1, checked), played),
        "%d held out as the test, %d in forget.bin (two records each)" % (sum(r["test"] for r in rows), sum(not r["test"] for r in rows)),
        "mean overrating: our score %.0f cp above the panel's; mean cost of the move %.0f cp" % (
            np.mean([r["own"] - r["panel"] for r in rows]), np.mean([r["panel_best"] - r["panel"] for r in rows])), "",
        "%-16s %7s %7s" % ("what made it juicy", "count", "share")]
    for tag in sorted(TAGS, key=lambda t: -by_tag[t]):
        lines.append("%-16s %7d %6.1f%%" % (tag, by_tag[tag], 100 * by_tag[tag] / len(rows)))
    phases = collections.Counter("opening" if r["men"] >= 26 else "middlegame" if r["men"] >= 14 else "endgame" for r in rows)
    lines += ["", "by phase: " + ", ".join("%s %d" % kv for kv in phases.most_common())]
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.dir, "temptations.txt"), "w", encoding="utf-8").write(text + "\n")
    path = os.path.join(args.dir, "temptation_density.tsv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("when\tchecked\ttemptations\t" + "\t".join(TAGS) + "\n")
        f.write("%s\t%d\t%d\t%s\n" % (time.strftime("%Y-%m-%d %H:%M"), checked, len(rows), "\t".join(str(by_tag[t]) for t in TAGS)))


def test(args):
    rows = [r for r in load(args) if r["test"]]
    if not rows:
        print("no held-out temptations yet")
        return
    limit = chess.engine.Limit(depth=1)
    lines = ["%d held-out temptations: how often a network's first instinct is the tempting move, or the best move" % len(rows)]
    for spec in args.net:
        name, path = spec.split("=", 1)
        engine = instinct.open_net(path)
        bait = good = 0
        for r in rows:
            move = instinct.first_move(engine, chess.Board(r["fen"]), limit)
            bait += move == r["move"]
            good += move == r["best"]
        engine.quit()
        lines.append("%-16s takes the bait %5.1f%%   finds the best move %5.1f%%" % (name, 100 * bait / len(rows), 100 * good / len(rows)))
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.dir, "temptation_test.txt"), "a", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M\n") + text + "\n\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "test", "report"])
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--net", action="append", default=[], help="test: NAME=PATH")
    args = parser.parse_args()
    dict(run=run, test=test, report=report)[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
