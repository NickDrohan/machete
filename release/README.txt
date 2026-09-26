machete 0.2
===========

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
            0.2 reads network format 2 only; a 0.1 network will not load.
  Ponder    supported: go ponder, ponderhit and stop.

Not supported yet: opening books, endgame tablebases, Chess960.


How strong
----------
Against machete 0.1's engine, head to head, one thread each:
  +209 +/- 94 Elo at 10+0.1 and +179 +/- 91 at 60+0.6 (SPRT, both accepted),
  and +246 +/- 67 over 100 games at 10+0.1 in a later control match.
Against Rybka 2.3.2a (CCRL 40/15 about 3050) at 3 minutes + 2 seconds, from
balanced openings with no books: 10 wins in 10 games.
Its rating on an external list has not been re-measured; 0.1 was estimated at
3100-3200 on the CCRL 40/15 scale. It still loses clearly to today's strongest
engines.


What changed since 0.1
----------------------
Search: time management for real clocks (a soft target scaled by how settled
the best move is, and a hard stop); singular extensions and multi-cut;
correction history by pawn structure; a transposition table of 4-way buckets
replaced by depth and age; quiet history kept between moves; null move only
at or above beta; late-move reductions adjusted by history.

Speed, with the search unchanged: about 25% faster - the network's output
layer through SSE2 multiply-add, piece colour and kind looked up rather than
divided, legality tested only for moves that can expose the king, and fewer
repeated computations.

Endgames: against a bare king the engine drives it to the edge (and, with
bishop and knight, to the right corner): hard endings converted 6 of 12
against 1 of 12 before.

Evaluation: a new network - 768 -> 256 -> 1 with 8 output layers chosen by the
number of pieces left - trained on 118.6 million positions: 0.1's 63.6
million plus 55 million from a newer generator whose teachers (Stockfish,
PlentyChess, Reckless, Obsidian, Caissa) were chosen by how well their labels
track deep evaluations.


Credits
-------
Built with the Mach compiler 5.11.0 and mach-std 7.1. The network's training
positions were labelled by the engines named above; no engine's code is used.
