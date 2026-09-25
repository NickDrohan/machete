"""Check that a teacher which stops answering cannot stall gen.py.

    python harness/nnue/hang.py

A stand-in teacher answers its first few searches and never answers the next,
which is how an engine ignoring its node limit looks from outside. gen.py's
worker must kill it, start a fresh one, throw away the game it was part way
through, and record the position it hung on. The stand-in that hangs scores
every position +11 and its replacement 0, so a row scored 11 in the shard is a
row from the game that should have been thrown away.

    python harness/nnue/hang.py teacher [--hang-at N] [--score CP] [--log PATH]

is the stand-in itself: legal moves at a fixed score, and from its Nth search
on, silence until its input closes. Exits non-zero if any check fails.
"""

import argparse
import concurrent.futures
import multiprocessing
import os
import random
import shutil
import sys
import tempfile
import threading

import chess
import chess.engine
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen
import panel
from reference import RECORD

# after 1.e4 c5: an en passant square no pawn can use, which python-chess
# sends anyway, so a recorded position built any other way will not match
BOOK = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
HANG_AT = 4         # the opening check and the first moves answered, then nothing
PATIENCE = 5        # gen.HUNG_AFTER, for this check; the stand-in answers in milliseconds
DEADLINE = 120      # the whole check: a worker that stalls must fail it, not hang it
POSITIONS = 100


def teacher(hang_at, score, log):
    board = chess.Board()
    position = ""
    multipv = 1
    searches = 0
    hung = False
    for line in sys.stdin:
        words = line.split()
        if hung or not words:
            continue
        if words[0] == "uci":
            print("id name hang.py stand-in")
            print("option name Threads type spin default 1 min 1 max 1")
            print("option name Hash type spin default 16 min 1 max 1024")
            print("option name MultiPV type spin default 1 min 1 max 8")
            print("uciok", flush=True)
        elif words[0] == "isready":
            print("readyok", flush=True)
        elif words[:3] == ["setoption", "name", "MultiPV"]:
            multipv = int(words[4])
        elif words[0] == "position":
            position = line.strip()
            if words[1] == "startpos":
                board, rest = chess.Board(), words[2:]
            else:
                board, rest = chess.Board(" ".join(words[2:8])), words[8:]
            for move in rest[1:]:
                board.push_uci(move)
        elif words[0] == "go":
            searches += 1
            if searches == hang_at:
                hung = True
                with open(log, "w") as handle:
                    handle.write(position + "\n" + line.strip() + "\n")
                continue
            moves = sorted(board.legal_moves, key=chess.Move.uci)
            random.Random(board.fen()).shuffle(moves)
            for rank, move in enumerate(moves[:multipv], 1):
                print("info multipv {} depth 1 score cp {} nodes 1 pv {}".format(rank, score, move.uci()))
            print("bestmove " + (moves[0].uci() if moves else "0000"), flush=True)
        elif words[0] == "quit":
            break
    return 0


def exited(engine):
    try:
        engine.returncode.result(10)
        return True
    except concurrent.futures.TimeoutError:
        return False


def check(name, condition, detail=""):
    if condition:
        print("  ok   {}".format(name))
        return 0
    print("  FAIL {} {}".format(name, detail))
    return 1


def main():
    work = tempfile.mkdtemp()
    book = os.path.join(work, "book.epd")
    with open(book, "w") as handle:
        handle.write(BOOK + "\n")
    log = os.path.join(work, "stand-in.log")
    opened = []

    def open_engine(name, hash_mb=64):
        command = [sys.executable, os.path.abspath(__file__), "teacher"]
        if not opened:
            command += ["--hang-at", str(HANG_AT), "--score", "11", "--log", log]
        engine = chess.engine.SimpleEngine.popen_uci(command, timeout=30)
        engine.configure({"Threads": 1, "Hash": hash_mb})
        opened.append(engine)
        return engine

    panel.open_engine = open_engine
    panel.path_of = lambda name: "hang.py"
    gen.HUNG_AFTER = PATIENCE

    def stalled():
        print("  FAIL still running after {} s".format(DEADLINE), flush=True)
        os._exit(1)

    alarm = threading.Timer(DEADLINE, stalled)
    alarm.daemon = True
    alarm.start()
    out = os.path.join(work, "out.bin")
    args = argparse.Namespace(out=out, engines="Stand-in", book=book, positions=POSITIONS,
                              nodes=1500, depth=8, workers=1, hash=16, seed=1)
    gen.worker(0, args, multiprocessing.Value("l", 0))

    rows = np.fromfile(gen.shard_path(out, 0), dtype=RECORD)
    record = ""
    if os.path.exists(gen.hang_path(out, 0)):
        with open(gen.hang_path(out, 0)) as handle:
            record = handle.read()
    sent = ["", ""]
    if os.path.exists(log):
        with open(log) as handle:
            sent = handle.read().splitlines()

    failures = 0
    failures += check("the worker finished its share", len(rows) > POSITIONS,
                      "{} rows".format(len(rows)))
    failures += check("the teacher was restarted once", len(opened) == 2,
                      "{} started".format(len(opened)))
    failures += check("the teacher that hung was killed", exited(opened[0]))
    failures += check("no row of the abandoned game was written", not (rows["score"] == 11).any(),
                      "{} rows scored 11".format(int((rows["score"] == 11).sum())))
    failures += check("the position it hung on is recorded as it was sent",
                      bool(sent[0]) and sent[0] in record.splitlines(), repr(sent[0]))
    failures += check("so is the search it was given",
                      bool(sent[1]) and sent[1] in record.splitlines(), repr(sent[1]))
    shutil.rmtree(work, ignore_errors=True)
    return failures


if __name__ == "__main__":
    if sys.argv[1:2] == ["teacher"]:
        parser = argparse.ArgumentParser()
        parser.add_argument("teacher")
        parser.add_argument("--hang-at", type=int, default=0)
        parser.add_argument("--score", type=int, default=0)
        parser.add_argument("--log")
        options = parser.parse_args()
        sys.exit(teacher(options.hang_at, options.score, options.log))
    failures = main()
    # not sys.exit: a teacher that was never killed keeps its python-chess
    # thread alive, and that thread would hold the interpreter open for good
    sys.stdout.flush()
    os._exit(1 if failures else 0)
