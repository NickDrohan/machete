"""Find the positions strong engines cannot agree about.

    python harness/nnue/contested.py data/train.bin --out data/contested.json \
        --positions 250 --controls 0.2

Disagreement between several strong engines is the best cheap signal for "this
position is hard", which is the standard query-by-committee argument. Here it
also does a second job: it picks out the positions where one engine's opinion
cannot be treated as the answer, which is exactly where an empirical result is
worth paying for.

Selection is on the *move* they choose, not on their evaluation. Measured over
real positions, four top engines differ by 206cp in the middle of a decided
position and by 32cp in a balanced one - almost all of that spread is the
different ways engines scale centipawns to a win probability, not a
disagreement about chess. They pick different moves about half the time, and
that is a real difference.

A fifth of the output is deliberately positions everyone agrees on. Without
them there is no way to tell "bad at hard positions" from "bad everywhere",
and no way to check the measuring apparatus itself.
"""

import argparse
import collections
import json
import os
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel
from reference import RECORD


def boards_from(path, wanted, seed, min_pieces=6, max_cp=250):
    """Rebuild legal positions from the generated training records.

    Positions the generator already scored as decided are skipped before any
    engine is asked about them. Engines disagree about decided positions
    constantly - they are arguing about how to write down a win, not about who
    is better - and playing such a position out thirty times returns thirty
    identical results. The stored score makes that filter free.
    """
    data = np.memmap(path, dtype=RECORD, mode="r")
    rng = np.random.RandomState(seed)
    seen = set()
    out = []
    for index in rng.choice(len(data), min(len(data), wanted * 60), replace=False):
        row = data[index]
        if row["count"] < min_pieces:
            continue
        if abs(int(row["score"])) > max_cp:
            continue
        board = chess.Board(None)
        for i in range(row["count"]):
            code = int(row["pieces"][i])
            board.set_piece_at(int(row["squares"][i]),
                               chess.Piece(code % 6 + 1,
                                           chess.WHITE if code < 6 else chess.BLACK))
        board.turn = chess.WHITE if row["stm"] == 0 else chess.BLACK
        if not board.is_valid() or board.is_game_over():
            continue
        fen = board.fen()
        if fen in seen:
            continue
        seen.add(fen)
        out.append((fen, int(row["score"])))
        if len(out) >= wanted:
            break
    return out


def poll(engines, board, nodes):
    """Every engine's best move and evaluation for one position."""
    import chess.engine
    verdicts = {}
    for name, engine in engines.items():
        try:
            info = engine.analyse(board, chess.engine.Limit(nodes=nodes))
            move = info["pv"][0].uci() if info.get("pv") else None
            score = info["score"].pov(board.turn).score(mate_score=10000)
            verdicts[name] = {"move": move, "cp": score}
        except Exception:
            verdicts[name] = {"move": None, "cp": None}
    return verdicts


def disagreement(verdicts):
    """How split the panel is: 0.0 when unanimous, towards 1.0 when scattered."""
    moves = [v["move"] for v in verdicts.values() if v["move"]]
    if not moves:
        return 0.0, 0
    counts = collections.Counter(moves)
    top = counts.most_common(1)[0][1]
    return 1.0 - float(top) / len(moves), len(counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--out", default="data/contested.json")
    parser.add_argument("--positions", type=int, default=250,
                        help="contested positions to keep")
    parser.add_argument("--controls", type=float, default=0.2,
                        help="extra fraction that are unanimous, as a baseline")
    parser.add_argument("--nodes", type=int, default=300000)
    parser.add_argument("--engines", default="Stockfish,Berserk,Alexandria,Obsidian,Caissa,Seer")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--scan", type=int, default=3000,
                        help="positions to examine while looking for split ones")
    parser.add_argument("--max-cp", type=int, default=250,
                        help="keep only positions neither side has already won")
    args = parser.parse_args()

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    engines = {}
    for name in names:
        engines[name] = panel.open_engine(name)
    print("panel: {}".format(", ".join(names)))

    candidates = boards_from(args.data, args.scan, args.seed, max_cp=args.max_cp)
    print("{} candidate positions rebuilt".format(len(candidates)))

    contested, controls = [], []
    want_controls = int(args.positions * args.controls)
    examined = 0
    try:
        for fen, stored in candidates:
            if len(contested) >= args.positions and len(controls) >= want_controls:
                break
            board = chess.Board(fen)
            verdicts = poll(engines, board, args.nodes)
            split, distinct = disagreement(verdicts)
            examined += 1
            # the stored score was one engine at low depth; check the panel agrees
            # the position is still live before spending games on it
            seen_cp = [abs(v["cp"]) for v in verdicts.values() if v["cp"] is not None]
            if not seen_cp or sorted(seen_cp)[len(seen_cp) // 2] > args.max_cp:
                continue
            record = {"fen": fen, "stored_cp": stored, "split": round(split, 3),
                      "distinct_moves": distinct, "verdicts": verdicts}
            if distinct == 1 and len(controls) < want_controls:
                controls.append(record)
            elif distinct >= 3 and len(contested) < args.positions:
                contested.append(record)
            sys.stdout.write("\r{} examined  {} contested  {} controls".format(
                examined, len(contested), len(controls)))
            sys.stdout.flush()
    finally:
        for engine in engines.values():
            panel.quiet_quit(engine)

    payload = {"panel": names, "nodes": args.nodes,
               "contested": contested, "controls": controls}
    with open(args.out, "w") as handle:
        json.dump(payload, handle, indent=1)
    print("\n{} contested and {} control positions from {} examined -> {}".format(
        len(contested), len(controls), examined, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
