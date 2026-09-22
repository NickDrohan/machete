"""Stop games that are already over.

Two engines of similar strength spend a lot of time finishing positions whose
result nobody doubts. Measured over 722 of our own games, drawn games ran to a
median of 169 plies against 116 for decisive ones and consumed 20% of every
ply played, and decisive games still grind out long conversions after the
outcome is settled. Adding the same idea to the data generator took it from
800 to 1,385 positions a second.

The safety property is that **both engines must agree**. A single engine's
misjudgement cannot end a game: a draw is called only when both sides report a
near-zero score for a run of plies, and a win only when both sides agree on the
same side being far ahead. That is what makes this different from resigning on
one engine's opinion, which can hand a result to whichever engine is more
wrong.

Defaults follow the settings the engine-testing community has converged on,
conservatively: draws need both scores inside 10 cp for 10 plies and only
after move 40, so early symmetrical positions are not cut short; wins need
both scores past 1000 cp for 8 plies.

**Off by default, because it measured no gain in match.py.** Four paired runs
of the same self-play match came to 214s without and 216s with, inside a
192-236s run-to-run spread. The reason is that match.py's loop already ends
dead games: `is_game_over(claim_draw=True)` claims threefold repetition and the
fifty-move rule, so the shuffle-to-a-draw endgame terminates on its own, and
median game length is 118 plies against a 300-ply cap.

The generator is the opposite case and already adjudicates: it dropped
claim_draw for speed, since that call walks the move stack every ply, so its
games did run to the cap - and adjudication took it from 800 to 1,385
positions a second.

Kept and tested because it becomes worth switching on the moment games start
reaching the ply cap, at long time controls or against an opponent that will
not repeat. Left off so that new measurements stay comparable with every Elo
figure recorded so far, all of which were taken without it.
"""


class Adjudicator(object):
    def __init__(self, draw_score=10, draw_plies=10, draw_after=40,
                 win_score=1000, win_plies=8, enabled=True):
        self.draw_score = draw_score
        self.draw_plies = draw_plies
        self.draw_after = draw_after * 2      # moves to plies
        self.win_score = win_score
        self.win_plies = win_plies
        self.enabled = enabled
        self.reset()

    def reset(self):
        self.quiet_run = 0
        self.win_run = 0
        self.win_for_white = None
        self.last = {}

    def observe(self, board, white_to_move, score_stm):
        """Record one side's score, from the side to move's point of view.

        Returns a result string once both sides agree for long enough, else
        None. Scores are converted to white's point of view so the two sides'
        opinions can be compared at all.
        """
        if not self.enabled or score_stm is None:
            return None
        white_view = score_stm if white_to_move else -score_stm
        self.last["w" if white_to_move else "b"] = white_view
        if len(self.last) < 2:
            return None
        both = list(self.last.values())

        if board.ply() >= self.draw_after and all(abs(v) <= self.draw_score for v in both):
            self.quiet_run += 1
            if self.quiet_run >= self.draw_plies:
                return "1/2-1/2"
        else:
            self.quiet_run = 0

        if all(v >= self.win_score for v in both):
            side = True
        elif all(v <= -self.win_score for v in both):
            side = False
        else:
            side = None
        if side is None or side != self.win_for_white:
            self.win_run = 0
            self.win_for_white = side
        if side is not None:
            self.win_run += 1
            if self.win_run >= self.win_plies:
                return "1-0" if side else "0-1"
        return None


def score_of(info, white_to_move):
    """The side-to-move score from an engine's info dict, or None."""
    score = info.get("score") if info else None
    if score is None:
        return None
    pov = score.relative
    return pov.score(mate_score=10000)


def add_arguments(parser):
    parser.add_argument("--adjudicate", type=int, default=0,
                        help="stop games both engines agree are over; measured no "
                             "gain while claim_draw already ends dead games")
    parser.add_argument("--draw-score", type=int, default=10)
    parser.add_argument("--draw-plies", type=int, default=10)
    parser.add_argument("--draw-after", type=int, default=40, help="move number")
    parser.add_argument("--win-score", type=int, default=1000)
    parser.add_argument("--win-plies", type=int, default=8)


def from_arguments(args):
    return Adjudicator(draw_score=args.draw_score, draw_plies=args.draw_plies,
                       draw_after=args.draw_after, win_score=args.win_score,
                       win_plies=args.win_plies, enabled=bool(args.adjudicate))
