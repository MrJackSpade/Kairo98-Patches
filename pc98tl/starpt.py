"""Custom's Star Platinum (STAR_PT: SP.COM runs the modules SPO, SPG, SPD, SPF, SPE and SPV.BIN in turn,
each a PKLITE-packed program, pc98tl/pklite.py): its text, and English drawn half-width.

GDM archives (`gdm`, `gdm_bytes`): an LZSS block (the entries' places, dwords from the table block's
end, the last the archive's end), then the entries, each an LZSS block.  An LZSS block: a word, the
length after the header; a word, the flags' length; the flags (a bit each, the low bit first: 0 a
literal byte, 1 a copy: a byte, its distance less 1, then a byte, its length less 3); the data.  An entry
written again is a block of literals (`literal`); the others are kept as they are.

SCENARIO.GDM (SPV.BIN): each entry a word (the code's length), the bytecode, then its strings (0-ended;
the code names them by number, so they can be any length).  A string is lines of text with codes:
\\/ a new screen, \\k a key wait, \\pN_ a pause, \\wN the typing speed, \\S \\D \\B \\C \\+ \\L \\l \\b \\K
(screen, window and voice settings), \\- a long dash.  A speaker's line is "name<tab>「...」" (a name of
four characters without the tab), their later lines starting with a tab and two spaces; narration
starts with spaces (four a paragraph, two a later line); a menu's choices are strings of one line.
`units` splits a string into its lines' leading codes and units (a speaker, the indent, the lines and
the codes after them), `string_bytes` puts them together again.

MUSIC.GDM's text entries (the card game's lines): CR LF lines, a balloon's lines up to ##.

The programs' text: 0-ended strings in their data segments (`program_strings`), written in place.

English (`patch_module`): the programs draw a byte below 100h as a blank (their glyph routine,
`GLYPH_SIG`); it is made to call a helper (a segment put in before DGROUP, pc98tl/adl5.py `_move_up`)
that draws such a byte from the BIOS 8x16 font, so ASCII is drawn half-width (the text routines step 8
dots a byte).  The patcher breaks the English between words (`wrap`) at the string's width and starts
a new screen (the speaker again) after `PAGE` lines.  SPV's script buffer is made larger
(`BUFFER_SIG`).  The modules are written unpacked.
"""
import re
import struct

from .adl5 import _move_up
from .kuro import _asm16, _exe

BS = b"\\"
LINE = 76                   # columns of the story's window
PAGE = 4                    # lines a screen
NAME = 7                    # letters of a name before the tab
BALLOON = 27                # letters a balloon's line (the card game: the program breaks a line after 28)
BALLOON_LINES = 4
CODE = re.compile(rb"\\(?:[pw]\d+_?|[cC][a-z]|[SDBCLlbKk]\d*|/|\+|-)")
LEAD = re.compile(rb"(?:\\(?:[pw]\d+_?|[SDBCbKk]\d*|/|\+))*")
TAIL = re.compile(rb"(?:\\(?:[pw]\d+_?|[bKk]))*$")
NAME_RE = re.compile(rb"((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){1,4})(\t|(?=\x81\x75))")
JP = re.compile(rb"[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]")


# ---- GDM ------------------------------------------------------------------------------------------------

def block(data, at):
    """(an LZSS block's data, the place after it)."""
    total, nflag = struct.unpack_from("<HH", data, at)
    q = at + 4
    flags, d, end = q, q + nflag, q + total
    out = bytearray()
    bit = 0
    while d < end:
        f = data[flags + bit // 8] >> (bit % 8) & 1
        bit += 1
        if not f:
            out.append(data[d])
            d += 1
        else:
            dist, ln = data[d] + 1, data[d + 1] + 3
            d += 2
            for _ in range(ln):
                out.append(out[-dist])
    return bytes(out), end


def literal(data):
    """An LZSS block of literals only."""
    nflag = (len(data) + 7) // 8
    if nflag + len(data) > 0xFFFF:
        raise ValueError("a GDM entry of %d bytes (an entry's block holds 58,000)" % len(data))
    return struct.pack("<HH", nflag + len(data), nflag) + bytes(nflag) + data


def gdm(data):
    """(the entries (None for an empty place), their blocks as they are, the table's block)."""
    table, base = block(data, 0)
    offs = [struct.unpack_from("<I", table, 4 * k)[0] for k in range(len(table) // 4)]
    last = max(k for k, o in enumerate(offs) if o or k == 0)
    entries, raw = [], []
    for k in range(last):
        if k and not offs[k]:
            entries.append(None)
            raw.append(None)
            continue
        e, end = block(data, base + offs[k])
        entries.append(e)
        raw.append(data[base + offs[k]:end])
    return entries, raw, data[:base]


def gdm_bytes(raw, table_block):
    """An archive of blocks (None an empty place); the table's block kept if its places are the same."""
    old = block(table_block, 0)[0]
    body, table = bytearray(), bytearray()
    for r in raw:
        table += struct.pack("<I", len(body) if r is not None else 0)
        if r is not None:
            body += r
    table += struct.pack("<I", len(body))
    table = bytes(table.ljust(len(old), b"\0"))
    return (table_block if table == old else literal(table)) + bytes(body)


# ---- SCENARIO.GDM ---------------------------------------------------------------------------------------

def strings(entry):
    """(the code, with its length word; the strings)."""
    cl = struct.unpack_from("<H", entry, 0)[0]
    return entry[:cl + 2], entry[cl + 2:].split(b"\0")


def entry_bytes(code, strs):
    return code + b"\0".join(strs)


def has_text(b):
    return JP.search(b) is not None


class Unit:
    """A speaker's or the narration's lines: the leading codes, the indent, the name (and its tab), the
    lines (each [indent, text]) and the codes after the last."""

    def __init__(self, lead, ws, name, sep, text):
        self.lead, self.ws, self.name, self.sep = lead, ws, name, sep
        self.lines = [[b"", text]]
        self.tail = b""

    def close(self):
        last = self.lines[-1]
        m = TAIL.search(last[1])
        self.tail, last[1] = last[1][m.start():], last[1][:m.start()]

    def body(self):
        return b"\n".join(t for _i, t in self.lines)

    def cont(self):
        """The indent of the later lines."""
        if len(self.lines) > 1:
            return self.lines[1][0]
        return b"\t  " if self.name is not None else b"  "

    def bytes(self):
        out = self.lead + self.ws + (self.name + self.sep if self.name is not None else b"")
        return out + b"\n".join(i + t for i, t in self.lines) + self.tail


def units(s):
    """A string as [bytes or Unit] (bytes: codes and new lines between the units)."""
    parts, cur = [], None
    lines = s.split(b"\n")
    for k, line in enumerate(lines):
        if k:
            parts.append(b"\n")
        lead = LEAD.match(line).group()
        rest = line[len(lead):]
        if not has_text(rest) and not CODE.sub(b"", rest).strip():
            parts.append(line)
            cur = None
            continue
        if (cur is not None and BS + b"/" not in lead and BS + b"+" not in lead
                and (rest.startswith(b"\t  ") or (rest.startswith(b"  ") and not rest.startswith(b"    ")))):
            cur.lines.append([lead + rest[:3 if rest[0] == 9 else 2], rest[3 if rest[0] == 9 else 2:]])
            parts.pop()          # (the new line is the unit's)
            continue
        if cur is not None:
            cur.close()
        ws = re.match(rb"[ \t]*", rest).group()
        rest = rest[len(ws):]
        m = NAME_RE.match(rest) if not ws else None
        name, sep = (m.group(1), m.group(2)) if m else (None, b"")
        cur = Unit(lead, ws, name, sep, rest[m.end():] if m else rest)
        parts.append(cur)
    if cur is not None:
        cur.close()
    return parts


def string_bytes(parts):
    return b"".join(p if isinstance(p, bytes) else p.bytes() for p in parts)


def cols(b):
    """Columns a line takes (codes none, a tab to the next eighth)."""
    b = CODE.sub(b"", b)
    c = i = 0
    while i < len(b):
        x = b[i]
        if 0x81 <= x <= 0x9f or 0xe0 <= x <= 0xfc:
            c, i = c + 2, i + 2
        elif x == 9:
            c, i = (c // 8 + 1) * 8, i + 1
        else:
            c, i = c + 1, i + 1
    return c


def entry_width(strs):
    """The story window's columns in an entry's scenes: its widest line (within LINE)."""
    w = [cols(line) for s in strs if has_text(s) for line in s.split(b"\n")]
    w = [x for x in w if x <= LINE]
    return max(w) if w else LINE


def string_width(s, default):
    """The columns a string's English is broken at: a string of three lines or more its widest line (a
    narrower layout), a shorter one the entry's."""
    lines = [cols(line) for line in s.split(b"\n") if has_text(line)]
    lines = [x for x in lines if x <= LINE]
    return max(lines) if len(lines) >= 3 else default


def show(b):
    """Text as strings.json shows it: codes as {...}; characters the font has but Shift-JIS does not as
    {Gxxxx}."""
    out, k = [], 0
    while k < len(b):
        m = CODE.match(b, k)
        if m:
            out.append("{%s}" % m.group()[1:].decode("ascii"))
            k = m.end()
            continue
        x = b[k]
        if 0x81 <= x <= 0x9f or 0xe0 <= x <= 0xfc:
            pair = b[k:k + 2]
            try:
                out.append(pair.decode("cp932"))
            except UnicodeDecodeError:
                out.append("{G%s}" % pair.hex())
            k += 2
        else:
            out.append("{ESC}" if x == 0x1b else chr(x) if x != 0x0d else "")
            k += 1
    return "".join(out)


def ascii_text(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "「": '"', "」": '"',
             "『": '"', "』": '"', "（": "(", "）": ")", "　": " "}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if 0x20 <= ord(c) < 0x7F or c in "\n\t" else "?" for c in s)


def tokens(text):
    """English as [(kind, value)]: word, space, code (its bytes), break."""
    out = []
    for m in re.finditer(r"\{([A-Za-z][A-Za-z0-9_]*|/|\+|-)\}|\n|[ ]+|[^ \n{]+|\{", ascii_text(text)):
        g = m.group()
        if m.group(1) is not None:
            if m.group(1).startswith("G"):
                continue
            if m.group(1) == "ESC":
                out.append(("code", b"\x1b"))
                continue
            out.append(("code", BS + m.group(1).encode("ascii")))
        elif g == "\n":
            out.append(("break", None))
        elif g.isspace():
            out.append(("space", g.encode("ascii")))
        else:
            out.append(("word", g.encode("ascii")))
    return out


def plain(text):
    """English as it stands (its spaces kept), codes as their bytes."""
    out = bytearray()
    for kind, val in tokens(text):
        out += val if kind != "break" else b"\n"
    return bytes(out)


def wrap(text, width):
    """[line bytes] of English broken between words at `width` letters (codes kept, no width)."""
    lines, line, n = [], bytearray(), 0
    width = max(width, 8)
    for kind, val in tokens(text):
        if kind == "code":
            line += val
        elif kind == "break":
            lines.append(bytes(line).rstrip(b" "))
            line, n = bytearray(), 0
        elif kind == "space":
            if n:
                line += b" "
                n += 1
        else:
            while len(val) > width:
                if n:
                    lines.append(bytes(line).rstrip(b" "))
                    line, n = bytearray(), 0
                lines.append(val[:width])
                val = val[width:]
            if n + len(val) > width and n:
                lines.append(bytes(line).rstrip(b" "))
                line, n = bytearray(), 0
            line += val
            n += len(val)
    lines.append(bytes(line).rstrip(b" "))
    while len(lines) > 1 and not lines[-1]:
        lines.pop()
    return lines


def english_string(parts, texts, names, width):
    """A string again with English: texts {unit index: English}, names {Japanese name: English} (a
    unit without English is kept as it is).  A unit's English is broken at `width` columns, under the
    speaker's name; a screen runs to PAGE lines, the rest on a new screen (a key wait, the speaker again)."""
    out, used = bytearray(), 0
    for k, p in enumerate(parts):
        if isinstance(p, bytes):
            out += p
            if BS + b"/" in p:
                used = 0
            continue
        if BS + b"/" in p.lead:
            used = 0
        if k not in texts:
            out += p.bytes()
            used += len(p.lines)
            continue
        name = p.name
        if name is not None:
            name = ascii_text(names.get(name) or "").encode("ascii") or name
        cont = p.cont()
        tag = name + (b"\t" if p.sep or name != p.name else b"") if name is not None else b""
        lines = wrap(texts[k], width - max(cols(p.ws + tag), cols(cont)))
        head = p.lead + p.ws + tag
        again = tag or p.ws
        if used >= PAGE:
            out += BS + b"k\n" + BS + b"/"
            used = 0
        for n, line in enumerate(lines):
            if n == 0:
                out += head + line
            elif used >= PAGE:
                out += BS + b"k\n" + BS + b"/" + again + line
                used = 0
            else:
                out += b"\n" + cont + line
            used += 1
        out += p.tail
    return bytes(out)


# ---- MUSIC.GDM text -------------------------------------------------------------------------------------

def is_balloons(entry):
    return entry is not None and b"##\r\n" in entry and has_text(entry)


def balloons(entry):
    """The balloons' texts (CR LF lines) and what follows the last ##."""
    parts = entry.split(b"##\r\n")
    return parts[:-1], parts[-1]


def balloons_bytes(texts, tail):
    return b"".join(t + b"##\r\n" for t in texts) + tail


def balloon(text):
    """A balloon's English: lines of BALLOON letters (CR LF between them), and how many."""
    lines = wrap(text, BALLOON)
    return b"\r\n".join(lines), len(lines)


def is_credits(entry):
    """A staff roll: CR LF lines, text placed by tabs, the scrolling's numbers between them."""
    if entry is None or is_balloons(entry) or len(KANA.findall(entry)) < 8 or b"\r\n" not in entry:
        return False
    return all(has_text(x) or x.isdigit() or not x.strip(b"\t .#\x1a") for x in entry.split(b"\r\n"))


def credit(line, text):
    """A staff roll's line with English: centred where the Japanese was centred (spaces before it)."""
    ws = re.match(rb"[ \t]*", line).group()
    centre = cols(ws) + cols(line[len(ws):]) / 2
    b = plain(text.replace("\n", " ")).strip()
    return b" " * max(0, int(round(centre - len(b) / 2))) + b


# ---- the programs ---------------------------------------------------------------------------------------

# the glyph routine: mov si, [bp+4] / mov dx, [bp+6] / cmp dx, 100h / jge (a code) / (a byte below 100h:
# the glyph cleared) ... / pop di / pop si / pop bp / ret
GLYPH_SIG = re.compile(rb"\x8b\x76\x04\x8b\x56\x06(\x81\xfa\x00\x01\x7d.\x33\xd2\xeb\x09\xc4\x1c\x03\xda"
                       rb"\x26\xc6\x07\x00\x42\x39\x54\x0a\x7f\xf2)\x5f\x5e\x5d\xc3", re.S)
# SPV's script buffer: push 0 / push 4000h / call farmalloc / ... / mov [buf+2], dx / mov [buf], ax
BUFFER_SIG = re.compile(rb"\x6a\x00\x68(\x00\x40)\xe8..\x83\xc4\x04\x89\x16..\xa3", re.S)
BUFFER = 0xFFF0
STRING = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x09\x0d\x0a\x1b])+(?=\x00)")
KANA = re.compile(rb"\x82[\x9f-\xf1]|\x83[\x40-\x96]")

HELPER = """
ank:
    cmp dx, 0x100
    jb a_small
    clc
    .byte 0xcb
a_small:
    push ax
    push bx
    push cx
    push dx
    push di
    push es
    les bx, dword ptr [si]
    mov di, bx
    mov cx, word ptr [si + 10]
    xor al, al
a_clear:
    jcxz a_cleared
    mov byte ptr es:[di], al
    inc di
    dec cx
    jmp a_clear
a_cleared:
    cmp dl, 0x21
    jb a_done
    cmp dl, 0x7e
    ja a_done
    push bx
    push es
    mov dh, 0x80
    mov bx, cs
    mov cx, {g}
    mov ah, 0x14
    int 0x18
    pop es
    pop bx
    mov di, bx
    xor bx, bx
    mov cx, word ptr [si + 10]
    shr cx, 1
    cmp cx, 16
    jbe a_rows
    mov cx, 16
a_rows:
    mov al, byte ptr cs:[bx + {g} + 2]
    mov byte ptr es:[di], al
    inc bx
    add di, 2
    loop a_rows
a_done:
    pop es
    pop di
    pop dx
    pop cx
    pop bx
    pop ax
    stc
    .byte 0xcb
"""


def dgroup(img):
    """The data segment (the start-up's mov dx, DGROUP)."""
    if img[0] != 0xBA:
        raise SystemExit("the program's start-up is not laid out as expected")
    return struct.unpack_from("<H", img, 1)[0]


def program_strings(img, console=False):
    """[(offset in the image, end)] of a program's Japanese strings: 0-ended runs in its DGROUP (after a 0
    or FFh) with kana in them; a console program's (`console`: a resident driver's, the start-up disk
    maker's) anywhere in its image."""
    out = []
    for m in STRING.finditer(img, 1 if console else dgroup(img) * 16):
        if img[m.start() - 1] not in (0x00, 0xFF):
            continue
        try:
            img[m.start():m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(KANA.findall(img, m.start(), m.end())) >= 2:
            out.append((m.start(), m.end()))
    return out


def patch_module(exe, places, name, buffer=False, helper=True):
    """A module (unpacked) with its strings' English (places [(image offset, bytes)]), the half-width
    helper (`helper`: a module that draws text) and (`buffer`) SPV's larger script buffer."""
    exe = bytearray(exe)
    hdr, rel_at, img, fixups = _exe(bytes(exe))
    if not helper:
        for at, b in places:
            img[at:at + len(b)] = b
        return bytes(exe[:hdr]) + bytes(img)
    if rel_at + 4 * (len(fixups) + 1) > hdr:
        # (the header a paragraph longer for the relocation entry the call adds)
        exe[hdr:hdr] = bytes(16)
        struct.pack_into("<H", exe, 8, hdr // 16 + 1)
        hdr, rel_at, img, fixups = _exe(bytes(exe))
    for at, b in places:
        img[at:at + len(b)] = b
    dg = dgroup(img)
    if buffer:
        hits = list(BUFFER_SIG.finditer(bytes(img[:dg * 16])))
        if len(hits) != 1:
            raise SystemExit("%s: the script buffer's signature is found %d times" % (name, len(hits)))
        struct.pack_into("<H", img, hits[0].start(1), BUFFER)
    hits = list(GLYPH_SIG.finditer(bytes(img[:dg * 16])))
    if len(hits) != 1:
        raise SystemExit("%s: the glyph routine's signature is found %d times" % (name, len(hits)))
    m = hits[0]
    site, done = m.start(1), m.end(1)
    code, _a = _asm16(HELPER.format(g=0x100), 0, ["ank"])
    g = len(code) + (-len(code) % 2)
    code, addr = _asm16(HELPER.format(g=g), 0, ["ank"])
    room = code + bytes(g - len(code)) + bytes(0x30)
    paras = -(-len(room) // 16)
    # call far helper / jc (the routine's end) / jmp (where jge went)
    jge = site + 6 + struct.unpack("b", img[site + 5:site + 6])[0]
    new = b"\x9a" + struct.pack("<HH", addr["ank"], dg)
    new += b"\x72" + bytes([done - (site + 7)]) + b"\xeb" + bytes([(jge - (site + 9)) & 0xFF])
    img[site:done] = new + b"\x90" * (done - site - len(new))
    seg = max(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v * 16 <= site)
    out = bytearray(_move_up(bytes(exe), hdr, img, fixups, rel_at, dg, paras, room, name))
    nrel = struct.unpack_from("<H", out, 6)[0]
    struct.pack_into("<HH", out, rel_at + 4 * nrel, site + 3 - seg * 16, seg)
    struct.pack_into("<H", out, 6, nrel + 1)
    return bytes(out)
