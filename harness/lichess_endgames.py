"""Endgames the lichess bot could have won and drew or lost: where, how, and what kind.

    python harness/lichess_endgames.py --since "2026-10-01 00:00" [--workers 4] [--nodes 1500000]
        [--winning 200] [--out E:/machete/lichess-games/endgames]

An endgame starts when the queens are off the board (the owner's definition,
and the one the three-layer network uses). For every game the bot drew or lost
(lichess_review.fetch; the bot's own token exports them), every position from
the first queenless one on is scored by Stockfish 19 from the bot's side. A
game is a missed win when one of those positions was at least --winning
centipawns for the bot.

In each missed win, the move that let it go is the bot's move with the largest
fall in Stockfish's score taken from a winning position (at least --winning)
to one that is not (under half of it); when no single move does that, the
largest fall from a winning position. Each such move is described by what it
did, so the misses can be counted by kind:

  passer      the bot had a passed pawn before its move and fewer after the
              reply - given up, traded or let go
  trade       the move captured, and Stockfish's choice did not
  king        Stockfish's choice was a king move and the bot's was not
  pawn        the bot pushed a pawn and Stockfish's choice was a piece move
  clock       the bot had under 10 seconds left
  shuffle     the game ended in a repetition or the fifty-move rule while the
              bot was still winning by Stockfish's score: no move threw the
              win away, the bot never found the way in

A miss can be several kinds at once. Writes OUT.jsonl (every missed win with
its score curve) and OUT.txt (the counts and each game, with a link).
"""
import argparse
import collections
import datetime
import json
import multiprocessing
import os
import sys
import time

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "nnue"))
import lichess_review  # noqa: E402
import panel  # noqa: E402


def queenless(board):
    return not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK)


def passers(board, colour):
    """The squares of `colour`'s passed pawns: no enemy pawn ahead on its own or a neighbouring file."""
    theirs = board.pieces(chess.PAWN, not colour)
    found = []
    for sq in board.pieces(chess.PAWN, colour):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        ahead = range(r + 1, 8) if colour == chess.WHITE else range(0, r)
        if not any(chess.square(ff, rr) in theirs for ff in (f - 1, f, f + 1) if 0 <= ff < 8 for rr in ahead):
            found.append(sq)
    return found


def signature(board, colour):
    """The material as 'KRPP v KRP', the bot's side first."""
    def side(c):
        return "K" + "".join(sym * len(board.pieces(kind, c)) for kind, sym in
                             ((chess.ROOK, "R"), (chess.BISHOP, "B"), (chess.KNIGHT, "N"), (chess.PAWN, "P")))
    return side(colour) + " v " + side(not colour)


def watch_parent(parent):
    """Pool initializer: a worker whose main process has gone exits, taking its Stockfish with it.
    On 2026-10-14 the main process died twice and its workers ran Stockfish for hours with nowhere to send results."""
    import threading

    def alive():
        # not os.kill(parent, 0): on Windows that terminates the process instead of testing it
        import ctypes
        k = ctypes.windll.kernel32
        handle = k.OpenProcess(0x1000, False, parent)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(handle, ctypes.byref(code))
        k.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE

    def watch():
        while True:
            time.sleep(10)
            if not alive():
                os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


def score_curve(sf, boards, start, colour, nodes):
    curve = []
    for i in range(start, len(boards)):
        b = boards[i]
        # the fifty-move rule and threefold repetition end a lichess game by
        # themselves; scored as live positions they read as wins Stockfish
        # could still play for, which they are not
        if b.is_game_over(claim_draw=True) or b.halfmove_clock >= 100:
            outcome = b.outcome(claim_draw=True)
            if outcome is None:
                curve.append(dict(ply=i, s=0, best=None))
                continue
            s = 0 if outcome.winner is None else (3000 if outcome.winner == colour else -3000)
            curve.append(dict(ply=i, s=s, best=None))
            continue
        info = sf.analyse(b, chess.engine.Limit(nodes=nodes))
        pv = info.get("pv")
        curve.append(dict(ply=i, s=info["score"].pov(colour).score(mate_score=3000), best=pv[0].uci() if pv else None))
    return curve


def analyse(item):
    game, nodes, winning, screen = item
    colour = chess.WHITE if game["me"] == "white" else chess.BLACK
    board = chess.Board()
    boards = []
    for san in game["moves"]:
        boards.append(board.copy())
        board.push_san(san)
    boards.append(board.copy())
    start = next((i for i, b in enumerate(boards) if queenless(b)), None)
    if start is None:
        return dict(game, endgame=None)
    sf = panel.open_engine("Stockfish", 128)
    # a quick pass first: an endgame Stockfish never puts the bot near
    # winning at `screen` nodes is not searched deeply. The bar for the deep
    # pass is half of --winning, so a position a shallow search undervalues
    # by up to a pawn still gets its deep look.
    curve = score_curve(sf, boards, start, colour, screen) if screen else None
    screened = curve is not None and max(c["s"] for c in curve) < winning / 2
    if not screened:
        curve = score_curve(sf, boards, start, colour, nodes)
    panel.quiet_quit(sf)
    peak = max(curve, key=lambda c: c["s"])
    row = dict(game, endgame=start, curve=curve, peak=peak["s"], peak_ply=peak["ply"], screened=screened)
    if peak["s"] < winning:
        return row
    at = {c["ply"]: c for c in curve}
    mine = []
    for c in curve:
        i = c["ply"]
        if i >= len(game["moves"]) or boards[i].turn != colour or i + 1 not in at:
            continue
        before, after = c["s"], at[i + 1]["s"]
        b = boards[i]
        move = b.parse_san(game["moves"][i])
        best = chess.Move.from_uci(c["best"]) if c["best"] else None
        reply = boards[i + 2] if i + 2 < len(boards) else boards[i + 1]
        kinds = []
        if len(passers(reply, colour)) < len(passers(b, colour)):
            kinds.append("passer")
        if b.is_capture(move) and not (best and b.is_capture(best)):
            kinds.append("trade")
        if best and b.piece_type_at(best.from_square) == chess.KING and b.piece_type_at(move.from_square) != chess.KING:
            kinds.append("king")
        if b.piece_type_at(move.from_square) == chess.PAWN and best and b.piece_type_at(best.from_square) != chess.PAWN:
            kinds.append("pawn")
        clocks = game.get("clocks") or []
        left = clocks[i] / 100.0 if i < len(clocks) else None
        if left is not None and left < 10:
            kinds.append("clock")
        mine.append(dict(ply=i, move=game["moves"][i], best=b.san(best) if best else None, before=before, after=after,
                         fall=before - after, kinds=kinds, fen=b.fen(), material=signature(b, colour),
                         passers=len(passers(b, colour)), clock=left, men=len(b.piece_map())))
    gone = [m for m in mine if m["before"] >= winning and m["after"] < winning / 2]
    culprit = max(gone or [m for m in mine if m["before"] >= winning] or [None], key=lambda m: m["fall"] if m else 0)
    end = boards[-1]
    shuffle = (end.is_repetition(3) or end.halfmove_clock >= 100) and curve[-1]["s"] != 0 and \
        max(c["s"] for c in curve[-12:]) >= winning
    if culprit is None or (shuffle and culprit["fall"] < winning / 2):
        culprit = dict(culprit or {}, kinds=(culprit or {}).get("kinds", []) + ["shuffle"])
    elif shuffle:
        culprit["kinds"].append("shuffle")
    row.update(missed=True, culprit=culprit, falls=sorted(mine, key=lambda m: -m["fall"])[:5],
               ending="repetition" if end.is_repetition(3) else ("fifty" if end.halfmove_clock >= 100 else game["status"]))
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="local time, 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--config", default="E:/machete/lichess-bot/config.yml")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--nodes", type=int, default=1500000)
    parser.add_argument("--winning", type=int, default=200)
    parser.add_argument("--screen", type=int, default=100000,
                        help="nodes for the quick first pass (0 to search every endgame deeply)")
    parser.add_argument("--out", default="E:/machete/lichess-games/endgames")
    args = parser.parse_args()

    games = lichess_review.fetch(args.config, args.since)
    with open(args.out + "_games.ndjson", "w", encoding="utf-8") as f:
        for g in games:
            f.write(json.dumps(g) + "\n")
    nonwins = [g for g in games if g["result"] != "win"]
    print("{} games since {}: {} not won".format(len(games), args.since, len(nonwins)), flush=True)
    # every game's analysis is kept as it finishes, and a rerun skips the games
    # already done: the first run died after hours with nothing saved
    done_path = args.out + "_done.jsonl"
    rows = []
    if os.path.exists(done_path):
        with open(done_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.endswith("\n")]
    have = {r["id"] for r in rows}
    # the games most likely to hold a missed win first: draws, then against the lowest-rated opponents
    todo = sorted((g for g in nonwins if g["id"] not in have), key=lambda g: (g["result"] != "draw", g["diff"]))
    print("{} already analysed, {} to go".format(len(rows), len(todo)), flush=True)
    with multiprocessing.Pool(args.workers, initializer=watch_parent, initargs=(os.getpid(),)) as pool, open(done_path, "a", encoding="utf-8") as done:
        for n, row in enumerate(pool.imap_unordered(analyse, [(g, args.nodes, args.winning, args.screen) for g in todo], chunksize=1)):
            rows.append(row)
            done.write(json.dumps(row) + "\n")
            done.flush()
            if n % 50 == 49:
                print("  {} of {}".format(n + 1, len(todo)), flush=True)
    rows = [r for r in rows if r["id"] in {g["id"] for g in nonwins}]
    reached = [r for r in rows if r.get("endgame") is not None]
    missed = [r for r in rows if r.get("missed")]
    with open(args.out + ".jsonl", "w", encoding="utf-8") as f:
        for r in missed:
            f.write(json.dumps(r) + "\n")

    out = []
    c = collections.Counter(g["result"] for g in games)
    out.append("{} games since {}: {} W {} D {} L".format(len(games), args.since, c["win"], c["draw"], c["loss"]))
    out.append("{} not won, {} of them reached an endgame (queens off), {} with the bot at +{} or better there".format(
        len(nonwins), len(reached), len(missed), args.winning))
    out.append("  of those, drawn {} and lost {}; against lower-rated opponents {}".format(
        sum(r["result"] == "draw" for r in missed), sum(r["result"] == "loss" for r in missed), sum(r["diff"] < 0 for r in missed)))
    kinds = collections.Counter(k for r in missed for k in r["culprit"].get("kinds", []))
    out.append("")
    out.append("what the move that let the win go did (a miss can be several):")
    for k, n in kinds.most_common():
        out.append("  {:<8} {}".format(k, n))
    out.append("  (none)   {}".format(sum(1 for r in missed if not r["culprit"].get("kinds"))))
    mats = collections.Counter(r["culprit"].get("material", "?") for r in missed)
    out.append("")
    out.append("material when it went (bot first):")
    for m, n in mats.most_common(12):
        out.append("  {:<22} {}".format(m, n))
    out.append("")
    for r in sorted(missed, key=lambda r: -r["peak"]):
        m = r["culprit"]
        day = datetime.datetime.fromtimestamp(r["created"] / 1000).strftime("%m-%d")
        out.append("https://lichess.org/{}  {} {:<5} vs {} ({:+d})  {} by {}, {}, peak +{} at ply {}".format(
            r["id"], day, r["me"], r["opp"], r["diff"], r["result"], r["ending"], r["speed"], r["peak"], r["peak_ply"]))
        if m.get("move"):
            out.append("    ply {} {} ({:+d} -> {:+d}), Stockfish {}; {}; {} passed pawn(s); clock {}; kinds: {}".format(
                m["ply"], m["move"], m["before"], m["after"], m["best"], m["material"], m["passers"],
                "{:.0f}s".format(m["clock"]) if m["clock"] is not None else "?", ", ".join(m["kinds"]) or "-"))
            out.append("    " + m["fen"])
        else:
            out.append("    no single move: kinds {}".format(", ".join(m.get("kinds", []))))
    text = "\n".join(out)
    open(args.out + ".txt", "w", encoding="utf-8").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
