"""Build machete's attack suite and attack book from engine miniatures.

    python harness/nnue/attack_suite.py PGN [PGN ...] --suite data/attack_suite.epd \
        --book data/attack_book.epd [--workers 8] [--min-plies 40] [--max-plies 100]

A miniature is a decisive engine game shorter than --max-plies (and longer
than --min-plies, which drops crashes and forfeits): one engine beat another
by force, usually by attacking its king. Two things are taken from each.

  The suite: positions where the winner's move was the only one that kept the
  attack - Stockfish 19 at depth 20 rates it at least MARGIN centipawns above
  its second choice, with the winner not yet winning outright (below +600).
  Written as EPD with bm (the move) and the margin, so an engine can be scored
  on how many it finds. It measures whether machete can attack.

  The book: the build-up positions, the winner to move, a little better
  (+30 to +250) in the plies before its score first passes +300. The data
  generator plays games from them, so the network sees attacks develop.

Pass 1 scores every position of a game with SF19 at PASS1_NODES; pass 2 runs
the MultiPV-2 depth-20 check only where the winner's score climbed.

Each finished game is appended to --progress as one JSON line, and a restart
skips the games already there, so a crash or a reboot costs one game per
worker, not the night. A game whose engine fails (a slow start on a busy
machine timed out once and took the whole first run with it) is retried once
and otherwise recorded as failed and skipped.
"""
import argparse
import collections
import json
import multiprocessing
import os
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

PASS1_NODES = 200000
MARGIN = 100
DEPTH = 20


def miniatures(paths, lo, hi):
    out = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            while True:
                try:
                    game = chess.pgn.read_game(handle)
                except Exception:
                    continue
                if game is None:
                    break
                result = game.headers.get("Result")
                if result not in ("1-0", "0-1") or game.board().fen() != chess.STARTING_FEN:
                    continue
                if game.headers.get("Variant", "Standard").lower() not in ("standard", ""):
                    continue
                moves = [m.uci() for m in game.mainline_moves()]
                if lo <= len(moves) < hi:
                    name = "%s-%s %s" % (game.headers.get("White", "?")[:20], game.headers.get("Black", "?")[:20], game.headers.get("Event", "")[:30])
                    out.append(("%d:%d" % (paths.index(path), len(out)), name, result, moves))
    return out


def work(item):
    for attempt in range(2):
        try:
            return item[0], analyse(item)
        except Exception as problem:  # noqa: BLE001 - one bad game must not end the run
            last = repr(problem)
    return item[0], {"failed": last}


def analyse(item):
    _, name, result, moves = item
    winner = chess.WHITE if result == "1-0" else chess.BLACK
    engine = panel.open_engine("Stockfish", 64)
    board = chess.Board()
    curve = []  # (ply, fen, winner's score) for every position
    for ply in range(len(moves)):
        info = engine.analyse(board, chess.engine.Limit(nodes=PASS1_NODES))
        curve.append((ply, board.fen(), info["score"].pov(winner).score(mate_score=3000)))
        board.push_uci(moves[ply])
    suite, book = [], []
    cross = next((p for p, _, s in curve if s >= 300), len(curve))
    for ply, fen, score in curve:
        b = chess.Board(fen)
        if b.turn != winner or b.is_check():
            continue
        if 30 <= score <= 250 and cross - 24 <= ply < cross:
            book.append(fen)
        # pass 2 where the winner's score climbs over the next two plies
        nxt = curve[ply + 2][2] if ply + 2 < len(curve) else None
        if nxt is None or score >= 600 or nxt - score < 40:
            continue
        infos = engine.analyse(b, chess.engine.Limit(depth=DEPTH), multipv=2)
        if len(infos) < 2 or not infos[0].get("pv"):
            continue
        s1 = infos[0]["score"].pov(winner).score(mate_score=3000)
        s2 = infos[1]["score"].pov(winner).score(mate_score=3000)
        best = infos[0]["pv"][0]
        if best.uci() == moves[ply] and s1 - s2 >= MARGIN and s1 < 600:
            suite.append((fen, b.san(best), s1, s1 - s2, name, ply + 1))
    engine.quit()
    return {"suite": suite, "book": book}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn", nargs="+")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--book", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--min-plies", type=int, default=40)
    parser.add_argument("--max-plies", type=int, default=100)
    parser.add_argument("--progress", default=None, help="one JSON line per finished game; resumes from it")
    args = parser.parse_args()

    games = miniatures(args.pgn, args.min_plies, args.max_plies)
    progress = args.progress or args.suite + ".progress.jsonl"
    finished = {}
    if os.path.exists(progress):
        for line in open(progress, encoding="utf-8"):
            row = json.loads(line)
            finished[row["key"]] = row
    todo = [g for g in games if g[0] not in finished]
    print("%d miniatures, %d already done, %d to go" % (len(games), len(finished), len(todo)), flush=True)
    with open(progress, "a", encoding="utf-8") as log, multiprocessing.Pool(args.workers) as pool:
        for key, out in pool.imap_unordered(work, todo, chunksize=1):
            out["key"] = key
            log.write(json.dumps(out) + "\n")
            log.flush()
            finished[key] = out
            if len(finished) % 50 == 0:
                print("%d/%d games" % (len(finished), len(games)), flush=True)
    suite, book, failed = [], [], 0
    for row in finished.values():
        if "failed" in row:
            failed += 1
            continue
        suite += [tuple(x) for x in row["suite"]]
        book += row["book"]
    print("%d games failed twice and were skipped" % failed, flush=True)
    seen = set()
    with open(args.suite, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# %d attack positions from %d engine miniatures, written by harness/nnue/attack_suite.py:\n" % (len(suite), len(games)))
        handle.write("# the winner's move, which Stockfish 19 at depth %d rates %d+ cp above its second choice\n" % (DEPTH, MARGIN))
        for fen, san, s1, margin, name, ply in suite:
            key = " ".join(fen.split()[:4])
            if key in seen:
                continue
            seen.add(key)
            handle.write('%s bm %s; c0 "sf19 %+d margin %d"; id "%s ply %d";\n' % (key, san, s1, margin, name.replace('"', ""), ply))
    unique = list(dict.fromkeys(book))
    with open(args.book, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# %d attack build-up positions (winner to move, +30..+250, before its score passes +300), from %d miniatures\n" % (len(unique), len(games)))
        for fen in unique:
            handle.write(fen + "\n")
    print("suite: %d positions -> %s; book: %d positions -> %s" % (len(seen), args.suite, len(unique), args.book))
    return 0


if __name__ == "__main__":
    sys.exit(main())
