# machete - notes for agents

A UCI chess engine written in Mach, plus a Python harness that measures it.
Start with [HANDOFF.md](HANDOFF.md) (boundary, house rules, how to build), then
[ROADMAP_3500.md](ROADMAP_3500.md) sections 1-5 before picking up a work package.
[RESULTS.tsv](RESULTS.tsv) is the ledger; [ASSUMPTIONS.md](ASSUMPTIONS.md) the evidence.

## Measurements go through the job queue

Two measurements at once contaminate each other, and the owner runs Arena
tournaments on this machine. So:

- **Never start a match, SPRT, ladder, tournament or data generation by hand.**
  Submit it:

  ```bash
  py -3.7 harness/jobqueue.py submit --id SPRT-S06 --change "S-06: mate distance pruning" \
      --predicted +3 --test wp/S-06 --against "dev (b454e97)" --tc "movetime 200" \
      --requires E:/machete/ab/s06.exe -- \
      py -3.7 -u harness/match.py E:/machete/ab/s06.exe E:/machete/ab/dev.exe --sprt 0 10 ...
  ```

  `--predicted` is required: write the Elo you expect before it runs.
  `--requires` holds the job until that file exists - point it at finished
  copies, never at a network still training.
- **One runner plays the queue:** `py -3.7 harness/jobqueue.py run`, launched with
  `powershell -File harness/detach.ps1 "py -3.7 -u harness/jobqueue.py run"` so it
  outlives the session. A second runner refuses to start. It runs jobs one at a
  time in submission order, waits until no engine, match driver, data generator
  or Arena is running outside it (GPU training is allowed), and appends one line
  per job to `RESULTS.tsv`. Output: `data/queue/logs/`.
- **Before anything you do run directly** - `check.sh`, a build, a quick probe -
  run `py -3.7 harness/jobqueue.py status`. If it says busy, the owner's work
  wins: wait, or run only what is cheap and single-threaded, and say so.
- Afterwards, check that nothing of yours is still running. Killing a shell does
  not always kill the process under it. Never kill the owner's processes, nor
  the servers on ports 8420 and 8421.

`harness/sprt_queue.sh` is superseded; `harness/longqueue.sh` is not yet
converted to jobs.

## Documentation moves with the code

A result, a finished or abandoned work package, a changed behaviour or a
broken assumption updates the docs **in the same commit, before the turn ends**
(ROADMAP rule 20). The checklist, which Cursor loads automatically, is
[.cursor/rules/docs-stay-current.mdc](.cursor/rules/docs-stay-current.mdc):
ledger line for every test, WP status in the roadmap, `bench.expected` if the
node count moved, gate counts in HANDOFF, assumption status in ASSUMPTIONS.
Commit hashes quoted in docs must resolve in this repository.

## Practicalities on this machine

- Compiler: `mach` is not on PATH; `$MACH` is
  `D:/Dev/Claude/mach-portfolio/tools/mach-5.11.0/mach.exe`. `mach run` does not
  rebuild; check the build's exit code.
- `bash` in PowerShell is a broken WSL; use `C:\Program Files\Git\bin\bash.exe`
  for `check.sh`, with `PYTHON` and `MACH` set.
- Harness Python is 3.7 (`py -3.7`, has python-chess and psutil); the trainer is 3.13.
- PowerShell 5 has no `&&`; chain with `;`.
- Write files with the file tool, not heredocs (backslashes get mangled).
