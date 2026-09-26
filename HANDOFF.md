# Handing off the Mach side

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

**Every claim gets a gate, and every gate gets perturbed.** `check.sh` has 29.
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
bash check.sh                      # 29 gates; MACH=<path> to use a particular compiler

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

## Releases

**machete 0.1** is network A (md5 `b9f0183b`), about 3100-3200 on the CCRL
40/15 scale at 3+2 on one thread (ladder 4: Spike 1.4 and Rybka 2.3.2a, 40
games each). It was first released from mach-portfolio as `machete-v0.1`;
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
