"""Value each kind of training data by what a short fine-tune on it does to held-out error (the owner's
"golden ticket", 2026-10-23: find which positions add Elo and which do not).

    py -3.13 harness/nnue/value_runs.py OUTDIR [--base NET] [--positions 5000000] [--yardstick FILE]

From --base (0.5.1's network) each chunk gets one epoch at a low learning rate on --positions of its records,
and every result, with the base, is scored on three held-out sets: the yardstick (positions from the games
machete loses, Stockfish at 1M nodes), n1500b (ordinary openings, 1,500-node labels) and the newest farm
file of imbalanced 15,000-node positions. A chunk whose fine-tune lowers the yardstick error carries
something the base lacks; one that raises it is noise or a distribution the bot does not meet. The
imbalanced chunk runs twice on different seeds: the gap between the two is the test's own noise.

Step 1 of the plan is to check this against data changes whose Elo is known (human positions removed -27,
imbalanced against balanced 15,000-node data at 15M +484, deep 15,000-node data added +15, rook endings
added +8): if the ranking agrees, the test is worth using to sort data before spending a day on a training.

Step 1 half-agreed: a pure fine-tune measures how far a chunk shifts the network, not what it adds inside a
mix. Step 1b, --mix 0.2, trains each run on 20% chunk and 80% a proportional sample of the base's own
recipe (--recipe, its finished training job), plus a control run on the recipe sample alone.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C = "E:/machete/corpora/"


def newest(pattern):
    return sorted(glob.glob(C + pattern), key=os.path.getmtime)[-1].replace(os.sep, "/")


def files(pattern, skip=()):
    return [f.replace(os.sep, "/") for f in sorted(glob.glob(C + pattern), key=os.path.getmtime) if f.replace(os.sep, "/") not in skip]


def take(paths, n):
    """PATH or PATH@N specs adding up to n records, from the front of the list."""
    out, need = [], n
    for p in paths:
        k = os.path.getsize(p) // 70
        if k >= need:
            out.append("%s@%d" % (p, need))
            return out
        out.append(p)
        need -= k
    return out


def recipe_sample(job, n):
    """n records spread over the corpora of a finished training job, each in proportion to its share there."""
    specs = [a for a in json.load(open(job))["argv"] if a.split("@")[0].endswith(".bin")]
    sizes = []
    for s in specs:
        path, cap = (s.rsplit("@", 1) + [""])[:2] if "@" in os.path.basename(s) else (s, "")
        k = os.path.getsize(path) // 70
        sizes.append((path, min(k, int(cap)) if cap else k))
    total = sum(k for _, k in sizes)
    return ["%s@%d" % (p, max(1, k * n // total)) for p, k in sizes]


def chunks(held_u):
    u = files("depth/n15000u_*.bin", skip=(held_u,))
    return {
        "imbalanced15k": u,
        "imbalanced15k_seed2": u,
        "balanced15k": files("depth/n15000_*.bin"),
        "human": files("../claude/data/theoden_b*.bin"),
        "farm1500": [C + "gen5.bin", C + "pi_gen1.bin"],
        "rook": files("rook*.bin"),
        "frc_deficit": files("d*_deficit960.bin") + files("e*_deficit960.bin"),
        "athena": files("athena/athena_*.bin"),
        "endgame": files("endgame/endgame_*.bin"),
        "sf_obsidian": files("imb_sf_obsidian*.bin") + files("*/imb_sf_obsidian*.bin"),
        "pairings": files("eq_*.bin") + files("*/eq_*.bin"),
    }


def holdout(corpus, nets):
    env = dict(os.environ, MACHETE_LAYERS="phase3")
    out = subprocess.run([sys.executable, os.path.join(HERE, "holdout.py"), corpus] + nets + ["--sample", "40000"],
                         capture_output=True, text=True, env=env).stdout
    res = {}
    for line in out.splitlines():
        m = re.match(r"(\S+\.nnue)\s+([\d.]+)\s+([\d.]+) cp", line)
        if m:
            res[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--base", default="E:/machete/releases/machete-0.5.1/machete.nnue")
    ap.add_argument("--positions", type=int, default=5000000)
    ap.add_argument("--yardstick", default=C + "yardstick/yardstick_40k.bin")
    ap.add_argument("--mix", type=float, default=0.0,
                    help="the chunk's share of each run; the rest is a sample of --recipe's data (step 1b)")
    ap.add_argument("--recipe", default="E:/machete/queue-gpu/done/20261020-212629-000000-TRAIN-C33F280P3ALL.json",
                    help="the finished training job whose data the base network learned from")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    held_u = newest("depth/n15000u_*.bin")
    own = int(args.positions * args.mix) if args.mix else args.positions
    rest = recipe_sample(args.recipe, args.positions - own) if args.mix else []
    sets = {"yardstick": args.yardstick, "n1500b": C + "depth/n1500b.bin", "imbalanced_heldout": held_u}
    nets = {}
    runs = chunks(held_u)
    if args.mix:
        # the control: the base's own data alone, so each chunk is judged against what more of the same does
        runs = dict(recipe=[args.recipe], **runs)
    for name, paths in runs.items():
        paths = [p for p in paths if os.path.exists(p.split("@")[0])]
        if name != "recipe" and (not paths or sum(os.path.getsize(p) // 70 for p in paths) < own):
            print("skip %s: not %d records" % (name, own), flush=True)
            continue
        out = os.path.join(args.outdir, name + ".nnue").replace(os.sep, "/")
        if not os.path.exists(out):
            seed = "2" if name.endswith("seed2") else "1"
            cmd = [sys.executable, "-u", os.path.join(HERE, "train.py")] + (recipe_sample(args.recipe, args.positions) if name == "recipe" else take(paths, own) + rest) + [
                "--layers", "phase3", "--hidden", "768", "--scale", "150", "--blend", "1.0", "--epochs", "1",
                "--lr", "0.0001", "--validation", "50000", "--seed", seed, "--init", args.base, "--out", out]
            r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, MACHETE_LAYERS="phase3"))
            if r.returncode != 0:
                print("FAILED %s: %s" % (name, r.stdout[-400:] + r.stderr[-400:]), flush=True)
                continue
        nets[name] = out
        print("trained %s" % name, flush=True)
    table = {}
    for s, corpus in sets.items():
        res = holdout(corpus, [args.base] + list(nets.values()))
        base = res.get(os.path.basename(args.base))
        for name, path in nets.items():
            got = res.get(os.path.basename(path))
            if base and got:
                table.setdefault(name, {})[s] = 100.0 * (got[0] - base[0]) / base[0]
    json.dump(table, open(os.path.join(args.outdir, "value.json"), "w"), indent=1)
    print("\nchange in held-out loss after a 1-epoch fine-tune on %d positions (negative = the data helps)" % args.positions)
    print("%-22s %12s %10s %20s" % ("chunk", "yardstick", "n1500b", "imbalanced held-out"))
    for name, row in sorted(table.items(), key=lambda kv: kv[1].get("yardstick", 0)):
        print("%-22s %+11.2f%% %+9.2f%% %+19.2f%%" % (name, row.get("yardstick", 0), row.get("n1500b", 0), row.get("imbalanced_heldout", 0)))


if __name__ == "__main__":
    main()
