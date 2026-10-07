"""When the best move was not among our top three: which other way of judging would have found it?

    python harness/rl/schemas.py run    --dir E:/machete/rl-classical [--workers 6] [--limit 0]
    python harness/rl/schemas.py policy --dir E:/machete/rl-classical      # Leela's policy, GPU free only
    python harness/rl/schemas.py report --dir E:/machete/rl-classical

For every position the panel agreed a best move on, the league's network
(state.json's champion) ranks its own moves: every legal move is played and
the position after it searched at RANK_NODES, since the engine has no MultiPV.
Its top three are the move it played in the game and its two best others.
That ranking is kept for every position in rank.jsonl (temptations.py reads
it too).

A miss is a position where the panel's best move is not among those three.
Each miss is put to a fixed catalogue of fundamentally different ways of
choosing a move, each of which names exactly one move (or none):

  material    hand-written material and piece-square tables with a capture search, no network
  mobility    the move that leaves us the most moves and the opponent the fewest
  king        the move that most raises the pressure on the enemy king (attack_detector.py)
  forcing     mate, then the capture winning the most, then a safe check; none if nothing forces
  squares     the move whose piece gains the most by heat_mature.json: toward its favorite square
  classical   the classical-data network's first instinct (C33 at depth 1)
  depth       our own network with 30 times the nodes: the judgement was fine, the horizon was not
  policy      Leela's policy network alone, one node: a move chooser with no evaluation
  random      a random legal move: the floor every schema has to clear

schema_hits.jsonl records which of them named the best move. `report` prints
and appends to schema_density.tsv the share of misses each one solves, with
the misses fewer than three schemas solve counted as unexplained. A schema
that keeps solving misses night after night is a candidate to adopt.
"""
import argparse
import collections
import json
import multiprocessing
import os
import random
import sys
import time

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "nnue"))
import attack_detector  # noqa: E402
import instinct  # noqa: E402
import panel_label  # noqa: E402

RANK_NODES = 5000
DEPTH_FACTOR = 30
SCHEMAS = ("material", "mobility", "king", "forcing", "squares", "classical", "depth", "policy", "random")
LC0 = "C:/Users/Arman/Desktop/Games/Chess/arena_3.5.1/Engines/Leela 0.32.1/lc0.exe"
LC0_WEIGHTS = "C:/Users/Arman/Desktop/Games/Chess/arena_3.5.1/Engines/Leela 0.32.1/weights_run1_823134.lc0"

# PeSTO's tapered material values and piece-square tables (Ronald Friederich), from White's side, a8 first
MG_VALUE = (82, 337, 365, 477, 1025, 0)
EG_VALUE = (94, 281, 297, 512, 936, 0)
PHASE = (0, 1, 1, 2, 4, 0)
MG = (
    (0, 0, 0, 0, 0, 0, 0, 0, 98, 134, 61, 95, 68, 126, 34, -11, -6, 7, 26, 31, 65, 56, 25, -20, -14, 13, 6, 21, 23, 12, 17, -23,
     -27, -2, -5, 12, 17, 6, 10, -25, -26, -4, -4, -10, 3, 3, 33, -12, -35, -1, -20, -23, -15, 24, 38, -22, 0, 0, 0, 0, 0, 0, 0, 0),
    (-167, -89, -34, -49, 61, -97, -15, -107, -73, -41, 72, 36, 23, 62, 7, -17, -47, 60, 37, 65, 84, 129, 73, 44, -9, 17, 19, 53, 37, 69, 18, 22,
     -13, 4, 16, 13, 28, 19, 21, -8, -23, -9, 12, 10, 19, 17, 25, -16, -29, -53, -12, -3, -1, 18, -14, -19, -105, -21, -58, -33, -17, -28, -19, -23),
    (-29, 4, -82, -37, -25, -42, 7, -8, -26, 16, -18, -13, 30, 59, 18, -47, -16, 37, 43, 40, 35, 50, 37, -2, -4, 5, 19, 50, 37, 37, 7, -2,
     -6, 13, 13, 26, 34, 12, 10, 4, 0, 15, 15, 15, 14, 27, 18, 10, 4, 15, 16, 0, 7, 21, 33, 1, -33, -3, -14, -21, -13, -12, -39, -21),
    (32, 42, 32, 51, 63, 9, 31, 43, 27, 32, 58, 62, 80, 67, 26, 44, -5, 19, 26, 36, 17, 45, 61, 16, -24, -11, 7, 26, 24, 35, -8, -20,
     -36, -26, -12, -1, 9, -7, 6, -23, -45, -25, -16, -17, 3, 0, -5, -33, -44, -16, -20, -9, -1, 11, -6, -71, -19, -13, 1, 17, 16, 7, -37, -26),
    (-28, 0, 29, 12, 59, 44, 43, 45, -24, -39, -5, 1, -16, 57, 28, 54, -13, -17, 7, 8, 29, 56, 47, 57, -27, -27, -16, -16, -1, 17, -2, 1,
     -9, -26, -9, -10, -2, -4, 3, -3, -14, 2, -11, -2, -5, 2, 14, 5, -35, -8, 11, 2, 8, 15, -3, 1, -1, -18, -9, 10, -15, -25, -31, -50),
    (-65, 23, 16, -15, -56, -34, 2, 13, 29, -1, -20, -7, -8, -4, -38, -29, -9, 24, 2, -16, -20, 6, 22, -22, -17, -20, -12, -27, -30, -25, -14, -36,
     -49, -1, -27, -39, -46, -44, -33, -51, -14, -14, -22, -46, -44, -30, -15, -27, 1, 7, -8, -64, -43, -16, 9, 8, -15, 36, 12, -54, 8, -28, 24, 14),
)
EG = (
    (0, 0, 0, 0, 0, 0, 0, 0, 178, 173, 158, 134, 147, 132, 165, 187, 94, 100, 85, 67, 56, 53, 82, 84, 32, 24, 13, 5, -2, 4, 17, 17,
     13, 9, -3, -7, -7, -8, 3, -1, 4, 7, -6, 1, 0, -5, -1, -8, 13, 8, 8, 10, 13, 0, 2, -7, 0, 0, 0, 0, 0, 0, 0, 0),
    (-58, -38, -13, -28, -31, -27, -63, -99, -25, -8, -25, -2, -9, -25, -24, -52, -24, -20, 10, 9, -1, -9, -19, -41, -17, 3, 22, 22, 22, 11, 8, -18,
     -18, -6, 16, 25, 16, 17, 4, -18, -23, -3, -1, 15, 10, -3, -20, -22, -42, -20, -10, -5, -2, -20, -23, -44, -29, -51, -23, -15, -22, -18, -50, -64),
    (-14, -21, -11, -8, -7, -9, -17, -24, -8, -4, 7, -12, -3, -13, -4, -14, 2, -8, 0, -1, -2, 6, 0, 4, -3, 9, 12, 9, 14, 10, 3, 2,
     -6, 3, 13, 19, 7, 10, -3, -9, -12, -3, 8, 10, 13, 3, -7, -15, -14, -18, -7, -1, 4, -9, -15, -27, -23, -9, -23, -5, -9, -16, -5, -17),
    (13, 10, 18, 15, 12, 12, 8, 5, 11, 13, 13, 11, -3, 3, 8, 3, 7, 7, 7, 5, 4, -3, -5, -3, 4, 3, 13, 1, 2, 1, -1, 2,
     3, 5, 8, 4, -5, -6, -8, -11, -4, 0, -5, -1, -7, -12, -8, -16, -6, -6, 0, 2, -9, -9, -11, -3, -9, 2, 3, -1, -5, -13, 4, -20),
    (-9, 22, 22, 27, 27, 19, 10, 20, -17, 20, 32, 41, 58, 25, 30, 0, -20, 6, 9, 49, 47, 35, 19, 9, 3, 22, 24, 45, 57, 40, 57, 36,
     -18, 28, 19, 47, 31, 34, 39, 23, -16, -27, 15, 6, 9, 17, 10, 5, -22, -23, -30, -16, -16, -23, -36, -32, -33, -28, -22, -43, -5, -32, -20, -41),
    (-74, -35, -18, -18, -11, 15, 4, -17, -12, 17, 14, 17, 17, 38, 23, 11, 10, 17, 23, 15, 20, 45, 44, 13, -8, 22, 24, 27, 26, 33, 26, 3,
     -18, -4, 21, 24, 27, 23, 9, -11, -19, -3, 11, 21, 23, 16, 7, -9, -27, -11, 4, 13, 14, 4, -5, -17, -53, -34, -21, -11, -28, -14, -24, -43),
)
VALUE = (100, 320, 330, 500, 900, 0)


def static(board):
    """Material and piece-square tables, tapered, from the side to move."""
    mg = eg = phase = 0
    for square, piece in board.piece_map().items():
        k = piece.piece_type - 1
        index = square ^ 56 if piece.color else square  # the tables read from a8
        sign = 1 if piece.color else -1
        mg += sign * (MG_VALUE[k] + MG[k][index])
        eg += sign * (EG_VALUE[k] + EG[k][index])
        phase += PHASE[k]
    phase = min(24, phase)
    score = (mg * phase + eg * (24 - phase)) // 24
    return score if board.turn else -score


def quiesce(board, alpha, beta, depth=4):
    if board.is_checkmate():
        return -30000
    stand = static(board)
    if depth == 0 or stand >= beta:
        return stand
    alpha = max(alpha, stand)
    for move in sorted(board.generate_legal_captures(), key=lambda m: -VALUE[(board.piece_type_at(m.to_square) or 1) - 1]):
        board.push(move)
        score = -quiesce(board, -beta, -alpha, depth - 1)
        board.pop()
        if score >= beta:
            return score
        alpha = max(alpha, score)
    return alpha


def best_by(board, value):
    """The legal move with the highest value(move); ties go to the first in notation order."""
    best, top = None, None
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        v = value(move)
        if v is not None and (top is None or v > top):
            best, top = move, v
    return best.uci() if best else None


def after(board, move, f):
    board.push(move)
    try:
        return f(board)
    finally:
        board.pop()


def flipped(board):
    """The same position with the other side to move, or None when that is illegal."""
    if board.is_check():
        return None
    other = board.copy(stack=False)
    other.turn = not board.turn
    other.ep_square = None
    return other if other.is_valid() else None


def material(board):
    return best_by(board, lambda m: after(board, m, lambda b: -quiesce(b, -32000, 32000)))


def mobility(board):
    def value(b):
        mine = flipped(b)
        return (mine.legal_moves.count() if mine else 0) - b.legal_moves.count()
    return best_by(board, lambda m: after(board, m, value))


def king(board):
    def value(b):
        mine = flipped(b)
        if mine is None:  # the move gave check
            return 1000
        pressure, shield, files = attack_detector.features(mine)
        return pressure + 2 * files - shield
    return best_by(board, lambda m: after(board, m, value))


def forcing(board):
    def value(move):
        mover = board.piece_type_at(move.from_square)
        gain = 0
        if board.is_capture(move):
            victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant
            gain = VALUE[victim - 1]
        defended = board.is_attacked_by(not board.turn, move.to_square)
        if defended:
            gain -= VALUE[mover - 1]
        board.push(move)
        mate, check = board.is_checkmate(), board.is_check()
        board.pop()
        if mate:
            return 100000
        if gain > 0:
            return gain + (50 if check else 0)
        if check and not defended:
            return 50
        return None
    return best_by(board, value)


def squares(board, heat):
    men = chess.popcount(board.occupied)
    table = heat["opening" if men >= 26 else "middlegame" if men >= 14 else "endgame"]

    def value(move):
        piece = board.piece_at(move.from_square)
        kind = "PNBRQK"[(move.promotion or piece.piece_type) - 1]
        was = "PNBRQK"[piece.piece_type - 1]
        flip = 0 if board.turn else 56
        return table[kind]["edge"][move.to_square ^ flip] - table[was]["edge"][move.from_square ^ flip]
    return best_by(board, value)


def rank(engine, board, limit):
    """Every legal move with our network's score for it (from the mover), best first."""
    scored = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            score = 30000
        elif board.is_stalemate() or board.is_insufficient_material():
            score = 0
        else:
            score = -panel_label.score_of(engine.analyse(board, limit), board.turn)
        board.pop()
        scored.append((move.uci(), score))
    return sorted(scored, key=lambda x: (-x[1], x[0]))


def worker(tasks, results, own_net, classical_net, heat, game_nodes):
    panel_label.below_normal()
    own, classical = instinct.open_net(own_net), instinct.open_net(classical_net)
    limit = chess.engine.Limit(nodes=RANK_NODES)
    while True:
        task = tasks.get()
        if task is None:
            break
        board = chess.Board(task["fen"])
        ranking = rank(own, board, limit)
        top = [task["move"]] + [m for m, _ in ranking if m != task["move"]][:2]
        row = dict(fen=task["fen"], best=task["best"], move=task["move"], top=top, rank=ranking[:8],
                   scores={m: s for m, s in ranking if m in (task["best"], task["move"])}, miss=task["best"] not in top)
        if row["miss"]:
            rng = random.Random(task["fen"])
            row["schemas"] = dict(
                material=material(board), mobility=mobility(board), king=king(board), forcing=forcing(board),
                squares=squares(board, heat),
                classical=instinct.first_move(classical, board, chess.engine.Limit(depth=1)),
                depth=instinct.first_move(own, board, chess.engine.Limit(nodes=DEPTH_FACTOR * game_nodes)),
                random=rng.choice(sorted(m.uci() for m in board.legal_moves)))
        results.put(row)
    own.quit()
    classical.quit()


def league_net(folder):
    state = json.load(open(os.path.join(folder, "state.json"), encoding="utf-8"))
    return os.path.join(folder, "nets", state["champion"])


def run(args):
    panel_label.below_normal()
    rank_path = os.path.join(args.dir, "rank.jsonl")
    done = set()
    if os.path.exists(rank_path):
        done = {panel_label.position_key(json.loads(l)["fen"]) for l in open(rank_path, encoding="utf-8")}
    state = json.load(open(os.path.join(args.dir, "state.json"), encoding="utf-8"))
    current = "gen-%03d" % state["generation"]  # the ranking is the current network's: only its own games
    todo = [r for r in instinct.labelled(args.dir) if r["gen"] == current and r["legal"] > 3 and panel_label.position_key(r["fen"]) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("%d positions to rank" % len(todo), flush=True)
    if not todo:
        return report(args)
    heat = json.load(open(os.path.join(args.dir, "heat_mature.json")))["maps"]
    tasks, results = multiprocessing.Queue(), multiprocessing.Queue()
    pool = [multiprocessing.Process(target=worker, daemon=True,
                                    args=(tasks, results, league_net(args.dir), instinct.NETS["C33"], heat, args.game_nodes))
            for _ in range(args.workers)]
    for p in pool:
        p.start()
    for t in todo:
        tasks.put(dict(fen=t["fen"], best=t["best"], move=t["move"]))
    for _ in pool:
        tasks.put(None)
    with open(rank_path, "a", encoding="utf-8") as ranks, open(os.path.join(args.dir, "schema_hits.jsonl"), "a", encoding="utf-8") as hits:
        for _ in todo:
            row = results.get()
            schemas = row.pop("schemas", None)
            ranks.write(json.dumps(row) + "\n")
            if schemas:
                hits.write(json.dumps(dict(fen=row["fen"], best=row["best"], top=row["top"], schemas=schemas)) + "\n")
    panel_label.finish(pool)
    report(args)


def policy(args):
    """Leela's policy move for every miss that lacks one. Uses the GPU: run only when nothing trains."""
    path = os.path.join(args.dir, "schema_hits.jsonl")
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    todo = [r for r in rows if "policy" not in r["schemas"]]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        return
    engine = chess.engine.SimpleEngine.popen_uci([LC0, "--weights=" + LC0_WEIGHTS, "--threads=1"], timeout=180)
    limit = chess.engine.Limit(nodes=1)
    for r in todo:
        r["schemas"]["policy"] = instinct.first_move(engine, chess.Board(r["fen"]), limit)
    engine.quit()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    os.replace(tmp, path)
    print("Leela's policy asked on %d misses" % len(todo))


def report(args):
    rank_path, hits_path = os.path.join(args.dir, "rank.jsonl"), os.path.join(args.dir, "schema_hits.jsonl")
    if not os.path.exists(hits_path):
        print("no misses yet")
        return
    ranked = sum(1 for _ in open(rank_path, encoding="utf-8"))
    rows = [json.loads(l) for l in open(hits_path, encoding="utf-8")]
    solved = collections.Counter()
    asked = collections.Counter()
    explained = 0
    for r in rows:
        hit = [s for s in SCHEMAS if r["schemas"].get(s) == r["best"]]
        for s in SCHEMAS:
            if s in r["schemas"]:
                asked[s] += 1
        for s in hit:
            solved[s] += 1
        explained += len([s for s in hit if s != "random"]) >= 3
    lines = ["%d positions ranked, %d misses (%.1f%%): the panel's best move outside our top three" % (ranked, len(rows), 100 * len(rows) / max(1, ranked)),
             "%d of the misses (%.1f%%) are found by three or more schemas" % (explained, 100 * explained / max(1, len(rows))), "",
             "%-10s %8s %8s" % ("schema", "solves", "asked")]
    for s in sorted(SCHEMAS, key=lambda s: -solved[s] / max(1, asked[s])):
        if asked[s]:
            lines.append("%-10s %7.1f%% %8d" % (s, 100 * solved[s] / asked[s], asked[s]))
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.dir, "schemas.txt"), "w", encoding="utf-8").write(text + "\n")
    path = os.path.join(args.dir, "schema_density.tsv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("when\tranked\tmisses\texplained\t" + "\t".join(SCHEMAS) + "\n")
        f.write("%s\t%d\t%d\t%d\t%s\n" % (time.strftime("%Y-%m-%d %H:%M"), ranked, len(rows), explained,
                                         "\t".join("%.4f" % (solved[s] / asked[s]) if asked[s] else "" for s in SCHEMAS)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "policy", "report"])
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--game-nodes", type=int, default=100000, help="the nodes a move the league plays at")
    args = parser.parse_args()
    dict(run=run, policy=policy, report=report)[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
