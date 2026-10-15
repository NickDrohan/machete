"""When X1 shard generation hits the target, concat and train the odds net.

    python harness/nnue/wait_train_x1.py

Polls E:/machete/corpora/x1_handicap960_tb.bin.*.part until they hold at
least --target records (or gen.exe has exited and growth has stopped), then
concatenates and launches train.py on CUDA. Pure handicap960 data only.
"""

import argparse
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

PREFIX = r"E:\machete\corpora\x1_handicap960_tb.bin"
OUT_BIN = r"E:\machete\corpora\x1_handicap960_tb.bin"
OUT_NET = r"E:\machete\claude\nets\net_odds_sf.nnue"
LOG = r"E:\machete\claude\nets\net_odds_sf.log"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def positions():
    parts = glob.glob(PREFIX + ".*.part")
    return sum(os.path.getsize(p) for p in parts) // RECORD.itemsize, parts


def gen_running():
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq gen.exe"], text=True, stderr=subprocess.DEVNULL)
        return "gen.exe" in out.lower()
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=30_000_000)
    parser.add_argument("--poll", type=int, default=60)
    parser.add_argument("--hidden", type=int, default=768)
    parser.add_argument("--epochs", type=int, default=14)
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()

    stable = 0
    last = -1
    while True:
        n, parts = positions()
        running = gen_running()
        print("{}  {:,} / {:,}  gen={}".format(
            time.strftime("%H:%M:%S"), n, args.target, running), flush=True)
        if n >= args.target:
            break
        if not running:
            if n == last:
                stable += 1
            else:
                stable = 0
            if stable >= 3 and n > 0:
                print("gen stopped at {:,}; proceeding".format(n), flush=True)
                break
        last = n
        time.sleep(args.poll)

    concat = os.path.join(ROOT, "harness", "nnue", "concat_parts.py")
    subprocess.check_call([sys.executable, "-u", concat, PREFIX, "--out", OUT_BIN])
    if args.skip_train:
        return 0

    # panel relabel of the first --panel-limit boards on CPU while the GPU trains
    panel_bin = r"E:\machete\corpora\x1_panel_2m.bin"
    panel_log = r"E:\machete\claude\nets\x1_panel_2m.log"
    consensus = os.path.join(ROOT, "harness", "nnue", "consensus_label.py")
    panel_cmd = [
        sys.executable, "-u", consensus, OUT_BIN, panel_bin,
        "--workers", "10", "--limit", "2000000", "--hash", "64", "--force",
    ]
    print("panel:", " ".join(panel_cmd), flush=True)
    panel_proc = subprocess.Popen(
        panel_cmd, cwd=ROOT,
        stdout=open(panel_log, "w"), stderr=subprocess.STDOUT)

    train = os.path.join(ROOT, "harness", "nnue", "train.py")
    cmd = [
        sys.executable, "-u", train, OUT_BIN,
        "--out", OUT_NET, "--hidden", str(args.hidden),
        "--epochs", str(args.epochs), "--scale", "150", "--blend", "1.0",
        "--seed", "7", "--window", "120000000",
    ]
    print("training:", " ".join(cmd), flush=True)
    with open(LOG, "w") as log, open(LOG + ".err", "w") as err:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=err)
    print("train exit", proc.returncode, "log", LOG, flush=True)

    panel_code = panel_proc.wait()
    print("panel exit", panel_code, "log", panel_log, flush=True)
    if proc.returncode == 0 and panel_code == 0 and os.path.exists(panel_bin):
        panel_net = r"E:\machete\claude\nets\net_odds_panel2m.nnue"
        panel_train_log = r"E:\machete\claude\nets\net_odds_panel2m.log"
        pcmd = [
            sys.executable, "-u", train, panel_bin,
            "--out", panel_net, "--hidden", str(args.hidden),
            "--epochs", str(args.epochs), "--scale", "150", "--blend", "1.0",
            "--seed", "7",
        ]
        print("panel train:", " ".join(pcmd), flush=True)
        with open(panel_train_log, "w") as log, open(panel_train_log + ".err", "w") as err:
            p_exit = subprocess.run(pcmd, cwd=ROOT, stdout=log, stderr=err).returncode
        print("panel train exit", p_exit, flush=True)
        return p_exit if proc.returncode == 0 else proc.returncode
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
