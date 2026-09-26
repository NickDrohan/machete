"""Check UCI behaviour that a normal game never exercises.

    python harness/protocol.py ENGINE

Drives the engine directly over its pipes, rather than through python-chess,
so it can time `stop` and feed it malformed input. Exits non-zero on the first
failure, naming it.
"""

import os
import queue
import subprocess
import sys
import threading
import time

# generous, because a loaded machine must not fail a protocol claim;
# the latency claims below time themselves rather than relying on this
TIMEOUT = 40.0


class Engine(object):
    """The engine on pipes, its output read on a thread.

    A blocking readline() cannot time out: an engine that falls silent would
    hang the gate for ever rather than fail it, which is what happened the
    first time a ponder gate was perturbed.
    """

    def __init__(self, path):
        self.p = subprocess.Popen([os.path.abspath(path)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, universal_newlines=True, bufsize=1)
        self.lines = queue.Queue()
        reader = threading.Thread(target=self._pump)
        reader.daemon = True
        reader.start()

    def _pump(self):
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, command):
        self.p.stdin.write(command + "\n")
        self.p.stdin.flush()

    def readline(self, deadline):
        try:
            line = self.lines.get(timeout=max(0.0, deadline - time.time()))
        except queue.Empty:
            return ""
        if line is None:
            raise RuntimeError("engine closed its output")
        return line

    def read_until(self, prefix):
        """Every line up to and including the first that starts with prefix."""
        lines = []
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            line = self.readline(deadline)
            if not line:
                break
            lines.append(line.strip())
            if line.startswith(prefix):
                return lines
        raise RuntimeError("timed out after {:.0f} s waiting for '{}'".format(TIMEOUT, prefix))

    def wait_for(self, prefix):
        return self.read_until(prefix)[-1]


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
        uci_lines = engine.read_until("uciok")
        failures += check("advertises the Ponder option",
                          any(line.startswith("option name Ponder ") for line in uci_lines))
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

        # go nodes: a node-limited search stops at the limit, and after
        # ucinewgame the same request gives the same answer - which is what
        # makes a fixed-node test immune to the load on the machine
        answers = []
        for _ in range(2):
            engine.send("ucinewgame")
            engine.send("position fen r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
            engine.send("go nodes 10000")
            lines = engine.read_until("bestmove")
            counts = [int(line.split()[line.split().index("nodes") + 1])
                      for line in lines if line.startswith("info") and " nodes " in line]
            answers.append((lines[-1], counts))
        (best, counts), (again, _) = answers
        failures += check("go nodes 10000 answers, reporting at most 10000 nodes",
                          best.split()[1] != "0000" and counts and max(counts) <= 10000,
                          "{} after {}".format(best, counts))
        failures += check("go nodes gives the same answer twice", best == again,
                          "{} then {}".format(best, again))

        # pondering: the engine names the reply it expects, and searches it
        # without answering until the GUI says the reply was played
        engine.send("position startpos")
        engine.send("go depth 6")
        parts = engine.wait_for("bestmove").split()
        failures += check("bestmove names a ponder move",
                          len(parts) == 4 and parts[2] == "ponder" and len(parts[3]) >= 4, " ".join(parts))

        engine.send("position startpos moves e2e4 e7e5")
        engine.send("go ponder wtime 60000 btime 60000 movetime 50")
        time.sleep(0.4)
        engine.send("isready")
        seen = engine.read_until("readyok")
        failures += check("a ponder search does not answer before ponderhit",
                          not any(line.startswith("bestmove") for line in seen),
                          "; ".join(line for line in seen if line.startswith("bestmove")))
        start = time.time()
        engine.send("ponderhit")
        best = engine.wait_for("bestmove")
        elapsed = (time.time() - start) * 1000
        failures += check("ponderhit turns it into a timed search (50 ms budget, answered < 1000 ms)",
                          elapsed < 1000 and best.split()[1] != "0000",
                          "{} after {:.0f} ms".format(best, elapsed))

        # a ponderhit straight after go ponder, before the search thread has
        # started, must not be lost: that would ponder forever
        engine.send("position startpos moves e2e4")
        engine.send("go ponder movetime 50")
        engine.send("ponderhit")
        start = time.time()
        best = engine.wait_for("bestmove")
        elapsed = (time.time() - start) * 1000
        failures += check("an immediate ponderhit is not lost", elapsed < 1000,
                          "{} after {:.0f} ms".format(best, elapsed))

        engine.send("position startpos")
        engine.send("go ponder wtime 300000 btime 300000")
        time.sleep(0.3)
        start = time.time()
        engine.send("stop")
        best = engine.wait_for("bestmove")
        elapsed = (time.time() - start) * 1000
        failures += check("stop ends a ponder search within 500ms",
                          elapsed < 500 and best.split()[1] != "0000",
                          "{} after {:.0f} ms".format(best, elapsed))

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
            line = engine.readline(deadline)
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
