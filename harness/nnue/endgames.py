"""Training data for finishing a won game, which the main generator excludes.

    python harness/nnue/endgames.py data/endgames.bin --positions 4000000 --workers 12

The engine draws won endgames. Not all of them - it mates with KQ v K in 15
plies - but it fails whenever the win needs a plan with no material change,
like driving a king to a corner with two bishops, and 80 of 1,884 games in one
recent match ended drawn with one side a rook or more ahead.

The cause is that nothing in the evaluation distinguishes one won position from
another, and the reason for *that* is in this directory. `gen.py` adjudicates a
game once one side is 1,500 ahead for six plies, which is right for its purpose
and means the corpus contains no conversion technique at all: the positions
exist, but the *sequences* where a king is walked to the edge stop being
recorded exactly when they start. So this generator does the opposite job -
it starts from won endgames and plays them to mate with no adjudication.

## The label is the whole point

Writing a mate as a huge score would achieve nothing. The training target is
`sigmoid(score / SCALE)` with SCALE at 150, so +900 is already 0.9975 and
everything past it is 1.0 to five decimal places; a mate in 3 and a mate in 30
would both be 1.0 and the network would still have nothing to learn.

So distance to mate is mapped *into* the band the sigmoid can still resolve:

    score = NEAR - STEP * plies_to_mate,  clipped to [FAR, NEAR]

At the defaults that is 900 for a mate in one down to 400 for a mate in fifty,
which spans sigmoid 0.9975 to 0.9309 - a real gradient, where the raw scores
span nothing. The network is deliberately taught that KQ v K is worth about
+800 rather than +30000, because the engine does not need to know the
magnitude, it needs to know which way is downhill. Positions with no forced
mate yet keep the teacher's own score, clipped to the same band, so the two
label kinds meet rather than step.

This is the one place in the harness where a label is not simply the teacher's
evaluation, and it is a deliberate distortion with a measurable purpose:
`harness/endgame_suite.py` says whether it worked, and the tournament says what
it cost elsewhere.
"""

import argparse
import multiprocessing
import os
import random
import sys
import time

import chess
import chess.engine
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen
import panel
from reference import RECORD

NEAR = 900      # a mate in one, in centipawns on the training scale
FAR = 400       # a mate that is far enough away to be nearly flat
STEP = 10       # centipawns per ply of distance

# Material that is a forced win, and the ones this engine actually fails.
# Weighted towards the failures: KBB, KBN and queen-versus-a-piece are where
# the plan is long and the evaluation is flat, and KQ v K is included only so
# the easy case does not regress while the hard ones improve.
WINS = [
    (["Q"], [],        6),
    (["R"], [],        6),
    (["B", "B"], [],  14),
    (["B", "N"], [],  14),
    (["Q"], ["N"],    14),
    (["Q"], ["B"],    14),
    (["Q"], ["R"],    10),
    (["R"], ["N"],     8),
    (["R"], ["B"],     8),
    (["Q"], ["P"],     6),
    (["R"], ["P"],     6),
    (["R", "B"], [],   4),
    (["Q", "R"], [],   4),
]


def _pick(rng):
    total = sum(w for _, _, w in WINS)
    mark = rng.random() * total
    for strong, weak, weight in WINS:
        mark -= weight
        if mark <= 0:
            return strong, weak, weight
    return WINS[-1]


def build(rng):
    """Place kings and the winning material at random until it is legal."""
    strong, weak, _ = _pick(rng)
    winner = rng.choice([chess.WHITE, chess.BLACK])
    for _ in range(64):
        board = chess.Board(None)
        squares = rng.sample(range(64), 2 + len(strong) + len(weak))
        board.set_piece_at(squares[0], chess.Piece(chess.KING, winner))
        board.set_piece_at(squares[1], chess.Piece(chess.KING, not winner))
        at = 2
        ok = True
        for symbol in strong:
            piece = chess.Piece.from_symbol(symbol)
            piece.color = winner
            if piece.piece_type == chess.PAWN and chess.square_rank(squares[at]) in (0, 7):
                ok = False
                break
            board.set_piece_at(squares[at], piece)
            at += 1
        for symbol in weak:
            piece = chess.Piece.from_symbol(symbol)
            piece.color = not winner
            if piece.piece_type == chess.PAWN and chess.square_rank(squares[at]) in (0, 7):
                ok = False
                break
            board.set_piece_at(squares[at], piece)
            at += 1
        if not ok:
            continue
        board.turn = winner
        if board.is_valid() and not board.is_game_over():
            return board, winner
    return None, None


def label(score_cp, mate_plies):
    """Distance to mate, mapped into the band the sigmoid target can resolve."""
    if mate_plies is not None:
        value = NEAR - STEP * abs(mate_plies)
        value = max(FAR, min(NEAR, value))
        return value if mate_plies > 0 else -value
    if score_cp is None:
        return None
    return max(-NEAR, min(NEAR, score_cp))


def worker(index, args, counter):
    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    teacher = panel.open_engine(names[index % len(names)], args.hash)
    rng = random.Random(args.seed + index * 7919)
    share = args.positions // args.workers + 1
    mine = 0
    limit = chess.engine.Limit(nodes=args.nodes)
    try:
        with open("{}.{:02d}.part".format(args.out, index), "wb") as handle:
            while mine < share:
                board, winner = build(rng)
                if board is None:
                    continue
                rows, plies = [], 0
                while not board.is_game_over(claim_draw=True) and plies < args.max_plies:
                    info = teacher.analyse(board, limit)
                    relative = info["score"].relative
                    value = label(relative.score(), relative.mate() and relative.mate() * 2)
                    move = info.get("pv", [None])[0]
                    if move is None or move not in board.legal_moves:
                        break
                    if value is not None and len(board.piece_map()) <= args.max_pieces:
                        # result is filled in below, once the game has a winner
                        rows.append((gen.encode(board, value, 1, args.engine_id),
                                     board.turn))
                    board.push(move)
                    plies += 1
                # only keep games that were actually finished: a game that ran
                # out of plies is one the teacher could not convert either, and
                # its positions would teach exactly the behaviour being fixed
                if not board.is_checkmate() or not rows:
                    continue
                loser = board.turn            # the side to move is the mated one
                block = np.zeros(len(rows), dtype=RECORD)
                for slot, (row, turn) in enumerate(rows):
                    row["result"] = 0 if turn == loser else 2
                    block[slot] = row
                handle.write(block.tobytes())
                mine += len(block)
                with counter.get_lock():
                    counter.value += len(block)
    except KeyboardInterrupt:
        pass
    finally:
        panel.quiet_quit(teacher)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--positions", type=int, default=4000000)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--nodes", type=int, default=20000,
                        help="a mate has to actually be found, so this is higher than gen.py's")
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--max-pieces", type=int, default=7)
    parser.add_argument("--engines", default="Stockfish")
    parser.add_argument("--engine-id", type=int, default=0)
    parser.add_argument("--hash", type=int, default=64)
    parser.add_argument("--seed", type=int, default=99)
    args = parser.parse_args()

    counter = multiprocessing.Value("l", 0)
    workers = [multiprocessing.Process(target=worker, args=(i, args, counter))
               for i in range(args.workers)]
    started = time.time()
    for w in workers:
        w.start()
    try:
        while any(w.is_alive() for w in workers):
            time.sleep(5)
            done = counter.value
            rate = done / max(1e-9, time.time() - started)
            sys.stdout.write("\r{:,} positions  {:,.0f}/s".format(done, rate))
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    for w in workers:
        w.join()

    total = 0
    with open(args.out, "ab") as destination:
        for index in range(args.workers):
            path = "{}.{:02d}.part".format(args.out, index)
            if not os.path.exists(path):
                continue
            with open(path, "rb") as source:
                while True:
                    block = source.read(1 << 20)
                    if not block:
                        break
                    destination.write(block)
                    total += len(block)
            os.remove(path)
    print("\n{:,} positions written to {}".format(total // RECORD.itemsize, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
