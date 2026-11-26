# machete status, 2026-10-14 19:50

## What I did

Run by hand at 19:50. The scheduled runs at 14:17, 16:17 and 18:17 did not happen, so nobody checked for six hours. Lane A had been idle since 16:54 and lane B since 17:14. Both are refilled.

Results since the last report:
- The 0.3.0 search tune against Koivisto: 44-304-852, -284 ± 27 over 1,200 games at 10+0.1. 0.4.0's defaults scored -302 ± 28 in an earlier run, so that is about +18 outside, matching the +17 to +21 head to head. That run shared the machine differently, so the defaults are being rerun now under the same load (KOI-C33F140-FAST2).
- 280M Fischer Random supplement (C33F280) against 0.4.0's network: 70-196-85, -15 ± 37. The early stop rejected it. Like the 200M version (-18 ± 41), more Fischer Random data does not help beyond 140M.
- The search tune is at step 12,572 of 15,000. Chunks R7-R9 are queued.
- The endgame miner died without saving anything (cause unknown). It now saves each game as it finishes and has been restarted.
- GPU: TRAIN-C33F140K16F is training.

## Processes

- lichess bot: running
- orchestrator: running
- GPU queue runner: running
- lane A runner: running
- lane B runner: running
- farm watchdog: running
- live page relay: running
- deep-mate search: running
- GPU: 93 %, 6235 MiB, 8188 MiB, 60 (utilisation, memory used, memory total, temperature)

## Queues

**gpu**: 1 running, 1 pending
- running `TRAIN-C33F140K16F` since 2026-10-14 16:24:39: epoch 5 done: training loss 0.01616, validation 0.01656; last line: epoch 6  468,582,400 positions  loss 0.01591  305,510/s
- pending `TRAIN-D15000X60`

**lane A**: 0 running, 4 pending
- pending `ZONES-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `TIMED-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `LADDER-D15000X60-D500X60` (waits for d15000x60.nnue)
- pending `KOI-C33F140-FAST2`

**lane B**: 0 running, 3 pending
- pending `SPSA040-R7`
- pending `SPSA040-R8`
- pending `SPSA040-R9`

## Results in the last 26 hours

| job | finished | W-D-L | Elo | verdict |
|---|---|---|---|---|
| `SPSA040-R6` | 10-14 17:14 |  |  |  |
| `LADDER-C33F280-C33` | 10-14 16:54 | 57-102-42 | +26 ± 48 | accepted H1: the change is worth at least 15 Elo |
| `LADDER-C33F280-C33F140` | 10-14 16:43 | 70-196-85 | -15 ± 37 | accepted H0: the change is worth at most -15 Elo |
| `TRAIN-C33F280` | 10-14 16:24 |  |  |  |
| `SPSA040-R5` | 10-14 16:14 |  |  |  |
| `KOI-SPSA030-FAST` | 10-14 15:24 | 44-304-852 | -284 ± 27 |  |
| `SPSA040-R4` | 10-14 15:13 |  |  |  |
| `SPSA040-R3` | 10-14 14:12 |  |  |  |
| `SPSA040-R2` | 10-14 13:11 |  |  |  |
| `LONG-SPSA030-ON-040` | 10-14 13:07 | 49-326-25 | +21 ± 34 |  |
| `SPSA040-R1` | 10-14 12:11 |  |  |  |
| `SPSA-040-6` | 10-14 11:10 |  |  |  |
| `CONFIRM-SPSA030-ON-040` | 10-14 11:04 | 198-652-150 | +17 ± 22 |  |
| `SPSA-040-5` | 10-14 10:09 |  |  | **failed**: exit 4294967295 |
| `SPSA-040-4` | 10-14 10:09 |  |  |  |
| `SPSA-040-3` | 10-14 10:09 |  |  |  |
| `SPSA-040-2` | 10-14 10:08 |  |  |  |
| `SPSA-040-1` | 10-14 10:08 |  |  |  |
| `LADDER-C33F200-C33` | 10-14 09:57 | 45-74-28 | +40 ± 57 | accepted H1: the change is worth at least 15 Elo |
| `LADDER-C33F200-C33F140` | 10-14 09:52 | 57-147-71 | -18 ± 41 | accepted H0: the change is worth at most -15 Elo |
| `TRAIN-C33F200` | 10-14 09:42 |  |  |  |
| `SPRT-SPSA030-ON-040` | 10-14 03:10 | 88-247-46 | +38 ± 35 | accepted H1: the change is worth at least 10 Elo |
| `KOI-C33F140-FAST` | 10-14 02:48 | 34-290-876 | -302 ± 28 |  |
| `KOI-C33F140P3-FAST` | 10-14 02:47 | 33-315-852 | -290 ± 27 |  |
| `LONG2-C33F140P3-C33F140` | 10-13 21:29 | 125-570-105 | +9 ± 24 |  |
| `SPRT-C33F140P3-C33F140` | 10-13 18:55 | 446-1123-376 | +13 ± 15 | accepted H1: the change is worth at least 10 Elo |

## Search tune (SPSA)

step 12572 of 15000; plus side +5113 =14955 -5052

| constant | default | now |
|---|---|---|
| AspWindow | 25 | 18.5 |
| FutBase | 120 | 115.4 |
| FutMul | 110 | 101.2 |
| IirDepth | 6 | 5.6 |
| LmpBase | 6 | 7.0 |
| LmrBase | 75 | 86.0 |
| LmrDiv | 225 | 214.9 |
| LmrHistDiv | 4096 | 3932.1 |
| NmpBase | 3 | 2.3 |
| NmpDiv | 3 | 2.9 |
| NmpEvalDiv | 200 | 184.1 |
| QsDelta | 200 | 202.8 |
| RfpMargin | 85 | 60.4 |
| SeDepth | 8 | 6.2 |
| SeMargin | 2 | 2.4 |

## Lichess bot

- ratings: bullet 2748 (317 games), blitz 2799 (1095 games), rapid 2802 (35 games)
- last 24 hours: 106 games: 13 W 56 D 37 L; not won against lower-rated: 14; last game started 29 min ago
- 10-12 23:37  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 00:41  ALARM: the lichess bot has played no game for 63 minutes and has no daily limit: restarting it
- 10-13 01:42  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 02:44  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-14 03:05  ALARM: the lichess bot has played no game for 64 minutes and has no daily limit: restarting it

## Farm and orchestrator (last lines of its log)

```
10-14 05:20  mac starts n15000_mac_09 (4000000 positions at 15,000 nodes, seed 88109)
10-14 05:22  the 15,000-node set has reached 60M: training D15000X60 and matching it against D500X60
10-14 05:22  queueing TRAIN-D15000X60
10-14 05:22  queueing LADDER-D15000X60-D500X60
10-14 06:36  pi-02 finished n15000_pi02_08 (1000187 positions): pulled; the 15,000-node set is at 62.7M
10-14 06:36  pi-02 starts n15000_pi02_09 (1000000 positions at 15,000 nodes, seed 88309)
10-14 09:09  pi-01 finished n15000_pi01_06 (1000359 positions): pulled; the 15,000-node set is at 63.7M
10-14 09:09  pi-01 starts n15000_pi01_07 (1000000 positions at 15,000 nodes, seed 88207)
10-14 16:26  mac finished n15000_mac_09 (4000242 positions): pulled; the 15,000-node set is at 67.7M
10-14 16:26  mac starts n15000_mac_10 (4000000 positions at 15,000 nodes, seed 88110)
10-14 17:55  pi-02 finished n15000_pi02_09 (1000175 positions): pulled; the 15,000-node set is at 68.7M
10-14 17:55  pi-02 starts n15000_pi02_10 (1000000 positions at 15,000 nodes, seed 88310)
```

## Disks

- C 19 GB free of 299
- D 296 GB free of 3001
- E 6832 GB free of 8001

