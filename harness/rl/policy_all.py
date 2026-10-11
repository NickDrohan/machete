"""How often is a policy network's first choice the best move - on every position, not only our misses?

    python harness/rl/policy_all.py --dir E:/machete/rl-classical [--sample 20000]

schemas.py found Leela's policy network alone naming 42% of the best moves our
network and search missed together. That is on the misses; this asks the same
of a random sample of all the positions the panel agreed a best move on, so
the policy can be set beside our networks' first instinct (instinct.jsonl) on
the same positions. Leela is asked for one node: the policy head's top move,
no search and no evaluation. Uses the GPU; resumable (policy_all.jsonl).
"""
import argparse
import json
import os
import random
import sys

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import instinct  # noqa: E402
import panel_label  # noqa: E402
import schemas  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--sample", type=int, default=20000)
    args = parser.parse_args()
    rows = [json.loads(l) for l in open(os.path.join(args.dir, "instinct.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r["legal"] > 1]
    random.Random(1).shuffle(rows)
    rows = rows[:args.sample]
    out_path = os.path.join(args.dir, "policy_all.jsonl")
    done = {}
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            r = json.loads(line)
            done[panel_label.position_key(r["fen"])] = r["policy"]
    todo = [r for r in rows if panel_label.position_key(r["fen"]) not in done]
    if todo:
        engine = chess.engine.SimpleEngine.popen_uci([schemas.LC0, "--weights=" + schemas.LC0_WEIGHTS, "--threads=1"], timeout=180)
        limit = chess.engine.Limit(nodes=1)
        with open(out_path, "a", encoding="utf-8") as out:
            for n, r in enumerate(todo):
                move = instinct.first_move(engine, chess.Board(r["fen"]), limit)
                done[panel_label.position_key(r["fen"])] = move
                out.write(json.dumps(dict(fen=r["fen"], policy=move)) + "\n")
                if n % 200 == 0:
                    out.flush()
        engine.quit()
    rows = [r for r in rows if panel_label.position_key(r["fen"]) in done]
    names = [n for n in instinct.NETS if all(n in r["moves"] for r in rows)]
    lines = ["%d positions with a consensus best move: how often the first choice is that move" % len(rows), "",
             "%-22s %6.1f%%" % ("Leela's policy, 1 node", 100 * sum(done[panel_label.position_key(r["fen"])] == r["best"] for r in rows) / len(rows))]
    for name in names:
        lines.append("%-22s %6.1f%%   (at 40,000 nodes %.1f%%)" % (name + " first instinct", 100 * sum(r["moves"][name][0] == r["best"] for r in rows) / len(rows),
                                                                  100 * sum(r["moves"][name][1] == r["best"] for r in rows) / len(rows)))
    lines.append("%-22s %6.1f%%" % ("random move", 100 * sum(1 / r["legal"] for r in rows) / len(rows)))
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.dir, "policy_all.txt"), "w", encoding="utf-8").write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
