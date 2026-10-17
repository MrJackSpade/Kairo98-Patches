"""FamilySoft's Dies Irae (DIESIRAE\\DIES01.EXE): its scenario scripts (*.CEN), and English drawn half-width.

A script (`decode`, `encode`): "CEN" and a 0, then its text with every byte stored one less.  The text is
lines (CR LF) the program reads a byte at a time (`tokens`):

* ' a comment, to the line's end; space, CR, LF and 1Ah are skipped (so a message runs on across lines);
* # a command, to the line's end (#MK a,b a block, #CF / #CN a block on a flag, #ED a block's end;
  #MK a,1 is a menu: each line in it, outside a further #MK, one choice);
* * a code: letters, a space, a number (*F a face, *C a colour, *W a wait...);
* \\ and a letter: \\R a new line, \\P a wait and a new page, \\E the message's end (a wait), \\C a clear;
* __ and 1Ah: the script's end;
* any other byte and the one after it: a character, drawn full width (16 dots) from CG ROM.

DIES01.EXE reads a scene's script and then 000.CEN (the shared messages: errors, saving, the system
menu) into one buffer and makes its bytes one more, up to a count (17000 bytes; made `SCRIPT_LIMIT`,
the buffer `BUFFER`, by `patch_program`).

The message window is 24 characters (x 88h-200h, 16 dots each) by 3 lines; the program breaks a line at
its edge (at any character) and, past the third line, waits for a key and starts a new page.

English (`message`, `choice`, `patch_program`): two letters a character, as two-byte codes of printable
ASCII bytes (`LEADS`, `TRAILS`: none of # * \\ ' @ _ space, which the program reads as marks); the
glyph routine is made to jump, before its CG ROM read, to a helper in a segment of its own put in before
DGROUP (pc98tl/adl5.py `_move_up`) that, for such a code, fills the glyph buffer from two 8x16 BIOS glyphs
(int 18h AH=14h).  The patcher breaks the English between words at 48 letters with \\R; the program pages.
"""
import re
import struct

from .adl5 import _move_up
from .kuro import _asm16, _exe

HEAD = b"CEN\0"
LETTERS = (" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
           ".,'\"!?-:;()")
MARKS = b"#*\\'@_ "
LEADS = [b for b in range(0x21, 0x7F) if b not in MARKS]
TRAILS = [b for b in range(0x21, 0x7F) if b not in MARKS]
LINE = 48                                   # letters a line (24 characters)
CHOICE_ROOM = 10                            # a menu's box: x 1D8h-278h, 10 characters
CODE = re.compile(rb"\*[A-Z]{1,2} ?[0-9]*(?:,[0-9]+)*")
TOKEN = re.compile(r"\{([A-Z]{1,2})(-?[0-9,]*)\}")
assert len(LETTERS) ** 2 <= len(LEADS) * len(TRAILS)


def decode(data):
    """A script's text (its bytes one more) and the bytes after the end mark kept as they are."""
    if not data.startswith(HEAD):
        raise ValueError("not a CEN script")
    return bytes((b + 1) & 0xFF for b in data[4:])


def encode(text):
    return HEAD + bytes((b - 1) & 0xFF for b in text)


def tokens(t):
    """[(kind, start, end)]: comment, skip, cmd, code, esc, end, char."""
    out, i = [], 0
    while i < len(t):
        b = t[i]
        if b == 0x27:
            e = t.find(b"\r\n", i)
            e = len(t) if e < 0 else e
            out.append(("comment", i, e))
        elif b in (0x20, 0x0D, 0x0A, 0x1A):
            out.append(("skip", i, i + 1))
            e = i + 1
        elif b == 0x23 or b == 0x40:
            e = t.find(b"\r\n", i)
            e = len(t) if e < 0 else e
            out.append(("cmd", i, e))
        elif b == 0x2A:
            m = CODE.match(t, i)
            e = m.end() if m else i + 1
            out.append(("code", i, e))
        elif b == 0x5C:
            e = i + 2
            out.append(("esc", i, e))
        elif t[i:i + 2] == b"__":
            out.append(("end", i, len(t)))
            e = len(t)
        else:
            e = i + 2
            out.append(("char", i, min(e, len(t))))
        i = e
    return out


def units(t):
    """[(start, end, kind)] of the script's text: kind msg (a message: characters and the codes among
    them, up to an escape or a command) or choice (a line of a menu)."""
    out, stack, run = [], [], None

    def close():
        nonlocal run
        if run:
            out.append(run)
        run = None

    def menu():
        for kind, b in reversed(stack):
            if kind == "MK":
                return b == 1
        return False

    for kind, s, e in tokens(t):
        if kind == "char":
            if run and run[2] == "choice" and b"\n" in t[run[1]:s]:
                close()
            run = (run[0], e, run[2]) if run else (s, e, "choice" if menu() else "msg")
            continue
        if kind in ("skip", "code"):
            continue
        close()
        if kind == "cmd":
            c = t[s:e]
            m = re.match(rb"#MK ?(\d+)(?:,(\d+))?", c)
            if m:
                stack.append(("MK", int(m.group(2) or 0)))
            elif re.match(rb"#C[FN]", c):
                stack.append(("C", 0))
            elif c.startswith(b"#ED") and stack:
                stack.pop()
    close()
    return out


def show(t):
    """A unit as strings.json shows it: its characters, its codes as {Xn}; skipped bytes dropped."""
    out = []
    for kind, s, e in tokens(t):
        if kind == "char":
            out.append(t[s:e].decode("cp932", "replace"))
        elif kind == "code":
            out.append("{%s}" % t[s + 1:e].decode("ascii").replace(" ", ""))
    return "".join(out)


def codes(t):
    """{token: the code's bytes} of a unit's codes."""
    return {"{%s}" % t[s + 1:e].decode("ascii").replace(" ", ""): t[s:e]
            for kind, s, e in tokens(t) if kind == "code"}


def _normal(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if c in LETTERS or c == "\n" else "?" for c in s)


def _pair(a, b):
    k = LETTERS.index(a) * len(LETTERS) + LETTERS.index(b)
    return bytes([LEADS[k // len(TRAILS)], TRAILS[k % len(TRAILS)]])


def _pairs(letters):
    if len(letters) % 2:
        letters += " "
    return b"".join(_pair(letters[k], letters[k + 1]) for k in range(0, len(letters), 2))


def _items(text, known):
    """English as [(kind, value)]: text pieces, codes (their bytes), new lines."""
    out, last = [], 0
    for m in TOKEN.finditer(text):
        out.append(("text", text[last:m.start()]))
        if m.group(0) not in known:
            raise ValueError("%s is not one of the Japanese's codes" % m.group(0))
        out.append(("code", known[m.group(0)]))
        last = m.end()
    out.append(("text", text[last:]))
    return out


def message(text, known):
    """A message's English as the script holds it: broken between words at LINE letters with \\R (not
    after a full line, which the program breaks itself); codes kept where they are."""
    lines, line, width = [], [], 0          # line: [(kind, value)]
    for kind, val in _items(text, known):
        if kind == "code":
            line.append(("code", val))
            continue
        for n, para in enumerate(_normal(val).split("\n")):
            if n:
                lines.append((line, width))
                line, width = [], 0
            for word in re.findall(r"\S+|\s+", para):
                if word.isspace():
                    if width and width < LINE:
                        line.append(("text", " "))
                        width += 1
                    continue
                if width + len(word) > LINE and width:
                    while line and line[-1] == ("text", " "):
                        line.pop()
                        width -= 1
                    lines.append((line, width))
                    line, width = [], 0
                while len(word) > LINE:
                    lines.append(([("text", word[:LINE])], LINE))
                    word = word[LINE:]
                line.append(("text", word))
                width += len(word)
    lines.append((line, width))
    out = bytearray()
    for n, (line, width) in enumerate(lines):
        if n and lines[n - 1][1] < LINE - 1:
            out += b"\\R"
        pend = ""
        for kind, val in line:
            if kind == "text":
                pend += val
            else:
                out += _pairs(pend) + val
                pend = ""
        out += _pairs(pend)
    return bytes(out)


def choice(text, known, room):
    """A choice's English: one line, cut to `room` characters (two letters each)."""
    out, cut, letters = bytearray(), False, 0
    for kind, val in _items(text.replace("\n", " "), known):
        if kind == "code":
            out += val
            continue
        val = _normal(val)
        left = 2 * room - letters
        if len(val) > left:
            val, cut = val[:max(0, left)], True
        letters += len(val) + len(val) % 2
        out += _pairs(val)
    return bytes(out), cut


def rebuild(t, new):
    """`t` with each unit {start: (end, bytes)} replaced."""
    out, last = bytearray(), 0
    for s in sorted(new):
        e, b = new[s]
        out += t[last:s] + b
        last = e
    return bytes(out + t[last:])


# ---- DIES01.EXE ----------------------------------------------------------------------------------------

# the glyph routine: mov al, 0Bh / out 68h, al / (mov ax, [bp+4] / xchg al, ah) / shl ah, 1 / sub al, 1Fh
# ... the CG ROM read into the buffer ... / (mov al, 0Ah / out 68h, al)
GLYPH_SIG = re.compile(rb"\xb0\x0b\xe6\x68(\x8b\x46\x04\x86\xe0)\xd0\xe4\x2c\x1f\x78\x04\x3c\x61\x14\xde"
                       rb"\x05\xa1\x1f\x25\x7f\x7f\x80\xec\x20\xe6\xa1\x86\xe0\xe6\xa3.{8,40}?\xbf(..)"
                       rb".{0,60}?(\xb0\x0a\xe6\x68)", re.S)
# the entry: mov dx, DGROUP / mov cs:[x], dx
ENTRY_SIG = re.compile(rb"\xba(..)\x2e\x89\x16", re.S)
# the script buffer: mov ax, size / push ax / call malloc / pop cx / mov [script], ax / mov [script+2], dx
BUFFER_SIG = re.compile(rb"\xb8(..)\x50\xe8..\x59\xa3\xe8\x1e\x89\x16\xea\x1e", re.S)
# the loaded scene and 000.CEN made one more a byte, up to a count: mov si, count (on RR) ... cmp si, count
DECODE_SIG = re.compile(rb"\xbe(..)\xc4\x1e\xe8\x1e\x26\x8a\x07\xfe\xc0\xc4\x1e\xe8\x1e\x26\x88\x07"
                        rb"\xff\x06\xe8\x1e\x46\x81\xfe(..)\x7c", re.S)
BUFFER = 0x8000                             # the script buffer, made larger
SCRIPT_LIMIT = BUFFER - 0x66                # a scene and 000.CEN together, as the loader reads them

HELPER = """
site:
    mov ax, word ptr [bp + 4]
    cmp al, 0x21
    jb orig
    cmp al, 0x7e
    jbe pair
orig:
    xchg al, ah
    .byte 0xea
    .word {back}
seg2:
    .word 0
pair:
    push bx
    push cx
    push dx
    push si
    push di
    xor bh, bh
    mov bl, al
    mov dl, byte ptr cs:[bx + {leadix}]
    mov bl, ah
    dec bl
    mov dh, byte ptr cs:[bx + {trailix}]
    mov al, dl
    xor ah, ah
    mov cl, {ntrail}
    mul cl
    add al, dh
    adc ah, 0
    mov cl, {nletter}
    div cl
    push ax
    mov bl, al
    xor bh, bh
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov bx, cs
    mov cx, {g1}
    mov ah, 0x14
    int 0x18
    pop ax
    mov bl, ah
    xor bh, bh
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov bx, cs
    mov cx, {g2}
    mov ah, 0x14
    int 0x18
    mov di, {buffer}
    xor si, si
    mov cx, 16
fill:
    mov al, byte ptr cs:[si + {g1} + 2]
    mov byte ptr [di], al
    mov al, byte ptr cs:[si + {g2} + 2]
    mov byte ptr [di + 1], al
    inc si
    add di, 2
    loop fill
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov ax, ds
    mov es, ax
    .byte 0xea
    .word {done}
seg1:
    .word 0
"""


def dgroup(img):
    m = ENTRY_SIG.match(bytes(img[:8]))
    if not m:
        raise SystemExit("DIES01.EXE: the entry is not laid out as expected")
    return struct.unpack("<H", m.group(1))[0]


def patch_program(exe):
    """DIES01.EXE with the half-width helper (see the module's docstring)."""
    hdr, rel_at, img, fixups = _exe(exe)
    dg = dgroup(img)
    found = list(GLYPH_SIG.finditer(bytes(img[:dg * 16])))
    if len(found) != 1:
        raise SystemExit("DIES01.EXE: the glyph routine's signature is found %d times, not once" % len(found))
    m = found[0]
    a = m.start(1)
    seg = max(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v * 16 <= a)
    buffer = struct.unpack("<H", m.group(2))[0]
    letters = LETTERS.encode("ascii")
    leadix = bytes(LEADS.index(b) if b in LEADS else 0 for b in range(256))
    trailix = bytes(TRAILS.index(b) if b in TRAILS else 0 for b in range(256))

    def source(base):
        return HELPER.format(leadix=hex(base), trailix=hex(base + 256), letters=hex(base + 512),
                             g1=hex(base + 512 + 80), g2=hex(base + 512 + 80 + 0x14), buffer=hex(buffer),
                             ntrail=len(TRAILS), nletter=len(LETTERS), done=hex(m.start(3) - seg * 16),
                             back=hex(m.end(1) - seg * 16))
    names = ["site", "seg1", "seg2"]
    code, _a = _asm16(source(0x400), 0, names)
    base = len(code) + (-len(code) % 16)
    code, addr = _asm16(source(base), 0, names)
    if len(code) > base:
        raise SystemExit("DIES01.EXE: the helper's length changed")
    room = code + bytes(base - len(code)) + leadix + trailix + letters.ljust(80, b"\0") + bytes(0x28)
    paras = -(-len(room) // 16)
    img[a:a + 5] = b"\xea" + struct.pack("<HH", addr["site"], dg)
    # the script buffer and its decoding count made larger
    for sig, what in ((BUFFER_SIG, "script buffer"), (DECODE_SIG, "script decoding")):
        hits = list(sig.finditer(bytes(img[:dg * 16])))
        if len(hits) != 1:
            raise SystemExit("DIES01.EXE: the %s's signature is found %d times, not once" % (what, len(hits)))
    b = BUFFER_SIG.search(bytes(img[:dg * 16]))
    struct.pack_into("<H", img, b.start(1), BUFFER)
    c = DECODE_SIG.search(bytes(img[:dg * 16]))
    struct.pack_into("<H", img, c.start(1), SCRIPT_LIMIT)
    struct.pack_into("<H", img, c.start(2), SCRIPT_LIMIT)
    out = bytearray(_move_up(exe, hdr, img, fixups, rel_at, dg, paras, room, "DIES01.EXE"))
    for k in ("seg1", "seg2"):
        struct.pack_into("<H", out, hdr + dg * 16 + addr[k], seg)
    new_rel = [(a + 3 - seg * 16, seg), (addr["seg1"], dg), (addr["seg2"], dg)]
    nrel = struct.unpack_from("<H", out, 6)[0]
    if rel_at + 4 * (nrel + len(new_rel)) > hdr:
        raise SystemExit("DIES01.EXE: no room in the header for the new relocation entries")
    for j, (o, sg) in enumerate(new_rel):
        struct.pack_into("<HH", out, rel_at + 4 * (nrel + j), o, sg)
    struct.pack_into("<H", out, 6, nrel + len(new_rel))
    return bytes(out)


# the programs' DOS strings ($-ended): Shift-JIS with kana in it, written in place
DOS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]){4,}(?=\r\n\$|\n\r\$|\$)")


def dos_strings(data):
    """[(start, end)] of a program's Japanese DOS strings."""
    out = []
    for m in DOS_RUN.finditer(data):
        s, e = m.start(), m.end()
        if data[s:s + 1] == b"$":
            s += 1
        try:
            t = data[s:e].decode("cp932")
        except UnicodeDecodeError:
            continue
        if sum(1 for c in t if "぀" <= c <= "ヿ") >= 2:
            out.append((s, e))
    return out
