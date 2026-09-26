# Machete: the road to 3500

A work plan for agents. Each work package (WP) below is meant to be picked up
by one agent, done on one branch, measured once, and either merged or recorded
as a failure. Read sections 1 to 5 before touching any WP; they are short and
every rule in them exists because it was broken at least once.

Companion files: [HANDOFF.md](HANDOFF.md) (boundary and house rules),
[ASSUMPTIONS.md](ASSUMPTIONS.md) (the evidence behind every claim),
[RESULTS.tsv](RESULTS.tsv) (the ledger of every measured result).

---

## 1. Where we stand — updated 2026-09-25

### The engine today, and what is and is not measured about it

The shipping engine (machete 0.1, network A) is **not** the one LADDER-02
rated. Since then S-03, S-04 and S-05 merged and network A replaced the old
network; CONFIRM-01 measured the combination against the LADDER-02 engine at
**+109 +/- 49** (200 ms, 214 games). A self-play gain does not transfer one to
one onto a rating scale, so the honest statement is: **the current engine has
no rating of its own in the ledger.** `HANDOFF.md` quotes "about 3100-3200
(ladder 4: Spike and Rybka at 3+2)"; ladder 4 has no line in `RESULTS.tsv`
and two anchors are not a rating. P0-8 is what fixes this.

The reference field was re-run as **FIELD-02** (3+2, one thread, 128 MB, no
engine books, balanced book): 360 games, 78% drawn, spread 173, with Black
Marlin (-105) now the floor and Koivisto at -58. Section 2 uses FIELD-02.

Everything below this block, down to "The engine, profiled", is the
2026-09-22 picture, kept because the per-opponent detail is still the best
available.

### Rating (2026-09-22, the engine before network A)

| measurement | result | status |
|---|---|---|
| LADDER-01, 200 ms/move | 2769 +/- 122 | superseded |
| LADDER-02, 1000 ms/move | **2928 +/- 78**, chi2/dof 1.59 | **best estimate** |

LADDER-02's per-opponent results, 60 games each at 1000 ms a move:

| opponent | CCRL (as configured) | W-D-L | score | implied |
|---|---|---|---|---|
| AnMon 5.75 | 2400 | 53-4-3 | 0.917 | 2817 +/- 225 |
| SOS 5.1 | 2500 | 53-5-2 | 0.925 | 2936 +/- 258 |
| Ruffian 1.0.5 | 2570 | 49-6-5 | 0.867 | 2895 +/- 151 |
| Hermann 2.8 | 2600 | 49-7-4 | 0.875 | 2938 +/- 157 |
| Spike 1.4 | 2950 | 32-9-19 | 0.608 | 3026 +/- 92 |
| Rybka 2.3.2a | 3050 | 5-14-41 | 0.200 | 2809 +/- 119 |
| Koivisto 9.0 | 3300 | 1-2-57 | 0.033 | 2715 +/- 986 |

**A retracted claim.** An earlier version of this roadmap called Rybka an
invalid anchor, said it had played on up to 24 threads, and quoted 2963 +/- 65
without it. That was wrong, and how it was wrong is worth knowing. The claim
came from reading a *default option* (`Max CPUs` 2048), not from watching the
process: measured, Rybka runs **3 threads idle and 3 throughout a timed
search** on this 24-CPU machine. The "inconsistency" it was meant to explain was
not significant either - chi2 of 9.5 on 6 degrees of freedom has p = 0.15, and
with seven anchors there is an 18% chance one sits 2.2 standard deviations out
by luck alone. The supporting arithmetic was circular: dropping the largest
outlier always lowers chi2. 2928 +/- 78 stands. If Rybka's pairing is off at
all, the likelier cause is its anchor value (3050, unverified - P0-6).

**Two further caveats on the number.** `net/machete.nnue` was replaced after
LADDER-01 ran, so the 2769 to 2928 change mixes a new network with a 5x longer
clock and cannot be attributed to either. And the anchors' ratings are CCRL
40/15 (about 22 seconds a move) while we played at 1 second; SCALE-01 showed
machete *gains* with time (0.739 / 0.792 / 0.814 at 200 / 800 / 3200 ms,
sign test p = 0.016), so the true figure on the quoted scale is if anything
higher.

### The reference field

The owner's own top engines, round robin on this machine (FIELD-01 in the
ledger), Bradley-Terry fitted with the field mean at zero:

| engine | Elo | +/- |
|---|---|---|
| Stockfish | +63 | 37 |
| Berserk 13 | +47 | 36 |
| PlentyChess 7 | +39 | 29 |
| Obsidian 16 | +32 | 36 |
| Torch | -8 | 30 |
| Caissa 1.23 | -8 | 30 |
| Lc0 (CPU) | -43 | 46 |
| Dragon | -59 | 48 |
| **Koivisto 9.0** | **-63** | 55 |

360 games, **73.3% drawn**, and the entire field spans **127 Elo**. Koivisto is
its floor, and machete scored **1-2-57** against Koivisto. Machete is not near
the bottom of the target band; it is several hundred Elo below it.

### The engine, profiled

| property | value | note |
|---|---|---|
| evaluation | NNUE 768 -> 256 -> 1, CReLU, int16, QA 255 / QB 64 | no king buckets, no output buckets |
| training target | `sigmoid(score / 150)`, blend 1.0 | saturates above about +700 |
| corpus | 42.2M positions, five teachers | plus 21.3M unused in `data/train3.bin` |
| speed, 1 thread | 769,675 nps | idle machine; **any other load moves this by up to 79%**. `machete bench` does not load a network (it searches on the hand-written evaluation) and clears a 128 MB table six times, so its nps says nothing about playing speed; its node count is a signature of the search code only |
| speed, 8 threads | 5,279,319 nps | Lazy SMP |
| effective branching factor | 1.49 - 1.68 | respectable |
| nodes to depth 12 | 766k middlegame, 485k opening, 42k endgame | **large constant: ordering and pruning** |
| depth at ~1 s | about 12 in a middlegame | top engines report 18-22 (not directly comparable, but the gap is real) |

### Known defects, measured

1. **Won endgames are not converted.** 80 of 1,884 self-play games drawn while a
   rook or more ahead. Suite at 500 ms: 8 of 12 elementary wins convert; KQ v KN,
   KQ v KR, KR v KN and KBN v K all draw by the fifty-move rule. Cause: no
   evaluation gradient inside a won position (scale-150 saturation, and no
   classical mop-up knowledge anywhere).
2. **Time management is hard-deadline only.** `budget_ms` in `src/search.mach`
   is `remaining/movestogo + 3/4*inc` (thirty when `movestogo` is absent),
   capped at a third. It does skip an iteration it expects not to finish
   (`elapsed/2` past the deadline), but has no soft limit and no stability
   scaling. `movestogo` is parsed since P0-2. Most measurements used fixed
   `movetime`, which bypasses the time manager entirely.
3. ~~`go nodes` is not supported~~ - fixed (P0-2).
4. ~~The static evaluation is computed twice at the same node~~ - fixed (S-02).
5. **Quiescence never uses the transposition table, and stands pat in check.**
6. ~~Continuation history is dead weight~~ - removed (S-01).

### Settled - do not redo

| question | answer | evidence |
|---|---|---|
| Which slice of the corpus trains best? | None beats uniform sampling | TOUR-01, 4,200 games |
| Does validation loss rank corpora? | **No - anti-correlated.** `balanced` has the best loss and is 602 Elo worst | TOUR-01 |
| Does a longer clock hurt us? | No, we gain | SCALE-01 |
| Does the game-result term help the target? | No; blend 1.0 beats 0.9 and 0.8 | HIST-08, HIST-09 |
| Does an external corpus with a different label scale help? | No, -159 | HIST-06 |
| Is continuation history worth keeping? | No, **as implemented** - used in quiet-move ordering only. Its payoff elsewhere comes through LMR and pruning (S-08), which did not exist when it was tested; it may be retried as a new candidate after S-08 | SPRT-01 |
| Does endgame-heavy or Leela data help? | No: both converted hard endings better and lost strength (-13, -20) | SPRT-NET-EG, SPRT-NET-MIX |
| Colour-swap augmentation? | Provably a no-op | ASSUMPTIONS.md |
| Mirroring as a label-preserving symmetry? | False | ASSUMPTIONS.md |

---

## 2. What "3500" means

A target nobody can measure is a mood. It is defined operationally, in three
milestones, each checkable with tools in this repo once Phase 0 is done.

| milestone | definition | roughly |
|---|---|---|
| **M0 - instrument valid** | Phase 0 complete; LADDER re-run with every opponent verified single-threaded; baseline recorded | 0 Elo, prerequisite |
| **M1 - on the floor** | >= 25% against Koivisto 9.0 under the reference conditions | about 3100-3150 |
| **M2 - in the field** | >= 50% against Koivisto 9.0 | about 3300 |
| **M3 - 3500** | **>= 50% against the reference field as a whole**, i.e. machete is the field's median | the goal |

M3 is measured with `harness/stable.py` entering machete into the field,
under the same conditions as FIELD-02, all opponents pinned to one thread, at
least 100 games per pairing, and the pentanomial interval (P0-3) reported. The
field's median engines (Torch, Caissa) sit at the field mean.

A **CCRL-scale figure** is quoted alongside, never instead: the P0-6 gauntlet,
anchors' current CCRL 40/15 **1-CPU** ratings looked up and recorded with the
date, pooled, chi2/dof reported.

**Reference condition: 3+2**, one thread, 128 MB, no engine books, the
balanced book - FIELD-02's conditions. FIELD-01's time control was never
recorded, so FIELD-02 replaces it as the field. Koivisto stays the M1/M2
opponent for continuity with every earlier result, although FIELD-02 puts
Black Marlin below it.

---

## 3. The gap, and where the Elo is

From about 2928 to 3500 is roughly **570 Elo**. The estimates below are priors
from open-source engine development, **not measurements from this engine**, and
they do not add linearly - gains interact and shrink as the engine improves.
Every one of them has to prove itself in an SPRT.

| area | prior estimate | confidence | long pole |
|---|---|---|---|
| NNUE architecture (king buckets, width, output buckets, SCReLU) | +150 to +250 | high | Mach SIMD work, retraining |
| Data at scale (42M -> 500M-1B, coupled to the architecture) | +100 to +200 | high | **machine-days of generation** |
| Search features (singular extensions, correction history, improving, capture history, SEE pruning, ...) | +100 to +200 | high | one SPRT each |
| Parameter tuning (SPSA) | +50 to +100 | medium | tens of thousands of games |
| Time management (real clocks only) | +20 to +60 | medium | invisible under movetime |
| Endgame conversion | +15 to +30 | medium | in progress |
| Speed (eval caching, staged movegen, toolchain upgrade) | +20 to +40 | medium | |

**The honest schedule.** The machine plays about 35,000 games a day at 200 ms a
move (SPRT-01 ran 1,884 in 76 minutes), which is roughly **eight SPRTs a day** if it does nothing else. Data
generation competes for the same cores: 500M positions at the measured 1,385 a
second is about **100 hours of full-machine time**. So agents can write patches
far faster than the machine can judge them, and 3500 is a campaign of weeks, not
days. Section 4's queue exists because of this.

---

## 4. How agents work together

### Territory

| territory | owns | an agent here never touches |
|---|---|---|
| **MACH** | `src/*.mach`, `check.sh`, `fixtures/` | `harness/`, training data |
| **HARNESS** | `harness/`, `data/`, `E:/machete/`, the trainer | `src/` |

A WP marked **MACH+HARNESS** (the network format changes in Phase 4) is the only
exception, and it says so in its header.

### Tiers

Each WP carries a tier, so an orchestrator can route it:

- **Tier A** - mechanical and fully specified. The cheapest model will do.
- **Tier B** - a known technique applied to this code. Needs judgement about where it goes.
- **Tier C** - design work with real risk (SIMD, network format, anything that can silently corrupt an evaluation). Use a strong model, or have a Tier-C review before merge.

### Branches, one change each

- Branch `wp/<ID>-<slug>` from `main`. **One change per branch.**
- Never bundle. HIST-05's +157 was three changes at once and nobody will ever know which of them earned it.
- Merge only with: all gates green, the SPRT verdict in `RESULTS.tsv` in the same commit, and `fixtures/bench.expected` updated if the search changed.

### The machine is shared and scarce

Two measurements at once contaminate each other - LOAD-01 exists to find out by
how much, and until it reports, assume they do.

- P0-5 has landed: **submit a job to `harness/jobqueue.py`; never start a match
  by hand.** The runner waits for a quiet machine itself.
- Anything you still run directly - a gate, a build, a quick probe - **check
  first** with `python harness/jobqueue.py status`, which lists engines, match
  drivers and Arena. The owner runs tournaments in Arena on this machine; a
  2026-09-25 agent session ran its gates beside one without looking. Stopping a
  tool's shell does not always stop the process under it: check again after.
- Data generation runs overnight; SPRTs run by day; GPU training can overlap
  either, since it barely touches the CPU.
- Never kill the owner's servers on ports **8420** and **8421**.

### The ledger

Every test, pass or fail, gets one line in `RESULTS.tsv`, committed with the
change. Before running, write your **predicted** Elo in the WP's commit or PR.
Predictions that come back wrong are the most useful lines in the file.

### Always give the owner a watch link

Every match serves a live board. When you start one, probe the port and report
the URL **after** confirming it answers, not before.

---

## 5. The rules that were learned the hard way

Each of these cost at least one wrong result. They are not style.

1. **Report what you checked, not what you did.** Printing "killed 229000" after
   piping the kill command's output to nowhere; listing three live walls when one
   was up. Verify, then say.
2. **A failed build leaves the old binary.** Check the build's exit code. Hash
   both binaries of an A/B; identical hashes mean you are measuring nothing.
   `mach run . --profile release -- bench` runs the artifact but **does not rebuild**.
3. **Every gate is perturbed once, or it is not a gate.** Two gates were green
   for days while unable to fail: a stale node count, and a literal `\n` where a
   shell line continuation belonged, which meant the gate never executed.
4. **A search change updates `fixtures/bench.expected` in the same commit.**
   The bench gate is how an accidental search change gets noticed; a stale
   fixture turns it off.
5. **Stop an SPRT only for reasons unrelated to its data.** Stopping because it
   looks good invalidates the interval. SPRT-01 walked from LLR -2.16 back to
   -1.59 before resolving; a true value inside the bounds does that.
6. **Validation loss does not rank corpora.** Every subset predicts its own
   held-out slice well. `balanced` had the best loss and was the worst engine.
7. **Speed numbers are only comparable on the same tree and the same machine
   state.** The same binary read 428,950 / 541,676 / 769,675 nps in one afternoon.
8. **Pin every opponent to one thread and a fixed hash.** Engines name it
   differently: `Threads`, `Max CPUs`, `Cores`. If none can be set, the engine
   cannot be an anchor.
9. **`go nodes` counts one thread.** It exists since P0-2 and is exact and
   repeatable on one thread; with `Threads` above 1 the helpers are not
   counted and the result is not deterministic. Builds before P0-2 read a
   node limit as no limit and search to depth 62, which looks like a hang.
10. **Movetime matches cannot see time management.** Any time-management change
    is measured on a real clock or not at all.
11. **A mate written as a huge score teaches the network nothing.** At scale
    150, `sigmoid(900/150)` is 0.9975 and everything past it is flat.
12. **An unreferenced `.mach` module is never compiled** - it can be completely
    broken and the build still passes. Reproduced on mach 5.9.0. A new module is
    not real until something `use`s it; `mach check .` type-checks what is reachable.
13. **Write files with the file tool, not shell heredocs,** whenever the content
    has backslashes. `\n` and `\\` have been mangled three times.
14. **Several files here are CRLF.** Read bytes, normalise, edit, restore.
15. **The 300-ply cap scores any unfinished game as a draw**, including won ones.
    Count capped games separately from real draws.
16. **At the target level, 73% of games are draws.** Plan test sizes for it
    (P0-3, P0-4) before the engine gets there, not after.
17. **One engine death must not lose a run.** `tournament.py` retries a block;
    check that anything new you write does too, and that failures carry the
    exception type - an empty message cost 740 games once.
18. **A default setting is not a measurement of behaviour.** `Max CPUs 2048`
    was read as "runs on 24 threads"; measured, the engine ran on one. And
    dropping the largest outlier always improves a fit, so that improvement is
    not evidence the outlier was broken. Measure the process; test the
    significance; then explain.
19. **Anything started from a Claude tool dies when the session restarts.**
    The tools' shells live in a Windows job object owned by `claude.exe`, and
    `nohup` and `&` do not leave it. A 400-game match died twenty minutes in
    that way, with nothing in its log. Launch every long job - matches, data
    generation, queues - with `harness/detach.ps1`, which starts it through WMI
    and refuses to report success if `claude.exe` is still in its ancestry.
    Agents now also run from Cursor, whose shells have a different owner;
    `detach.ps1` only looks for `claude.exe`, and whether a Cursor-launched job
    survives a session restart has not been tested.
20. **Documentation moves with the code, in the same change.** A result, a
    finished WP, a changed behaviour or a broken assumption updates
    `RESULTS.tsv`, this file, `HANDOFF.md`, `ASSUMPTIONS.md` or the README
    before the turn ends - never "later". This file went stale in three days
    once: section 1 described an engine two merges and a network behind, and
    every commit hash in the ledger pointed at a repository that no longer
    exists here. The checklist is `.cursor/rules/docs-stay-current.mdc`.

---

## 6. The work packages

Phase 0 first, but not strictly in order: **P0-2, P0-3 and P0-5 matter most**
(deterministic tests, about a third fewer games per SPRT at these draw rates,
and a queue so agents cannot corrupt each other's measurements), and P0-8
waits for P0-6's anchors so the ladder is run once. After M0, Phases 1, 3 and
5 run in parallel (different territories), Phase 4 starts when Phase 5 has
data for it, and Phases 2 and 6 come last because tuning an engine whose
structure is still changing wastes the tune.

**Exception: data generation (D-02) does not wait for M0.** It measures
nothing, so an unvalidated instrument cannot spoil it, and at about 100
machine-hours per 500M positions it is the longest pole on the road. It runs
overnight from now, on whatever teacher panel D-07 supports.

### Phase 0 - Make the instrument trustworthy

Nothing claimed before M0 counts toward 3500.

#### P0-1 Pin every opponent to one thread · HARNESS · Tier A · **partly done**
- **Status (2026-09-25):** `harness/engine.py` has `pin()` and `ladder.py`, `stable.py`, `shadow.py`, `divergence.py` and `conversion.py` call it. **`tournament.py` and `scaling.py` do not**, and the gate test below does not exist.
- **Why:** nothing in the harness sets an opponent's threads or hash, so an anchor's strength depends on its defaults. None of today's anchors turned out to be multi-threaded - Rybka was suspected and measured at one search thread - but a rating that depends on luck about defaults is not measured. Pin it and the question goes away.
- **Change:** in `harness/ladder.py`, `harness/scaling.py`, `harness/tournament.py` and anywhere an external engine is opened, after `popen_uci` set the first of `Threads`, `Max CPUs`, `Cores`, `CPUs` that exists to 1, and `Hash` to a fixed 64 MB. If no thread option exists and the engine is not known to be single-threaded, refuse to use it and say which engine. Put the logic in one function in `harness/engine.py`, not four copies.
- **Gate:** a test that opens each configured opponent and asserts the option was set; perturb by removing the pin for one engine and confirm the check fails.
- **Accept:** every ladder opponent reports one thread.

#### P0-2 `go nodes` and `go movestogo` · MACH · Tier B · **Done** (`wp/P0-2-nodes-movestogo`, GATE-P02)
- **Result:** `go nodes N` stops at exactly N nodes on the main thread and gives the same move twice after `ucinewgame`; `movestogo` replaces the fixed thirty in `budget_ms`. Bench unchanged; unit tests and `protocol.py` both fail when the node check is removed. With several threads the limit bounds only the main thread, so fixed-node tests must run on one.
- **Why:** fixed-node tests are deterministic and immune to load; CCRL 40/15 sends `movestogo` on every move and we ignore it.
- **Change:** `src/uci.mach` parses `nodes N` and `movestogo N` into `Limits`; `src/search.mach` stops at the node count (checked where `out_of_time` is), and `budget_ms` uses `remaining / max(movestogo, 2)` when `movestogo` is given.
- **Gate:** extend `harness/protocol.py`: `go nodes 10000` returns a bestmove and reports at most about 10,000 nodes; perturb by disabling the check and confirm the gate times out.
- **Accept:** gates green; no SPRT needed (behaviour under `movetime` is unchanged - verify the bench node count does not move).

#### P0-3 Pentanomial statistics · HARNESS · Tier B
- **Why:** games are played in colour-reversed pairs on the same opening, so they are correlated; the trinomial model overstates the variance and wastes games. FIELD-01's alternating `1010` rows are exactly this effect.
- **Change:** `harness/match.py` records each pair's outcome (0, 0.5, 1, 1.5, 2 points) and computes the pentanomial LLR and Elo interval. Keep the trinomial figures printed alongside for one release so they can be compared.
- **Gate:** validate against simulation the way the trinomial SPRT was validated (5% false positives at true zero, at alpha 0.05); cross-check a finished match against `fastchess`'s pentanomial output if it is available.
- **Accept:** the SPRT's false-positive rate at true zero is within 2 points of alpha over 300 simulated runs.

#### P0-4 An unbalanced opening book · HARNESS · Tier A · **half done**
- **Status (2026-09-25):** `match.py --book FILE` and `ladder.py --self-book` exist, and `harness/books/balanced_200.epd` (the balanced book FIELD-02 used) is committed; no UHO book is on disk and the decisive-rate gate has not been run.
- **Why:** four random plies make weird, often lopsided or dead positions; at 73% draws an SPRT becomes very expensive. Worse, a random opening can *finish* a game: LADDER-02's only "win" over Koivisto was `1. f3 e5 2. g4 Qh4#`, all four moves random, machete never having played - and the ladder scored it. Until the book lands, reject any random opening that ends the game. Unbalanced books (UHO) are built to make decisive games likely while keeping pairs fair.
- **Change:** obtain a UHO book (the `official-stockfish/books` repository carries them - verify the source and licence before downloading, and download to `E:/`); `match.py` and `tournament.py` take `--book FILE` and draw openings from it, still one opening per colour-reversed pair.
- **Gate:** decisive-game rate on a 400-game self-match is reported with and without the book.
- **Accept:** decisive rate rises; the SPRT median game count at a fixed true Elo falls.
- **Ratings are a different job (2026-09-23).** A UHO book is for SPRTs between machete versions, where a lopsided start that both sides play once is fine. For a rating against outside engines, the ladder now uses `--self-book FIRST,REPLIES` (`harness/self_book.py`): every game starts from ply 0 with a first move White's own engine ranks among its best, and a reply Black's own engine ranks among its best. The reason: LADDER-03 at `--startpos` played the same Rybka game 20 times (1. e4 Nc6 2. d4 d5 3. e5 h5 4. Nf3 Nh6, which Stockfish rates +1.06, splitting only at move five), so its 3167 ± 120 is not a rating.

#### P0-5 One queue for the machine · HARNESS · Tier B · **Done** (`wp/P0-5-jobqueue`, GATE-P05)
- **Result:** `harness/jobqueue.py` (not `queue.py`: that name would shadow the standard library for every script in `harness/`). `submit` requires an id, a change and a prediction; `run` refuses a second runner, plays jobs strictly in order, passes over a job whose `--requires` files do not exist yet, waits until no engine, match driver, data generator or Arena runs outside it (GPU training allowed), and appends one line per job to `RESULTS.tsv`, parsing `match.py`'s summary. A job interrupted by a dead runner is retried once. Gate `harness/test_jobqueue.py` in `check.sh`; perturbed by removing the lock (a job ran twice, a runner crashed; caught). Its first run found a crash for a queue on another drive. Not yet done: `longqueue.sh` is still a script, not jobs; `sprt_queue.sh` is marked superseded.
- **After P0-5, section 4's rule applies:** submit a job; never start a match by hand.
- **Extended for the competition (GATE-P05B):** one machine-wide queue in `E:/machete/queue`; jobs carry `--team` and run in, and report to, the worktree that submitted them; `--kind train` runs in a GPU lane beside the cpu lane; `--kind data` is charged to a per-team budget and stopped at it. Perturbed by bypassing the budget: caught.
- **Why:** agents produce patches faster than the machine can test them, and two measurements at once corrupt each other.
- **Change:** `harness/queue.py` - a job file per test in `data/queue/`, one runner that executes them strictly in order, waits for the machine to be quiet first, writes the result line to `RESULTS.tsv`, and never starts a job while another runs. `harness/longqueue.sh` becomes a list of jobs.
- **Gate:** submit two jobs at once and show they ran serially. The runner itself is started with `harness/detach.ps1` (rule 19), or it dies the next time the session restarts.

#### P0-6 A gauntlet that can measure 3000 to 3600 · HARNESS · Tier B
- **Why:** there is no opponent between Rybka (3050) and Koivisto (3300), and we score 3% against Koivisto - nothing on disk measures us in the band we are climbing through.
- **Change:** a `harness/gauntlet.py` (or a mode of `ladder.py`) with three kinds of anchor: the single-threaded old engines up to Spike and Rybka; **old Stockfish releases** (for example 5, 7, 8, 9, 10, 11), whose single-CPU CCRL 40/15 ratings are long established and span roughly 3200 to 3550 - exactly the band being climbed; and the FIELD-02 engines, optionally at fixed time odds until machete gets close. *Not* `UCI_LimitStrength`: `UCI_Elo` is calibrated for human-like play on Stockfish's own scale, tops out below the band, and its weakening is noisiest at fast time controls. Look up each anchor's current CCRL 40/15 1-CPU rating and record it with the date and URL in the script.
- **Gate:** chi2/dof across anchors reported every run; above 1.5, the run says so.
- **Sanity-check every anchor at the test time control.** In LADDER-01 at 200 ms, Koivisto 9.0 hung a mate in one twice and threw away a +3.5 position once, across 40 games - not how a 3300 engine plays. An anchor that blunders like that is not measuring anything. Screen each anchor's losses with Stockfish for single moves costing a forced mate from a level position, and drop or re-time the anchor if they appear.

#### P0-7 A deterministic endgame gate · HARNESS (+ `check.sh`) · Tier A · needs P0-2
- **Why:** `harness/endgame_suite.py` uses `movetime`, so the same position converted once and failed once in the same day. A gate that flips on load is not a gate.
- **Change:** `--nodes N` mode; `check.sh` runs it and **reports** the conversion count without failing, until E-02 lands, after which it requires 12 of 12.

#### P0-8 Re-run the rating ladder · HARNESS · machine · needs P0-1, P0-4
- **Change:** LADDER-03 at 1000 ms and again at 10+0.1, 100 games per opponent, all pinned. Record both in the ledger. This is **M0**.

#### P0-9 Harness scripts that finish should exit · HARNESS · Tier A · **done for `ladder.py`** (`--linger`, default 600); **`watch.py` still has no `--linger`**
- `ladder.py` and `watch.py` keep their wall up forever after finishing, so they never exit on their own (a finished ladder process was still alive hours later). Add `--linger SECONDS`, default 600, then shut down.

### Phase 1 - Search (MACH)

Each is one branch and one SPRT. Test at STC first; confirm at LTC anything
that touches depth or pruning, and anything claimed above +15. Bounds:
[0, 5] once P0-3 and P0-4 are in, [0, 10] before that. Stop condition for every
one of them: **H0 means revert, record the result, and move on** - do not retune
the idea until it passes, which is how noise gets merged.

| id | change | where | tier | prior | needs |
|---|---|---|---|---|---|
| S-01 | **Done.** Continuation history removed; bench 158,026, identical to the ablation | `search.mach` | A | fewer nodes | - |
| S-02 | **Done** for the node itself: evaluated once, reused by futility; bench unchanged, so the tree is identical. Storing it in the TT entry is still open | `search_node`, `tt.mach` | B | speed | - |
| S-03 | **Done, +15 +/- 15** - improving in LMR only; the RFP half lost a mate in two and was dropped | `search_node` | B | +10..20 | S-02 |
| S-04 | **Done, +33 +/- 26.** TT probe and store in quiescence; SPRT [0,10] accepted H1 over 688 games; bench 118,470 | `quiesce` | B | +10..20 | - |
| S-05 | **Done, +17 +/- 18.** Quiescence in check searches all evasions, never stands pat, detects mate | `quiesce` | B | +5..15, correctness | - |
| S-06 | Mate-distance pruning | `search_node` head | A | +2..5 | - |
| S-07 | Capture history, used in ordering captures | `score_move`, `Search` | B | +10..20 | - |
| S-08 | History-adjusted LMR (reduce less for good history, more for bad) | LMR block | B | +10..25 | S-07 |
| S-09 | Null move: extra reduction from `(eval - beta)`, and require `eval >= beta` | NMP block | B | +5..15 | S-02 |
| S-10 | **Rejected, -9 +/- 18** (H0). SEE pruning at depth <= 6, quiets below -25d^2, captures below -90d. Retry with other thresholds only as a new candidate | move loop | B | +10..20 | - |
| S-11 | Razoring at depth 1-2 | `search_node` | B | +5..10 | S-02 |
| S-12 | **Singular extensions**, then double extensions and multi-cut | `search_node` | C | +20..50 | S-02 |
| S-13 | **Correction history**: learned correction of static eval keyed by pawn structure | new table, eval call site | C | +15..35 | S-02 |
| S-14 | ProbCut | `search_node` | B | +5..15 | S-10 |
| S-15 | Staged move generation (TT move, captures, killers, quiets) | `movegen.mach`, move loop | C | speed +5..15 | - |
| S-16 | **Parked, unmeasured.** A repetition penalty (a repeated position scores +/-2000 by default) is on `wip/repetition-penalty`. Not mergeable as written: it refuses a draw by repetition even when losing, and stores a path-dependent score in the TT at full depth. If contempt is wanted, the candidate is a small draw score relative to the root side, off by default, with its own SPRT. The defect it aimed at is eval saturation (E-02), not search | `search_node` | B | uncertain, likely negative | - |

S-01 and S-02 first: one clears dead weight, the other is the prerequisite for
half the table. Record the node count to depth 12 on the four positions in
section 1 before and after each merge; it is the fastest signal that a pruning
change did what it claimed.

### Phase 2 - Time management (MACH) · measured on real clocks only

| id | change | tier | prior |
|---|---|---|---|
| T-01 | Soft and hard limits; do not start an iteration past the soft limit; honour `movestogo` | B | +15..40 |
| T-02 | Scale the soft limit by best-move stability and by how much the score dropped | B | +10..20 |
| T-03 | Scale by the fraction of nodes spent on the best move | B | +5..15 |

**Measure at 10+0.1 with the clock, never with `movetime`** - under `movetime`
the time manager does not run, so every one of these would test as exactly zero.

### Phase 3 - Endgame

| id | territory | change | tier | accept |
|---|---|---|---|---|
| E-01 | HARNESS | **Decided: no.** Both supplements converted hard endings better and lost strength overall (SPRT-NET-EG -13, SPRT-NET-MIX -20). Conversion now rests on E-02 | A | ledger lines |
| E-02 | MACH | Mop-up knowledge when the material is a known win: drive the losing king to the edge (to the right corner for KBN), bring the kings together; applied on top of the network's score | B | endgame gate 12 of 12, SPRT non-regression [-5, 0] |
| E-03 | MACH | Syzygy tablebases - **decide first**, it was deliberately out of scope | C | owner's call |

### Phase 4 - The network (MACH+HARNESS, coupled)

The largest lever, and the riskiest, because the inference in Mach and the
exporter in Python must agree bit for bit. `check.sh`'s agreement gate
(engine against the numpy reference, to the centipawn, including the
worst-case overflow gates) is the safety net: **extend it to every new
architecture before training anything for it.**

| id | change | tier | prior | needs |
|---|---|---|---|---|
| N-01 | A format version in the network file header; the loader rejects a mismatch by name | B | prerequisite | - |
| N-02 | SCReLU activation (squared clipped ReLU) in place of CReLU | C | +10..30 | N-01 |
| N-03 | Wider accumulator: 256 -> 512, then 1024; check nps cost on a quiet machine | C | +30..80 | N-01, X-01 helps |
| N-04 | Output buckets by piece count (8) | C | +15..30 | N-01 |
| N-05 | **King buckets with horizontal mirroring**, plus an accumulator cache so a king move does not force a full refresh | C | +50..100 | N-01, data |
| N-06 | A second hidden layer | C | uncertain | N-05 |

Each step: extend the numpy reference and the agreement gate, train on the same
corpus as the baseline, SPRT against it. A wider or bucketed network needs more
data to beat a smaller one - if N-03 or N-05 comes back H0 on 42M positions,
that may be the data, not the idea (see D-02).

### Phase 5 - Data (HARNESS)

| id | change | tier | note |
|---|---|---|---|
| D-01 | **Done.** SIZE-02, 2,000 games: 42M +131, 20M +83, 8M +4, 2M -201. **Not saturated** - about +100 Elo per doubling from 2M to 8M, +60 to 20M, +45 from 20M to 42M. Returns are diminishing, so data alone will not reach 3500, but the next doubling is still worth roughly +35 to +45 | - | justifies D-02 |
| D-02 | Generate at scale: 500M, then 1B positions, one consistent pipeline, overnight only | B | about 100 machine-hours per 500M |
| D-03 | Race two pipelines on equal budgets: Stockfish labels (current) against machete self-play at fixed nodes (needs P0-2) | B | self-play is how most top open engines train |
| D-04 | Trainer throughput: profile `train.py` at 290k positions a second; evaluate a faster loader or an external trainer that can export our format | B | at 1B positions, 14 epochs is 13 hours per network |
| D-05 | Fold `data/train3.bin` (21.3M, unused) into the corpus | A | cheap |
| D-06 | Compressed storage once past about 200M positions | B | 70 bytes a record is 70 GB per billion |
| D-07 | **Teacher panel from LABEL-01.** At 1,500 nodes Berserk (.689) and Alexandria (.683) track deep evaluations far worse than Stockfish (.872), PlentyChess (.871), Reckless (.861) or Obsidian (.859), yet supplied about 40% of network A's labels. Generate an equal-size corpus from the better panel and SPRT the two networks. The most direct test of "label consistency beats depth" | B | cheap relative to its prior; decides D-02's panel |

Remember HIST-06: an outside corpus with a different label scale lost 159 Elo.
Consistency of labels has mattered more than their depth. Do not mix pipelines
inside one training run without a tournament saying it helps.

### Phase 6 - Tuning

| id | territory | change | tier |
|---|---|---|---|
| U-01 | MACH | Expose every search constant (section 6, Phase 1 margins, LMR table coefficients, aspiration window) as a UCI option, defaulting to today's values; bench unchanged | A |
| U-02 | HARNESS | An SPSA runner over those options | B |
| U-03 | both | Tune after each structural phase lands, never before - a tune does not survive a structure change | - |

### Phase 7 - Speed and small debts

| id | territory | change | tier |
|---|---|---|---|
| X-01 | MACH | **Done:** mach 5.11.0, std 7.1.0, the widen written as a literal at speed parity (commit c9e8847). Was: bump the pins (mach 5.9.0, std v3.2.0 at `62bd03f`). mach#3738 and #3739 are closed upstream; if the direct widen-then-multiply is now faster, delete the masking workaround in `nnue.mach`. See briar-systems/mach#3736 | B |
| X-02 | MACH | `#[embed]` the network into the binary | A |
| X-03 | MACH | One owner for `MAX_THREADS` | A |
| X-05 | MACH | Raise `MAX_PLY` from 64 (it sizes killers, evals and the PV, and quiescence returns a static eval at ply 63); strong engines use 128 or more, and a faster engine in a long endgame will reach it. Bench must not move | A |
| X-04 | MACH | **Done** (`wp/X-04-ponder`). `go ponder` waits for `ponderhit` or `stop` and never answers alone; `bestmove ... ponder ...` from the same iteration; budget and flag set before the search thread starts, so an immediate `ponderhit` is not lost. Bench unchanged (130,660); four protocol checks, two perturbed to failure. The earlier attempt, parked on `wip/repetition-penalty`, lost an immediate `ponderhit` and read the side to move from a position the search thread was changing | B |

---

## 7. Checkpoints

After each phase, before starting the next:

1. Run the P0-6 gauntlet and the M-milestone test that applies. Record both.
2. Re-profile (section 1's table): nps on a quiet machine, nodes to depth 12, the endgame gate.
3. Re-read section 3. If a phase delivered far less than its prior, find out why before spending the next one - the priors are guesses, and an assumption that is wrong is worth more than another feature.

**From 2026-09-25 the road forks** ([COMPETITION.md](COMPETITION.md)): teams
cursor and claude each take this plan from tag `competition-fork` in their own
worktree, and statuses below describe the common start. Each team tracks its
own progress in its own copy of this file.

The current position on the road (2026-09-25): **before M0.** Done: P0-2,
P0-5, X-04, and parts of P0-1, P0-4, P0-9. Next, by territory: MACH - X-05,
then Phase 1 (S-06, S-07) on fixed-node SPRTs once P0-3 lands; HARNESS -
finish P0-1 in `tournament.py` and `scaling.py`, then P0-3, then P0-6;
machine - D-07's corpus overnight, submitted through `jobqueue.py`.
