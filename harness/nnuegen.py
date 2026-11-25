"""Generate src/kernels.mach: the network's x86-64 kernels.

    python harness/nnuegen.py [--hidden 256] [--out src/kernels.mach]

Up to mach 6.10 these kernels were instruction bytes: mach 6.5 neither lowered vectors to 256 bits nor spelled AVX2,
pmaddwd, pmaxsw/pminsw or xgetbv in inline asm (briar-systems/mach#4128, MACH_FINDINGS #15). mach 7's assembler spells
all of them, and its register allocator refuses the old byte blocks, so from 7.0 they are written as instructions
under the instruction-set head they need (`x86-64` for SSE2, `x86-64,avx2` for the rest). The instructions,
registers and memory layout are the ones the bytes encoded; the assembler may pick shorter displacements.

They are generated rather than written so that the hidden width is one parameter: a wider network is this script with
--hidden and nnue.HIDDEN changed to match, and a test in nnue.mach refuses a build where the two differ.

Kernels, all on 16-bit accumulator lanes:
  accumulate_screlu_avx2  accumulate_avx2 with the hidden values squared first (format 5)
  accumulate_sse2/avx2  the output layer's half: clamp each lane to 0..QA,
                        multiply by its weight in pairs (pmaddwd), sum into
                        four 32-bit lanes written to `out`
  add/sub_column_avx2   into += / -= one weight column
  copy_half_avx2        to = from
  carry_add_sub(_sub)_avx2  to = from + add - sub (- sub2): a move's usual
                        changes to a child's half in one pass
Registers: xmm/ymm 0-5 and rax, rcx, rdx, r8, r9, all volatile under Win64.
"""
import argparse

I = "            "


def mem(base, d):
    return "[%s]" % base if d == 0 else "[%s + %d]" % (base, d)


def x86(body, params, head="x86-64"):
    """A kernel's body, x86-64 only; elsewhere the function does nothing and nnue never calls it."""
    return ["    $if ($mach.build.arch == $mach.arch.x86_64) {", "        asm %s {" % head] + \
           [I + "mov %s, {%s}" % p for p in params] + body + ["        }", "    }"]


def accumulate_sse2(hidden):
    body = [I + "# xmm4 = 0, xmm3 = QA (255) in every lane, xmm2 = the sums",
            I + "pxor xmm4, xmm4",
            I + "pcmpeqw xmm3, xmm3",
            I + "psrlw xmm3, 8",
            I + "pxor xmm2, xmm2"]
    for k in range(hidden // 8):
        d = 16 * k
        body += [I + "# lanes %d..%d" % (8 * k, 8 * k + 7),
                 I + "movdqu xmm0, %s" % mem("rdx", d),
                 I + "pmaxsw xmm0, xmm4",
                 I + "pminsw xmm0, xmm3",
                 I + "movdqu xmm1, %s" % mem("rcx", d),
                 I + "pmaddwd xmm0, xmm1",
                 I + "paddd xmm2, xmm0"]
    body += [I + "movdqu [rax], xmm2"]
    return (["# the output layer's half on SSE2: clamp to 0..QA, pmaddwd with the",
             "# weights, four 32-bit sums to `out`",
             "pub fun accumulate_sse2(values: *i16, weights: *i16, out: *i32) {"] +
            x86(body, [("rdx", "values"), ("rcx", "weights"), ("rax", "out")]) + ["}"])


def fold_and_store():
    return [I + "# ymm2 += ymm5, fold the high 128 bits onto the low, store four sums",
            I + "vpaddd ymm2, ymm2, ymm5",
            I + "vextracti128 xmm1, ymm2, 1",
            I + "vpaddd xmm2, xmm2, xmm1",
            I + "vmovdqu [rax], xmm2",
            I + "vzeroupper"]


def accumulate_avx2(hidden, screlu=False):
    body = [I + "# ymm4 = 0, ymm3 = QA (255) in every lane, ymm2 and ymm5 = the sums",
            I + "vpxor ymm4, ymm4, ymm4",
            I + "vpcmpeqw ymm3, ymm3, ymm3",
            I + "vpsrlw ymm3, ymm3, 8",
            I + "vpxor ymm2, ymm2, ymm2",
            I + "vpxor ymm5, ymm5, ymm5"]
    for k in range(hidden // 16):
        d = 32 * k
        v, s = k % 2, (2 if k % 2 == 0 else 5)
        body += [I + "# lanes %d..%d" % (16 * k, 16 * k + 15),
                 I + "vmovdqu ymm%d, %s" % (v, mem("rdx", d)),
                 I + "vpmaxsw ymm%d, ymm%d, ymm4" % (v, v),
                 I + "vpminsw ymm%d, ymm%d, ymm3" % (v, v)]
        if screlu:
            body += [I + "vpmullw ymm%d, ymm%d, ymm%d" % (v, v, v),
                     I + "vpsrlw ymm%d, ymm%d, 8" % (v, v)]
        body += [I + "vpmaddwd ymm%d, ymm%d, %s" % (v, v, mem("rcx", d)),
                 I + "vpaddd ymm%d, ymm%d, ymm%d" % (s, s, v)]
    body += fold_and_store()
    if screlu:
        head = ["# the output layer's half for SCReLU on AVX2: clamp, square, shift by 8, multiply-add",
                "pub fun accumulate_screlu_avx2(values: *i16, weights: *i16, out: *i32) {"]
    else:
        head = ["# the output layer's half on AVX2, 16 lanes a step, same sums as SSE2",
                "pub fun accumulate_avx2(values: *i16, weights: *i16, out: *i32) {"]
    return head + x86(body, [("rdx", "values"), ("rcx", "weights"), ("rax", "out")], "x86-64,avx2") + ["}"]


def column(op, name, verb, hidden):
    body = []
    for k in range(hidden // 16):
        n, d = k % 4, 32 * k
        body += [I + "vmovdqu ymm%d, %s" % (n, mem("rdx", d)),
                 I + "%s ymm%d, ymm%d, %s" % (op, n, n, mem("rcx", d)),
                 I + "vmovdqu %s, ymm%d" % (mem("rdx", d), n)]
    body.append(I + "vzeroupper")
    return ["# %s one weight column: into %s= row, %d lanes" % (verb, "+" if op == "vpaddw" else "-", hidden),
            "pub fun %s(into: *i16, row: *i16) {" % name] + \
        x86(body, [("rdx", "into"), ("rcx", "row")], "x86-64,avx2") + ["}"]


def carry(hidden, subtracts):
    """A child's half in one pass: to = from + add - sub (- sub2). The move's usual
    changes, done as a copy and then a pass per change, read and write the half
    once for each; this reads the parent and each weight row once and writes the
    child once. Lanes wrap like vpaddw/vpsubw anywhere else, so the order of the
    additions does not change the result."""
    params = [("rdx", "to"), ("rcx", "from"), ("rax", "add"), ("r8", "sub")]
    name, sig = "carry_add_sub_avx2", "to: *i16, from: *i16, add: *i16, sub: *i16"
    if subtracts == 2:
        params.append(("r9", "sub2"))
        name, sig = "carry_add_sub_sub_avx2", sig + ", sub2: *i16"
    body = []
    for k in range(hidden // 16):
        n, d = k % 4, 32 * k
        body += [I + "vmovdqu ymm%d, %s" % (n, mem("rcx", d)),
                 I + "vpaddw ymm%d, ymm%d, %s" % (n, n, mem("rax", d)),
                 I + "vpsubw ymm%d, ymm%d, %s" % (n, n, mem("r8", d))]
        if subtracts == 2:
            body.append(I + "vpsubw ymm%d, ymm%d, %s" % (n, n, mem("r9", d)))
        body.append(I + "vmovdqu %s, ymm%d" % (mem("rdx", d), n))
    body.append(I + "vzeroupper")
    what = "from + add - sub" + (" - sub2" if subtracts == 2 else "")
    return ["# a child's half in one pass: to = %s, %d lanes" % (what, hidden),
            "pub fun %s(%s) {" % (name, sig)] + x86(body, params, "x86-64,avx2") + ["}"]


def copy(hidden):
    body = []
    for k in range(hidden // 16):
        n, d = k % 4, 32 * k
        body += [I + "vmovdqu ymm%d, %s" % (n, mem("rcx", d)), I + "vmovdqu %s, ymm%d" % (mem("rdx", d), n)]
    body.append(I + "vzeroupper")
    return ["# copy a half: to = from, %d lanes" % hidden,
            "pub fun copy_half_avx2(to: *i16, from: *i16) {"] + \
        x86(body, [("rdx", "to"), ("rcx", "from")], "x86-64,avx2") + ["}"]


DETECT = '''# whether this CPU runs AVX2 and its operating system saves the ymm state:
# cpuid leaf 7 EBX bit 5, leaf 1 ECX bit 27 (OSXSAVE), then XCR0 bits 1-2
pub fun detect_avx2() bool {
    $if ($mach.build.arch == $mach.arch.x86_64) {
        var leaf7: u64  = 0;
        var leaf1: u64  = 0;
        var xcr0:  u64  = 0;
        val p7:    *u64 = ?leaf7;
        val p1:    *u64 = ?leaf1;
        val px:    *u64 = ?xcr0;
        asm x86-64 {
            mov r8, {p7}
            mov r9, {p1}
            push rbx
            mov eax, 7
            xor ecx, ecx
            cpuid
            mov [r8], rbx
            mov eax, 1
            xor ecx, ecx
            cpuid
            mov [r9], rcx
            pop rbx
        }
        if (((leaf1 >> 27) & 1) == 0) { ret false; }
        asm x86-64,xsave,osxsave {
            mov r8, {px}
            xor ecx, ecx
            xgetbv
            mov [r8], rax
        }
        ret ((leaf7 >> 5) & 1) == 1 && (xcr0 & 6) == 6;
    }
    $or {
        ret false;
    }
}'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--out", default="src/kernels.mach")
    args = parser.parse_args()
    h = args.hidden
    assert h % 16 == 0
    out = ["# GENERATED by harness/nnuegen.py --hidden %d; edit the generator, not this file." % h,
           "#",
           "# The network's x86-64 kernels for a hidden layer of %d lanes, as" % h,
           "# instructions; see the generator for their history. nnue.mach chooses",
           "# between them and holds each to its portable loop in tests.",
           "",
           "use std.types.bool.bool;",
           "use std.types.bool.false;",
           "",
           "pub val KERNEL_HIDDEN: i64 = %d;" % h,
           "", DETECT, ""]
    for block in (accumulate_sse2(h), accumulate_avx2(h), accumulate_avx2(h, screlu=True),
                  column("vpaddw", "add_column_avx2", "add", h), column("vpsubw", "sub_column_avx2", "subtract", h),
                  copy(h), carry(h, 1), carry(h, 2)):
        out += block + [""]
    # LF on every host, as .gitattributes wants; print() would write CRLF on Windows
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out).rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
