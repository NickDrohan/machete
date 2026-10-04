"""Hold the Mach match runner (src/tools/arena.mach) to match.py, game for game.

    python harness/arena_check.py ARENA_EXE ENGINE [--net NET] [--games 40] [--depth 6] [--book BOOK]

At a fixed depth, one thread and a cleared hash (both runners send ucinewgame
before every game), an engine's moves are deterministic, so match.py and the
Mach runner must play the same games from the same openings: the same moves
and the same results, down to where each game stops (mate, stalemate, the
fifty-move rule, a claimable threefold repetition, the ply cap). The check
plays the same match through both, reads both PGNs with python-chess, and
pairs the games by opening and colour. Exit 0 when every game matches.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))


def games_of(path):
    out = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            if game.errors:
                raise SystemExit("unreadable game in {}: {}".format(path, game.errors[0]))
            key = (" ".join(game.board().fen().split()[:4]), game.headers["White"])
            out[key] = ([m.uci() for m in game.mainline_moves()], game.headers["Result"])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arena")
    parser.add_argument("engine")
    parser.add_argument("--net", default="")
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--book", default=os.path.join(HERE, "books", "balanced_200.epd"))
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    work = tempfile.mkdtemp(prefix="arena_check_")
    py_pgn, mach_pgn = os.path.join(work, "match.pgn"), os.path.join(work, "arena.pgn")
    options = []
    if args.net:
        options = ["--option-a", "EvalFile=" + args.net, "--option-b", "EvalFile=" + args.net]
    common = ["--depth", str(args.depth), "--games", str(args.games), "--book", args.book,
              "--concurrency", str(args.concurrency), "--name-a", "A", "--name-b", "B"] + options
    t0 = time.time()
    py = subprocess.run([sys.executable, os.path.join(HERE, "match.py"), args.engine, args.engine,
                         "--watch", "0", "--pgn", py_pgn] + common, capture_output=True, text=True)
    py_s = time.time() - t0
    if py.returncode != 0:
        print(py.stdout[-1500:], py.stderr[-1500:])
        raise SystemExit("match.py failed")
    t0 = time.time()
    mach = subprocess.run([args.arena, args.engine, args.engine, "--pgn", mach_pgn] + common,
                          capture_output=True, text=True)
    mach_s = time.time() - t0
    if mach.returncode != 0:
        print(mach.stdout[-1500:], mach.stderr[-1500:])
        raise SystemExit("the Mach runner failed")
    a, b = games_of(py_pgn), games_of(mach_pgn)
    print("match.py: %d games in %.1fs; Mach: %d games in %.1fs" % (len(a), py_s, len(b), mach_s))
    for label, out in (("match.py", py.stdout), ("mach", mach.stdout)):
        summary = [l for l in out.splitlines() if l.startswith(("games", "score", "elo"))]
        print("  %-8s %s" % (label, " | ".join(summary)))
    bad = 0
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            print("only one side played", key)
            bad += 1
            continue
        (ma, ra), (mb, rb) = a[key], b[key]
        if ma != mb or ra != rb:
            bad += 1
            first = next((i for i in range(min(len(ma), len(mb))) if ma[i] != mb[i]), min(len(ma), len(mb)))
            print("differs: %s as white from %s: result %s vs %s, %d vs %d moves, first difference at move %d"
                  % (key[1], key[0], ra, rb, len(ma), len(mb), first))
    print("IDENTICAL: every game the same" if bad == 0 else "DIFFERENT: %d of %d games" % (bad, len(a)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
