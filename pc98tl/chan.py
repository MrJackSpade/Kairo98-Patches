"""D.O.'s CHAN.EXE (Moonlight Chan Rin Shan 1994, Yuu Disk Vol. 7): a mahjong game with a quiz.

Text is Shift-JIS (two bytes a character, 0Ah a new line), drawn 16x16 from the character ROM into the
graphics planes through the GRCG, by two routines:

* The text window (the quiz's question, the girls' profiles): a string is copied into a buffer
  (4F57h: bytes under 11h are controls, 20h one byte, anything else two), then drawn a character at a
  time (4E20h: 00 ends it, under 11h a control, else 4C8Fh draws dh:dl at [8] in the colour [2]),
  the line's room [0Ch] (in bytes, from [0Ah]) less two a character; at 0 a new line (4E9Fh: the rows
  left [10h], at the last a key wait and the window scrolled).  Its state is in the data segment.
* A string at a place (28EDh: ax:si the string, di the place, cl the colour), the menus' words and
  the quiz's three choices.

The quiz (QDAT): a directory of 16-byte entries (a 12-byte name, a word: the member's start in
paragraphs from the file's start), the twelfth followed by an entry with no name giving the end; each
member Qnn.QDT: a table of 100 word offsets (from the member's start, C8h bytes, as they are; Yuu Disk
Vol. 7's hold 50, the rest 0), then
the questions, every byte inverted (the program inverts each member past its table once loaded):
four word offsets (the question and the three choices), the right choice's number (a byte), then the
four strings, each ended by 00.  The program reads the whole file into its work segments 42F7h on
(four reads of 8000h bytes and one of 3000h, the stack right after).

The patch (patch_exe): a helper put in at the end of the code segment (pc98tl/adl5.py _move_up, the
segments after it moved up):

* A byte under 80h is a half-width letter: drawn 8 dots wide from the BIOS 8x16 font, bold as the
  program's characters, in the caller's colour, one byte along.  In the text window the line's room
  is taken one for it (the two decrements after 4C8Fh become a subtraction of the character's width,
  1 or 2); before a word that would not fit what is left of the line, the window's own new line
  (4E9Fh); a space at a line's start is not drawn.  The buffer copy takes a byte under 80h as one.
* A full-width character with one byte left on the line starts a new line first.
* The string routine draws a byte under 80h the same way.

QDAT grown past the five reads: the last read takes up to 8000h bytes, the stack segment and the
memory the program asks for past its image moving up by as many paragraphs (160 KB in all).
"""
import re
import struct

from .adl import _asm16, _call_target, _code_end
from .adl5 import _move_up

ROOM = 0x18                     # paragraphs for the helper
QDAT_SEGS = 5
QDAT_MAX = 0x28000              # four reads of 8000h and the last up to 8000h

# the character routine's draw (4CCCh): mov dh, [si] / inc si / mov dl, [si] / inc si / mov di, [8] /
# mov cl, [2] / call draw / mov [8], di / call wait / ret
# (the window's state: a block at B, 0 in Moonlight Chan Rin Shan, 5758h in Yuu Disk Vol. 7: [B+8] the
# cursor, [B+2] the colour, [B+0Ah] a line's room, [B+0Ch] what is left of it, [B+10h] the rows left)
DRAW_SIG = re.compile(rb"\x8a\x34\x46\x8a\x14\x46\x8b\x3e(..)\x8a\x0e(..)\xe8(..)\x89\x3e(..)\xe8(..)\xc3", re.S)
# the text loop's two decrements after the character: dec word [0Ch] / dec word [0Ch] / jne
DEC_SIG = "\xff\x0e{room}\xff\x0e{room}\x75"
# the text loop's new line: dec word [10h] / jne
NEWLINE_SIG = "\xff\x0e{rows}\x75.\xc6\x06{flag}\x01"
# the buffer copy: stosb / cmp al, 20h / je / movsb
COPY_SIG = re.compile(rb"\xaa\x3c\x20\x74.\xa4", re.S)
# the string routine's loop (290Eh): lodsb / mov dh, al / or al, al / je (the end) / lodsb / mov dl, al
STR_SIG = re.compile(rb"\xac\x8a\xf0\x0a\xc0\x74(.)\xac\x8a\xd0", re.S)
# the GRCG on in the colour dl (295Bh): mov al, C0h / out 7Ch, al
GRCG_SIG = re.compile(rb"\xb0\xc0\xe6\x7c\x32\xc0\xd0\xea", re.S)
# the quiz's reads: mov ax, 62F7h / mov cx, 3000h / call
LAST_READ_SIG = re.compile(rb"\xb8(..)\xb9\x00\x30\xe8", re.S)

HELPER = """
fallthrough:
    JMPN {after}

texthook:
    mov dh, byte ptr [si]
    cmp dh, 0x80
    jae tk2
    cmp dh, 0x20
    jne ta1
    mov ax, word ptr [{line}]
    cmp ax, word ptr [{left}]
    jne ta2
    inc si
    mov word ptr cs:[{w}], 0
    mov byte ptr cs:[{prev}], 0
    .byte 0xc3
ta1:
    cmp byte ptr cs:[{prev}], 0
    jne ta3
    push si
    xor cx, cx
tm:
    mov al, byte ptr [si]
    cmp al, 0x21
    jb tme
    cmp al, 0x80
    jae tme
    inc cx
    inc si
    jmp tm
tme:
    pop si
    mov ax, word ptr [{left}]
    cmp cx, ax
    jbe ta3
    cmp ax, word ptr [{line}]
    je ta3
    push si
    push dx
    CALLN {newline}
    pop dx
    pop si
ta3:
    mov byte ptr cs:[{prev}], 1
    jmp ta4
ta2:
    mov byte ptr cs:[{prev}], 0
ta4:
    inc si
    mov word ptr cs:[{w}], 1
    mov di, word ptr [{cursor}]
    mov cl, byte ptr [{color}]
    mov al, dh
    CALLN ank
    mov word ptr [{cursor}], di
    CALLN {wait}
    .byte 0xc3
tk2:
    mov byte ptr cs:[{prev}], 0
    cmp word ptr [{left}], 1
    jne tk3
    push si
    push dx
    CALLN {newline}
    pop dx
    pop si
tk3:
    mov word ptr cs:[{w}], 2
    inc si
    JMPN {back}

strhook:
    lodsb
    mov dh, al
    or al, al
    jne s1
    JMPN {strend}
s1:
    cmp al, 0x80
    jae s2
    mov cl, byte ptr cs:[{strcolor}]
    CALLN ank
    JMPN {strloop}
s2:
    JMPN {strnext}

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
    pop dx
    xor dh, dh
    cli
    CALLN {grcg}
    mov ax, 0xa800
    mov es, ax
    push cs
    pop ds
    mov si, {glyph2}
    mov cx, 16
a1:
    lodsb
    mov ah, al
    shr ah, 1
    or al, ah
    mov byte ptr es:[di], al
    add di, 0x50
    loop a1
    xor al, al
    out 0x7c, al
    sti
    pop es
    pop ds
    popa
    inc di
    .byte 0xc3
"""


def _one(seg, sig, what, name):
    found = list(sig.finditer(seg))
    if len(found) != 1:
        raise SystemExit("%s: the %s signature is found %d times, not once" % (name, what, len(found)))
    return found[0]


def patch_exe(exe, name="CHAN.EXE", qdat_size=None):
    """CHAN.EXE with the half-width helper (see the module's docstring); qdat_size: QDAT's size as
    built, past the five reads' 143360 bytes the last read and the memory grown for it."""
    if exe[:2] != b"MZ":
        raise SystemExit("%s: not an MZ program" % name)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    cs0 = code_seg * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    next_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > code_seg)
    split = _code_end(img, next_seg * 16, name)
    seg = bytearray(img[cs0:split])
    draw = _one(seg, DRAW_SIG, "character draw", name)
    base = struct.unpack("<H", draw.group(1))[0] - 8
    if struct.unpack("<H", draw.group(2))[0] != base + 2 or struct.unpack("<H", draw.group(4))[0] != base + 8:
        raise SystemExit("%s: the character draw is not laid out as expected" % name)
    wait = _call_target(seg, draw.start() + 21)

    def field(off):
        return re.escape(struct.pack("<H", base + off))
    dec = _one(seg, re.compile(DEC_SIG.encode("latin-1").replace(b"{room}", field(0x0C)), re.S), "line room", name)
    nl = _one(seg, re.compile(NEWLINE_SIG.encode("latin-1").replace(b"{rows}", field(0x10)).replace(b"{flag}", field(3)),
                              re.S), "new line", name).start()
    copy = _one(seg, COPY_SIG, "buffer copy", name).start()
    st = _one(seg, STR_SIG, "string routine", name)
    strend = st.start() + 7 + struct.unpack("b", st.group(1))[0]
    strloop = st.start()
    strnext = st.start() + 7
    grcg = _one(seg, GRCG_SIG, "GRCG", name).start()
    # (the string routine keeps its colour at cs:[x]: mov es:[x], cx before its loop)
    cm = re.compile(rb"\x26\x89\x0e(..)\xeb", re.S).search(seg, st.start() - 0x20, st.start())
    if not cm:
        raise SystemExit("%s: the string routine's colour is not found" % name)
    strcolor = struct.unpack("<H", cm.group(1))[0]
    at = len(seg)
    # (the room's end: the character's width (a word), the word flag (a byte, and one spare), the BIOS
    # font's answer (2 bytes, then 16 rows))
    w, prev, glyph = at + ROOM * 16 - 0x16, at + ROOM * 16 - 0x14, at + ROOM * 16 - 0x12
    src = HELPER.format(after=hex(at + ROOM * 16), w=hex(w), prev=hex(prev), newline=hex(nl),
                        wait=hex(wait), back=hex(draw.start() + 3), strend=hex(strend), strcolor=hex(strcolor),
                        strloop=hex(strloop), strnext=hex(strnext), glyph=hex(glyph), glyph2=hex(glyph + 2),
                        grcg=hex(grcg), cursor=hex(base + 8), color=hex(base + 2), line=hex(base + 0x0A),
                        left=hex(base + 0x0C))
    code, labels = _asm16(src, at, ("texthook", "strhook"))
    if len(code) > ROOM * 16 - 0x16:
        raise SystemExit("%s: the helper is %d bytes, the room %d" % (name, len(code), ROOM * 16 - 0x16))
    d0 = draw.start()
    seg[d0:d0 + 3] = b"\xe9" + struct.pack("<H", (labels["texthook"] - (d0 + 3)) & 0xFFFF)
    seg[dec.start():dec.start() + 8] = b"\x2e\xa1" + struct.pack("<H", w) + b"\x29\x06" + struct.pack("<H", base + 0x0C)
    seg[copy + 1:copy + 5] = b"\x3c\x80\x72" + seg[copy + 4:copy + 5]
    s0 = st.start()
    seg[s0:s0 + 5] = b"\xe9" + struct.pack("<H", (labels["strhook"] - (s0 + 3)) & 0xFFFF) + b"\x90\x90"
    for lo, n in ((d0, 3), (dec.start(), 8), (copy + 1, 4), (s0, 5)):
        if any(cs0 + lo - 1 <= f < cs0 + lo + n for f in fixups):
            raise SystemExit("%s: a segment fixup falls in a patched range" % name)
    if qdat_size and qdat_size > QDAT_MAX - 0x8000 + 0x3000:
        if qdat_size > QDAT_MAX:
            raise SystemExit("QDAT: %d bytes, the program reads 163840" % qdat_size)
        lr = _one(seg, LAST_READ_SIG, "quiz's last read", name)
        extra = 0x500
        seg[lr.start() + 3:lr.start() + 6] = b"\xb9\x00\x80"
    else:
        extra = 0
    img[cs0:cs0 + len(seg)] = seg
    out = bytearray(_move_up(exe, hdr, img, fixups, rel_at, next_seg, ROOM, code, name, split))
    if extra:
        # (the stack past the grown last read, the memory asked for with it)
        struct.pack_into("<H", out, 0x0E, struct.unpack_from("<H", out, 0x0E)[0] + extra)
        struct.pack_into("<H", out, 0x0A, struct.unpack_from("<H", out, 0x0A)[0] + extra)
    return bytes(out)


# ---- QDAT

def qdat_read(raw):
    """[(name, member bytes)] of QDAT (the members as on disk)."""
    ents = []
    at = 0
    while True:
        name = raw[at:at + 12].split(b"\x00")[0].decode("ascii")
        off = struct.unpack_from("<I", raw, at + 12)[0]
        ents.append((name, off))
        at += 16
        if not name:
            break
    return [(n, raw[o * 16:ents[k + 1][1] * 16]) for k, (n, o) in enumerate(ents[:-1])], at


def qdat_write(members, head_size):
    """QDAT with members ([(name, bytes)]), each padded to a paragraph."""
    out = bytearray(head_size)
    body = bytearray()
    start = -(-head_size // 16) * 16
    out += bytes(start - head_size)
    for k, (n, m) in enumerate(members):
        out[16 * k:16 * k + 12] = n.encode("ascii").ljust(12, b"\x00")
        struct.pack_into("<I", out, 16 * k + 12, (start + len(body)) // 16)
        body += m + bytes(-len(m) % 16)
    struct.pack_into("<I", out, 16 * len(members) + 12, (start + len(body)) // 16)
    return bytes(out + body)


TABLE = 0xC8


def member_read(m):
    """[(answer, [question, choice 1, choice 2, choice 3])] of a member (strings without their 00)."""
    n = TABLE // 2
    out = []
    dec = m[:TABLE] + bytes(255 - b for b in m[TABLE:])
    for k in range(n):
        at = struct.unpack_from("<H", dec, 2 * k)[0]
        if not at:
            # (Yuu Disk Vol. 7's members: 50 questions, the table's rest 0)
            break
        offs = struct.unpack_from("<4H", dec, at)
        ans = dec[at + 8]
        strs = [dec[o:dec.index(0, o)] for o in offs]
        out.append((ans, strs))
    return out


def member_write(entries):
    """A member from [(answer, [4 strings])], its entries inverted past the table."""
    body = bytearray()
    table = []
    for ans, strs in entries:
        at = TABLE + len(body)
        table.append(at)
        offs, o = [], at + 9
        for s in strs:
            offs.append(o)
            o += len(s) + 1
        body += struct.pack("<4H", *offs) + bytes([ans]) + b"".join(s + b"\x00" for s in strs)
    if len(table) > TABLE // 2:
        raise SystemExit("a member's table holds 100 questions")
    head = b"".join(struct.pack("<H", t) for t in table) + bytes(TABLE - 2 * len(table))
    if TABLE + len(body) > 0x8000:
        raise SystemExit("a member of %d bytes; the program inverts at most 32 KB" % (TABLE + len(body)))
    return head + bytes(255 - b for b in body)


# ---- the program's strings

# the profiles: mov si, table / xor ah, ah / add ax, ax / add si, ax / mov si, [si] / call text
PROFILES_SIG = re.compile(rb"\xbe(..)\x32\xe4\x03\xc0\x03\xf0\x8b\x34\xe8", re.S)
SJIS_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20\x0a])+\x00", re.S)


def data_segment(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    return hdr, min(v for v in (struct.unpack_from("<H", exe, hdr + f)[0] for f in fixups) if v > code_seg)


def profiles(exe):
    """(the table's file offset, [its entries' file offsets (Yuu Disk Vol. 7's name four girls twice
    each)], [(start, end past the 00)] of the block's strings): the block is the run of profiles (each
    starting as the table's first does) around the ones the table names, the others kept as they are."""
    hdr, ds = data_segment(exe)
    base = hdr + ds * 16
    m = _one(exe[hdr:base], PROFILES_SIG, "profiles", "CHAN.EXE")
    t = base + struct.unpack("<H", m.group(1))[0]

    def string_at(a, after_nul=True):
        if not 0 < a < len(exe) or after_nul and exe[a - 1] != 0:
            return None
        ms = SJIS_STR.match(exe, a)
        return ms.end() if ms else None
    refs = []
    while True:
        a = base + struct.unpack_from("<H", exe, t + 2 * len(refs))[0]
        # (Moonlight Chan Rin Shan's first profile follows the table straight)
        if string_at(a, after_nul=False) is None:
            break
        refs.append(a)
    head = exe[refs[0]:refs[0] + 4]
    start, end = min(refs), string_at(max(refs), after_nul=False)
    while True:
        prev = exe.rfind(b"\x00", 0, start - 1) + 1
        if exe[prev:prev + 4] != head or string_at(prev) != start:
            break
        start = prev
    while exe[end:end + 4] == head and string_at(end):
        end = string_at(end)
    block, a = [], start
    while a < end:
        block.append((a, string_at(a, after_nul=False)))
        a = block[-1][1]
    return t, refs, block


def strings(exe):
    """[(file start, end past the 00)] of the program's other strings: the data segment's, and the code
    segment's with two kana or more."""
    hdr, ds = data_segment(exe)
    t, refs, block = profiles(exe)
    out = []
    for m in SJIS_STR.finditer(exe, hdr + ds * 16):
        if len(m.group()) >= 5 and not block[0][0] <= m.start() < block[-1][1]:
            out.append((m.start(), m.end()))
    for m in SJIS_STR.finditer(exe, hdr, hdr + ds * 16):
        t2 = m.group()[:-1].decode("cp932", "replace")
        # (two kana or more: code bytes read as kanji have none)
        if len(m.group()) >= 7 and sum(1 for c in t2 if "぀" <= c <= "ヿ") >= 2:
            out.append((m.start(), m.end()))
    return sorted(out)


# ---- a console program run before the game (Yuu Disk Vol. 7's PSTAT.EXE: DOS's text console)

CONSOLE_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x0a\x0d\x1b])+\x00", re.S)
SJIS_CHAR = re.compile(rb"[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]", re.S)
ESC_SEQ = re.compile(rb"\x1b\[[0-9;>]*[A-Za-z]", re.S)


def console_strings(exe):
    """[(start, end past the 00)] of a console program's messages: NUL-ended strings in its data
    segment with two Shift-JIS characters or more."""
    hdr, ds = data_segment(exe)
    out = []
    for m in CONSOLE_STR.finditer(exe, hdr + ds * 16):
        if len(SJIS_CHAR.findall(m.group())) >= 2:
            out.append((m.start(), m.end()))
    return out
