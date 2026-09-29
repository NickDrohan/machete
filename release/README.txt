machete 0.3.2
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
            0.3.2 reads 768-wide format 3 networks only; an earlier
            version's network will not load.
  Ponder    supported: go ponder, ponderhit and stop.

Not supported yet: opening books, endgame tablebases, Chess960.


How strong
----------
0.3.2 changes one thing from 0.3.1: the network (below). Against the same
three outside engines at 2+1, on the openings 0.3.1 and 0.3.0 played:
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

Built with Mach 6.5.0 and mach-std 9.2.0.


Credits
-------
Built with the Mach compiler 6.5.0 and mach-std 9.2.0. The network's training
positions were labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa,
PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used.
