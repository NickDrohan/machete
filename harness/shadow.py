"""Put machete's view of every position beside what a strong engine thought.

    python harness/shadow.py data/games_stable.pgn --out data/shadow --workers 3

The stable round robin (harness/stable.py) records, for every move, the eval
the engine playing it reported at its own depth on a real clock. This goes
through the same positions with machete twice:

  quick   depth 1 - the network plus the capture search. What the network
          itself believes, with only the hanging pieces resolved.
  search  a fixed depth - the move machete would choose, and its score. Depth,
          not nodes: machete does not implement `go nodes`.

harness/stable.py's observer already records both as `[%machete ...]` beside
every move; those are read as they are, and only games without them are
searched here.

and asks three questions:

  1. Agreement: how often does machete pick the move a strong engine played?
  2. Evaluation gap: how far is machete's quick eval from the strong engine's,
     by phase and material? The big gaps, where the strong engine searched
     deep, are written to OUT.epd with that engine's eval - labelled by an
     engine far stronger than machete, at a depth our generator cannot afford.
  3. Calibration: whose eval predicts the game result better? Each source's
     centipawns are mapped to an expected score with the scale that fits it
     best, so the comparison is of information, not of units.

Rows are cached in OUT.json by game, so running it again while the round robin
is still playing only analyses the new games.
"""

import argparse
import collections
import io
import json
import math
import multiprocessing
import os
import re
import sys

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nnue"))
import engine as engines

EVAL = re.compile(r"\[%eval (#?-?[\d.]+),(\d+)\]")
MACHETE = re.compile(r"\[%machete (-?\d+),(-?\d+),(\w+),(\d+)\]")
MATE_CP = 3000
CLIP = 1000          # gaps and calibration use evals clipped to this
BLIND_GAP = 200      # a quick eval this far from the strong engine's is a blind spot
BLIND_DEPTH = 14     # ... when the strong engine searched at least this deep
PIECES = {chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B", chess.KNIGHT: "N"}


def to_cp(text):
    if text.startswith("#"):
        mate = int(text[1:])
        return MATE_CP if mate > 0 else -MATE_CP
    return int(round(float(text) * 100))


def phase(board):
    pieces = sum(len(board.pieces(k, c)) for k in PIECES for c in chess.COLORS)
    if board.fullmove_number <= 12 and pieces >= 12:
        return "opening"
    return "middlegame" if pieces > 6 else "endgame"


def signature(board):
    def side(colour):
        return "".join(PIECES[k] * len(board.pieces(k, colour)) for k in PIECES) or "K"
    return "{} v {}".format(side(chess.WHITE), side(chess.BLACK))


def white_cp(score):
    return score.white().score(mate_score=MATE_CP)


def analyse_game(job):
    """Every position of one game, as rows. Runs in a worker process."""
    number, text, binary, net, depth = job
    game = chess.pgn.read_game(io.StringIO(text))
    ours = None
    rows = []
    try:
        board = game.board()
        result = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}.get(game.headers["Result"])
        session = object()
        for node in game.mainline():
            found = EVAL.search(node.comment or "")
            if found and not board.is_game_over():
                seen = MACHETE.search(node.comment or "")
                if seen:
                    quick, searched = int(seen.group(1)), int(seen.group(2))
                    choice, reached = seen.group(3), int(seen.group(4))
                else:
                    if ours is None:
                        ours = chess.engine.SimpleEngine.popen_uci(binary)
                        ours.configure({"EvalFile": net})
                        engines.pin(ours, 64)
                    quick = white_cp(ours.analyse(board, chess.engine.Limit(depth=1), game=session)["score"])
                    deep = ours.analyse(board, chess.engine.Limit(depth=depth), game=session)
                    searched, choice, reached = white_cp(deep["score"]), deep["pv"][0].uci(), deep.get("depth")
                mover = game.headers["White"] if board.turn == chess.WHITE else game.headers["Black"]
                rows.append({
                    "game": number, "ply": board.ply(), "fen": board.fen(), "mover": mover,
                    "phase": phase(board), "signature": signature(board),
                    "strong": to_cp(found.group(1)), "strong_depth": int(found.group(2)),
                    "played": node.move.uci(),
                    "quick": quick, "machete": searched, "machete_move": choice,
                    "machete_depth": reached, "result": result,
                })
            board.push(node.move)
    finally:
        engines.shutdown(ours)
    return number, rows


def clip(cp):
    return max(-CLIP, min(CLIP, cp))


def expected(cp, scale):
    return 1.0 / (1.0 + 10.0 ** (-cp / scale))


def log_loss(pairs, scale):
    total = 0.0
    for cp, result in pairs:
        p = min(1 - 1e-6, max(1e-6, expected(cp, scale)))
        total -= result * math.log(p) + (1 - result) * math.log(1 - p)
    return total / len(pairs)


def best_scale(pairs):
    """The centipawn scale under which these evals best predict the results."""
    return min(range(50, 1501, 10), key=lambda s: log_loss(pairs, s))


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def quantile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] if values else 0


def report(rows, out):
    print("\n{} positions from {} games".format(len(rows), len({r["game"] for r in rows})))

    print("\n1. machete picks the strong engine's move")
    for key in ("phase", "mover"):
        groups = collections.defaultdict(list)
        for r in rows:
            groups[r[key]].append(r["machete_move"] == r["played"])
        for name, hits in sorted(groups.items(), key=lambda g: -len(g[1])):
            print("   {:<12} {:>6} positions  {:5.1%}".format(name, len(hits), sum(hits) / len(hits)))
        print()

    print("2. machete's quick eval against the strong engine's (centipawns, clipped at {})".format(CLIP))
    print("   {:<12} {:>7} {:>8} {:>8} {:>10}".format("", "count", "median", "90th", "bias"))
    groups = collections.defaultdict(list)
    for r in rows:
        if r["strong_depth"] >= BLIND_DEPTH:
            groups[r["phase"]].append(clip(r["quick"]) - clip(r["strong"]))
    for name in ("opening", "middlegame", "endgame"):
        gaps = groups.get(name, [])
        if gaps:
            print("   {:<12} {:>7} {:>8} {:>8} {:>+10.0f}".format(
                name, len(gaps), median([abs(g) for g in gaps]),
                quantile([abs(g) for g in gaps], 0.9), sum(gaps) / len(gaps)))
    print("   (bias > 0: machete thinks White is better than the strong engine does)")

    blind = [r for r in rows if r["strong_depth"] >= BLIND_DEPTH
             and abs(clip(r["quick"]) - clip(r["strong"])) >= BLIND_GAP]
    # one long ending contributes dozens of near-identical positions, so each
    # group says how many games it comes from, and is ranked by that
    print("\n   {} blind spots ({}+ cp from a strong engine at depth {}+) from {} games, by material:".format(
        len(blind), BLIND_GAP, BLIND_DEPTH, len({r["game"] for r in blind})))
    games_of = collections.defaultdict(set)
    counts = collections.Counter(r["signature"] for r in blind)
    for r in blind:
        games_of[r["signature"]].add(r["game"])
    print("   {:<24} {:>6} {:>10}".format("", "games", "positions"))
    for name in sorted(games_of, key=lambda n: (-len(games_of[n]), -counts[n]))[:12]:
        print("   {:<24} {:>6} {:>10}".format(name, len(games_of[name]), counts[name]))

    print("\n3. whose eval predicts the result (log loss, lower is better; each at its best scale)")
    decided = [r for r in rows if r["result"] is not None]
    for name, key in (("strong engine", "strong"), ("machete searched", "machete"), ("machete quick", "quick")):
        pairs = [(clip(r[key]), r["result"]) for r in decided]
        if pairs:
            scale = best_scale(pairs)
            print("   {:<18} {:.4f}  at scale {}".format(name, log_loss(pairs, scale), scale))

    with open(out + ".epd", "w", newline="\n") as handle:
        handle.write("# positions where machete's network disagrees with a strong engine by {}+ cp;\n"
                     "# ce is that engine's eval in centipawns from the side to move\n".format(BLIND_GAP))
        for r in blind:
            stm = 1 if " w " in r["fen"] else -1
            handle.write("{} ce {}; c0 \"{} d{}\";\n".format(
                " ".join(r["fen"].split()[:4]), stm * r["strong"], r["mover"], r["strong_depth"]))
    print("\n{} blind spots written to {}.epd".format(len(blind), out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--engine", default=engines.MACHETE)
    parser.add_argument("--net", default=os.path.join(os.path.dirname(HERE), "net", "machete.nnue"))
    parser.add_argument("--depth", type=int, default=10, help="for games without [%%machete]")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", default="data/shadow")
    args = parser.parse_args()

    cache = {}
    if os.path.exists(args.out + ".json"):
        with open(args.out + ".json") as handle:
            for r in json.load(handle):
                cache.setdefault(r["game"], []).append(r)

    jobs = []
    with open(args.pgn, encoding="utf-8", errors="replace") as handle:
        number = 0
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            number += 1
            if number not in cache:
                jobs.append((number, str(game), os.path.abspath(args.engine),
                             os.path.abspath(args.net), args.depth))
    print("{} games cached, {} to analyse".format(len(cache), len(jobs)))
    sys.stdout.flush()
    if jobs:
        with multiprocessing.Pool(args.workers) as pool:
            for done, (number, rows) in enumerate(pool.imap_unordered(analyse_game, jobs), 1):
                cache[number] = rows
                sys.stdout.write("\r{} of {} games".format(done, len(jobs)))
                sys.stdout.flush()
        with open(args.out + ".json", "w") as handle:
            json.dump([r for number in sorted(cache) for r in cache[number]], handle)
    rows = [r for number in sorted(cache) for r in cache[number]]
    if rows:
        report(rows, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
