"""Generate labelled positions to train the network on.

    python harness/nnue/gen.py data/train.bin --positions 20000000 --workers 20

A strong engine plays itself from positions reached in real games, and every
position it passes through is written out with the score its own search gave
and the result the game eventually reached. Generating and labelling are the
same work this way: the search that picks the move is the search that produces
the label.

The budget is a node count, not a depth. At a fixed depth a sharp middlegame
costs many times what a quiet opening does, so the finishing time of a run is
unknowable until it finishes; at a fixed node count it is arithmetic.

What changed on 2026-09-24, and why - each measured, not assumed:

  starts       every game from the book (15,875 positions from real games).
               Six in ten used to start from eight random plies, which reach
               positions nobody plays; Koivisto's wins over machete turned in
               the opening in 17 of 29 games.
  variety      one move in twenty is a near-best move - any of the teacher's
               top lines within VARIETY_MARGIN of its best - not a random one.
               Random moves were the main source of already-decided positions.
  repetition   a threefold repetition ends the game as the draw it is. It used
               to run on to the fifty-move rule, and one shuffle produced the
               same position dozens of times: 5-6% of network A's corpus were
               repeats, 10% of its endgame rows.
  once         a position is written once per game, however often it recurs.
  endings      with ENDGAME_PIECES or fewer pieces, the teacher searches
               ENDGAME_NODES_FACTOR times longer, so that mates are found, and
               the label is distance to mate in the band the training sigmoid
               can resolve (ending_label, shared with endgames.py). At 1,500
               nodes the teachers scored king and rook against king +3 to +5.
  teachers     Stockfish, PlentyChess, Reckless, Obsidian and Caissa, the five
               whose 1,500-node scores best match the round robin's depth-20+
               evaluations (RESULTS.tsv LABEL-01). Berserk and Alexandria, 40%
               of network A's labels, matched them worst of the strong engines.

Positions in check are skipped: what they are worth belongs to the tactics
that follow rather than to anything a static network can learn.

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
VARIETY_CHANCE = 0.05   # how often a near-best move is played instead of the best
VARIETY_MARGIN = 50     # ... chosen among the teacher's lines within this of its best
VARIETY_LINES = 4
ENDGAME_PIECES = 5      # kings included: KR v K, KQ v KN, KBB v K
ENDGAME_NODES_FACTOR = 20
MATE_NEAR = 900         # ending_label: a mate in one, on the training scale
MATE_FAR = 400          # ... a mate far enough away to be nearly flat
MATE_STEP = 10          # ... centipawns per ply of distance
MAX_PLIES = 300
OPENING_BALANCE = 150   # a game starting further from equal than this is skipped
ADJUDICATE_AT = 1500    # once one side is this far ahead for a while, stop
ADJUDICATE_PLIES = 6

TEACHERS = "Stockfish,PlentyChess,Reckless,Obsidian,Caissa"


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


def ending_label(score_cp, mate_plies):
    """Distance to mate, mapped into the band the sigmoid target can resolve.

    See endgames.py for why: a mate written as a huge score is 1.0 to five
    decimal places whether it is a mate in 3 or in 30, and the network then
    has nothing to learn about which way is downhill.
    """
    if mate_plies is not None:
        value = MATE_NEAR - MATE_STEP * abs(mate_plies)
        value = max(MATE_FAR, min(MATE_NEAR, value))
        return value if mate_plies > 0 else -value
    if score_cp is None:
        return None
    return max(-MATE_NEAR, min(MATE_NEAR, score_cp))


def position_key(board):
    """What makes two positions the same for repetition: pieces, turn, rights."""
    return (board.board_fen(), board.turn, board.castling_rights, board.ep_square)


def play_game(engine, limit, ending_limit, rng, book, engine_id):
    """One game. Returns encoded rows with the result still to be filled in.

    The game-over test is deliberately the cheap one. python-chess's
    `is_game_over(claim_draw=True)` walks the whole move stack looking for a
    threefold repetition, which profiled at a seventh of the entire run - more
    than the position encoding and board copying put together. Here a game ends
    on mate, stalemate, bare material, the fifty-move counter, the ply cap, or
    a threefold repetition counted in a dictionary as the game goes.

    Two filters keep the output useful rather than merely plentiful. A game
    whose opening is already lopsided is abandoned before it starts, and one
    that becomes lopsided is adjudicated rather than played out. Measured on
    the previous corpus, 55% of positions were beyond 400cp and only 9.7%
    inside 50cp - and the training target is a sigmoid, so everything in that
    55% sat flat against the top of the curve contributing almost no gradient.
    """
    board = chess.Board(rng.choice(book))
    if board.is_game_over():
        return [], None

    # refuse an opening that has already decided the game
    opening_info = engine.analyse(board, limit)
    if abs(score_of(opening_info, board.turn)) > OPENING_BALANCE:
        return [], None

    rows, turns = [], []
    outcome = "1/2-1/2"
    decided = 0
    seen = {}
    while board.ply() < MAX_PLIES:
        legal = list(board.legal_moves)
        if not legal:
            if board.is_check():
                outcome = "0-1" if board.turn == chess.WHITE else "1-0"
            break
        if board.halfmove_clock >= 100 or board.is_insufficient_material():
            break
        key = position_key(board)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3:
            break

        ending = len(board.piece_map()) <= ENDGAME_PIECES
        info = engine.analyse(board, ending_limit if ending else limit)
        score = score_of(info, board.turn)
        if seen[key] == 1 and not board.is_check():
            label = score
            if ending:
                relative = info["score"].relative
                label = ending_label(relative.score(), relative.mate() and relative.mate() * 2)
            # encoded now rather than copied for later: a copy costs three
            # times what the encoding does
            rows.append(encode(board, label, 1, engine_id))
            turns.append(board.turn)

        if abs(score) >= ADJUDICATE_AT:
            decided += 1
            if decided >= ADJUDICATE_PLIES:
                ahead = board.turn if score > 0 else not board.turn
                outcome = "1-0" if ahead == chess.WHITE else "0-1"
                break
        else:
            decided = 0

        move = info.get("pv", [None])[0]
        if rng.random() < VARIETY_CHANCE:
            # a second, multi-line search picks the move; the label above
            # stays the single-line search's, at full strength
            lines = engine.analyse(board, limit, multipv=VARIETY_LINES)
            best = score_of(lines[0], board.turn)
            near = [line["pv"][0] for line in lines
                    if line.get("pv") and best - score_of(line, board.turn) <= VARIETY_MARGIN]
            if near:
                move = rng.choice(near)
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
    # only the labels: five engines steer middlegames five different ways, and
    # a corpus of one engine's self-play only ever visits that engine's taste.
    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    engine_name = names[index % len(names)]
    engine_id = index % len(names)
    engine = panel.open_engine(engine_name, args.hash)
    with open(args.book) as handle:
        book = [line.strip() for line in handle if line.strip()]
    if args.nodes > 0:
        limit = chess.engine.Limit(nodes=args.nodes)
        ending_limit = chess.engine.Limit(nodes=args.nodes * ENDGAME_NODES_FACTOR)
    else:
        limit = chess.engine.Limit(depth=args.depth)
        ending_limit = chess.engine.Limit(depth=args.depth + 6)
    rng = random.Random(args.seed + index * 7919)
    share = args.positions // args.workers + 1
    mine = 0
    if index < len(names):
        print("worker {} -> {} with {} book openings".format(index, engine_name, len(book)))
    try:
        with open(shard_path(args.out, index), "wb") as handle:
            while mine < share:
                seen, outcome = play_game(engine, limit, ending_limit, rng, book, engine_id)
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
        panel.quiet_quit(engine)


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
    parser.add_argument("--engines", default=TEACHERS,
                        help="panel members to rotate across workers")
    parser.add_argument("--book", default="data/book.epd",
                        help="positions from real games; every game starts from one")
    parser.add_argument("--positions", type=int, default=20000000)
    parser.add_argument("--nodes", type=int, default=6000,
                        help="search budget per position; 0 uses --depth instead")
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--hash", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    if not os.path.exists(args.book):
        parser.error("the book {} is missing; every game starts from it".format(args.book))

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
