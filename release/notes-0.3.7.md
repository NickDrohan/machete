<div align="center">

# ♞ machete 0.3.7

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.7-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![positions](https://img.shields.io/badge/training%20positions-364M-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: the Sveshnikov Sicilian replaces the Marshall

0.3.7 changes **one thing**: what machete answers 1.e4 with. The network (C33), the search and everything else are 0.3.6's.

The Marshall was machete's worst opening on lichess: as Black in the Ruy Lopez it went 1 win, 6 draws, 17 losses on 0.3.3, against opponents who replayed the same booked refutation game after game. The replacement was chosen by measurement, not by taste:

| Black system | over 3.17 billion LAION Stockfish games | under best play by both sides | machete as Black against full Stockfish 19 (250 games) |
|---|---|---|---|
| **Sveshnikov** | 48.0% | **46.6%** | **11.0%** |
| Marshall | 49.4% | 42.5% | 11.0% |
| Dragon | 39.5% | 47.0% | 8.8% |
| Kalashnikov | 51.1% | 36.2% | 8.0% |
| Najdorf | 42.6% | 18.5% | 7.0% |

The Sveshnikov is the one Sicilian that is good on all three. The middle column matters most: LAION's openings are partly random, so an average over all its games rewards a system where White often goes wrong. The Kalashnikov averaged 51.1% for Black but its main line, 6.N1c3 a6 7.Na3 b5 8.Nd5, gives Black 31.7%, which is what a booked opponent would play.

The lines (`repertoire.txt`, `black sveshnikov:`) come from the same data: at Black's turns the move that is best under best play, at White's every reply played in 5% or more of 80 million games, 18 plies deep. They cover the main lines 7.Bg5 and 7.Nd5, the Rossolimo 3.Bb5, 3.Nc3, 2.Nc3 and the Alapin 2.c3.

| test | result |
|---|---|
| repertoire against 0.3.6, from the start position, 10+0.1 | see the release body (no cost expected: the repertoire is a bonus at the root) |
| nodes at a fixed depth (bench) | 154,921, unchanged |

Self-play cannot say whether an opening suits machete against the field; lichess can. The number to watch is machete's score as Black against 1.e4.

## 🔧 Built with Mach 6.10.1

The compiler moves from 6.5.0 to 6.10.1 and the standard library to 9.4.1. The moves are identical (the same node counts at every depth tested); bench is 2-4% faster.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (C33, 0.3.7's own), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Every network since 0.3.2 loads in 0.3.7.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, among them the node-count signature (154,921, unchanged). The test above was played by the Mach match runner, game for game identical to the Python one it replaced.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.4.1** · training positions labelled by Stockfish 19 and 16, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
