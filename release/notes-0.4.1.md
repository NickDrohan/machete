<div align="center">

# ♞ machete 0.4.1

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.4.1-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.4.0](https://img.shields.io/badge/against%200.4.0-%2B31%20%C2%B1%2018-blue)
![against Koivisto](https://img.shields.io/badge/against%20Koivisto%209.0-%2B17%20over%200.4.0-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-36%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: the search's constants, tuned

0.4.1 changes **one thing**: thirteen of the fifteen numbers that decide how hard the search prunes and reduces. The network is 0.4.0's, byte for byte; the code is 0.4.0's apart from those defaults.

The numbers had never been tuned for a network evaluation: they were inherited from published engines when machete still evaluated by hand. They were tuned by SPSA, in self-play at 5+0.05: 5,746 steps on 0.3.0 two weeks ago (never applied), continued on 0.4.0 to 15,457 steps (about 31,000 games).

| constant | 0.4.0 | 0.4.1 | what it does |
|---|---|---|---|
| RfpMargin | 85 | **57** | reverse futility margin per ply: prune a node whose evaluation is this far above beta |
| FutBase / FutMul | 120 / 110 | **115 / 99** | futility margin near the horizon |
| LmpBase | 6 | **7** | quiet moves tried before late move pruning |
| NmpBase | 3 | **2** | null move reduction, fixed part |
| NmpEvalDiv | 200 | **181** | null move: a ply more per this many centipawns above beta |
| LmrBase / LmrDiv | 75 / 225 | **86 / 213** | late move reduction table |
| LmrHistDiv | 4096 | **3849** | history worth one ply of reduction |
| SeDepth | 8 | **6** | shallowest node that tries a singular extension |
| AspWindow | 25 | **19** | aspiration window half-width |
| QsDelta | 200 | **203** | quiescence delta margin |
| IirDepth | 6 | **5** | internal iterative reduction from this depth |

NmpDiv (3) and SeMargin (2) came out where they were.

| 0.4.1's search against 0.4.0's, same network, no early stop | games | result |
|---|---|---|
| **10+0.1** | 1,500 | **+31 ± 18** (292 wins, 1,048 draws, 160 losses) |
| **60+0.6** | 600 | +14 ± 28 (78 wins, 468 draws, 54 losses) |

**Against an outside engine.** Gains inside one engine family have overstated gains outside it before, so each search played Koivisto 9.0 (one thread, 128 MB, no books) over 1,200 games at 10+0.1 under the same conditions: 0.4.0 scored −308 ± 28, 0.4.1 −291 ± 27. About +17, in line with the head-to-head result.

The 0.3.0 tune alone was worth as much (+17 ± 22 and +21 ± 34 against 0.4.0's defaults, −284 ± 27 against Koivisto); continuing it moved the numbers further but not the strength (+3 ± 18 against it). This release ships the finished tune, the one with the most games behind it.

## 🔬 What else the week found

- **Inputs by game phase.** A network that reads the board through three layers (opening, middlegame, and the endgame, which begins when the queens come off) beat 0.4.0's eight king zones +13 ± 15 over 1,945 games at 10+0.1, but only +9 ± 24 at 60+0.6. A second training with another seed is being measured before it ships.
- **More data keeps helping, a little.** Adding 140M more Fischer Random positions (280M in all) lowered the error on positions no network had seen and played +7 ± 18 over 1,500 games; 60M more ordinary positions +13 ± 18. Neither is in this release.
- **The lichess games.** Of 1,061 games the bot did not win since 1 October, 816 reached an endgame and 10 of those had the bot two pawns ahead somewhere; all ten were rook positions and the moves that let them go were rook placement. A training set of 20 million rook endgames from real games is being generated.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue`, `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Every network since 0.3.2 loads in 0.4.1.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 36 gates in `check.sh` pass, among them the node-count signature, which moves from 154,921 to 197,209 because the search changed. The packaged engine searches exactly the tree 0.4.0 searches with the tuned values set as options (635,361 nodes to depth 14 from a Sicilian, both ways; 0.4.0's defaults search 809,913), so the matches above, played with 0.4.0's executable and the tuned values as options, measure this build. Every constant is still a UCI option, so 0.4.0's search is one `setoption` per constant away.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network C33F140, unchanged from 0.4.0 · tuned by SPSA in self-play; no engine's code is used

</div>
