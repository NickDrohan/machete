# machete

A chess engine in Mach, named for what it does to a variation tree. It speaks UCI, so it plays in any chess GUI and against the models in `llmchess`.
**Status: playing. Move generation, search and the UCI protocol are done and gated.**

```bash
scripts/mach build products/machete --profile release
out=products/machete/out/windows-x86_64/release/bin/machete.exe

$out                                  # UCI mode: speak the protocol on stdin/stdout
$out smp 8 3000 <fen...>              # search with 8 threads for 3 seconds
$out go 8 <fen...>                    # search one position, print bestmove
$out bench                            # fixed-depth node-count signature
$out perft 5                          # 4865609, from the start position
$out perft 4 <fen...>                 # any position; FEN may be several arguments
$out divide 3 <fen...>                # per-root-move counts, for comparing with a reference
```

## How it is built

Bitboards: one `u64` per piece code, plus a mailbox for "what is on this square". Leaper attacks
are precomputed tables; sliding attacks are magic-bitboard lookups, with the ray walker they
replaced kept as the reference the tests check them against.

Moves pack into a `u32` (from, to, 4-bit flag). Generation is pseudo-legal: it obeys piece
movement but may leave the mover's king in check, and callers make the move and ask
`left_in_check`. Castling is the exception, since an attacked transit square is invisible after
the move, so the king's start and transit squares are tested during generation.

`make` pushes an `Undo` record and `unmake` pops it, restoring the position exactly, including
the Zobrist key. The key is maintained incrementally and tested against a from-scratch recompute.
Nothing allocates: the position, its 1024-ply history and each move list are fixed arrays.

## Working on this

[ROADMAP_3500.md](ROADMAP_3500.md) is the plan from here to 3500, written as
work packages for agents. [HANDOFF.md](HANDOFF.md) is the entry point for the Mach side: which files are
the engine and which are the harness, the house rules and where they came
from, and what is genuinely open. [ASSUMPTIONS.md](ASSUMPTIONS.md) is the
evidence behind it.

## What the numbers rest on

`check.sh` proves the code does what it says. [ASSUMPTIONS.md](ASSUMPTIONS.md) is the other
half: the claims a gate cannot express, about whether a measurement means what we think it
means. It lists every assumption an Elo figure here depends on, marks each measured, open or
retired, and names the test. Two of its entries were found false and two gates were found
silent while it was being written, which is the argument for keeping it.

## Correctness

Move generation is the part of an engine where "looks right" is worthless, so nothing here
rests on inspection:

- **Published perft counts.** All six standard positions match exactly, to depths of millions of
  nodes (start depth 5 = 4,865,609; Kiwipete depth 4 = 4,085,603).
- **Differential testing.** `harness/perft_diff.py` compares `divide` against python-chess on
  random positions from random games. On a mismatch it descends into the first disagreeing move
  until it can name the exact position and move, then prints which moves were generated
  illegally and which legal ones were missed.
- **Unit tests** covering FEN round-trips, rejected malformed FEN, check detection, and exact
  unmake of castling, en passant and promotion-captures.

The differential harness was verified by breaking the engine: disabling en passant generation
made it report
`rnb1kbr1/1B1p3n/pP4P1/2p1p2p/4Pp1q/N6N/1PPP1P1P/R1BQK2R b q e3 0 16 — legal moves missed: ['f4e3']`.

An early failure came from this repo, not the engine: a mistyped FEN for standard position 6.
python-chess agreed with the engine, which is exactly what a second implementation is for.

## Speed

| | |
| --- | --- |
| perft 5 from the start position | 0.67s, ~7.3M nodes/second |
| search, one thread | ~1.0M nodes/second |
| search, 24 threads | ~14.5M nodes/second |
| startup | 2ms |

### Magic bitboards

A rook only cares about the occupancy of squares it can be blocked on. Masking those bits,
multiplying by a constant that spreads them across the top of the word and shifting down yields a
table index, so a sliding attack is one multiply, one shift and one load instead of four ray
walks. Measured against the ray walker it replaced, interleaved to control for drift: perft 0.67s
against 0.85s (1.26x), search about 8% faster, node counts identical.

The constants are found by a randomised search and committed. Two things keep that honest: the
lookups are checked against the ray walker over random occupancies and exhaustively over every
subset of the mask for two squares, and a separate test proves the *committed* constants are
valid without the startup fallback that would otherwise silently repair a bad paste.

### Hardware bit scans

std's `popcount` is the SWAR sequence and its `ctz` calls `popcount` again. x86-64 has had all
three as single instructions since 2008, so `bitboard.mach` uses them through inline assembly.
The assembler has no mnemonic for `popcnt`, `bsf` or `bsr`, so they go in as raw encodings with a
declared clobber set — reported upstream as briar-systems/mach#3724, which was accepted.

Worth **about 3%**: interleaved runs averaged 2225ms against 2300ms, faster in 5 of 6 pairs. The
interesting part is the negative result: bit scans were not the bottleneck. Every scan keeps a
`*_software` twin, tested to agree across ~1.2M values, so the fallback other targets take is a
tested path rather than dead code.

## Lazy SMP

Several threads search the same position, each on its own copy of the board, sharing only the
transposition table and an atomic stop flag. There is no work splitting: the table is the
channel, and the helpers drift into different move orders, which is what makes sharing pay.

| threads | 1 | 2 | 4 | 8 | 16 | 24 |
| --- | --- | --- | --- | --- | --- | --- |
| nodes/second | 1.06M | 2.16M | 3.89M | 6.65M | 11.5M | 14.5M |
| scaling | 1.0x | 2.0x | 3.7x | 6.3x | 10.8x | **13.7x** |

Nodes are not strength, so that was measured too: **8 threads beat 1 thread by +144 +/- 69 Elo**
over 120 games at 100ms a move.

The table is written without locks, and an entry caught half-written is *detected* rather than
tolerated: each slot holds the data word and the key xored with it, so a torn pair fails to
match and is ignored. See the Search section for the cost of that, which is none.

## Portability

The engine cross-compiles from Windows to statically linked ELF binaries for linux-x86_64 and
linux-aarch64, and a gate builds both. The aarch64 build takes the software path for the bit
scans. Neither is executed here, so the claim is "it compiles", not "it works".

## Search

Iterative deepening principal variation search: fail-soft alpha-beta, a 32 MB transposition
table, null-move pruning, late-move reductions, futility and reverse futility pruning,
aspiration windows, and a quiescence search over captures and promotions. Move ordering is the
transposition move, then queen promotions, then captures ranked by static exchange evaluation,
then killers and history. Evaluation is material, piece-square tables that taper the king into
the endgame, the bishop pair, and doubled, isolated and passed pawns.

### Every search change was matched before it was kept

Node counts and puzzle scores are not strength. Each change below played 300 games at 40ms a
move against the build immediately before it:

| change | bench nodes | Elo | verdict |
| --- | --- | --- | --- |
| aspiration windows | 1,890,407 -> 2,069,812 | +36 +/- 40 | kept, not proven alone |
| SEE ordering and quiescence pruning | -> 1,150,591 | +24 +/- 40 | kept, not proven alone |
| futility and reverse futility | -> 389,251 | **+68 +/- 40** | proven |
| **all three together, against the baseline** | 1,890,407 -> 389,251 | **+111 +/- 42** | **proven** |

The last row is the one that settles it. Two of the three changes cannot be proven on their own
at 300 games, but the stack they form is worth +111 Elo against the build before any of them,
and the individual estimates sum to +128, which is consistent with it.

The transposition table also moved to lockless hashing: each slot stores the data word and the
key xored with it, so an entry caught half-written by another thread fails to match and is
ignored instead of trusted. Node counts are identical, it is about 7% faster from the smaller
16-byte slots, and it removes the torn-entry caveat the parallel search used to carry.

Two of the individual intervals touch zero, which is simply what a 300-game match can resolve.
That is why
`harness/match.py` now also runs a sequential test (`--sprt elo0 elo1`): it stops as soon as the
evidence favours one hypothesis rather than always paying for 300 games. Validating it on a pair
with a known gap took 172 games instead of 300.

That validation run is also how a bug in it was found. The first version accepted "worth at least
10 Elo" after a single game: with no losses yet, the variance estimate collapses and the
likelihood ratio explodes. It now reports no evidence until both a win and a loss exist.

### The pruning campaign, and the test that was measuring the wrong thing

The engine was searching about ten times the nodes Stockfish did and reaching four plies less.
That is the effective branching factor - the ratio of nodes between consecutive depths - which was
about 2.4 here against roughly 1.5 for a strong engine.

Six changes attacked it. Measured on Kiwipete, single thread, to depth 12:

| stack | nodes to depth 12 | time |
| --- | --- | --- |
| before | 3,411,900 | 7119 ms |
| + logarithmic reduction table | 1,924,603 | 3641 ms |
| + late move pruning | 1,349,700 | 3029 ms |
| + null move at `3 + depth/3` | 876,271 | 1943 ms |
| + reverse futility to depth 8, internal iterative reduction | 807,300 | 1740 ms |
| + 128 MB table, delta pruning in quiescence | 645,156 | 1499 ms |

5.6x fewer nodes, and with 24 threads the depth reached in three seconds went from 11 to 15.
Then the games were played, at 40ms a move, and said the whole thing was worse:

| configuration | 40ms a move | 300ms a move |
| --- | --- | --- |
| reduction table alone | +12 +/- 23 (900 games) | - |
| + aggressive LMP, history, null | -53 +/- 40 | - |
| everything | -34 +/- 34 | +10 +/- 48 |
| everything, softened | -21 +/- 26 (700 games) | **+76 +/- 35 (400 games)** |

The bottom right cell is the one that matters, and it arrived last. **The same code is -21 Elo at
40ms a move and +76 at 300ms.** Aggressive pruning trades accuracy for depth, and depth only pays
when there is time to reach it: at 40ms the engine never gets deep enough to spend what the
pruning bought. Every earlier test ran at 40ms because it was cheap, which measured the wrong
regime and came within one commit of throwing the work away.

The softened configuration is what ships. Two of the six changes were bugs rather than bad ideas,
and finding them moved the same stack about 60 Elo: internal iterative reduction was firing in
principal variation nodes, dropping a ply exactly where the move gets chosen, and late move
pruning was cutting after seven quiet moves at depth 2.

One more lesson, cheaply bought: a 300-game match cannot resolve a 30 Elo change. The softened
stack measured +29 +/- 40 over 300 games and -21 +/- 26 over 700 at the same control. The first
number had already been written up as a success.

### Three changes the measurements rejected outright

- **Razoring** broke mate in two. Every other prune survived that fixture; this one did not.
- **Removing check extensions** lost both the mate-in-two and mate-in-three suites *and* was
  slower, because the search found nothing and re-searched.
- **A cheaper evaluation** was the obvious guess for the per-node cost. Material-only raised nps
  15% and searched 10% *more* nodes, for no net gain, so the evaluation was left alone rather
  than made incremental. Replacing the static exchange evaluation with plain MVV-LVA ordering
  also raised nps and cost 33% more nodes.

### Tactics are generated and proved, not chosen

`harness/make_tactics.py` plays random games to checkmate, rewinds, and keeps only positions
where python-chess proves a forced mate in exactly N with a unique first move. The engine solves
all 21 at the gated depths.

Those fixtures have now caught two real search bugs:

**Late-move reductions lost a mate in two** until depth 5, because a reduced search returned a
score at or below alpha, so no re-search fired and the mating move was discarded. The obvious
fix — never reduce anything tactical, and relieve PV nodes — found the mate but cost 41% more
nodes and measured -43 +/- 40 Elo. Split apart, only the PV relief mattered: it finds the mate on
its own for 33% and measured +1 +/- 39. The engine ships the cheaper half.

**Futility pruning lost a different mate in two** on its first run, by pruning a quiet mating
move. Whether a quiet move gives check is only knowable after making it, so the test moved to
after `make`. Same 66% node reduction, tactics intact.

## UCI

The search runs on its own thread, so `stop` and `isready` are answered while it is thinking, as
the protocol requires. `harness/protocol.py` drives the engine over its pipes and checks the
parts a normal game never reaches: `stop` returns a move in well under 500 ms, `isready` is
answered mid-search, malformed FENs and illegal moves in a `position` command do not take the
engine down, and mates are reported as `score mate` rather than centipawns.

`harness/match.py` plays engine against engine through python-chess, alternating colours and
playing each opening from both sides. With one engine it is a self-play soak test where any
illegal move, crash or hang fails the run; with two it prints an Elo difference with an error
bar.

`harness/vs_llm.py` plays the engine against a local Ollama model, which is how `machete` joins the
`llmchess` tournament. A first game against `qwen3.8:27b` is in
[`games/vs-qwen3.8-27b.pgn`](games/vs-qwen3.8-27b.pgn): the engine won a pawn on move 3. Cloud
models are refused so positions never leave this machine.

The `Hash` option is reported but fixed at 64 MB: the table is a static array, so the engine
allocates nothing at all, at startup or during search.

## Watching it play

`harness/watch.py` plays machete against another UCI engine and serves a live board on
`127.0.0.1:8730` — the position, the move list, and what each side thinks the score, depth and
node count are. It is one file with no CDN and no assets: the page is plain HTML with a polling
fetch, and the board is drawn with CSS grid and Unicode pieces.

```bash
python harness/watch.py                               # vs Stockfish at 1500 Elo
python harness/watch.py --elo 2200 --threads 8 --movetime 500
python harness/watch.py --opponent other-engine.exe --games 30
```

It plays games back to back, swapping colours each time, and keeps a running W-L-D tally, so the
board is never idle. This is a viewer rather than a measurement: `harness/match.py` is what
produces numbers, and nothing here is gated, because it needs an opponent engine that the gates
cannot assume is installed.

## Evaluation: the network

The hand-written evaluation is material, piece-square tables, the bishop pair and three pawn
terms. A blunder profile of 278 moves from real games said where that runs out: `positional
drift` accounted for 44 moves and 5,746 centipawns of loss, four times the next category. That
is not a search problem, and it is not a problem a few more hand-written terms would fix.

So machete also has a network. `768 -> 256 -> 1`, a perspective net: a feature is (colour, piece,
square) with all three relative to whichever side is looking, so one set of weights serves both
sides and black's view is white's view with the colours swapped and the board turned around. The
side to move's half of the hidden layer is read first, which lets the network learn that having
the move is worth something.

Everything is integers. Hidden values live on a scale where 1.0 is 255 and output weights on one
where 1.0 is 64, so the dot product lands on their product and one divide at the end gives
centipawns. The trainer clips weights every step so the quantized accumulator cannot overflow an
int16, and refuses to export a net whose worst-case accumulator would - a net can train
beautifully and then evaluate garbage once quantized, and that failure is silent.

The trained network ships as `net/machete.nnue`; load it with
`setoption name EvalFile value net/machete.nnue`. Without it the engine falls back to the
hand-written evaluation silently, which is the right behaviour for a missing file and a trap for
a mistyped one - check for `info string network loaded` if a result looks wrong. The two
evaluations disagree by design, so no score may be compared across that boundary.

It is worth **+259 +/- 44 Elo** over the hand-written evaluation: 400 games at 300 ms a move,
312 wins, 29 draws, 59 losses. Both sides are this same binary, so that number is the
evaluation and nothing else.

Getting there took two separate things, and for a while only one of them was true. The first
net, trained on half the data and running on a scalar forward pass, measured **+14 +/- 69** at
equal time - indistinguishable from no change at all. At equal *depth* the same net measured
**+135 +/- 75**. That pair of numbers is the whole diagnosis: the evaluation was already good,
and the engine was handing all of it back in search speed. `--depth` exists in `harness/match.py`
for exactly this, because a timed match answers two questions at once and cannot say which one
failed.

### The accumulator is never recomputed

A move changes at most four features, so the hidden layer is patched rather than rebuilt. The
patch hooks into `put` and `remove` in `position.mach` - the only two functions that touch the
board - which means castling, en passant and promotion need no special handling anywhere in the
network code. `make` copies the parent's hidden layer into the next slot and lets those two
functions patch it; `unmake` pops.

That last word cost an afternoon. The pop was originally the first line of `unmake`, which meant
the `put` and `remove` calls that restore the board wrote their patches into the *parent's* slot
and corrupted it. Every sibling move after the first was then evaluated from a poisoned
accumulator. Nothing crashed and the engine played on.

The gate that caught it plays a random game and, after every move, compares the patched
accumulator against one built from the board with no history. It failed on the first move of the
first game. It is in `movegen.mach` rather than `nnue.mach` because that is where legal move
generation lives, and generating legal moves makes and unmakes every pseudo-legal move on the
way - so the gate covers a slot being reused by one sibling after another, which is exactly the
case that was broken.

A second gate compares the engine's evaluation against `harness/nnue/reference.py`, an
independent numpy implementation of the same integer arithmetic, and requires them to be equal to
the centipawn rather than close. Perturbing the clipping bound by one moved a score from 3966 to
3973 and the gate caught it. The network it checks is generated from a seed rather than
committed, so the gate covers the code that writes the file as well as the code that reads it.

### 128 bits at a time

A network cost the search 3.0x its speed to begin with. Getting that to 1.05x took three
changes, and the order they are described in is not the order they were tried, because the first
guess about where the time went was wrong.

The idiom underneath all of it: a vector written as a literal is eight scalar loads and seven
lane inserts, so the pointer is reinterpreted instead and the whole register arrives in one move.

    fun load8(p: *i16, at: i64) i16x8 {
        ret @((?p[at]):~*i16x8);
    }

**Measuring the wrong thing.** Patching the hidden layer is 256 int16 additions per feature per
perspective, so the accumulator looked like the whole problem, and short-circuiting the forward
pass to a constant seemed to confirm it: 79,000 nodes per second became 89,000, apparently 12%.
That number was worthless. An evaluation that always returns zero prunes differently, so the two
runs searched different trees and their node rates were not comparable.

The honest version is a marginal cost: run the forward pass *twice* and keep everything else
identical. The tree stays byte-for-byte the same and the difference is what one extra pass costs.
It came to 2.98 microseconds a node, against a total network overhead of 2.95 - so the forward
pass was essentially the entire cost and the accumulator was already noise.

**Deferring the accumulator.** A search reaches 69,928 positions through make() at depth 9 and
evaluates 12,720 of them; the rest are illegal, or late move pruning throws them away. So a move
now records what it changed and returns, and the hidden layer is built only when something asks
for an evaluation - 13,398 slots built instead of 69,928. On its own this was worth almost
nothing, 3.00x down to 2.90x, because it was optimising the thing that was not the bottleneck.
Once the forward pass got fast it was worth 1.26x, and it stays.

**The forward pass.** Every product fits an int16 exactly, because a clipped hidden value is
0..255 and a weight is -127..127, and 255 * 127 = 32385. Only the sum needs to be wider.

The first attempt widened the inputs and multiplied in `i32x4`, and measured *slower* than
scalar - 222,000 nodes per second against 191,000. SSE2 has no packed 32-bit multiply, so that
multiply is emulated. Multiplying in `i16x8`, which is a single instruction, and widening only
the products afterwards gave 599,000.

Widening wants a shift, and Mach has no vector shifts yet: they are "deferred to a later
increment" because a per-lane variable shift is not 1:1 on the SSE2 baseline. So it is done by
masking. Reinterpreted as `i32x4`, the low half of each lane holds one product; a second pass
offset by one element puts the products in between into that same position, and a sum does not
care what order it is taken in.

    no network   801,000 nps
    network      765,000 nps

Medians of five runs on an idle machine. Both of those numbers are about 20% higher than the
first set recorded here, because that set was taken while a stopped harness run was still alive
and holding four opponent engines at full tilt. Nothing was wrong with the engine; the machine
was lying. Check what the box is doing before believing a node rate.

Run to run this benchmark varies by about 15%, so it resolves a 1.26x change and cannot resolve
a 1.05x one. `#[align(16)]` on the weights and the accumulator measured inside that noise in
both directions; it is kept because it states an assumption the SIMD loads were already making,
not because it was shown to be faster.

### Where the training data comes from

`harness/nnue/gen.py` has Stockfish 17 play itself from random openings and writes every
position with the score its own search gave and the result the game reached. Generating and
labelling are the same work that way: the search that picks the move is the search that produces
the label.

Three things in it were measured rather than assumed:

- **A node budget, not a depth.** At a fixed depth a sharp middlegame costs many times what a
  quiet opening does. 1,500 nodes reaches median depth 12 and costs 5.5 ms; 6,000 nodes reaches
  median depth 13 and costs 18.8 ms. Four times the budget bought one ply.
- **Processes, not threads.** python-chess drives every engine it owns from one asyncio loop on
  one thread. Twenty threads took turns through a single interpreter and the whole box did the
  work of about one core.
- **The cheap game-over test.** `is_game_over(claim_draw=True)` walks the move stack looking for
  a threefold repetition on every ply. It profiled at a seventh of the entire run - more than the
  position encoding and board copying together. Dropping it took a position from 15 ms to 10 ms.

### Which positions are worth keeping

The obvious optimisation is to train on the *good* positions rather than all of them, and the
obvious way to pick them is held-out loss. Both are wrong, measured on the board rather than
argued.

`harness/nnue/subset.py` cuts the 42.2M corpus into seven equal 8,000,000-position slices along
the axes worth suspecting, `harness/tournament.py` trains one network on each and plays them
all-play-all. 4,200 games:

| network | Elo | trained on |
|---|---|---|
| control | +245 +/- 27 | *the same file as uniform, entered twice* |
| spread | +244 +/- 27 | 1.6M from each of five teachers |
| uniform | +234 +/- 27 | random 8M of all 42.2M |
| solo | +210 +/- 28 | Stockfish only |
| decided | -86 +/- 34 | score at least 400 from equal |
| opening | -136 +/- 35 | 25 pieces or more |
| endgame | -342 +/- 35 | 12 pieces or fewer |
| balanced | -368 +/- 35 | score within 150 of equal |

`control` is the same network file as `uniform` entered a second time, so its true difference is
exactly zero. They finished 11 Elo apart and scored 0.493 against each other over 150 games.
That is the tournament measuring its own error in the same run as the result it qualifies, which
is what makes the rest of the table worth reading.

**No slice beat sampling the whole corpus.** And `balanced`, which has the best validation loss
in the field by a factor of 2.4, produces the weakest engine by 602 Elo - near-equal positions
are trivial to predict on a held-out slice of near-equal positions, so every subset scores well
on itself and the metric is circular. The ordering shows the mechanism: `decided` finishes 282
Elo above `balanced`, so knowing which positions are won matters far more than discriminating
finely near zero. A network that only ever saw a score within 150 of equal cannot tell +200 from
+800, and has nothing to steer toward.

## Deliberately not built

No opening book, endgame tablebases or pondering. Gated on windows-x86_64 only.
