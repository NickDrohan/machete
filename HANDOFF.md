# Handing off the Mach side

This engine has two halves that barely touch. If you are here for the Mach
work, this says which files are yours, what the house rules are, and what is
actually open.

## The boundary

**Yours — everything that plays chess.** `src/*.mach` (4,569 lines),
`check.sh`, `fixtures/`. It compiles to one 218 KB binary that speaks UCI and
needs nothing else at runtime. Arena loads it directly.

**Not yours unless you want it — everything that measures.** `harness/*.py`
(4,845 lines): match drivers, the rating ladder, the tournament, the live
board, the training-data generator, the PyTorch trainer. Python never gets a
vote on a move. During a running tournament the split measures 83% engine,
17% harness.

The test for whether a change belongs on your side: delete `harness/` and the
engine still plays chess. Delete `src/` and there is nothing left to test.

## House rules

These are not style preferences. They came from being wrong.

**Every claim gets a gate, and every gate gets perturbed.** `check.sh` has 18.
A new one is not finished until it has been made to fail on purpose and the
failure recorded in the commit message. Two gates in this repo were green for
days while being structurally incapable of failing - one held a stale node
count, one had a literal `\n` where a line continuation belonged and had never
executed once.

**No performance claim without a measurement next to it.** Not "this should be
faster". A `bench` number, or nothing. Node rates are only comparable across
identical search trees; a change that alters pruning changes the tree, and
comparing nps across it measures nothing.

**Check the binary actually rebuilt.** A failed build leaves the previous
executable in place. That has produced a phantom regression, a passing gate on
an unbuilt exe, and two identical files presented as an A/B pair. Hash the
binary or check the exit code.

**Measure on a quiet machine.** An orphaned match process once held four cores
and put every nps figure 20% low.

## The Mach language, briefly

No type inference, no `else` (use `or`), no `while` (use `for`), no compound
assignment. `?x` is address-of, `@p` is dereference, `::` is a value cast,
`:~` is a bitwise reinterpret. Arrays take constant expressions. `sel` guards
tags. **An unreferenced module is not compiled**, which is a real trap: a file
can be broken and silent.

Two std limitations shaped code here: `i16x8` multiply is one instruction but
there is no packed 32-bit multiply (#3739) and no vector shifts (#3740). The
NNUE forward pass works around both by multiplying in `i16x8` and widening the
products by masking - see `src/nnue.mach`.

## What is actually open

Ordered by how much Elo is plausibly sitting in it. Full reasoning and the
evidence for each is in [ASSUMPTIONS.md](ASSUMPTIONS.md).

**The pruning constants have never been tuned against this evaluation.** NMP
`3 + depth/3`, LMR `0.75 + ln(d)ln(m+1)/2.25`, LMP `6 + depth^2`, RFP
`85*depth`, futility `120 + 110*depth`. Every one inherited from published
engines. The evaluation is now a network rather than the hand-written one
those margins were chosen against, and a different evaluation wants different
margins. This is the largest untapped source in the engine and nobody has
touched it.

**Continuation history may not be earning its place.** `-5.6 +/- 21` over
1,060 games, and it searches 4.5% *more* nodes to reach depth 8 (165,161
against 158,026). An SPRT against bounds [0, 10] ran to 1,060 games without
resolving and was stopped for the machine, not for the number. If it lands on
H0 the feature comes out and `fixtures/bench.expected` goes back to 158,026.
The ablation is one line: `cont_slot` returning -1 disables both the read and
the update.

**Won endgames are not converted, and there is no endgame knowledge at all.**
Over 1,884 self-play games, 80 ended drawn with one side a rook or more ahead.
Reproduced: KQ v K mates in 15 plies, but **KQ v KN and KBB v K both draw by
the fifty-move rule**. It is not a search bug - from KQ v K at depth 18 it
finds mate in 9 - it is that nothing in the evaluation rewards driving a king
toward a corner, so a win needing a plan rather than a capture has no gradient
to follow. `eval.mach` has no corner, edge or king-proximity term and no
mate-distance pruning, and with a network loaded the classical evaluation is
not consulted anyway. The harness half of the fix (endgame data, which the
generator's adjudication currently excludes by construction) is being handled
on the Python side. Roughly 4.2% of games are at stake.

**Not built yet:** singular extensions, staged move generation.

**Architecture, untested:** `HIDDEN = 256` has never been varied, so it is
possible every data experiment is bounded by the architecture rather than the
data. Wider accumulator, piece-count output buckets and mirrored king
conditioning are all unexplored.

**Known small debts:** `MAX_THREADS` is duplicated rather than having one
owner. `go ponder` still misbehaves and wants about ten lines to make safe.
The network is loaded from a file at runtime; `#[embed]` would fold it into
the binary.

## Running it

```bash
bash check.sh                      # 18 gates
bash ../../scripts/check.sh        # every product's gates

mach build . --profile release     # build
mach run   . --profile release -- bench    # run the built artifact
mach check .                       # type-check without building
```

`mach run` resolves the built artifact from the manifest, so there is no reason
to type `out/<target>/<profile>/bin/machete.exe` by hand - which most of this
repo's history did, in four places independently. The harness still needs a
real path, because python-chess spawns the engine itself and an A/B match
points at two renamed copies that no manifest describes; `harness/engine.py`
owns that path now, with `MACHETE_BIN` to override it.

Note that `mach run` does **not** rebuild. A failed build leaves the previous
binary in place, so `mach build` and `mach run` are two steps and the build's
exit code is the one that matters.

The harness needs Python 3.7 with python-chess for the game-playing scripts
and 3.13 with PyTorch for the trainer. `MACHETE_ARENA` points at the folder
holding Arena's `Engines` directory if yours is not on the Desktop; the
external engines are only needed by the measurement scripts, never to build or
test the engine itself.
