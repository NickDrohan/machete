<div align="center">

# ♞ machete 0.5.0

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.0-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.4.1](https://img.shields.io/badge/against%200.4.1-%2B26%20%C2%B1%2018-blue)
![speed](https://img.shields.io/badge/nodes%20per%20second-1.24x%200.4.1-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-36%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes%20in%20play-exactly%20one-lightgrey)

</div>

---

## 🎯 One change in play: the network reads the board by phase

Until now each side's half of the network was chosen by where its own king stood: eight king zones, each with its own set of inputs. A king that walks up the board in an endgame changed zones again and again, and a zone's inputs had to learn the opening, the middlegame and the endgame at once.

0.5.0's network chooses by **the kind of position** instead:

| layer | when |
|---|---|
| opening | queens on, 28 or more men on the board |
| middlegame | queens on, fewer men |
| endgame | from the moment the queens come off |

Each side still reads the board mirrored by its king's file. The network, **C33F280P3**, has three layers of inputs where 0.4.1's had eight zones, so it is 3.5 MB where 0.4.1's was 9.4 MB, and it was trained on more: 0.4.0's recipe plus 280 million Fischer Random positions where 0.4.0 had 140 million, 644 million positions in all.

The search is 0.4.1's, its tuned constants unchanged.

| the 0.5.0 package against the 0.4.1 package, each with its own network | games | result |
|---|---|---|
| **10+0.1**, no early stop | 1,500 | **+26 ± 18** (346 wins, 920 draws, 234 losses) |

| the network against 0.4.1's, same search (0.4.0's), no early stop | games | result |
|---|---|---|
| 10+0.1 | 1,500 | +19 ± 18 (359 wins, 864 draws, 277 losses) |
| 60+0.6 | 600 | +18 ± 28 (102 wins, 427 draws, 71 losses) |

And the two things in it, each on its own:

- **Layers by phase against king zones**, the same data: +13 ± 15 over 1,945 games at 10+0.1 (sequential test accepted, at least 10 Elo); a second training with another seed +14 ± 18 over 1,500.
- **280M Fischer Random positions against 140M**, both three-layer: +17 ± 18 over 1,500 games. A second seed of the 280M network played the first +10 ± 18, so the gain is not one lucky training.

## ⚡ And it is faster: the same moves, 1.24 times the nodes a second

Two things make 0.5.0 search more nodes in the same time, neither of which changes a move it plays:

- **The smaller network** stays in the processor's cache: 16% more nodes per second on its own.
- **A move's changes to the network are applied in one pass.** A quiet move adds one input and takes one away, a capture adds one and takes two; the network's running sums were copied from the parent position and then passed over once per change. Two new AVX2 kernels read the parent's sums and each weight row once and write the child's once: 8.1% less time for the same search, the tree identical node for node.

Together, on one thread, 305,000 nodes a second where 0.4.1 searches 246,000 (median of eight runs each, 1.5 million nodes on five positions).

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue`, `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them.

**0.5.0 reads three-layer networks only.** A network made for 0.4.1 or earlier (eight king zones) is refused with a message, and the engine falls back to its much weaker built-in evaluation; keep the `machete.nnue` that comes with it.

<details>
<summary><b>🔬 What else the week measured</b></summary>

- **More data on top of this network** - 22.7M rook endgames, 60M more ordinary positions, or the 133.5M human-game positions swapped for engine self-play - each played +5 to +10 against it over 1,500 games, inside the noise. None is in this release.
- **Ideas from another engine family's search**, each on its own against 0.4.1 over 1,500 games: razoring +9 ± 18, a wider mop-up evaluation +3, a drawishness scale −10, capture history −14, recapture and seventh-rank extensions −17 ± 18. None is in this release.
- **Move ordering.** A capture that loses material was searched before every quiet move except the killers and the counter move, against the comment beside it. The fix is being measured for the next release.
- **The bot's time losses.** Of 15 recent games lost on time, 12 had 30 seconds to 21 minutes left: the bot program, not the engine, gave up on games whose connection to lichess had dropped. The bot now reconnects.

</details>

<details>
<summary><b>🧪 How it was tested</b></summary>

The 36 gates in `check.sh` pass. The gate that holds the engine's network arithmetic to a numpy reference now builds its test networks in the layout the engine is built for (it reads `LAYERS` from the source), and fails when given the other layout. The node-count signature is 197,209 as in 0.4.1: it runs without a network. With 0.5.0's network, the packaged engine searches exactly the tree of the engine the network was measured on with 0.4.1's tuned constants as options (352,454 / 339,616 / 59,718 nodes to depth 13 on three positions), with the AVX2 kernels on or off. The fused kernels are held to the copy-and-passes loops on full-range values by a unit test, which fails when one subtraction is turned into an addition.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0**, the latest releases · network C33F280P3 · trained on positions labelled by Stockfish and other engines; no engine's code is used

</div>
