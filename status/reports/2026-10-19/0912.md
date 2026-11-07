# machete status, 2026-10-19 09:12

## What I did

Status at 09:15 on 19 October.

- The PC restarted at 19:57 on the 18th (started from the owner's Windows account, "Other (Unplanned)"). The log-on task brought everything back by 19:59, but two things broke. A match record was left empty, and lane A's runner crashed on it every two minutes for 13 hours. The rook-data training was killed and marked failed, so the GPU was idle for 13 hours. Both fixed. Seven jobs killed in the restart chain are requeued; the first Stockfish-v-Obsidian chunk kept 0.19M finished positions.
- The job queue now puts a job that Windows kills during a shutdown back in pending and stops the runner, instead of failing it and starting the next one. Tested both ways on a scratch queue.
- Cursor ports, each alone on 0.4.1, 1,500 games at 10+0.1, no early stop: razoring +9 ± 18, wider mop-up +3 ± 18, drawish scaling -10 ± 18, capture history -14 ± 18. None is distinguishable from zero. Next: the extensions test again, then the endgame tests for mop-up and drawish scaling.
- Stockfish v Obsidian from imbalanced starts runs at about 5 positions a second (80 ms a move each plus takebacks), so a 2M chunk takes days. The other pairings run at about 19 a second.

## Processes

- lichess bot: running
- orchestrator: running
- GPU queue runner: running
- lane A runner: running
- lane B runner: running
- farm watchdog: running
- live page relay: running
- deep-mate search: running
- GPU: 3 %, 702 MiB, 8188 MiB, 43 (utilisation, memory used, memory total, temperature)

## Queues

**gpu**: 1 running, 1 pending
- running `TRAIN-C33F280P3R` since 2026-10-19 09:08:43: no epoch finished yet; last line: 666,446,919 positions (18.66 GB packed), training on cuda
- pending `TRAIN-C33F140VS` (waits for eq_sf_alexandria_sf.ok, eq_sf_reckless_sf.ok, eq_sf_plenty_sf.ok, eq_alexandria_reckless_sf.ok, eq_alexandria_plenty_sf.ok, eq_reckless_plenty_sf.ok)

**lane A**: 1 running, 7 pending
- running `PORTEG-mopup` since 2026-10-19 09:09:53
- pending `PORT-extend`
- pending `PORTROOK-mopup`
- pending `PORTEG-drawish`
- pending `PORTROOK-drawish`
- pending `CONFIRM-C33F280P3N60-C33F280P3`
- pending `CONFIRM-C33F280P3R-C33F280P3` (waits for c33f280p3r.nnue)
- pending `CONFIRM-C33F140VS-C33F140` (waits for c33f140vs.nnue)

**lane B**: 1 running, 25 pending
- running `GEN-EQ-OBSIDIAN-RECKLESS` since 2026-10-18 19:59:27
- pending `GEN-IMB-SF-OBSIDIAN-1`
- pending `GEN-IMB-SF-OBSIDIAN-2`
- pending `RELABEL-IMB_SF_OBSIDIAN_1` (waits for imb_sf_obsidian_1.ok)
- pending `RELABEL-IMB_SF_OBSIDIAN_2` (waits for imb_sf_obsidian_2.ok)
- pending `GEN-EQ-ALEXANDRIA-RECKLESS`
- pending `GEN-EQ-RECKLESS-PLENTY`
- pending `RELABEL-EQ_ALEXANDRIA_RECKLESS` (waits for eq_alexandria_reckless.ok)
- pending `RELABEL-EQ_RECKLESS_PLENTY` (waits for eq_reckless_plenty.ok)
- and 17 more pending

## Results in the last 26 hours

| job | finished | W-D-L | Elo | verdict |
|---|---|---|---|---|
| `PORT-razor` | 10-18 19:06 | 243-1052-205 | +9 ± 18 |  |
| `PORT-caphist` | 10-18 17:42 | 186-1069-245 | -14 ± 18 |  |
| `TRAIN-C33F280P3N60` | 10-18 17:42 |  |  |  |
| `PORT-drawish` | 10-18 16:17 | 191-1076-233 | -10 ± 18 |  |
| `PORT-mopup` | 10-18 14:54 | 241-1029-230 | +3 ± 18 |  |
| `GEN-ROOK8` | 10-18 13:28 |  |  | **failed**: exit 4294967295 |
| `CONFIRM-C33F140D15K100-C33F140` | 10-18 08:37 | 293-979-228 | +15 ± 18 |  |

## Search tune (SPSA)

step 15457 of 15000; plus side +6355 =18285 -6250

| constant | default | now |
|---|---|---|
| AspWindow | 25 | 18.6 |
| FutBase | 120 | 115.3 |
| FutMul | 110 | 99.1 |
| IirDepth | 6 | 5.2 |
| LmpBase | 6 | 7.2 |
| LmrBase | 75 | 85.7 |
| LmrDiv | 225 | 213.2 |
| LmrHistDiv | 4096 | 3848.5 |
| NmpBase | 3 | 2.2 |
| NmpDiv | 3 | 2.8 |
| NmpEvalDiv | 200 | 180.6 |
| QsDelta | 200 | 203.4 |
| RfpMargin | 85 | 57.4 |
| SeDepth | 8 | 6.0 |
| SeMargin | 2 | 2.4 |

## Lichess bot

- ratings: bullet 2748 (421 games), blitz 2767 (1345 games), rapid 2838 (61 games)
- last 24 hours: 89 games: 21 W 37 D 31 L; not won against lower-rated: 12; last game started 1.7 h ago
- 10-16 02:02  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-16 03:03  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-17 08:49  ALARM: the lichess bot has played no game for 570 minutes and has no daily limit: restarting it
- 10-18 08:22  ALARM: the lichess bot has played no game for 63 minutes and has no daily limit: restarting it
- 10-19 06:54  ALARM: the lichess bot has played no game for 62 minutes and has no daily limit: restarting it

## Farm and orchestrator (last lines of its log)

```
10-19 08:47  the CPU queue runner is not running: restarting it
10-19 08:49  the CPU queue runner is not running: restarting it
10-19 08:51  the CPU queue runner is not running: restarting it
10-19 08:53  the CPU queue runner is not running: restarting it
10-19 08:55  the CPU queue runner is not running: restarting it
10-19 08:57  the CPU queue runner is not running: restarting it
10-19 08:59  the CPU queue runner is not running: restarting it
10-19 09:01  the CPU queue runner is not running: restarting it
10-19 09:03  the CPU queue runner is not running: restarting it
10-19 09:05  the CPU queue runner is not running: restarting it
10-19 09:07  the CPU queue runner is not running: restarting it
10-19 09:09  the CPU queue runner is not running: restarting it
```

## Disks

- C 24 GB free of 299
- D 166 GB free of 3001
- E 6823 GB free of 8001

