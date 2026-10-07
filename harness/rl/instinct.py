"""Is a network's first instinct already the best move?

    python harness/rl/instinct.py run    --dir E:/machete/rl-classical [--workers 6] [--limit 0]
        [--net NAME=PATH ...]
    python harness/rl/instinct.py report --dir E:/machete/rl-classical

For every position the panel agreed a best move on (labels.jsonl, written by
panel_label.py), each network is asked twice through the same engine
(machete 0.3.6): at depth 1, which is the network's own judgement with next
to no search - its first instinct - and at 40,000 nodes, a real search. Both
moves are written to instinct.jsonl; `report` prints how often each was the
panel's best move.

Two floors are printed beside the networks, so the measure is known to be
able to fail: a random legal move, and the first legal move in the engine's
list order.

Resumable: positions already in instinct.jsonl are skipped for the networks
they already hold.
"""
import argparse
import collections
import json
import multiprocessing
import os
import sys

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import panel_label  # noqa: E402

ENGINE = "E:/machete/releases/machete-0.3.6/machete.exe"
NETS = collections.OrderedDict([
    ("F60", "E:/machete/claude/nets/f60.nnue"),
    ("F100", "E:/machete/claude/nets/f100.nnue"),
    ("F100D", "E:/machete/claude/nets/f100d.nnue"),
    ("F120", "E:/machete/claude/nets/f120.nnue"),
    ("F120D", "E:/machete/claude/nets/f120d.nnue"),
    ("S60", "E:/machete/claude/nets/s60.nnue"),
    ("C33", "E:/machete/claude/nets/c33.nnue"),
])
SEARCH_NODES = 40000


def open_net(path):
    engine = chess.engine.SimpleEngine.popen_uci(ENGINE, timeout=60)
    engine.configure({"EvalFile": path, "Repertoire": 0, "Threads": 1})
    return engine


def first_move(engine, board, limit):
    info = engine.analyse(board, limit)
    pv = info.get("pv")
    return pv[0].uci() if pv else engine.play(board, limit).move.uci()


def labelled(folder):
    """Positions with a consensus best move, in the order the panel wrote them."""
    path = os.path.join(folder, "labels.jsonl")
    if not os.path.exists(path):
        return
    with open(path, "rb") as f:
        for line in f:
            if not line.endswith(b"\n"):
                break
            row = json.loads(line)
            if row["best"]:
                yield row


def worker(tasks, results, nets):
    panel_label.below_normal()
    engines = {name: open_net(path) for name, path in nets.items()}
    shallow, deep = chess.engine.Limit(depth=1), chess.engine.Limit(nodes=SEARCH_NODES)
    while True:
        task = tasks.get()
        if task is None:
            break
        board = chess.Board(task["fen"])
        moves = dict(task.get("moves", {}))
        for name in nets:
            if name not in moves:
                moves[name] = [first_move(engines[name], board, shallow), first_move(engines[name], board, deep)]
        results.put(dict(fen=task["fen"], best=task["best"], legal=task["legal"], moves=moves))
    for engine in engines.values():
        engine.quit()


def run(args):
    panel_label.below_normal()
    nets = collections.OrderedDict((k, v) for k, v in NETS.items() if os.path.exists(v))
    for spec in args.net:
        name, path = spec.split("=", 1)
        nets[name] = path
    out_path = os.path.join(args.dir, "instinct.jsonl")
    have = {}
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            row = json.loads(line)
            have[panel_label.position_key(row["fen"])] = row
    todo = []
    for row in labelled(args.dir):
        old = have.get(panel_label.position_key(row["fen"]))
        if old is None or any(n not in old["moves"] for n in nets):
            todo.append(dict(fen=row["fen"], best=row["best"], legal=row["legal"], moves=old["moves"] if old else {}))
    if args.limit:
        todo = todo[:args.limit]
    print("%d positions to ask %s" % (len(todo), ", ".join(nets)), flush=True)
    if not todo:
        return
    tasks, results = multiprocessing.Queue(), multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, args=(tasks, results, nets), daemon=True) for _ in range(args.workers)]
    for p in pool:
        p.start()
    for t in todo:
        tasks.put(t)
    for _ in pool:
        tasks.put(None)
    for _ in todo:
        row = results.get()
        have[panel_label.position_key(row["fen"])] = row
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        for row in have.values():
            out.write(json.dumps(row) + "\n")
    os.replace(tmp, out_path)
    report(args)


def report(args):
    rows = [json.loads(l) for l in open(os.path.join(args.dir, "instinct.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r["legal"] > 1]  # a forced move tests nothing
    if not rows:
        print("nothing yet")
        return
    names = [n for n in NETS if all(n in r["moves"] for r in rows)] + sorted({n for r in rows for n in r["moves"]} - set(NETS))
    names = [n for n in names if all(n in r["moves"] for r in rows)]
    lines = ["%d positions with a consensus best move and a choice to make" % len(rows), "",
             "%-12s %16s %18s" % ("network", "first instinct", "40,000 nodes")]
    for name in names:
        d1 = sum(r["moves"][name][0] == r["best"] for r in rows) / len(rows)
        deep = sum(r["moves"][name][1] == r["best"] for r in rows) / len(rows)
        lines.append("%-12s %15.1f%% %17.1f%%" % (name, 100 * d1, 100 * deep))
    lines.append("%-12s %15.1f%%" % ("random move", 100 * sum(1 / r["legal"] for r in rows) / len(rows)))
    first = sum(next(iter(chess.Board(r["fen"]).legal_moves)).uci() == r["best"] for r in rows) / len(rows)
    lines.append("%-12s %15.1f%%" % ("first listed", 100 * first))
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.dir, "instinct.txt"), "w", encoding="utf-8").write(text + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--net", action="append", default=[], help="NAME=PATH, another network to ask")
    args = parser.parse_args()
    run(args) if args.command == "run" else report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
