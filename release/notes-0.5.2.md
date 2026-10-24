<div align="center">

# ♞ machete 0.5.2

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.2-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

A release of fixes found by playing: one opening hole, one clock habit, and three new options. The network and the search are 0.5.1's: with an increment and the repertoire off, 0.5.2 searches exactly the tree 0.5.1 searches (same nodes and moves to depth 13 on three positions), so 0.5.1's measurements stand for it (+19 ± 12 against 0.5.0, −228 ± 24 against Koivisto 9.0).

**The Vienna Gambit is gone.** In a gauntlet against eight top engines, three of them (Torch, Alexandria, Berserk) won the same way: the repertoire's Vienna Gambit 3.f4 against 2...Nf6 reached 6.d4 Bb4, and machete gave a bishop with 7.Bb5+ c6 8.O-O cxb5 for compensation it believed in (0.00) and Stockfish did not (−2.3). Its Vienna games as White went 0-3-6. Against 2...Nf6 the repertoire now plays 3.Bc4. From 1.e4 e5 2.Nc3 Nf6, 0.5.1 played 3.f4 in 4 games of 12; 0.5.2 plays 3.Bc4 in all 12.

**Sudden death spends its clock.** In the same gauntlet, at 10+0, machete finished game after game with two to five minutes of its ten unused while its opponents searched deeper: the search spends a mean 0.44 of its aim (5,314 moves measured). With no increment the share is now a twentieth of the clock, not a twenty-fifth, and the lag reserve from 0.5.1 still stands behind it. Against 0.5.1's share, same engine, 1,000 games at 30+0: +2 ± 22, no game lost on time. Games with an increment are unchanged.

**New options, off by default:**

| option | what it does | measured |
|---|---|---|
| `Hash` | the transposition table's size, 1 MB to 32 GB (was fixed at 128 MB) | default 128 searches exactly as before; a larger table is being measured |
| `PasserBonus` | a passed-pawn term on top of the network once the queens are off, for the ranks where the network under-values passers (5/25/40 cp on the 5th/6th/7th) | −9 ± 8 over 1,800 games: the bias is real on paper, the search already covers it; left off |
| `SuddenMoves` | the share of the clock taken per move with no increment (default 20) | above |

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (0.5.1's network, unchanged), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes; the node-count signature is 0.5.1's (209,573). New tests: `Hash` resizes to a power of two and a resized table starts empty; `PasserBonus` sums both sides' passers, signs them for the side to move and steps aside while a queen is on the board; the sudden-death share keeps a 5+0 game with 130 ms of lag a move alive for 120 moves spending its whole aim every move (twice what a search spends), and fails at a share of 14.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network C33F280P3ALL, unchanged from 0.5.1 · no engine's code is used

</div>
