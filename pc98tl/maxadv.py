"""Melody's MAX Adventure Scenario Driver (Kurayami): its scripts, its program's strings, and English
in them at any length.

The game runs from a launcher (YAMI.COM, whose menu is DOS `$` strings, rewritten in place: the
memory past the program is its own) that starts the disk driver
EXDD (it serves the files in the PCK archives, pc98tl/maxpck.py) and the engine MAXG.EXE.  MAXG.EXE
is encrypted (`decrypt`: each byte rotated left one, XORed with a running key) over an LZEXE 0.91
program (pc98tl/lzexe.py); a patched build writes it out unpacked (`engine_exe`).

Scripts (*.MDR in MDR.PCK, each byte XORed with FFh) are bytecode run from offset 0 in a 64K buffer:
a byte opcode and its operands; opcode 16h is a goto (a word, the new place).  The text is in
(`records`):
* 0Eh: a message: text up to `04 xx` (the wait, read with it) or a control byte;
* 05h: a line of dialogue: `05 09 c name 09 c 00 text 04 xx`;
* 95h: a chapter title, ended by 0;
* 15h: a menu of choices: `15 00`, then each item's text ended by 0Dh, `00 00`, the item's target
  (a word), and 00 (another item), FFh (the end), `01 w name 00` (a condition, then another item)
  or a menu of its own (15h);
* 34h: a string variable (@mN) set to a text, ended by 0Ah;
* the staff roll, a block of lines (0Dh between) at the script's end, ended by 1Ah, which opcode
  ABh points at.
Text is Shift-JIS and ASCII (drawn half-width by the engine, which breaks lines at the window's
edge), with `@xx` codes (colour, speed, @m0 the hero's name) and 0Dh a new line.

English (`rewrite`): each record with English is written anew, in its place if it fits, else at the
script's end with a goto to it in the old one's place; it ends with a goto back to the place after
the old record.  Nothing else moves.  The menu's items' targets, being after it, are kept.
"""
import re
import struct

from . import lzexe

CH = rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|@[a-z][0-9a-z]|[\x20-\x3f\x41-\x7e]|[\xa1-\xdf]|\x0d)"
MSG = re.compile(rb"\x0e(" + CH + rb"+)(\x04.|(?=\x00|\x06\x00|\x0e|\x01))", re.S)
DLG = re.compile(rb"\x05\x09(.)(" + CH + rb"*)\x09(.)\x00(" + CH + rb"*)(\x04.)", re.S)
TTL = re.compile(rb"\x95(" + CH + rb"+)\x00", re.S)
TXT = re.compile(CH + rb"*")
# a menu item's text (ended by 0Dh)
ITEM = re.compile(rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|@[a-z][0-9a-z]|[\x20-\x3f\x41-\x7e]|[\xa1-\xdf])*")
WIDE = re.compile(rb"[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]")
GOTO = 0x16
BUFFER = 0xFFF0


def xor(b):
    return bytes(c ^ 0xFF for c in b)


def choice(x, p, items):
    """The end of the menu at x[p] (after its FFh); items gets (text start, text end) of each."""
    p += 2
    while True:
        t = ITEM.match(x, p).end()
        if x[t] != 0x0D:
            raise ValueError("a menu item without its end at %x" % t)
        items.append((p, t))
        q = t + 5
        while True:
            s = x[q]
            q += 1
            if s == 0xFF:
                return q
            if s == 0:
                break
            if s == 1:
                q = x.index(0, q + 2) + 1
                if x[q] == 0xFF:
                    return q + 1
                break
            if s == 0x15:
                q = choice(x, q - 1, items)
                continue
            raise ValueError("a menu item followed by %02x at %x" % (s, q - 1))
        p = q


def _wide(t):
    return len(WIDE.findall(t))


# opcode ABh with the staff roll's place (a word): the block, at the script's end, is lines of text
# with 0Dh between them, ended by 1Ah
ROLL = re.compile(rb"\xab(..)", re.S)
ROLL_END = 0x1A


def records(x):
    """[(kind, start, end, parts)] of a script's text, by place; parts are the (start, end) of each
    piece of text in it (dialogue: the name, then the line)."""
    out = []
    for m in DLG.finditer(x):
        out.append(("dlg", m.start(), m.end(), [m.span(2), m.span(4)]))
    for m in MSG.finditer(x):
        if _wide(m.group(1)):
            out.append(("msg", m.start(), m.end(), [m.span(1)]))
    for m in TTL.finditer(x):
        if _wide(m.group(1)):
            out.append(("ttl", m.start(), m.end(), [m.span(1)]))
    for m in SET.finditer(x):
        if _wide(m.group(2)) or KANA.search(m.group(2)):
            out.append(("set", m.start(), m.end(), [m.span(2)]))
    for m in re.finditer(rb"\x15\x00@c", x):
        items = []
        e = choice(x, m.start(), items)
        out.append(("cho", m.start(), e, items))
    for m in ROLL.finditer(x):
        at = struct.unpack("<H", m.group(1))[0]
        e = len(x) - 1
        if m.start() < at < e and x[e] == ROLL_END and TXT.match(x, at).end() == e and _wide(x[at:e]) > 4:
            out.append(("roll", at, e, [(at, e)], m.start() + 1))
    out.sort(key=lambda r: r[1])
    # (a record inside another's span is not a record: a 05/0E/95 byte in a menu's text, say)
    keep, end = [], -1
    for r in out:
        if r[1] >= end:
            keep.append(r)
            end = max(end, r[2])
    return keep


# --- text as shown, and English -----------------------------------------------------------------

def show(b):
    """Shift-JIS and ASCII as they read; @xx codes as {@xx}, 0Dh a new line."""
    out, p = [], 0
    while p < len(b):
        c = b[p]
        if c == 0x40 and p + 2 < len(b) + 1:
            out.append("{@%s}" % b[p + 1:p + 3].decode("ascii", "replace"))
            p += 3
        elif c == 0x0D:
            out.append("\n")
            p += 1
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            out.append(b[p:p + 2].decode("cp932", "replace"))
            p += 2
        else:
            out.append(b[p:p + 1].decode("cp932", "replace"))
            p += 1
    return "".join(out)


TOKEN = re.compile(r"\{@([a-z][0-9a-z])\}")


def tokens(text):
    return TOKEN.findall(text)


def encode(text):
    """English as the script holds it: ASCII, {@xx} as @xx, a new line 0Dh; anything else '?'."""
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    out = bytearray()
    pos = 0
    for m in list(TOKEN.finditer(text)) + [None]:
        seg = text[pos:m.start() if m else len(text)]
        for ch in seg:
            for c in subst.get(ch, ch):
                if c == "\n":
                    out.append(0x0D)
                elif 0x20 <= ord(c) < 0x7F and c != "@":
                    out.append(ord(c))
                else:
                    out.append(ord("?"))
        if m is None:
            break
        out += b"@" + m.group(1).encode("ascii")
        pos = m.end()
    return bytes(out)


WIDTH = 54                          # the message window's columns (half-width)
ROWS = 3
WAIT = b"\x04\x00"
NAME_COLS = 8                       # @m0, the hero's name, at its longest (four full-width letters)


def _cells(b):
    """Columns the text takes: ASCII one, Shift-JIS two, @xx none (@m0 the name, @mN a number)."""
    n, p = 0, 0
    while p < len(b):
        c = b[p]
        if c == 0x40:
            n += NAME_COLS if b[p + 1:p + 3] == b"m0" else (4 if b[p + 1:p + 2] == b"m" else 0)
            p += 3
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            n, p = n + 2, p + 2
        else:
            n, p = n + 1, p + 1
    return n


def wrap(text, first=0, width=WIDTH):
    """[line] of English broken between words: the first line starts at column `first`; 0Dh a new
    line; a word longer than a line is cut."""
    lines = []
    for para in text.split(b"\r"):
        line, col = bytearray(), first if not lines else 0
        for word in para.split(b" "):
            w = _cells(word)
            if line and col + 1 + w > width:
                lines.append(bytes(line))
                line, col = bytearray(), 0
            elif line:
                line += b" "
                col += 1
            while col + w > width and width - col > 0:
                cut = width - col
                lines.append(bytes(line + word[:cut]))
                word, line, col = word[cut:], bytearray(), 0
                w = _cells(word)
            line += word
            col += w
        lines.append(bytes(line))
    return lines


def paged(old, kind, parts, start, texts):
    """A message or a line of dialogue anew, its English in pages of ROWS lines, each but the last
    ended by the wait; the last ended as the old one was."""
    tail = old[parts[-1][1] - start:]               # the old ending (04 xx), or nothing
    if kind == "msg":
        head, first = b"\x0e", 0
    else:
        a, b = parts[0]
        head = old[:a - start] + texts[0] + old[b - start:parts[1][0] - start]
        first = _cells(texts[0])
    lines = wrap(texts[-1], first)
    pages = [lines[k:k + ROWS] for k in range(0, len(lines), ROWS)]
    out = bytearray()
    for n, page in enumerate(pages):
        out += head + b"\r".join(page) + (tail if n == len(pages) - 1 else WAIT)
    return bytes(out)


def rewrite(x, english):
    """The script with its records' text replaced.  english: {(record start, part index): bytes}
    (encoded); records without English stay as they are.  Raises ValueError past the buffer."""
    x = bytearray(x)
    tail = bytearray()
    gaps = []                       # [place, size]: what a moved record leaves after its goto
    for r in records(bytes(x)):
        kind, start, end, parts = r[0], r[1], r[2], r[3]
        new = [english.get((start, k)) for k in range(len(parts))]
        if not any(n is not None for n in new):
            continue
        texts = [n if n is not None else bytes(x[a:b]) for n, (a, b) in zip(new, parts)]
        if kind == "roll":
            block = texts[0] + bytes([ROLL_END])
            at = len(x) + len(tail)
            tail += block
            struct.pack_into("<H", x, r[4], at)
            continue
        if kind in ("msg", "dlg"):
            body = bytearray(paged(bytes(x[start:end]), kind, parts, start, texts))
        else:
            # the record anew: the old bytes with each piece of text replaced
            body, last = bytearray(), start
            for t, (a, b) in zip(texts, parts):
                body += x[last:a] + t
                last = b
            body += x[last:end]
        body += bytes([GOTO]) + struct.pack("<H", end)
        if len(body) <= end - start:
            # in place, its goto back skipping the rest of the old record
            x[start:start + len(body)] = body
            continue
        # elsewhere: in the room an earlier moved record left, else after the script
        gap = next((g for g in gaps if g[1] >= len(body)), None)
        if gap:
            at = gap[0]
            x[at:at + len(body)] = body
            gap[0] += len(body)
            gap[1] -= len(body)
        else:
            at = len(x) + len(tail)
            tail += body
        x[start:start + 3] = bytes([GOTO]) + struct.pack("<H", at & 0xFFFF)
        if end - start > 3:
            gaps.append([start + 3, end - start - 3])
    out = bytes(x + tail)
    if len(out) > BUFFER:
        raise ValueError("%d bytes, the script buffer holds %d" % (len(out), BUFFER))
    return out


# --- the launcher's menu (YAMI.COM: `$` strings, printed by mov dx, string / mov ah, 9) ---------

def com_strings(com):
    """[(start, end)] of the program's `$` strings with Japanese (start to its `$`), a COM program at
    100h: each starts where a mov dx points (BA, word), or right after the `$` of the one before."""
    out = []
    for m in re.finditer(rb"[^$\x00]*?(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc])[^$\x00]*\$", com, re.S):
        s, e = m.start(), m.end() - 1
        start = None
        for k in range(s, e):
            if any(com[j] == 0xBA and struct.unpack_from("<H", com, j + 1)[0] == k + 0x100
                   for j in range(len(com) - 2)):
                start = k
                break
        if start is None and s and com[s - 1] == 0x24:
            start = s
        if start is not None:
            out.append((start, e))
    return out


# --- strings inside programs, in place ----------------------------------------------------------

RUN = re.compile(rb"(?:[\x81-\x9f][\x40-\x7e\x80-\xfc]|[\x20-\x23\x25-\x7e])+")
# the name-entry screen's letters (kept: they are what the player picks a name from)
PALETTE = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ".encode("cp932")


def program_strings(img, lo=0, hi=None):
    """[(start, end)] of the Japanese strings in a program image: runs of Shift-JIS (level 1) and
    ASCII between ends (0, $, CR, LF, or the m of an escape sequence)."""
    out = []
    hi = len(img) if hi is None else hi
    pal = img.find(PALETTE)
    for m in RUN.finditer(img, lo, hi):
        s, e = m.span()
        t = m.group()
        if _wide(t) < 2 or (pal >= 0 and pal - 0x200 <= s <= pal + 0x120):
            continue
        pre = img[s - 1] if s else 0
        post = img[e] if e < len(img) else 0
        if pre not in (0, 0x24, 0x0A, 0x0D, 0x6D) or post not in (0, 0x24, 0x0D, 0x0A):
            continue
        try:
            t.decode("cp932", errors="strict")
        except UnicodeDecodeError:
            continue
        out.append((s, e))
    # the system menu's settings (items of a menu in the engine's own script: @c, then a value with
    # half-width kana, "4096色ｱﾅﾛｸﾞ")
    for m in MENU_VALUE.finditer(img, lo, hi):
        s, e = m.span()
        if (s, e) not in out and img[s - 1] in (0, 0x0A) and img[e] in (0, 0x0A, 0x0D):
            out.append((s, e))
    # and the values its script sets string variables to (34h)
    for m in SET.finditer(img, lo, hi):
        if (_wide(m.group(2)) or KANA.search(m.group(2))) and m.span(2) not in out:
            out.append(m.span(2))
    return sorted(set(out))


# @c and a colour digit, then a value of Shift-JIS, digits and half-width kana
MENU_VALUE = re.compile(rb"@c[0-9a-f](?:[\x81-\x9f][\x40-\x7e\x80-\xfc]|[0-9]|[\xa6-\xdf])+")
# opcode 34h: a string variable (@mN) set to a text, ended by 0Ah
SET = re.compile(rb"\x34([\x00-\x1f])((?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e]|[\xa6-\xdf])+)\x0a",
                 re.S)
KANA = re.compile(rb"[\xa6-\xdf]")


def value_texts(engine_img):
    """{place: value} of the settings' values in the engine: its menu's items (@cX dropped) and its
    script's string variables (34h)."""
    out = {}
    for m in MENU_VALUE.finditer(engine_img):
        out[m.start()] = m.group()[3:]
    for m in SET.finditer(engine_img):
        if _wide(m.group(2)) or KANA.search(m.group(2)):
            out[m.start(2)] = m.group(2)
    return out


def values(data, engine_img):
    """[(start, end)] in the system file of the settings' values the system menu shows (the
    engine's values, as the menu last stored them there)."""
    out = []
    for v in set(value_texts(engine_img).values()):
        for k in re.finditer(re.escape(v), data):
            s, e = k.span()
            if (not s or data[s - 1] in (0, 0x0A)) and (e == len(data) or data[e] in (0, 0x0A)) and (s, e) not in out:
                out.append((s, e))
    return sorted(out)


def in_place(img, s, e, en):
    """The string at img[s:e] replaced by English (padded with spaces); ValueError if longer."""
    if len(en) > e - s:
        raise ValueError("%d letters, room for %d" % (len(en), e - s))
    img = bytearray(img)
    img[s:e] = en + b" " * (e - s - len(en))
    return bytes(img)


# --- the engine: MAXG.EXE ------------------------------------------------------------------------

def decrypt(exe):
    """The engine's LZEXE program (an MZ program) from MAXG.EXE: its image decrypted, its entry the
    LZEXE unpacker's."""
    h = list(struct.unpack_from("<14H", exe, 0))
    hdr = h[4] * 16
    img = bytearray(exe[hdr:])
    st = img[h[11] * 16:]
    if st[:6] != bytes.fromhex("9cfae800005b"):
        raise ValueError("MAXG.EXE: not the expected encryption stub")
    cs, ip, _ss, _sp, count = struct.unpack_from("<5H", st, 8)
    key = st[0x14]
    for i in range(count):
        al = ((img[i] << 1) | (img[i] >> 7)) & 0xFF
        al ^= key
        key = (key + al) & 0xFF
        img[i] = al
    h[11], h[10] = cs, ip
    head = bytearray(exe[:hdr])
    struct.pack_into("<14H", head, 0, *h)
    return bytes(head + img)


def engine(exe):
    """unpack()'s result for the engine (its image, relocations, entry)."""
    return lzexe.unpack(decrypt(exe))


def engine_exe(p, image):
    """A plain MZ program of the engine with its image replaced."""
    return lzexe.build(p, image, keep_most=True)
