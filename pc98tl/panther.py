"""Panther Software's Hamlet (1994): HAM.EXE and its scenes (.P, .CMN), as D.O. sold it.

Text is Shift-JIS, drawn 16x16 from the character ROM into the graphics planes through the GRCG.

* The scenes are overlays of code (the engine reads one whole into its overlay segment, at offset 0,
  and runs it): they call the engine through int 1Eh (ax: the function).  A scene's strings sit
  among its code, NUL-ended; a message is shown by mov si, offset / mov bx, the face / mov ax, 5 /
  int 1Eh (function 5: HAM.EXE 9D1Ah), its offset an immediate of the mov si.
* The message routines (9D1Ah, and 9F2Ah's at a window of its own) draw pages of 5 lines of 23
  characters: two bytes a character (A0ADh draws one: the GRCG on in the colour dx, the glyph from
  the character ROM, bold cl dots, 16 rows), 0Dh a new line, 00 the end; after a page, a key wait
  and the window cleared.
* A string routine (A07Ch: es:bx, the colour dx, bold cl) draws at di, skipping bytes under 81h.
* HAM.EXE's own strings (the weapons' names in fixed slots, the menus, the disk prompts, the items'
  descriptions) are in its data segment: a message named by a mov si, a menu's label by a mov bx
  before a call of the string routine.
* START.BIN and START2.BIN are scenes as the .P are.
* HOPEN.EXE (the opening) has its text in its data segment (opening_text): a glossary page (strings
  one after another, mov si naming the first, each drawn a character at a time by 2105h at a di of the
  code's), records (a word di, then the string; mov si naming the first, mov cx their count, for
  3402h's story pages, revealed by 3325h, and 2D11h's character names, drawn into the box their card
  moves with) and three mode labels (mov dx, for the string routine 145Ch).

The patch (patch_ham): a helper put in at the end of HAM.EXE's code segment (pc98tl/adl5.py
_move_up):

* In the message routines a byte from 20h to 7Fh is a half-width letter: drawn 8 dots wide from the
  BIOS 8x16 font, bold as the routine's characters, two to a character's place in the line's count;
  a full-width character after an odd number of them starts on the next column.  The English is
  wrapped by the patcher between words with 0Dh (a line of 46 letters, one short so that a full line
  never leaves an empty one).
* The string routine draws a byte from 20h to 7Fh the same way.
* HAM.EXE's messages and labels longer than their own bytes go in room put in after its data segment
  (grow_data; the segments from the next on moved up).
* HOPEN.EXE (patch_hopen): its character loops, the reveal and its string routine draw a byte from 20h
  to 7Fh 8 dots wide the same way; its text is rebuilt in room put in after its data segment.
* The overlay segment grows to the largest scene as built (the work segments after it, past the
  image, move up; the memory the program asks for with them): a scene may take 65535 bytes.
"""
import re
import struct

from .adl import _asm16, _call_target, _code_end
from .adl5 import _move_up

ROOM = 0x18
OVERLAY_MAX = 0xFFFF            # the loader's read: cx = FFFFh

# a message loop's character (9D6Fh): cmp bh, 0Dh / je (new line) / mov bl, [si] / mov cl, 2 / mov dx, bp /
# call a / call draw / call b / mov ax, 3 / int 33h / or bx, bx / jne / call wait / pop cx / inc si /
# add di, 2 / loop (the line's next) / jmp (past the line)
MSG_SIG = re.compile(rb"\x80\xff\x0d\x74(.)\x8a\x1c\xb1\x02\x8b\xd5\xe8(..)\xe8(..)\xe8(..)\xb8\x03\x00\xcd\x33"
                     rb"\x0b\xdb\x75\x03\xe8(..)\x59\x46\x83\xc7\x02\xe2(.)\xeb\x01", re.S)
# the string routine's loop (A0E5h): mov dh, es:[bx] / inc bx / or dh, dh / je / cmp dh, 81h / jb (the loop)
STR_SIG = re.compile(rb"\x26\x8a\x37\x43\x0a\xf6\x74.\x80\xfe\x81\x72(.)", re.S)
# the character draw (A0ADh) after its frame: mov [bp-15h], cl / call wait1 / mov cx, 14h / loop / call a /
# call wait2 / mov ax, dx / call grcg on
DRAW_SIG = re.compile(rb"\x88\x4e\xeb\xe8(..)\xb9\x14\x00\xe2\xfe\xe8(..)\xe8(..)\x8b\xc2\xe8(..)", re.S)
# the GRCG off: push ax / xor al, al / out 7Ch, al / pop ax / ret
GRCG_OFF_SIG = re.compile(rb"\x50\x32\xc0\xe6\x7c\x58\xc3", re.S)
# the overlay loader: mov cx, FFFFh / mov dx, 0 / push seg / pop ds
LOADER_SIG = re.compile(rb"\xb9\xff\xff\xba\x00\x00\x68(..)\x1f", re.S)

MSG_PART = """
msg{k}:
    cmp bh, 0x0d
    jne m1{k}
    mov byte ptr cs:[{half}], 0
    JMPN {newline}
m1{k}:
    cmp bh, 0x80
    jae m2{k}
    cmp bh, 0x20
    jb m2{k}
    mov al, bh
    mov dx, bp
    mov cl, 2
    CALLN {a}
    CALLN ankframe
    CALLN {b}
    mov ax, 3
    int 0x33
    or bx, bx
    jne m3{k}
    CALLN {wait}
m3{k}:
    pop cx
    inc di
    xor byte ptr cs:[{half}], 1
    jz m4{k}
    inc cx
m4{k}:
    dec cx
    jz m5{k}
    JMPN {loop}
m5{k}:
    mov byte ptr cs:[{half}], 0
    JMPN {past}
m2{k}:
    cmp byte ptr cs:[{half}], 0
    je m6{k}
    mov byte ptr cs:[{half}], 0
    inc di
m6{k}:
    JMPN {dbl}
"""
HELPER = """
fallthrough:
    JMPN {after}

{msgparts}
strhook:
    cmp dh, 0x81
    jae s1
    cmp dh, 0x20
    jb s2
    mov al, dh
    mov cl, byte ptr [bp - 0x15]
    CALLN ank
    inc di
s2:
    JMPN {strloop}
s1:
    JMPN {strnext}

ankframe:
    push ax
    push cx
    CALLN {wait1}
    mov cx, 0x14
af1:
    loop af1
    CALLN {wait2}
    pop cx
    pop ax
    push ax
    mov ax, dx
    CALLN {grcgon}
    pop ax
    CALLN ank
    CALLN {grcgoff}
    .byte 0xc3

ank:
    pusha
    push ds
    push es
    push cx
    mov dl, al
    mov dh, 0x80
    mov bx, cs
    mov cx, {glyph}
    mov ah, 0x14
    int 0x18
    pop cx
    xor ch, ch
    or cx, cx
    jnz a0
    inc cx
a0:
    mov ax, 0xa800
    mov es, ax
    push cs
    pop ds
    mov si, {glyph2}
    mov bx, 16
a1:
    lodsb
    xor ah, ah
    push cx
a2:
    or ah, al
    shl al, 1
    loop a2
    pop cx
    mov byte ptr es:[di], ah
    add di, 0x50
    dec bx
    jnz a1
    pop es
    pop ds
    popa
    .byte 0xc3
"""


def _one(seg, sig, what, name="HAM.EXE"):
    found = list(sig.finditer(seg))
    if len(found) != 1:
        raise SystemExit("%s: the %s signature is found %d times, not once" % (name, what, len(found)))
    return found[0]


def _image(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    return hdr, rel_at, fixups


def data_segment(exe):
    """A program's data segment: the first segment the relocations name past the code's."""
    hdr, rel_at, fixups = _image(exe)
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    return min(v for v in (struct.unpack_from("<H", exe, hdr + f)[0] for f in fixups) if v > code_seg)


def string_routine(exe):
    """The string routine's entry (an offset in the code segment): the push bp / mov bp, sp before the
    one call into the string loop (A07Ch)."""
    hdr, rel_at, fixups = _image(exe)
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    seg = exe[hdr + code_seg * 16:hdr + data_segment(exe) * 16]
    loop = _one(seg, STR_SIG, "string loop").start()
    calls = [k for k in range(max(0, loop - 0x100), loop) if seg[k] == 0xE8
             and 0 <= loop - (k + 3 + struct.unpack_from("<h", seg, k + 1)[0]) <= 4]
    if len(calls) != 1:
        raise SystemExit("HAM.EXE: the string routine's call into its loop is found %d times, not once" % len(calls))
    entry = seg.rfind(b"\x55\x8b\xec", 0, calls[0])
    if entry < 0:
        raise SystemExit("HAM.EXE: the string routine's entry is not found")
    return entry


def grow_data(exe, blob, name="HAM.EXE"):
    """(the program with blob put in at the end of its data segment, before the next segment the relocations
    name (those from it on moved up), blob's offset in the data segment)."""
    hdr, rel_at, fixups = _image(exe)
    ds = data_segment(exe)
    nxt = min(v for v in (struct.unpack_from("<H", exe, hdr + f)[0] for f in fixups) if v > ds)
    at = (nxt - ds) * 16
    if at + len(blob) > 0x10000:
        raise SystemExit("%s: its strings take %d bytes past the data segment, room for %d; shorten them"
                         % (name, len(blob), 0x10000 - at))
    img = bytearray(exe[hdr:])
    # (HOPEN.EXE's file ends 10 bytes short of the next segment: the rest of the data segment zeroes)
    img += bytes(max(0, nxt * 16 - len(img)))
    out = _move_up(exe, hdr, img, fixups, rel_at, nxt, -(-len(blob) // 16), blob, name)
    return out, at


def overlay_room(exe):
    """(the overlay segment, the next segment past it) as the program has them."""
    hdr, rel_at, fixups = _image(exe)
    img = exe[hdr:]
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    # (two loaders, the scenes' and the opening's, into the same segment)
    lds = {struct.unpack("<H", m.group(1))[0]
           for m in LOADER_SIG.finditer(img[code_seg * 16:segs[[s > code_seg for s in segs].index(True)] * 16])}
    if len(lds) != 1:
        raise SystemExit("HAM.EXE: the overlay loaders are not found, or not into one segment")
    ov = lds.pop()
    nxt = min(s for s in segs if s > ov)
    return ov, nxt


def patch_ham(exe, overlay_size=0):
    """HAM.EXE with the half-width helper; overlay_size: the largest scene as built (the segments past
    the overlay segment moved up for it when it outgrows its room)."""
    if exe[:2] != b"MZ":
        raise SystemExit("HAM.EXE: not an MZ program")
    hdr, rel_at, fixups = _image(exe)
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    cs0 = code_seg * 16
    next_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > code_seg)
    split = _code_end(img, next_seg * 16, "HAM.EXE")
    seg = bytearray(img[cs0:split])
    msgs = list(MSG_SIG.finditer(seg))
    if len(msgs) != 2:
        raise SystemExit("HAM.EXE: the message loops' signature is found %d times, not twice" % len(msgs))
    at = len(seg)
    half, glyph = at + ROOM * 16 - 0x14, at + ROOM * 16 - 0x12
    m0 = msgs[0]
    a = _call_target(seg, m0.start() + 11)
    draw = _call_target(seg, m0.start() + 14)
    b = _call_target(seg, m0.start() + 17)
    wait = _call_target(seg, m0.start() + 29)
    parts = ""
    for k, m in enumerate(msgs):
        s0 = m.start()
        parts += MSG_PART.format(k=k + 1, half=hex(half), newline=hex(s0 + 5 + struct.unpack("b", m.group(1))[0]),
                                 loop=hex(s0 + 39 + struct.unpack("b", m.group(6))[0]), past=hex(s0 + 42),
                                 dbl=hex(s0 + 5), a=hex(a), b=hex(b), wait=hex(wait))
    d = DRAW_SIG.search(seg, draw, draw + 0x20)
    if not d:
        raise SystemExit("HAM.EXE: the character draw is not laid out as expected")
    wait1 = _call_target(seg, d.start() + 3)
    wait2 = _call_target(seg, d.start() + 11)
    grcgon = _call_target(seg, d.start() + 19)
    grcgoff = _one(seg, GRCG_OFF_SIG, "GRCG off").start()
    st = _one(seg, STR_SIG, "string loop")
    strloop = st.start()
    strnext = st.start() + 13
    src = HELPER.replace("{msgparts}", parts).format(
        after=hex(at + ROOM * 16), half=hex(half), wait1=hex(wait1), wait2=hex(wait2), grcgon=hex(grcgon),
        grcgoff=hex(grcgoff), strloop=hex(strloop), strnext=hex(strnext), glyph=hex(glyph), glyph2=hex(glyph + 2))
    code, labels = _asm16(src, at, ("msg1", "msg2", "strhook"))
    if len(code) > ROOM * 16 - 0x14:
        raise SystemExit("HAM.EXE: the helper is %d bytes, the room %d" % (len(code), ROOM * 16 - 0x14))
    room = code
    for m, lab in zip(msgs, ("msg1", "msg2")):
        s = m.start()
        seg[s:s + 5] = b"\xe9" + struct.pack("<H", (labels[lab] - (s + 3)) & 0xFFFF) + b"\x90\x90"
    s = st.start() + 8
    seg[s:s + 5] = b"\xe9" + struct.pack("<H", (labels["strhook"] - (s + 3)) & 0xFFFF) + b"\x90\x90"
    for lo, n in [(m.start(), 5) for m in msgs] + [(s, 5)]:
        if any(cs0 + lo - 1 <= f < cs0 + lo + n for f in fixups):
            raise SystemExit("HAM.EXE: a segment fixup falls in a patched range")
    img[cs0:cs0 + len(seg)] = seg
    out = bytearray(_move_up(exe, hdr, img, fixups, rel_at, next_seg, ROOM, bytes(room), "HAM.EXE", split))
    # (the overlay segment grown: the segments past it, beyond the image, moved up)
    ov, nxt = overlay_room(bytes(out))
    need = -(-overlay_size // 16) - (nxt - ov)
    if overlay_size > OVERLAY_MAX:
        raise SystemExit("a scene of %d bytes; the engine reads at most 65535" % overlay_size)
    if need > 0:
        hdr2, rel2, fix2 = _image(bytes(out))
        for f in fix2:
            v = struct.unpack_from("<H", out, hdr2 + f)[0]
            if v >= nxt:
                struct.pack_into("<H", out, hdr2 + f, v + need)
        ss = struct.unpack_from("<H", out, 0x0E)[0]
        if ss >= nxt:
            struct.pack_into("<H", out, 0x0E, ss + need)
        struct.pack_into("<H", out, 0x0A, struct.unpack_from("<H", out, 0x0A)[0] + need)
    return bytes(out)


# HOPEN.EXE, the opening: its text in its data segment, drawn 16x16 from the character ROM.
# a character loop's pair (2105h, 2D11h, 3402h): mov dh, al / lodsb / mov dl, al (then its setup and the call
# of the character draw, 217Ch)
OPEN_CHAR_SIG = re.compile(rb"\x8a\xf0\xac\x8a\xd0")
# the reveal's loop (3329h): lodsb / or al, al / je / lodsb / push si / push di / push ds / push es /
# mov ax, delay / call wait / mov ax, from / mov ds, ax / mov ax, to / mov es, ax / mov si, di /
# mov dx, 4Eh / mov cx, 10h / movsw / add si, dx / add di, dx / loop / pop es / pop ds / pop di / add di, 2 /
# pop si / call done / jmp (the loop)
OPEN_REVEAL_SIG = re.compile(rb"\xac\x0a\xc0\x74.\xac\x56\x57\x1e\x06\xb8(..)\xe8(..)\xb8(..)\x8e\xd8\xb8(..)"
                             rb"\x8e\xc0\x8b\xf7\xba\x4e\x00\xb9\x10\x00\xa5\x03\xf2\x03\xfa\xe2\xf9\x07\x1f\x5f"
                             rb"\x83\xc7\x02\x5e\xe8(..)\xeb.", re.S)
# the GRCG on in the colour dl (2245h): mov al, C0h / out 7Ch, al / xor al, al / shr dl, 1 / jae / not al /
# out 7Eh, al
OPEN_GRCG_SIG = re.compile(rb"\xb0\xc0\xe6\x7c\x32\xc0\xd0\xea\x73\x02\xf6\xd0\xe6\x7e")
OPEN_ROOM = 0x14

OPEN_CHAR_PART = """
ch{k}:
    cmp al, 0x80
    jae c1{k}
    cmp al, 0x20
    jb c1{k}
    {setup}
    CALLN ankdraw
    JMPN {next}
c1{k}:
    mov dh, al
    lodsb
    mov dl, al
    JMPN {back}
"""
OPEN_HELPER = """
fallthrough:
    JMPN {after}

{charparts}
reveal:
    cmp al, 0x80
    jae r1
    cmp al, 0x20
    jb r1
    push si
    push di
    push ds
    push es
    mov ax, {delay}
    CALLN {wait}
    mov ax, {src}
    mov ds, ax
    mov ax, {dst}
    mov es, ax
    mov si, di
    mov dx, 0x4f
    mov cx, 0x10
r2:
    movsb
    add si, dx
    add di, dx
    loop r2
    pop es
    pop ds
    pop di
    inc di
    pop si
    CALLN {done}
    JMPN {top}
r1:
    lodsb
    push si
    push di
    JMPN {back}

strhook:
    cmp dh, 0x81
    jae s1
    cmp dh, 0x20
    jb s2
    mov al, dh
    mov cl, 1
    CALLN ank
    inc di
s2:
    JMPN {strloop}
s1:
    JMPN {strnext}

ankdraw:
    pusha
    push ax
    mov dl, cl
    CALLN {grcg}
    pop ax
    mov cl, 1
    or bl, bl
    jz ad1
    inc cl
ad1:
    CALLN ank
    xor al, al
    out 0x7c, al
    popa
    inc di
    .byte 0xc3
""" + HELPER[HELPER.index("ank:"):]


def _call_to(seg, at):
    return (at + 3 + struct.unpack_from("<h", seg, at + 1)[0]) & 0xFFFF


def _card_box(seg, at):
    """(left column, width) of the box a character's card moves with, its name drawn into it (call at the
    card's move: a call in its first bytes saves the box, mov si, the box's top left / mov bx, its width in bytes),
    or None."""
    if seg[at] != 0xE8:
        return None
    move = _call_to(seg, at)
    for j in range(move, move + 0x10):
        if seg[j] == 0xE8:
            save = _call_to(seg, j)
            if seg[save] == 0xBE and seg[save + 3] == 0xBB:
                return (struct.unpack_from("<H", seg, save + 1)[0] % 80, struct.unpack_from("<H", seg, save + 4)[0])
    return None


def opening_text(exe):
    """HOPEN.EXE's text: [{"kind": "records" (word di, then the string, count of them), "lines" (strings one
    after another, each at a di of the code's) or "string" (one, es:bx for the string routine), "refs":
    [the file offsets of the immediates naming it], "items": [(di or None, start, end past the 00)]}]."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    ds = data_segment(exe)
    base = hdr + ds * 16
    seg = exe[hdr:base]
    sites = [m.start() for m in OPEN_CHAR_SIG.finditer(seg)]
    # (the record loops: push cx / lodsw / mov di, ax; the line routines: a character loop's pair soon after)
    entries = {}
    for k in range(len(seg) - 3):
        if seg[k] != 0xE8:
            continue
        t = _call_to(seg, k)
        if seg[t:t + 4] == b"\x51\xad\x8b\xf8":
            entries[t] = "records"
        elif any(0 < s - t < 0x10 for s in sites):
            entries[t] = "lines"
    st = _one(seg, STR_SIG, "string loop", "HOPEN.EXE").start()
    strfn = {_call_to(seg, k) for k in range(len(seg) - 3) if seg[k] == 0xE8 and 0 < st - _call_to(seg, k) < 0x40}
    if len(strfn) != 1:
        raise SystemExit("HOPEN.EXE: the string routine's entry is not found")
    strfn = strfn.pop()
    blocks = {}
    for k in range(len(seg) - 3):
        if seg[k] == 0xBE:
            # (mov si, the text / ... / call a record loop or a line routine)
            calls = [j for j in range(k + 3, min(k + 14, len(seg) - 3)) if seg[j] == 0xE8 and _call_to(seg, j) in entries]
            if not calls:
                continue
            t = _call_to(seg, calls[0])
            off = struct.unpack_from("<H", seg, k + 1)[0]
            if entries[t] == "records":
                m = re.search(rb"\xb9(.)\x00", seg[k + 3:calls[0]], re.S)
                if not m:
                    continue
                count = m.group(1)[0]
            else:
                # (the routine's calls before the next mov si or ret)
                count, j = 0, calls[0]
                while j < len(seg) - 3 and seg[j] not in (0xBE, 0xC3):
                    if seg[j] == 0xE8 and _call_to(seg, j) == t:
                        count += 1
                        j += 3
                        continue
                    j += 1
            b = blocks.setdefault(off, {"kind": entries[t], "refs": [], "count": count})
            b["refs"].append(hdr + k + 1)
            b["count"] = max(b["count"], count)
            if entries[t] == "records" and _card_box(seg, calls[0] + 3):
                b["box"] = _card_box(seg, calls[0] + 3)
        elif seg[k] == 0xBA:
            # (mov dx, the text / ... / call the string routine, es the data segment)
            calls = [j for j in range(k + 3, min(k + 12, len(seg) - 3)) if seg[j] == 0xE8 and _call_to(seg, j) == strfn]
            if calls:
                off = struct.unpack_from("<H", seg, k + 1)[0]
                b = blocks.setdefault(off, {"kind": "string", "refs": [], "count": 1})
                b["refs"].append(hdr + k + 1)
    out = []
    for off, b in sorted(blocks.items()):
        p, items = base + off, []
        for _n in range(b["count"]):
            di = None
            if b["kind"] == "records":
                di = struct.unpack_from("<H", exe, p)[0]
                p += 2
            e = exe.index(0, p) + 1
            items.append((di, p, e))
            p = e
        out.append({"kind": b["kind"], "refs": b["refs"], "items": items, "offset": off, "box": b.get("box")})
    return out


def patch_hopen(exe):
    """HOPEN.EXE with the half-width helper: its character loops, the reveal and the string routine draw a
    byte from 20h to 7Fh 8 dots wide from the BIOS 8x16 font."""
    if exe[:2] != b"MZ":
        raise SystemExit("HOPEN.EXE: not an MZ program")
    hdr, rel_at, fixups = _image(exe)
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    cs0 = code_seg * 16
    next_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > code_seg)
    split = _code_end(img, next_seg * 16, "HOPEN.EXE")
    seg = bytearray(img[cs0:split])
    at = len(seg)
    glyph = at + OPEN_ROOM * 16 - 0x12
    draw = None
    parts, sites = "", []
    for k, m in enumerate(OPEN_CHAR_SIG.finditer(seg)):
        s = m.start()
        c = seg.find(b"\xe8", s + 5, s + 12)
        if c < 0:
            raise SystemExit("HOPEN.EXE: a character loop is not laid out as expected")
        if draw is None:
            draw = _call_to(seg, c)
        elif _call_to(seg, c) != draw:
            raise SystemExit("HOPEN.EXE: the character loops call different draws")
        setup = ".byte " + ", ".join(hex(v) for v in seg[s + 5:c]) if c > s + 5 else ""
        parts += OPEN_CHAR_PART.format(k=k, setup=setup, next=hex(c + 3), back=hex(s + 5))
        sites.append((s, "ch%d" % k))
    rv = _one(seg, OPEN_REVEAL_SIG, "reveal", "HOPEN.EXE")
    r0 = rv.start()
    gr = _one(seg, OPEN_GRCG_SIG, "GRCG", "HOPEN.EXE").start()
    st = _one(seg, STR_SIG, "string loop", "HOPEN.EXE")
    u = lambda g: hex(struct.unpack("<H", g)[0])
    src = OPEN_HELPER.replace("{charparts}", parts).format(
        after=hex(at + OPEN_ROOM * 16), delay=u(rv.group(1)), wait=hex(_call_to(seg, r0 + 13)), src=u(rv.group(3)),
        dst=u(rv.group(4)), done=hex(_call_to(seg, r0 + 48)), top=hex(r0), back=hex(r0 + 8), strloop=hex(st.start()),
        strnext=hex(st.start() + 13), grcg=hex(gr), glyph=hex(glyph), glyph2=hex(glyph + 2))
    code, labels = _asm16(src, at, [lab for _s, lab in sites] + ["reveal", "strhook"])
    if len(code) > OPEN_ROOM * 16 - 0x14:
        raise SystemExit("HOPEN.EXE: the helper is %d bytes, the room %d" % (len(code), OPEN_ROOM * 16 - 0x14))
    hooks = [(s, 5, lab) for s, lab in sites] + [(r0 + 5, 3, "reveal"), (st.start() + 8, 5, "strhook")]
    for s, n, lab in hooks:
        if any(cs0 + s - 1 <= f < cs0 + s + n for f in fixups):
            raise SystemExit("HOPEN.EXE: a segment fixup falls in a patched range")
        seg[s:s + n] = b"\xe9" + struct.pack("<H", (labels[lab] - (s + 3)) & 0xFFFF) + b"\x90" * (n - 3)
    img[cs0:cs0 + len(seg)] = seg
    return _move_up(exe, hdr, img, fixups, rel_at, next_seg, OPEN_ROOM, code, "HOPEN.EXE", split)
