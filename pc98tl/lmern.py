"""Panther Software's Lesser Mern (1994): LESS.EXE and its maps' scripts (MDTnnn), as D.O. sold it.

Text is Shift-JIS, drawn 16x16 from the character ROM into the graphics planes through the GRCG.

* LESS.EXE's data segment (0EA3h) holds the game's own text (monsters, items, magic, battle and system
  messages, menus: NUL-ended strings, many lists walked by counting their NULs, item records a name and
  its numbers) and, from B4D8h, the map's script: MDTnnn read whole there, its first 32 words and the
  speaker names' table (header word 8: a count, then the names' offsets) made addresses by adding B4D8h.
  A script's messages are inline in its events (an event's bytes, then a message to its 00) and in
  tables of them.
* Messages go through one routine (2167h): a copier (2299h) builds the message into a buffer (1C96h,
  810 bytes), a byte under 11h a control (01, 04-06, 09, 0B-0F with one byte after it: 0Bh n the
  speaker's name, copied two bytes at a time), a byte from 11h a character (two bytes, a space one);
  then the window's routine draws it a character at a time (1FD7h), its line's room counted in bytes,
  a new line where it runs out (or at 0Ah) and a key wait when the window is full.
* A string routine (E82Eh) draws a NUL-ended string, two bytes a character, at di (menus, names).

The patch (patch_less):

* Room: the data segment grows to 64 KB (the segments after it move up); the buffer moves to its last
  2 KB (BUF), and a script may take what is left from B4D8h (MDT_MAX).  A segment of the game's
  English (the program's strings' continuations) is put in after the data segment.
* A helper put in at the end of the code segment (pc98tl/adl5.py _move_up).  The copier, the window and
  the string routine:
  - draw (or copy) a byte under 80h as one byte, a half-width letter drawn 8 dots wide from the BIOS
    8x16 font, bold where the program's characters are, in the caller's colour, one byte of room;
  - skip 7Eh (filler);
  - follow 7Fh lo hi (go on at that offset of the data segment) and 7Ch lo hi (of the English
    segment), coming back after it at 7Dh: a string keeps its own bytes (and the lists their
    layout) with its English going on elsewhere.
  The window's line breaks between words (a word that would not fit what is left of the line starts a
  new line; a space at a line's start is not drawn; a full-width character with one byte left starts a
  new line); the copier never overruns the buffer (what would pass its end is dropped).
"""
import re
import struct

from .adl import _asm16, _call_target, _code_end
from .adl5 import _move_up
from .panther import HELPER as _PANTHER_HELPER

MDT_BASE = 0xB4D8
BUF = 0xF800                    # the new buffer: the data segment's last 2 KB
BUF_SIZE = 0x800
MDT_MAX = BUF - MDT_BASE        # a script with its English
ROOM = 0x24

# the message routine (2167h): push ds / push es / call copier / push si / mov ax, data / mov ds, ax /
# mov es, ax / mov si, buffer / xor ah, ah / lodsb / or al, al / je / cmp al, 11h / jae / dec al / shl ax, 1 /
# mov bx, table / add bx, ax / mov ax, cs:[bx] / call ax / jmp / dec si / call char / dec [room] /
# dec [room] / jne / cmp byte [si], 0Ah / jne / inc si / call newline / jmp
DRAW_SIG = re.compile(rb"\x1e\x06\xe8(..)\x56\xb8(..)\x8e\xd8\x8e\xc0\xbe(..)\x32\xe4\xac\x0a\xc0\x74.\x3c\x11"
                      rb"\x73.\xfe\xc8\xd1\xe0\xbb..\x03\xd8\x2e\x8b\x07\xff\xd0\xeb.\x4e\xe8(..)\xff\x0e(..)"
                      rb"\xff\x0e..\x75.\x80\x3c\x0a\x75\x01\x46\xe8(..)\xeb.", re.S)
# the copier (2299h): push ds / push es / mov ax, data / mov es, ax / mov di, buffer / lodsb / or al, al /
# je / cmp al, 11h / jae / ... call cs:[bx] / jmp / stosb / cmp al, 20h / je / movsb / jmp / stosb /
# pop es / pop ds / ret
COPY_SIG = re.compile(rb"\x1e\x06\xb8..\x8e\xc0\xbf(..)\xac\x0a\xc0\x74.\x3c\x11\x73.\x32\xff\x8a\xd8\xfe\xcb"
                      rb"\x03\xdb\x81\xc3..\x2e\xff\x17\xeb.\xaa\x3c\x20\x74.\xa4\xeb.\xaa\x07\x1f\xc3", re.S)
# the window's character (1FD7h): call delay / mov ax, [lines] / ... / mov dh, es:[si] / inc si /
# mov dl, es:[si] / inc si / mov di, [pos] / mov cl, [colour] / call draw / mov [pos], di / call tick / ret
CHAR_SIG = re.compile(rb"\xe8(..)\xa1..\x48\x75.\x80\x3e..\x03\x73.\x33\xdb.{0,48}?\x26\x8a\x34\x46\x26\x8a"
                      rb"\x14\x46\x8b\x3e(..)\x8a\x0e(..)\xe8..\x89\x3e..\xe8(..)\xc3", re.S)
# the string routine's character (E84Fh): lodsb / mov dh, al / or al, al / je / lodsb / mov dl, al /
# push si / push di
STR_SIG = re.compile(rb"\xac\x8a\xf0\x0a\xc0\x74.\xac\x8a\xd0\x56\x57", re.S)
# the GRCG on in the colour dl: mov al, C0h / out 7Ch, al / xor al, al / shr dl, 1 / jae / not al / out 7Eh, al
GRCG_SIG = re.compile(rb"\xb0\xc0\xe6\x7c\x32\xc0\xd0\xea\x73\x02\xf6\xd0\xe6\x7e")

# (an escape: 7Fh/7Ch lo hi go on at the offset, 7Dh back, 7Eh skipped; {p} the routine's variables'
# prefix, {back} where to go on, {setes} also es for the window)
ESCAPE = """
{p}esc:
    cmp al, 0x7e
    je {p}e9
    cmp al, 0x7d
    je {p}er
    push ax
    lodsw
    mov word ptr cs:[{p}vsi], si
    mov word ptr cs:[{p}vds], ds
    mov si, ax
    pop ax
    cmp al, 0x7f
    je {p}e9
    mov ax, cs
    add ax, {delta}
    mov ds, ax
    {setes}
    jmp {p}e9
{p}er:
    mov si, word ptr cs:[{p}vsi]
    mov ds, word ptr cs:[{p}vds]
    {setes}
{p}e9:
    JMPN {back}
"""

HELPER = """
fallthrough:
    JMPN {after}

dchar:
    cmp al, 0x80
    jb dc0
    JMPN dd0
dc0:
    cmp al, 0x7c
    jb dc1
    JMPN desc
dc1:
    cmp al, 0x20
    jne dw0
    mov bx, word ptr es:[{room}]
    cmp bx, word ptr es:[{width}]
    jne ddraw
    JMPN {loop}
dw0:
    mov ah, byte ptr [si - 2]
    cmp ah, 0x21
    jb dw1
    cmp ah, 0x7c
    jb ddraw
dw1:
    push si
    xor cx, cx
    dec si
dw2:
    mov ah, byte ptr [si]
    cmp ah, 0x21
    jb dw3
    cmp ah, 0x7c
    jae dw3
    inc cx
    inc si
    jmp dw2
dw3:
    pop si
    cmp cx, word ptr es:[{room}]
    jbe ddraw
    mov bx, word ptr es:[{room}]
    cmp bx, word ptr es:[{width}]
    je ddraw
    push ax
    push ds
    push es
    pop ds
    CALLN {newline}
    pop ds
    pop ax
ddraw:
    push ax
    push ds
    push es
    pop ds
    CALLN {delay}
    pop ds
    pop ax
    mov di, word ptr es:[{pos}]
    mov cl, byte ptr es:[{colour}]
    mov ch, 2
    CALLN ankc
    inc word ptr es:[{pos}]
    push ds
    push es
    pop ds
    CALLN {tick}
    pop ds
    dec word ptr es:[{room}]
    jz deol
    JMPN {loop}
deol:
    cmp byte ptr [si], 0x0a
    jne deol1
    inc si
deol1:
    push ds
    push es
    pop ds
    CALLN {newline}
    pop ds
    JMPN {loop}
dd0:
    cmp word ptr es:[{room}], 1
    jne dd1
    push ax
    push ds
    push es
    pop ds
    CALLN {newline}
    pop ds
    pop ax
dd1:
    dec si
    CALLN {dbl}
    JMPN {afterdbl}

copych:
    cmp al, 0x7c
    jb cc1
    cmp al, 0x80
    jae cc1
    JMPN cesc
cc1:
    cmp di, {bufend}
    jae cskip
    stosb
    cmp al, 0x80
    jb cn
    movsb
cn:
    JMPN {cploop}
cskip:
    cmp al, 0x80
    jb cn
    inc si
    JMPN {cploop}

strch:
    cmp dh, 0x80
    jae sd
    cmp dh, 0x7c
    jb sc1
    mov al, dh
    JMPN sesc
sc1:
    cmp dh, 0x20
    jb sd
    mov al, dh
    mov cx, word ptr es:[0]
    mov ch, 2
    CALLN ankc
    inc di
    JMPN {strloop}
sd:
    lodsb
    mov dl, al
    JMPN {strback}

ankc:
    pusha
    push es
    push ax
    mov dl, cl
    CALLN {grcg}
    pop ax
    mov cl, ch
    CALLN ank
    xor al, al
    out 0x7c, al
    pop es
    popa
    .byte 0xc3
{escapes}
""" + _PANTHER_HELPER[_PANTHER_HELPER.index("ank:"):]


def _image(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    return hdr, rel_at, fixups


def _one(seg, sig, what, name="LESS.EXE"):
    found = list(sig.finditer(seg))
    if len(found) != 1:
        raise SystemExit("%s: the %s signature is found %d times, not once" % (name, what, len(found)))
    return found[0]


def data_segment(exe, name="LESS.EXE"):
    """The program's data segment (the message routine's mov ax)."""
    hdr, rel_at, fixups = _image(exe)
    m = _one(exe[hdr:], DRAW_SIG, "message routine", name)
    return struct.unpack("<H", m.group(2))[0]


def patch_less(exe, english=b"", name="LESS.EXE"):
    """LESS.EXE (or ENDG.EXE, the ending, with the same routines) with room for its text (the data segment grown to 64 KB, the buffer at BUF), the English
    segment (english, its offsets those of 7Ch) after it, and the half-width helper (see the module's
    docstring)."""
    if exe[:2] != b"MZ":
        raise SystemExit("%s: not an MZ program" % name)
    if len(english) > 0xFFF0:
        raise SystemExit("%s: its strings' English takes %d bytes past their own, room for 65520" % (name, len(english)))
    hdr, rel_at, fixups = _image(exe)
    ds = data_segment(exe, name)
    segs = sorted({struct.unpack_from("<H", exe, hdr + f)[0] for f in fixups})
    nxt = min(s for s in segs if s > ds)
    eng = bytes(english) + bytes(-len(english) % 16)
    grow = 0x1000 - (nxt - ds) + len(eng) // 16
    img = bytearray(exe[hdr:])
    img += bytes(max(0, nxt * 16 - len(img)))
    room = bytes((0x1000 - (nxt - ds)) * 16) + eng
    exe = _move_up(exe, hdr, img, fixups, rel_at, nxt, grow, room, name)
    hdr, rel_at, fixups = _image(exe)
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    cs0 = code_seg * 16
    split = _code_end(img, ds * 16, name)
    seg = bytearray(img[cs0:split])
    dm = _one(seg, DRAW_SIG, "message routine", name)
    cm = _one(seg, COPY_SIG, "copier", name)
    d0, c0 = dm.start(), cm.start()
    dbl = _call_target(seg, d0 + 0x2c)
    ch = CHAR_SIG.match(seg, dbl)
    if not ch:
        raise SystemExit("%s: the window's character routine is not laid out as expected" % name)
    nl = _call_target(seg, d0 + 0x3f)
    w = re.compile(rb"\xa1(..)\xa3" + re.escape(dm.group(5)), re.S).search(seg, nl, nl + 0x40)
    if not w:
        raise SystemExit("%s: the window's width is not found" % name)
    st = _one(seg, STR_SIG, "string routine", name)
    gr = GRCG_SIG.search(seg)
    at = len(seg)
    end = at + ROOM * 16
    glyph = end - 0x12
    # (the escapes' variables: a return si and ds for each routine, before the glyph's buffer)
    var = {"c": end - 0x20, "d": end - 0x1c, "s": end - 0x18}
    # (the English segment: after the grown data segment, the helper's room before both)
    delta = ds + ROOM + 0x1000 - code_seg
    escapes = ""
    for p, back, setes in (("c", c0 + 0x0a, ""), ("d", d0 + 0x10, ""), ("s", st.start(), "")):
        escapes += ESCAPE.format(p=p, back=hex(back), setes=setes, delta=hex(delta)).replace(
            "%svsi" % p, hex(var[p])).replace("%svds" % p, hex(var[p] + 2))
    u = lambda g: hex(struct.unpack("<H", g)[0])
    src = HELPER.replace("{escapes}", escapes).format(
        after=hex(end), room=u(dm.group(5)), width=u(w.group(1)), loop=hex(d0 + 0x10), newline=hex(nl),
        delay=hex(_call_target(seg, dbl)), pos=u(ch.group(2)), colour=u(ch.group(3)),
        tick=hex(_call_target(seg, ch.end() - 4)), dbl=hex(dbl), afterdbl=hex(d0 + 0x2f),
        bufend=hex(BUF + BUF_SIZE - 4), cploop=hex(c0 + 0x0a), strloop=hex(st.start()),
        strback=hex(st.start() + 10), grcg=hex(gr.start()), glyph=hex(glyph), glyph2=hex(glyph + 2))
    code, labels = _asm16(src, at, ("dchar", "copych", "strch"))
    if len(code) > ROOM * 16 - 0x20:
        raise SystemExit("%s: the helper is %d bytes, the room %d" % (name, len(code), ROOM * 16 - 0x20))
    hooks = [(d0 + 0x2b, 4, "dchar"), (c0 + 0x24, 5, "copych"), (st.start() + 7, 3, "strch")]
    for s, n, lab in hooks:
        if any(cs0 + s - 1 <= f < cs0 + s + n for f in fixups):
            raise SystemExit("%s: a segment fixup falls in a patched range" % name)
        seg[s:s + n] = b"\xe9" + struct.pack("<H", (labels[lab] - (s + 3)) & 0xFFFF) + b"\x90" * (n - 3)
    # (the buffer moved to BUF)
    seg[d0 + 0x0e:d0 + 0x10] = struct.pack("<H", BUF)
    seg[c0 + 0x08:c0 + 0x0a] = struct.pack("<H", BUF)
    img[cs0:cs0 + len(seg)] = seg
    return _move_up(exe, hdr, img, fixups, rel_at, ds, ROOM, code, name, split)


# OPEN.EXE, the opening: a script (its VM at 6615h: a word fetched, a byte from 80h a character for the
# text screen, else a control: 20h-5Fh in classes of 16 (20h n: the cursor on n+1 cells, 30h n / 40h n:
# timing, 50h n b: a picture's frame), 00h/01h a wait, 02h lo hi a gosub, 03h its return, 05h the text
# (words of Shift-JIS to a 00 at a word's start: each character's glyph made a gaiji, the next code down
# from BCh), 06h n the codes' base, 07h n / 08h n: n codes put at the cursor (at once / one a tick),
# 09h x y the cursor (column x, row y), 0Ah / 0Dh a new line, 0Ch the window cleared, 10h-14h sounds,
# 60h-7Fh nothing).
OPEN_ARGS = {0x02: 2, 0x04: 3, 0x06: 1, 0x07: 1, 0x08: 1, 0x09: 2, 0x10: 1, 0x11: 1, 0x12: 1, 0x13: 1, 0x14: 2}
# the text's upload loop: lodsw / and al, al / je / xchg ah, al / mov dx, ax / call jis / call glyph /
# mov dl, BCh / sub dl, cl / call gaiji / dec cx / dec bx / jne
OPEN_UPLOAD_SIG = re.compile(rb"\xad\x22\xc0\x74.\x86\xc4\x8b\xd0\xe8(..)\xe8(..)\xb2\xbc\x2a\xd1\xe8..\x49\x4b\x75.", re.S)
OPEN_HELPER = """
fallthrough:
    JMPN {after}

pair:
    cmp al, 0x80
    jb p1
    xchg ah, al
    mov dx, ax
    CALLN {jis}
    CALLN {glyph}
    JMPN {back}
p1:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    push ax
    mov al, 0x0a
    out 0x68, al
    pop ax
    push ax
    mov dl, al
    mov dh, 0x80
    mov bx, cs
    mov cx, {left}
    mov ah, 0x14
    int 0x18
    pop ax
    mov dl, ah
    mov dh, 0x80
    mov bx, cs
    mov cx, {right}
    mov ah, 0x14
    int 0x18
    mov al, 0x0b
    out 0x68, al
    lea di, [bp + 0xac]
    mov si, 0
p2:
    mov ah, byte ptr cs:[si + {right2}]
    mov al, byte ptr cs:[si + {left2}]
    xchg ah, al
    mov dx, ax
    shl ax, 1
    or ax, dx
    xchg ah, al
    stosw
    inc si
    cmp si, 16
    jb p2
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    JMPN {back}
"""


def open_ops(d, p, end):
    """[(offset, control or None for a character, its argument bytes)] of OPEN.EXE's script, p to end."""
    out = []
    while p < end:
        b = d[p]
        if b >= 0x80:
            out.append((p, None, d[p:p + 2]))
            p += 2
        elif b >= 0x20:
            n = 2 if 0x50 <= b < 0x60 else 1
            out.append((p, b, d[p + 1:p + n]))
            p += n
        elif b == 0x05:
            e = p + 1
            while e < len(d) and d[e] != 0:
                e += 2
            out.append((p, b, d[p + 1:e + 1]))
            p = e + 1
        else:
            n = OPEN_ARGS.get(b, 0)
            out.append((p, b, d[p + 1:p + 1 + n]))
            p += 1 + n
    return out


def open_messages(exe):
    """OPEN.EXE's messages: [{"text": (its 05's offset in the image, end past its 00), "chars": its
    characters, "pages": [(its 09's offset, end past its last 07/08, the column)]}]: a text whose pages
    (a 09, codes put, to the 0Ch that clears them) put as many codes as it has characters."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    d = exe[hdr:]
    out = []
    for m in re.finditer(rb"\x05(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+\x00", d):
        s = m.start()
        chars = (m.end() - s - 2) // 2
        if chars < 2 or "�" in m.group()[1:-1].decode("cp932", "replace"):
            continue
        ops = open_ops(d, m.end(), min(len(d), m.end() + 0x400))
        pages, placed, k = [], 0, 0
        while k < len(ops) and placed < chars:
            while k < len(ops) and ops[k][1] not in (0x09, 0x05, 0x07, 0x08, None):
                k += 1
            if k >= len(ops) or ops[k][1] != 0x09:
                break
            start, col, last = ops[k][0], ops[k][2][0], None
            k += 1
            while k < len(ops) and ops[k][1] not in (0x0C, 0x05, 0x09, None):
                if ops[k][1] in (0x07, 0x08):
                    placed += ops[k][2][0]
                    last = ops[k][0] + 2
                k += 1
            if last:
                pages.append((start, last, col))
            if k < len(ops) and ops[k][1] == 0x0C:
                k += 1
        if placed == chars and pages:
            out.append({"text": (s, m.end()), "chars": chars, "pages": pages})
    return out


def open_layout(d, page, lines):
    """A page's script anew for its English lines (each an even number of letters, two to a code): its
    09, the codes' base 0, the page's own other controls kept in their order at the same share of the
    way through it, the codes put one a tick, a new line (0Dh 0Ah) between lines."""
    start, end, col = page
    ops = open_ops(d, start, end)
    jp = sum(a[0] for _p, c, a in ops if c in (0x07, 0x08))
    keep, done = [], 0
    for _p, c, a in ops[1:]:
        if c in (0x07, 0x08):
            done += a[0]
        elif c not in (0x06, 0x0A, 0x0D, None) and not 0x20 <= c < 0x30:
            keep.append((done / max(1, jp), bytes([c]) + a))
    total = sum(len(t) // 2 for t in lines)
    out = bytearray(d[start:start + 3]) + b"\x06\x00"
    placed = 0
    for n, t in enumerate(lines):
        for _k in range(len(t) // 2):
            while keep and keep[0][0] * total <= placed:
                out += keep.pop(0)[1]
            out += b"\x08\x01"
            placed += 1
        if n + 1 < len(lines):
            out += b"\x0d\x0a"
    for _f, b in keep:
        out += b
    return bytes(out)


def patch_open(exe, english):
    """OPEN.EXE with the half-width helper (two letters to a gaiji) and its messages' English:
    english = {a message's 05 offset: [its pages' lines, each line an even number of letters]}; each
    message's text and pages go on in room put in after the image (02h, a gosub, to them; 60h to the
    Japanese's end)."""
    if exe[:2] != b"MZ":
        raise SystemExit("OPEN.EXE: not an MZ program")
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    img = bytearray(exe[hdr:])
    end = -(-len(img) // 16) * 16
    img += bytes(end - len(img))
    found = list(OPEN_UPLOAD_SIG.finditer(img))
    if len(found) != 1:
        raise SystemExit("OPEN.EXE: the text's upload loop is found %d times, not once" % len(found))
    site = found[0].start() + 5
    src = OPEN_HELPER.format(after=hex(end + 0x200), jis=hex(_call_target(img, site + 4)),
                             glyph=hex(_call_target(img, site + 7)), back=hex(site + 10),
                             left=hex(end + 0x1C0), right=hex(end + 0x1E0), left2=hex(end + 0x1C2),
                             right2=hex(end + 0x1E2))
    code, labels = _asm16(src, end, ("pair",))
    if len(code) > 0x1C0:
        raise SystemExit("OPEN.EXE: the helper is %d bytes, the room 448" % len(code))
    room = bytearray(code) + bytes(0x200 - len(code))
    msgs = {mm["text"][0]: mm for mm in open_messages(exe)}
    for at, pages in sorted(english.items()):
        mm = msgs[at]
        s, e = mm["text"]
        go = end + len(room)
        room += b"\x05" + b"".join(b"".join(lines) for lines in pages) + b"\x00\x03"
        img[s:e] = b"\x02" + struct.pack("<H", go) + b"\x60" * (e - s - 3)
        for page, lines in zip(mm["pages"], pages):
            ps, pe, _col = page
            go = end + len(room)
            room += open_layout(img, page, lines) + b"\x03"
            img[ps:pe] = b"\x02" + struct.pack("<H", go) + b"\x60" * (pe - ps - 3)
    if end + len(room) > 0xFFF0:
        raise SystemExit("OPEN.EXE: its English takes %d bytes, room for %d" % (len(room) - 0x200, 0xFFF0 - end - 0x200))
    img[site:site + 10] = b"\xe9" + struct.pack("<H", (labels["pair"] - (site + 3)) & 0xFFFF) + b"\x90" * 7
    if any(site - 1 <= f < site + 10 for f in fixups):
        raise SystemExit("OPEN.EXE: a segment fixup falls in the patched range")
    room += bytes(-len(room) % 16)
    return _move_up(exe, hdr, img, fixups, rel_at, end // 16, len(room) // 16, bytes(room), "OPEN.EXE", end)


# LM.COM and OP.COM, the menu run first (from the opening or the game): their string routine (the same
# loop as LESS.EXE's, its colour at es:[a word of its own]) and the memory they keep (mov bx, n /
# add bx, 100h / shr bx, 4 / mov ah, 4Ah / int 21h).
COM_RESIZE_SIG = re.compile(rb"\xbb(..)\x81\xc3\x00\x01\xc1\xeb\x04\xb4\x4a\xcd\x21", re.S)
COM_HELPER = """
strch:
    cmp dh, 0x80
    jae sd
    cmp dh, 0x20
    jb sd
    mov al, dh
    mov cx, word ptr es:[{colour}]
    mov ch, 2
    CALLN ankc
    inc di
    JMPN {strloop}
sd:
    lodsb
    mov dl, al
    JMPN {strback}

ankc:
    pusha
    push es
    push ax
    mov dl, cl
    CALLN {grcg}
    pop ax
    mov cl, ch
    CALLN ank
    xor al, al
    out 0x7c, al
    pop es
    popa
    .byte 0xc3
""" + _PANTHER_HELPER[_PANTHER_HELPER.index("ank:"):]


def patch_com(com, name):
    """LM.COM or OP.COM with a helper at its end: its string routine draws a byte from 20h to 7Fh 8 dots
    wide from the BIOS 8x16 font, bold, one column; the memory it keeps grown to hold the helper."""
    out = bytearray(com)
    found = list(STR_SIG.finditer(out))
    if len(found) != 1:
        raise SystemExit("%s: the string routine is found %d times, not once" % (name, len(found)))
    st = found[0].start()
    c = out.rfind(b"\x26\x89\x0e", 0, st)
    if c < 0 or st - c > 0x20:
        raise SystemExit("%s: the string routine's colour is not found" % name)
    colour = struct.unpack_from("<H", out, c + 3)[0]
    gr = GRCG_SIG.search(out)
    rs = list(COM_RESIZE_SIG.finditer(out))
    if not gr or len(rs) != 1:
        raise SystemExit("%s: the GRCG routine or the memory resize is not found" % name)
    out += bytes(-len(out) % 16)
    at = len(out) + 0x100
    glyph = at + 0x100 - 0x12
    src = COM_HELPER.format(colour=hex(colour), strloop=hex(st + 0x100), strback=hex(st + 0x10a),
                            grcg=hex(gr.start() + 0x100), glyph=hex(glyph), glyph2=hex(glyph + 2))
    code, labels = _asm16(src, at, ("strch",))
    if len(code) > 0x100 - 0x14:
        raise SystemExit("%s: the helper is %d bytes, the room %d" % (name, len(code), 0x100 - 0x14))
    out += code + bytes(0x100 - len(code))
    s = st + 7
    out[s:s + 3] = b"\xe9" + struct.pack("<H", (labels["strch"] - (s + 0x100 + 3)) & 0xFFFF)
    keep = struct.unpack("<H", rs[0].group(1))[0]
    need = len(out) + 0x100
    if need > keep:
        struct.pack_into("<H", out, rs[0].start() + 1, need)
    return bytes(out)
