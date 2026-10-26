"""A trusted held-out set for valuing training data: positions from the games machete actually plays and
loses, scored deeper than any training data.

    python harness/nnue/yardstick.py --pgn GAUNTLET.pgn --games LICHESS.json --out yardstick.bin
        [--sample 40000] [--nodes 1000000] [--workers 8] [--seed 1]

Positions come from an Arena gauntlet's PGN (machete against stronger engines) and from the bot's lichess
games (the JSON lichess_review.fetch returns), plies 12 to 140, every third ply, one copy of each position.
Each is scored by Stockfish 19 at --nodes nodes, single-threaded, so the label does not depend on the
machine's load; the result field is the game's result from the side to move. The records are the trainer's
70-byte format, so holdout.py reads them like any corpus. None of these positions is in any training set.
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys

import chess
import chess.engine
import chess.pgn
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

SF = "C:/Users/Arman/Desktop/Games/Chess/arena_3.5.1/Engines/Stockfish 19/stockfish/stockfish-windows-x86-64-universal.exe"
RESULT = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


def positions_from_moves(moves_san, result_white, out):
    b = chess.Board()
    for ply, san in enumerate(moves_san):
        try:
            b.push_san(san)
        except ValueError:
            return
        n = ply + 1
        if 12 <= n <= 140 and n % 3 == 0 and not b.is_game_over():
            r = result_white if b.turn == chess.WHITE else 1.0 - result_white
            out[" ".join(b.fen().split()[:4])] = (b.fen(), r)


def gather(args):
    found = {}
    if args.pgn:
        f = open(args.pgn, encoding="latin-1")
        while True:
            g = chess.pgn.read_game(f)
            if g is None:
                break
            r = RESULT.get(g.headers.get("Result"))
            if r is None:
                continue
            b = g.board()
            sans = []
            for mv in g.mainline_moves():
                sans.append(b.san(mv))
                b.push(mv)
            positions_from_moves(sans, r, found)
    if args.games:
        for g in json.load(open(args.games)):
            if g.get("status") in ("started", "aborted"):
                continue
            mine = {"win": 1.0, "draw": 0.5, "loss": 0.0}[g["result"]]
            r_white = mine if g["me"] == "white" else 1.0 - mine
            positions_from_moves(g["moves"], r_white, found)
    return found


def label(job):
    fens, nodes = job
    # a generous timeout: on a loaded machine the handshake can take longer than python-chess's 10 s
    e = chess.engine.SimpleEngine.popen_uci(SF, timeout=600)
    e.configure({"Threads": 1, "Hash": 64})
    out = []
    for fen, r in fens:
        b = chess.Board(fen)
        sc = e.analyse(b, chess.engine.Limit(nodes=nodes))["score"].relative.score(mate_score=32000)
        out.append((fen, r, max(-32000, min(32000, sc))))
    e.quit()
    return out


def to_record(fen, r, score):
    b = chess.Board(fen)
    rec = np.zeros(1, dtype=RECORD)[0]
    pieces = sorted(b.piece_map().items())
    rec["stm"] = 0 if b.turn == chess.WHITE else 1
    rec["count"] = len(pieces)
    for k, (sq, p) in enumerate(pieces):
        rec["pieces"][k] = (0 if p.color == chess.WHITE else 1) * 6 + (p.piece_type - 1)
        rec["squares"][k] = sq
    rec["score"] = score
    rec["result"] = int(round(r * 2))
    rec["engine"] = 0
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", default="")
    ap.add_argument("--games", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=40000)
    ap.add_argument("--nodes", type=int, default=1000000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    found = list(gather(args).values())
    random.Random(args.seed).shuffle(found)
    found = found[:args.sample]
    print("%d positions to label at %d nodes" % (len(found), args.nodes), flush=True)
    chunks = [(found[i::args.workers * 8], args.nodes) for i in range(args.workers * 8)]
    # each finished chunk is appended to a .part file at once, so a failure loses one chunk, not the run
    part = args.out + ".part"
    if os.path.exists(part):
        os.remove(part)
    done = 0
    with mp.Pool(args.workers) as pool:
        for k, rows in enumerate(pool.imap_unordered(label, chunks)):
            with open(part, "ab") as f:
                np.array([to_record(*x) for x in rows], dtype=RECORD).tofile(f)
            done += len(rows)
            print("  %d of %d chunks, %d records" % (k + 1, len(chunks), done), flush=True)
    os.replace(part, args.out)
    print("%d records -> %s" % (done, args.out))


if __name__ == "__main__":
    main()
