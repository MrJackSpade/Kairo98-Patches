"""Isaku's AI5 (pc98tl/ai5.py, engine "isaku"): its English kept out of the scripts.

Isaku's AI5.EXE (EXEPACK'd) runs a script loaded at a fixed address of its data segment (the scene
at 0, below the libraries the game keeps loaded: DEF.MES at 6F54h, DUNCALL.MES at 88B8h, ITEMMAIN.MES
at 9A4Ch; its variables from E000h), and system call 2Ah is a gosub to an address (three bytes: the
09h number's, the spare low bits set).  The scenes nearly fill their room as they are; so the English
goes into a segment of its own:

* a half-width string (06 ... 06) the rebuilt script would carry becomes 06 7Fh, the offset (three
  bytes, a 09h number's, never 00, 01 or 06), 06; its letters (to an 06) at that offset of the
  script's English, a member of the script's archive named after it (NAME.ENG, one for every script);
* each 2Ah's address is moved with what it points at (the scene's own statements, or a library's);
* AI5.EXE (unpacked) gets a helper: loading a script (its loader, 4B3Dh) loads its English into the
  English segment (a scene's at 0, each library's at a place of its own), and the half-width string
  statement draws 06 7Fh's letters from there; the memory the program asks for grows by 64 KB for the
  segment.
"""
import difflib
import re
import struct

from . import ai5, exepack
from .adl import _asm16
from .adl5 import _move_up

FAR = 0x7F
LIBRARY_START = 0x6F54          # (the scene's room ends where the first library is loaded)


def enc09(v):
    """The three bytes of 2Ah's address (the 09h number's encoding, its spare low bits set)."""
    hi, lo = v >> 8, v & 0xFF
    ax0 = (hi << 2) | ((lo >> 7) & 1) << 1 | (lo >> 6) & 1
    bl0 = ((lo & 0x3F) << 2) | 3
    w = (ax0 << 2) | 3
    b1 = ((w >> 8) << 2) | 3
    b2 = w & 0xFF
    return bytes([b1 & 0xFF, b2, bl0])


def dec09(b):
    return ai5._num(b"\x09" + bytes(b), 0)[1]


def calls(d):
    """[offset of 2Ah's address bytes] of a script."""
    return [t[1] + 2 for t in ai5.tokenize(d) if t[0] == "op" and t[3] == 4 and d[t[1] + 1] == 0x2A]


def far_strings(d):
    """(the script with its half-width strings of 4 letters or more moved out, its English): each
    06 ... 06 statement (not a call's argument) 06 7Fh lo hi 06."""
    out, blob, last = bytearray(), bytearray(), 0
    for kind, s, e, _x in ai5.tokenize(d):
        if kind == "ank" and e - s - 2 >= 4:
            out += d[last:s] + bytes([6, FAR]) + enc09(len(blob)) + b"\x06"
            blob += d[s + 1:e]
            last = e
    out += d[last:]
    return bytes(out), bytes(blob)


def _sig(d, t):
    kind, s, e, _x = t
    return ("T",) if kind in ("ch", "ank") else (kind, d[s:e] if kind != "op" or d[s] != 4 or d[s + 1] != 0x2A
                                                     else d[s:s + 2])


def offset_map(old, new):
    """{an old statement's offset: its new one} for the statements outside the text that a rebuild
    left as they were (matched in order); a text's first character maps to where its text begins."""
    a, b = ai5.tokenize(old), ai5.tokenize(new)
    sa, sb = [_sig(old, t) for t in a], [_sig(new, t) for t in b]
    m = {}
    for i, j, n in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_matching_blocks():
        for k in range(n):
            m[a[i + k][1]] = b[j + k][1]
    # (a text run: its first character maps to the new text's first token)
    for k, t in enumerate(a):
        if t[1] not in m and t[0] in ("ch", "ank"):
            nxt = next((m[u[1]] for u in a[k:] if u[1] in m), len(new))
            m[t[1]] = nxt
    return m


def remap(d, own, libs):
    """d with its 2Ah addresses moved: one in the scene's room by own ({old: new}), one in a
    library's by its map (libs: {base: (old length, {old: new})})."""
    out = bytearray(d)
    for at in calls(d):
        v = dec09(d[at:at + 3])
        new = None
        for base, (length, m) in libs.items():
            if base <= v < base + length:
                if v - base not in m:
                    raise SystemExit("a call into the library at %04x goes to %04x, not a statement" % (base, v))
                new = base + m[v - base]
        if new is None:
            if v not in own:
                raise SystemExit("a call goes to %04x, not a statement of its script" % v)
            new = own[v]
        out[at:at + 3] = enc09(new)
    return bytes(out)


# ---- AI5.EXE

# the half-width string statement (0310h): inc si / lodsb / cmp al, 6 / jne / jmp next; its draw:
# mov bx, [x] / mov dx, [y] / call pos / push si / mov cl, [colour] / call ank / pop si / mov cx, [width] /
# call advance / call after / jmp (loop)
ANK_SIG = re.compile(rb"\x46\xac\x3c\x06\x75\x03\xe9(..)\x8b\x1e(..)\x8b\x16(..)\xe8(..)\x56\x8a\x0e(..)\xe8(..)"
                     rb"\x5e\x8b\x0e(..)\xe8(..)\xe8(..)\xeb.", re.S)
# the loader (4B3Dh): test byte [flags], 2 / jne / call / jae / jmp error / ret
LOAD_SIG = re.compile(rb"\xf6\x06(..)\x02\x75\x09\xe8..\x73\x03\xe9..\xc3", re.S)
ROOM = 0x18
HELPER = """
fallthrough:
    JMPN {after}

ank:
    inc si
    cmp byte ptr [si], 0x7f
    je a1
n1:
    lodsb
    cmp al, 6
    je a3
    CALLN dr
    jmp n1
a3:
    JMPN {next}
a1:
    mov al, byte ptr [si + 1]
    shr al, 2
    mov ah, al
    mov al, byte ptr [si + 2]
    shr ax, 2
    mov bl, byte ptr [si + 3]
    mov cx, 2
a0:
    shr ax, 1
    rcr bl, 1
    loop a0
    mov ah, al
    mov al, bl
    add si, 4
    push bx
    mov bx, si
    CALLN region
    add ax, bx
    pop bx
    mov word ptr cs:[{fptr}], ax
a2:
    push ds
    push di
    mov ax, cs
    add ax, {delta}
    mov ds, ax
    mov di, word ptr cs:[{fptr}]
    mov al, byte ptr [di]
    pop di
    pop ds
    inc word ptr cs:[{fptr}]
    cmp al, 6
    je a4
    CALLN dr
    jmp a2
a4:
    inc si
    JMPN {next}

dr:
    mov bx, word ptr [{x}]
    mov dx, word ptr [{y}]
    CALLN {pos}
    push si
    mov cl, byte ptr [{colour}]
    CALLN {draw}
    pop si
    mov cx, word ptr [{width}]
    CALLN {advance}
    CALLN {after2}
    .byte 0xc3

region:
{regions}
    mov bx, 0
    .byte 0xc3

load:
    push bx
    push es
    push dx
    CALLN tramp
    pop dx
    pop es
    pop bx
    push ax
    push cx
    push si
    push di
    mov ax, es
    mov cx, ds
    cmp ax, cx
    jne l9
    mov si, dx
l1:
    cmp byte ptr [si], 0
    je l2
    inc si
    jmp l1
l2:
    sub si, 4
    cmp si, dx
    jb l9
    cmp byte ptr [si], 0x2e
    jne l9
    mov ax, word ptr [si + 1]
    or ax, 0x2020
    cmp ax, 0x656d
    jne l9
    mov al, byte ptr [si + 3]
    or al, 0x20
    cmp al, 0x73
    jne l9
    push word ptr [si + 1]
    push word ptr [si + 3]
    mov word ptr [si + 1], 0x6e65
    mov byte ptr [si + 3], 0x67
    push bx
    push es
    CALLN region
    mov ax, cs
    add ax, {delta}
    mov es, ax
    CALLN tramp
    pop es
    pop bx
    pop ax
    mov byte ptr [si + 3], al
    pop word ptr [si + 1]
l9:
    pop di
    pop si
    pop cx
    pop ax
    clc
    .byte 0xc3

tramp:
    test byte ptr [{flags}], 2
    JMPN {loadback}
"""
REGION = """    cmp bx, {lo}
    jb r{k}
    cmp bx, {hi}
    jae r{k}
    mov bx, {base}
    .byte 0xc3
r{k}:"""


def patch_exe(packed, regions):
    """Isaku's AI5.EXE, unpacked, with the helper (see the module's docstring): regions = [(first
    address, end, the English's offset)] of the libraries (a scene's English at 0)."""
    exe = bytearray(exepack.unpack(packed)) if exepack.is_packed(packed) else bytearray(packed)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    img = bytearray(exe[hdr:])
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    nxt = min(s for s in segs if s > code_seg)
    split = nxt * 16
    seg = bytearray(img[code_seg * 16:split])
    am, lm = list(ANK_SIG.finditer(seg)), list(LOAD_SIG.finditer(seg))
    if len(am) != 1 or len(lm) != 1:
        raise SystemExit("AI5.EXE: the half-width string or the loader is found %d / %d times, not once" % (
            len(am), len(lm)))
    a0, l0 = am[0].start(), lm[0].start()
    u = lambda g: hex(struct.unpack("<H", g)[0])
    rel = lambda at, g: hex((at + struct.unpack("<h", g)[0]) & 0xFFFF)
    at = len(seg)
    end = at + ROOM * 16
    fptr = end - 2
    # (the English segment: past the program's memory, grown by 64 KB for it; the helper's room before)
    image_paras = (len(img) + ROOM * 16 + 15) // 16
    minalloc = struct.unpack_from("<H", exe, 0x0A)[0]
    delta = image_paras + minalloc - code_seg
    regs = "\n".join(REGION.format(k=k, lo=hex(lo), hi=hex(hi), base=hex(base)) for k, (lo, hi, base) in enumerate(regions))
    src = HELPER.format(after=hex(end), fptr=hex(fptr), delta=hex(delta),
                        x=u(am[0].group(2)), y=u(am[0].group(3)), pos=rel(a0 + 0x14, am[0].group(4)),
                        colour=u(am[0].group(5)), draw=rel(a0 + 0x1C, am[0].group(6)), width=u(am[0].group(7)),
                        advance=rel(a0 + 0x24, am[0].group(8)), after2=rel(a0 + 0x27, am[0].group(9)),
                        next=rel(a0 + 9, am[0].group(1)), regions=regs, flags=u(lm[0].group(1)),
                        loadback=hex(l0 + 5))
    code, labels = _asm16(src, at, ("ank", "load"))
    if len(code) > ROOM * 16 - 2:
        raise SystemExit("AI5.EXE: the helper is %d bytes, the room %d" % (len(code), ROOM * 16 - 2))
    for s, n, lab in ((a0, 9, "ank"), (l0, 5, "load")):
        if any(code_seg * 16 + s - 1 <= f < code_seg * 16 + s + n for f in fixups):
            raise SystemExit("AI5.EXE: a segment fixup falls in a patched range")
        seg[s:s + n] = b"\xe9" + struct.pack("<H", (labels[lab] - (s + 3)) & 0xFFFF) + b"\x90" * (n - 3)
    img[code_seg * 16:split] = seg
    out = bytearray(_move_up(bytes(exe), hdr, img, fixups, rel_at, nxt, ROOM, code, "AI5.EXE", split))
    struct.pack_into("<H", out, 0x0A, minalloc + 0x1000)
    return bytes(out)


def libraries(store):
    """{NAME.MES: the address it is loaded at} of the scripts loaded at a fixed address (1Ch, the
    name, a 09h number)."""
    out = {}
    for _name, path in store.items:
        for m in re.finditer(rb"\x04\x1c\x06([!-~]+\.mes)\x06\x02\x09(...)", store.read(path), re.I | re.S):
            out[m.group(1).decode("ascii").upper()] = dec09(m.group(2))
    return out


def _build(d, values, warn, ids, name):
    if not values:
        return d, b"", {t[1]: t[1] for t in ai5.tokenize(d)}
    new = ai5.rebuild(d, values, warn, ids, name)
    script, blob = far_strings(new)
    return script, blob, offset_map(d, script)


def patch_scripts(store, by_ref, ids, warn, mode):
    """Every script rebuilt with its English kept out of it (see the module's docstring); returns
    (scripts rebuilt, the libraries' English regions for patch_exe)."""
    libs = libraries(store)
    order = sorted(libs.values())
    slots = {base: (order[k + 1] if k + 1 < len(order) else ai5.SCRIPT_ROOM) - base for k, base in enumerate(order)}
    built = {}
    for name, path in store.items:
        d = store.read(path)
        values = {a: t for (f, a), t in by_ref.items() if f == name}
        built[name] = [path, d, values, libs.get(name.split("/")[-1].upper())] + list(_build(d, values, warn, ids, name))
    # (the English segment: each library's English after the scene's, the scene's room what is left)
    lib_eng = {}
    for path, d, values, base, script, blob, m in built.values():
        if base is not None:
            lib_eng[base] = max(lib_eng.get(base, 0), len(blob) + 1)
    scene_room = 0x10000 - sum(lib_eng.values())
    regions, at = [], scene_room
    for base in order:
        if base in lib_eng:
            regions.append((base, base + slots[base], at))
            at += lib_eng[base]
    for name, b in built.items():
        path, d, values, base, script, blob, m = b
        if base is None and len(blob) + 1 > scene_room:
            if mode != "pseudo":
                raise SystemExit("%s: its English takes %d bytes, the English segment has room for %d; "
                                 "shorten these strings: %s" % (name, len(blob) + 1, scene_room,
                                                                 ", ".join(sorted({ids[(name, a)] for a in values}))))
            # (the --pseudo filler: every string cut in proportion until the English fits)
            cut = 0
            while len(blob) + 1 > scene_room:
                total = sum(len(v) for v in values.values())
                ratio = max(0.0, 1 - (len(blob) + 1 - scene_room) * 1.1 / max(1, total))
                for a in values:
                    v = values[a]
                    keep = max(min(len(v), 4), int(len(v) * ratio))
                    while keep < len(v) and "{" in v[:keep] and "}" not in v[v.rindex("{", 0, keep):keep]:
                        keep += 1
                    values[a] = v[:keep]
                after = sum(len(v) for v in values.values())
                if after == total:
                    raise SystemExit("%s: the English does not fit even with its filler cut" % name)
                cut += total - after
                script, blob, m = _build(d, values, [], ids, name)
            warn.append("%s: the filler was cut by %d letters to fit the English segment" % (name, cut))
            b[4:7] = [script, blob, m]
    lib_maps = {b[3]: (len(b[1]), b[6]) for b in built.values() if b[3] is not None}
    done = 0
    for name, (path, d, values, base, script, blob, m) in built.items():
        own = m if base is None else {base + k: base + v for k, v in m.items()}
        script = remap(script, own, lib_maps)
        room = slots[base] if base is not None else LIBRARY_START
        if len(script) > room:
            raise SystemExit("%s: %d bytes, its room %d" % (name, len(script), room))
        if script != d:
            ai5.tokenize(script)
            store.write(path, script)
            done += 1
        if isinstance(path, tuple):
            store.write((path[0], path[1].rsplit(".", 1)[0] + ".ENG"), blob + b"\x06")
    return done, regions
