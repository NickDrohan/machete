"""Put an external corpus's labels on our teachers' scale.

    python harness/nnue/fit_scale.py CORPUS.bin --sample 20000 [--nodes 1500] [--out fit.json]

Our own corpora are labelled by five teachers at 1,500 nodes, each on its
own centipawn scale, and the trainer turns every label into a win
probability with one constant (sigmoid(cp / 150)). An external corpus such
as theoden8's (Stockfish 16 at depth 18-22, on Stockfish's normalised scale)
means something else by "100 centipawns", and mixing it in unfitted was
worth -68 Elo once (RESULTS.tsv, 2026-09-22). This samples positions from
the corpus, has each teacher score them at the budget our generator uses,
and fits the factor f that best makes sigmoid(f * external / 150) match the
teachers' mean win probability. It also fits f against each teacher alone:
if it is 1 against Stockfish and larger against the panel, the corpus is on
Stockfish's scale and the panel is not.

Castling rights and en passant are not stored in our records; the sampled
positions are set up without them, which changes almost no quiet
position's score at this budget.
"""
import argparse
import json
import math
import os
import sys

import chess
import chess.engine
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

ARENA = os.environ.get("MACHETE_ARENA", os.path.expanduser("~/Desktop/Games/Chess/arena_3.5.1"))
TEACHERS = {
    "Stockfish":   r"Engines\Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe",
    "PlentyChess": r"Engines\Plenty\PlentyChess-7.0.0-windows-ssse3.exe",
    "Reckless":    r"Engines\Reckless 0.9.0 dev-2a847427\reckless-windows-avx2.exe",
    "Obsidian":    r"Engines\Obsidian160-avx2.exe",
    "Caissa":      r"Engines\Caissa\caissa-1.23-x64-sse2.exe",
}
SCALE = 150.0
CLAMP = 2000


def board_of(row):
    board = chess.Board(None)
    for k in range(int(row["count"])):
        code = int(row["pieces"][k])
        colour = chess.WHITE if code < 6 else chess.BLACK
        kind = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING][code % 6]
        board.set_piece_at(int(row["squares"][k]), chess.Piece(kind, colour))
    board.turn = chess.WHITE if int(row["stm"]) == 0 else chess.BLACK
    return board


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def fit(external, teacher):
    """The f minimising the squared gap between sigmoid(f e / S) and the
    teacher's win probability, by a fine grid: one parameter, no surprises."""
    e = np.asarray(external, dtype=float)
    t = np.asarray(teacher, dtype=float)
    best = (None, None)
    for f in np.arange(0.4, 4.001, 0.01):
        err = np.mean((1 / (1 + np.exp(-f * e / SCALE)) - t) ** 2)
        if best[0] is None or err < best[1]:
            best = (f, err)
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--nodes", type=int, default=1500)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    records = np.fromfile(args.corpus, dtype=RECORD, count=3_000_000)
    step = max(1, len(records) // args.sample)
    rows = records[::step][:args.sample]
    boards, external = [], []
    for row in rows:
        b = board_of(row)
        if not b.is_valid() or b.is_game_over():
            continue
        boards.append(b)
        external.append(max(-CLAMP, min(CLAMP, int(row["score"]))))
    print("{} positions sampled from {} ({} skipped as invalid or over)".format(len(boards), args.corpus, len(rows) - len(boards)))

    scores = {}
    for name, rel in TEACHERS.items():
        path = os.path.join(ARENA, rel)
        engine = chess.engine.SimpleEngine.popen_uci(path, cwd=os.path.dirname(path))
        engine.configure({k: v for k, v in (("Threads", 1), ("Hash", 16)) if k in engine.options})
        got = []
        for b in boards:
            info = engine.analyse(b, chess.engine.Limit(nodes=args.nodes))
            s = info["score"].relative.score(mate_score=10000) if "score" in info else 0
            got.append(max(-CLAMP, min(CLAMP, s)))
        engine.quit()
        scores[name] = got
        f, err = fit(external, [sigmoid(s / SCALE) for s in got])
        med_ratio = np.median(np.abs(got)) / max(1.0, np.median(np.abs(external)))
        print("  {:<12} f = {:.2f}  (rms {:.4f}; median |score| ratio {:.2f})".format(name, f, math.sqrt(err), med_ratio))
        sys.stdout.flush()
    panel = np.mean([[sigmoid(s / SCALE) for s in scores[n]] for n in TEACHERS], axis=0)
    f, err = fit(external, panel)
    print("panel mean: f = {:.2f} (rms {:.4f}); multiply the corpus's scores by f to put them on the teachers' scale".format(f, math.sqrt(err)))
    if args.out:
        json.dump({"corpus": args.corpus, "sample": len(boards), "nodes": args.nodes, "f_panel": round(float(f), 3),
                   "per_teacher": {n: round(float(fit(external, [sigmoid(s / SCALE) for s in scores[n]])[0]), 3) for n in TEACHERS}},
                  open(args.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
