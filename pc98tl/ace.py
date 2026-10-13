"""Ace of Spades (LoveGun): the *.S scripts and ACE.EXE's text, half-width English.

A script (*.S): a word, the file's length less 4; a word, its number of lines; then the lines, each a
run of JIS characters stored as words low byte first (a word 215Ah is the bytes 5A 21), ended by a 0
byte, the last line ended by B1h 0Dh instead.  ACE.EXE draws a line from its start, a character a
16x16 cell (its glyph read with int 18h AH=14h, the JIS code in DX), into a line buffer 36 cells wide:
a line holds 36 characters (`LINE_CELLS`).  ACE.EXE's own strings (its menus) are the same words, each
ended by a 0, in its data segment (`program_strings`).

Half-width English: two letters are put in one cell, written as one word: the first letter's ASCII
code, then the second's with bit 7 set (A0h-FEh: no JIS row has bit 7 set, and the first byte is
never 0 or B1h, the line's and the script's ends).  ACE.EXE's glyph reader (`patch_program`) is given
a helper: for a cell whose high byte has bit 7 set it reads the two letters' 8x16 glyphs from the BIOS
font (int 18h AH=14h, DH 80h) and puts them side by side in the 16x16 pattern; any other code goes to
int 18h as before.  The helper is put in at the end of the code segment holding the reader (after its last routine,
which runs on two bytes past the next segment's start): the
segments after it move up (pc98tl/adl5.py _move_up), the entry's segment with them.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .adl5 import _move_up
from .illusion_font import _asm

LINE_CELLS = 36
END = b"\xb1\x0d"


# ---- scripts ---------------------------------------------------------------------------------------
def read_script(data):
    """[line bytes] of a script."""
    size, count = struct.unpack_from("<HH", data, 0)
    if size != len(data) - 4 or not data.endswith(END):
        raise ValueError("not a .S script")
    body = data[4:-len(END)]
    lines = body.split(b"\0")
    if len(lines) != count:
        raise ValueError(".S script: %d lines, the header says %d" % (len(lines), count))
    return lines


def write_script(lines):
    body = b"\0".join(lines) + END
    return struct.pack("<HH", len(body), len(lines)) + body


def show(line):
    """A line's text: JIS words as Japanese, letter pairs as their letters."""
    out = ""
    for k in range(0, len(line) - 1, 2):
        lo, hi = line[k], line[k + 1]
        if hi & 0x80:
            out += chr(lo) + chr(hi & 0x7F)
        else:
            try:
                out += (b"\x1b$B" + bytes([hi, lo]) + b"\x1b(B").decode("iso2022_jp")
            except UnicodeDecodeError:
                out += "?"
    return out


def cells(text):
    """The cells `text` takes: a Japanese character one, two letters one."""
    n, run = 0, 0
    for ch in text:
        if ord(ch) < 0x80:
            run += 1
        else:
            n += (run + 1) // 2 + 1
            run = 0
    return n + (run + 1) // 2


def encode(text):
    """Words for `text`: letters (ASCII, anything else not Japanese becoming ?) two to a word, the
    second with bit 7 set (a lone one paired with a space); Japanese as JIS words."""
    out, run = bytearray(), ""

    def flush():
        nonlocal run
        if len(run) % 2:
            run += " "
        for k in range(0, len(run), 2):
            out.extend([ord(run[k]), ord(run[k + 1]) | 0x80])
        run = ""
    for ch in text:
        o = ord(ch)
        if 0x20 <= o < 0x7F:
            run += ch
            continue
        try:
            j = ch.encode("iso2022_jp")
        except UnicodeEncodeError:
            j = b""
        if j.startswith(b"\x1b$B") and len(j) == 8:
            flush()
            out.extend([j[4], j[3]])
        else:
            run += "?"
    flush()
    return bytes(out)


# ---- the program -----------------------------------------------------------------------------------
def _segments(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    img = bytearray(exe[hdr:])
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    return hdr, rel_at, img, fixups




def program_strings(exe):
    """[(start, end)] of the JIS strings in the program's data (the segments after the code's), each
    ended by a 0 (not counted)."""
    hdr, _r, img, fixups = _segments(exe)
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    data = segs[-2] * 16 if len(segs) > 1 else 0
    out = []
    # (the strings lie end to end, each after the last one's 0, so a chunk between 0s is taken
    # whole, at any byte; one with any byte outside JIS is data)
    s = data
    while s < len(img):
        e = img.find(b"\0", s)
        if e < 0:
            break
        start, s = s, e + 1
        if e - start < 4 or (e - start) % 2:
            continue
        if any(not 0x21 <= b <= 0x7E for b in img[start:e]):
            continue
        s_, e_ = start, e
        words = [img[k:k + 2] for k in range(s_, e_, 2)]
        # (a JIS row each, and some kana, full-width punctuation or digits: ASCII file names
        # such as "DE.o" or "OP_1.G" read as kanji-row words only)
        if not all(0x21 <= w[1] <= 0x28 or 0x30 <= w[1] <= 0x74 for w in words):
            continue
        if not any(w[1] in (0x21, 0x23, 0x24, 0x25) for w in words):
            continue
        out.append((hdr + s_, hdr + e_))
    return out


# the glyph reader: mov al, 0Bh / out 68h, al / mov dx, [bp-2] / mov al, 0 / mov ah, 14h /
# mov bx, [bp-xx] / mov cx, [bp-yy] / int 18h / mov al, 0Ah / out 68h, al
READER = re.compile(rb"\xb0\x0b\xe6\x68\x8b\x56\xfe\xb0\x00\xb4\x14\x8b\x5e(.)\x8b\x4e(.)\xcd\x18\xb0\x0a\xe6\x68", re.S)

HELPER = """
    test dh, 0x80
    jnz half
    int 0x18
    mov al, 0x0a
    .byte 0xc3
half:
    push dx
    push si
    push di
    push es
    push ds
    mov es, bx
    mov di, cx
    mov word ptr es:[di], 0x0202
    push cs
    pop ds
    mov si, dx
    xor dh, dh
    CALLN letter
    mov dx, si
    mov dl, dh
    and dl, 0x7f
    xor dh, dh
    inc di
    CALLN letter
    pop ds
    pop es
    pop di
    pop si
    pop dx
    mov al, 0x0a
    .byte 0xc3
letter:
    push bx
    push cx
    push si
    push di
    push es
    mov dh, 0x80
    mov bx, cs
    mov cx, {buf}
    mov ah, 0x14
    int 0x18
    pop es
    pop di
    push di
    mov si, {buf} + 2
    mov cx, 16
copy:
    lodsb
    mov byte ptr es:[di + 2], al
    add di, 2
    loop copy
    pop di
    pop si
    pop cx
    pop bx
    .byte 0xc3
"""


def _asm16(src, org):
    lines, calls = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("CALLN "):
            tag = "__call%d" % len(calls)
            calls.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org,
                      [t for t, _x in calls] + sorted({x for _t, x in calls}))
    code = bytearray(code)
    for tag, target in calls:
        at = addr[tag] - org
        code[at:at + 3] = b"\xe8" + ((addr[target] - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("ACE.EXE: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code)


def patch_program(exe):
    """ACE.EXE with the half-width helper (see the module's docstring)."""
    hdr, rel_at, img, fixups = _segments(exe)
    found = [m for m in READER.finditer(img)]
    if len(found) != 1:
        raise SystemExit("ACE.EXE: the glyph reader's signature is found %d times, not once" % len(found))
    m = found[0]
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    code_seg = max(s for s in segs if s * 16 <= m.start())
    next_seg = min(s for s in segs if s * 16 > m.start())
    # (the code segment's last routine runs on past the next segment's start, its leave / retf
    # there; that segment's own code begins after the zeros that follow: the room goes in after it)
    split = next_seg * 16
    while img[split] != 0:
        split += 1
    if split - next_seg * 16 > 15 or any(img[split:split + 8]):
        raise SystemExit("ACE.EXE: the code segment's end is not laid out as expected")
    org = split - code_seg * 16
    # (assembled twice: the glyph buffer goes after the code)
    code = _asm16(HELPER.format(buf=hex(org + 0x100)), org)
    code = _asm16(HELPER.format(buf=hex(org + len(code))), org)
    paras = -(-(len(code) + 2 + 16) // 16)
    # the reader's int 18h / mov al, 0Ah becomes call helper / nop (the helper returns with al 0Ah,
    # for the out 68h after it)
    at = m.start(0) + 17
    call = bytes([0xE8]) + struct.pack("<H", (org - ((at - code_seg * 16) + 3)) & 0xFFFF)
    img[at:at + 4] = call + bytes([0x90])
    out = bytearray(_move_up(exe, hdr, img, fixups, rel_at, next_seg, paras, code, "ACE.EXE", split=split))
    cs = struct.unpack_from("<H", out, 0x16)[0]
    if cs >= next_seg:
        struct.pack_into("<H", out, 0x16, cs + paras)
    return bytes(out)
