machete 0.3.7
=============

A UCI chess engine written in Mach (https://github.com/briar-systems/mach),
a low-level, explicitly typed systems language. Windows x86-64.

  machete.exe     the engine (no runtime or installer needed)
  machete.nnue    its evaluation network; keep it in the same folder


Using it in Arena (or any UCI GUI)
----------------------------------
1. Put both files in one folder, e.g. Arena\Engines\machete\.
2. Engines > Install New Engine > choose machete.exe; type UCI.
3. That's it. The engine loads machete.nnue from its own folder on start-up;
   the EvalFile option shows the path it loaded. If it shows <empty>, the
   network was not found and the engine is playing on its much weaker
   fallback evaluation - check the file is beside machete.exe.

Options:
  Threads   1 to 32 (default 1). Lazy SMP.
  Hash      fixed at 128 MB in this version; the option is accepted and ignored.
  EvalFile  path to a network file; defaults to machete.nnue beside the exe.
            0.3.7 reads 768-wide format 3 networks: every one since 0.3.2 loads,
            0.3.1's and earlier do not.
  Ponder    supported: go ponder, ponderhit and stop.
  Repertoire  0 to 100 (default 40): prefer the author's openings - White the
            Vienna, English and Catalan; Black the Sveshnikov Sicilian,
            Nimzo-Indian and Grunfeld - by this many centipawns. 0 plays without it.
  Contempt  0 to 100 (default 0): against an opponent rated at or below the
            engine, score draws this much against it. Needs UCI_RatingAdv.

Not supported yet: opening books, endgame tablebases, Chess960.


What changed since 0.3.6
------------------------
One thing, the opening against 1.e4: the Sveshnikov Sicilian replaces the
Marshall, which lost 17 of 24 games on lichess against booked opponents. The
Sveshnikov was chosen over 3.17 billion Stockfish self-play games (LAION), by
its result under best play by both sides (46.6% for Black, the best Sicilian
there), and tied first of eight systems for machete against full Stockfish.
Built with Mach 6.10.1 and mach-std 9.4.1 (same moves, bench 2-4% faster).


What changed since 0.3.5
------------------------
One thing, in the search: when the side to move has its queen within two
squares of the enemy king, its quiet moves are no longer pruned near the
horizon and are reduced one ply less. On lichess 0.3.3 took a pawn and was
mated in five by quiet moves it had pruned; 0.3.4 needed depth 22 to see it,
0.3.6 sees it at depth 18. Against 0.3.4 with the same network: +2 +/- 17
Elo over 1673 games, no cost. The network is 0.3.5's.


What changed since 0.3.4
------------------------
One thing: the network. C33 is 0.3.4's recipe plus 10.5 million more of the
data farm's positions (Stockfish 19 at 1500 nodes a move from a broad opening
book): 364 million in all. Against 0.3.4's network on the same engine at
10+0.1: +18 +/- 21 Elo over 1096 games, SPRT accepted; the packaged engines
head to head, +5 +/- 11 over 4000 games. The search, the repertoire and the options are 0.3.4's.


What changed since 0.3.3
------------------------
One thing: the network. C30 is trained on 0.3.3's positions plus 40 million
new ones that the data farm's Raspberry Pis made, Stockfish 19 against itself
at 1500 nodes a move from a broad opening book: 353 million in all, the same
768-wide shape. Head to head at 10+0.1 against 0.3.3 as released: +24 +/- 24
Elo over 824 games (204 wins, 474 draws, 146 losses), SPRT accepted. The
search, the repertoire and the options are 0.3.3's.


What changed since 0.3.2
------------------------
One thing in how it plays: the repertoire above, on by default. Measured at
no cost: +3 +/- 22 Elo against the same engine without it, from the start
position (1000 games). The network and search are 0.3.2's. New options:
Contempt, UCI_RatingAdv and Variety, off by default, and Avx2, on (turning it
off forces the SSE2 kernels, for timing).


How strong
----------
0.3.6 plays as strongly as 0.3.5 against itself (+2 +/- 17) and sees attacks on its
king sooner. 0.3.5 was 0.3.4 plus about +5 (4000 games); 0.3.4 was 0.3.3 plus +24. 0.3.2 changed one thing from 0.3.1, the
network: head to head at 10+0.1, +28 +/- 27 Elo over 659 games (176 wins, 360
draws, 123 losses). Against three outside engines at 2+1, on the openings
0.3.1 and 0.3.0 played:
  Spike 1.4      51 wins,  8 draws,  1 loss     (0.3.1: 49,  9, 2)
  Rybka 2.3.2a   45 wins, 12 draws,  3 losses   (0.3.1: 43, 11, 6)
  Koivisto 9.0    0 wins, 17 draws, 43 losses   (0.3.1:  1, 15, 44)
63.6% against them together where 0.3.1 scored 61.4%: about +15 Elo, inside
the noise of 180 games but in the direction the head-to-head test measured.
On the CCRL Blitz scale (2+1, one CPU) that is still somewhere around
3050-3150; ASSESSMENT.md in the repository explains why only a range.


What changed since 0.3.1
------------------------
Network: C22 - 8 king buckets x 768 inputs -> 768 -> 8 output layers, half
again 0.3.1's width, trained on 282 million positions: 0.3.1's 262 million
plus 20 million from the engine's own games labelled by Stockfish 19. At
equal time, 768 wide beat 512 wide on the same data by +13 +/- 17 Elo
(SPRT accepted, 10+0.1). 1024 wide lost (-17 +/- 26): at that width the
slower evaluation costs more than the network adds.

Nothing else changed: the search, options and AVX2 kernels are 0.3.1's, the
kernels generated for the new width.

Built with Mach 6.10.1 and mach-std 9.4.1.


Credits
-------
Built with the Mach compiler 6.10.1 and mach-std 9.4.1. The network's training
positions were labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa,
PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used.
