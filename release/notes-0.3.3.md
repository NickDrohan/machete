<div align="center">

# ♞ machete 0.3.3

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.3-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.5-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![repertoire](https://img.shields.io/badge/repertoire-6%20systems-blue)
![cost](https://img.shields.io/badge/cost%20of%20the%20repertoire-none%20measured-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: the author's repertoire

0.3.3 changes **one thing** in how machete plays: it now prefers **its author's openings**. The network, search and everything else are 0.3.2's.

| as White | as Black |
|---|---|
| the **Vienna** (1.e4 e5 2.Nc3) | the **Marshall** against 1.e4 (1...e5, aiming for 8...d5 in the Ruy Lopez) |
| the **English** (1.c4) | the **Nimzo-Indian** against 1.d4 and 1.c4 |
| the **Catalan** (1.d4 Nf6 2.c4 e6 3.g3) | the **Grünfeld** against 1.d4 and 1.c4 |

The lines are in `repertoire.txt`: 56 of them, checked move by move by `harness/repgen.py` and compiled into the engine. A root move that reaches one of their positions gets a bonus (UCI option `Repertoire`, default **40** centipawns): each game one system per side is drawn to aim for and gets the full bonus, the rest of the repertoire half. It is a preference, not a book - a move the search judges worse by more than the bonus is still not played - and transpositions count, because positions are matched, not move orders.

| test | games | result |
|---|---|---|
| Repertoire 40 vs off, from the start position, 10+0.1 | 1,000 | **+3 ± 22** |
| Repertoire 60 vs off, same | 1,000 | +18 ± 22 |
| vs Spike 1.4, 2+1, from the start: on / off | 60 / 60 | 95.8% / 96.7% |
| vs Rybka 2.3.2a, 2+1, from the start: on / off | 60 / 60 | 88.3% / 93.3% (inside the noise of 60 games) |

No measurable cost. What it changes is which games machete plays: on lichess, 12 of its first 37 losses came with it playing 1...c5 as Black, which the repertoire replaces with 1...e5.

## 🔧 New options, off by default

| option | default | what it does |
|---|---|---|
| `Repertoire` | **40** | the bonus above; 0 turns the repertoire off |
| `Contempt` | 0 | against an opponent rated at or below the engine (`UCI_RatingAdv` ≥ 0), a draw scores this many centipawns against it, so it plays on for a win; against a stronger one a draw stays 0 |
| `UCI_RatingAdv` | 0 | the engine's rating minus the opponent's, which GUIs and lichess-bot send before each game |
| `Variety` / `VarietyMoves` | 0 / 8 | small random bonuses in the first moves, so repeated games differ |
| `Avx2` | on | off forces the SSE2 kernels (for timing) |

`Contempt` and `Variety` are off, so they change nothing unless set. Contempt is under test on its own and would become the default in a later version only if it measures positive.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (the same 768-wide network as 0.3.2), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. 0.3.2's network loads in 0.3.3.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, each made to fail on purpose once, among them the node-count signature (154,591, unchanged). Three new unit tests cover the repertoire: every line plays out on the engine's own board and reaches exactly the positions python-chess counts (a deliberately broken move was caught); a line prefers only its own side's moves; and each game's draw lands on every system. One more covers `Contempt`: a draw scores against the engine only when it is not the weaker side.

</details>

---

<div align="center">

Built with **Mach 6.5.0** and **mach-std 9.2.0** · repertoire positions from TCEC games · training positions labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
