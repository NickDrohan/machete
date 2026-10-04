"""Hold the Mach generator (src/tools/gen.mach) to gen.py, byte for byte.

    python harness/nnue/gen_check.py GEN_EXE BOOK.epd [--positions 2000] [--nodes 1500]

Both are made deterministic the same way: book positions taken in order
instead of at random, and no variety moves. Stockfish at a fixed node count
with one thread is deterministic for a given sequence of commands, so gen.py's
own play_game (with its random source replaced) and `gen ... gate` must then
play the same games and write the same records. The check plays one worker's
worth of games each way and compares the files byte for byte, naming the first
record that differs. Exit 0 when identical.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen  # noqa: E402
import panel  # noqa: E402
from reference import RECORD  # noqa: E402


class InOrder(object):
    """gen.py's random source, made deterministic: choice() walks the book in
    order and random() never asks for a variety move."""

    def __init__(self):
        self.next = 0

    def choice(self, seq):
        item = seq[self.next % len(seq)]
        self.next += 1
        return item

    def random(self):
        return 1.0


def python_side(book_path, positions, nodes, out):
    book = [line.strip() for line in open(book_path) if line.strip() and not line.startswith("#")]
    engine = panel.open_engine("Stockfish", 32)
    limit = chess.engine.Limit(nodes=nodes)
    ending = chess.engine.Limit(nodes=nodes * gen.ENDGAME_NODES_FACTOR)
    rng, written, share = InOrder(), 0, positions + 1
    started = time.time()
    with open(out, "wb") as handle:
        while written < share:
            seen, outcome = gen.play_game(engine, limit, ending, rng, book, 0)
            if not seen:
                continue
            rows = np.zeros(len(seen), dtype=RECORD)
            for slot, (row, turn) in enumerate(seen):
                if outcome == "1/2-1/2":
                    row["result"] = 1
                elif (outcome == "1-0") == (turn == chess.WHITE):
                    row["result"] = 2
                else:
                    row["result"] = 0
                rows[slot] = row
            handle.write(rows.tobytes())
            written += len(rows)
    panel.quiet_quit(engine)
    return written, time.time() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gen_exe")
    parser.add_argument("book")
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--nodes", type=int, default=1500)
    args = parser.parse_args()

    work = tempfile.mkdtemp(prefix="gen_check_")
    py_out, mach_out = os.path.join(work, "python.bin"), os.path.join(work, "mach.bin")
    py_rows, py_s = python_side(args.book, args.positions, args.nodes, py_out)
    started = time.time()
    run = subprocess.run([args.gen_exe, mach_out, args.book, panel.path_of("Stockfish"), str(args.positions),
                          str(args.nodes), "1", "1", "gate"], capture_output=True, text=True)
    mach_s = time.time() - started
    if run.returncode != 0:
        print(run.stdout[-2000:], run.stderr[-2000:])
        raise SystemExit("the Mach generator failed (exit %d)" % run.returncode)
    a = np.fromfile(py_out, dtype=RECORD)
    b = np.fromfile(mach_out, dtype=RECORD)
    print("gen.py: %d positions in %.1fs (%.0f/s); Mach: %d in %.1fs (%.0f/s), one worker each"
          % (len(a), py_s, len(a) / py_s, len(b), mach_s, len(b) / mach_s))
    same = len(a) == len(b) and a.tobytes() == b.tobytes()
    if not same:
        n = min(len(a), len(b))
        diff = next((i for i in range(n) if a[i].tobytes() != b[i].tobytes()), n)
        print("first difference at record %d of %d / %d" % (diff, len(a), len(b)))
        for name, rows in (("gen.py", a), ("mach", b)):
            if diff < len(rows):
                r = rows[diff]
                print("  %-7s stm %d count %d score %d result %d engine %d" % (name, r["stm"], r["count"], r["score"], r["result"], r["engine"]))
    print("IDENTICAL" if same else "DIFFERENT")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
