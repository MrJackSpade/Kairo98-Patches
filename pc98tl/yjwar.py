"""Youjuu Senki - A.D. 2048 (YJWAR.EXE): its archives and its text files.

NCA archive ("NCARC01", 0, the files' count (a word at 8); from 10 an 18-byte entry each: the size
(a dword) and the name (14 bytes, a space first, NUL-padded); the files one after another after the
directory: `nca`, `nca_build`).

Text is Shift-JIS, in the archives' files with every bit inverted (`inv`): the program draws a byte
below 80h as a half-width letter itself, and breaks a line at its window's edge (mid-word).

* SYSDATA.NCA's *.TXB, the scenes' messages (`txb`): entries one after another, each its speaker's
  face (a byte), its kind (a byte: 1, 2, 5 a face's message, 3 a message, 6 the opening's centred
  page, 7 a prompt, 8 an ending's message, 9 a sound's caption), a zero, its length (a word: the text
  and its end), the text (inverted) and FFh; a lone FFh after the last.
* ANMSC.NCA's *.SC, the animated scenes (`sc`): "AnmScenario V1.0", the body's length (a word at
  30h), the body from 40h: commands, each AAh, its op, its length (a word, the whole command's) and
  its operands; op 24h a message (a word, the text inverted and FFh), op 29h a line of a profile (its
  place: x and y, words, then the text inverted and FFh).  No command holds a place in the body, so
  a command may grow.
* *.MSG (the maps' battle lines) and DATA_*.TXT (the data pages): plain Shift-JIS lines (CR LF).
* UNIT.DAT (and the program's own copy of the table): 48-byte records, the name first (20 bytes,
  NUL-ended).
"""
import struct

NCA_MAGIC = b"NCARC01\x00"
SC_MAGIC = b"AnmScenario V1.0"
UNIT = 48
NAME = 20


def inv(b):
    return bytes(c ^ 0xFF for c in b)


def nca(raw):
    """[(name, bytes)]."""
    if raw[:8] != NCA_MAGIC:
        raise ValueError("not an NCA archive")
    n = struct.unpack_from("<H", raw, 8)[0]
    off, out = 10 + 18 * n, []
    for k in range(n):
        sz = struct.unpack_from("<I", raw, 10 + 18 * k)[0]
        out.append((raw[14 + 18 * k:28 + 18 * k], raw[off:off + sz]))
        off += sz
    return out


def name(field):
    return field.split(b"\0")[0].strip().decode("ascii")


def nca_build(raw, new):
    """The archive with new {name: bytes}."""
    files = nca(raw)
    head = bytearray(raw[:10])
    body = bytearray()
    for f, b in files:
        b = new.get(name(f), b)
        head += struct.pack("<I", len(b)) + f
        body += b
    return bytes(head + body)


def txb(t):
    """[(start of the text, its end (the FFh), face, kind)]."""
    out, i = [], 0
    while t[i] != 0xFF:
        n = struct.unpack_from("<H", t, i + 3)[0]
        if t[i + 5 + n - 1] != 0xFF:
            raise ValueError("an entry at %x without its end" % i)
        out.append((i + 5, i + 5 + n - 1, t[i], t[i + 1]))
        i += 5 + n
    if i != len(t) - 1:
        raise ValueError("bytes after the last entry")
    return out


def txb_build(t, new):
    """The file with new {text's start: [inverted texts (no FFh)]}: a text's several pages become
    entries one after another, each with the entry's face and kind."""
    out = bytearray()
    for s, e, _f, _k in txb(t):
        for b in new.get(s, [t[s:e]]):
            head = bytearray(t[s - 5:s])
            struct.pack_into("<H", head, 3, len(b) + 1)
            out += head + b + b"\xff"
    return bytes(out + b"\xff")


def sc(b):
    """[(command's place, op, text's start or None, text's end)]: the body's commands."""
    if b[:16] != SC_MAGIC:
        raise ValueError("not an AnmScenario")
    end = 0x40 + struct.unpack_from("<H", b, 0x30)[0]
    if end != len(b):
        raise ValueError("the body's length is not the file's")
    out, i = [], 0x40
    while i < end:
        if b[i] != 0xAA:
            raise ValueError("no command at %x" % i)
        op, n = b[i + 1], struct.unpack_from("<H", b, i + 2)[0]
        if op in (0x24, 0x29):
            s = i + 4 + (2 if op == 0x24 else 4)
            if b[i + n - 1] != 0xFF:
                raise ValueError("a text at %x without its end" % i)
            out.append((i, op, s, i + n - 1))
        else:
            out.append((i, op, None, None))
        i += n
    return out


def sc_build(b, new):
    """The scenario with new {text's start: [inverted texts (no FFh)]}: a message's several pages
    become commands one after another, each with the command's operands."""
    body = bytearray()
    for i, op, s, e in sc(b):
        n = struct.unpack_from("<H", b, i + 2)[0]
        if s is not None and s in new:
            for page in new[s]:
                cmd = bytearray(b[i:s]) + page + b"\xff"
                struct.pack_into("<H", cmd, 2, len(cmd))
                body += cmd
        else:
            body += b[i:i + n]
    head = bytearray(b[:0x40])
    struct.pack_into("<H", head, 0x30, len(body))
    return bytes(head + body)
