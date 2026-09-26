# Round 2: Claude against Cursor, from machete 0.2

Designed 2026-09-26 at the owner's request by team claude, winner of round 1,
and set by the owner. Round 1's rules (COMPETITION.md) hold except where this
file changes them. Only the owner changes this file.

**Goal:** by noon on 2026-09-27, a new release (v0.3.0) with a large Elo gain
over 0.2, and a synthesis patch (v0.3.1) that combines both teams' proven work.

## The start

Both teams fork from tag **`round2-fork`**: machete 0.2.0 (network C2) on mach
6.0.0 and mach-std 9.0.0 (`E:/machete/tools/mach-6.0.0/mach.exe`), with this
file. Round 1's branches are yours to reuse, but a change counts only once it
is measured again from `round2-fork`.

| team | worktree | branches | deliverable folder | queue | CPUs | watch ports |
|---|---|---|---|---|---|---|
| **claude** | `D:/Dev/Claude/machete-claude` | `claude2/*` | `E:/machete/competition/round2/claude/` | `E:/machete/queue-claude` | 0-11 (die 0) | 8800-8819 |
| **cursor** | `D:/Dev/Claude/machete-cursor` | `cursor2/*` | `E:/machete/competition/round2/cursor/` | `E:/machete/queue-cursor` | 12-23 (die 1) | 8820-8839 |

Nothing is shared after the fork: do not read the other team's branches,
worktree, folders, queue or logs. Everything on disk at the fork is fair game,
read-only (the owner's ruling of round 1).

## The machine is split, not shared

Round 1's single first-come queue let one team's backlog and one long job
starve every other measurement for eight hours. So:

- **CPU.** Each team has its own queue and runner, pinned to its half of the
  processor. Engines inherit the runner's CPUs, so neither team can slow or
  block the other. Submit with `--queue E:/machete/queue-<team> --team <team>`.
  A team's runner runs one CPU job at a time, as before.
- **GPU.** One shared queue, `E:/machete/queue-gpu`, first come first served.
  At most **one training per team** may be pending or running there at once,
  and each training is submitted with `--timeout-hours 1`.
- **Outside the queue:** builds, unit tests, `check.sh`, `bench`,
  `harness/speed_ab.py` and `harness/profile.py`, on your own CPUs only
  (`start /affinity` or psutil), never on the other team's.
- **The owner's Arena** stays closed overnight, or is pinned to CPUs the owner
  chooses.

## Rules learned in round 1

1. **Every measurement is bounded.** A match or SPRT has a game cap and
   `--timeout-hours` of at most 1.5. An SPRT that has not decided by its cap
   is recorded as "no effect found", not left running.
2. **At most three jobs pending per team** in its queue, and one in the GPU
   queue. Queue what can finish; a backlog tells you nothing.
3. **A speed claim needs a speed measurement.** A change that is meant to
   leave the search unchanged must show the same node counts and moves with
   the network loaded, and a CPU-time gain in `harness/speed_ab.py`. `bench`
   (which searches without the network) and `agree.py` (which evaluates from
   scratch) prove neither speed nor strength. Round 1's losing entry passed
   both and was 13 times slower than the engine it started from.
4. **A strength claim needs games.** Every search, evaluation or network
   change is judged by SPRT or a fixed match against its own base, at 10+0.1
   or longer, with one thread per engine.
5. **Anchor before you deliver.** Before each READY, the entry plays at least
   200 games against v0.2.0 at 10+0.1 in your own queue, recorded in your
   ledger as `ANCHOR-<team>-<n>`. An entry below v0.2.0 is not delivered.
6. **Synthesis-ready.** Keep `SYNTHESIS.md` in your worktree: for every change
   in your entry, its commit, what it does, and the ledger line that measured
   it on its own. Only changes measured on their own go into the v0.3.1 patch.
7. **Visibility.** Every match job passes `--watch` with a port in your range,
   and the owner can follow each queue in its queue view.
8. **Watch, don't estimate.** Check your jobs; a job whose log and engines
   stop moving is stopped and recorded, not waited on.

## Delivering

As in round 1: `machete.exe`, `machete.nnue` and `READY` (the commit) in your
round 2 deliverable folder, named `machete <team>` in `id name`, one thread
when given `Threads 1`, at most 128 MB of tables, no book or tablebases of its
own, the network loaded from beside the executable. **The folders freeze at
08:30 on 2026-09-27.** Deliver early and often.

## The final (09:00 to about 10:30)

`E:/machete/competition/round2/run_final.sh`, `harness/referee.py` from the
neutral worktree, one thread and 128 MB each, the balanced book, real clocks,
no adjudication:

| phase | pairings | games each | at once |
|---|---|---|---|
| 10+0.1 | claude-cursor, claude-v0.2.0, cursor-v0.2.0 | 200 | 8 per pairing |
| 60+0.6 | the same three | 100 | 8 per pairing |
| anchor | each entry against Koivisto 9.0 (CCRL ~3300), and v0.2.0 likewise | 40 | 8 per match |

The winner scores more over both head-to-head phases pooled. The v0.2.0 and
Koivisto results measure each entry's gain, in the head-to-head sense and on
an external scale.

## After the final

- **v0.3.0** is the winning entry, released through the template flow.
- **v0.3.1** takes the runner-up's changes that `SYNTHESIS.md` shows were each
  proven on their own, merges them into v0.3.0, and must beat v0.3.0 in one
  bounded confirmation match before it ships.
