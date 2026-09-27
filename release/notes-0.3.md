<div align="center">

# ♞ machete 0.3

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.0-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![vs 0.2](https://img.shields.io/badge/vs%200.2-%2B54%20to%20%2B60%20Elo-blue)
![koivisto](https://img.shields.io/badge/vs%20Koivisto%209.0-0--8--32%20(0.2%3A%200--7--33)-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![search](https://img.shields.io/badge/search-unchanged%20from%200.2-lightgrey)

</div>

---

## 🏆 What 0.3 is

The winner of round 2 of the two-agent contest: Claude Code and Cursor each took machete 0.2, on its own half of one machine and its own job queue, and made it as strong as they could in a day. A neutral referee then played every entry against every other, with **v0.2.0 itself as the control**, on real clocks, no books, one thread and 128 MB each. Team cursor's entry won and is 0.3.

| pairing | 10+0.1 · 200 games | 60+0.6 · 100 games |
|---|---|---|
| **machete 0.3** vs machete 0.2 | 66 W · 99 D · 35 L · **+54 ± 34** | 27 W · 63 D · 10 L · **+60 ± 41** |
| **machete 0.3** vs team claude's entry | 69 W · 86 D · 45 L · +42 ± 37 | 23 W · 61 D · 16 L · +24 ± 43 |
| **machete 0.3** vs Koivisto 9.0 (CCRL ~3300) | — | 0 W · 8 D · 32 L · about 380 below (0.2: 0 W · 7 D · 33 L) |

**On an external scale,** 0.3 rates about **3000-3100 on the CCRL Blitz scale** (one CPU), from 140 games against seven listed engines with their published ratings held fixed (`ASSESSMENT.md`). The anchors disagree among themselves by several hundred Elo on this hardware, so it is a range; on it 0.3 and 0.2 are indistinguishable at both 2+1 and 10+0.1 (1,100 games in all). The head-to-head gain in the table above is real against 0.2 and does not appear against other engines: what 0.3 delivers is the king-bucket network format, on which the next networks build.

Team claude's official entry played as 0.2 does (its measured changes came out level or worse, so none shipped; 30 W · 140 D · 30 L against 0.2 at 10+0.1). The full table, both teams' `SYNTHESIS.md` and the referee's log are in `competition/round2/`.

How the entry came to be, since the numbers alone would mislead: the king-bucket evaluation and its network were written and trained by team claude in **round 1** (`N-05`, then set aside as "level with 0.2" after 446 games with an earlier network). Round 2's rules made everything on disk fair game; team cursor rebuilt that work on Mach 6 with the later network, measured it properly, and delivered it - while team claude spent the round on search features that did not pass their tests. The engine is better for it, which was the point.

## ✨ What changed

- **Evaluation: king buckets.** Each side reads the board through one of 8 zones chosen by where its own king stands, after mirroring the board so that king is on files a–d - sixteen views of the same weights. A pawn storm means one thing against a castled king and another against one in the centre, and now the network can tell. A king move into another zone rebuilds that side's half of the accumulator, lazily, only when the position is actually evaluated; every other move stays incremental.
- **Network C7** - 8 king buckets × 768 inputs → 256 → 8 output layers chosen by the number of pieces left, int16, format 3. Trained on **153.7 million** positions: 0.2's 118.6 million plus 35.1 million quiet positions from the theoden8 corpus (Lichess analysis at depth 18–22, mapped to our teachers' scale), 14 epochs.
- **Built with Mach 6.0.0 and mach-std 9.0.0** - 2.6% faster than the same code under 5.11, with the search tree unchanged.
- **The search is 0.2's**, unchanged: the node-count signature is the same 154,591.

## 📦 What's in the box

The **`-complete.zip`** is the one to play with:

| file | what it is |
|---|---|
| `machete.exe` | the engine: one static binary, no installer, no runtime |
| `machete.nnue` | its network (8 × 768 → 256 → 8 output layers, int16, format 3; 3.1 MB) |
| `README.txt` | setup, options, strength notes |
| `SHA256SUMS.txt` | checksums for the two files above |

The other archives are what CI builds for every platform - `machete` and `binpack` for Windows (x86-64), Linux (x86-64 and aarch64) and macOS (x86-64 and Apple silicon) - executables only; the engine needs **`machete.nnue`** (attached separately) beside it. Only the Windows build has been played and gated. **A 0.2 network will not load in 0.3**: the format changed with the king buckets.

<details>
<summary><b>🧪 How it was tested</b></summary>

35 gates in `check.sh`, each made to fail on purpose once: exact perft; `divide` against python-chess on random positions; every mate in one, two and three; a node-count signature; the network's integer arithmetic against a numpy reference, including the king-bucket orientation and worst-case overflow; the incremental accumulator against a fresh one after every move of random games, across king moves between zones; the trainer's GPU features against the same reference; parallel search; UCI including ponder; a self-play soak; the network found beside the executable. The release binary is byte for byte the one that played the final, rebuilt from its commit; the only change is the name it reports.

</details>

<details>
<summary><b>🔧 Options</b></summary>

| option | range | notes |
|---|---|---|
| `Threads` | 1–32 | default 1 |
| `Hash` | — | fixed at 128 MB; accepted and ignored |
| `EvalFile` | path | defaults to `machete.nnue` beside the executable; format 3 only |
| `Ponder` | on/off | supported |

**Not yet:** opening books, tablebases, Chess960.

</details>

<details>
<summary><b>🔐 Checksums (SHA-256)</b></summary>

```
7f4bd954ba16a7504d9ebd80e157466bfe7bd50ef955c878fb75be6e1c28ba95  machete.exe
ba8f36f00c6661ab489e3aaa13502c04c1dc2a7e07d162da61ddf32921c76039  machete.nnue
```

</details>

---

<div align="center">

Built with **Mach 6.0.0** and **mach-std 9.0.0** · training positions labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
