# What building machete says about Mach

machete exists partly to put Mach to real work and report what that work
finds. Each entry names what was observed, the evidence, and whether it has
gone upstream. Earlier findings live in the README: the missing
`popcnt`/`bsf`/`bsr` mnemonics (briar-systems/mach#3724, accepted) and the
SIMD widening results on #3736.

## 2026-09-24 - a binpack decoder in Mach (machete, `src/binpack.mach`)

A port of `harness/nnue/leela.py`, which reads the Leela Chess Zero training
data Stockfish trains on. The Python version was the oracle.

**It works, exactly.** The Mach decoder's records are byte-identical to the
Python reference: 406,343 records on nnue-pytorch's sample, 2,000,000 from the
Leela file (140,000,000 bytes), and a 451,559-position fixture now gated in
`check.sh`. That covers bit-level decoding, reuse of the engine's own move
generation and attack tables, and floating-point work that had to match numpy
and Python's `round` to the last bit - including parsing the score table
with `std.data.json`, whose floats came out exact.

**It is fast.** 2,000,000 positions in 14.6 s against Python's 9 min 26 s on
one core: 39x, on a machine busy with other work. Not yet profiled; the hot
path generates the legal move list for every position.

**It compiled first time** - 600 lines across a library module and a second
executable artifact - with the conventions read from working code.

Findings:

| | finding | evidence | upstream |
|---|---|---|---|
| 1 | **Withdrawn: the skill was right, our copy was stale.** A local clone of the Mach repo still carried `writing-mach`, which says there are no tagged unions and spells the entry point `$main.symbol`. Upstream replaced it on 2026-07-03 with one `mach` skill (`doc/skills/mach/SKILL.md`, last updated 2026-09-14) that documents `tag`, `sel` and `#[symbol("main")]` exactly as the compiler takes them. The lesson is ours: read the skill from upstream, not from a clone three months old. | upstream `doc/skills/mach/SKILL.md`; local clone at 89608869, 2026-06-11 | not reported - nothing to report |
| 2 | **std has no zstd.** `std.compress` has gzip, zlib and inflate. The large public chess datasets (linrock's binpacks, Lichess's evaluation dumps) ship as zstd, so the Mach decoder reads a copy decompressed by Python first. A zstd decoder would make the tool self-contained - and would be a substantial, well-specified piece of Mach to write. | `std/src/compress/` (also upstream `dev`); `leela.py --decompress` | briar-systems/mach-std#913 |
| 3 | **Two artifacts in one project: a clear error, good behaviour.** Adding a second `bin` artifact made `mach test` stop with "several artifacts support the selected target and none is marked `default = true`", naming both and the fix. `default = true` on one, `--bin` for the other, and both build and test. | `products/machete/mach.toml` | positive; nothing to report |
