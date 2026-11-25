<div align="center">

# ♞ machete 0.6.0

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.6.0-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%207.0-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**Mach 7.0.** machete is built with Mach 7.0.0 and mach-std 10.1.1. The search is unchanged move for move: the same node count on the bench and on 80 fixed-depth middlegame searches. It is **5.3% faster** in total time over those searches, alternating builds, and the executable shrank from 321 KB to 187 KB.

| test, same network | games | result |
|---|---|---|
| 80 searches to depth 14, one thread, against the 0.5.6 build | — | identical nodes, 5.3% less time |
| 10+0.1 against 0.5.6 as released, same network (candidate C) | 2,000 | +1 ± 15 (256 wins, 1,495 draws, 249 losses) |

The port needed four small source changes on top of `mach migrate`. Predicates return `bool`, now a one-bit type. The network's SSE2 and AVX2 kernels are generated as instructions instead of instruction bytes: Mach 7 spells AVX2, `pmaddwd`, `pmaxsw` and `xgetbv`, and it refuses the old byte blocks. The engine process uses std 10's environment type. The Leela-data decoder reads JSON through the new mach-json package. The findings went upstream as briar-systems/mach#4985.

**The network is candidate E.** It is 0.5.6's recipe trained again with every position labelled up to 18 November, including deeply searched middlegames and games played on from positions the bot lost, for 14 epochs.

| test, same search | games / positions | result |
|---|---|---|
| 10+0.1 against 0.5.6's network | 2,000 games | −1 ± 15 (289 wins, 1,417 draws, 294 losses) |
| held-out missed moves: does the search find the move the bot missed in its own losses? | 691 positions | 403 found, against 387 for 0.5.6's network |
| the same, the bot's single turning move per lost game | 96 positions | 50 found, against 45 |

E is level with 0.5.6's network on the clock and finds more of the moves the bot got wrong, though neither difference is significant on its own.

## 🧪 What was tried and left out

| change | result | |
|---|---|---|
| enhanced transposition cutoffs (look up each child before searching) | −5 ± 15 at 10+0.1, 2,000 games; 2.5–4% fewer nodes | out |
| a larger transposition table (128 MB → 2 GB) at the bot's 1 s a move, 8 threads | depth 15.96 → 16.02 | default unchanged |
| target scale 250 instead of 150 (candidate G) | −7 ± 15 against F over 2,000 games | out |
| 2.5 M positions from strong bot-vs-bot games added to E's data (candidate F) | +5 ± 15 against E; fewer missed moves found | out |
| fine-tunes from E with 25% or 50% bot-vs-bot positions, or 23% "time-travel" positions | +12 to +15 missed moves against a matched control, but none beat E | out |

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (candidate E), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Tablebase files are not included: the 3-4-5 man set is about 1 GB from any Syzygy mirror.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes on Mach 7.0. That covers:

- perft, and divide against python-chess on 330 random positions;
- the mate suites;
- network output exactly matching a numpy reference;
- the SSE2 and AVX2 kernels searching the same tree;
- training-feature parity, SMP scaling and UCI;
- self-play;
- the Leela decoder byte for byte against its Python reference;
- cross-compilation to every target.

The node-count signature is unchanged at 131,948. There are 69 unit tests.

</details>

---

<div align="center">

Built with **Mach 7.0.0**, **mach-std 10.1.1** and **mach-json 0.1.0** · network candidate E · tablebase probing after Fathom (MIT); no engine's code is linked

</div>
