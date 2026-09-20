"""Check UCI behaviour that a normal game never exercises.

    python harness/protocol.py ENGINE

Drives the engine directly over its pipes, rather than through python-chess,
so it can time `stop` and feed it malformed input. Exits non-zero on the first
failure, naming it.
"""

import os
import subprocess
import sys
import time

# generous, because a loaded machine must not fail a protocol claim;
# the latency claims below time themselves rather than relying on this
TIMEOUT = 40.0


class Engine(object):
    def __init__(self, path):
        self.p = subprocess.Popen([os.path.abspath(path)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, universal_newlines=True, bufsize=1)

    def send(self, command):
        self.p.stdin.write(command + "\n")
        self.p.stdin.flush()

    def wait_for(self, prefix):
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine closed its output waiting for '{}'".format(prefix))
            if line.startswith(prefix):
                return line.strip()
        raise RuntimeError("timed out waiting for '{}'".format(prefix))


def check(name, condition, detail=""):
    if condition:
        print("  ok   {}".format(name))
        return 0
    print("  FAIL {} {}".format(name, detail))
    return 1


def main():
    engine = Engine(sys.argv[1])
    failures = 0
    try:
        engine.send("uci")
        engine.wait_for("uciok")
        engine.send("isready")
        failures += check("isready answers readyok", engine.wait_for("readyok") == "readyok")

        # stop must interrupt an infinite search promptly
        engine.send("position startpos")
        engine.send("go infinite")
        time.sleep(0.5)
        start = time.time()
        engine.send("stop")
        best = engine.wait_for("bestmove")
        elapsed = (time.time() - start) * 1000
        failures += check("stop returns bestmove within 500ms",
                          elapsed < 500, "took {:.0f} ms".format(elapsed))
        failures += check("stop returns a real move", len(best.split()) > 1 and best.split()[1] != "0000", best)

        # isready must be answered while a search is running
        engine.send("go infinite")
        time.sleep(0.2)
        engine.send("isready")
        failures += check("isready answered mid-search", engine.wait_for("readyok") == "readyok")
        engine.send("stop")
        engine.wait_for("bestmove")

        # malformed input must not take the engine down
        engine.send("position fen not-a-fen")
        engine.send("position startpos moves e2e4 z9z9")
        engine.send("wibble")
        engine.send("isready")
        failures += check("survives malformed input", engine.wait_for("readyok") == "readyok")

        # a mate is reported as a mate score, not a centipawn score
        engine.send("position fen 8/8/5K1k/8/R7/8/8/8 w - - 7 84")
        engine.send("go depth 3")
        seen_mate = False
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            line = engine.p.stdout.readline()
            if "score mate" in line:
                seen_mate = True
            if line.startswith("bestmove"):
                failures += check("finds the mate from a fen position",
                                  line.split()[1] == "a4h4", line.strip())
                break
        failures += check("reports a mate score", seen_mate)

        engine.send("quit")
        failures += check("exits cleanly on quit", engine.p.wait(timeout=5) == 0)
    finally:
        if engine.p.poll() is None:
            engine.p.kill()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
