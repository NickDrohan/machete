# Handing off machete

## 2026-10-04: the 0.4.0 match, the chunk catalog, the mate dataset

**The 0.4.0 match** (`E:/machete/competition/v040/RESULT.md`): `c36` (the dev engine with a new network, C36) against `0.4.0_perplexity` (0.3.6's exact search about 4.5% faster on this PC, network C33), by the neutral referee at tag `referee-v1`.

| phase | games | c36 W-D-L | points | c36 Elo (95%) |
|---|---|---|---|---|
| 10+0.1 | 400 | 75-237-88 | 193.5 - 206.5 | -11.3 +/- 21.0 |
| 60+0.6 | 100 | 13-71-16 | 48.5 - 51.5 | -10.4 +/- 34.1 |
| pooled | 500 | 88-308-104 | 242 - 258 | -11.1 +/- 18.2 |

Perplexity's entry wins on points (51.6%); the interval contains zero. The 10+0.1 phase was clean. Another session started a 20-worker generator 16 minutes into the 60+0.6 phase, so that phase ran on an overloaded machine (no forfeits), and the two context matches against 0.3.6 are invalid (146 and 43 time forfeits in 200 games each). Perplexity's archive held only Linux binaries; its Windows engine was built by the referee from its source bundle at the commit in its `READY`. The owner has not yet said whether to replay the loaded phases. A live scoreboard for referee result files is `E:/machete/competition/v040/scoreboard.py`.

**Cursor's corpus** (as the owner described it; Cursor's own notes are the source): training entirely a piece down, from Fischer Random positions. Its files in `E:/machete/corpora` are `x0_control_30m.bin` and `x1_handicap960_tb.bin` (generating, 20 Stockfish workers). When it runs, the PC has no spare threads: matches lose games on time.

**The chunk catalog** (`catalog/`, page: `catalog/chunk-catalog.html`): every training chunk, the networks trained on it, and what each experiment that isolated a chunk measured: 31 chunks, 37 training runs, 19 experiments. It could be built in retrospect because every training run's corpus list is in the GPU queue's job records. `catalog/chunks_meta.json` is the hand-kept half (what a chunk is, what an experiment measured); `python harness/nnue/chunk_catalog.py` regenerates `catalog.json`, `chunk_ledger.tsv` (the record of Elo shifts by chunk) and the page. **To record a new chunk trial: add the chunk and one experiment to `chunks_meta.json` and run the script.** What the record says so far: the only chunks with an interval clear of zero are the foundation (removing or halving it costs 28 to 54 Elo) and the repertoire set (+10 +/- 8, from a running log); the Pi farm's broad-book positions gave +16 +/- 19 once and then nothing; attack, conversion and narrow-opening chunks have not shown a gain; one training seed is worth about +/-6.

**The deep-mate dataset** (`harness/nnue/mate_retro.py`, output `E:/machete/mates/retro.jsonl`): the owner's design. A random checkmate (3 to 32 men, a normal army), then a reverse search: take back a move, and keep the predecessor only when Stockfish 19 proves a forced mate exactly one ply longer. Taking back an attacker's move always leaves a forced mate; taking back a defender's move does only if every other defender move also loses, which is what the proof checks. It is a sampled reverse search (a beam), not the whole tree. Each line has the FEN, the distance in plies, the attacker, Stockfish's line, the proof's nodes, the seed and the parent. A trial of 204 positions reached 10 plies; 16 re-proved with 10 to 100 times the nodes all kept their distance. It runs at idle priority from its own clone (`D:/Dev/Claude/machete-mates`, `E:/machete/mates/run.sh`, log `run.log`), one seed at a time, until stopped. **Not done yet:** a converter from `retro.jsonl` to a training chunk, and the first network trained with it; when that happens it goes in the catalog like any chunk. The positions are chaotic by construction (they come from random mates, not games); whether that helps or hurts is what the chunk experiment is for.
**The self-play league** (`harness/rl/league.py`, state in `E:/machete/rl`): the owner asked for a reinforcement-learning harness where the two Pis play each other with networks trained on the Fischer Random and deep-mate chunks, to see whether it finds moves Stockfish likes. Built and smoke-tested; **not started for real**, because (1) both Pis are running Cursor's generators, (2) the deep-mate chunk has a few hundred positions, (3) no network trained on both chunks exists yet (only Cursor's 3M pilot, `net_x1_3m.nnue`).
How it works: pi-01 plays the champion, pi-02 the challenger, one engine each, driven from the PC over ssh at a fixed node count. A generation is `play` (the games become a chunk labelled by the movers' own search scores and results), `judge` (Stockfish 19 on the PC scores a sample of the moves: first-choice rate, top-three rate, centipawns given up; written to `approval.tsv`; never a training signal), `train` (`train.py --init`, new: the champion fine-tuned on the last generations' chunks), `promote` (55% or more against the champion). The engine on the Pis is cross-compiled here (`mach build . -p release -a machete -t linux-aarch64`) and lives in `~/machete/rl` with its networks.
To start: `python harness/rl/league.py deploy --engine out/linux-aarch64/release/bin/machete --net START.nnue`, then `... loop --games 200 --nodes 30000 --concurrency 3`.
What the smoke test (two generations of four games, `E:/machete/rl-smoke`) showed: 569 moves in 81 s at 8,000 nodes with one engine a Pi; fine-tuning on 509 positions made the network worse and the yardstick caught it (first choice 38.7% against the champion's 51.7%, 41.9 cp a move given up against 14.0). A generation needs thousands of games, not four. The engine does not play Chess960 (no 960 castling), so league games start from the ordinary balanced book.

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

**0.3.6 is the released version and it is what the lichess bot runs** (still true on 2026-10-04; see the section above for what has happened since). 0.3.7 (the Sveshnikov repertoire) failed both of its tests, was taken off the bot after about 40 games, and was never published; its PR is closed. Nothing is training or queued on the PC. Both Pis are generating Sveshnikov games, which is now the wrong opening, and have nothing queued after that. The one open decision is which Sicilian (or whether any) replaces the Marshall.

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
