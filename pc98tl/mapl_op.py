"""The opening programs of MBS Truse's MAPL games (DOOP_OP.EXE): their subtitles, and English for them.

A small one-segment program (CS = DS = SS; the stack the 4 KB after its image).  Its subtitle drawer
(`DRAWER`) writes to the text layer from BX: "&" a new line (the column back to 3, two rows down), "#"
and a byte the colour, "/" the subtitle's end (a pause, the text cleared), "$" the scene's end; any
other two bytes a full-width character, a full-width space only a step.  Each scene's subtitles are
reached by "mov bx, place" before a call to the drawer (`sections`).

English (`patch`): the subtitles are laid out again after the program's image (in the bottom of its
stack's room: they and the drawer's hook may take `ROOM` bytes, the stack keeping the rest) and the
"mov bx" places moved; letter pairs (pc98tl/illusion_font24.py's) are drawn by a hook in the drawer's
Shift-JIS conversion as two ANK characters of the text layer, half-width, in the two cells of one
full-width place.
"""
import re
import struct

DRAWER = re.compile(rb"\xb8\x00\xa0\x8e\xc0\xc6\x06(..)\xe1\xc7\x06(..)\x03\x00\xc7\x06(..)\x15\x00", re.S)
# add ah, ah; sub al, 1Fh (the conversion's start) ... three vsync waits, the cell writer, inc column
CONVERT = re.compile(rb"\x02\xe4\x2c\x1f\x78\x04\x3c\x61\x14\xde\x05\xa1\x1f\x25\x7f\x7f"
                     rb"\xe8(..)\xe8..\xe8..\xe8(..)\xff\x06", re.S)
ROOM = 0x900
LINE_CELLS = 37      # full-width places on a line (the column starts at 3)
ROWS = 2


def _layout(exe):
    h = struct.unpack_from("<14H", exe, 0)
    base = h[4] * 16
    cs = base + h[11] * 16
    return h, base, cs


def sections(exe):
    """(drawer's place, [(place of the "mov bx" immediate, section's offset)]), offsets in CS."""
    h, base, cs = _layout(exe)
    m = DRAWER.search(exe, cs)
    if not m:
        raise ValueError("the subtitle drawer not found")
    drawer = m.start() - cs
    out = []
    for c in re.finditer(rb"\xbb(..)\xe8(..)", exe[cs:], re.S):
        at = c.start()
        target = (at + 6 + struct.unpack("<h", c.group(2))[0]) & 0xFFFF
        if target == drawer:
            out.append((cs + at + 1, struct.unpack("<H", c.group(1))[0]))
    return drawer, out


def subtitles(exe):
    """[(section's offset, [subtitle bytes])]: each section's subtitles (split at "/"; the last ended
    by "$")."""
    h, base, cs = _layout(exe)
    _d, secs = sections(exe)
    out = []
    for _imm, off in secs:
        i = cs + off
        e = exe.index(b"$", i)
        # ("$" and "/" are never a trail byte here: the drawer reads them where a character starts)
        out.append((off, _split(exe[i:e])))
    return out


def _split(b):
    parts, cur, i = [], bytearray(), 0
    while i < len(b):
        c = b[i]
        if c == 0x2F:
            parts.append(bytes(cur))
            cur = bytearray()
            i += 1
        elif c == 0x23:
            cur += b[i:i + 2]
            i += 2
        elif c == 0x26:
            cur.append(c)
            i += 1
        else:
            cur += b[i:i + 2]
            i += 2
    parts.append(bytes(cur))
    return parts


HOOK = """
    hook:
        cmp ah, 0xa0
        jb sj
        cmp ah, 0xdf
        ja sj
        pop dx
        sub ah, 0xa0
        test al, 0x80
        jz p1
        and al, 0x7f
        add ah, 0x40
    p1:
        add ah, 0x20
        push ax
        CALLN WAIT
        CALLN WAIT
        CALLN WAIT
        CALLN CELL
        pop ax
        mov byte ptr es:[bp], ah
        mov byte ptr es:[bp + 1], 0
        mov byte ptr es:[bp + 2], al
        mov byte ptr es:[bp + 3], 0
        inc word ptr [COLUMN]
        .byte 0xe9, 0, 0
    sj:
        add ah, ah
        sub al, 0x1f
        .byte 0xc3
"""


def patch(exe, new):
    """The program with new subtitles {(section offset, number): bytes}: every section laid out after
    the image, after the pair hook; refused past ROOM."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    h, base, cs = _layout(exe)
    drawer, secs = sections(exe)
    m = DRAWER.search(exe, cs)
    column = struct.unpack("<H", m.group(2))[0]
    loop = m.end() - cs
    cv = CONVERT.search(exe, cs + drawer)
    if not cv:
        raise ValueError("the drawer's conversion not found")
    at = cv.start() - cs
    wait = (at + 19 + struct.unpack("<h", cv.group(1))[0]) & 0xFFFF
    cell = (at + 28 + struct.unpack("<h", cv.group(2))[0]) & 0xFFFF
    end = len(exe) - cs                         # the new bytes' offset (the image's end)
    src = HOOK.replace("WAIT", "0x%x" % wait).replace("CELL", "0x%x" % cell).replace("COLUMN", "0x%x" % column)
    code, labs = _asm(Ks(KS_ARCH_X86, KS_MODE_16), src, end, ("hook",))
    code = bytearray(code)
    j = code.index(b"\xe9\x00\x00")
    struct.pack_into("<H", code, j + 1, (loop - (end + j + 3)) & 0xFFFF)
    out = bytearray(exe)
    out[cs + at:cs + at + 4] = b"\xe8" + struct.pack("<H", (end - (at + 3)) & 0xFFFF) + b"\x90"
    area = bytearray(code)
    for imm, off in secs:
        subs = dict(subtitles(exe))[off]
        place = end + len(area)
        area += b"/".join(new.get((off, k), s) for k, s in enumerate(subs)) + b"$"
        struct.pack_into("<H", out, imm, place)
    if len(area) > ROOM:
        raise ValueError("the opening's subtitles past %d bytes" % (ROOM - len(code)))
    out += area
    # the header: the image grows; the memory asked for stays the same
    total = len(out)
    paras = (len(area) + 15) // 16
    hdr = list(h)
    hdr[1], hdr[2] = total % 512, (total + 511) // 512
    hdr[5] = max(0, hdr[5] - paras)
    struct.pack_into("<14H", out, 0, *hdr)
    return bytes(out)


# ---- the openings with "@" texts (CH_OPEN.EXE, LZEXE)
#
# A text drawer (`AT_DRAWER`) draws a string through the kanji-ROM glyph library (the one MAPL.EXE uses):
# "@" and a letter and its digits a command ("@n" a new line, "@w" the speed, "@r" a pause, "@h" the
# line's height, "@c" the colour), a lead byte and the next a character, another byte a half-width step.
# Its callers push the string's far place ("push ds; push offset") and a width of -1 (no wrapping).

AT_DRAWER = re.compile(rb"\xc8\x26\x00\x00\x56\x57\x8b\x7e\x0e\xc7\x46\xec\x11\x00")
AT_CMD = re.compile(r"@[A-Za-z][0-9]*")
AT_LINE = 60         # letters a line holds (the texts start 128 dots from the left)


def at_texts(image, dgroup):
    """[(DGROUP offset, bytes)]: the strings the text drawer's callers name."""
    m = AT_DRAWER.search(image)
    if not m:
        raise ValueError("the opening's text drawer not found")
    fn = m.start()
    out = []
    for c in re.finditer(rb"\x9a(..)(..)", image, re.S):
        off, seg = struct.unpack("<HH", c.group(1) + c.group(2))
        if seg * 16 + off != fn:
            continue
        p = image.rfind(b"\x1e\x68", c.start() - 16, c.start())
        if p < 0:
            raise ValueError("a text drawer call without its string")
        at = struct.unpack_from("<H", image, p + 2)[0]
        s = image[dgroup + at:image.index(0, dgroup + at)]
        out.append((at, s))
    return out


def at_show(b):
    return b.decode("cp932", "replace").replace("@n", "\n")
