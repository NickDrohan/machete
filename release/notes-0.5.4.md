<div align="center">

# ♞ machete 0.5.4

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.4-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**It uses its clock.** The lichess bot's games ended with 24-52% of the clock unused. With an increment, the engine now aims for twice what it did per move. In sudden death the aim is unchanged: there twice a twentieth is a tenth, which runs out in long games once lichess's lag is counted.

**Three search changes,** each a small plus alone on the clock and kept together:

| change | alone (10+0.1, 1,000 games) |
|---|---|
| a table score whose bound lies past the evaluation replaces it | +10 ± 22 |
| one more ply of late move reduction at an expected cut node | +9 ± 22 |
| ProbCut: a capture that beats beta by 200 at depth − 4 cuts | +6 ± 22 |

**Together with the time change: +25 ± 15 Elo** against 0.5.3's search, same network, 30+0.3, 2,000 games (274 wins, 1,593 draws, 133 losses, no losses on time). At bullet (1+0, 600 games) −9 ± 28, no losses on time. Gains against machete itself have run three to four times what shows against other engines.

**A new kind of network: SCReLU.** Each hidden value is clipped and squared before the output layer, as most strong NNUE engines do (file format 5). Its output is computed in one pass with the square fused into the multiply-add, so it costs 4.5% of the speed of 0.5.3's network. The shipped network, C33F280P3ALLSQ, is 0.5.1's data and recipe trained with SCReLU: held-out loss 0.01463.

| network test | games | Elo |
|---|---|---|
| SCReLU 768 against 0.5.3's network, both on 0.5.4's search, 10+0.1 | 2,000 | **+9 ± 15** |
| SCReLU against clipped relu, same 200M sample, equal nodes | 1,000 | +6 ± 22 |
| the same pair, 10+0.1 | 1,000 | +6 ± 22 |

Every measure of the network is positive, and none alone is significant.

**A stop that arrives as a search starts now holds.** A `go ponder` followed at once by `stop` used to search on until the GUI gave up; on the bot 25 of 25 such stops were lost before the fix, none after, and every search thread is joined before the engine answers.

## 🧪 What was tried and left out

| change | result | |
|---|---|---|
| a second hidden layer of 16 after SCReLU | +25 ± 22 at equal nodes, **−52 ± 22** on the clock | out: half the speed, even with a kernel four units a pass |
| more root preference for checks and captures (ForceBonus 25) | −40 ± 18 | out |
| contempt 60 against 20, versus a much weaker engine | +220 against +207 | not adopted yet |

The second layer stays on its branch until it is fast enough.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (C33F280P3ALLSQ), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. 0.5.3's network still loads.

`harness/nnue/train.py --activation screlu` writes format 5 directly. `harness/experience_build.py` now skips games lost on time in their first 20 plies and takes moves the engine panel's games flag, unless the bot's own games say otherwise; `harness/book_build.py` builds the bot's opening book.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes. The node-count signature is 121,806 (was 209,573). The mate-in-two gate runs at depth 5: the table's score as evaluation takes one of its eight positions a ply later than before. At a fixed depth the release searches node for node as the measured candidate did, on AVX2 and SSE2. The SCReLU output matches the numpy reference exactly on 183 positions, and a test holds the AVX2 kernel to the portable sum, which is done in 64 bits since its weights would overflow 16-bit products.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network C33F280P3ALLSQ · no engine's code is used

</div>
