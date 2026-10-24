"""D.O.'s Branmarker (the floppy release: self-booting disks, DO the loader, DOS.SYS the program in one
64 KB segment, its overlays (the MAPnn modules, OPENG, BROE) loaded at 0B88Ch in the same segment): English
drawn half-width.

The message routine copies a text into a buffer (control codes below 0Dh, a space alone, every other
byte the first of a two-byte character) and draws it a character at a time: two bytes, a 16x16 glyph
read from the CG ROM by its JIS code (the Shift-JIS converted first), 16 dots on, two columns of the
row counted.

English (`patch_dos`) goes as pairs of ASCII letters, each pair a "character" of the routine: the glyph
fetch (`FETCH`) reads a pair's two 8x16 letters (the CG window's one-byte area, code high byte 0) into
the glyph's left and right halves, a kanji's two halves as before; the conversion runs inside it (its
own call made a `ret`).  A space is written 7Fh (the copy routine copies a space alone, so a pair must
not start with one), drawn as a space.  The room comes from the prompt's blink, an unrolled loop
written again as a loop (`BLINK`).
"""
import re
import struct

from .kuro import _asm16

CONV = re.compile(rb"\x80\xfe\x9e\x72\x05\x80\xee\xb1\xeb\x03\x80\xee\x71\x02\xf6\xfe\xc6\x80\xfa\x7f\x72\x02"
                  rb"\xfe\xca\x80\xfa\x9e\x73\x04\x80\xea\x1f\xc3\x80\xea\x7d\xfe\xc6\xc3")
FETCH = re.compile(rb"\x53\x51\x52\x57\xb0\x0b\xe6\x68\xbf\x10\x29\xbe\x01\x01\xbb\x00\x20\xb9\x10\x00"
                   rb"\x80\xee\x20.{39}\xb0\x0a\xe6\x68\x5f\x5a\x59\x5b\xc3", re.S)
BLINK = re.compile(rb"\x56\x06\xbb\x00\xa8\xb9\x00\x08\xba\x50\x00\x8e\xc3\x8b\x3e(..)\xbe(..)"
                   rb"(?:\xad\x26\x31\x05\x03\xfa\x26\x31\x05\x03\xfa){7}\xad\x26\x31\x05\x03\xfa\x26\x31\x05"
                   rb"\x03\xd9\x80\xff\xc0\x75\x02\xb7\xe0\x80\xff\xe8\x75\x93\x07\x5e\xc3", re.S)
# the message copy (text and its codes into the buffer; 04/05/06 names and numbers inserted), up to the
# number's handler that follows it
COPY = re.compile(re.escape(bytes.fromhex(
    "1e06b800108ec0bf4029ac3c0474363c0574343c0674333c0a7509ac32e426a38824ebe6aa3c0274153c0374113c0974"
    "0d3c0a74093c0c74053c207401a40ac075c8071fc3eb06eb3b90eb6490ac561e32e4bb8c26fec8c1e00203d8b800108e"
    "d8b00aaa32c0aa1ec537ac0ac07404aaa4ebf71fb009aab00aaaa18824aab0011f5eebbaac561ebb1c2832e4fec8d1e0"
    "03d8b800108ed88b07bb8c26fec8c1e00203d8c537ac0ac07404aaa4ebf7ebce")))
NUMBER_END = re.compile(rb"\xb0\x01\x1f\x5e\xe9(..)", re.S)   # the number's handler's way back
BUFFER_READ = re.compile(rb"\xbe\x40\x29")                     # the drawing's mov si, 2940h
SPACE = 0x7F
BANK = 0x1000      # DATA.SYS's segment: English that does not fit in place goes on after its end
BUFFER = 0xE800    # the message buffer, moved from 2940h (214 bytes) to 1000:E800 (1 KB, under the stack)
BUFFER_SIZE = 0x400
BANK_START = 0xCE70  # DATA.SYS's variables after its end reach CE66h
BANK_END = BUFFER    # the bank's room: up to the buffer
GOTO_BANK = 0x0E   # 0E lo hi: the text goes on at 1000:hi lo
GOTO_NEAR = 0x0F   # 0F lo hi: the text goes on at hi lo in the same segment (an overlay's own English)
ORG = 0x100  # DOS.SYS runs at offset 100h of its segment, as a .COM

CONV_NEW = """
conv:
    cmp dh, 0x9e
    jb c1
    sub dh, 0x40
c1:
    sub dh, 0x71
    add dh, dh
    inc dh
    cmp dl, 0x7f
    jb c2
    dec dl
c2:
    cmp dl, 0x9e
    jae c3
    sub dl, 0x1f
    .byte 0xc3
c3:
    sub dl, 0x7d
    inc dh
    .byte 0xc3
"""

FETCH_NEW = """
fetch:
    push bx
    push cx
    push dx
    push di
    cmp dh, 0x80
    jae f_kanji
    mov bl, dl
    mov cl, dh
    xor bh, bh
    xor ch, ch
    CALLN fix
    mov ax, {go}
    jmp ax
f_kanji:
    mov ax, {conv}
    call ax
    sub dh, 0x20
    mov bh, dl
    mov bl, dh
    mov cx, bx
    mov ax, {go}
    jmp ax
fix:
    cmp bl, {space}
    jne x1
    mov bl, 0x20
x1:
    cmp cl, {space}
    jne x2
    mov cl, 0x20
x2:
    .byte 0xc3
hi:
    cmp dh, 0xa0
    jb h1
    and dh, 0x7f
h1:
    .byte 0xc3
"""

COPY_NEW = """
copy:
    push ds
    push es
    .byte 0x68
    .word 0x1000
    pop es
    mov di, {buf}
c_loop:
    lodsb
    cmp al, 4
    je c_name
    cmp al, 5
    je c_plain
    cmp al, 6
    je c_number
    cmp al, 0x0a
    jne c_2
    lodsb
    xor ah, ah
    mov word ptr es:[0x2488], ax
    jmp c_loop
c_2:
    cmp al, 0x0e
    je c_bank
    cmp al, 0x0f
    je c_near
    stosb
    cmp al, 2
    je c_next
    cmp al, 3
    je c_next
    cmp al, 9
    je c_next
    cmp al, 0x0c
    je c_next
    cmp al, 0x20
    je c_next
    movsb
c_next:
    or al, al
    jne c_loop
    pop es
    pop ds
    .byte 0xc3
c_number:
    .byte 0xe9
    .word {number}
c_bank:
    lodsw
    xchg si, ax
    .byte 0x68
    .word 0x1000
    pop ds
    jmp c_loop
c_near:
    lodsw
    xchg si, ax
    jmp c_loop
c_name:
    lodsb
    push si
    push ds
    xor ah, ah
    CALLN c_index
    .byte 0x68
    .word 0x1000
    pop ds
    mov ax, 0x000a
    stosw
    push ds
    lds si, [bx]
    CALLN c_pairs
    pop ds
    mov ax, 0x0a09
    stosw
    mov ax, word ptr [0x2488]
    stosb
c_done:
    mov al, 1
    pop ds
    pop si
    jmp c_next
c_plain:
    lodsb
    push si
    push ds
    mov bx, 0x281c
    xor ah, ah
    dec al
    shl ax, 1
    add bx, ax
    .byte 0x68
    .word 0x1000
    pop ds
    mov ax, word ptr [bx]
    CALLN c_index
    lds si, [bx]
    CALLN c_pairs
    jmp c_done
c_index:
    mov bx, 0x268c
    dec al
    shl ax, 2
    add bx, ax
    .byte 0xc3
c_pairs:
    lodsb
    or al, al
    je c_p1
    stosb
    movsb
    jmp c_pairs
c_p1:
    .byte 0xc3
"""

BLINK_NEW = """
blink:
    push si
    push es
    mov bx, 0xa800
    mov cx, 0x800
    mov dx, 0x50
b1:
    mov es, bx
    mov di, word ptr [{pos}]
    mov si, {buf}
    push cx
    mov cx, 8
b2:
    lodsw
    xor word ptr es:[di], ax
    add di, dx
    xor word ptr es:[di], ax
    add di, dx
    loop b2
    pop cx
    add bx, cx
    cmp bh, 0xc0
    jne b3
    mov bh, 0xe0
b3:
    cmp bh, 0xe8
    jne b1
    pop es
    pop si
    .byte 0xc3
go:
    mov al, 0x0b
    out 0x68, al
    mov di, 0x2910
    mov dx, 0x2000
g1:
    mov al, bh
    out 0xa1, al
    mov al, bl
    out 0xa3, al
    mov al, dl
    out 0xa5, al
    in al, 0xa9
    mov ah, al
    mov al, ch
    out 0xa1, al
    mov al, cl
    out 0xa3, al
    mov al, dh
    out 0xa5, al
    in al, 0xa9
    stosw
    add dx, 0x101
    cmp dl, 0x10
    jb g1
    mov al, 0x0a
    out 0x68, al
    pop di
    pop dx
    pop cx
    pop bx
    .byte 0xc3
"""


def _once(pat, b, name, what):
    hits = list(pat.finditer(b))
    if len(hits) != 1:
        raise SystemExit("%s: the %s is found %d times, not once" % (name, what, len(hits)))
    return hits[0]


def patch_dos(dos, name="DOS.SYS"):
    """DOS.SYS with the pairs of letters drawn (see the module's docstring)."""
    d = bytearray(dos)
    cv = _once(CONV, bytes(d), name, "Shift-JIS conversion")
    ft = _once(FETCH, bytes(d), name, "glyph fetch")
    bl = _once(BLINK, bytes(d), name, "prompt's blink")
    conv_at = cv.start() + 1
    code, _a = _asm16(CONV_NEW, ORG + conv_at, ["conv"])
    if len(code) > cv.end() - conv_at:
        raise SystemExit("%s: the conversion does not fit" % name)
    d[cv.start()] = 0xC3
    d[conv_at:conv_at + len(code)] = code
    pos, buf = struct.unpack("<H", bl.group(1))[0], struct.unpack("<H", bl.group(2))[0]
    src = BLINK_NEW.format(pos=hex(pos), buf=hex(buf))
    code, addr = _asm16(src, ORG + bl.start(), ["blink", "go"])
    if len(code) > bl.end() - bl.start():
        raise SystemExit("%s: the blink and the fetch's loop do not fit" % name)
    d[bl.start():bl.start() + len(code)] = code
    code, addr = _asm16(FETCH_NEW.format(go=hex(addr["go"]), conv=hex(ORG + conv_at), space=hex(SPACE)),
                        ORG + ft.start(), ["fetch", "fix", "hi"])
    if len(code) > ft.end() - ft.start():
        raise SystemExit("%s: the glyph fetch does not fit" % name)
    d[ft.start():ft.end()] = code + b"\x90" * (ft.end() - ft.start() - len(code))
    hi = addr["hi"]
    cp = _once(COPY, bytes(d), name, "message copy")
    back = NUMBER_END.search(bytes(d), cp.end(), cp.end() + 0x30)
    if not back:
        raise SystemExit("%s: the number's handler is not after the message copy" % name)
    src = COPY_NEW.format(buf=hex(BUFFER), number="0")
    code, addr = _asm16(src, ORG + cp.start(), ["copy", "c_next", "c_number"])
    rel = (ORG + cp.end() - (addr["c_number"] + 3)) & 0xFFFF   # the near jump into the number's handler
    code, addr = _asm16(COPY_NEW.format(buf=hex(BUFFER), number=hex(rel)), ORG + cp.start(),
                        ["copy", "c_next", "c_number"])
    if len(code) > cp.end() - cp.start():
        raise SystemExit("%s: the message copy does not fit" % name)
    d[cp.start():cp.end()] = code + b"\x90" * (cp.end() - cp.start() - len(code))
    d[back.start(1):back.end(1)] = struct.pack("<H", (addr["c_next"] - (ORG + back.end(1))) & 0xFFFF)
    rd = _once(BUFFER_READ, bytes(d), name, "message buffer's reading")
    d[rd.start() + 1:rd.end()] = struct.pack("<H", BUFFER)
    return bytes(d), {"conv": ORG + cv.start(), "hi": hi}


# an overlay's own character loop: xchg ah,al / mov dx,ax / call the conversion
MODULE_CHAR = re.compile(rb"\x86\xc4\x8b\xd0\xe8(..)", re.S)
MODULE_AT = 0xB98C  # where DOS.SYS loads its overlays
MODULE_END = 0xE000  # an overlay's English after its end stays below the program's own (DOS_HIGH)
DOS_HIGH = 0xE000    # the program's English that does not fit in place: E000h-EFFFh of its segment
DOS_HIGH_END = 0xF000  # (loaded with it, the file made longer; no overlay but BROE reaches it)


def patch_module(mod, entries, base=MODULE_AT):
    """An overlay with its own character loop (OPENG, BROE, the omake program's copy of BROE's loops):
    its calls of the conversion made calls of `hi`, which takes a first byte A0h-FFh for a pair's first
    letter (its low 7 bits)."""
    d = bytearray(mod)
    n = 0
    for m in MODULE_CHAR.finditer(mod):
        at = base + m.end(1)
        if (at + struct.unpack("<h", m.group(1))[0]) & 0xFFFF != entries["conv"]:
            continue
        d[m.start(1):m.end(1)] = struct.pack("<H", (entries["hi"] - at) & 0xFFFF)
        n += 1
    return bytes(d), n


def pairs(text):
    """ASCII as the routine's pairs: a space 7Fh, an odd run made even with a space."""
    b = text.encode("ascii").replace(b" ", bytes([SPACE]))
    return b + (bytes([SPACE]) if len(b) % 2 else b"")


def high_pairs(text):
    """Pairs for an overlay's character loop: each pair's first letter with its high bit set."""
    b = bytearray(pairs(text))
    for i in range(0, len(b), 2):
        b[i] |= 0x80
    return bytes(b)


# ---- texts in the programs, the overlays and DATA.SYS ----
#
# A message is a run of elements up to a 00: a code with its byte (01 colour, 04 n a speaker's name on
# its own line, 05 n a name the game puts in, 06 n a number, 07 n a face, 08 n an effect, 0A n an
# attribute, 0B n a wait), a code alone (02 and 09 new lines, 09 counting the window's lines and paging,
# 03 a key and the window cleared, 0C a key), a lone space, or a two-byte character.  A plain string
# (menus, names, items, the load prompt) is two-byte characters up to a 00, drawn by the plain drawer.

ARG1 = frozenset((1, 4, 5, 6, 7, 8, 0x0A, 0x0B))
SINGLE = frozenset((2, 3, 9, 0x0C))
LINE_START = frozenset((2, 3, 4, 9, 0x0C))   # codes after which the text starts a line
WIDTH = 40           # letters on a line of the message window (40 columns, a letter a column)
NAME_WIDTH = 12      # the room allowed for a name the game puts in (05 n) when breaking lines
NUMBER_WIDTH = 6     # and for a number (06 n, full-width digits)
RUN = re.compile(rb"(?:[\x81-\x84\x88-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){2,}")
KANA = re.compile("[぀-ヿ、。！？「」・ー]")
# the plain string drawer: ds from ax, the string at si up to a 00, a lone space half a cell
PLAIN = re.compile(rb"\x1e\x06\x8e\xd8\xb8\x00\x10\x8e\xc0\xe8..\xe8\x03\x00\x07\x1f\xc3\xac\x8a\xf0\x0a\xf6"
                   rb"\x74\x13\x80\xfe\x20\x75\x03\x47\xeb\xf1", re.S)
TOKEN = re.compile(r"\{([NV])(\d+)\}")
REAL_KANA = re.compile("[ぁ-ヺ]")


def _lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def _rare(b):
    """Whether two-byte characters include a JIS level-2 kanji (from 989Fh): without kana, bytes of code
    that happen to read as characters."""
    return any(b[i] << 8 | b[i + 1] >= 0x989F for i in range(0, len(b) - 1, 2) if _lead(b[i]))


def elements(d, p, limit=4000):
    """A message's elements from p up to its 00: [(start, end)], None where a byte breaks the grammar."""
    out = []
    s = p
    while p < len(d) and p - s < limit:
        b = d[p]
        if b == 0:
            out.append((p, p + 1))
            return out
        if b in ARG1:
            n = 2
        elif b in SINGLE or b == 0x20:
            n = 1
        elif _lead(b) and p + 1 < len(d) and 0x40 <= d[p + 1] <= 0xFC:
            n = 2
        else:
            return None
        out.append((p, p + n))
        p += n
    return None


def show(d, s, e):
    """A text as strings.json shows it: 09 a new line, 05 n {Nn}, 06 n {Vn}."""
    out, p = [], s
    while p < e:
        b = d[p]
        if b == 9:
            out.append("\n")
            p += 1
        elif b == 0x20:
            out.append(" ")
            p += 1
        elif b in (5, 6):
            out.append("{%s%d}" % ("N" if b == 5 else "V", d[p + 1]))
            p += 2
        else:
            out.append(d[p:p + 2].decode("cp932"))
            p += 2
    return "".join(out)


class Text:
    """A text in a file: bytes [start, end), its message's end (after the 00), message or plain."""

    def __init__(self, start, end, rec_end, message):
        self.start, self.end, self.rec_end, self.message = start, end, rec_end, message


def _calls(d, base):
    """{address: [routines called after a mov si of it]}"""
    out = {}
    for m in re.finditer(rb"\xbe(..)", d, re.S):
        x = struct.unpack("<H", m.group(1))[0]
        p = m.end()
        for _ in range(4):        # the next few instructions: the first call
            if p + 3 > len(d):
                break
            if d[p] == 0xE8:
                out.setdefault(x, []).append((base + p + 3 + struct.unpack_from("<h", d, p + 1)[0]) & 0xFFFF)
                break
            p += {0xB8: 3, 0xB9: 3, 0xBA: 3, 0xBB: 3, 0xBF: 3, 0x8C: 2, 0x8E: 2, 0x1E: 1, 0x06: 1, 0x57: 1,
                  0x56: 1, 0x50: 1, 0x0E: 1}.get(d[p], 99)
            if p > len(d):
                break
    return out


def texts(d, base, plain=None, data=False):
    """The texts of a program, an overlay or (data) DATA.SYS, in order.  `plain` the plain drawer's address:
    a string a mov si of which is followed by a call of it, or one in a packed table of strings (three or
    more without codes, only 00s between them), is plain; DATA.SYS's are all plain; the rest messages."""
    calls = {} if data else _calls(d, base)
    words = {struct.unpack_from("<H", d, i)[0] for i in range(len(d) - 1)}
    out = []
    taken = 0
    for m in RUN.finditer(d):
        a = m.start()
        if a < taken:
            continue
        els = elements(d, a)
        if not els:
            continue
        try:
            t = show(d, a, m.end())
        except UnicodeDecodeError:
            continue
        if not REAL_KANA.search(t) and (_rare(d[a:m.end()]) or
                                   not (a and d[a - 1] in (0, *SINGLE) or a > 1 and d[a - 2] in ARG1)):
            continue
        end = a
        for p, q in els:
            b = d[p]
            if _lead(b) or b in (5, 6):
                end = q
            elif b not in (9, 0x20):
                break
        s = a
        if a >= 3 and d[a - 2] in (5, 6) and (d[a - 3] in (0, 0x20, *SINGLE) or base + a - 2 in words or
                                             a >= 4 and (d[a - 4] in ARG1 or _lead(d[a - 4]))):
            s = a - 2
        rec_end = els[-1][1]
        codes = s < a or any(d[p] in ARG1 or d[p] in SINGLE for p, _q in els)
        routines = [r for k in range(max(0, s - 6), s + 1) for r in calls.get(base + k, [])]
        t = Text(s, end, rec_end, not data)
        t.codes = codes or s and (d[s - 1] in SINGLE or s > 1 and d[s - 2] in ARG1)
        if routines and all(r == plain for r in routines):
            t.message = False
        out.append(t)
        taken = end
    # packed tables of plain strings
    run = []
    for t in out + [None]:
        if t is not None and not t.codes and (not run or t.start - run[-1].rec_end <= 1):
            run.append(t)
            continue
        if len(run) >= 3:
            for x in run:
                x.message = False
        run = [t] if t is not None and not t.codes else []
    return out


def plain_drawer(dos):
    """The plain drawer's address in a DOS.SYS."""
    m = _once(PLAIN, dos, "DOS.SYS", "plain string drawer")
    return ORG + m.start()


# ---- the opening's and the ending's texts ----
#
# OPENG, BROE and the omake program's copy of BROE draw their texts from streams of their own: a byte
# below 80h an operation (a line's place, a wait, a picture, the speaker's mouth (1xh) every two
# characters, ...), a pair of bytes from 80h a character.  The staff roll's streams: a byte below 20h
# lines down, 20h-7Fh columns along, a pair from 80h a character, 00 the end.  Their English goes in
# place as pairs of letters (each pair's first byte with its high bit set: `high_pairs`), the mouth's
# operations spread over it as over the Japanese, room left over filled with waits of a tick (30h) or,
# on a staff roll, a column along (21h).

CHAR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+")
MOUTH = range(0x10, 0x20)
WAIT_TICK = 0x30
ARGS_OP = frozenset((2, 3, 4, 6, 7, 8, 9, 0x0C))   # operations with an argument after them
COLUMN = 0x21


class Scene:
    """A text of a stream: bytes [start, end), its mouth operations, staff roll or story."""

    def __init__(self, start, end, mouths, staff):
        self.start, self.end, self.mouths, self.staff = start, end, mouths, staff

    @property
    def room(self):
        """Letters it holds: the Japanese's bytes without its operations."""
        return self.end - self.start - len(self.mouths)


def _op(b):
    return 0x10 <= b < 0x80 and b != 0x20


def scenes(d, lo=0, hi=None, staff_from=None):
    """The stream texts in d[lo:hi]: a run of characters next to an operation byte, with the mouth's
    operations and the runs after them.  From `staff_from` on, the staff roll's (no mouth)."""
    hi = len(d) if hi is None else hi
    out = []
    taken = lo
    for m in CHAR.finditer(d, lo, hi):
        a = m.start()
        if a < taken:
            continue
        try:
            d[a:m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        staff = staff_from is not None and a >= staff_from
        if not staff and not KANA.search(d[a:m.end()].decode("cp932")) and _rare(d[a:m.end()]):
            continue
        before = d[a - 1] if a else 0
        after = d[m.end()] if m.end() < len(d) else 0
        if not staff and before in ARGS_OP:
            continue                  # an operation's argument
        if staff:
            if not (0 < before < 0x80 or before == 0):
                continue
        elif not (_op(before) or _op(after) or before == 0 and _op(after)):
            continue
        e, mouths = m.end(), []
        while not staff and e + 2 < hi and d[e] in MOUTH:
            n = CHAR.match(d, e + 1)
            if not n:
                break
            mouths.append(d[e])
            e = n.end()
        out.append(Scene(a, e, mouths, staff))
        taken = e
    return out


def scene_show(d, s):
    """The Japanese of a stream text (its operations left out)."""
    out, p = [], s.start
    while p < s.end:
        if d[p] in MOUTH and p not in (s.start,):
            p += 1
            continue
        out.append(d[p:p + 2].decode("cp932"))
        p += 2
    return "".join(out)


def encode_scene(s, text):
    """A stream text's English in its room: pairs with the high bit, the mouth every two pairs."""
    pairs_ = high_pairs(text)
    room = s.end - s.start
    if len(pairs_) > room:
        raise ValueError("%d letters, room for %d" % (len(pairs_), s.room))
    out = bytearray()
    k = 0
    for i in range(0, len(pairs_), 2):
        out += pairs_[i:i + 2]
        if s.mouths and i % 4 == 2 and len(out) + 1 + len(pairs_) - i - 2 <= room:
            out.append(s.mouths[k % len(s.mouths)])
            k += 1
    out += bytes([COLUMN if s.staff else WAIT_TICK]) * (room - len(out))
    return bytes(out)


# ---- English in the messages ----

WORDS = re.compile(r"\{([NV])(\d+)\}|(\{D\})|\n|[ ]+|[^ \n{]+|\{")
LETTER = re.compile(rb"\x2e\x88\x16(..)", re.S)   # mov cs:[x], dl: a disk's letter put in a prompt
DISK_LETTER = "Ｂ".encode("cp932")            # the letter's place in the English: a full-width B


def letters(d, base):
    """{file offset of a prompt's disk letter (its first byte): offset of the address the program
    writes the letter's second byte to}"""
    out = {}
    for m in LETTER.finditer(d):
        x = struct.unpack("<H", m.group(1))[0] - 1 - base
        if 0 <= x < len(d) - 1 and _lead(d[x]):
            out[x] = m.start(1)
    return out


def _words(text):
    """Paragraphs of words, a word [pieces]: ("t", letters) or ("i", code bytes, width)."""
    paras, words, cur = [], [], []
    for m in WORDS.finditer(text):
        g = m.group()
        if m.group(3):
            cur.append(("i", DISK_LETTER, 2))
        elif m.group(1):
            cur.append(("i", bytes([5 if m.group(1) == "N" else 6, int(m.group(2))]),
                        NAME_WIDTH if m.group(1) == "N" else NUMBER_WIDTH))
        elif g == "\n":
            if cur:
                words.append(cur)
            paras.append(words)
            words, cur = [], []
        elif g.isspace():
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(("t", g))
    if cur:
        words.append(cur)
    paras.append(words)
    return paras


def _width(word):
    return sum(len(p[1]) if p[0] == "t" else p[2] for p in word)


def _split(word, room):
    """A word wider than a line cut at `room` letters (its letters only)."""
    head, tail, w = [], [], 0
    for p in word:
        if tail or p[0] == "i" and w + p[2] > room:
            tail.append(p)
        elif p[0] == "i":
            head.append(p)
            w += p[2]
        elif w + len(p[1]) <= room:
            head.append(p)
            w += len(p[1])
        else:
            k = room - w
            if k > 0:
                head.append(("t", p[1][:k]))
            tail.append(("t", p[1][k:]))
            w = room
    return head, tail


def _line(words):
    """A line's elements and its width: letters in pairs, inserts as their codes."""
    out, run, w = [], "", 0
    for i, word in enumerate(words):
        if i:
            run += " "
        for p in word:
            if p[0] == "t":
                run += p[1]
            else:
                if run:
                    b = pairs(run)
                    out += [b[k:k + 2] for k in range(0, len(b), 2)]
                    w += len(b)
                    run = ""
                out.append(p[1])
                w += p[2]
    if run:
        b = pairs(run)
        out += [b[k:k + 2] for k in range(0, len(b), 2)]
        w += len(b)
    return out, w


def encode_message(text, col=0):
    """A message text's English: ([element bytes], the column after it).  Letters go in pairs (a space
    7Fh), lines broken between words at WIDTH letters with 09 (none after a line that fills the window,
    which goes on to the next line itself), \\n a new line, {Nn}/{Vn} the game's name or number."""
    out = []
    for k, para in enumerate(_words(text)):
        if k:
            out.append(b"\x09")
            col = 0
        line, w = [], col
        queue = list(para)
        while queue:
            word = queue.pop(0)
            ww = _width(word)
            need = ww + (1 if line else 0)
            if w + need <= WIDTH:
                line.append(word)
                w += need
                continue
            if line:
                els, lw = _line(line)
                out += els
                if col + lw < WIDTH:
                    out.append(b"\x09")
                col, line, w = 0, [], 0
                queue.insert(0, word)
                continue
            head, tail = _split(word, WIDTH - w)     # a word longer than the line
            els, lw = _line([head])
            out += els
            if col + lw < WIDTH:
                out.append(b"\x09")
            col, w = 0, 0
            if tail:
                queue.insert(0, tail)
        if line:
            els, lw = _line(line)
            out += els
            col += lw
            if col >= WIDTH:
                col = 0
    return out, col


class Placer:
    """Where English that does not fit in place goes: `code` 0E (DATA.SYS's bank, at `at` in segment
    1000h) or 0F (in the text's own segment, `at` its address), up to `limit`; `then` another Placer for
    what does not fit in this one."""

    def __init__(self, code, at, limit, what, then=None):
        self.code, self.at, self.limit, self.what, self.then = code, at, limit, what, then
        self.data = bytearray()

    def put(self, b):
        a = self.at + len(self.data)
        if a + len(b) > self.limit:
            if self.then:
                return self.then.put(b)
            raise ValueError("%s: the English does not fit (%d bytes over)" % (self.what, a + len(b) - self.limit))
        self.data += b
        return bytes([self.code]) + struct.pack("<H", a)


def references(d, base, starts, inside=()):
    """Addresses code or tables point at among `starts` (texts' and their codes' places): a mov's
    immediate, or two or more pointers side by side (two or four bytes apart) outside the messages
    (`inside`: their [start, end) ranges)."""
    starts = set(starts)
    out = set()
    text = bytearray(len(d))
    for a, b in inside:
        text[a:b] = bytes([1]) * (b - a)
    for m in re.finditer(rb"[\xb8-\xbf](..)", d, re.S):
        v = struct.unpack("<H", m.group(1))[0]
        if v in starts:
            out.add(v)
    for i in range(len(d) - 5):
        if text[i]:
            continue
        v = struct.unpack_from("<H", d, i)[0]
        if v in starts and (struct.unpack_from("<H", d, i + 2)[0] in starts or
                            i + 6 <= len(d) and struct.unpack_from("<H", d, i + 4)[0] in starts):
            out.add(v)
            out.add(struct.unpack_from("<H", d, i + 2)[0])
            if i + 6 <= len(d):
                out.add(struct.unpack_from("<H", d, i + 4)[0])
    return out & starts


def patch_messages(d, base, items, place, words=frozenset()):
    """Write the English of a file's messages.  items: [(Text, English or None)] (messages only, in order);
    place: the Placer for what does not fit; words: addresses other code may point at (a message entered
    part way, at one of its texts or the codes before it, is written from there on its own)."""
    groups = {}
    for t, en in items:
        groups.setdefault(t.rec_end, []).append((t, en))
    for rec_end, grp in groups.items():
        if not any(en for _t, en in grp):
            continue
        grp.sort(key=lambda x: x[0].start)
        # where the message may be entered: its first text, a later text or the codes just before it
        starts = [grp[0][0].start]
        for (t0, _e0), (t, _e) in zip(grp, grp[1:]):
            p = t0.end
            while p < t.start:
                if base + p in words and p - starts[-1] >= 3:
                    starts.append(p)
                    break
                b = d[p]
                p += 2 if b in ARG1 or _lead(b) else 1
            else:
                if base + t.start in words and t.start - starts[-1] >= 3:
                    starts.append(t.start)
        texts_at = {t.start: (t, en) for t, en in grp}

        def run(p, q):
            """Elements from p to q, English for the texts, and the column."""
            out, col = [], 0
            while p < q:
                if p in texts_at and texts_at[p][1]:
                    t, en = texts_at[p]
                    els, col = encode_message(en, col)
                    out += els
                    p = t.end
                    continue
                b = d[p]
                n = 2 if b in ARG1 or _lead(b) else 1
                out.append(bytes(d[p:p + n]))
                if b in LINE_START:
                    col = 0
                elif _lead(b):
                    col += 2
                p += n
            return out

        for i, p in enumerate(starts):
            q = starts[i + 1] if i + 1 < len(starts) else rec_end
            room = q - p
            own = run(p, q)
            size = sum(map(len, own))
            if i + 1 < len(starts) and size + 3 <= room:
                blob = b"".join(own) + bytes([GOTO_NEAR]) + struct.pack("<H", base + q)
            elif i + 1 == len(starts) and size <= room:
                blob = b"".join(own)
            else:
                full = run(p, rec_end)
                k, used = 0, 0
                while k < len(full) and used + len(full[k]) + 3 <= room:
                    used += len(full[k])
                    k += 1
                blob = b"".join(full[:k]) + place.put(b"".join(full[k:]))
            d[p:q] = blob + b"\0" * (room - len(blob))


def patch_plain(d, start, room, text, high=False):
    """A plain string's English in place: up to `room` letters, a 00 after it."""
    b = high_pairs(text) if high else pairs(text)
    if len(b) > room:
        raise ValueError("%d letters, room for %d" % (len(b), room))
    d[start:start + room] = b + b"\0" * (room - len(b))


def patch_prompt(d, base, start, room, text, site):
    """A disk prompt's English in place ({D} the disk's letter, which the program writes there): the
    program's write of the letter (its address at `site`) pointed at the letter's new place."""
    els, _col = encode_message(text)
    b = b"".join(els)
    if len(b) > room:
        raise ValueError("%d bytes, room for %d" % (len(b), room))
    at = 0
    for e in els:
        if e == DISK_LETTER:
            break
        at += len(e)
    else:
        raise ValueError("no {D} for the disk's letter")
    d[start:start + room] = b + bytes(room - len(b))
    d[site:site + 2] = struct.pack("<H", base + start + at + 1)
