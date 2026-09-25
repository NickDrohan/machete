<div align="center">

# ♞ machete 0.1

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.1-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%205.11-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![strength](https://img.shields.io/badge/strength-~3100--3200%20CCRL--scale-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-29%20passing-brightgreen)
![size](https://img.shields.io/badge/engine-220%20KB-lightgrey)
![deps](https://img.shields.io/badge/runtime%20dependencies-none-lightgrey)

</div>

---

## ⬇️ Install in 30 seconds

1. Download **`machete-0.1.0-windows-x86_64-complete.zip`** below and unzip it anywhere, e.g. `Arena\Engines\machete\`.
2. In Arena: **Engines → Install New Engine →** pick `machete.exe` **→ UCI**.
3. Play. The engine loads `machete.nnue` from its own folder on start-up, and the `EvalFile` option shows the path it found.

> [!TIP]
> If `EvalFile` shows `<empty>`, the network is not beside `machete.exe` and the engine is playing on its much weaker fallback evaluation.

## 📦 What's in the box

The **`-complete.zip`** is the one to play with:

| file | what it is |
|---|---|
| `machete.exe` | the engine: one static 220 KB binary, no installer, no runtime |
| `machete.nnue` | its evaluation network (768 → 256 → 1, int16) |
| `README.txt` | setup, options, strength notes |
| `SHA256SUMS.txt` | checksums for the two files above |

The other archives are what CI builds for every platform - `machete` and `binpack`, the Leela training-data decoder, for Windows (x86-64), Linux (x86-64 and aarch64) and macOS (x86-64; Apple silicon runs it under Rosetta, as the native build waits on briar-systems/mach#3888) - executables only. The engine needs **`machete.nnue`** (attached separately) in the same folder; only the Windows build has been played and gated.

## 💪 How strong

Roughly **3100–3200 on the CCRL 40/15 scale**, one thread, 3 minutes + 2 seconds, from the latest rating ladder:

| opponent | CCRL 40/15 | machete scored | implied |
|---|---|---|---|
| Spike 1.4 | 2950 | 23 W · 11 D · 6 L | 3108 ± 127 |
| Rybka 2.3.2a | 3050 | 28 W · 7 D · 5 L | 3278 ± 148 |
| Koivisto 9.0 | 3300 | 0 W · 2 D · 38 L | well short |

Every game started from move 1 with openings the engines chose themselves, no opening books on either side, no move cap. An estimate with a wide error bar, not a rating-list entry - and it loses clearly to today's top engines.

## ⚙️ Under the hood

- **Search** — iterative-deepening PVS, transposition table (128 MB), null-move pruning, late-move reductions tuned by an *improving* signal, futility and reverse futility pruning, aspiration windows, quiescence that answers checks. Lazy SMP up to 32 threads (8 threads: **+144 Elo** over 1).
- **Evaluation** — an NNUE trained on 63.6 million positions from the self-play of Stockfish, Berserk, Alexandria, Obsidian and Caissa, each scored by that engine's own search.
- **Move generation** — magic bitboards and hardware bit scans; perft verified exactly against published counts and differentially against python-chess.
- **In Mach** — about 4,600 lines. Against a pure-Python reference it is **66–108× faster** at move generation.

<details>
<summary><b>🧪 How it was tested</b></summary>

Every claim is a gate in `check.sh`, and every gate has been made to fail on purpose once, so none of them is passing by accident:

- exact perft on the six standard positions; `divide` matches python-chess on 330 random positions
- every mate in one, two and three in the fixture sets found at fixed depth
- the network's integer arithmetic matches a numpy reference exactly, including worst-case overflow in both signs
- a fixed-depth node-count signature, so any accidental search change fails
- a won game the engine once drew is replayed, and it must never stop on a mate it has not searched to its length
- UCI behaviour including `stop` and malformed input; a self-play soak with no illegal move or crash
- the network is found beside the executable - and its absence is reported, not hidden

</details>

<details>
<summary><b>🔧 Options</b></summary>

| option | range | notes |
|---|---|---|
| `Threads` | 1–32 | default 1 |
| `Hash` | — | fixed at 128 MB in this version; accepted and ignored |
| `EvalFile` | path | defaults to `machete.nnue` beside the executable |

**Not yet:** pondering (leave *ponder* off), opening books, tablebases, Chess960. Queen against knight, queen against rook and two bishops are still sometimes drawn by the fifty-move rule.

</details>

<details>
<summary><b>🔐 Checksums (SHA-256)</b></summary>

```
c5002087ddafa7518604d5b44b4433b553ff3a8153b1b9c28211ae0c7c5edd23  machete.exe
8b1fa3c74cc05813ce22ef7d568c76ce2217861feffe259cea64f24b06243c1a  machete.nnue
```

</details>

---

<div align="center">

Built with **Mach 5.11.0** and **mach-std 7.1** · the network's training positions were labelled by the engines named above; no engine's code is used

</div>
