# Round 2 final, 2026-09-26 21:56 to 23:56

`run_final.sh` as the rules describe it, with a fourth entry: **lite**, team
claude's exhibition entry (`claude2/lite` cb86dfe, the unmeasured search stack
with S-01 and S-02 off), added at the owner's request after the freeze so its
games were played in the same tournament. It is not an official entry; the
official entries are `claude` (aa27be7) and `cursor` (dad58a0), and the
control `v020` (the v0.2.0 release). Six pairings, 200 games at 10+0.1 and 100
at 60+0.6 each, then each entry against Koivisto 9.0, 40 games at 60+0.6.
Elo is from the first-named entry's side. The Koivisto error bars are the
harness's formula at a 7-11% score, where it is meaningless; the result is
that every entry, 0.2 included, is about 350-450 Elo below Koivisto, with no
wins.

**Winner: cursor** (54.7% over the two head-to-head phases pooled), and so
v0.3.0.

| match | result | score | Elo |
|---|---|---|---|
| claude-cursor-10-0.1 | 45 W 86 D 69 L | 0.4400 | -41.9 +/- 36.6 |
| claude-cursor-60-0.6 | 16 W 61 D 23 L | 0.4650 | -24.4 +/- 42.7 |
| claude-koivisto-60-0.6 | 0 W 6 D 34 L | 0.075 | -436 +/- 1054 |
| claude-v020-10-0.1 | 30 W 140 D 30 L | 0.5000 | -0.0 +/- 26.4 |
| claude-v020-60-0.6 | 11 W 69 D 20 L | 0.4550 | -31.4 +/- 37.9 |
| cursor-koivisto-60-0.6 | 0 W 8 D 32 L | 0.100 | -382 +/- 306 |
| cursor-v020-10-0.1 | 66 W 99 D 35 L | 0.5775 | +54.3 +/- 34.3 |
| cursor-v020-60-0.6 | 27 W 63 D 10 L | 0.5850 | +59.6 +/- 41.2 |
| lite-claude-10-0.1 | 39 W 127 D 34 L | 0.5125 | +8.7 +/- 29.2 |
| lite-claude-60-0.6 | 18 W 72 D 10 L | 0.5400 | +27.9 +/- 36.0 |
| lite-cursor-10-0.1 | 52 W 93 D 55 L | 0.4925 | -5.2 +/- 35.3 |
| lite-cursor-60-0.6 | 15 W 68 D 17 L | 0.4900 | -6.9 +/- 38.7 |
| lite-koivisto-60-0.6 | 0 W 9 D 31 L | 0.113 | -359 +/- 251 |
| lite-v020-10-0.1 | 39 W 125 D 36 L | 0.5075 | +5.2 +/- 29.6 |
| lite-v020-60-0.6 | 8 W 80 D 12 L | 0.4800 | -13.9 +/- 30.5 |
| v020-koivisto-60-0.6 | 0 W 7 D 33 L | 0.087 | -407 +/- 1065 |

| entry | points, both phases | games | score |
|---|---|---|---|
| cursor | 492.0 | 900 | 54.7% |
| lite | 453.5 | 900 | 50.4% |
| v020 | 431.0 | 900 | 47.9% |
| claude | 423.5 | 900 | 47.1% |
