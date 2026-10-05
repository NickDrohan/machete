"""A self-play league between the two Raspberry Pis, and whether Stockfish likes its moves.

    python harness/rl/league.py deploy --engine out/linux-aarch64/release/bin/machete --net START.nnue
    python harness/rl/league.py play   [--games 40] [--nodes 30000] [--concurrency 1]
    python harness/rl/league.py judge  [--sample 400] [--judge-nodes 300000]
    python harness/rl/league.py train  [--epochs 3] [--lr 0.0002] [--window 4]
    python harness/rl/league.py loop   [--generations 0]         # play, judge, train, promote, repeat
    python harness/rl/league.py status

pi-01 plays the champion network and pi-02 the challenger; in generation 0
both play the starting network. The controller runs here on the PC and
speaks UCI to one engine on each Pi through ssh, so each Pi searches its own
moves and nothing but moves crosses the network. A move is a fixed number of
nodes, not a clock, so the ssh round trip costs nothing in strength.

One generation:

  play    every opening of the book twice, colours swapped. Each position
          the mover was not in check in and had not seen before is written
          with the mover's own search score and, when the game ends, its
          result: the league's training chunk for that generation, in the
          trainer's record format.
  judge   Stockfish 19 on the PC looks at a sample of the moves played and
          says how good they were: how often the move was its first choice,
          how often among its first three, and how many centipawns it gave
          up. This is the league's yardstick. It is never a training signal:
          the league learns only from its own searches and results.
  train   the champion is trained on (--init) for a few epochs on the last
          --window generations' chunks, target a blend of search score and
          game result: the next challenger.
  promote a challenger that scored 55% or more against the champion in its
          own generation's games becomes the champion.

State is in --dir (default E:/machete/rl): state.json, one folder a
generation, nets/, and approval.tsv, the record of Stockfish's verdict by
generation. Every step is resumable from state.json.

The Pis must already hold the engine and networks (`deploy` copies them; the
engine is cross-compiled here with `mach build . -p release -a machete -t
linux-aarch64`). No repository or credential goes to a Pi.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import random
import subprocess
import sys
import time

import chess
import chess.engine
import chess.pgn
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nnue"))
import gen  # noqa: E402  (encode, score_of, position_key and its adjudication constants)
import panel  # noqa: E402

SSH = "C:/Program Files/Git/usr/bin/ssh.exe"
SCP = "C:/Program Files/Git/usr/bin/scp.exe"
KEY = "C:/Users/Arman/.ssh/machete_farm"
PIS = {"pi-01": dict(host="192.168.1.151", jump=None), "pi-02": dict(host="192.168.1.165", jump="192.168.1.151")}
REMOTE = "machete/rl"
BOOK = os.path.join(HERE, "..", "books", "balanced_200.epd")
PROMOTE_AT = 0.55
MAX_PLIES = 300


def ssh_options(pi):
    opts = ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30"]
    if PIS[pi]["jump"]:
        opts += ["-o", "ProxyCommand=\"%s\" -i %s -o BatchMode=yes -W %%h:%%p rabbit@%s" % (SSH, KEY, PIS[pi]["jump"])]
    return opts


def remote(pi, command, check=True):
    return subprocess.run([SSH] + ssh_options(pi) + ["rabbit@" + PIS[pi]["host"], command],
                          capture_output=True, text=True, timeout=600, check=check).stdout.strip()


def copy(pi, local, target):
    subprocess.run([SCP, "-q"] + ssh_options(pi) + [local.replace("\\", "/"), "rabbit@%s:%s" % (PIS[pi]["host"], target)],
                   check=True, timeout=1800)


def open_remote(pi, net):
    """A UCI engine on a Pi, through ssh, with its network set."""
    engine = chess.engine.SimpleEngine.popen_uci(
        [SSH] + ssh_options(pi) + ["rabbit@" + PIS[pi]["host"], "cd %s && exec ./machete" % REMOTE], timeout=60)
    engine.configure({"EvalFile": "/home/rabbit/%s/nets/%s" % (REMOTE, net), "Threads": 1, "Repertoire": 0})
    return engine


def load_state(folder):
    path = os.path.join(folder, "state.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return dict(generation=0, champion=None, challenger=None, history=[])


def save_state(folder, state):
    tmp = os.path.join(folder, "state.json.tmp")
    json.dump(state, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, os.path.join(folder, "state.json"))


def gen_dir(folder, generation):
    path = os.path.join(folder, "gen-%03d" % generation)
    os.makedirs(path, exist_ok=True)
    return path


# ---- deploy ----

def deploy(args, state):
    os.makedirs(os.path.join(args.dir, "nets"), exist_ok=True)
    name = os.path.basename(args.net)
    local = os.path.join(args.dir, "nets", name)
    if os.path.abspath(args.net) != os.path.abspath(local):
        open(local, "wb").write(open(args.net, "rb").read())
    for pi in PIS:
        remote(pi, "mkdir -p %s/nets" % REMOTE)
        if args.engine:
            copy(pi, args.engine, "%s/machete.new" % REMOTE)
            remote(pi, "cd %s && chmod +x machete.new && mv machete.new machete" % REMOTE)
        copy(pi, local, "%s/nets/%s" % (REMOTE, name))
        print("%s: %s" % (pi, remote(pi, "cd %s && printf 'uci\\nquit\\n' | ./machete | grep 'id name'; ls nets | tr '\\n' ' '" % REMOTE)))
    if state["champion"] is None:
        state["champion"] = state["challenger"] = name
        save_state(args.dir, state)
        print("generation 0 starts from %s on both Pis" % name)


def push_net(folder, name):
    for pi in PIS:
        copy(pi, os.path.join(folder, "nets", name), "%s/nets/%s" % (REMOTE, name))


# ---- play ----

def play_game(champion, challenger, fen, champion_white, nodes, rng):
    """One game; returns (records with the side that moved, result, pgn game, the moves for judging)."""
    board = chess.Board(fen)
    engines = {champion_white: champion, not champion_white: challenger}
    limit = chess.engine.Limit(nodes=nodes)
    rows, turns, moves, seen, decided, outcome = [], [], [], {}, 0, "1/2-1/2"
    start = board.copy()
    while True:
        if board.is_checkmate():
            outcome = "0-1" if board.turn == chess.WHITE else "1-0"
            break
        if board.is_stalemate() or board.halfmove_clock >= 100 or board.is_insufficient_material() or board.ply() - start.ply() >= MAX_PLIES:
            break
        key = gen.position_key(board)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3:
            break
        info = engines[board.turn].analyse(board, limit)
        move = info.get("pv", [None])[0]
        if move is None or move not in board.legal_moves:
            move = engines[board.turn].play(board, limit).move
        score = gen.score_of(info, board.turn)
        who = "champion" if (board.turn == chess.WHITE) == champion_white else "challenger"
        if seen[key] == 1 and not board.is_check():
            rows.append(gen.encode(board, score, 1))
            turns.append(board.turn)
        moves.append(dict(fen=board.fen(), move=move.uci(), who=who, score=score, nodes=info.get("nodes")))
        if abs(score) >= gen.ADJUDICATE_AT:
            decided += 1
            if decided >= gen.ADJUDICATE_PLIES:
                ahead = board.turn if score > 0 else not board.turn
                outcome = "1-0" if ahead == chess.WHITE else "0-1"
                break
        else:
            decided = 0
        board.push(move)
    for row, turn in zip(rows, turns):  # the result from the side to move: 0 lost, 1 drew, 2 won
        if outcome != "1/2-1/2":
            row["result"] = 2 if (outcome == "1-0") == (turn == chess.WHITE) else 0
    game = chess.pgn.Game.from_board(board)
    game.headers.update(White="champion" if champion_white else "challenger", Black="challenger" if champion_white else "champion", Result=outcome)
    return rows, outcome, game, moves


def play(args, state):
    folder = gen_dir(args.dir, state["generation"])
    done_path = os.path.join(folder, "games.jsonl")
    finished = set()
    if os.path.exists(done_path):
        finished = {json.loads(l)["game"] for l in open(done_path, encoding="utf-8")}
    book = [l.strip() for l in open(args.book, encoding="utf-8") if l.strip() and not l.startswith("#")]
    rng = random.Random(1000 + state["generation"])
    openings = rng.sample(book, min(len(book), (args.games + 1) // 2))
    jobs = [(2 * i + side, fen, side == 0) for i, fen in enumerate(openings) for side in (0, 1)][:args.games]
    jobs = [j for j in jobs if j[0] not in finished]
    print("generation %d: %s (pi-01) against %s (pi-02), %d games to play at %d nodes a move" % (
        state["generation"], state["champion"], state["challenger"], len(jobs), args.nodes), flush=True)

    def worker(batch):
        champion = open_remote("pi-01", state["champion"])
        challenger = open_remote("pi-02", state["challenger"])
        try:
            for number, fen, champion_white in batch:
                rows, outcome, game, moves = play_game(champion, challenger, fen, champion_white, args.nodes, rng)
                with lock:
                    with open(os.path.join(folder, "chunk.bin"), "ab") as f:
                        f.write(np.array(rows, dtype=gen.RECORD).tobytes())
                    with open(os.path.join(folder, "games.pgn"), "a", encoding="utf-8") as f:
                        f.write(str(game) + "\n\n")
                    with open(os.path.join(folder, "moves.jsonl"), "a", encoding="utf-8") as f:
                        for m in moves:
                            f.write(json.dumps(dict(m, game=number)) + "\n")
                    points = 0.5 if outcome == "1/2-1/2" else float((outcome == "1-0") != champion_white)
                    with open(done_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(dict(game=number, result=outcome, challenger=points, plies=len(moves), positions=len(rows))) + "\n")
                    print("  game %3d: %s in %d plies (challenger %.1f)" % (number, outcome, len(moves), points), flush=True)
        finally:
            for e in (champion, challenger):
                try:
                    e.quit()
                except Exception:
                    pass

    import threading
    lock = threading.Lock()
    batches = [jobs[i::args.concurrency] for i in range(args.concurrency)]
    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as pool:
        list(pool.map(worker, [b for b in batches if b]))
    games = [json.loads(l) for l in open(done_path, encoding="utf-8")]
    score = sum(g["challenger"] for g in games) / max(1, len(games))
    summary = dict(games=len(games), challenger_score=score, positions=sum(g["positions"] for g in games))
    json.dump(summary, open(os.path.join(folder, "play.json"), "w"))
    print("generation %d: %d games, challenger scored %.1f%%, %d positions" % (state["generation"], len(games), 100 * score, summary["positions"]))
    return summary


# ---- judge ----

def judge(args, state):
    folder = gen_dir(args.dir, state["generation"])
    moves = [json.loads(l) for l in open(os.path.join(folder, "moves.jsonl"), encoding="utf-8")]
    rng = random.Random(7 + state["generation"])
    moves = [m for m in moves if abs(m["score"]) < 600]  # decided positions say little about move quality
    sample = rng.sample(moves, min(args.sample, len(moves)))
    sf = panel.open_engine("Stockfish", 256)
    limit = chess.engine.Limit(nodes=args.judge_nodes)
    tally = collections.defaultdict(lambda: dict(n=0, first=0, top3=0, loss=0.0, bad=0))
    for m in sample:
        board = chess.Board(m["fen"])
        played = chess.Move.from_uci(m["move"])
        lines = sf.analyse(board, limit, multipv=3)
        best = lines[0]["score"].pov(board.turn).score(mate_score=3000)
        choices = [l["pv"][0] for l in lines if l.get("pv")]
        if played in choices:
            mine = lines[choices.index(played)]["score"].pov(board.turn).score(mate_score=3000)
        else:
            mine = sf.analyse(board, limit, root_moves=[played])["score"].pov(board.turn).score(mate_score=3000)
        loss = max(0, min(300, best - mine))
        t = tally[m["who"]]
        t["n"] += 1
        t["first"] += played == choices[0]
        t["top3"] += played in choices
        t["loss"] += loss
        t["bad"] += loss >= 100
    panel.quiet_quit(sf)
    report = {}
    for who, t in tally.items():
        report[who] = dict(moves=t["n"], first=t["first"] / t["n"], top3=t["top3"] / t["n"], loss=t["loss"] / t["n"], blunders=t["bad"] / t["n"])
    json.dump(report, open(os.path.join(folder, "judge.json"), "w"), indent=1)
    path = os.path.join(args.dir, "approval.tsv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("generation\tside\tnetwork\tmoves\tfirst_choice\ttop_three\tmean_loss_cp\tlost_100cp\n")
        for who, r in sorted(report.items()):
            f.write("%d\t%s\t%s\t%d\t%.3f\t%.3f\t%.1f\t%.3f\n" % (state["generation"], who, state[who], r["moves"], r["first"], r["top3"], r["loss"], r["blunders"]))
    for who, r in sorted(report.items()):
        print("generation %d %-10s %-22s Stockfish's first choice %.1f%%, in its top three %.1f%%, gave up %.1f cp a move, %.1f%% of moves lost 100+ cp (%d moves)" % (
            state["generation"], who, state[who], 100 * r["first"], 100 * r["top3"], r["loss"], 100 * r["blunders"], r["moves"]))
    return report


# ---- train ----

def train(args, state):
    g = state["generation"]
    chunks = [os.path.join(args.dir, "gen-%03d" % k, "chunk.bin") for k in range(max(0, g - args.window + 1), g + 1)]
    chunks = [c for c in chunks if os.path.exists(c)]
    total = sum(os.path.getsize(c) for c in chunks) // 70
    name = "rl-%03d.nnue" % (g + 1)
    out = os.path.join(args.dir, "nets", name)
    held = max(64, min(20000, total // 10))
    if total < held * 4:
        raise SystemExit("only %d positions in the window: play more games before training" % total)
    command = [sys.executable, "-u", os.path.join(HERE, "..", "nnue", "train.py")] + chunks + [
        "--init", os.path.join(args.dir, "nets", state["champion"]), "--out", out, "--hidden", str(args.hidden),
        "--epochs", str(args.epochs), "--lr", str(args.lr), "--scale", "150", "--blend", str(args.blend),
        "--validation", str(held), "--batch", str(max(32, min(16384, total // 50, held))), "--seed", str(g + 1)]
    print("training %s from %s on %d positions (%d generations)" % (name, state["champion"], total, len(chunks)), flush=True)
    log = open(os.path.join(gen_dir(args.dir, g), "train.log"), "w", encoding="utf-8")
    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    return name


# ---- the loop ----

def advance(args, state, summary, new_net):
    g = state["generation"]
    promoted = g > 0 and summary["challenger_score"] >= PROMOTE_AT
    state["history"].append(dict(generation=g, champion=state["champion"], challenger=state["challenger"],
                                 challenger_score=summary["challenger_score"], games=summary["games"], promoted=promoted))
    if promoted:
        state["champion"] = state["challenger"]
    state["challenger"] = new_net
    state["generation"] = g + 1
    save_state(args.dir, state)
    push_net(args.dir, new_net)
    print("generation %d done: %s; next, %s (champion) against %s" % (g, "challenger promoted" if promoted else "champion kept", state["champion"], new_net), flush=True)


def loop(args, state):
    count = 0
    while not args.generations or count < args.generations:
        summary = play(args, state)
        judge(args, state)
        new_net = train(args, state)
        advance(args, state, summary, new_net)
        count += 1


def status(args, state):
    print("generation %d: champion %s, challenger %s" % (state["generation"], state["champion"], state["challenger"]))
    for h in state["history"]:
        print("  gen %d: %s against %s, challenger %.1f%% over %d games%s" % (
            h["generation"], h["champion"], h["challenger"], 100 * h["challenger_score"], h["games"], ", promoted" if h["promoted"] else ""))
    path = os.path.join(args.dir, "approval.tsv")
    if os.path.exists(path):
        print(open(path, encoding="utf-8").read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["deploy", "play", "judge", "train", "loop", "status"])
    parser.add_argument("--dir", default="E:/machete/rl")
    parser.add_argument("--engine", default="", help="deploy: the aarch64 engine binary")
    parser.add_argument("--net", default="", help="deploy: the starting network")
    parser.add_argument("--book", default=BOOK)
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--nodes", type=int, default=30000, help="nodes a move in the league's games")
    parser.add_argument("--concurrency", type=int, default=1, help="games at once (one engine process a game on each Pi)")
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--judge-nodes", type=int, default=300000, help="Stockfish's nodes a position when judging")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=0.0002)
    parser.add_argument("--blend", type=float, default=0.7, help="how much of the target is the search score; the rest is the game result")
    parser.add_argument("--window", type=int, default=4, help="generations of games trained on")
    parser.add_argument("--hidden", type=int, default=768)
    parser.add_argument("--generations", type=int, default=0, help="loop: 0 runs until stopped")
    args = parser.parse_args()
    os.makedirs(args.dir, exist_ok=True)
    state = load_state(args.dir)
    if args.command == "deploy":
        deploy(args, state)
    elif args.command == "status":
        status(args, state)
    elif args.command == "play":
        play(args, state)
    elif args.command == "judge":
        judge(args, state)
    elif args.command == "train":
        print(train(args, state))
    else:
        loop(args, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
