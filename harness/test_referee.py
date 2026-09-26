"""The referee's claims (harness/referee.py), checked cheaply.

    python harness/test_referee.py [ENGINE] [NETWORK]

1. Pentanomial arithmetic on pairs whose answer is known.
2. A move that overruns its clock is a forfeit for the side to move, and the
   engine is restarted for the next game rather than ending the match.
3. A live match of one pair between two copies of the same engine writes its
   result, and running it again with more games resumes rather than restarts.

Single-threaded and about half a minute, so it can run beside other work.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

import chess
import chess.engine
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as engines  # noqa: E402
import referee  # noqa: E402


HANGING_ENGINE = r"""
import sys
for line in sys.stdin:
    word = line.split()[0] if line.split() else ""
    if word == "uci":
        print("id name hang\noption name Threads type spin default 1 min 1 max 1\nuciok", flush=True)
    elif word == "isready":
        print("readyok", flush=True)
    elif word == "quit":
        break
"""


def check(name, condition, detail=""):
    if condition:
        print("  ok   {}".format(name))
        return 0
    print("  FAIL {} {}".format(name, detail))
    return 1


def main():
    exe = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else engines.MACHETE
    net = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(HERE), "net", "machete.nnue")
    failures = 0

    # 1. arithmetic
    counts, mean, elo, margin = referee.pentanomial([1.0] * 10)
    failures += check("all drawn pairs: score 0.5, elo 0, no spread",
                      counts == [0, 0, 10, 0, 0] and mean == 0.5 and elo == 0.0 and margin == 0.0,
                      str((counts, mean, elo, margin)))
    counts, mean, elo, margin = referee.pentanomial([2.0, 2.0, 1.0, 1.0])
    failures += check("pairs 2,2,1,1: score 0.75, elo +190.8",
                      counts == [0, 0, 2, 0, 2] and mean == 0.75 and abs(elo - 190.85) < 0.1,
                      str((counts, mean, elo)))
    # the point of pairing: [2,0] pairs (one win each way) look noisier per game
    # than per pair only if the pair is ignored; pairs of 1.0 are certain draws
    _, _, _, pent = referee.pentanomial([1.0, 1.0, 1.5, 0.5] * 25)
    _, _, tri = referee.trinomial([1, 0, 0.5, 0.5, 1, 0.5, 0.5, 0] * 25)
    failures += check("pentanomial interval narrower than trinomial on the same games",
                      pent < tri, "pentanomial {:.1f}, trinomial {:.1f}".format(pent, tri))

    work = tempfile.mkdtemp(prefix="referee-test-")
    try:
        for side in ("a", "b"):
            os.makedirs(os.path.join(work, side))
            shutil.copy(exe, os.path.join(work, side, "machete.exe"))
            shutil.copy(net, os.path.join(work, side, "machete.nnue"))

        # 2. the watchdog, against a stub engine that accepts `go` and never answers
        stub = os.path.join(work, "hang.py")
        with open(stub, "w") as f:
            f.write(HANGING_ENGINE)
        saved = referee.WATCHDOG_S
        referee.WATCHDOG_S = 0.5
        player = referee.Player("a", os.path.join(work, "a"))
        real_path = player.path
        player.path = [sys.executable, stub]
        player.start()
        board = chess.Board()
        limit = chess.engine.Limit(white_clock=0.2, black_clock=0.2, white_inc=0, black_inc=0)
        caught = []

        def attempt():
            try:
                player.play(board, limit)
            except referee.Forfeit as f:
                caught.append(f)
        # on its own thread, so a watchdog that does not fire fails this test
        # instead of hanging it
        attempt_thread = threading.Thread(target=attempt)
        attempt_thread.daemon = True
        attempt_thread.start()
        attempt_thread.join(15)
        referee.WATCHDOG_S = saved
        forfeited = caught[0] if caught else None
        if attempt_thread.is_alive():
            forfeited = None
            pid = player.engine.transport.get_pid()
            psutil.Process(pid).kill()
            attempt_thread.join(5)
            player.engine = None
        failures += check("a move past its clock is a forfeit for the side to move",
                          forfeited is not None and forfeited.color == chess.WHITE
                          and "hung" in forfeited.why, repr(forfeited))
        failures += check("the forfeiting engine is stopped", player.engine is None)
        player.path = real_path
        again = player.start().engine.play(board, chess.engine.Limit(depth=2))
        failures += check("and restarts for the next game", again.move in board.legal_moves)
        player.stop()

        # 3. a live pair, then a resume
        out = os.path.join(work, "final.json")
        base = [sys.executable, os.path.join(HERE, "referee.py"),
                "--a", "one=" + os.path.join(work, "a"), "--b", "two=" + os.path.join(work, "b"),
                "--tc", "1+0.01", "--concurrency", "1", "--watch", "0", "--out", out]
        first = subprocess.run(base + ["--games", "2"], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True, timeout=300)
        with open(out) as f:
            state = json.load(f)
        played = [p for p in state["pairs"] if p]
        failures += check("a pair is played and recorded",
                          first.returncode == 0 and len(played) == 1 and len(played[0]["a_games"]) == 2,
                          first.stdout[-400:])
        failures += check("the report carries the pentanomial line", "pentanomial" in first.stdout,
                          first.stdout[-400:])
        second = subprocess.run(base + ["--games", "4"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, timeout=300)
        with open(out) as f:
            state = json.load(f)
        failures += check("rerun with more games resumes: one pair kept, one added",
                          "resuming: 1 of 2" in second.stdout and all(state["pairs"]),
                          second.stdout[-400:])
        failures += check("games reach the PGN", os.path.exists(os.path.join(work, "final.pgn")))

        # 4. pooling two time controls into one verdict
        other = os.path.join(work, "other.json")
        with open(other, "w") as f:
            json.dump({"a": "one", "b": "two", "tc": "180+2", "book": "x",
                       "pairs": [{"a_games": [1.0, 1.0], "a_points": 2.0, "notes": ["normal", "normal"]}] * 3}, f)
        pooled = subprocess.run([sys.executable, os.path.join(HERE, "referee.py"), "pool", out, other],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=60)
        failures += check("pool reports every pair of both matches and names a result",
                          pooled.returncode == 0 and "5 pairs" in pooled.stdout and "result:" in pooled.stdout,
                          pooled.stdout[-400:])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
