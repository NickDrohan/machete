"""A MilkDrop-style visualiser driven by a network while it trains.

    python harness/nnue/trainviz.py "data/train_*.log" --port 8790

Given a pattern, it follows whichever matching log was written to last, so one
visualiser left running shows each training run in turn.

Nothing on the screen is decoration for its own sake. Three things feed it:

  the training log   loss every chunk, throughput, validation per epoch
  the GPU            utilisation, temperature, power, clock, from nvidia-smi
  the weights        the network file the trainer rewrites after every epoch:
                     768 inputs (12 piece types x 64 squares) x 256 neurons,
                     which is the texture the kaleidoscope is cut from - so
                     the patterns are the network, and they change as it learns

The page (trainviz.html) warps its previous frame and draws on top, the way
MilkDrop does; the data sets how. It only reads: the log, nvidia-smi and the
network file. Click the page for full screen.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference

HERE = os.path.dirname(os.path.abspath(__file__))
PROGRESS = re.compile(r"epoch (\d+)\s+([\d,]+) positions\s+loss ([\d.]+)\s+([\d,]+)/s")
DONE = re.compile(r"epoch (\d+) done: training loss ([\d.]+), validation ([\d.]+)")
WROTE = re.compile(r"wrote (\S+\.nnue)")
TOTAL = re.compile(r"([\d,]+) positions, training on (\w+)")
HISTORY = 512


class Watch(object):
    def __init__(self, log, epochs):
        self.lock = threading.Lock()
        self.log = log
        self.state = {"epoch": 0, "epochs": epochs, "positions": 0, "total": 0, "loss": None,
                      "rate": 0, "device": "", "validation": [], "history": [], "gpu": {},
                      "weights": 0}
        self.seen = None
        self.net_path = None
        self.net_stamp = None
        self.weights = b""
        self.sizes = {}
        self.following = None

    def current_log(self):
        """The log itself, or the match of a pattern that is being written.

        Windows does not move a file's modified time while a writer holds it
        open, so a training log in progress can look older than one that
        finished minutes ago. A file that has grown since the last look is the
        one being written; until one has, the most recently modified wins.
        """
        matches = glob.glob(self.log)
        if not matches:
            return self.log
        sizes = {path: os.path.getsize(path) for path in matches}
        grown = [path for path in matches if sizes[path] > self.sizes.get(path, sizes[path])]
        self.sizes = sizes
        if grown:
            self.following = max(grown, key=lambda path: sizes[path])
        if self.following not in sizes:
            self.following = max(matches, key=os.path.getmtime)
        return self.following

    def read_log(self):
        path = self.current_log()
        with self.lock:
            if path != self.state.get("log"):
                # a new run: its history is not the last one's
                self.state.update({"log": path, "history": [], "validation": [], "epoch": 0,
                                   "positions": 0, "total": 0, "loss": None, "rate": 0})
                self.seen = None
                self.net_path = None
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 200000))
                text = handle.read().decode("utf-8", "replace")
        except OSError:
            return
        lines = re.split(r"[\r\n]+", text)
        with self.lock:
            s = self.state
            for line in lines:
                total = TOTAL.search(line)
                if total:
                    s["total"] = int(total.group(1).replace(",", ""))
                    s["device"] = total.group(2)
                wrote = WROTE.search(line)
                if wrote:
                    self.net_path = wrote.group(1)
            s["validation"] = [[int(e), float(t), float(v)] for e, t, v in DONE.findall(text)]
            last = None
            for line in lines:
                found = PROGRESS.search(line)
                if found:
                    last = found
            if last:
                key = (last.group(1), last.group(2))
                if key != self.seen:
                    self.seen = key
                    s["epoch"] = int(last.group(1))
                    s["positions"] = int(last.group(2).replace(",", ""))
                    s["loss"] = float(last.group(3))
                    s["rate"] = int(last.group(4).replace(",", ""))
                    s["history"] = (s["history"] + [s["loss"]])[-HISTORY:]

    def read_gpu(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
                 "temperature.gpu,power.draw,clocks.sm", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5).stdout.strip().split(", ")
            gpu = {"name": out[0], "util": float(out[1]), "mem": float(out[2]),
                   "memTotal": float(out[3]), "temp": float(out[4]), "power": float(out[5]),
                   "clock": float(out[6])}
        except Exception:
            gpu = {}
        with self.lock:
            self.state["gpu"] = gpu

    def read_weights(self):
        path = self.net_path
        if not path or not os.path.exists(path):
            return
        stamp = os.path.getmtime(path)
        if stamp == self.net_stamp:
            return
        try:
            net = reference.load(path)
        except Exception:
            return          # caught mid-write; the next poll will read it whole
        w = net["feature_weights"].astype(np.float32)      # 768 inputs x 256 neurons
        spread = float(w.std()) or 1.0
        pixels = ((np.tanh(w.T / (2.0 * spread)) + 1.0) * 127.5).astype(np.uint8)
        with self.lock:
            self.weights = pixels.tobytes()                # 256 rows of 768
            self.net_stamp = stamp
            self.state["weights"] += 1

    def run(self):
        tick = 0
        while True:
            self.read_log()
            if tick % 2 == 0:
                self.read_gpu()
            if tick % 10 == 0:
                self.read_weights()
            tick += 1
            time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", help="the trainer's log file, or a pattern such as data/train_*.log")
    parser.add_argument("--epochs", type=int, default=14, help="how many the run was started with")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()

    watch = Watch(args.log, args.epochs)
    threading.Thread(target=watch.run, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state"):
                with watch.lock:
                    body, kind = json.dumps(watch.state).encode("utf-8"), "application/json"
            elif self.path.startswith("/weights"):
                with watch.lock:
                    body, kind = watch.weights, "application/octet-stream"
            else:
                # read each time, so an edit to the page shows on a reload
                with open(os.path.join(HERE, "trainviz.html"), "rb") as handle:
                    body, kind = handle.read(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print("watch the training at http://127.0.0.1:{}".format(args.port))
    sys.stdout.flush()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
