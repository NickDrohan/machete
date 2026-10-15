# Handing off machete

## 2026-10-04: LeelaKnightOdds path — 100% handicap Chess960

**Owner direction.** The 0.7 net is trained only on Fischer-random starts
with one side about a knight down (exactly the LeelaKnightOdds shape). Equal
material and classical C33 data stay out of that net. Labels should come from
a panel of top engines with Stockfish 19, and when they diverge a deeper
search resolves the vote.

**Panel tool (CONSENSUS-SMOKE).** `harness/nnue/consensus_label.py` scores
each position with Stockfish, PlentyChess, Reckless, Obsidian and Caissa
(LABEL-01 / D-07 panel — Berserk and Alexandria left out). Scores are pooled
in win-probability space; if the WP range exceeds a 50 cp gap around equality,
Stockfish searches at 16k then 48k nodes and, if still alone, its deep score
is the adjudicating vote. Engine id 12. Smoke on 400 X1 rows: 11.8% deepened,
about 15 positions/s with 2 workers.

**GPU tonight.** Done:
- `net_odds_sf.nnue` — full 30,000,851 X1, val loss 0.00902
  (NET-ODDS-SF). Packaged `E:/machete/candidates/odds_sf/`.
- Panel slice `x1_panel_2m.bin` — 2M rows, 23.5% deepened
  (PANEL-2M). `net_odds_panel2m.nnue` val loss 0.01480
  (NET-ODDS-PANEL2M). Packaged `E:/machete/candidates/odds_panel2m/`.

**Stage 1 result (SPRT-ODDS-SF).** Predicted **−25 Elo**. Actual: **+203 ± 72**
in 131 games at 10+0.1 (94–12–25), H1 accepted (LLR +3.06). Nets verified
distinct (sha256 odds_sf `b50a566f…`, x0 `25ac4c63…`); each side loaded its
folder's `machete.nnue`.

**That +203 does not mean the odds net is strong.** Diagnostics 2026-10-05
(80/60 games at 300 ms, balanced book, folder-loaded nets):
- odds_sf vs released 0.3.6 / C33: **0–1–79**, about −880 Elo
- net_x0 vs released 0.3.6 / C33: **0–0–80** (shut out; DIAG-X0-C33)
- odds_sf vs net_x0: **47–4–9**, about +260 Elo (reproduces SPRT-ODDS-SF)

So X1 (the Fischer / piece-down set) is intact and trains a net that beats
our 30M C33 *retrain*, but that retrain is itself far below real C33. The
odds net's eval on normal-chess positions is nearly uncorrelated with C33
(corr ~0.07 at 150k nodes). Live SPRT-ODDS-VS036 shows the same stomping
(0.3.6 winning almost every game); LLR stuck at 0 because the SPRT code
returns no evidence while wins=0.

**What we still have on disk**
- X1: `E:/machete/corpora/x1_handicap960_tb.bin` — **30,000,851** handicap960+TB
- Panel slice: `x1_panel_2m.bin` — 2M consensus labels (23.5% deepened)
- Nets: `net_odds_sf.nnue`, `net_odds_panel2m.nnue`, `net_x0.nnue`
- X2 done on pi-01 (CORPUS-X2): `…/pi-01/x2_handicap960.bin` — **20,000,129**, no takeback
- pi-01 now on `gap960_10m` (same book as CORPUS-GAP960, takeback 4, no odds)
- pi-02 still on X3 equal960+TB (~14.7M / 20M at ~150/s)

Next real test: not vs net_x0. Either mix odds data into a C33-scale corpus,
or measure odds-trained nets only as an *additive* slice on top of C33.

**Why odds_sf loses (ODDS-LOSSES, ODDS-MATERIAL-PROBE).** Stockfish 19 at
150k nodes graded every odds_sf move in its 89 lost games
(`harness/nnue/odds_losses.py`, `E:/machete/claude/odds_losses.json`):
- 85/89 games have a ≥150 cp blunder; 112 of 147 blunders at even material,
  mostly middlegame (median ply 38). 60% of games were already below −100
  before the first big blunder: slow drift out of the opening.
- Refutations: material tactic 59, quiet/strategic 51, king attack 37.
- It castled in 22 of 40 games with rights; 0.3.6 in 33 of 37. X1 had
  castling removed, so the net never saw a castled king.
- Piece values are flattened. Static eval of the start minus one black
  piece: knight +789, rook +905, queen +1034 (C33 +456 / +607 / +1200).
  In X1, a minor up labels 0.923 WP and a queen up 0.995. 51% of labels sit
  beyond 0.97/0.03, so sigmoid(cp/150) gives almost no gradient between them.

**Retrain in progress (TRAIN-C33HX2 / PREDICT-C33HX).** C33 recipe (364M) + X1 30M + X2 20M = **413,696,473** positions; 14 epochs, scale 150, blend 1.0, seed 7, window 120M. Output E:/machete/claude/nets/c33hx.nnue. Predicted **+15** vs 0.3.6. SPRT after train finishes and the net is packaged.

**Targeted data: CORPUS-GAP960** (Windows done: 10,000,727 records in 208 min at ~800/s; pi-01 twin still generating).1M/10M at ~877/s; pi-01 also
making a 10M twin). Still 100% Chess960 with a side a piece down, but the
other side pays for it, so labels stay in the sloped part of the sigmoid:
`harness/nnue/gap960_book.py` → `E:/machete/books/gap960.epd` (GAP960-BOOK):
minor-for-pawns, exchange, queen-for-R+minor/RR, rook-for-two-minors,
knight-for-bishop. Half use the 18 back ranks with the king on e and rooks on a/h,
with KQkq rights (the engine has no 960 castling). No `odds` flag: the
generator gate (|eval| ≤ 150) keeps the balanced starts (34% pass).
Smoke audit (GAP960-SMOKE-AUDIT): saturated labels 23% vs X1 51%, even
material 53% vs 22%, draws 34% vs 18%. Output
`E:/machete/corpora/gap960_10m.bin`. Training is not queued yet: the final
file appears during the merge, so a `--requires` chain could start on a
partial file. Train after the job shows done. Plan: X1 + GAP960 (40M),
same recipe, then compare against odds_sf and 0.3.6.

## 2026-10-04: the 0.7 corpus experiment, handicap Chess960 with take-backs

**The bet.** Training on handicap Chess960 games builds a stronger net for
normal chess than the same number of C33 positions. The take-back branches
make it denser.
- The starts are Chess960 with castling removed, 2 random plies, then one
  random side is about a knight down. The handicap is a knight, a bishop,
  3 non-centre pawns, or 2 pawns including a d/e pawn.
- Take-back works like a parent letting a child take a move back. At
  MultiPV-4 points where a second move is within 50 cp, the game is
  replayed from there with that move. Each tree is deduplicated.

Books and tools:
- Books (HANDICAP960-BOOK): `E:/machete/books/handicap960.epd` and
  `equal960.epd`, 20,000 positions each, from
  `harness/nnue/handicap960_book.py`.
- Generator flag: `takeback N` in `src/tools/gen.mach` and `gen.py`
  (GEN-TAKEBACK). Gate mode turns it off, and gate parity is still
  byte-identical.
- Known gap: `play_branch` does not recompute `ep_pot` while it replays the
  trunk.

Corpora (all 1,500-node Stockfish 19 labels):
- X0 control (CORPUS-X0): `E:/machete/corpora/x0_control_30m.bin`. A 30M
  uniform sample of the 18 C33 sources. Its net is
  `E:/machete/claude/nets/net_x0.nnue` (NET-X0): val loss 0.00382, 15/35 on
  the takeover suite.
- X1 = handicap960 + `takeback 4`, on the PC.
  - 20 workers, seed 71001, target 30M, about 1,130 positions a second.
  - Shards: `E:/machete/corpora/x1_handicap960_tb.bin.NN.part`.
  - **Done:** `E:/machete/corpora/x1_handicap960_tb.bin`, 30,000,851 records
    (finished ~00:53 on 10-05). Shard parts removed after merge.
  - `wait_train_x1.py` got stuck overnight (parts gone → it saw 0 rows).
    Restarted by hand 2026-10-05 ~09:48:
    - GPU: training `net_odds_sf.nnue` on the full 30M (SF labels).
    - CPU: panel-relabeling first 2M → `x1_panel_2m.bin`, then
      `net_odds_panel2m.nnue`.
- X2 = handicap960 without take-backs, on pi-01: `x2_handicap960.bin`,
  seed 72001, 3.46M of 20M at about 208 positions a second (~22 h left).
- X3 = equal960 + `takeback 4`, on pi-02: `x3_equal960_tb.bin`, seed 73001,
  2.50M of 20M at about 150 positions a second (~32 h left).
- pi-01's `stomp1` was stopped at about 3.87M. Its partial shards are still
  on the Pi.

Pilot (PILOT-X0X1): 3M-position nets from X0 and from the live X1 shards.
- Both train and quantize cleanly.
- Both search all 200 `balanced_200` positions without error.
- On the takeover suite X0 scores 15/35 (quiet 8/24) and X1 scores 13/35
  (quiet 5/24). That is noise. Only games will settle this.

Next steps:
- Stage 1: when X1 reaches 30M, train it with X0's recipe. Write a
  prediction, then SPRT X1 vs X0 at 10+0.1 on the balanced book through
  `harness/jobqueue.py`.
- Stage 2 (X2 vs X1, X3 vs X1) runs only if X1 is at least level.

## 2026-10-04: the stomp games, as a generation book

`2026_Machete3.6_Stomp.pgn`, 44 games at 180+3. Machete won none: 31 losses,
13 draws (STOMP-SEED). The other engine is already +80 centipawns, from its
own eval, at median ply 54. Machete's own eval does not drop hard until
median ply 125. The losses sit in the systems it chooses: the Catalan, the
Marshall (C89), the Vienna, the English, the Bogo-Indian.

`E:/machete/books/stomp_seed.epd` is the seed, 368 positions, written by
`harness/nnue/stomp_seed.py`. 231 are attack: the crusher to move as its
advantage crosses +80, +150 and +300. 137 are defend: machete to move on
the ply before that advantage appears, and on the later ply where its own
eval finally falls. One FEN each, and every line loads. A teacher playing
both sides from that book is the training set: the win, and the defense
against it. The comments in the PGN are not labels. Machete's scores are
the thing that was wrong.

Production: two runs of the same book, both with the sharp-stretch
generator. pi-01 `stomp1` is Stockfish 19 at 1,500 nodes, 3 workers,
seed 61005, target 8,000,000, about 140 positions a second. The PC,
after the Arena tournament was canceled, is `stomp_pc` at
`E:/machete/corpora/stomp_pc.bin`: the same teacher and node budget, 16
workers, seed 61006, the same 8,000,000 target, about 600 positions a
second. A leftover machete process was still searching and was stopped
so the cores were free. pi-01's Sveshnikov file `sv1.bin` is full
(20,000,115 records) and does not go into the next network. pi-02 was
stopped on its Sveshnikov run and moved to the odds book. The watchdog
log has not moved since 10-03 19:35.

The takeover suite (`E:/machete/books/stomp_takeover.epd`, 35 positions,
STOMP-MOVES): the current engine finds the move that first reached +80 in
19 of 35, and 12 of 24 when that move is quiet. Ten times the nodes flips
h3 and Qb6 onto the crusher's move. Qc7, Rc6, Rd8, g4 and Be4 stay wrong,
and Be4's score for the other move goes up. Those are the network. The
clock in this 180+3 event is not the hole: both sides spend a median of
3 seconds, and machete spends slightly more in the moves before +80 than
after.

LeelaKnightOdds and LeelaRookOdds play only from a start with that piece
missing, on a network built for that position. The rating is the rating of
those games. pi-02 was taken off the Sveshnikov run and is generating
`odds1` from `E:/machete/books/odds_kn.epd` (eight knight and rook starts),
Stockfish at 1,500 nodes, target 2,000,000. The opening gate is 700 for
that run, so a missing knight or rook is kept and a missing queen is still
skipped. This file is not mixed into the candidate until it has been
measured against C33. The stomp runs remain the equal-material games.

Candidate training started 2026-10-04: C36 is C33's recipe and C33's
files plus `stomp_pc.bin` (8,000,907 positions), one copy. 371,696,400
positions, hidden 768, 14 epochs, scale 150, blend 1.0, seed 7, window
120,000,000. Output `E:/machete/claude/nets/c36.nnue`. Finished 16:54, no error.
The odds file is not in it. The packaged candidate is
`E:/machete/candidates/c36/`: `machete.exe` and `machete.nnue`. It
answers `uci` as machete 0.3.6 and loads that network from its own
folder.

Prediction, written before any C36 game (PREDICT-C36). Against released
0.3.6 at 10+0.1, one thread, 128 MB: **+6 Elo**, a score of 50.9%. The
range I still expect to believe afterward is −12 to +20. Under about
2,000 games the match cannot tell +6 from zero. The speed is worth
about +3. The 8 million stomp positions are 2% of the file; a narrow
slice of that size has come out between −5 and +10 before, and the seed
noise of one training is ±6. Exploit mode adds about nothing in
self-play, because a jump of 80 centipawns is rare between equals. At
180+3 the same guess is +8, because the extra data is positions from
that kind of game and the speed matters less.

## 2026-10-04: one evaluation pass instead of a copy plus a pass per piece

On `feat/corpus-3000`. A quiet move used to copy a 768-wide half and then
add and subtract a column each. Those are one kernel now
(`apply_sub_add_avx2`), and a capture's two removals are
`apply_sub_sub_avx2` plus the arrival. The column kernels also issue four
independent AVX2 chains before they store. Integer results match the old
loops (the nnue test). Bench is still **154,921** nodes: the tree did not
change. On one middlegame, 8 interleaved runs, both sides searched
1,999,098 nodes; the paired nps ratio's median is **+4.3%** (SPEED-ACC).
That is the whole claim. A few percent of speed is a few Elo, not the
gap to 3000.

## 2026-10-03: 2760 to 3000 is not a rebuild of C33's corpus

Work on `feat/corpus-3000` (`D:/Dev/Claude/machete-corpus`), off the other
agent's checkout. Lichess is about 2760 on 0.3.6 / C33. +240 Elo is an 80%
score against the current engine. Nothing since C30 has moved more than +24,
and the last three data ideas are zero: more of the same games (C34, −3 ± 17),
attack games mixed in (C31, −18 ± 27), a Kalashnikov slice (C35, +1 ± 14).
One training's luck is about ±6 (C33S8).

Two measurements, before any retrain:

- **CORPUS-DUP.** The first 2M rows of every source C33 trained on: 35.4M
  rows, 1.72% duplicates, 0.16% of positions with labels more than 50 cp
  apart. Deduplicating this pile does not create a new corpus.
- **LABEL-DEPTH.** Stockfish 19 at 16,000 nodes versus 1,500, on 400
  `pi_gen4` positions inside ±400 cp: mean absolute gap **30.9 cp**, median
  16, correlation 0.945. Six percent move by more than 100 cp. C33 itself
  sits 69 cp from the longer search (correlation 0.764): that is the residual
  the 768-wide net already fits, and C34 showed more of these labels do not
  shrink it. Width 1024 on the same kind of data lost 17 Elo at equal time
  (SPRT-WIDTH-1024), so a bigger net without a faster evaluation is not free.

A careful retrain of the existing files, deeper labels on the same positions,
or another broad-book generation would repeat a result we already have.

What can still move the rating, in the order the games support. The 80
lichess draws and losses split 36 evaluation, 22 search or time, and the
clock is 15–20 points behind from move 10. Each of these is tens of Elo if
it works, not 240, and they have to be measured one at a time:

1. **Speed, then width.** 512 → 768 was +13 at equal time; 768 → 1024 was
   −17 because the evaluation got slower. 256-bit kernels are the thing that
   makes the width experiment real. A faster evaluation also buys the depth
   the 22 search errors missed.
2. **Search after a mistake** (`plans/attack-plan.md`). Yardstick: the
   3,114-position attack suite, where quiet moves and sacrifices are the miss.
3. **The clock against a booked opponent.** The opening discount was nothing
   in self-play, where both sides think in the opening. Lichess opponents
   play the first ten moves instantly.
4. **New data only after a net that can use it.** The untested corpus is not
   more games from the same book. It is positions the current net is wrong
   about, one copy, a second seed, then an SPRT and a packaged match. That
   waits on (1): mining hard positions for a net that is already at its
   capacity just reweights C33.

Openings stay as they are. No Sicilian beat the Marshall against full
Stockfish, and 0.3.7 lost on the bot.

## 2026-10-03: working from a clone

Everything needed to build, test and change the engine is in this repository
on `dev`. The training data, the LAION games, the job queues, the Raspberry
Pi farm and the lichess bot are on the owner's PC and are **not** here; the
paths under `E:/` below are that machine's. Do not copy the bot's lichess
token or any other credential to a cloud machine.

### Set up

```bash
# the compiler: Mach 6.10.1 (https://github.com/briar-systems/mach/releases/tag/v6.10.1)
curl -fsSL https://machlang.org/install.sh | sh   # installs the latest release; or unpack the v6.10.1 archive
mach dep pull .                       # mach-std 9.4.1, at the recorded pin
mach build . -p release -a machete    # also: -a arena, -a gen, -a trainer, -a binpack
mach test .                           # 58 tests; `-a arena`, `-a gen`, `-a trainer` for the tools' own
pip install chess numpy               # the harness; torch only for harness/nnue/train.py
MACH=mach PYTHON=python bash check.sh # the 35 acceptance gates
```

Mach 6.8 renamed two flags: `--bin X` is `-a X`, `--all-targets` is `-t '*'`.
The engine loads `machete.nnue` from beside the executable; `net/machete.nnue`
is 0.3.6's network (C33).

### What can be done from a clone

- Search and engine changes, measured with the match runner
  (`arena`, or `harness/match.py`): `arena A B --tc 10+0.1 --book harness/books/balanced_200.epd --sprt 0 10 --games 4000 --concurrency N`.
- The attack-suite yardstick needs `attack_suite.epd`, which is on the PC; ask for it or rebuild it with `harness/nnue/attack_suite.py` from engine miniatures.
- Network training needs the corpora (about 26 GB packed) and is not possible from a clone alone.

### Known issues, found while preparing this handoff

- `arena` against `harness/match.py` (`harness/arena_check.py`, 20 games at depth 5): 2 games differ, a draw declared one ply apart in games of about 190 moves; the results are the same. Present under Mach 6.5 and 6.10 alike.
- `harness/nnue/trainer_check.py` on `pi_gen4_pi01_snap1.bin`: the losses agree to 3e-07 relative, but one feature weight differs by 7e-03 after 10 steps, over the check's 1e-04 limit. Same under both compilers; the earlier pass was on another corpus.
- `harness/nnue/train.py` here is the fixed trainer (the old streaming window is dropped before the next is loaded). The prefetching version it replaces spilled past an 8 GB card into system memory and trained at a tenth of its speed.

## 2026-10-03: state, results and decisions

## State in one paragraph

**0.3.6 is the released version and it is what the lichess bot runs.** 0.3.7 (the Sveshnikov repertoire) failed both of its tests, was taken off the bot after about 40 games, and was never published; its PR is closed. Nothing is training or queued on the PC. Both Pis are generating Sveshnikov games, which is now the wrong opening, and have nothing queued after that. The one open decision is which Sicilian (or whether any) replaces the Marshall.

## Versions

| version | change | measured | where |
|---|---|---|---|
| 0.3.4 | network C30 | +24 ± 24 vs 0.3.3 | released |
| 0.3.5 | network C33 | +5 ± 11 vs 0.3.4 (4,000 games) | released |
| **0.3.6** | king-danger search fix | −1 ± 12 vs 0.3.5; sees the lichess mate at depth 18, not 22 | **released, on the bot** |
| 0.3.7 | Sveshnikov for the Marshall | **−16 ± 20** vs 0.3.6; lichess 1-3-7 as Black vs 1.e4 | **rejected**, PR #36 closed |

`dev` and `main` are at 0.3.6. `dev` also has Mach 6.10.1 and mach-std 9.4.1 (PR #35): same moves, bench 2–4% faster, all 35 gates pass. Build with `E:/machete/tools/mach-6.10.1/mach.exe`; `--bin` is now `-a`, `--all-targets` is `-t '*'`.

## What was learned (the numbers to keep)

**Networks**
- More broad self-play data has plateaued: C34 (+19.3M positions) is −3 ± 17 against C33.
- One training run's luck is about ±6 Elo: C33 with another seed is −6 ± 12. A network needs an SPRT **and** a packaged head-to-head.
- Narrow opening data did not help where it was aimed: C35 (C33 + 15.4M Kalashnikov positions) scored 8.2% as Black in the Kalashnikov against full Stockfish, C33 8.7%; +1 ± 14 in general play.
- Attack games mixed into training: −18 at three copies, undecided (slightly positive at most) at one.

**Openings**
- What lichess bots play decides the system. After 1.e4 c5 2.Nf3 **Nc6** they play the Rossolimo (3.Bb5) in 11 of 13 games; after 2...**d6** they play 3.d4 in 18 of 21 and never 3.Bb5+.
- LAION **averages mislead**: its openings are partly random. Rank by minimax (`laion_tree.py --minimax`). The Kalashnikov averages 51% for Black and is worth 36% under best play.
- machete as Black against full Stockfish 19 (like-for-like LAION books, ±2.5 points):

| 2...d6 systems, 400 games | score | | Bb5 lines, 250 games | score |
|---|---|---|---|---|
| Classical | 8.6% | | Moscow (2...d6 3.Bb5+) | 8.6% |
| Scheveningen | 7.5% | | Rossolimo 3...d6 | 8.0% |
| Najdorf | 7.0% | | Rossolimo 3...e6 | 7.6% |
| Dragon | 6.4% | | Rossolimo 3...g6 | 7.2% |
| | | | Rossolimo 3...Nf6 (0.3.7's) | 5.2% |

  Earlier, same test on other books: Marshall 11.0%, Sveshnikov 11.0%. **No Sicilian beat the Marshall here**, and the gaps between the 2...d6 systems are inside the noise.
- 0.3.6 with the Marshall on lichess: as Black vs 1.e4, 18 games, 4-6-8. On 0.3.3 it was 1-6-17; the newer networks may have fixed most of it. **The case for replacing the Marshall is weaker than it looked.**

**Lichess, 80 draws and losses at depth 22**
- 36 evaluation errors, 22 search or time errors (found at depth 16, missed in the game), 22 other.
- Draws are level games, not thrown wins. Losses are decided around ply 72.
- machete is 15–20 points of clock behind from move 10 (6.6 s a move in the opening against 2.9 s).

**Tried and not kept**
- Opening-clock discount (`feat/opening-clock`): nothing in self-play after 3,820 games. Needs a booked opponent to test.
- Continuation history, capture history: both below zero.

## Open decisions for the owner

1. **The Black repertoire against 1.e4.** Options: keep the Marshall (0.3.6 is doing acceptably with it); or a 2...d6 Sicilian, where the Classical tested best but not significantly. Any change gets its self-play no-cost check **before** it goes on the bot.
2. **What the Pis generate next.** Their queues are empty on purpose.
3. **The GPU.** Nothing worth training is queued. The next real GPU work is the Mach GPU trainer and a faster evaluation on Mach 6.10 (256-bit vectors, compute shaders).

## Suggested next steps, in order

1. **Search, the 22 of 80**: the "exploit mode" from `plans/attack-plan.md` (in this repository) (search quiet attacking moves deeper after the opponent's mistake). Yardstick: `suite_score.py` on the 3,114-position attack suite, where 0.3.4 finds 74.5% (68% of quiet moves, 63% of sacrifices).
2. **The clock**: a test against an opponent that plays its first ten moves instantly, then decide on `feat/opening-clock`.
3. **Speed**: AVX2 kernels as plain 256-bit vector code, then a wider network.
4. **Openings**: only with a field check, a minimax value and a full-Stockfish test, all three.

## What is running

| thing | state |
|---|---|
| lichess bot | running detached (`E:/machete/claude/r3/bot_start.cmd`), engine 0.3.6, 8 threads, Contempt 20 |
| CPU and GPU queues | runners alive, **nothing queued** |
| farm watchdog | running detached (`E:/machete/farm/watchdog.sh`), log `watchdog.log`; starts the next line of `queue-pi-0N.txt` when a Pi is idle |
| pi-01 | `sv1`, Sveshnikov book, 14.2M of 20M, done about 08:30 on 10-04 |
| pi-02 | `sv2`, Sveshnikov book, 2.3M of 20M, done about 00:00 on 10-05 |
| Pi queues | empty: the watchdog will log "idle and its queue is empty" hourly once a run ends |

Anything started from a Claude tool dies with the session; the bot, the watchdog and the queue runners were started through WMI and survive.

## Data on disk

- `E:/machete/corpora/`: `pi_gen4_pi01_sf19.bin` (20M broad), `attack_pi02_gen4_sf19.bin` (20M attack book), `kalashnikov_gen1_sf19.bin.*.part` (15.0M, PC) and `kalashnikov_snap1.bin` (15.4M, in C35), `attack_gen4_sf19.bin`.
- On the Pis, not pulled: pi-01 `gen5.bin` (20M broad), pi-02 `gen5.bin` (20M Kalashnikov), `sv1`, `sv2` in progress.
- `E:/chess-data/laion-chess/` (838 GB, 3.17B games) and `laion-index/` (opening, result, length per game).
- Books: `E:/machete/books/systems-laion/`, `open-d6/`, `rossolimo/` (tests); `kalashnikov_gen.epd`, `sveshnikov_gen.epd` (generation); `attack_suite.epd`, `attack_book.epd`.
- Networks: `E:/machete/claude/nets/` c30 to c35, c33s8.

## Code

- Engine repo `D:/Dev/Claude/machete-030`, currently on `feat/variety` (harness tools, pushed). `dep/std` shows as modified there; it is the 9.4.1 pin already on `dev`, harmless.
- Branches: `feat/sveshnikov` (0.3.7, rejected), `feat/opening-clock` (unproven), `feat/king-danger*` and `feat/mach-6.10` (merged).
- New harness tools on `feat/variety`, not yet on `dev`: `laion_index.py`, `laion_rank.py`, `laion_tree.py`, `laion_book.py`, `laion_prefix_book.py`, `laion_quality.py`, `system_books.py`, `suite_score.py`, `attack_detector.py`, `lichess_review.py --all-draws`.
- `D:/Dev/Claude/machete-train` (`feat/mach-trainer`): the Mach trainer, gen and arena; arena has `--a-colour`. Still on Mach 6.5.

## Mistakes to not repeat

- 0.3.7 went on the bot before its self-play check finished.
- An opening was recommended from an average over LAION games, then from minimax, without first checking what the field replies.
- The PC queues sat idle overnight three times (8 to 10 hours each) and the Pis twice. The watchdog now covers the Pis; the PC queues still need work queued ahead.

---

# Earlier handoffs

## machete 0.3.1 (2026-09-28)

0.3.1 is 0.3's search with a network twice as wide: C20, 8 king buckets x 768
-> 512 -> 8 output layers, trained on 262M positions through the streaming
trainer (`train.py --window`). The engine's width is `HIDDEN` in
`src/nnue.mach`, and every hand-encoded kernel comes from
`harness/nnuegen.py --hidden N` into `src/kernels.mach`; `check.sh` generates
its test networks at that width. Measured: +33 +/- 30 over 0.3.0 at 10+0.1
(CONFIRM-031A), 61.4% against 54.2% for 0.3.0 against Spike, Rybka and
Koivisto on the same openings (LADDER031, LADDER2), width alone +29 +/- 28
(SPRT-WIDTH-512). Speed: AVX2 accumulator kernels +13-20% with the 512-wide
network on Zen 3, Zen 4 and Zen+ (SPEED-AVX2-CLOUD; +4.3% was at 256 wide), the
move picker +3.9% (SPEED-PICK); Mach 6.5 itself neutral.

Open when 0.3.1 shipped: C21 (512 wide, + 20M Stockfish 19 positions) and
C22 (768 wide) training; whether streaming itself costs strength (C7W -17
+/- 15 against C7, C7W8 pending); SPSA of the search constants at 4,209 of
15,000 steps, never applied.

## machete 0.3 (2026-09-27)

0.3 is round 2's winner (COMPETITION_ROUND2.md): team cursor's entry, released
from issue #15. It is 0.2's search, unchanged (bench 154591), with the
king-bucket evaluation N-05 and network C7 - both team claude's round-1 work
(`claude/kb`, TRAIN-C7), which team cursor rebuilt on Mach 6, measured and
delivered. The final measured it at +54 +/- 34 (10+0.1, 200 games) and
+60 +/- 41 (60+0.6, 100 games) against v0.2.0; `release/notes-0.3.md` has the
table, `competition/round2/` both teams' SYNTHESIS.md, the referee's log and
the results. The network file format is MCHNNUE3 (8 king buckets x 768
inputs); `harness/nnue/reference.py` defines it.

Left for 0.3.1 and after, on 0.3.0's engine:

- team claude's accumulator cache (`claude2/kb` 0484d54, a Finny table) was
  measured on 0.3.0 the night of the release: no gain (median speed ratio
  0.997 over 12 rounds on a quiet machine, SPEED-CACHE-030) and dropped.
- the external ladder (ASSESSMENT.md): 0.3.0 and 0.2.0 are indistinguishable
  against other engines at 2+1 and at 10+0.1, so the king-bucket gain is
  family-specific; the next network work should be judged on the ladder,
  not only head-to-head. Deep labels in place of our own lost (C10 -23, C11
  -28); the seed noise floor is -2 +/- 14 (C7B).
- team claude's search work on `claude2/search`: continuation history (-3 +/-
  19 on its own), exchange and history pruning (-7 +/- 24), and, never measured
  on their own, capture history, ProbCut, the table's score for pruning,
  singular +2/-1, LMP/LMR refinements, a fifty-move fade of the evaluation,
  correction history by non-pawn pieces, and node-share time management. The
  stack cost 26% of the nodes per second, unexplained. Its constants are UCI
  options (U-01, U-03) and `harness/spsa.py` (U-02) tunes them.
- the pruning constants are still 0.2's, never tuned for a network evaluation.
- network C9 (C2's data + 30M Leela, without king buckets) trained but never
  tested; a king-bucket network on C7's data plus Leela's is the obvious next
  training.

## machete 0.2 (2026-09-26)

0.2 is team claude's entry from the Claude-vs-Cursor contest (COMPETITION.md):
claude/bundle with network C2, released from issue #10. What it holds and how
each part was measured is in `release/notes-0.2.md`, `ROADMAP_3500.md` and
`RESULTS.tsv` (SPRT-C-FULL, SPRT-C-FULL60, CONV-E02). The network file format
is now MCHNNUE2 (8 output layers); `harness/nnue/reference.py` defines it.

Left for after 0.2, measured but not shipped: the king-bucket build (N-05,
claude/kb) with network C5 came out level with 0.2 over 446 games (+10, -13
to +34) - its better evaluation costs 7% speed; networks C6-C8 were trained
but never tested; per-teacher centipawn scales were never fitted.


This engine has two halves that barely touch. If you are here for the Mach
work, this says which files are yours, what the house rules are, and what is
actually open.

## The boundary

**Yours — everything written in Mach.** `src/*.mach` (19 files, 5,458 lines),
`check.sh`, `fixtures/`. Two executables from one `mach.toml`:

- `machete` (220 KB, the default artifact) plays chess. It speaks UCI and needs
  nothing else at runtime; Arena loads it directly, and it loads
  `machete.nnue` from its own folder on start-up. Released as **machete 0.1**
  (see *Releases* below).
- `binpack` (171 KB, `src/tools/binpack.mach` over `src/binpack.mach`) decodes
  Leela Chess Zero's training data from Stockfish's binpack format into our
  training records, reusing the engine's own board and move generation. Its
  records are byte-identical to the Python reference, `harness/nnue/leela.py`,
  and it is 39x faster.

**Not yours unless you want it — everything that measures.** `harness/**/*.py`
(7,936 lines): match drivers, the rating ladder, the stable round robin and
its analysis, the training-data generator, the PyTorch trainer. Python never
gets a vote on a move. During a running tournament the split measures 83%
engine, 17% harness.

The test for whether a change belongs on your side: delete `harness/` and the
engine still plays chess. Delete `src/` and there is nothing left to test.

**machete exists to exercise Mach**, so moving Python work into Mach is
welcome, not scope creep - the binpack decoder was the first. What each port
teaches about the language goes in [MACH_FINDINGS.md](MACH_FINDINGS.md), and
from there upstream (the first: zstd, briar-systems/mach-std#913). machete
grew up as `products/machete` in the private mach-portfolio repository and
moved here, history and all, on 2026-09-25 (#1). The next candidate is the match runner - engines
on pipes, concurrent games, real clocks - which would work `std.process` and
`std.sync` hard and run every SPRT from then on.

## House rules

These are not style preferences. They came from being wrong.

**Every claim gets a gate, and every gate gets perturbed.** `check.sh` has 31.
A new one is not finished until it has been made to fail on purpose and the
failure recorded in the commit message. Two gates in this repo were green for
days while being structurally incapable of failing - one held a stale node
count, one had a literal `\n` where a line continuation belonged and had never
executed once.

**Documentation moves with the code.** Every change that measures, finishes,
or alters something updates the ledger and the docs in the same commit, before
the turn ends (ROADMAP rule 20; the checklist is
`.cursor/rules/docs-stay-current.mdc`, which Cursor agents load automatically).

**No performance claim without a measurement next to it.** Not "this should be
faster". A `bench` number, or nothing. Node rates are only comparable across
identical search trees; a change that alters pruning changes the tree, and
comparing nps across it measures nothing.

**Check the binary actually rebuilt.** A failed build leaves the previous
executable in place. That has produced a phantom regression, a passing gate on
an unbuilt exe, and two identical files presented as an A/B pair. Hash the
binary or check the exit code.

**Measure on a quiet machine, through the queue.** An orphaned match process
once held four cores and put every nps figure 20% low, and the owner runs
tournaments here. Every match, SPRT, ladder or data-generation run is a job
for `harness/jobqueue.py` (ROADMAP P0-5), never started by hand; its single
runner waits for a quiet machine and writes the ledger line. Before running
anything directly, `py -3.7 harness/jobqueue.py status` says what else is on
the machine.

## The Mach language, briefly

No type inference, no `else` (use `or`), no `while` (use `for`), no compound
assignment. `?x` is address-of, `@p` is dereference, `::` is a value cast,
`:~` is a bitwise reinterpret. Arrays take constant expressions. Tagged values
(`res`, `opt`, `err`) are read with `sel` guards. **An unreferenced module is
not compiled**, which is a real trap: a file can be broken and silent.

**Read the language skill from upstream**, `doc/skills/mach/SKILL.md` in
briar-systems/mach, not from a local clone of the compiler repo: one here was
three months stale, still calling tags unsupported, and nearly produced a false
bug report. Working code in `src/` is the other reliable reference.

The NNUE forward pass multiplies in `i16x8` and widens the products with a
vector literal of extended lanes (`i32x4{product[0]::i32, ...}`), which mach
5.11 packs (#3738). The three codegen issues it once had to work around -
#3738, #3739 (32-bit multiply), #3740 (vector shifts) - are all closed.

## What is actually open

**The prioritised plan is [ROADMAP_3500.md](ROADMAP_3500.md)** - work packages
with tiers, territories, measurement protocol and acceptance criteria. What
follows is the short version. Evidence for each item is in
[ASSUMPTIONS.md](ASSUMPTIONS.md); every measured result is in
[RESULTS.tsv](RESULTS.tsv).

**The pruning constants have never been tuned against this evaluation.** NMP
`3 + depth/3`, LMR `0.75 + ln(d)ln(m+1)/2.25`, LMP `6 + depth^2`, RFP
`85*depth`, futility `120 + 110*depth`. Every one inherited from published
engines. The evaluation is now a network rather than the hand-written one
those margins were chosen against, and a different evaluation wants different
margins. This is the largest untapped source in the engine and nobody has
touched it.

**Continuation history is gone** (ROADMAP S-01, done). SPRT-01 accepted H0
over 1,884 games, -6 +/- 16, and it searched 4.5% *more* nodes to reach depth
8. The table, its updates, its use in move ordering and the `ply` parameter
only it needed were all removed; the bench signature is 158,026, exactly what
the one-line ablation had measured, which is the proof the removal matches it.

**The static evaluation is computed once per node** (S-02, done). Reverse
futility and futility used to evaluate the same position separately. The bench
node count is unchanged by it, so the tree searched is identical and the
change is a pure saving.

**A search bug that drew won endings is fixed** (2026-09-24, `think()` in
`src/search.mach`). Iterative deepening stopped on any mate score, including
one read back from the transposition table at depth 1, then replayed the
table's move: it drew queen and bishop against a bare king by the fifty-move
rule while reporting mate in 19-30. It now stops only once the mate is
searched to its length. `harness/conversion.py` replays that game as a gate,
and `harness/divergence.py` measured the fix where it acts (132 differing
moves in 40,000 positions: 2 better, 0 worse).

**Hard won endings still convert only sometimes.** Five games each, 1 s a
move against Stockfish: KQ v KN 2/5, KQ v KR 1/5, KBB v K 4/5 (easy mates
5/5). That is the evaluation, not the search - nothing in it rewards driving
a king to a corner - and it is being fixed with data on the Python side
(`endgames.py`, and the new generator's mate-distance labels). `eval.mach` is
only the fallback when no network is loaded.

**Search, next.** Against Koivisto, half the games turned on a search mistake
(depth would have found the move), not an evaluation one. Not built yet:
singular extensions, correction history, capture history, staged move
generation.

**A like-for-like speed comparison with C++.** Stockfish's perft is 12x
machete's, but it counts the last ply's legal moves without making them, using
a pin-aware generator; machete makes, checks and unmakes every leaf. A legal
generator with bulk counting would make the engine faster and give the Mach
team a real Mach-against-C++ number. Against pure Python, Mach is 66-108x on
perft.

**Architecture, untested:** `HIDDEN = 256` has never been varied, so it is
possible every data experiment is bounded by the architecture rather than the
data. Wider accumulator, piece-count output buckets and mirrored king
conditioning are all unexplored.

**Known small debts:** `MAX_THREADS` is duplicated rather than having one
owner. (`go ponder` is fixed - ROADMAP X-04.)
`Hash` is reported but fixed at 128 MB (2^23 slots). The network is loaded
from a file at runtime - `machete.nnue` beside the executable, or `EvalFile` -
and `#[embed]` would fold it into the binary so a release is one file.

## Running it

```bash
bash check.sh                      # 31 gates; MACH=<path> to use a particular compiler

mach build . --profile release     # build both executables
mach run   . --profile release -- bench    # run the built engine
mach test  .                       # the engine's inline tests
mach test  . --bin binpack         # the decoder's
mach check .                       # type-check without building
```

The decoder reads uncompressed binpack; `python harness/nnue/leela.py
FILE.binpack.zst --decompress FILE.binpack` makes the copy, since std has no
zstd yet (mach-std#913).

`mach run` resolves the built artifact from the manifest, so there is no reason
to type `out/<target>/<profile>/bin/machete.exe` by hand - which most of this
repo's history did, in four places independently. The harness still needs a
real path, because python-chess spawns the engine itself and an A/B match
points at two renamed copies that no manifest describes; `harness/engine.py`
owns that path now, with `MACHETE_BIN` to override it.

Note that `mach run` does **not** rebuild. A failed build leaves the previous
binary in place, so `mach build` and `mach run` are two steps and the build's
exit code is the one that matters.

### Measuring: the job queue

```bash
py -3.7 harness/jobqueue.py status                 # queue, runner, team hours, what is busy
py -3.7 harness/jobqueue.py submit --team cursor --id SPRT-S06 \
    --change "S-06: mate distance pruning" --predicted +3 --against "cursor/main (abc1234)" \
    --tc "movetime 200" --requires E:/machete/cursor/ab/s06.exe -- py -3.7 -u harness/match.py ...
powershell -File harness/detach.ps1 "py -3.7 -u harness/jobqueue.py run"   # the one runner
```

One queue serves every worktree: `E:/machete/queue` (override with
`MACHETE_QUEUE`), with pending, running, done, failed and logs folders and the
runner's log `runner.log`. A job runs in the worktree it was submitted from
and writes that worktree's `RESULTS.tsv`. `--team` is required
(cursor, claude or owner - see COMPETITION.md). `--kind` is `measure` (the
default) or `data`, which share the cpu lane and wait for a quiet machine, or
`train`, which runs in a separate gpu lane beside them, one training at a
time. `data` jobs are charged to the team's budget (`budget.json`, 48 h) and
stopped at it.

Copy both binaries of an A/B out of `out/` and hash them before submitting:
the job runs later, and a rebuild in between would otherwise change what it
measures. `--requires` holds a job until its input exists, so a job can be
submitted before the network it tests has finished training - as long as it
points at the finished copy.

## Releases

**machete 0.1** is network A (md5 `b9f0183b`), about 3100-3200 on the CCRL
40/15 scale at 3+2 on one thread (ladder 4: Spike 1.4 and Rybka 2.3.2a, 40
games each; ladder 4 has no line in `RESULTS.tsv`, so treat the range as
unverified until P0-8). It was first released from mach-portfolio as `machete-v0.1`;
here it is `v0.1.0`.

Releases follow the template's flow (see *Releases* in the README): set
`version` in `mach.toml`, merge `dev` into `main`, push a `vX.Y.Z` tag, and
`.github/workflows/cd.yml` publishes a GitHub release with every executable
for every target. Two things it does not do yet, so a release is finished by
hand:

- **attach the network.** `net/machete.nnue` must sit beside `machete.exe`;
  the engine loads it from its own folder. `#[embed]` would end this step.
- **the release page.** `release/notes-X.Y.md` replaces the generated notes
  (`gh release edit vX.Y.Z --notes-file ...`), and `release/README.txt` goes
  in the Windows download. Check every number in both against the code: 0.1's
  notes caught a wrong thread limit and hash size.

The engine's UCI name is set in `src/uci.mach` (`id name machete 0.1`); bump
it with the version. Its `id author` still reads `mach-portfolio`.

## Python

The harness needs Python 3.7 with python-chess for the game-playing scripts
and 3.13 with PyTorch for the trainer. `MACHETE_ARENA` points at the folder
holding Arena's `Engines` directory if yours is not on the Desktop; the
external engines are only needed by the measurement scripts, never to build or
test the engine itself.
