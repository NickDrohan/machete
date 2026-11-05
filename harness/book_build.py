"""A first opening book, from the bot's own games, so its first moves take no clock (it spent a quarter of it by move 16).

    py -3.13 book_build.py [--workers 4] [--nodes 1000000]

A move enters when the bot has been to the position 10 times or more before ply 30, played the move 5 times or more, it
has done at least about as well as the ratings predicted, it is not on the avoid list, and Stockfish finds it within
MARGIN of the position's best. Writes book_moves.json; experience_build.py turns that into book.bin less whatever
the avoid list says, so a move that starts to lose leaves the book after the next game.
"""
import argparse
import json
import multiprocessing as mp

import chess
import chess.engine

OUT = "E:/machete/experience/"
SF = "C:/Users/Arman/Desktop/Games/Chess/arena_3.5.1/Engines/Stockfish 19/stockfish/stockfish-windows-x86-64-universal.exe"
MARGIN = 30


def check(job):
    key, moves, nodes = job
    e = chess.engine.SimpleEngine.popen_uci(SF, timeout=600)
    e.configure({"Threads": 1, "Hash": 128})
    b = chess.Board(key + " 0 1")
    best = e.analyse(b, chess.engine.Limit(nodes=nodes))["score"].relative.score(mate_score=30000)
    kept, dropped = {}, []
    for uci, n in moves:
        s = e.analyse(b, chess.engine.Limit(nodes=nodes), root_moves=[chess.Move.from_uci(uci)])["score"].relative.score(mate_score=30000)
        if s >= best - MARGIN:
            kept[uci] = n
        else:
            dropped.append((uci, best - s))
    e.quit()
    return key, kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--nodes", type=int, default=1000000)
    args = ap.parse_args()
    table = json.load(open(OUT + "positions.json"))
    avoid = json.load(open(OUT + "avoid.json"))
    jobs = []
    for key, row in table.items():
        total = sum(v[0] + v[1] + v[2] for v in row["moves"].values())
        if row["ply"] >= 30 or total < 10:
            continue
        ok = []
        for uci, v in row["moves"].items():
            n = v[0] + v[1] + v[2]
            if n >= 5 and v[3] / n >= -0.05 and uci not in avoid.get(key, ()):
                ok.append((uci, n))
        if ok:
            jobs.append((key, ok, args.nodes))
    print("%d positions, %d moves to check" % (len(jobs), sum(len(j[1]) for j in jobs)), flush=True)
    book, dropped = {}, 0
    with mp.Pool(args.workers) as pool:
        for k, (key, kept, out) in enumerate(pool.imap_unordered(check, jobs)):
            dropped += len(out)
            if kept:
                book[key] = kept
            if k % 50 == 0:
                print("%d of %d" % (k, len(jobs)), flush=True)
    json.dump(book, open(OUT + "book_moves.json.tmp", "w"))
    import os
    os.replace(OUT + "book_moves.json.tmp", OUT + "book_moves.json")
    print("%d positions and %d moves kept, %d moves dropped by Stockfish" % (len(book), sum(len(v) for v in book.values()), dropped))


if __name__ == "__main__":
    main()
