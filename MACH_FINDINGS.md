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

## 2026-09-25 - moving to mach-template, and the first macOS build

Putting machete on briar-systems/mach-template brought its CI: every target
built on every host, formatting checked, releases cut from tags.

| | finding | evidence | upstream |
|---|---|---|---|
| 4 | **More than 128 MB of static data does not link on `darwin-aarch64`**: "macho: dynamic call-site displacement overflows a 26-bit branch". A 12-line program with a 140 MB array fails where 100 MB builds, and the same 140 MB program builds for `darwin-x86_64`. machete's 128 MB transposition table is a static array, so machete does not build for Apple silicon; its decoder, without the table, does. | the repro in the issue; `mach build . --target darwin-aarch64` | briar-systems/mach#3888 |
| 5 | **`mach fmt` made adoption painless.** The code, written without the formatter, needed 181 changed lines across 9 files, all layout; the node-count signature was unchanged, and uncommitted work was carried across by formatting base and work separately. | the import pull request, NickDrohan/machete#2 | positive; nothing to report |


## 2026-09-26 - moving to mach 6.0.0 and mach-std 9.0.0

| | finding | evidence | upstream |
|---|---|---|---|
| 10 | **mach#3888 was fixed within a day of the report.** The Mach-O writer had placed call stubs after the static data; they now sit in `__TEXT` after the code, as Apple's `ld` does. machete builds for `darwin-aarch64` again and its CI leg is back. | briar-systems/mach#3888, fixed by #3899 | resolved; positive |
| 11 | **For a few hours no std release fit the newest compiler.** mach 6.0.0 shipped at 14:51 and std 8.2.0 (from 04:38) declares `mach = "^5.12"`, which a caret range reads as excluding 6.0. `mach dep update` said so exactly - "std 8.2.0 requires mach ^5.12, and this is mach 6.0.0" - and std 9.0.0, tagged minutes later with `mach = "^6"`, resolved it. Clear error, brief gap. | `mach dep update . std` | not reported; the resolver's message was all that was needed |
| 12 | **`mach test .` quietly tests less than it used to.** Since 5.12 it tests only the default artifact's modules, so the `binpack` decoder's own tests dropped out of `mach test .` without a warning - 51 tests ran where 54 exist. `--bin binpack` runs them; check.sh now gates that too. A line saying which artifacts' tests were not selected would have caught it. | `mach test .` against `--bin binpack` | not yet reported - worth an issue |
| 13 | **6.0 made the engine 2.6% faster with nothing else changed**, the same search tree node for node - likely the register allocator's copy coalescing (#3939). The breaking change that touched us, tests declared by identifier, was 54 mechanical renames. | `harness/speed_ab.py`, 0.2 (mach 5.11) against the same source on 6.0 | positive |
