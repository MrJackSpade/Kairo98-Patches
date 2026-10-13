"""Tokenized N88-BASIC(86) programs (Starcraft's Mystery House: MYS 98, the
game, and M98, its title and instructions): the string literals rewritten
at any length.

A protected ("P") save is the tokenized program with every byte rotated
right by one bit (pc98tl/n88basic.py).  The program is a run of lines, each
[length (2)][line number (2)][tokens][00], the length counting the whole
line; a line of length 0 ends it.  Lines are found by their lengths, not by
pointers, and jumps name line numbers, so a line may change size: the
program is laid out again with every line's length set to its new size.

In a line: a keyword is one byte 80h-FEh (PRINT C0h, DATA 91h, IF A8h,
THEN D6h, ELSE 99h written ":ELSE"), FF xx a function, 01 a space between
tokens; a variable is its first letter, the number of further letters, the
letters, and a type character ($ % ! #); numeric constants are 0B-0F, 1C,
1D and 1F with their operand bytes (10h-1Ah the numbers 0-10); a string
literal runs from " to the next " or the line's end, its bytes as they are
printed (half-width katakana, ASCII); ' starts a comment; a DATA statement
runs to the next : as plain text.

The game prints its messages with PRINT on the text layer, 80 columns, and
matches what the player types against words: DATA lists of verbs and nouns
searched for in the typed line (INSTR, a verb's space before it and a
noun's after it are part of the match), and whole commands compared with =.
"""
import struct

from . import n88basic

CONST = {0x0B: 2, 0x0C: 2, 0x0D: 2, 0x0E: 2, 0x0F: 1, 0x1C: 2, 0x1D: 4, 0x1F: 8}
PRINT, DATA, THEN, ELSE = 0xC0, 0x91, 0xD6, 0x99
MAX_LITERAL = 255        # a string's length byte


def read(prog, protected=True):
    """[(line number, body)] of a protected program (or, protected=False,
    a plain binary save) and the bytes after its end (the save's padding
    to whole sectors)."""
    p = n88basic.unprotect(prog) if protected else bytes(prog)
    out, pos = [], 0
    while True:
        if pos + 4 > len(p):
            raise ValueError("N88-BASIC: the program runs past its file")
        ln, num = struct.unpack_from("<HH", p, pos)
        # (the end: a length of 0, or as M98 leaves it, a word and line number 0)
        if ln == 0 or out and num <= out[-1][0]:
            return out, p[pos:]
        if ln < 5 or pos + ln > len(p) or p[pos + ln - 1] != 0:
            raise ValueError("N88-BASIC: a line at %x is not laid out as expected" % pos)
        out.append((num, bytes(p[pos + 4:pos + ln - 1])))
        pos += ln


def write(lines, tail, size=None, protected=True):
    """The protected program from [(line number, body)] and the tail read()
    gave, padded with the tail's bytes to `size` when it is no larger."""
    lines = list(lines)
    if size is None:
        # (the end mark, without the zeros the save filled its last sector with.  A file whose
        # last sector holds only zeros (the mark's 00s, cut off by a sector's end) is not run
        # when the disk starts it: the last line gets spaces (01) until the mark starts a sector)
        tail = tail[:4]
        end = sum(len(body) + 5 for _num, body in lines)
        if 256 - len(tail) < end % 256:
            num, body = lines[-1]
            lines[-1] = (num, body + b"\x01" * (256 - end % 256))
    out = bytearray()
    for num, body in lines:
        if len(body) + 5 > 0xFFFF:
            raise ValueError("N88-BASIC: line %d is too long" % num)
        out += struct.pack("<HH", len(body) + 5, num) + body + b"\0"
    out += tail
    if size is not None and len(out) < size:
        out += bytes(size - len(out))
    return n88basic.protect(bytes(out)) if protected else bytes(out)


def _walk(body):
    """[(start, end, what)] of a line body's pieces: "str" (a literal and
    its quotes), "data" (a DATA statement's text), "rem" (a comment),
    "space" (a 01 between tokens), "const", "var", "tok"; and for a
    literal, its statement and the significant byte before it."""
    out, i, stmt, before, fresh = [], 0, None, None, True
    n = len(body)
    while i < n:
        b = body[i]
        if b == 0x22:
            k = body.find(b'"', i + 1)
            k = n if k < 0 else k
            out.append((i, min(k + 1, n), "str", (stmt, before)))
            before, fresh = 0x22, False
            i = k + 1
            continue
        if stmt == DATA and b != 0x3A:
            out.append((i, i + 1, "data", None))
            i += 1
            continue
        if b == 0x27:                       # ' comment: the rest of the line
            out.append((i, n, "rem", None))
            break
        if b == 0x01:
            out.append((i, i + 1, "space", None))
            i += 1
            continue
        if b == 0x20:
            out.append((i, i + 1, "tok", None))
            i += 1
            continue
        if b == 0x3A:
            out.append((i, i + 1, "tok", None))
            stmt, fresh, before = None, True, b
            i += 1
            continue
        if b in CONST:
            out.append((i, i + 1 + CONST[b], "const", None))
            i += 1 + CONST[b]
            before, fresh = b, False
            continue
        if 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A:
            # a variable: letter, count, letters, type character
            j = i + 2 + body[i + 1]
            if j < n and body[j] in b"$%!#":
                j += 1
            out.append((i, j, "var", None))
            i = j
            before, fresh = 0x41, False
            continue
        if b == 0xFF:
            out.append((i, i + 2, "tok", None))
            i += 2
            before, fresh = b, False
            continue
        if b in (THEN, ELSE):
            stmt, fresh = None, True
        elif b >= 0x80 and fresh and not 0xF0 <= b <= 0xFE:
            stmt, fresh = b, False
        else:
            fresh = False
        out.append((i, i + 1, "tok", None))
        before = b
        i += 1
    return out


def compact(body):
    """The line without the spaces kept between its tokens (01 bytes: only
    LIST shows them), to leave the program room for longer text."""
    return b"".join(body[s:e] for s, e, what, _x in _walk(body) if what != "space")


def literals(body):
    """[(start, end, statement, before)] of the string literals in a line's
    body: start..end the text between the quotes, statement the keyword
    that begins its statement (None for an assignment), before the
    significant byte before the opening quote."""
    return [(s + 1, e - 1 if body[e - 1:e] == b'"' and e - 1 > s else e, x[0], x[1])
            for s, e, what, x in _walk(body) if what == "str"]
