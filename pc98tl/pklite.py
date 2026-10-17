"""PKLITE packed DOS programs: unpacking to a plain MZ program, by running the program's own decompressor.

PKLITE 1.50's "extra" decompressor decrypts itself before it runs, so the program is unpacked by running
it (unicorn, 16-bit real mode): loaded as DOS would load it, its decompressor runs until the unpacked
program's own first interrupt (its startup's first DOS call); the far jump into the program before it is
the entry, its SS:SP the program's stack.  Run twice, loaded 1000h paragraphs apart: the words that
differ by that much are the relocations (their values less the load segment the original segments).
The image is the paragraphs the decompressor wrote from the load segment up, without a gap.
"""
import os
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_BLOCK, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn.x86_const import (UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_DS,
                               UC_X86_REG_ES, UC_X86_REG_AX)

SHIFT = 0x1000


def is_packed(exe):
    return exe[:2] == b"MZ" and exe[0x1E:0x20] == b"PK"


def _machine():
    """A 16-bit machine with its first megabyte mapped.  (Unicorn 2.1 on Windows faults on the first
    mapping a process makes; with faulthandler's handler in place the fault comes back as an OSError,
    without it the process dies: the handler is put in, quietly, for that first try, which is made
    again.)"""
    import faulthandler
    global _SINK, _MACHINE
    if _MACHINE is not None:
        _MACHINE.mem_write(0, bytes(0x100000))
        return _MACHINE
    if not faulthandler.is_enabled():
        _SINK = open(os.devnull, "w")
        faulthandler.enable(file=_SINK)
    for _ in range(3):
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        try:
            u.mem_map(0, 0x100000)
            _MACHINE = u
            return u
        except OSError:
            continue
    raise SystemExit("PKLITE: unicorn cannot map the machine's memory")


_SINK = None
_MACHINE = None             # (one machine a process, cleared for each run: unicorn does not take more)


def _run(exe, load):
    h = struct.unpack_from("<14H", exe, 0)
    hdr = h[4] * 16
    size = (h[2] - 1) * 512 + (h[1] or 512) - hdr if h[2] else len(exe) - hdr
    module = bytearray(exe[hdr:hdr + size])
    for k in range(h[3]):
        o, s = struct.unpack_from("<HH", exe, h[12] + 4 * k)
        at = s * 16 + o
        struct.pack_into("<H", module, at, (struct.unpack_from("<H", module, at)[0] + load) & 0xFFFF)
    u = _machine()
    psp = load - 0x10
    u.mem_write(psp * 16, b"\xcd\x20" + struct.pack("<H", 0xA000) + bytes(252))
    u.mem_write(load * 16, bytes(module))
    u.reg_write(UC_X86_REG_DS, psp)
    u.reg_write(UC_X86_REG_ES, psp)
    u.reg_write(UC_X86_REG_SS, (h[7] + load) & 0xFFFF)
    u.reg_write(UC_X86_REG_SP, h[8])
    u.reg_write(UC_X86_REG_CS, (h[11] + load) & 0xFFFF)
    u.reg_write(UC_X86_REG_IP, h[10])
    stub = (h[11] + load) * 16
    state = {"entry": None, "stack": None, "cs": u.reg_read(UC_X86_REG_CS), "top": load * 16}

    def block(uc, addr, size, data):
        cs = uc.reg_read(UC_X86_REG_CS)
        if cs != state["cs"]:
            state["cs"] = cs
            state["entry"] = (cs, uc.reg_read(UC_X86_REG_IP))
            state["stack"] = (uc.reg_read(UC_X86_REG_SS), uc.reg_read(UC_X86_REG_SP))

    written = bytearray(0x10000)      # the paragraphs written to

    def write(uc, access, addr, size, value, data):
        written[(addr >> 4) & 0xFFFF] = 1

    def intr(uc, no, data):
        # (no exception raised in a hook: unicorn's native side does not survive it)
        state["int"] = (no, uc.reg_read(UC_X86_REG_AX) >> 8, uc.reg_read(UC_X86_REG_CS))
        uc.emu_stop()

    hooks = [u.hook_add(UC_HOOK_BLOCK, block), u.hook_add(UC_HOOK_MEM_WRITE, write), u.hook_add(UC_HOOK_INTR, intr)]
    try:
        u.emu_start(stub + h[10], 0xFFFFF, count=200000000)
    finally:
        for k in hooks:
            u.hook_del(k)
    no = state.get("int")
    if no and no[0] == 0x21 and no[1] in (0x09, 0x4C) and no[2] == stub // 16:
        raise SystemExit("PKLITE: the decompressor stopped (not enough memory?)")
    if not state["entry"]:
        raise SystemExit("PKLITE: the program's entry is not reached")
    # the image: the paragraphs written from the load segment up, without a gap (the decompressor's own
    # copy, above, is apart from it)
    top = load
    while top < 0xA000 and written[top]:
        top += 1
    top *= 16
    return bytes(u.mem_read(load * 16, top - load * 16)), state["entry"], state["stack"], h


def unpack(exe, load=0x1000):
    """The program unpacked: a plain MZ program (its image, relocations, entry and stack).  The
    emulation runs in a Python of its own started with faulthandler (`-X faulthandler`): unicorn on
    Windows faults inside itself, which only that keeps from ending the process."""
    import subprocess
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.exe"), os.path.join(tmp, "out.exe")
        open(src, "wb").write(exe)
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # (now and then unicorn's faults end the process all the same: it is run again)
        for _ in range(4):
            r = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "pc98tl.pklite", src, dst, hex(load)],
                               cwd=here, capture_output=True, text=True)
            if not r.returncode and os.path.exists(dst):
                return open(dst, "rb").read()
            if "SystemExit" in r.stderr or "PKLITE:" in r.stderr:
                break
        raise SystemExit("PKLITE: the unpacking failed: %s" % (r.stdout + r.stderr)[-400:])


def _unpack(exe, load=0x1000):
    a, entry, stack, h = _run(exe, load)
    b, _e2, _s2, _h = _run(exe, load + SHIFT)
    n = min(len(a), len(b))
    img = bytearray(a[:n])
    relocs = []
    k = 0
    while k < n - 1:
        x, y = struct.unpack_from("<H", a, k)[0], struct.unpack_from("<H", b, k)[0]
        if x != y and (y - x) & 0xFFFF == SHIFT:
            struct.pack_into("<H", img, k, (x - load) & 0xFFFF)
            relocs.append(k)
            k += 2
            continue
        k += 1
    cs, ip = entry
    ss, sp = stack
    head = 0x20 + 4 * len(relocs)
    head += -head % 16
    total = head + len(img)
    packed_mem = (len(exe) - h[4] * 16) + 16 * h[5]
    minalloc = max(0x100, -(-(packed_mem - len(img)) // 16))
    out = struct.pack("<14H", 0x5A4D, total % 512, -(-total // 512), len(relocs), head // 16, minalloc, 0xFFFF,
                      (ss - load) & 0xFFFF, sp, 0, ip, (cs - load) & 0xFFFF, 0x20, 0) + b"\0" * 4
    out += b"".join(struct.pack("<HH", r & 0xF, r >> 4) for r in relocs)
    return bytes(out.ljust(head, b"\0")) + bytes(img)


if __name__ == "__main__":
    import sys
    _src, _dst, _load = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
    _out = _unpack(open(_src, "rb").read(), _load)
    open(_dst, "wb").write(_out)
