<div align="center">

# ♞ machete 0.5.5

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.5-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**A wider network, trained on the middlegame.** The hidden layer is 1,024 wide (was 768), still SCReLU (file format 5). The shipped network, candidate C, is 0.5.4's recipe plus every distinct middlegame position generated this week (15.1M) and every distinct position played out from the bot's own lost games (8.1M), all labelled deeply by Stockfish: 15,000 nodes where a side is clearly winning, up to 200,000 where the position is close. 949M positions, 14 epochs.

| network test, same search, 10+0.1 | games | Elo |
|---|---|---|
| candidate C against 0.5.4's network | 1,355 | **+13** (285 wins, 837 draws, 233 losses) |
| candidate B (C with less of the new data) against 0.5.4's network | 2,000 | +13 ± 15 |
| candidate A (middlegame data only) against 0.5.4's network | 2,000 | +14 ± 15 |
| 1,024 wide, 0.5.4's data only, against 0.5.4's network | 2,000 | +10 ± 15 |

No one match is significant; four 1,024-wide networks all ahead of 0.5.4's network are. On the bot's own middlegame positions (9,804 positions, Stockfish 1M nodes) the evaluation's error falls from 0.1152 to 0.0966, and on its opening positions from 0.0518 to 0.0491. C's match was stopped at 1,355 games so it could ship.

**A forced move on a clock is no longer searched deep.** With one legal move the engine searches only far enough to have a reply to ponder on, and keeps the time.

## 🧪 What was tried and left out

| change | result | |
|---|---|---|
| 20 small edits to C's output layer, tuned by 24,000 games (SPSA) | +4 ± 15 against C | out: not shown |
| the output layer re-solved on the bot's own positions | −7 ± 10 | out: lower error against Stockfish is not strength |
| steering edits: bishop pair ±30 cp, king attack ±20 cp | −23 to −31 ± 22 | out: they change the play, and cost what any edit of that size costs |

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (candidate C), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. **0.5.4's network does not load in 0.5.5** (it is 768 wide), and 0.5.5's does not load in 0.5.4.

`harness/nnue/train.py --init` now starts from a format 5 network (fine-tuning).

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes. The node-count signature is unchanged at 121,806 (the bench runs without a network). At a fixed node count the release searches node for node as the measured build did. The network's output matches the numpy reference exactly on 333 positions. Candidate C has played on the lichess bot since 2026-11-12 01:35.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network candidate C (c1024-candC-screlu) · no engine's code is used

</div>
