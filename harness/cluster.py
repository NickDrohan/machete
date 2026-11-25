"""machete-cluster (beta): one UCI engine made of every machine on the farm (the owner, 2026-11-25).

    py -3.13 harness/cluster.py [--config harness/cluster.json] [--log FILE]

A GUI, match runner or lichess-bot talks to this as to any UCI engine. Behind it, each machine runs its own machete,
and each search is split at the root: the legal moves are dealt out to the machines in proportion to their speed
(`go ... searchmoves <their share>`), each machine searches only its share with the full clock, and the move played is
the best any machine reports. A machine that finds a decisive line - a mate it delivers, at any depth, or a score of at least `win_cp` at depth
`win_depth` or more - stops every other machine at once, and its move is played (the owner's "a machine that believes
it has a winning branch signals stop and eval").

Root splitting needs no change to the engine (machete has supported searchmoves for a long time), costs one round trip
a move, and works with any number of machines. What it gives up: the machines share no transposition table and do not
learn from each other's scores, so one machine can search a hopeless move as deeply as the best one. Whether that loses
more than the extra machines gain is the question this beta exists to measure.

Not supported yet: pondering (the cluster advertises no Ponder option), MultiPV, and machines joining mid-game.

cluster.json lists the machines: each a name, the command that starts its machete speaking UCI on stdin/stdout (ssh for
remote ones), a weight (its share of the root moves, roughly its speed), and the options set on it alone. Options the
GUI sets are passed to every machine, except Threads, EvalFile and SyzygyPath, which each machine's entry owns.
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

import chess

HERE = os.path.dirname(os.path.abspath(__file__))
OWN_OPTIONS = {"threads", "evalfile", "syzygypath"}
NAME = "machete-cluster 0.6.0-beta"


class Worker:
    """One machine's machete over a pipe; a reader thread turns its output into events on the shared queue."""

    def __init__(self, spec, events, log):
        self.name = spec["name"]
        self.weight = float(spec.get("weight", 1.0))
        self.options = spec.get("options", {})
        self.events = events
        self.log = log
        self.alive = True
        self.busy = False      # sent a go and has not yet answered it
        self.sent = 0          # searches started (go commands sent)
        self.answered = 0      # searches answered (bestmoves read); a line belongs to search answered + 1
        self.proc = subprocess.Popen(spec["command"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            line = line.strip()
            search = self.answered + 1
            if line.startswith("bestmove"):
                self.answered += 1
                self.busy = self.answered < self.sent
            self.events.put((self, search, line))
        self.alive = False
        self.events.put((self, self.answered + 1, None))

    def send(self, line):
        if not self.alive:
            return
        if line.startswith("go"):
            self.sent += 1
            self.busy = True
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except OSError:
            self.alive = False
        self.log("> %s: %s" % (self.name, line))


def parse_info(line):
    """depth, score (centipawns, mates mapped far beyond any evaluation) and first pv move of an info line, or None."""
    t = line.split()
    if "score" not in t or "pv" not in t or "depth" not in t:
        return None
    try:
        depth = int(t[t.index("depth") + 1])
        kind, value = t[t.index("score") + 1], int(t[t.index("score") + 2])
        if "lowerbound" in t or "upperbound" in t:
            return None
        move = t[t.index("pv") + 1]
    except (ValueError, IndexError):
        return None
    score = (100000 - abs(value)) * (1 if value > 0 else -1) if kind == "mate" else value
    return depth, score, move, kind, value


class Cluster:
    def __init__(self, config, log):
        self.cfg = config
        self.log = log
        self.events = queue.Queue()
        self.workers = [Worker(spec, self.events, log) for spec in config["machines"]]
        self.board = chess.Board()
        self.position_line = "position startpos"
        self.win_cp = int(config.get("win_cp", 600))
        self.win_depth = int(config.get("win_depth", 10))
        self.overhead = int(config.get("overhead_ms", 60))     # kept back from each move for the round trips
        self.grace = int(config.get("grace_ms", 40))           # how long a stop is given to land
        # "split": every machine searches only its share of the root moves (beta 1). "anchored": the first machine
        # (the PC) searches every move as it would alone, the others search shares of the moves as second opinions,
        # and the PC's move is played unless another machine shows a better one by `margin_cp` at a depth within
        # `depth_slack` of the PC's (beta 2, after split lost 0-4-6 to the PC alone at 10+0.1).
        self.mode = config.get("mode", "anchored")
        self.margin = int(config.get("margin_cp", 30))
        self.slack = int(config.get("depth_slack", 2))

    # ---- plumbing ----
    def all(self, line):
        for w in self.workers:
            w.send(line)

    def wait_for(self, word, workers, timeout=30.0):
        """Drain events until each of `workers` has said a line starting with `word`."""
        pending = set(w for w in workers if w.alive)
        end = time.time() + timeout
        while pending and time.time() < end:
            try:
                w, _search, line = self.events.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if line is None or line.startswith(word):
                pending.discard(w)

    def start(self):
        self.all("uci")
        self.wait_for("uciok", self.workers, 60)
        for w in self.workers:
            for k, v in w.options.items():
                w.send("setoption name %s value %s" % (k, v))
        self.all("isready")
        self.wait_for("readyok", self.workers, 60)
        live = [w.name for w in self.workers if w.alive]
        self.log("machines up: %s" % ", ".join(live))

    # ---- UCI commands from the GUI ----
    def uci(self):
        print("id name %s" % NAME)
        print("id author Nick Drohan")
        for line in self.cfg.get("advertise", []):
            print(line)
        print("uciok", flush=True)

    def setoption(self, line):
        t = line.split()
        if "name" in t:
            name = " ".join(t[t.index("name") + 1:t.index("value") if "value" in t else len(t)])
            if name.lower() in OWN_OPTIONS:
                return
        self.all(line)

    def position(self, line):
        self.position_line = line
        t = line.split()
        board = chess.Board() if t[1] == "startpos" else chess.Board(" ".join(t[t.index("fen") + 1:t.index("moves") if "moves" in t else len(t)]))
        if "moves" in t:
            for u in t[t.index("moves") + 1:]:
                board.push_uci(u)
        self.board = board
        self.all(line)

    def split(self, moves, workers):
        """Deal the root moves out by weight: likely-good moves first (captures by value, then checks), each going to
        the machine furthest below its share, so every machine gets a mix and the fastest the first pick."""
        b = self.board

        def key(m):
            gain = 0
            if b.is_capture(m):
                victim = b.piece_at(m.to_square)
                gain = 10 * (victim.piece_type if victim else 1) - b.piece_at(m.from_square).piece_type
            return (-gain, -int(b.gives_check(m)))
        ordered = sorted(moves, key=key)
        total = sum(w.weight for w in workers)
        share = {w: [] for w in workers}
        for m in ordered:
            w = min(workers, key=lambda x: (len(share[x]) + 1) / (x.weight / total))
            share[w].append(m)
        return share

    def budget(self, t):
        """The coordinator's own clock: milliseconds for this move, or None to search until told to stop. A machine
        left to its own time management plans as if it were alone, and waiting for the slowest one plus the round
        trips lost every game on time (beta 1, 2026-11-25: 55 losses on time in 64 games at 10+0.1)."""
        def num(word):
            return int(t[t.index(word) + 1]) if word in t else None
        if "infinite" in t or "depth" in t or "nodes" in t:
            return None
        if "movetime" in t:
            return max(10, num("movetime") - self.overhead)
        ours = num("wtime" if self.board.turn == chess.WHITE else "btime")
        if ours is None:
            return None
        inc = num("winc" if self.board.turn == chess.WHITE else "binc") or 0
        return max(10, min(ours // 25 + inc * 4 // 5, ours // 4) - self.overhead)

    def go(self, line):
        t = line.split()
        moves = list(self.board.legal_moves)
        if "searchmoves" in t:
            allowed = set(t[t.index("searchmoves") + 1:])
            moves = [m for m in moves if m.uci() in allowed]
            t = t[:t.index("searchmoves")]
        budget = self.budget(t)
        # a machine still finishing the last search sits this one out rather than answer the wrong position
        live = [w for w in self.workers if w.alive and not w.busy] or [w for w in self.workers if w.alive][:1]
        if not moves:
            print("bestmove 0000", flush=True)
            return
        anchor = self.workers[0] if self.workers[0] in live else None
        if len(moves) == 1 or len(live) == 1:
            share = {live[0]: moves}
        elif self.mode == "anchored" and anchor is not None:
            share = {anchor: moves}
            helpers = [w for w in live if w is not anchor]
            share.update({w: ms for w, ms in self.split(moves, helpers).items() if ms})
        else:
            share = {w: ms for w, ms in self.split(moves, live).items() if ms}
        head = "go movetime %d" % budget if budget is not None else " ".join(t)
        for w, ms in share.items():
            w.send("%s searchmoves %s" % (head, " ".join(m.uci() for m in ms)))
        deadline = None if budget is None else time.time() + budget / 1000.0
        self.collect(share, deadline, anchor if self.mode == "anchored" else None)

    def collect(self, share, deadline, anchor=None):
        """Wait for the searching machines' bestmoves, relaying the best line, until all have answered or the clock's
        deadline passes; stop them all early on a decisive line. Past the deadline (and a short grace for the stop to
        land) the best answer so far is played, and a machine that has not answered sits out the next search."""
        best = {}            # worker -> (depth, score, move, kind, value)
        done = {}            # worker -> bestmove
        stopped = False
        shown = None
        searching = set(share)
        give_up = None
        while searching:
            now = time.time()
            if deadline is not None and not stopped and now >= deadline:
                self.stop(share)
                stopped = True
            if stopped and give_up is None:
                give_up = now + self.grace / 1000.0
            if give_up is not None and now >= give_up:
                break
            try:
                w, search, line = self.events.get(timeout=0.02)
            except queue.Empty:
                if self.gui_stop.is_set() and not stopped:
                    self.stop(share)
                    stopped = True
                continue
            # only this search's lines: a machine's output for an earlier search (late, or after a stop) is dropped
            if w not in searching or search != w.sent:
                continue
            if line is None:
                searching.discard(w)
                continue
            if line.startswith("bestmove"):
                done[w] = line.split()[1]
                searching.discard(w)
                continue
            info = parse_info(line)
            if not info:
                continue
            best[w] = info
            depth, score, move, kind, value = info
            top = max(best.values(), key=lambda x: x[1])
            if top is info and (shown is None or shown != (depth, move, score)):
                shown = (depth, move, score)
                words = line.split()
                print("info depth %d score %s %d pv %s string from %s" % (depth, kind, value, " ".join(words[words.index("pv") + 1:]), w.name), flush=True)
            # a mate the side to move delivers is proven at whatever depth it is found; a large score needs depth
            decisive = (kind == "mate" and value > 0) or (depth >= self.win_depth and score >= self.win_cp)
            if not stopped and decisive:
                self.log("%s found a decisive line at depth %d (%s %d): stopping the others" % (w.name, depth, kind, value))
                self.stop(share)
                stopped = True
            if self.gui_stop.is_set() and not stopped:
                self.stop(share)
                stopped = True
        legal = {m.uci() for m in self.board.legal_moves}
        candidates = [(best[w][1], best[w][0], done.get(w) or best[w][2], w) for w in best]
        candidates = [c for c in candidates if c[2] in legal]
        mine = [c for c in candidates if c[3] is anchor] if anchor is not None else []
        if not candidates:
            move = next((m for m in done.values() if m in legal), None) or next(iter(self.board.legal_moves)).uci()
            self.log("bestmove %s: no machine reported a legal move with a score" % move)
        elif mine:
            # the anchor's move unless a second opinion beats it clearly, at a comparable depth, or proves a mate
            score, depth, move, w = mine[0]
            for c in sorted(candidates, key=lambda c: (c[0], c[1]), reverse=True):
                if c[3] is anchor:
                    break
                if c[0] >= 90000 or (c[0] >= score + self.margin and c[1] >= depth - self.slack):
                    score, depth, move, w = c
                    break
            self.log("bestmove %s from %s (score %d, depth %d; anchor %s)%s" % (move, w.name, score, depth,
                     "kept" if w is anchor else "overruled", "" if not searching else "; late: " + ", ".join(x.name for x in searching)))
        else:
            score, depth, move, w = max(candidates, key=lambda c: (c[0], c[1]))
            self.log("bestmove %s from %s (score %d, depth %d)%s" % (move, w.name, score, depth,
                     "" if not searching else "; late: " + ", ".join(x.name for x in searching)))
        print("bestmove %s" % move, flush=True)

    def stop(self, share):
        """Stop the machines searching this move, and no others: an idle engine told to stop may answer with a
        bestmove for its last search, which the next search would then read as its own."""
        for w in share:
            if w.busy:
                w.send("stop")

    def quit(self):
        self.all("quit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "cluster.json"))
    ap.add_argument("--log", default="")
    args = ap.parse_args()
    logf = open(args.log, "a", encoding="utf-8") if args.log else None

    def log(text):
        if logf:
            logf.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))
            logf.flush()
    cluster = Cluster(json.load(open(args.config)), log)
    cluster.gui_stop = threading.Event()
    lines = queue.Queue()

    def read_stdin():
        # stop and quit must reach a search while it runs, so they raise the flag the search watches at once
        for raw in sys.stdin:
            line = raw.strip()
            if line.startswith("go"):
                cluster.gui_stop.clear()
            if line in ("stop", "quit"):
                cluster.gui_stop.set()
            if line != "stop":
                lines.put(line)
        cluster.gui_stop.set()
        lines.put("quit")
    threading.Thread(target=read_stdin, daemon=True).start()
    cluster.start()
    while True:
        line = lines.get()
        log("< %s" % line)
        word = line.split()[0] if line else ""
        if word == "uci":
            cluster.uci()
        elif word == "isready":
            cluster.all("isready")
            cluster.wait_for("readyok", cluster.workers, 30)
            print("readyok", flush=True)
        elif word == "setoption":
            cluster.setoption(line)
        elif word == "ucinewgame":
            cluster.all("ucinewgame")
        elif word == "position":
            cluster.position(line)
        elif word == "go":
            cluster.go(line)
        elif word == "quit":
            cluster.quit()
            return


if __name__ == "__main__":
    main()
