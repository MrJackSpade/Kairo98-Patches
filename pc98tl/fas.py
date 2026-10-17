"""May-Be Soft's FAS engine (Escape!: ESCAPE\\FAS.EXE, Borland C++ 1993): its scripts, and English drawn
half-width.

Packs (`pack`, `pack_bytes`; ES_FSXP.DAT the scenes' FSX scripts, ES_HSXP.DAT the H scenes' HSX ones):
a directory of 24-byte entries (a name of 16 bytes, the size and the place, dwords), two bytes, then the
files in turn.

A script (`events`): "EV10" (an FSX "EV101", then its picture and map names), a word at 8 the events'
count, their places from 32 (dwords; several may name one event).  An event: a word A (its head's
length), a word B (its code's length), 12 zeros, the event's bytecode (A less 16 bytes, plain), the code
(B bytes, each stored XOR D6h), then the names its code uses (pictures, music; named by their place
after the code).

The bytecode (`bytecode`): 00 nothing; 01 jump, code, condition (call the code if it holds); 04 var, value,
code; 05 var, value, code, settings; 06 code, condition, settings; 08; 09 var, value; 0A var, value, code;
0B an expression (words up to FDFFh, then the variable); FE the event's end; FF the end.  A condition:
bytes up to 0 (08 and, 09 or, else a comparison and two words); settings: 5-byte entries up to 0.  The
code places (words, from the code's start) are what `code_places` finds.

The code: message streams (`streams`), each up to a 0: two-byte Shift-JIS characters, and codes 01h-1Fh
with their arguments (`ARGS`): 0B the message's end (a key, the window cleared), 0C a new line (at the
indent), 0D a key, 11 n the indent (n characters), 0A n a face; a speaker's name is the text before an
11.  The program breaks a line by itself at 48 (or 60) columns and clears the window after five.

English (`patch_exe`): a byte 20h-7Eh in a message is drawn as one half-width letter: the message
routine's character fetch (`FETCH_SIG`) calls a helper that takes such a byte as a character of one byte
(the text routine, Borland's cputs on the text screen, draws it half-width), and the column's step
(`STEP_SIG`) calls one that steps one column for it.  The helpers are in a segment put in before DGROUP
(pc98tl/adl5.py `_move_up`).  The patcher breaks the English between words (`LINE` columns, under the
speaker's name) and waits for a key and starts a new window after `PAGE` lines.
"""
import re
import struct

from .adl5 import _move_up
from .kuro import _asm16, _exe, dgroup

KEY = 0xD6
LINE = 47                   # columns a line (the program breaks one itself at 48)
PAGE = 5                    # lines a window
# arguments' bytes of the message codes (None: not a code)
ARGS = {0x01: 5, 0x02: 2, 0x03: 1, 0x04: 2, 0x05: 2, 0x06: 7, 0x07: 0, 0x08: 6, 0x09: 3, 0x0A: 1,
        0x0B: 0, 0x0C: 0, 0x0D: 0, 0x0E: 2, 0x0F: 3, 0x10: 0, 0x11: 1, 0x12: 1, 0x1F: 1}
NEWLINE, KEYWAIT, END, INDENT = 0x0C, 0x0D, 0x0B, 0x11


def lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


# ---- packs ----------------------------------------------------------------------------------------------

def pack(data):
    """[(name, bytes)] and the directory's tail (the two bytes after it)."""
    first = struct.unpack_from("<I", data, 20)[0]
    n = first // 24
    out = []
    for k in range(n):
        name = data[24 * k:24 * k + 16].rstrip(b"\0").decode("ascii")
        size, at = struct.unpack_from("<II", data, 24 * k + 16)
        out.append((name, data[at:at + size]))
    return out, data[24 * n:first]


def pack_bytes(files, tail):
    head = 24 * len(files) + len(tail)
    out, body = bytearray(), bytearray()
    for name, b in files:
        out += name.encode("ascii").ljust(16, b"\0") + struct.pack("<II", len(b), head + len(body))
        body += b
    return bytes(out + tail + body)


# ---- scripts --------------------------------------------------------------------------------------------

def event_places(script):
    n = struct.unpack_from("<H", script, 8)[0]
    return list(struct.unpack_from("<%dI" % n, script, 32))


def events(script):
    """[(place, head, code (decoded), names)] in the script's order."""
    places = sorted(set(event_places(script)))
    out = []
    for k, at in enumerate(places):
        a, b = struct.unpack_from("<HH", script, at)
        end = places[k + 1] if k + 1 < len(places) else len(script)
        code = bytes(c ^ KEY for c in script[at + a:at + a + b])
        out.append((at, script[at:at + a], code, script[at + a + b:end]))
    return out


def script_bytes(script, codes):
    """The script with its events' code replaced ({place: new code}): the heads' code places moved
    (`code_places`), the events and their places in the count table moved."""
    places = sorted(set(event_places(script)))
    evs = events(script)
    out = bytearray(script[:places[0]])
    moved = {}
    for at, head, code, names in evs:
        new = codes.get(at)
        head = bytearray(head)
        if new is not None:
            new_code, remap = new
            for p in code_places(head):
                old = struct.unpack_from("<H", head, p)[0]
                struct.pack_into("<H", head, p, remap[old])
            code = new_code
        struct.pack_into("<H", head, 2, len(code))
        moved[at] = len(out)
        out += head + bytes(c ^ KEY for c in code) + names
    n = struct.unpack_from("<H", script, 8)[0]
    for k in range(n):
        at = struct.unpack_from("<I", out, 32 + 4 * k)[0]
        struct.pack_into("<I", out, 32 + 4 * k, moved[at])
    return bytes(out)


def _condition(head, k):
    while head[k]:
        if head[k] in (8, 9):
            k += 1
        else:
            k += 5
    return k + 1


def _settings(head, k):
    while head[k]:
        k += 5
    return k + 1


def code_places(head):
    """The places in an event's head of its words that name a place in the code."""
    out = []
    k = 16
    while True:
        op = head[k]
        if op == 0x00 or op == 0x08 or op == 0xFE:
            k += 1
        elif op == 0x01:
            out.append(k + 3)
            k = _condition(head, k + 5)
        elif op == 0x04 or op == 0x0A:
            out.append(k + 4)
            k += 6
        elif op == 0x05:
            out.append(k + 4)
            k = _settings(head, k + 6)
        elif op == 0x06:
            out.append(k + 1)
            k = _settings(head, _condition(head, k + 3))
        elif op == 0x09:
            k += 4
        elif op == 0x0B:
            k += 1
            while struct.unpack_from("<H", head, k)[0] != 0xFDFF:
                k += 2
            k += 4
        elif op == 0xFF:
            if k + 1 != len(head):
                raise ValueError("an event's head ends at %d of %d" % (k + 1, len(head)))
            return out
        else:
            raise ValueError("an event's head: op %02X at %d" % (op, k))


def _op_len(code, k):
    op = code[k]
    if op == 0x12 and code[k + 1] == 0xFF:
        return 4
    n = ARGS.get(op)
    if n is None:
        raise ValueError("message code %02X at %d" % (op, k))
    return 1 + n


def streams(code):
    """[(start, end)] of the code's message streams (end: after the 0)."""
    out, k, start = [], 0, 0
    while k < len(code):
        b = code[k]
        if b == 0:
            k += 1
            out.append((start, k))
            start = k
        elif lead(b):
            k += 2
        elif 0x20 <= b <= 0x7E:
            k += 1
        else:
            k += _op_len(code, k)
    if start != len(code):
        raise ValueError("the code ends inside a message stream")
    return out


def tokens(code, start, end):
    """A stream as [(kind, bytes)]: "text" (a character), "op" (a code with its arguments), "end"."""
    out, k = [], start
    while k < end:
        b = code[k]
        if b == 0:
            out.append(("end", code[k:k + 1]))
            k += 1
        elif lead(b):
            out.append(("text", code[k:k + 2]))
            k += 2
        elif 0x20 <= b <= 0x7E:
            out.append(("text", code[k:k + 1]))
            k += 1
        else:
            n = _op_len(code, k)
            out.append(("op", code[k:k + n]))
            k += n
    return out


def units(toks):
    """A stream's text: [(kind, first token, end token)], kind "name" (text before an 11, the indent) or
    "msg" (text, with its new lines and key waits, up to another code)."""
    out, k = [], 0
    while k < len(toks):
        kind, b = toks[k]
        if kind != "text":
            k += 1
            continue
        j = k
        while j < len(toks) and (toks[j][0] == "text" or (toks[j][0] == "op" and toks[j][1][0] in (NEWLINE, KEYWAIT))):
            j += 1
        while j > k and toks[j - 1][0] != "text":
            j -= 1
        name = j < len(toks) and toks[j][0] == "op" and toks[j][1][0] == INDENT
        out.append(("name" if name else "msg", k, j))
        k = j
    return out


def show(toks):
    """Text as strings.json shows it: a new line as \\n, a key wait as {K}."""
    out = []
    for kind, b in toks:
        if kind == "text":
            out.append(b.decode("cp932", "replace"))
        elif b[0] == NEWLINE:
            out.append("\n")
        elif b[0] == KEYWAIT:
            out.append("{K}")
    return "".join(out)


def cols(toks):
    return sum(len(b) for kind, b in toks if kind == "text")


# ---- English --------------------------------------------------------------------------------------------

def ascii_text(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "「": '"', "」": '"',
             "『": '"', "』": '"', "【": "[", "】": "]", "（": "(", "）": ")", "　": " "}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if 0x20 <= ord(c) < 0x7F or c == "\n" else "?" for c in s)


def wrap(text, first, width):
    """[[line bytes, key wait after it]] of English broken between words: the first line `first`
    letters, the rest `width`; {K} a key wait, \\n a new line."""
    lines, line, wait = [], bytearray(), False
    room = first
    for m in re.finditer(r"\{K\}|\n|[ ]+|[^ \n{]+|\{", ascii_text(text)):
        g = m.group()
        if g == "{K}":
            wait = True
            continue
        if g == "\n":
            lines.append([bytes(line).rstrip(b" "), wait])
            line, wait, room = bytearray(), False, width
            continue
        if g.isspace():
            if line:
                line += b" "
            continue
        w = g.encode("ascii")
        while len(w) > room:
            if line.strip():
                lines.append([bytes(line).rstrip(b" "), wait])
                line, wait, room = bytearray(), False, width
                continue
            lines.append([w[:room], wait])
            w, line, wait, room = w[room:], bytearray(), False, width
        if len(line) + len(w) > room:
            lines.append([bytes(line).rstrip(b" "), wait])
            line, wait, room = bytearray(), False, width
        line += w
    lines.append([bytes(line).rstrip(b" "), wait])
    return lines


def message(text, start, indent, row):
    """A message's English as code bytes: broken at LINE columns (the first line from column `start`,
    the rest at the indent), a new line by 0C, a key and a new window after PAGE lines (from row `row`).
    Returns the bytes and the row after."""
    lines = wrap(text, max(LINE - start, 8), max(LINE - indent, 8))
    out = bytearray()
    for n, (line, wait) in enumerate(lines):
        if n:
            if row == PAGE - 1:
                out.append(KEYWAIT)
            out.append(NEWLINE)
            row = (row + 1) % PAGE
        out += line
        if wait:
            out.append(KEYWAIT)
    return bytes(out), row


def name(text, indent):
    """A speaker's name in English, padded to the indent."""
    b = ascii_text(text).replace("\n", " ").encode("ascii")
    return b.ljust(indent)


# ---- the program ----------------------------------------------------------------------------------------

# the message routine's character fetch: les bx, [bp-4] / mov al, es:[bx] / mov ah, 0 / mov bx, ax /
# test byte ptr [bx+lead table], 4 / jne (a character) / jmp (a code)
FETCH_SIG = re.compile(rb"\xc4\x5e\xfc\x26\x8a\x07\xb4\x00\x8b\xd8\xf6\x87(..)\x04\x75\x03\xe9(..)", re.S)
# the column's step after a character: add word ptr [column], 2 / cmp byte ptr [mode], 0 / je
STEP_SIG = re.compile(rb"\x83\x06(..)\x02\x80\x3e..\x00\x74", re.S)

HELPER = """
fetch:
    les bx, dword ptr [bp - 4]
    mov al, byte ptr es:[bx]
    mov ah, 0
    mov bx, ax
    test byte ptr [bx + {table}], 4
    jnz f_lead
    cmp al, 0x20
    jb f_code
    cmp al, 0x7e
    ja f_code
    mov byte ptr [bp - 0x30], al
    mov byte ptr [bp - 0x2f], 0
    inc word ptr [bp - 4]
    mov ax, 2
    .byte 0xcb
f_lead:
    mov ax, 1
    .byte 0xcb
f_code:
    xor ax, ax
    .byte 0xcb
step:
    add word ptr [{column}], 2
    cmp byte ptr [bp - 0x2f], 0
    jne s_done
    dec word ptr [{column}]
s_done:
    .byte 0xcb
"""


def patch_exe(exe, places=()):
    """FAS.EXE with the half-width helpers (and its own text in place: [(image offset, bytes)])."""
    exe = bytearray(exe)
    hdr, rel_at, img, fixups = _exe(bytes(exe))
    for at, b in places:
        img[at:at + len(b)] = b
    dg = dgroup(bytes(exe))
    f = list(FETCH_SIG.finditer(bytes(img[:dg * 16])))
    s = list(STEP_SIG.finditer(bytes(img[:dg * 16])))
    if len(f) != 1 or len(s) != 1:
        raise SystemExit("FAS.EXE: the message routine's signatures are found %d and %d times" % (len(f), len(s)))
    f, s = f[0], s[0]
    table = struct.unpack("<H", f.group(1))[0]
    column = struct.unpack("<H", s.group(1))[0]
    fetch = f.start()
    lead_at = f.start() + 20                                  # (after the jmp: the character's path)
    code_at = f.end() + struct.unpack("<h", f.group(2))[0]
    char_at = lead_at + 0x18                                  # (the character's path after its fetch)
    if img[lead_at:lead_at + 6] != b"\xc4\x5e\xfc\x26\x8a\x07" or img[char_at:char_at + 4] != b"\x83\x7e\xdc\x00":
        raise SystemExit("FAS.EXE: the message routine's character path is not laid out as expected")
    code, addr = _asm16(HELPER.format(table=table, column=column), 0, ["fetch", "step"])
    paras = -(-len(code) // 16)
    new = b"\x9a" + struct.pack("<HH", addr["fetch"], dg) + b"\x48"
    new += b"\x74" + bytes([lead_at - (fetch + 8)])
    new += b"\x7f" + bytes([char_at - (fetch + 10)])
    new += b"\xe9" + struct.pack("<h", code_at - (fetch + 13))
    img[fetch:fetch + 20] = new + b"\x90" * (20 - len(new))
    step = s.start()
    img[step:step + 5] = b"\x9a" + struct.pack("<HH", addr["step"], dg)
    segs = sorted(set(struct.unpack_from("<H", img, x)[0] for x in fixups))
    out = bytearray(_move_up(bytes(exe), hdr, img, fixups, rel_at, dg, paras, code, "FAS.EXE"))
    nrel = struct.unpack_from("<H", out, 6)[0]
    for site in (fetch, step):
        seg = max(v for v in segs if v * 16 <= site)
        struct.pack_into("<HH", out, rel_at + 4 * nrel, site + 3 - seg * 16, seg)
        nrel += 1
    struct.pack_into("<H", out, 6, nrel)
    return bytes(out)
