<div align="center">

# ♞ machete 0.5.6

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.6-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**Continuation history.** A quiet move is now ordered by how it has done as the answer to the move just played and to the side's own previous move, not only by how it has done in general. It costs 7.7% of the search's speed and is worth it:

| test, same network | games | Elo |
|---|---|---|
| fixed nodes (40,000 a move) against 0.5.5 | 2,000 | +16.5 ± 9.6 |
| 10+0.1 against 0.5.5, first run | 3,000 | +9 ± 12 |
| 10+0.1 against 0.5.5, second run | 3,000 | +12 ± 12 |
| both runs together | 6,000 | **about +10** (935 wins, 4,310 draws, 755 losses) |

**Syzygy tablebases.** With `SyzygyPath` set to a folder of `.rtbw` files (up to five men), the search knows the result of those endings outright, probing after every capture and pawn move. The tables are read and decoded in Mach: `src/syzygy.mach` rewrites the WDL half of the Fathom prober (MIT; its notice is in `notices/FATHOM-LICENSE.txt`), and nothing links C. Its answers match python-chess's on 25,000 random three-to-five-man positions, 3,600 of them with en passant possible. Against the same engine without tables, 10+0.1: +4 ± 15 over 2,000 games (few games reach five men at that speed). In a queen-and-pawn against rook ending it reaches depth 18 in 200,000 nodes, where it needed 1.3 million without.

**Chess960.** `UCI_Chess960` makes the engine play Fischer Random: castling is the king taking its own rook, and FENs may give castling rights by file (Shredder-FEN) or as KQkq (X-FEN). Its move counts match python-chess's on six Chess960 positions.

## 🧪 What was tried and left out

| change | result | |
|---|---|---|
| capture history, two strengths | −10 ± 10 and −31 ± 9 at fixed nodes | out |
| history pruning, two margins | +2 ± 9 and +1 ± 9 at fixed nodes | out: not shown |
| staged move generation, two forms | −20 ± 9 and −10 ± 9 at fixed nodes | out: quiet moves scored after the captures' subtrees had moved the history |
| prefetching the table entry | 3.7% slower | out |
| continuation history from one move back only | 3.6% slower, +4 ± 12 on the clock | out |

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (0.5.5's network), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Tablebase files are not included: the 3-4-5 man set is about 1 GB from any Syzygy mirror.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes; the node-count signature is now 131,948 (continuation history, and castling's history slot under the new encoding). 69 unit tests, among them Chess960 perft against python-chess and the staged-mode and castling-spelling tests.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network 0.5.5's (candidate C) · tablebase probing after Fathom (MIT); no engine's code is linked

</div>
