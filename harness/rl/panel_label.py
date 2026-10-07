"""What the teacher panel says of every position the league played: its best move and its score.

    python harness/rl/panel_label.py --dir E:/machete/rl-classical [--nodes 100000] [--workers 10]
        [--follow] [--limit 0]

The league's games are played by our own network, so its own scores are not a
label to learn from. Here five teachers - Stockfish, PlentyChess, Reckless,
Obsidian and Caissa, the panel of harness/nnue/consensus_label.py - each search
every position of gen-*/moves.jsonl at --nodes and give their best move and
score. Written to labels.jsonl, one line a position:

    best     the consensus best move: the move at least three teachers chose
             (three of those that answered, when one is missing); null when
             they do not agree, and such a position takes no part in any
             "was the best move found" statistic
    cp       the consensus score from the side to move: the median of the
             teachers' scores in win-probability space (sigmoid(cp/150)), the
             pooling consensus_label.py uses, so no engine's centipawn scale
             decides it
    teachers each one's move and score
    move, own, who, game   what the league's engine played there and thought

A position (board, side to move, castling, en passant) is labelled once.
Resumable: positions already in labels.jsonl are skipped. --follow keeps
reading moves.jsonl as the league writes it. Runs below normal priority: the
lichess bot and the matches keep their clocks.
"""
import argparse
import collections
import ctypes
import glob
import json
import math
import multiprocessing
import os
import sys
import time

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nnue"))
import panel  # noqa: E402

TEACHERS = ("Stockfish", "PlentyChess", "Reckless", "Obsidian", "Caissa")
AGREE = 3
SCALE = 150.0
CLAMP = 2000


def below_normal():
    if os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def to_wp(cp):
    return 1.0 / (1.0 + math.exp(-float(cp) / SCALE))


def from_wp(p):
    p = min(1.0 - 1e-6, max(1e-6, float(p)))
    return int(round(SCALE * math.log(p / (1.0 - p))))


def pooled(scores):
    """The median of the scores in win-probability space, in centipawns."""
    wps = sorted(to_wp(s) for s in scores)
    n = len(wps)
    middle = wps[n // 2] if n % 2 else (wps[n // 2 - 1] + wps[n // 2]) / 2
    return max(-CLAMP, min(CLAMP, from_wp(middle)))


def score_of(info, turn):
    score = info["score"].pov(turn)
    if score.is_mate():
        return CLAMP if score.mate() > 0 else -CLAMP
    return max(-CLAMP, min(CLAMP, int(score.score())))


def position_key(fen):
    return " ".join(fen.split()[:4])


def consensus(answers):
    """(best move or None, votes for it) from {teacher: (move, cp)}."""
    votes = collections.Counter(move for move, _ in answers.values())
    move, count = votes.most_common(1)[0]
    return (move if count >= AGREE else None), count


def ask(engines, name, board, limit):
    """One teacher's (move, cp), or None after a second failure; a failed engine is reopened."""
    for _ in range(2):
        try:
            if name not in engines:
                engines[name] = panel.open_engine(name, 32)
            info = engines[name].analyse(board, limit)
            pv = info.get("pv")
            if pv:
                return pv[0].uci(), score_of(info, board.turn)
        except Exception:
            pass
        try:
            engines.pop(name).close()
        except Exception:
            pass
    return None


def worker(tasks, results, nodes):
    below_normal()
    engines = {}
    limit = chess.engine.Limit(nodes=nodes)
    while True:
        task = tasks.get()
        if task is None:
            break
        board = chess.Board(task["fen"])
        answers = {}
        for name in TEACHERS:
            answer = ask(engines, name, board, limit)
            if answer:
                answers[name] = answer
        row = dict(task, legal=board.legal_moves.count(), teachers=answers)
        if len(answers) >= AGREE + 1:
            row["best"], row["votes"] = consensus(answers)
            row["cp"] = pooled([cp for _, cp in answers.values()])
        else:
            row["best"], row["votes"], row["cp"] = None, 0, None
        results.put(row)
    for engine in engines.values():
        panel.quiet_quit(engine)


def new_tasks(folder, offsets, seen):
    """Positions the league has written since the last look, each once."""
    tasks = []
    for path in sorted(glob.glob(os.path.join(folder, "gen-*", "moves.jsonl"))):
        with open(path, "rb") as f:
            f.seek(offsets.get(path, 0))
            while True:
                line = f.readline()
                if not line.endswith(b"\n"):
                    break  # the league is still writing this line
                offsets[path] = f.tell()
                m = json.loads(line)
                key = position_key(m["fen"])
                if key in seen:
                    continue
                seen.add(key)
                tasks.append(dict(fen=m["fen"], move=m["move"], own=m["score"], who=m["who"], game=m["game"],
                                  gen=os.path.basename(os.path.dirname(path))))
    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--out", default="", help="default <dir>/labels.jsonl")
    parser.add_argument("--nodes", type=int, default=100000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--follow", action="store_true", help="keep going as the league writes more")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many positions (checks)")
    args = parser.parse_args()
    below_normal()
    out_path = args.out or os.path.join(args.dir, "labels.jsonl")
    seen = set()
    if os.path.exists(out_path):
        seen = {position_key(json.loads(l)["fen"]) for l in open(out_path, encoding="utf-8")}
    labelled = len(seen)
    tasks, results = multiprocessing.Queue(), multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, args=(tasks, results, args.nodes), daemon=True) for _ in range(args.workers)]
    for p in pool:
        p.start()
    offsets, pending, done, agreed, start, last = {}, 0, 0, 0, time.time(), time.time()
    with open(out_path, "a", encoding="utf-8") as out:
        while True:
            if pending < 4 * args.workers:
                fresh = new_tasks(args.dir, offsets, seen)
                if args.limit:
                    fresh = fresh[:max(0, args.limit - done - pending)]
                for t in fresh:
                    tasks.put(t)
                pending += len(fresh)
            if pending == 0:
                if not args.follow or (args.limit and done >= args.limit):
                    break
                time.sleep(20)
                continue
            row = results.get()
            pending -= 1
            done += 1
            agreed += row["best"] is not None
            out.write(json.dumps(row) + "\n")
            if time.time() - last > 60:
                out.flush()
                last = time.time()
                print("%s  %d labelled this run (%d in all), consensus on %.1f%%, %.1f a second, %d waiting" % (
                    time.strftime("%H:%M"), done, labelled + done, 100 * agreed / done, done / (time.time() - start), pending), flush=True)
            if args.limit and done >= args.limit:
                break
    for _ in pool:
        tasks.put(None)
    print("%d positions labelled, consensus best move on %.1f%%" % (done, 100 * agreed / max(1, done)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
