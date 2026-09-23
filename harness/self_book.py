"""Openings the engines choose for themselves, from the starting position.

Two single-threaded engines started from the same position play the same game:
the ladder's startpos run against Rybka was twenty copies of 1. e4 Nc6 2. d4 d5
3. e5 h5, split only at move five by timing noise. A book of canned positions
avoids that but puts words in the engines' mouths, and random walks hand one
side a lost position before either has thought.

So each engine picks its own variety. The side with White ranks its first moves
and the best `first` of them are kept; the side with Black ranks its replies to
each, and the best `replies` are kept. Every game starts from ply 0 with one of
those two-move openings, cycled so each is played before any repeats.

Ranking uses no engine option at all, so it works on any UCI engine: every
legal move is played, the engine evaluates the position after it, and the
moves are ordered by that score from the mover's side. MultiPV would be
quicker, but machete and several of the older opponents do not have it.

A move the engine itself rates more than `margin` centipawns below its best is
dropped, so no engine is made to play a move it thinks is bad. Rankings are
cached per engine and position, so each is computed once.
"""

import json
import os
import threading

import chess
import chess.engine

MATE = 100000
_cache_lock = threading.Lock()


def _load(path):
    if not os.path.isfile(path):
        return {}
    with open(path) as handle:
        return json.load(handle)


def ranked(engine, name, board, seconds, cache_path):
    """[(uci, centipawns)] best first, scored from the side to move."""
    key = "{} | {}".format(name, board.fen())
    with _cache_lock:
        cache = _load(cache_path)
        if key in cache:
            return [tuple(pair) for pair in cache[key]]
    scores = []
    for move in board.legal_moves:
        after = board.copy()
        after.push(move)
        info = engine.analyse(after, chess.engine.Limit(time=seconds), game=object())
        scores.append((move.uci(), -info["score"].pov(after.turn).score(mate_score=MATE)))
    scores.sort(key=lambda pair: -pair[1])
    with _cache_lock:
        cache = _load(cache_path)
        cache[key] = scores
        with open(cache_path, "w") as handle:
            json.dump(cache, handle, indent=1)
    return scores


def choices(scores, count, margin):
    """The best `count` moves that are within `margin` of the best."""
    best = scores[0][1]
    return [uci for uci, cp in scores[:count] if best - cp <= margin]


def openings(white, white_name, black, black_name, first, replies, seconds, margin, cache_path):
    """Two-move openings: White's own first moves, each with Black's own replies."""
    start = chess.Board()
    result = []
    for uci in choices(ranked(white, white_name, start, seconds, cache_path), first, margin):
        board = start.copy()
        board.push_uci(uci)
        for reply in choices(ranked(black, black_name, board, seconds, cache_path), replies, margin):
            result.append([chess.Move.from_uci(uci), chess.Move.from_uci(reply)])
    return result
