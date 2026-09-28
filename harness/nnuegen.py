"""Generate src/kernels.mach: the network's hand-encoded x86-64 kernels.

    python harness/nnuegen.py [--hidden 256] > src/kernels.mach

mach 6.5 neither lowers vectors to 256 bits nor spells AVX2, pmaddwd,
pmaxsw/pminsw or xgetbv in inline asm (briar-systems/mach#4128, MACH_FINDINGS
#15), so every kernel below is instruction bytes. They are generated rather
than written so that the hidden width is one parameter: a wider network is
this script with --hidden and nnue.HIDDEN changed to match, and a test in
nnue.mach refuses a build where the two differ.

Kernels, all on 16-bit accumulator lanes:
  accumulate_sse2/avx2  the output layer's half: clamp each lane to 0..QA,
                        multiply by its weight in pairs (pmaddwd), sum into
                        four 32-bit lanes written to `out`
  add/sub_column_avx2   into += / -= one weight column
  copy_half_avx2        to = from
Encodings: two-byte VEX (C5) where it suffices, three-byte (C4) for
vextracti128. Registers: xmm/ymm 0-5 only, all volatile under Win64.
"""
import argparse

RDX, RCX, RAX = 2, 1, 0


def d32(d):
    return [d & 0xFF, (d >> 8) & 0xFF, (d >> 16) & 0xFF, (d >> 24) & 0xFF]


def c5(vvvv, L, pp):
    """Two-byte VEX: R and vvvv stored inverted; vvvv 0 means none."""
    return [0xC5, 0x80 | ((~vvvv & 15) << 3) | (L << 2) | pp]


def modrm_mem(reg, base):
    return 0x80 | (reg << 3) | base


def modrm_reg(reg, rm):
    return 0xC0 | (reg << 3) | rm


# ------------------------------------------------------------------ VEX.256
def vload(n, base, d):
    return c5(0, 1, 2) + [0x6F, modrm_mem(n, base)] + d32(d)


def vstore(n, base, d):
    return c5(0, 1, 2) + [0x7F, modrm_mem(n, base)] + d32(d)


def vop_mem(op, dst, src1, base, d):
    return c5(src1, 1, 1) + [op, modrm_mem(dst, base)] + d32(d)


def vop_reg(op, dst, src1, src2):
    return c5(src1, 1, 1) + [op, modrm_reg(dst, src2)]


VZEROUPPER = [0xC5, 0xF8, 0x77]

# --------------------------------------------------------------- SSE2 bytes
def sload(n, base, d):   # movdqu xmmN, [base + d]
    return [0xF3, 0x0F, 0x6F, modrm_mem(n, base)] + d32(d)


def sop_reg(op, dst, src):
    return [0x66, 0x0F, op, modrm_reg(dst, src)]


PMAXSW, PMINSW, PMADDWD, PADDD, PADDW, PSUBW, PXOR, PCMPEQW = 0xEE, 0xEA, 0xF5, 0xFE, 0xFD, 0xF9, 0xEF, 0x75


def line(bs, writes=None):
    w = ", ".join(writes) if writes else ""
    return "            .byte " + ", ".join("0x%02X" % b for b in bs) + " :: writes(%s)" % w


def x86(body, params):
    """A kernel's body, x86-64 only; elsewhere the function does nothing and
    nnue never calls it."""
    return ["    $if ($mach.build.arch == $mach.arch.x86_64) {", "        asm x86_64 {"] + \
           ["            mov %s, {%s}" % p for p in params] + body + ["        }", "    }"]


def accumulate_sse2(hidden):
    body = ["            # xmm4 = 0, xmm3 = QA (255) in every lane, xmm2 = the sums",
            line(sop_reg(PXOR, 4, 4), ["xmm4"]),
            line(sop_reg(PCMPEQW, 3, 3), ["xmm3"]),
            line([0x66, 0x0F, 0x71, 0xD3, 0x08], ["xmm3"]),
            line(sop_reg(PXOR, 2, 2), ["xmm2"])]
    for k in range(hidden // 8):
        d = 16 * k
        body += ["            # lanes %d..%d" % (8 * k, 8 * k + 7),
                 line(sload(0, RDX, d), ["xmm0"]),
                 line(sop_reg(PMAXSW, 0, 4), ["xmm0"]),
                 line(sop_reg(PMINSW, 0, 3), ["xmm0"]),
                 line(sload(1, RCX, d), ["xmm1"]),
                 line(sop_reg(PMADDWD, 0, 1), ["xmm0"]),
                 line(sop_reg(PADDD, 2, 0), ["xmm2"])]
    body += ["            # movdqu [rax], xmm2", line([0xF3, 0x0F, 0x7F, 0x10])]
    return (["# the output layer's half on SSE2: clamp to 0..QA, pmaddwd with the",
             "# weights, four 32-bit sums to `out`",
             "pub fun accumulate_sse2(values: *i16, weights: *i16, out: *i32) {"] +
            x86(body, [("rdx", "values"), ("rcx", "weights"), ("rax", "out")]) + ["}"])


def accumulate_avx2(hidden):
    body = ["            # ymm4 = 0, ymm3 = QA (255) in every lane, ymm2 and ymm5 = the sums",
            line(vop_reg(PXOR, 4, 4, 4), ["xmm4"]),
            line(vop_reg(PCMPEQW, 3, 3, 3), ["xmm3"]),
            line(c5(3, 1, 1) + [0x71, modrm_reg(2, 3), 0x08], ["xmm3"]),
            line(vop_reg(PXOR, 2, 2, 2), ["xmm2"]),
            line(vop_reg(PXOR, 5, 5, 5), ["xmm5"])]
    for k in range(hidden // 16):
        d = 32 * k
        v, s = k % 2, (2 if k % 2 == 0 else 5)
        body += ["            # lanes %d..%d" % (16 * k, 16 * k + 15),
                 line(vload(v, RDX, d), ["xmm%d" % v]),
                 line(vop_reg(PMAXSW, v, v, 4), ["xmm%d" % v]),
                 line(vop_reg(PMINSW, v, v, 3), ["xmm%d" % v]),
                 line(vop_mem(PMADDWD, v, v, RCX, d), ["xmm%d" % v]),
                 line(vop_reg(PADDD, s, s, v), ["xmm%d" % s])]
    body += ["            # ymm2 += ymm5, fold the high 128 bits onto the low, store four sums",
             line(vop_reg(PADDD, 2, 2, 5), ["xmm2"]),
             # vextracti128 xmm1, ymm2, 1: C4 E3 7D 39 /r ib, reg = source, rm = destination
             line([0xC4, 0xE3, 0x7D, 0x39, modrm_reg(2, 1), 0x01], ["xmm1"]),
             # vpaddd xmm2, xmm2, xmm1 (VEX.128)
             line(c5(2, 0, 1) + [PADDD, modrm_reg(2, 1)], ["xmm2"]),
             # vmovdqu [rax], xmm2 (VEX.128)
             line(c5(0, 0, 2) + [0x7F, 0x10]),
             line(VZEROUPPER)]
    return (["# the output layer's half on AVX2, 16 lanes a step, same sums as SSE2",
             "pub fun accumulate_avx2(values: *i16, weights: *i16, out: *i32) {"] +
            x86(body, [("rdx", "values"), ("rcx", "weights"), ("rax", "out")]) + ["}"])


def column(op, name, verb, hidden):
    body = []
    for k in range(hidden // 16):
        n = k % 4
        body += [line(vload(n, RDX, 32 * k), ["xmm%d" % n]),
                 line(vop_mem(op, n, n, RCX, 32 * k), ["xmm%d" % n]),
                 line(vstore(n, RDX, 32 * k))]
    body.append(line(VZEROUPPER))
    return ["# %s one weight column: into %s= row, %d lanes" % (verb, "+" if op == PADDW else "-", hidden),
            "pub fun %s(into: *i16, row: *i16) {" % name] + x86(body, [("rdx", "into"), ("rcx", "row")]) + ["}"]


def copy(hidden):
    body = []
    for k in range(hidden // 16):
        n = k % 4
        body += [line(vload(n, RCX, 32 * k), ["xmm%d" % n]), line(vstore(n, RDX, 32 * k))]
    body.append(line(VZEROUPPER))
    return ["# copy a half: to = from, %d lanes" % hidden,
            "pub fun copy_half_avx2(to: *i16, from: *i16) {"] + x86(body, [("rdx", "to"), ("rcx", "from")]) + ["}"]


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
        asm x86_64 {
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
        asm x86_64 {
            mov r8, {px}
            xor ecx, ecx
            # xgetbv
            .byte 0x0F, 0x01, 0xD0 :: writes(rax, rdx)
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
    args = parser.parse_args()
    h = args.hidden
    assert h % 16 == 0
    out = ["# GENERATED by harness/nnuegen.py --hidden %d; edit the generator, not this file." % h,
           "#",
           "# The network's hand-encoded x86-64 kernels for a hidden layer of %d" % h,
           "# lanes; see the generator for why they are bytes. nnue.mach chooses",
           "# between them and holds each to its portable loop in tests.",
           "",
           "use std.types.bool.bool;",
           "use std.types.bool.false;",
           "",
           "pub val KERNEL_HIDDEN: i64 = %d;" % h,
           "", DETECT, ""]
    for block in (accumulate_sse2(h), accumulate_avx2(h), column(PADDW, "add_column_avx2", "add", h),
                  column(PSUBW, "sub_column_avx2", "subtract", h), copy(h)):
        out += block + [""]
    print("\n".join(out).rstrip("\n"))


if __name__ == "__main__":
    main()
