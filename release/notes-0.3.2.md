<div align="center">

# ♞ machete 0.3.2

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.2-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.5-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![vs 0.3.1](https://img.shields.io/badge/vs%200.3.1-%2B28%20Elo-blue)
![outside](https://img.shields.io/badge/vs%20other%20engines-63.6%25%20(0.3.1%3A%2061.4%25)-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change

0.3.2 changes **one thing** from 0.3.1, so that what it gains can be pinned on something: **the network is 768 wide instead of 512**. The search, the options and the AVX2 kernels are 0.3.1's (the kernels generated for the new width). Everything else that has been built since - an opening repertoire, opening variety, a larger training set in the repertoire's openings - waits for versions of its own.

| test | games | result |
|---|---|---|
| **machete 0.3.2** vs machete 0.3.1, both as released, 10+0.1 | 659 | 176 W · 360 D · 123 L · **+28 ± 27** (SPRT accepted) |
| **768 wide** vs 512 wide, same 282M training positions, equal time, 10+0.1 | 1,704 | 366 W · 1035 D · 303 L · **+13 ± 17**, SPRT accepted |
| vs Spike 1.4, 2+1, the openings 0.3.1 played | 60 | **51 W · 8 D · 1 L** (0.3.1: 49 · 9 · 2) |
| vs Rybka 2.3.2a, 2+1, same openings | 60 | **45 W · 12 D · 3 L** (0.3.1: 43 · 11 · 6) |
| vs Koivisto 9.0, 2+1, same openings | 60 | **0 W · 17 D · 43 L** (0.3.1: 1 · 15 · 44) |

Against the three outside engines together 0.3.2 scores **63.6%** where 0.3.1 scored **61.4%**: about +15 Elo, inside the noise of 180 games, in the direction the head-to-head test measured. On the CCRL Blitz scale that is still somewhere around **3050-3150**, one CPU; `ASSESSMENT.md` explains why only a range.

**What didn't make it**, measured the same night: a 1024-wide network lost to 768 (**−17 ± 26**, the slower evaluation costing more than the network adds), and training 22 epochs instead of 14 did nothing at either width (−1 ± 15, +3 ± 15).

## ✨ The network

**C22: 8 king buckets × 768 inputs → 768 → 8 output layers**, int16, format 3, 9.5 MB. Trained on **282 million** positions: 0.3.1's 262 million plus 20 million from the engine's own games, labelled by **Stockfish 19** on two Raspberry Pis.

## 📦 What's in the box

The **`-complete.zip`** is the one to play with:

| file | what it is |
|---|---|
| `machete.exe` | the engine: one static binary, no installer, no runtime |
| `machete.nnue` | its network (768 wide, format 3; 9.5 MB) |
| `README.txt` | setup, options, strength notes |
| `SHA256SUMS.txt` | checksums for the two files above |

The other archives are what CI builds for every platform - `machete` and `binpack` for Windows (x86-64), Linux (x86-64 and aarch64) and macOS (x86-64 and Apple silicon) - executables only; the engine needs **`machete.nnue`** (attached separately) beside it. **A 0.3.1 network will not load in 0.3.2**: the width differs, and the engine refuses a file of another width.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, each made to fail on purpose once. The release build's source is the measured 768-wide build's with only the version line changed; the two give the same node-count signature (154,591) and the same network evaluation on every position checked.

</details>

<details>
<summary><b>🔐 Checksums (SHA-256)</b></summary>

```
21be097de50f59ea37b7ed393f74197a5254babb3bee36d128322171b45b7881  machete.exe
fb55d8b36e09676edebf35267100d4200b8717a71ce7ba8a8572f4162f039196  machete.nnue
```

</details>

---

<div align="center">

Built with **Mach 6.5.0** and **mach-std 9.2.0** · training positions labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
