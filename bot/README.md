# machete's changes to lichess-bot

Patches against lichess-bot 2026.8.9.2, which machete plays through. Apply from lichess-bot's folder with `patch -p1 < file`.

- `lichess_bot.patch`: a game whose stream ends while the game goes on reconnects, instead of walking away from it; a
  `gameStart` repeated for a game that already has a thread is ignored. Without that, a reconnecting event stream set
  two engines playing one side, each answering a position a move old.
- `extra_game_handlers.patch`: sends `MoveOverhead` and `UCI_RatingAdv`, which python-chess does not send to UCI engines.
- `engine_wrapper.patch`: leaves a move on the avoid list when a replacement is within a pawn of it. The list's path is a
  constant at the top; set it for your machine. An engine must honour `searchmoves` for this (machete does from 0.5.3).

`harness/experience_build.py` builds the list from the bot's own games; run it every few minutes. Its paths are constants too.
