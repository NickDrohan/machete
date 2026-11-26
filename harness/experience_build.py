"""The bot's experience: every position it has been to on its own move, what it played, how those games ended.

    py -3.13 experience_build.py [--check]

Adds the games lichess has that games.json lacks, then writes positions.json and avoid.json (position -> moves the bot
should not repeat), both atomically, so each new game counts from the next one on. Run every few minutes by
orchestrate.py. --check tests the rules on the newer half of the games, flagging from the older half only.

A move is flagged when it has done worse than the opponents' ratings predicted (residual: result less expected score),
over FLAG_VISITS games or more, or when it has only ever lost, REPEAT_LOSSES times or more: the same game lost again.
"""
import argparse
import datetime
import json
import math
import os
import struct
import sys

import chess
import chess.polyglot

sys.path.insert(0, "D:/Dev/Claude/machete-050/harness")
import lichess_review as lr

OUT = "E:/machete/experience/"
FLAG_VISITS = 5
FLAG_RESIDUAL = -0.15
REPEAT_LOSSES = 3
SHORT_PLIES = 20
PANEL_VISITS = 10
PANEL_RESIDUAL = -0.10
VALUE = {"win": 1.0, "draw": 0.5, "loss": 0.0}


def expected(diff):
    return 1 / (1 + 10 ** (diff / 400))


def walk(g):
    side = chess.WHITE if g["me"] == "white" else chess.BLACK
    b = chess.Board()
    try:
        for ply, san in enumerate(g["moves"]):
            m = b.parse_san(san)
            if b.turn == side:
                yield ply, " ".join(b.fen().split()[:4]), m.uci()
            b.push(m)
    except ValueError:
        return


def table_of(games):
    table = {}
    for g in games:
        # a game decided on the clock in its first moves says something about a connection, not a move (lichess's
        # outage of 2026-10-31 lost 1ZN1JY7Q after 1.c4 e5; opponents have also flagged at move 6)
        if g["status"] == "outoftime" and len(g["moves"]) < SHORT_PLIES:
            continue
        i = {"win": 0, "draw": 1, "loss": 2}[g["result"]]
        residual = VALUE[g["result"]] - expected(g["diff"])
        for ply, key, move in walk(g):
            row = table.setdefault(key, {"ply": ply, "moves": {}})
            row["ply"] = min(row["ply"], ply)
            v = row["moves"].setdefault(move, [0, 0, 0, 0.0])
            v[i] += 1
            v[3] += residual
    return table


def flagged(table):
    avoid = {}
    for key, row in table.items():
        for move, v in row["moves"].items():
            n = v[0] + v[1] + v[2]
            if (n >= FLAG_VISITS and v[3] / n < FLAG_RESIDUAL) or (v[2] >= REPEAT_LOSSES and v[2] == n):
                avoid.setdefault(key, []).append(move)
    return avoid


def panel_flags(table):
    """Moves the engine panel's games flag (panel_learn.py): PANEL_VISITS games or more at a residual below PANEL_RESIDUAL.
    Flagged from the panel alone, these moves scored -0.113 on lichess against 0.000 for the panel's other moves
    (2026-11-02, 243 visits). A move lichess itself has played PANEL_VISITS times at a residual no worse than PANEL_RESIDUAL
    is kept: on 2026-11-03 the panel alone (23 games, -0.104) took the Grunfeld's 6...Nxc3 from the bot, which lichess had
    played 45 times at -0.036, and its replacement Nb6 lost to justbot-v1."""
    try:
        panel = json.load(open(OUT + "panel.json"))
    except OSError:
        return {}
    out = {}
    for key, row in panel.items():
        for move, (n, total) in row.items():
            if n < PANEL_VISITS or total / n >= PANEL_RESIDUAL:
                continue
            seen = table.get(key, {}).get("moves", {}).get(move)
            if seen and sum(seen[:3]) >= PANEL_VISITS and seen[3] / sum(seen[:3]) >= PANEL_RESIDUAL:
                continue
            out.setdefault(key, []).append(move)
    return out


def check(games):
    cut = len(games) // 2
    avoid = flagged(table_of(games[:cut]))
    hit, rest = [], []
    for g in games[cut:]:
        (hit if any(move in avoid.get(key, ()) for _, key, move in walk(g)) else rest).append(g)
    def stats(s):
        r = [VALUE[g["result"]] - expected(g["diff"]) for g in s]
        m = sum(r) / max(1, len(r))
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / max(1, len(r) - 1) / max(1, len(r)))
        return m, 1.96 * sd
    print("flagged from the older %d games: %d moves" % (cut, sum(len(v) for v in avoid.values())))
    print("newer games through one: %d, against rating %+.3f +/- %.3f" % ((len(hit),) + stats(hit)))
    print("other newer games:       %d, against rating %+.3f +/- %.3f" % ((len(rest),) + stats(rest)))


# the book against bots rated below the bot (lichess-bot's get_book_move picks it by rating): book.bin with
# weaker_lines()' positions' moves replaced. Ruy Lopez after 8.c3, the closed 8...d6 for the Marshall's 8...d5: against 0.3.0 as
# Black, 500 games each, it won 59% to 53% and drew 34% to 44% (RUY-CLOSED/MARSHALL-VS-030, 2026-11-05), after
# TGkqTnOC drew a Marshall in 143 moves against a bot 270 below.
def weaker_lines():
    """WEAKER_LINES by position key, filled from the moves that reach each position."""
    b = chess.Board()
    for san in "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 O-O c3".split():
        b.push_san(san)
    return {" ".join(b.fen().split()[:4]): {"d7d6": 325}}


# The owner's choices against the queen's pawn (2026-11-15): 1...Nf6 or 1...d5 at random, the Queen's Gambit Declined
# after 1...d5, and 3...d5 in place of the Bogo-Indian (3...Bb4+ scored -0.16 a game over 121 games; Stockfish has
# 3...d5 best). Each move was checked at 20M Stockfish nodes, all within 12 cp of the best. These replace whatever
# the bot's own record put in those positions, avoid list included.
REPERTOIRE_LINES = [
    ("d4", {"Nf6": 60, "d5": 40}),
    ("d4 Nf6 c4 e6 Nf3", {"d5": 100}),
    ("d4 Nf6 c4 e6 Nf3 d5 Nc3", {"Be7": 60, "Bb4": 40}),
    ("d4 Nf6 c4 e6 Nf3 d5 g3", {"Be7": 100}),
    ("d4 d5 c4", {"e6": 100}),
    ("d4 d5 c4 e6 Nc3", {"Nf6": 100}),
    ("d4 d5 c4 e6 Nf3", {"Nf6": 100}),
    ("d4 d5 c4 e6 Nc3 Nf6 Nf3", {"Be7": 60, "Bb4": 40}),
    ("d4 d5 c4 e6 Nc3 Nf6 Bg5", {"Be7": 100}),
    ("d4 d5 c4 e6 Nc3 Nf6 cxd5", {"exd5": 100}),
    ("d4 d5 Nf3", {"Nf6": 100}),
]


def repertoire_lines():
    """REPERTOIRE_LINES by position key, the moves in UCI."""
    out = {}
    for line, moves in REPERTOIRE_LINES:
        b = chess.Board()
        for san in line.split():
            b.push_san(san)
        out[" ".join(b.fen().split()[:4])] = {b.parse_san(m).uci(): w for m, w in moves.items()}
    return out


def write_book(avoid):
    """book.bin in polyglot's format: book_moves.json (book_build.py) less the avoid list, weighted by visits; and
    book_weaker.bin, the same with WEAKER_LINES' moves in their positions."""
    try:
        moves = json.load(open(OUT + "book_moves.json"))
    except OSError:
        return
    chosen = repertoire_lines()
    moves = dict(moves, **chosen)
    # the owner's choice stands over the bot's own record (3...d5 after 3.Nf3 was on the avoid list from 9 games)
    avoid = {k: v for k, v in avoid.items() if k not in chosen}
    write_polyglot(moves, avoid, "book.bin")
    write_polyglot(dict(moves, **weaker_lines()), avoid, "book_weaker.bin")


def write_polyglot(moves, avoid, name):
    rows = []
    for key, kept in moves.items():
        b = chess.Board(key + " 0 1")
        z = chess.polyglot.zobrist_hash(b)
        for uci, n in kept.items():
            if uci in avoid.get(key, ()):
                continue
            m = chess.Move.from_uci(uci)
            to = m.to_square
            if b.is_castling(m):  # polyglot writes castling as the king taking its own rook
                to = chess.square(7 if b.is_kingside_castling(m) else 0, chess.square_rank(m.from_square))
            raw = to | (m.from_square << 6)
            rows.append(struct.pack(">QHHI", z, raw, min(n, 65535), 0))
    rows.sort()
    with open(OUT + name + ".tmp", "wb") as f:
        f.write(b"".join(rows))
    # lichess-bot opens the book for each move: if it holds it right now the next run replaces it
    try:
        os.replace(OUT + name + ".tmp", OUT + name)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    path = OUT + "games.json"
    games = json.load(open(path)) if os.path.exists(path) else []
    if args.check:
        check(games)
        return
    last = max((g["created"] for g in games), default=0)
    since = datetime.datetime.fromtimestamp((last + 60000) / 1000) if last else datetime.datetime.now() - datetime.timedelta(days=400)
    have = {g["id"] for g in games}
    new = [g for g in lr.fetch("E:/machete/lichess-bot/config.yml", since.strftime("%Y-%m-%d %H:%M")) if g["id"] not in have]
    if games and not new:
        return
    games = sorted(games + new, key=lambda g: g["created"])
    json.dump(games, open(path + ".tmp", "w"))
    os.replace(path + ".tmp", path)
    table = table_of(games)
    json.dump(table, open(OUT + "positions.json.tmp", "w"))
    os.replace(OUT + "positions.json.tmp", OUT + "positions.json")
    avoid = flagged(table)
    for key, moves in panel_flags(table).items():
        avoid.setdefault(key, []).extend(m for m in moves if m not in avoid[key])
    json.dump(avoid, open(OUT + "avoid.json.tmp", "w"))
    os.replace(OUT + "avoid.json.tmp", OUT + "avoid.json")
    write_book(avoid)
    print("%d new, %d games, %d positions, %d moves to avoid in %d positions" % (len(new), len(games), len(table), sum(len(v) for v in avoid.values()), len(avoid)))


if __name__ == "__main__":
    main()
