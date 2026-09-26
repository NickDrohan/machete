<div align="center">

# ♞ machete 0.2

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.2-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%205.11-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![vs 0.1](https://img.shields.io/badge/vs%200.1-%2B180%20to%20%2B250%20Elo-blue)
![rybka](https://img.shields.io/badge/vs%20Rybka%202.3.2a-10%2F10-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-33%20passing-brightgreen)
![speed](https://img.shields.io/badge/search-~25%25%20faster-lightgrey)

</div>

---

## 🏆 What 0.2 is

The engine that won a two-agent contest on one machine: Claude Code and Cursor each took machete 0.1 and made it as strong as they could, sharing the CPU and GPU through one job queue, then played a final under a neutral referee - with the original 0.1 engine alongside as a control.

| pairing | 10+0.1 · 100 games | 180+2 · 40 games |
|---|---|---|
| **machete 0.2** vs the other entry | 90 W · 10 D · 0 L | 32 W · 8 D · 0 L |
| **machete 0.2** vs machete 0.1 | 66 W · 29 D · 5 L · **+246 ± 67** | 20 W · 18 D · 2 L · **+168 ± 68** |

One thread and 128 MB each, balanced openings played with both colours, real clocks, no adjudication, no forfeits.

## ⬇️ Install in 30 seconds

1. Download **`machete-0.2.0-windows-x86_64-complete.zip`** below and unzip it anywhere, e.g. `Arena\Engines\machete\`.
2. In Arena: **Engines → Install New Engine →** pick `machete.exe` **→ UCI**.
3. Play. The engine loads `machete.nnue` from its own folder, and the `EvalFile` option shows the path it found.

> [!IMPORTANT]
> 0.2 uses a new network format. Keep the `machete.nnue` that comes with it - a 0.1 network will not load, and the engine says so rather than guessing.

## 💪 How strong

| test | result |
|---|---|
| vs 0.1's engine, 10+0.1 (SPRT) | **+209 ± 94**, 48 W · 27 D · 5 L, accepted |
| vs 0.1's engine, 60+0.6 (SPRT) | **+179 ± 91**, 40 W · 35 D · 3 L, accepted |
| vs **Rybka 2.3.2a** (CCRL ≈ 3050), 3+2, no books | **10 W · 0 D · 0 L** |

0.1 was estimated at 3100–3200 on the CCRL 40/15 scale; 0.2 has not been re-rated against an external list, and it still loses clearly to today's strongest engines.

## ✨ What changed

- **Time management for real clocks** — a soft target scaled by how settled the best move is and whether the score is falling, and a hard stop that always keeps a reserve.
- **Search** — singular extensions and multi-cut, correction history by pawn structure, a transposition table in 4-way cache-line buckets replaced by depth and age, quiet history kept between moves, null move only at or above beta, late-move reductions adjusted by history.
- **Speed, same search** — about **25% faster**: the network's output layer through SSE2 `pmaddwd`, piece colour and kind looked up instead of divided (Mach compiles `/ 6` to `div`), legality tested only for moves that can expose the king.
- **Endgames** — mop-up against a bare king: hard endings converted **6 of 12**, against 1 of 12 before.
- **Network** — 8 output layers chosen by the number of pieces left, trained on **118.6 million** positions, including 55 million labelled by a panel chosen for how well its labels track deep evaluations.
- **Pondering** — `go ponder`, `ponderhit` and `stop`.

## 📦 What's in the box

The **`-complete.zip`** is the one to play with:

| file | what it is |
|---|---|
| `machete.exe` | the engine: one static binary, no installer, no runtime |
| `machete.nnue` | its network (768 → 256 → 8 output layers, int16, format 2) |
| `README.txt` | setup, options, strength notes |
| `SHA256SUMS.txt` | checksums for the two files above |

The other archives are what CI builds for every platform - `machete` and `binpack` for Windows (x86-64), Linux (x86-64 and aarch64) and macOS (x86-64; Apple silicon via Rosetta while briar-systems/mach#3888 is open) - executables only; the engine needs **`machete.nnue`** (attached separately) beside it. Only the Windows build has been played and gated.

<details>
<summary><b>🧪 How it was tested</b></summary>

33 gates in `check.sh`, each made to fail on purpose once: exact perft; `divide` against python-chess on 330 random positions; every mate in one, two and three; a node-count signature; the network's integer arithmetic against a numpy reference, including worst-case overflow; the trainer's GPU features against the same reference; parallel search; UCI including ponder; a self-play soak; the network found beside the executable. Every search change was judged by SPRT at a real clock, and every speed change was required to leave the search tree identical.

</details>

<details>
<summary><b>🔧 Options</b></summary>

| option | range | notes |
|---|---|---|
| `Threads` | 1–32 | default 1 |
| `Hash` | — | fixed at 128 MB; accepted and ignored |
| `EvalFile` | path | defaults to `machete.nnue` beside the executable |
| `Ponder` | on/off | supported |

**Not yet:** opening books, tablebases, Chess960.

</details>

<details>
<summary><b>🔐 Checksums (SHA-256)</b></summary>

```
CHECKSUMS
```

</details>

---

<div align="center">

Built with **Mach 5.11.0** and **mach-std 7.1** · training positions labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless; no engine's code is used

</div>
