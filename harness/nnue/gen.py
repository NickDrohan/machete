"""Generate labelled positions to train the network on.

    python harness/nnue/gen.py data/train.bin --positions 20000000 --workers 20

A strong engine plays itself from random openings, and every position it passes
through is written out with the score its own search gave and the result the
game eventually reached. Generating and labelling are the same work this way:
the search that picks the move is the search that produces the label.

The budget is a node count, not a depth. At a fixed depth a sharp middlegame
costs many times what a quiet opening does, so the finishing time of a run is
unknowable until it finishes; at a fixed node count it is arithmetic.

Openings are eight random plies, and one move in twenty is played at random, so
the games do not all run down the same few lines. Positions in check are
skipped: what they are worth belongs to the tactics that follow rather than to
anything a static network can learn.

The output is a flat array of fixed-size records; see RECORD. Each worker fills
its own shard and the shards are joined at the end, so an interrupted run still
leaves usable data behind.

Workers are processes, not threads. python-chess drives every engine it owns
from one asyncio loop on one thread, so twenty threads take turns through a
single interpreter and the whole box does the work of about one core.
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
import panel
from reference import RECORD

CLAMP = 10000           # mate scores become this, so one position cannot dominate
OPENING_PLIES = 8
RANDOM_MOVE_CHANCE = 0.02   # was 0.05: random moves are the main source of
                            # already-decided positions, which the sigmoid
                            # target flattens into no gradient at all
MAX_PLIES = 300
OPENING_BALANCE = 150   # a game starting further from equal than this is skipped
ADJUDICATE_AT = 1500    # once one side is this far ahead for a while, stop
ADJUDICATE_PLIES = 6

DEFAULT_ENGINE = os.path.join(
    r"~\Desktop\Games\Chess\arena_3.5.1",
    "Engines", "Stockfish", "stockfish", "stockfish-windows-x86-64-avx2.exe")


def encode(board, score, result, engine_id=0):
    row = np.zeros(1, dtype=RECORD)[0]
    row["engine"] = engine_id
    row["stm"] = 0 if board.turn == chess.WHITE else 1
    items = list(board.piece_map().items())
    row["count"] = len(items)
    for slot, (square, piece) in enumerate(items):
        colour = 0 if piece.color == chess.WHITE else 1
        row["pieces"][slot] = colour * 6 + (piece.piece_type - 1)
        row["squares"][slot] = square
    row["score"] = score
    row["result"] = result
    return row


def score_of(info, turn):
    score = info["score"].pov(turn)
    if score.is_mate():
        return CLAMP if score.mate() > 0 else -CLAMP
    return max(-CLAMP, min(CLAMP, score.score()))


def opening_position(book, rng):
    """Where a game starts: a real opening, or a short random walk."""
    if book and rng.random() < 0.4:
        return chess.Board(rng.choice(book))
    board = chess.Board()
    for _ in range(OPENING_PLIES):
        moves = list(board.legal_moves)
        if not moves:
            return None
        board.push(rng.choice(moves))
    return board


def play_game(engine, limit, rng, book, engine_id):
    """One game. Returns encoded rows with the result still to be filled in.

    The game-over test is deliberately the cheap one. python-chess's
    `is_game_over(claim_draw=True)` walks the whole move stack looking for a
    threefold repetition, which profiled at a seventh of the entire run - more
    than the position encoding and board copying put together. Here a game ends
    on mate, stalemate, bare material, the fifty-move counter, or the ply cap.
    A repetition just runs on to the cap and is recorded as the draw it is.

    Two filters keep the output useful rather than merely plentiful. A game
    whose opening is already lopsided is abandoned before it starts, and one
    that becomes lopsided is adjudicated rather than played out. Measured on
    the previous corpus, 55% of positions were beyond 400cp and only 9.7%
    inside 50cp - and the training target is a sigmoid, so everything in that
    55% sat flat against the top of the curve contributing almost no gradient.
    """
    board = opening_position(book, rng)
    if board is None or board.is_game_over():
        return [], None

    # refuse an opening that has already decided the game
    opening_info = engine.analyse(board, limit)
    if abs(score_of(opening_info, board.turn)) > OPENING_BALANCE:
        return [], None

    rows, turns = [], []
    outcome = "1/2-1/2"
    decided = 0
    while board.ply() < MAX_PLIES:
        legal = list(board.legal_moves)
        if not legal:
            if board.is_check():
                outcome = "0-1" if board.turn == chess.WHITE else "1-0"
            break
        if board.halfmove_clock >= 100 or board.is_insufficient_material():
            break

        info = engine.analyse(board, limit)
        score = score_of(info, board.turn)
        if not board.is_check():
            # encoded now rather than copied for later: a copy costs three
            # times what the encoding does
            rows.append(encode(board, score, 1, engine_id))
            turns.append(board.turn)

        if abs(score) >= ADJUDICATE_AT:
            decided += 1
            if decided >= ADJUDICATE_PLIES:
                ahead = board.turn if score > 0 else not board.turn
                outcome = "1-0" if ahead == chess.WHITE else "0-1"
                break
        else:
            decided = 0

        if rng.random() < RANDOM_MOVE_CHANCE:
            board.push(rng.choice(legal))
        else:
            move = info.get("pv", [None])[0]
            if move is None or move not in legal:
                move = engine.play(board, limit).move
            board.push(move)
    return list(zip(rows, turns)), outcome


def shard_path(out, index):
    return "{}.{:02d}.part".format(out, index)


def worker(index, args, counter):
    # every worker plays and labels with one engine for its lifetime, and the
    # workers are spread across the panel. Rotating per game would mean each
    # worker holding every engine open; rotating per worker costs nothing and
    # mixes the corpus just as well. It also varies the games themselves, not
    # only the labels: six engines steer middlegames six different ways, and a
    # corpus of one engine's self-play only ever visits that engine's taste.
    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    engine_name = names[index % len(names)]
    engine_id = index % len(names)
    engine = panel.open_engine(engine_name, args.hash)
    book = []
    if args.book and os.path.exists(args.book):
        with open(args.book) as handle:
            book = [line.strip() for line in handle if line.strip()]
    if args.nodes > 0:
        limit = chess.engine.Limit(nodes=args.nodes)
    else:
        limit = chess.engine.Limit(depth=args.depth)
    rng = random.Random(args.seed + index * 7919)
    share = args.positions // args.workers + 1
    mine = 0
    if index < len(names):
        print("worker {} -> {}{}".format(index, engine_name,
              " with {} book openings".format(len(book)) if book else ""))
    try:
        with open(shard_path(args.out, index), "wb") as handle:
            while mine < share:
                seen, outcome = play_game(engine, limit, rng, book, engine_id)
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
                mine += len(rows)
                with counter.get_lock():
                    counter.value += len(rows)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            engine.quit()
        except Exception:
            pass


def join_shards(out, workers):
    """Concatenate the shards into one file and remove them."""
    total = 0
    with open(out, "ab") as destination:
        for index in range(workers):
            path = shard_path(out, index)
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
    return total // RECORD.itemsize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--engines",
                        default="Stockfish,Berserk,Alexandria,Obsidian,Caissa,Seer",
                        help="panel members to rotate across workers")
    parser.add_argument("--book", default="data/book.epd",
                        help="opening positions; 40% of games start from one")
    parser.add_argument("--positions", type=int, default=20000000)
    parser.add_argument("--nodes", type=int, default=6000,
                        help="search budget per position; 0 uses --depth instead")
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--hash", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    directory = os.path.dirname(os.path.abspath(args.out))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    counter = multiprocessing.Value("l", 0)
    started = time.time()
    workers = [multiprocessing.Process(target=worker, args=(i, args, counter))
               for i in range(args.workers)]
    for process in workers:
        process.start()
    try:
        while any(process.is_alive() for process in workers):
            time.sleep(2.0)
            count = counter.value
            rate = count / max(1e-9, time.time() - started)
            left = (args.positions - count) / max(1.0, rate)
            sys.stdout.write("\r{:,} positions  {:,.0f}/s  {:.0f} min left    ".format(
                count, rate, left / 60.0))
            sys.stdout.flush()
    except KeyboardInterrupt:
        for process in workers:
            process.terminate()
    for process in workers:
        process.join()
    total = join_shards(args.out, args.workers)
    print("\n{:,} positions in {} ({:.1f} min)".format(
        total, args.out, (time.time() - started) / 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
