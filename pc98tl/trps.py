"""Custom's engine for Teen (TEEN\\TEEN.COM runs INIT.EXE, CUSTOM.EXE and MENU.EXE; MENU.EXE plays the
opening, TEEN_S1.EXE and TEEN_S2.EXE the two scenarios; the library is Custom's "Terpsichorean"): its
text, and English drawn half-width.

Messages: DATA_00.MSG and DATA_nn.1MS / DATA_nn.2MS, CR LF lines, each byte b stored as rol(b, 5) xor 55h
(`decode`, `encode`).  The scenes, compiled into the programs, name a message by its line's number, so a
line can be any length.  A line is Shift-JIS and the user-defined characters of TEEN.GAI (lead bytes
from EBh: `show` writes them {Gxxxx}).  The programs' message routine draws a line a character at a time
at its window's columns (TEEN.INI: 32 full-width characters a row, 4 rows, `window`), going down a row at
the edge and waiting for a key and clearing the window after the last row.

The programs are PKLITE-packed (pc98tl/pklite.py) and are written back unpacked.  Their own strings are
0-ended in their data (`program_strings`) and are written in place.

English (`patch_program`): the message routine passes over a byte that is not a Shift-JIS lead
(`LOOP_A`/`LOOP_B`: MENU.EXE's build reads the lead table through DS, the scenarios' through a segment).
There it is made to call a helper (a segment put in before the program's last, pc98tl/adl5.py
`_move_up`) that draws the byte with the routine's own call (its glyph routine draws a byte below 100h
from the BIOS 8x16 font) and steps one column instead of two; the helper finds the call's segment from
its caller's.  The patcher breaks the English between words at the window's width and fills each row
with spaces to the edge (the routine has no new-line code).
"""
import re
import struct

from .adl5 import _move_up
from .kuro import _asm16, _exe

# ---- the message files ----------------------------------------------------------------------------------


def decode(data):
    return bytes((((b ^ 0x55) << 3) | ((b ^ 0x55) >> 5)) & 0xFF for b in data)


def encode(data):
    return bytes(((((b << 5) | (b >> 3)) & 0xFF) ^ 0x55) for b in data)


def lines(data):
    """The decoded file's lines (CR LF apart)."""
    return decode(data).split(b"\r\n")


def join(ls):
    return encode(b"\r\n".join(ls))


GAIJI = re.compile(rb"[\xeb-\xfc][\x40-\x7e\x80-\xfc]")
CHAR = re.compile(rb"[\xeb-\xfc][\x40-\x7e\x80-\xfc]|[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|[\x00-\x7f\xa0-\xdf]")


def show(b):
    """A line as strings.json shows it: the user-defined characters as {Gxxxx}."""
    out = []
    for m in CHAR.finditer(b):
        c = m.group()
        out.append("{G%s}" % c.hex() if GAIJI.fullmatch(c) else c.decode("cp932", "replace"))
    return "".join(out)


def window(ini):
    """(letters a row, rows) of the message window from TEEN.INI (its columns are full-width ones)."""
    t = ini.decode("cp932", "replace")
    cols = re.search(r"メッセージの桁数\s*=\s*(\d+)", t)
    rows = re.search(r"メッセージの行数\s*=\s*(\d+)", t)
    if not cols or not rows:
        raise ValueError("TEEN.INI: the message window's size is not found")
    return 2 * int(cols.group(1)), int(rows.group(1))


TOKEN = re.compile(r"\{G([0-9a-f]{4})\}|[ ]+|[^ {]+|\{")


def layout(text, width):
    """The English's bytes: ASCII and {Gxxxx}, broken between words at `width` letters, each row but the
    last filled with spaces to the edge (the routine then goes down a row)."""
    from .aypio import ascii_text
    rows, cur, n = [], [], 0
    words = []
    for para in ascii_text(text).split("\n"):
        words.append(None)
        for m in TOKEN.finditer(para):
            g = m.group()
            if m.group(1):
                words.append(bytes.fromhex(m.group(1)))
            elif g.isspace():
                words.append(b" ")
            else:
                words.append(g.encode("ascii"))
    words = words[1:]

    def flush():
        nonlocal cur, n
        while cur and cur[-1] == b" ":
            cur.pop()
        rows.append(b"".join(cur))
        cur, n = [], 0

    for w in words:
        if w is None:
            flush()
            continue
        if w == b" ":
            if cur:
                cur.append(w)
                n += 1
            continue
        if n + len(w) > width and n:
            flush()
        cur.append(w)
        n += len(w)
    flush()
    return b"".join(r.ljust(width) if k < len(rows) - 1 else r for k, r in enumerate(rows))


# ---- the programs ---------------------------------------------------------------------------------------

STRING = re.compile(rb"(?<=\0)(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e\r\n\t\x1b])+(?=\0)")
JAPANESE = re.compile(r"[ぁ-ヶ一-龥]")
DS_LOAD = re.compile(rb"\xb8(..)\x8e\xd8", re.S)        # mov ax, (a data segment) / mov ds, ax
DEBUG = re.compile(r"［[^］]*］_pc\d")      # a choice's condition, shown only by the debug display


def program_strings(img, fixups):
    """[(image offset, end)] of a program's Japanese strings: 0-ended, from its first data segment on (the
    lowest a function loads into DS, else its last segment), with kana in them, or two or more kanji and
    nothing but full-width characters and spaces (code's bytes are rarely either)."""
    fix = set(fixups)
    ds = [struct.unpack("<H", m.group(1))[0] for m in DS_LOAD.finditer(img) if m.start() + 1 in fix]
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    lo = (min(ds) if ds else max(segs)) * 16
    # (the offsets the code pushes or loads: a string whose start is not one but one two bytes on is, has
    # data before it, such as a word that reads as a kanji)
    named = {struct.unpack("<H", m.group(1))[0] for m in re.finditer(rb"[\x68\xb8-\xbf](..)", img[:lo], re.S)}
    out = []
    for m in STRING.finditer(img, lo):
        start = m.start()
        seg = max(s for s in segs if s * 16 <= start)
        if start - seg * 16 not in named:
            for d in (2,):
                if start + d - seg * 16 in named:
                    start += d
                    break
        try:
            t = img[start:m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        n = len(JAPANESE.findall(t))
        if re.search(r"[-]", t) or DEBUG.match(t):
            continue
        if n < 2:
            # (one kanji, a name such as 愛: a common one (JIS level 1) whose place the code names)
            c = img[start:m.end()]
            if (len(c) == 2 and 0x889F <= (c[0] << 8 | c[1]) <= 0x9872
                    and start - max(s for s in segs if s * 16 <= start) * 16 in named):
                out.append((start, m.end()))
            continue
        if re.search(r"[ぁ-ヶ]", t):
            out.append((start, m.end()))
            continue
        # (kanji alone: a short word, or with full-width letters, spaces or brackets)
        if (not re.search(r"[!-~]", t) and not re.search(r"(.)\1\1", re.sub(r"[ 　]", "", t))
                and (n <= 4 or re.search(r"[　！-～【】［］]", t))):
            out.append((start, m.end()))
    return out


CONDITION = re.compile(rb"(?<=\0)\x81\x6d((?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc])+?)\x81\x6e_pc\d")


def conditions(img):
    """[(image offset, end, label)] of the labels in a choice's conditions ("［label］_pcN <= ..."): the
    program finds a choice by its label there, so a label's English goes in both."""
    out = []
    for m in CONDITION.finditer(img):
        try:
            out.append((m.start(1), m.end(1), m.group(1).decode("cp932")))
        except UnicodeDecodeError:
            pass
    return out


# the message routine's step past a byte: mov al, [bp+c] / mov ah, 0 / (the lead table's segment) / mov bx,
# ax / test byte [bx+table], 4 / jne (a lead) / jmp (the next byte)
LOOP_A = re.compile(rb"\x8a\x46(.)\xb4\x00\xba(..)\x8b\xd8\x8e\xc2\x26\xf6\x87(..)\x04\x75\x03\xe9..", re.S)
LOOP_B = re.compile(rb"\x8a\x46(.)\xb4\x00\x8b\xd8\xf6\x87(..)\x04\x75\x03\xe9..", re.S)
# a lead's path: the second byte, the call that draws the character (its colour, the window's column,
# row and row height, the window), the column moved on by 2
LEAD = re.compile(rb"\xc4\x5e.\x26\x8a\x07\xb4\x00\x8b\x56.\xc1\xe2\x08\x03\xd0\x89\x56.\xff\x46.\x52\x6a\xff"
                  rb"\xc4\x5e\x06\x26\xff\x77(.)\x83\xec\x04\x26\x8b\x47(.)\xc1\xe0\x03\x89\x46.\x26\x8b\x47(.)"
                  rb"\x26\xf7\x6f(.)\x89\x46.\x8b\x46.\x89\x46.\x8b\x46.\x89\x46.\x26\xff\x77(.)\x26\xff\x77(.)"
                  rb"\x9a(..)(..)\x83\xc4\x0e(\xc4\x5e\x06\x26\x83\x47(.)\x02)", re.S)

HELPER = """
ank:
    push di
    mov dx, bx
    les bx, dword ptr [bp + 6]
    push dx
    mov ax, 0xffff
    push ax
    push word ptr es:[bx + {attr}]
    mov ax, word ptr es:[bx + {row}]
    imul word ptr es:[bx + {height}]
    push ax
    mov ax, word ptr es:[bx + {col}]
    shl ax, 3
    push ax
    push word ptr es:[bx + {hi}]
    push word ptr es:[bx + {lo}]
    mov di, sp
    mov cx, word ptr ss:[di + 18]
    add cx, {delta}
    push cs
    mov ax, back
    push ax
    push cx
    mov ax, {draw}
    push ax
    .byte 0xcb
back:
    add sp, 14
    les bx, dword ptr [bp + 6]
    dec word ptr es:[bx + {col}]
    pop di
    mov bx, sp
    mov word ptr ss:[bx], {ret}
    .byte 0xcb
"""


def _segment(img, fixups, at):
    """The code segment of the function around `at`: the segment of the far calls (call seg:off, the
    segment a fixup) to the nearest function start before it."""
    best = None
    for f in fixups:
        if f < 3 or img[f - 3] != 0x9A:
            continue
        seg = struct.unpack_from("<H", img, f)[0]
        target = seg * 16 + struct.unpack_from("<H", img, f - 2)[0]
        if target <= at and at - seg * 16 < 0x10000 and (best is None or target > best[0]):
            best = (target, seg)
    return best[1] if best else None




# the message window's next row: past its last row, the wait for a key and the window cleared (push [bp+8] /
# push bx / push cs / call (the wait) / add sp, 4); and the key state's call in the message routine
PAGE = re.compile(rb"\x26\x3b\x47.\x7c.\xff\x76\x08\x53(\x0e\xe8(..)\x83\xc4\x04)", re.S)
KEYS = re.compile(rb"\x9a(..)(..)\xa9\x00\x40", re.S)

PAGE_WAIT = """
page:
    push di
    mov di, sp
    push word ptr ss:[di + 8]
    push word ptr ss:[di + 6]
    mov cx, word ptr ss:[di + 4]
    push cs
    mov ax, p_back
    push ax
    push cx
    mov ax, {wait}
    push ax
    .byte 0xcb
p_back:
    add sp, 4
p_keys:
    mov di, sp
    mov cx, word ptr ss:[di + 4]
    add cx, {kdelta}
    push cs
    mov ax, p_state
    push ax
    push cx
    mov ax, {keys}
    push ax
    .byte 0xcb
p_state:
    and ax, 0xbfff
    jnz p_keys
p_flush:
    mov ah, 1
    int 0x18
    or bh, bh
    jz p_done
    mov ah, 0
    int 0x18
    jmp p_flush
p_done:
    pop di
    .byte 0xca, 4, 0
"""

# the kanji glyph routine's read of a glyph from the font: cmp di, [bp+0Eh] / jne / mov ah, 14h / mov bx, ss /
# lea cx, [bp+buf] / mov dx, [bp+0Eh] / int 18h
KANJI_READ = re.compile(rb"\x3b\x7e\x0e\x75\x0c(\xb4\x14\x8c\xd3\x8d\x4e(.)\x8b\x56\x0e\xcd\x18)", re.S)
PAIR_ROWS = range(0x79, 0x7F)       # JIS rows of the pairs' codes (Shift-JIS EDh-EFh: no font, no TEEN.GAI)

KANJI = """
kanji:
    push si
    push di
    mov ax, word ptr [bp + 0xe]
    sub ah, {row0}
    jb k_rom
    cmp ah, {nrows}
    jae k_rom
    sub al, 0x21
    jb k_rom
    cmp al, 94
    jae k_rom
    mov cl, al
    mov al, ah
    mov ah, 94
    mul ah
    xor ch, ch
    add ax, cx
    cmp ax, word ptr cs:[{count}]
    jae k_rom
    shl ax, 1
    mov si, ax
    mov si, word ptr cs:[si + {table}]
    mov dx, si
    mov dl, dh
    mov dh, 0x80
    mov ah, 0x14
    mov bx, ss
    lea cx, [bp {buf}]
    int 0x18
    mov cx, 16
    xor di, di
k_copy:
    mov al, byte ptr [bp + di {rows}]
    mov byte ptr cs:[di + {tmp}], al
    inc di
    loop k_copy
    mov dx, si
    mov dh, 0x80
    mov ah, 0x14
    mov bx, ss
    lea cx, [bp {buf}]
    int 0x18
    mov si, 15
k_merge:
    mov al, byte ptr [bp + si {rows}]
    mov ah, byte ptr cs:[si + {tmp}]
    mov di, si
    shl di, 1
    mov word ptr [bp + di {rows}], ax
    dec si
    jns k_merge
    mov word ptr ss:[bp {buf}], 0x202
    jmp k_done
k_rom:
    mov ah, 0x14
    mov bx, ss
    lea cx, [bp {buf}]
    mov dx, word ptr [bp + 0xe]
    int 0x18
k_done:
    pop di
    pop si
    .byte 0xcb
"""


def _disp(n):
    return ("+ %#x" if n >= 0 else "- %#x") % abs(n)


def _sjis(j1, j2):
    s1 = (j1 + 1) // 2 + (0x70 if j1 <= 0x5E else 0xB0)
    s2 = j2 + (0x1F if j1 & 1 else 0x7E)
    if j1 & 1 and s2 >= 0x7F:
        s2 += 1
    return bytes((s1, s2))


def pair_codes(texts):
    """{two letters: Shift-JIS code} for the pairs the texts are written in."""
    codes = {}
    cells = [(r, c) for r in PAIR_ROWS for c in range(0x21, 0x7F)]
    for t in texts:
        for k in range(0, len(t), 2):
            p = t[k:k + 2]
            if p not in codes:
                if len(codes) >= len(cells):
                    raise SystemExit("the programs' strings need more than %d different pairs of letters; "
                                     "shorten them" % len(cells))
                codes[p] = _sjis(*cells[len(codes)])
    return codes


def pairs(t, codes):
    """ASCII bytes (of even length) as the pairs' codes."""
    return b"".join(codes[t[k:k + 2]] for k in range(0, len(t), 2))


def has_routines(exe):
    _h, _r, img, _f = _exe(exe)
    b = bytes(img)
    return any(p.search(b) for p in (LOOP_A, LOOP_B, KANJI_READ))


# the one-byte glyph routine widens its 8x16 glyph a row a word, counting the rows with a local it sets only
# later ([bp-24h]; its menus happen to leave 16 there, a message's helper does not): mov cx, [bp-24h] made
# mov cx, 16
ANK_ROWS = re.compile(rb"\xfd\x8d\x76\xef\x8d\x7e\xfe\xb4\x00(\x8b\x4e\xdc)\xac\xab\xe2\xfc\xfc")


def _rel(out, rel_at, at, seg):
    nrel = struct.unpack_from("<H", out, 6)[0]
    struct.pack_into("<HH", out, rel_at + 4 * nrel, at - seg * 16, seg)
    struct.pack_into("<H", out, 6, nrel + 1)


def patch_program(exe, places, paired, name):
    """A program (unpacked) with its strings' English: places [(image offset, bytes)] written as they are,
    paired [(image offset, room, ASCII bytes)] written as pairs of letters (each a code its glyph routine
    draws as two letters: `KANJI`); the message routine's one-byte helper (`HELPER`)."""
    exe = bytearray(exe)
    hdr, rel_at, img, fixups = _exe(bytes(exe))
    for at, b in places:
        img[at:at + len(b)] = b
    b = bytes(img)
    for m in ANK_ROWS.finditer(b):
        img[m.start(1):m.end(1)] = b"\xb9\x10\x00"
    loops = [(p, m) for p in (LOOP_A, LOOP_B) for m in p.finditer(b)]
    reads = list(KANJI_READ.finditer(b))
    if not loops and not reads:
        if paired:
            raise SystemExit("%s: no glyph routine to draw the pairs of letters" % name)
        return bytes(exe[:hdr]) + bytes(img)
    if len(loops) > 1 or len(reads) > 1:
        raise SystemExit("%s: the message routine or the glyph routine is found more than once" % name)
    texts = [t.ljust(-(-len(t) // 2) * 2) for _a, _r, t in paired]
    codes = pair_codes(texts)
    for (at, room, _t), t in zip(paired, texts):
        enc = pairs(t, codes)[:room - room % 2]
        img[at:at + room] = enc + b" " * (room - len(enc))
    src, calls = "", []
    split = max(struct.unpack_from("<H", img, f)[0] for f in fixups)
    if loops:
        pat, m = loops[0]
        lead = LEAD.match(b, m.end())
        if not lead:
            raise SystemExit("%s: the message routine is not laid out as expected" % name)
        attr, col, row, height, hi, lo = (lead.group(k)[0] for k in range(1, 7))
        if lead.group(10)[0] != col:
            raise SystemExit("%s: the message routine's column is not laid out as expected" % name)
        seg = _segment(img, fixups, m.start())
        if seg is None:
            raise SystemExit("%s: the message routine's segment is not found" % name)
        draw_seg = struct.unpack("<H", lead.group(8))[0]
        src += HELPER.format(attr=hex(attr), row=hex(row), height=hex(height), col=hex(col), hi=hex(hi),
                             lo=hex(lo), delta=hex((draw_seg - seg) & 0xFFFF),
                             draw=hex(struct.unpack("<H", lead.group(7))[0]), ret=hex(lead.start(9) - seg * 16))
        calls.append(("ank", pat, m, seg))
        # (after a window's last row the wait for a key, then the keys let go of before it goes on: the
        # key that ended the wait would end the message's own wait at once)
        pg = PAGE.search(b, m.end())
        keys = KEYS.search(b, m.end())
        if not pg or not keys or _segment(img, fixups, pg.start()) != seg:
            raise SystemExit("%s: the message window's next page is not laid out as expected" % name)
        wait = (pg.start(1) + 4 - seg * 16 + struct.unpack("<h", pg.group(2))[0]) & 0xFFFF
        kseg = struct.unpack("<H", keys.group(2))[0]
        src += PAGE_WAIT.format(wait=hex(wait), kdelta=hex((kseg - seg) & 0xFFFF),
                                keys=hex(struct.unpack("<H", keys.group(1))[0]))
        calls.append(("page", None, pg, seg))
    if reads:
        r = reads[0]
        buf = struct.unpack("b", r.group(2))[0]
        seg = _segment(img, fixups, r.start())
        if seg is None:
            raise SystemExit("%s: the glyph routine's segment is not found" % name)
        calls.append(("kanji", None, r, seg))
    table = sorted(codes.items(), key=lambda kv: kv[1])

    def source(base):
        s = src
        if reads:
            s += KANJI.format(row0=hex(PAIR_ROWS[0]), nrows=len(PAIR_ROWS), count=hex(base),
                              table=hex(base + 2), tmp=hex(base + 2 + 2 * len(table)), buf=_disp(buf), rows=_disp(buf + 2))
        return s

    names = (["ank", "back", "page"] if loops else []) + (["kanji"] if reads else [])
    code, _a = _asm16(source(0x400), 0, names)
    base = len(code) + (len(code) % 2)
    code, addr = _asm16(source(base), 0, names)
    data = struct.pack("<H", len(table)) + b"".join(p.encode("ascii")[:1] + p.encode("ascii")[1:2]
                                                    for p, _c in table) + bytes(16)
    room = code + bytes(base - len(code)) + data
    if rel_at + 4 * (len(fixups) + len(calls)) > hdr:
        # (the header longer for the relocation entries the calls add)
        more = -(-(rel_at + 4 * (len(fixups) + len(calls)) - hdr) // 16)
        exe[hdr:hdr] = bytes(16 * more)
        struct.pack_into("<H", exe, 8, hdr // 16 + more)
        hdr, rel_at, img2, fixups = _exe(bytes(exe))
        img2[:] = img
        img = img2
    sites = []
    for tag, pat, m, seg in calls:
        call = b"\x9a" + struct.pack("<HH", addr[tag], split)
        if tag in ("kanji", "page"):
            # (the page's call: push cs / call near / add sp, 4 made call far, the helper's retf 4 the add)
            new = call + b"\x90" * (len(m.group(1)) - 5)
            img[m.start(1):m.end(1)] = new
            sites.append((m.start(1) + 3, seg))
            continue
        c = m.group(1)[0]
        if pat is LOOP_A:
            # mov bx, [bp+c] / nop nop / (the segment kept where its fixup is) / mov es, dx / test / jne / call
            new = b"\x8b\x5e" + bytes([c]) + b"\x90\x90\xba" + m.group(2) + b"\x8e\xc2\x26\xf6\x87" + m.group(3)
            new += b"\x04\x75\x05" + call
            sites.append((m.end() - 2, seg))
        else:
            new = b"\x8b\x5e" + bytes([c]) + b"\xf6\x87" + m.group(2) + b"\x04\x75\x07" + call + b"\x90\x90"
            sites.append((m.end() - 4, seg))
        if len(new) != m.end() - m.start():
            raise SystemExit("%s: the message routine's step does not fit" % name)
        img[m.start():m.end()] = new
    paras = -(-len(room) // 16) + 1
    out = bytearray(_move_up(bytes(exe), hdr, img, fixups, rel_at, split, paras, room, name))
    for at, seg in sites:
        _rel(out, rel_at, at, seg)
    return bytes(out)
