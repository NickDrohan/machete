"""Where a machete search spends its time, by sampling the running engine.

    python harness/profile.py out/windows-x86_64/release/bin/machete.exe --net NET \
        [--fen FEN] [--seconds 10]

Build with debug information first (`mach build . --profile release -g`): the
code is the same optimised code, and the DWARF sections name its functions.
The engine is started, told to search one position, and every thread is
paused about once a millisecond to read where it is (SuspendThread,
GetThreadContext, ResumeThread). Each instruction pointer is mapped to the
function containing it through .debug_info, and the report counts samples
per function: a flat profile, self time only.

Windows only. Nothing here needs administrator rights, unlike the system
profilers, and nothing is installed.
"""

import argparse
import os
import collections
import ctypes
import ctypes.wintypes as wt
import struct
import subprocess
import sys
import time

# ------------------------------------------------------------------ the PE and DWARF


def pe_sections(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    count = struct.unpack_from("<H", blob, pe + 6)[0]
    symptr, nsym = struct.unpack_from("<II", blob, pe + 12)
    optional = struct.unpack_from("<H", blob, pe + 20)[0]
    image_base = struct.unpack_from("<Q", blob, pe + 24 + 24)[0]
    strings = symptr + 18 * nsym
    table = pe + 24 + optional
    sections = {}
    for i in range(count):
        at = table + 40 * i
        name = blob[at:at + 8].rstrip(b"\0").decode()
        vsize, va, rsize, rptr = struct.unpack_from("<IIII", blob, at + 8)
        if name.startswith("/"):
            off = strings + int(name[1:])
            name = blob[off:blob.index(b"\0", off)].decode()
        sections[name] = (va, blob[rptr:rptr + min(vsize, rsize)] if rptr else b"")
    return image_base, sections


def uleb(data, at):
    result, shift = 0, 0
    while True:
        byte = data[at]
        at += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return result, at


def sleb(data, at):
    result, shift = 0, 0
    while True:
        byte = data[at]
        at += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            if byte & 0x40:
                result -= 1 << shift
            return result, at


def abbrevs(data, offset):
    table = {}
    at = offset
    while True:
        code, at = uleb(data, at)
        if code == 0:
            return table
        tag, at = uleb(data, at)
        children = data[at]
        at += 1
        attrs = []
        while True:
            name, at = uleb(data, at)
            form, at = uleb(data, at)
            const = None
            if form == 0x21:  # implicit_const
                const, at = sleb(data, at)
            if name == 0 and form == 0:
                break
            attrs.append((name, form, const))
        table[code] = (tag, children, attrs)


FIXED = {0x0B: 1, 0x05: 2, 0x06: 4, 0x07: 8, 0x0C: 1, 0x11: 1, 0x12: 2, 0x13: 4, 0x14: 8,
         0x0E: 4, 0x17: 4, 0x10: 4, 0x1F: 4, 0x19: 0, 0x1E: 16, 0x20: 8, 0x25: 1, 0x26: 2,
         0x27: 3, 0x28: 4, 0x29: 1, 0x2A: 2, 0x2B: 3, 0x2C: 4, 0x21: 0}


def functions(sections):
    """[(low, high, name)] for every subprogram with a code range, sorted by low."""
    info = sections[".debug_info"][1]
    abbrev = sections[".debug_abbrev"][1]
    strs = sections[".debug_str"][1]
    found = []
    at = 0
    while at < len(info):
        unit_length, version = struct.unpack_from("<IH", info, at)
        end = at + 4 + unit_length
        unit_type, address_size, abbrev_off = struct.unpack_from("<BBI", info, at + 6)
        cursor = at + 12
        table = abbrevs(abbrev, abbrev_off)
        while cursor < end:
            code, cursor = uleb(info, cursor)
            if code == 0:
                continue
            tag, _, attrs = table[code]
            values = {}
            for name, form, const in attrs:
                value = None
                if form == 0x01:        # addr
                    value = struct.unpack_from("<Q", info, cursor)[0]
                    cursor += address_size
                elif form == 0x08:      # string
                    stop = info.index(b"\0", cursor)
                    value = info[cursor:stop].decode("utf-8", "replace")
                    cursor = stop + 1
                elif form == 0x0E:      # strp
                    off = struct.unpack_from("<I", info, cursor)[0]
                    value = strs[off:strs.index(b"\0", off)].decode("utf-8", "replace")
                    cursor += 4
                elif form in (0x0F,):   # udata
                    value, cursor = uleb(info, cursor)
                elif form == 0x0D:      # sdata
                    value, cursor = sleb(info, cursor)
                elif form == 0x18:      # exprloc
                    size, cursor = uleb(info, cursor)
                    cursor += size
                elif form in (0x0A,):   # block1
                    cursor += 1 + info[cursor]
                elif form == 0x09:      # block
                    size, cursor = uleb(info, cursor)
                    cursor += size
                elif form == 0x21:
                    value = const
                elif form in FIXED:
                    size = FIXED[form]
                    if size in (1, 2, 4, 8):
                        value = int.from_bytes(info[cursor:cursor + size], "little")
                    cursor += size
                else:
                    raise ValueError("DWARF form 0x{:x} not handled".format(form))
                values[name] = (form, value)
            if tag == 0x2E and 0x11 in values:          # subprogram with low_pc
                low = values[0x11][1]
                high_form, high = values.get(0x12, (None, 0))
                if high_form != 0x01:
                    high = low + high                  # high_pc as a length
                name = values.get(0x03, (None, "?"))[1]
                found.append((low, high, name))
        at = end
    found.sort()
    return found


# ------------------------------------------------------------------ sampling

TH32CS_SNAPTHREAD = 0x4
THREAD_ALL = 0x0002 | 0x0008 | 0x0040  # suspend/resume, get context, query
CONTEXT_CONTROL = 0x00100001


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]


def threads_of(pid):
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    entry = THREADENTRY32()
    entry.dwSize = ctypes.sizeof(THREADENTRY32)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(entry))
    while ok:
        if entry.th32OwnerProcessID == pid:
            out.append(entry.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return out


def sample(pid, seconds, interval):
    """Instruction pointers of the busiest thread: the search, not the UCI reader."""
    k32 = ctypes.windll.kernel32
    k32.OpenThread.restype = wt.HANDLE
    buffer = ctypes.create_string_buffer(1232 + 16)
    base = (ctypes.addressof(buffer) + 15) & ~15
    context = (ctypes.c_char * 1232).from_address(base)

    class FILETIME(ctypes.Structure):
        _fields_ = [("low", wt.DWORD), ("high", wt.DWORD)]

    def cpu(h):
        times = [FILETIME() for _ in range(4)]
        k32.GetThreadTimes(h, *[ctypes.byref(t) for t in times])
        return (times[3].high << 32 | times[3].low)

    handles = [k32.OpenThread(THREAD_ALL, False, tid) for tid in threads_of(pid)]
    before = [cpu(h) for h in handles]
    time.sleep(0.3)
    busiest = max(range(len(handles)), key=lambda i: cpu(handles[i]) - before[i])
    h = handles[busiest]
    ips = []
    stop = time.perf_counter() + seconds
    while time.perf_counter() < stop:
        if k32.SuspendThread(h) != 0xFFFFFFFF:
            struct.pack_into("<I", context, 0x30, CONTEXT_CONTROL)
            if k32.GetThreadContext(h, ctypes.c_void_p(base)):
                ips.append(struct.unpack_from("<Q", context, 0xF8)[0])
            k32.ResumeThread(h)
        # time.sleep rounds up to the 15 ms timer tick; spin instead
        until = time.perf_counter() + interval
        while time.perf_counter() < until:
            pass
    for handle in handles:
        if handle:
            k32.CloseHandle(handle)
    return ips


def module_base(pid, name):
    import ctypes.wintypes
    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x0410, False, pid)
    modules = (wt.HMODULE * 256)()
    needed = wt.DWORD()
    psapi.EnumProcessModules(h, modules, ctypes.sizeof(modules), ctypes.byref(needed))
    first = modules[0]
    k32.CloseHandle(h)
    return first


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--net", required=True)
    parser.add_argument("--fen", default="r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    blob = open(args.engine, "rb").read()
    image_base, sections = pe_sections(blob)
    funcs = functions(sections)
    lows = [f[0] for f in funcs]

    proc = subprocess.Popen([os.path.abspath(args.engine)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            universal_newlines=True)
    proc.stdin.write("uci\nsetoption name EvalFile value {}\nposition fen {}\ngo infinite\n".format(
        args.net, args.fen))
    proc.stdin.flush()
    time.sleep(0.5)
    base = module_base(proc.pid, args.engine) or image_base
    ips = sample(proc.pid, args.seconds, 0.001)
    proc.stdin.write("stop\nquit\n")
    proc.stdin.flush()
    proc.wait()

    import bisect
    counts = collections.Counter()
    inside = 0
    for ip in ips:
        address = ip - base + image_base
        k = bisect.bisect_right(lows, address) - 1
        if k >= 0 and funcs[k][0] <= address < funcs[k][1]:
            counts[funcs[k][2]] += 1
            inside += 1
        else:
            counts["(outside machete's code: waiting, the OS, std)"] += 1
    total = sum(counts.values())
    print("{} samples, {} in machete's functions".format(total, inside))
    for name, n in counts.most_common(args.top):
        print("{:6.1%}  {}".format(n / total, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
