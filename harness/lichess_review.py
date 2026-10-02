"""Review the lichess bot's games since a time: the record, and every game it should have won.

    python harness/lichess_review.py --since "2026-09-29 22:41" --engine machete.exe --net machete.nnue
        [--config E:/machete/lichess-bot/config.yml] [--workers 6] [--out review.txt] [--all-draws]

The bot account's own token (lichess-bot's config) exports its games; the
public export is closed for bot accounts. Then:

  1. the record: by colour, by the opponent's rating against the bot's, by
     opening family, and how often the repertoire's systems were reached;
  2. every loss, and every draw or loss against a bot rated at or below it
     (the owner's standard: those are failures to explain), taken apart with
     Stockfish 19 at depth 22 on every position: where the game turned (the
     first ply from which the bot never got back above -1.50), the costliest
     moves the bot made with Stockfish's choice, and what the bot's own engine
     thought of the worst position at depth 16 - optimism there is an
     evaluation error, a different move at depth is a search or time error.

--all-draws takes every draw apart, not only those against bots rated at or
below it: a win let slip against a stronger bot is as much a failure.

It uses the engine the bot runs, so a review of a version is a review of that
version.
"""
import argparse
import collections
import datetime
import json
import multiprocessing
import os
import statistics
import sys

import chess
import chess.engine
import requests
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "nnue"))
import panel  # noqa: E402

BOT = "nickdrohan"


def fetch(config, since):
    token = yaml.safe_load(open(config))["token"]
    stamp = int(datetime.datetime.strptime(since, "%Y-%m-%d %H:%M").timestamp() * 1000)
    r = requests.get("https://lichess.org/api/games/user/" + BOT,
                     params={"since": stamp, "clocks": "true", "opening": "true"},
                     headers={"Accept": "application/x-ndjson", "Authorization": "Bearer " + token}, timeout=120)
    r.raise_for_status()
    games = []
    for line in r.text.splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        if g["status"] in ("started", "created", "aborted", "noStart"):
            continue
        p = g["players"]
        me = "white" if p["white"]["user"]["name"].lower() == BOT else "black"
        op = "black" if me == "white" else "white"
        result = "draw" if not g.get("winner") else ("win" if g["winner"] == me else "loss")
        games.append(dict(id=g["id"], me=me, result=result, status=g["status"], opp=p[op]["user"]["name"],
                          diff=(p[op].get("rating") or 0) - (p[me].get("rating") or 0),
                          opening=g.get("opening", {}).get("name", "?"), moves=g["moves"].split()))
    return games


def record(games):
    out = []
    c = collections.Counter(g["result"] for g in games)
    n = len(games)
    out.append("%d games: %d W %d D %d L, score %.1f%%" % (n, c["win"], c["draw"], c["loss"], 100.0 * (c["win"] + c["draw"] / 2.0) / max(1, n)))
    for side in ("white", "black"):
        s = [g for g in games if g["me"] == side]
        cc = collections.Counter(g["result"] for g in s)
        out.append("  as %-5s %3d games: %2d W %2d D %2d L" % (side, len(s), cc["win"], cc["draw"], cc["loss"]))
    for lo, hi, label in ((-9999, -150, "150+ weaker"), (-150, 1, "0-150 weaker or equal"), (1, 150, "0-150 stronger"), (150, 9999, "150+ stronger")):
        s = [g for g in games if lo <= g["diff"] < hi]
        if s:
            cc = collections.Counter(g["result"] for g in s)
            out.append("  opponent %-22s %3d games: %2d W %2d D %2d L  (%.0f%%)" % (
                label, len(s), cc["win"], cc["draw"], cc["loss"], 100.0 * (cc["win"] + cc["draw"] / 2.0) / len(s)))
    fam = collections.defaultdict(collections.Counter)
    for g in games:
        fam[(g["me"], g["opening"].split(":")[0])][g["result"]] += 1
    out.append("  openings (bot's colour, family: W-D-L):")
    for (side, name), cc in sorted(fam.items(), key=lambda kv: -sum(kv[1].values()))[:14]:
        out.append("    %-5s %-34s %d-%d-%d" % (side, name[:34], cc["win"], cc["draw"], cc["loss"]))
    return out


def analyse(item):
    game, engine_path, net = item
    colour = chess.WHITE if game["me"] == "white" else chess.BLACK
    sf = panel.open_engine("Stockfish", 128)
    board = chess.Board()
    curve = []
    for i in range(len(game["moves"]) + 1):
        if board.is_game_over():
            break
        info = sf.analyse(board, chess.engine.Limit(depth=22))
        best = info["pv"][0] if info.get("pv") else None
        curve.append(dict(ply=i, fen=board.fen(), s=info["score"].pov(colour).score(mate_score=3000),
                          best=board.san(best) if best else None))
        if i < len(game["moves"]):
            board.push_san(game["moves"][i])
    panel.quiet_quit(sf)
    mine = [c for c in curve[:-1] if chess.Board(c["fen"]).turn == colour and c["ply"] < len(game["moves"])]
    costs = []
    for c in mine:
        after = curve[c["ply"] + 1]["s"] if c["ply"] + 1 < len(curve) else c["s"]
        costs.append(dict(ply=c["ply"] + 1, fen=c["fen"], move=game["moves"][c["ply"]], best=c["best"],
                          before=c["s"], after=after, cost=c["s"] - after))
    turn = next((c["ply"] for c in curve if all(x["s"] <= -150 for x in curve if x["ply"] >= c["ply"])), None)
    # the losing move is the costliest one made while the game was still alive:
    # a pawn push at -10 in a dead position explains nothing
    alive = [c for c in costs if c["before"] > -300]
    worst = max(alive, key=lambda c: c["cost"]) if alive else None
    if worst:
        me = chess.engine.SimpleEngine.popen_uci(engine_path, cwd=os.path.dirname(engine_path) or None)
        me.configure({"EvalFile": net, "Threads": 1})
        b = chess.Board(worst["fen"])
        info = me.analyse(b, chess.engine.Limit(depth=16))
        worst["own_eval"] = info["score"].pov(colour).score(mate_score=3000)
        worst["own_move"] = b.san(info["pv"][0]) if info.get("pv") else None
        me.quit()
    peak = max(curve, key=lambda c: c["s"]) if curve else None
    return dict(game, curve=curve, costs=costs, turn=turn, worst=worst, peak=peak,
                after_opening=curve[min(30, len(curve) - 1)]["s"] if curve else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="local time, 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--net", required=True)
    parser.add_argument("--config", default="E:/machete/lichess-bot/config.yml")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="")
    parser.add_argument("--all-draws", action="store_true")
    args = parser.parse_args()

    games = fetch(args.config, args.since)
    lines = ["lichess review since %s" % args.since] + record(games)
    failures = [g for g in games if g["result"] == "loss" or (g["result"] == "draw" and (args.all_draws or g["diff"] <= 0))]
    lines.append("")
    lines.append("%d games to explain (every loss, and %s)" % (
        len(failures), "every draw" if args.all_draws else "draws against bots rated at or below the bot"))
    with multiprocessing.Pool(args.workers) as pool:
        done = pool.map(analyse, [(g, os.path.abspath(args.engine), os.path.abspath(args.net)) for g in failures])
    turns = [d["turn"] for d in done if d["turn"] is not None]
    if turns:
        lines.append("  lost for good (Stockfish below -1.50 to the end) at ply: median %d, quartiles %s" % (
            statistics.median(turns), [int(q) for q in statistics.quantiles(turns, n=4)] if len(turns) > 1 else turns))
    for d in sorted(done, key=lambda d: (d["result"], d["diff"])):
        w = d["worst"]
        lines.append("")
        lines.append("%s %s %-5s vs %s (%+d) - %s, %d plies, %s" % (
            d["id"], d["result"], d["me"], d["opp"], d["diff"], d["status"], len(d["moves"]), d["opening"][:40]))
        lines.append("  after the opening (ply 30): %+d; best position %+d at ply %d; turned at ply %s" % (
            d["after_opening"] or 0, d["peak"]["s"] if d["peak"] else 0, d["peak"]["ply"] if d["peak"] else 0, d["turn"]))
        bad = sorted([c for c in d["costs"] if c["cost"] >= 40], key=lambda c: c["ply"])
        if bad:
            lines.append("  moves costing 40+ cp: " + ", ".join("%d.%s %+d->%+d (best %s)" % (
                (c["ply"] + 1) // 2, c["move"], c["before"], c["after"], c["best"]) for c in bad[:8]))
        if w:
            lines.append("  worst: %d.%s %+d->%+d, Stockfish %s; the bot's engine thinks %+d and plays %s" % (
                (w["ply"] + 1) // 2, w["move"], w["before"], w["after"], w["best"], w["own_eval"], w["own_move"]))
    text = "\n".join(lines)
    print(text)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
