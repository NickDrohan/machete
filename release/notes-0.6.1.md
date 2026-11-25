<div align="center">

# ♞ machete 0.6.1

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.6.1-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%207.0-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**DTZ tablebases, read in Mach.** With `SyzygyPath` set, machete now reads the DTZ tables (`.rtbz`) beside the WDL ones, so it knows how to *win* a won ending, not only that it is won. `src/syzygy.mach` rewrites the DTZ half of the Fathom prober (MIT), as 0.5.6 rewrote the WDL half: the stored-side flag, the 8- and 16-bit value maps, and one ply of search when a table holds only the other side to move. Nothing links C.

At the root, the search is held to the moves Fathom's root ranking keeps: the moves that keep the best result and, in a won ending, keep it winnable inside the fifty-move rule. Once a position has repeated, it insists on progress. The search still chooses among them, so a mate it sees is still found the fastest way.

| test | positions / games | result |
|---|---|---|
| WDL and DTZ against python-chess, random 3-5 man positions | 25,000 (3,600 with en passant possible) | 0 disagreements |
| 21 tablebase wins needing 40-100 plies to the next capture or pawn move, each played twice, colours swapped, against 0.6.0, both with tables, 10+0.1 | 42 games | 20 wins, 18 draws, 4 losses: 0.6.1 converted about 20 of 21, 0.6.0 about 4 |

This fixes the failure `ASSUMPTIONS.md` recorded: won endings drawn by the fifty-move rule when the win needs a plan with no material change, now for every ending of up to five men. New debugging commands `tbdtz` and `tbroot` print the probe and the moves the root keeps.

**More of the pipeline in Mach.** Two new tools ship beside the engine:

- **`label`** scores training records with a teacher engine: `label 15k`, then `label relabel` for the close ones. It is byte for byte the farm's old Python labellers, which stay in `harness/farm/` as its reference, and now labels on the PC and the whole farm.
- **`records`** gives `stats`, `show` and `diff` for training-record files.

`check.sh` gates both. `tbcheck` holds the prober to python-chess's answers in `fixtures/syzygy_reference.txt`.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (0.6.0's network, candidate E), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them.

Tablebase files are not included. The 3-4-5 man set is about 1 GB from any Syzygy mirror: put the `.rtbw` and `.rtbz` files in one folder and give it as `SyzygyPath`.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes, including the new gates: the labeller against its Python reference with machete as the teacher, `records diff` able to fail, and the Syzygy prober against python-chess with the tables in `$SYZYGY`. The node-count signature is unchanged at 131,948, and there are 69 unit tests.

</details>

---

<div align="center">

Built with **Mach 7.0.0**, **mach-std 10.1.1** and **mach-json 0.1.0** · network candidate E · tablebase probing after Fathom (MIT); no engine's code is linked

</div>
