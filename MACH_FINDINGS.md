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
| 14 | **`mach build .` builds only the default artifact since 6.0**, as `mach test .` tests only its modules (finding 12): under 5.11 one build produced `machete.exe` and `binpack.exe`, under 6.0 it produces `machete.exe` alone and `--bin binpack` is needed for the other. Nothing says so, and CI, which builds each artifact by name from `mach build --plan`, did not notice; `check.sh`'s two decoder gates found `binpack.exe` missing when the 0.3.0 release was gated, and now build it. A build that skips a declared artifact could say which. | `mach build . --profile release` then `ls out/.../bin`; `check.sh` on 0.3.0 | not yet reported - the same issue as finding 12 |
| 13 | **6.0 made the engine 2.6% faster with nothing else changed**, the same search tree node for node - likely the register allocator's copy coalescing (#3939). The breaking change that touched us, tests declared by identifier, was 54 mechanical renames. | `harness/speed_ab.py`, 0.2 (mach 5.11) against the same source on 6.0 | positive |
| 15 | **AVX2 is unreachable except as hand-encoded bytes.** `extensions = ["x86-64-v3"]` leaves the binary byte-identical, `i16x16` is scalarized (2x slower), and inline asm has no VEX forms, so machete's AVX2 accumulator kernels are 146 VEX instructions written as `.byte` by a generator script, with `cpuid`/`xgetbv` detection by hand. The first draft had a wrong `vvvv` field that only a runtime test caught. Worth +4.3% nodes per second even on Zen+, which splits 256-bit ops. Suggested: VEX.256 in inline asm ahead of the 256-bit value work, `ymm` clobber names, a std CPU-feature query, `cpuid`'s implicit outputs in its table row | `harness/avx2gen.py`, SPEED-AVX2 | commented on briar-systems/mach#4128 (the VEX encoder is #3751, PR #4126) |
| 16 | **Loads are neither hoisted nor reused.** mach 6.5 reloads a loop-invariant field (`list.count`) and a value that only changes with its index (`scores[best]`) on every iteration of a store-free loop, and loads a `val` table entry twice in straight-line code. Hoisting by hand in one function made the whole engine 3.9% faster; force-inlining the small hot helpers, measured alongside, made it 1.4% slower, so load elimination is the lever, not inlining. Suggested order: pure `val`-global loads first, then loop LICM of loads when the loop has no stores, then redundant-load elimination with a simple base-object alias rule | SPEED-PICK, `--emit-asm` of `search.pick` and `position.put` | briar-systems/mach#4162 |
