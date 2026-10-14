"""How often the search, set one way, finds the move the panel agreed was best.

    python harness/search_agree.py run --name NAME [--set K=V ...] [--nodes 40000]
        [--limit 0] [--workers 8] [--engine EXE] [--net NNUE]
    python harness/search_agree.py report [--against defaults]

The positions are the league's: 95,835 from machete's own games where at
least three of the five panel engines (Stockfish, PlentyChess, Reckless,
Obsidian, Caissa) named the same best move (E:/machete/rl-classical/
instinct.jsonl). A forced move tests nothing, so positions with one legal move
are left out.

Each setting is a name and the search constants it changes (the UCI spin
options of search.mach's tunables); `run` searches every position to a fixed
number of nodes from an empty table and keeps the move it chose, in
OUT/NAME.jsonl, resumably. `report` prints each setting's share of panel moves
and, against one setting, the positions only one of the two got right: on the
same positions the noise is in those alone, so the comparison is far sharper
than either share's own margin.

What this measures is not Elo. Between networks it ranked all seven the league
measured in the order their games did (instinct.txt: 50.3% for F60 up to 60.5%
for C33, about 37 Elo a point between S60 and C33). Whether it ranks search
settings the way games do is what the first settings run are for, and any
setting it favours is a candidate for an SPRT, never a default by itself.
"""

import argparse
import json
import math
import multiprocessing
import os

import chess
import chess.engine

POSITIONS = "E:/machete/rl-classical/instinct.jsonl"
OUT = "E:/machete/claude/search_agree"
ENGINE = "E:/machete/claude/r3/m-dev-inc.exe"
NET = "E:/machete/claude/nets/c33f140.nnue"


def positions(limit):
    rows = []
    with open(POSITIONS, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["legal"] > 1:
                rows.append((row["fen"], row["best"]))
    return rows[:limit] if limit else rows


# the names in an OrderingStats line, in the order its counts are kept
CUTS = ("1", "2", "3", "4-6", "7+", "tt", "capture", "killer", "counter", "history", "losing")


def ordering(text):
    """The counts from an engine's "ordering cuts at 1 N 2 N ... by tt N ..." line, or None."""
    words = (text or "").split()
    if not words or words[0] != "ordering":
        return None
    found = {words[k]: int(words[k + 1]) for k in range(len(words) - 1) if words[k] in CUTS and words[k + 1].isdigit()}
    return [found.get(name, 0) for name in CUTS]


def worker(tasks, results, engine_path, options, nodes):
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=60)
        if "OrderingStats" in engine.options:
            options = dict(options, OrderingStats=True)
        engine.configure(options)
    except Exception as e:  # said once, not a hang: run() waits on results
        results.put((None, repr(e), None, None))
        return
    limit = chess.engine.Limit(nodes=nodes)
    while True:
        task = tasks.get()
        if task is None:
            break
        i, fen = task
        # a new game every position: the table starts empty, so no position
        # is helped by what the one before it left behind
        info = engine.analyse(chess.Board(fen), limit, game=i)
        pv = info.get("pv")
        results.put((i, pv[0].uci() if pv else None, info.get("depth"), ordering(info.get("string"))))
    engine.quit()


def run(args):
    rows = positions(args.limit)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, args.name + ".jsonl")
    settings = dict(s.split("=", 1) for s in args.set)
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if "settings" in row:
                    if row["settings"] != settings or row["nodes"] != args.nodes or row["net"] != args.net:
                        raise SystemExit("{} was run with other settings: {}".format(path, row))
                else:
                    done.add(row["i"])
    options = {"EvalFile": args.net, "Repertoire": 0, "Threads": 1, "Hash": 128}
    options.update({k: int(v) for k, v in settings.items()})
    todo = [(i, fen) for i, (fen, _) in enumerate(rows) if i not in done]
    print("{}: {} positions to search at {:,} nodes, {}".format(args.name, len(todo), args.nodes, settings or "defaults"), flush=True)
    tasks, results = multiprocessing.Queue(), multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, args=(tasks, results, args.engine, options, args.nodes))
            for _ in range(args.workers)]
    for p in pool:
        p.start()
    for t in todo:
        tasks.put(t)
    for _ in pool:
        tasks.put(None)
    with open(path, "a", encoding="utf-8") as out:
        if not done:
            out.write(json.dumps({"settings": settings, "nodes": args.nodes, "net": args.net, "engine": args.engine}) + "\n")
        for n in range(len(todo)):
            i, move, depth, cuts = results.get()
            if i is None:
                for p in pool:
                    p.terminate()
                raise SystemExit("a worker could not start the engine: " + move)
            row = {"i": i, "move": move, "depth": depth}
            if cuts:
                row["cuts"] = cuts
            out.write(json.dumps(row) + "\n")
            if n % 1000 == 999:
                out.flush()
                print("  {:,} of {:,}".format(n + 1, len(todo)), flush=True)
    for p in pool:
        p.join()


def cut_summary(name):
    """Every position's cutoff counts added up, as shares: the first move cutting, then each reason, or ''."""
    total = [0] * len(CUTS)
    with open(os.path.join(OUT, name + ".jsonl"), encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for k, v in enumerate(row.get("cuts") or []):
                total[k] += v
    cuts = sum(total[:5])
    if not cuts:
        return ""
    share = lambda k: 100.0 * total[k] / cuts
    return "cuts {:,}: first move {:.1f}%, by " .format(cuts, share(0)) + ", ".join(
        "{} {:.1f}%".format(CUTS[k], share(k)) for k in range(5, len(CUTS)))


def load(name):
    moves, depths, head = {}, [], None
    with open(os.path.join(OUT, name + ".jsonl"), encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if "settings" in row:
                head = row
            else:
                moves[row["i"]] = row["move"]
                if row["depth"]:
                    depths.append(row["depth"])
    return head, moves, depths


def report(args):
    rows = positions(0)
    names = sorted(f[:-6] for f in os.listdir(OUT) if f.endswith(".jsonl"))
    base_head, base, _ = load(args.against)
    print("{:<22} {:>7} {:>7} {:>7}   against {}: only this / only that, difference, z".format(
        "setting", "searched", "panel", "depth", args.against))
    for name in names:
        head, moves, depths = load(name)
        right = sum(1 for i, m in moves.items() if m == rows[i][1])
        line = "{:<22} {:>7,} {:>6.2f}% {:>7.2f}".format(name, len(moves), 100.0 * right / max(1, len(moves)),
                                                          sum(depths) / max(1, len(depths)))
        if name != args.against:
            shared = [i for i in moves if i in base]
            ours = sum(1 for i in shared if moves[i] == rows[i][1] and base[i] != rows[i][1])
            theirs = sum(1 for i in shared if base[i] == rows[i][1] and moves[i] != rows[i][1])
            z = (ours - theirs) / math.sqrt(ours + theirs) if ours + theirs else 0.0
            line += "   {:,} / {:,}  {:+.2f} points  z {:+.1f}".format(
                ours, theirs, 100.0 * (ours - theirs) / max(1, len(shared)), z)
        print(line + "   " + json.dumps(head["settings"] if head else {}))
        cuts = cut_summary(name)
        if cuts:
            print("{:<22} {}".format("", cuts))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", required=True)
    r.add_argument("--set", action="append", default=[], help="a search constant, as its UCI name=value")
    r.add_argument("--nodes", type=int, default=40000)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--engine", default=ENGINE)
    r.add_argument("--net", default=NET)
    p = sub.add_parser("report")
    p.add_argument("--against", default="defaults")
    args = parser.parse_args()
    run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    main()
