# Training machete's network in Mach

The owner's direction (2026-09-30): move everything to Mach over time, starting
with the trainer. `harness/nnue/train.py` (PyTorch) is the reference until the
Mach trainer has trained a network that plays as well as a PyTorch one.

## Where it stands

**Phase 1 - a CPU trainer, proven equal to PyTorch: done.**

- `src/train.mach`: the network, target, loss, backward pass, PyTorch's Adam and
  the weight clip; the quantized export (`MCHNNUE3`). Threads split the work by
  hidden unit, so no two write the same memory.
- `src/tools/train.mach` (artifact `trainer`): `train check` (fixed batches in
  file order, for comparison) and `train export`.
- `harness/nnue/trainer_check.py`: runs PyTorch and Mach from the same weights
  over the same batches.
  - 10 steps of 512: losses agree to 1e-7 relative, weights to 3.5e-6 - exact.
    A deliberately wrong Adam constant (beta2 0.99) fails it (weights 6.5e-3).
  - 200 steps of 4096 on 8 threads: within PyTorch's own noise. PyTorch against
    itself with each batch reordered drifts nearly as far (mean weight gap
    2.7e-4 against Mach's 3.7e-4; loss 3.3e-4 against 5.0e-4). Adam amplifies
    rounding: a weight with a near-zero gradient takes a full learning-rate step
    in whichever direction its rounding points.
- Unit tests (`mach test . --bin trainer`): exp, orientation, rounding, and a
  finite-difference gradient check on active hidden units (a check on an
  inactive unit compared 0 with 0 and passed with a halved gradient; it now
  fails that).

Speed, first cut: ~19k positions/s on 8 threads of a busy Threadripper 2920X,
against ~500k/s for PyTorch on the RTX 4060 Ti.

## Plan

**Phase 2 - a trainer that can train a whole network.**
`train run`: corpora as `path[@N]`, a held-out validation set, shuffling by
windows sampled from every source (train.py's lesson: contiguous windows drift,
-55 Elo), epochs with the 0.8-per-epoch learning-rate decay, a `.partial` file
each epoch renamed at the end (the queue's `--requires` must never see a
network still training). Gate: a small network trained both ways on the same
data, compared by SPRT at equal settings - it must not lose.

**Phase 3 - speed on the CPU.**
SIMD (f32x8 where the target has AVX2) for the feature sums and the gradient
scatter; Adam only on rows a batch touched, with the skipped decay applied
lazily when a row is next touched (exact for Adam's moment decay, and the
dense update of 4.7M weights is most of a small batch's time); a persistent
worker pool instead of three spawns per step; reading records with prefetch.
Target: within 5x of the GPU.

**Phase 4 - the GPU from Mach.**
`mach-vk` (Vulkan declarations, commands loaded at runtime) and compute
shaders written in Mach, as the `boom` engine writes its shaders. The feature
transformer is a sparse gather-sum per position: one workgroup per position,
one invocation per hidden unit; the backward pass scatters with atomics or a
sort by feature. Gate: the same trainer_check comparison, then the same SPRT.

**Phase 5 - the rest of the harness.**
The data generator (the engine already plays; the teacher is Stockfish over
UCI, which Mach can drive through std.process), the match runner, the SPRT.
Python stays where a library is the point (python-chess for PGN and legality
checks in tests) until Mach has one.

## Findings for the Mach team (MACH_FINDINGS.md when it is merged)

- mach-std has sqrt but no exp or ln; the engine and the trainer each carry
  their own. A trainer needs exp for the sigmoid.
