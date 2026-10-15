"""Seed a generation book from games in which stronger engines beat machete.

    python harness/nnue/stomp_seed.py TOURNAMENT.pgn --out book.epd

The comments Arena writes on each move are that engine's eval of the
position it was about to play, in pawns, from its own side. Machete's
numbers are not labels. They only say when its view of the game fell
apart. The other engine's numbers say when it took over.

Two kinds of position go in the book, and the teacher then plays both
sides of every one of them:

  attack   the crusher is to move and its eval has just crossed into a
           real advantage, or is still climbing through +300. Games from
           here are the conversion.
  defend   machete is to move on the ply its own eval dropped hardest,
           and on the two plies before that. Games from here are the
           choice it missed, while the position is still a position.

Draws contribute only the ply where machete's eval was worst, so a hold
is in the book too. The same FEN is written once.
"""

import argparse
import collections
import re

import chess
import chess.pgn

SCORE = re.compile(r"([+-]?\d+\.\d+)/(\d+)")
MAC = "achete"


def cp_of(comment):
    found = SCORE.search(comment or "")
    if not found:
        return None
    return int(round(float(found.group(1)) * 100))


def walk(game):
    """(ply, board_before, cp, machete_moved) for every commented move."""
    white = game.headers.get("White", "")
    mac_white = MAC in white.lower()
    node = game
    ply = 0
    rows = []
    while node.variations:
        nxt = node.variation(0)
        ply += 1
        cp = cp_of(nxt.comment)
        if cp is not None:
            machete_moved = (node.board().turn == chess.WHITE) == mac_white
            rows.append((ply, node.board().copy(), cp, machete_moved))
        node = nxt
    return mac_white, rows


def seeds_of(game):
    """FENs to keep, each tagged attack or defend."""
    mac_white, rows = walk(game)
    result = game.headers.get("Result", "*")
    mac_result = result if mac_white else {"1-0": "0-1", "0-1": "1-0", "1/2-1/2": "1/2-1/2"}.get(result, result)
    kept = []
    mac = [(ply, board, cp) for ply, board, cp, mine in rows if mine]
    opp = [(ply, board, cp) for ply, board, cp, mine in rows if not mine]
    if mac_result == "0-1":
        # the crusher's side of the takeover: first time it crosses each band
        crossed = set()
        for ply, board, cp in opp:
            for band in (80, 150, 300):
                if cp >= band and band not in crossed and cp < 600:
                    crossed.add(band)
                    kept.append((board, "attack"))
            if 40 <= cp <= 250 and ply % 4 == 0:
                kept.append((board, "attack"))
        # machete's worst single drop, and the two looks before it
        worst = None
        for i in range(1, len(mac)):
            drop = mac[i - 1][2] - mac[i][2]
            if worst is None or drop > worst[0]:
                worst = (drop, i)
        if worst is not None and worst[0] >= 40:
            for j in range(max(0, worst[1] - 2), worst[1] + 1):
                kept.append((mac[j][1], "defend"))
        # the move that let the advantage appear, which is much earlier than
        # the move where machete's own eval finally falls
        born = next((ply for ply, _, cp in opp if cp >= 80), None)
        if born is not None:
            earlier = [row for row in mac if row[0] < born]
            if earlier:
                kept.append((earlier[-1][1], "defend"))
    elif mac_result == "1/2-1/2" and mac:
        worst_i = min(range(len(mac)), key=lambda i: mac[i][2])
        kept.append((mac[worst_i][1], "defend"))
    return mac_result, kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgn")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    seen = {}
    summary = collections.Counter()
    games = 0
    with open(args.pgn, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            games += 1
            mac_result, kept = seeds_of(game)
            summary[mac_result] += 1
            for board, kind in kept:
                fen = board.fen()
                if fen not in seen:
                    seen[fen] = kind
                elif seen[fen] != kind:
                    seen[fen] = "both"

    order = sorted(seen, key=lambda fen: (seen[fen], fen))
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        out.write("# seed from %s\n" % args.pgn.replace("\\", "/"))
        out.write("# %d games, machete %s. attack = crusher to move in the takeover;\n"
                  % (games, dict(summary)))
        out.write("# defend = machete to move where its eval fell, or its worst moment of a draw.\n")
        out.write("# one FEN per line, nothing after it: gen.py passes the line to Board().\n")
        out.write("# %s attack, %s defend, %s both.\n" % (
            sum(1 for k in seen.values() if k == "attack"),
            sum(1 for k in seen.values() if k == "defend"),
            sum(1 for k in seen.values() if k == "both")))
        for fen in order:
            out.write(fen + "\n")
    kinds = collections.Counter(seen.values())
    print("{:,} games, {:,} positions ({})".format(games, len(seen), dict(kinds)))
    print("wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
