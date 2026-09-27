"""Emit machete's AVX2 accumulator kernels as Mach inline asm with VEX bytes.

The assembler has no AVX2 mnemonics (mach 6.0), so each instruction is its
two-byte-VEX encoding. HIDDEN = 256 int16 = 512 bytes = 16 ymm registers'
worth; the loops are fully unrolled over ymm0..ymm3 in rotation.
"""
HIDDEN_BYTES = 512


def vex2(reg_n_inverted_vvvv, L, pp):
    # C5 [R vvvv L pp], R and vvvv stored inverted: vvvv = 0 encodes as 1111, "no register"
    return [0xC5, (1 << 7) | ((~reg_n_inverted_vvvv & 15) << 3) | (L << 2) | pp]


def disp32(d):
    return [d & 0xFF, (d >> 8) & 0xFF, (d >> 16) & 0xFF, (d >> 24) & 0xFF]


def load(n, base_rm, d):   # vmovdqu ymmN, [base + d]
    return vex2(0, 1, 2) + [0x6F, 0x80 | (n << 3) | base_rm] + disp32(d)


def store(n, base_rm, d):  # vmovdqu [base + d], ymmN
    return vex2(0, 1, 2) + [0x7F, 0x80 | (n << 3) | base_rm] + disp32(d)


def arith(op, n, base_rm, d):  # vpaddw/vpsubw ymmN, ymmN, [base + d]
    return vex2(n, 1, 1) + [op, 0x80 | (n << 3) | base_rm] + disp32(d)


RDX, RCX = 2, 1
VZEROUPPER = [0xC5, 0xF8, 0x77]


def line(bs, n=None):
    tail = " :: writes(xmm%d)" % n if n is not None else " :: writes()"
    return "            .byte " + ", ".join("0x%02X" % b for b in bs) + tail


def column(op, name, verb):
    out = ["# {} one weight column into a half, 256 lanes as 16 ymm registers:".format(verb),
           "# into (rdx) {}= row (rcx). Callers check AVX2 first (see AVX2).".format("+" if op == 0xFD else "-"),
           "fun {}(into: *i16, row: *i16) {{".format(name),
           "    asm x86_64 {",
           "        mov rdx, {into}",
           "        mov rcx, {row}"]
    for k in range(HIDDEN_BYTES // 32):
        n = k % 4
        out.append(line(load(n, RDX, 32 * k), n))
        out.append(line(arith(op, n, RCX, 32 * k), n))
        out.append(line(store(n, RDX, 32 * k)))
    out.append(line(VZEROUPPER))
    out += ["    }", "}"]
    return "\n".join(out)


def copy():
    out = ["# copy a half, 512 bytes, as 16 ymm registers: to (rdx) = from (rcx)",
           "fun copy_half_avx2(to: *i16, from: *i16) {",
           "    asm x86_64 {",
           "        mov rdx, {to}",
           "        mov rcx, {from}"]
    for k in range(HIDDEN_BYTES // 32):
        n = k % 4
        out.append(line(load(n, RCX, 32 * k), n))
        out.append(line(store(n, RDX, 32 * k)))
    out.append(line(VZEROUPPER))
    out += ["    }", "}"]
    return "\n".join(out)


if __name__ == "__main__":
    print(column(0xFD, "add_column_avx2", "add"))
    print()
    print(column(0xF9, "sub_column_avx2", "subtract"))
    print()
    print(copy())
