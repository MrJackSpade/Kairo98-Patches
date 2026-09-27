"""JAST family-A scene files (*.OVL): tokenizer and rebuilder.

A scene file starts with a header of word offsets (count = first word / 2),
each the start of a table; some tables hold word offsets into the file
(block starts, jump targets).  After the tables comes the scene stream, which
the engine's text interpreter reads byte by byte:

  text          Shift-JIS pairs, ASCII 20-7E (but "%"), half-width kana A1-DF
  % n n n       a name placeholder (three digits)
  01            end of a message (wait, clear)
  02 x, 03 x    return to the scene code with a value (03 00 00 ends a file)
  04 x y z      05 x y      06 a b c d      07 x      08 x
  0A            new line
  0B op ...     variable operations; 32-35 (if var ... goto word offset),
                36 (goto word offset) and 37 (goto one of a table of word
                offsets, indexed by a variable) carry file offsets
  0C op [x y]   0D op [x y]   0E op ...     0F
  00            end

Text may change length: every offset (header-table words that point into the
stream, and the goto operands) is moved with it.  tokenize() checks that
every such offset lands on a token boundary; a file that fails is left alone.
"""
import re
import struct

SJIS3 = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]){3}")

# operand bytes after the 0B sub-op byte
OP0B = {0x01: 2, 0x02: 2, 0x03: 2, 0x04: 2, 0x05: 2, 0x06: 3, 0x07: 3, 0x08: 3, 0x09: 3,
        0x0A: 1, 0x32: 3, 0x33: 3, 0x34: 3, 0x35: 3, 0x36: 2}
FIXED = {0x01: 0, 0x02: 1, 0x03: 1, 0x04: 3, 0x05: 2, 0x06: 4, 0x07: 1, 0x08: 1, 0x0A: 0, 0x0F: 0}


def _is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


class Token:
    __slots__ = ("kind", "start", "raw", "targets")

    def __init__(self, kind, start, raw, targets=()):
        self.kind, self.start, self.raw, self.targets = kind, start, raw, list(targets)


def header(data):
    """The table offsets.  A few files start with a zero word; their offsets
    follow it."""
    first = 2 if struct.unpack_from("<H", data, 0)[0] == 0 else 0
    n = struct.unpack_from("<H", data, first)[0] // 2
    return [struct.unpack_from("<H", data, 2 * i)[0] for i in range(first // 2, n)]


class TokenError(ValueError):
    def __init__(self, msg, pos, toks):
        ValueError.__init__(self, msg)
        self.pos, self.toks = pos, toks


def tokenize(data, start):
    try:
        return _tokenize(data, start)
    except TokenError:
        raise
    except IndexError as ex:
        raise TokenError("truncated operand", getattr(ex, "pos", len(data)), [])


def _tokenize(data, start):
    """Tokens from `start` to the end.  Text runs (with %nnn) are "text";
    targets are (offset in raw, absolute target) for goto operands."""
    toks, i, n = [], start, len(data)
    while i < n:
        b = data[i]
        if _is_lead(b) or (0x20 <= b <= 0x7E and b != 0x25) or 0xA1 <= b <= 0xDF or b == 0x25 or b == 0x09:
            j = i
            while j < n:
                c = data[j]
                if _is_lead(c):
                    j += 2
                elif c == 0x25:
                    j += 4
                elif 0x20 <= c <= 0x7E or 0xA1 <= c <= 0xDF or c == 0x09:
                    j += 1
                else:
                    break
            toks.append(Token("text", i, data[i:j]))
            i = j
            continue
        if b in FIXED:
            k = 1 + FIXED[b]
            toks.append(Token("code", i, data[i:i + k]))
            i += k
            continue
        if b == 0x0B:
            op = data[i + 1]
            if op == 0x37:
                # table of word offsets: count unknown; take words that point
                # inside the file at even-looking positions, stopped by the
                # first that doesn't (checked later against token starts)
                j, targets = i + 3, []
                while j + 1 < n:
                    w = struct.unpack_from("<H", data, j)[0]
                    if not (start <= w < n):
                        break
                    targets.append((j - i, w))
                    j += 2
                toks.append(Token("code", i, data[i:j], targets))
                i = j
                continue
            if op not in OP0B:
                raise TokenError("unknown 0B op %02x at %x" % (op, i), i, toks)
            k = 2 + OP0B[op]
            targets = []
            if 0x32 <= op <= 0x35:
                targets = [(3, struct.unpack_from("<H", data, i + 3)[0])]
            elif op == 0x36:
                targets = [(2, struct.unpack_from("<H", data, i + 2)[0])]
            toks.append(Token("code", i, data[i:i + k], targets))
            i += k
            continue
        if b == 0x0C or b == 0x0D:
            op = data[i + 1]
            k = 2 + (2 if (op in (1, 2, 3) if b == 0x0C else op == 1) else 0)
            toks.append(Token("code", i, data[i:i + k]))
            i += k
            continue
        if b == 0x0E:
            op = data[i + 1]
            k = 2 + (1 if op in (1, 2, 3) else 0)
            toks.append(Token("code", i, data[i:i + k]))
            i += k
            continue
        if b == 0x00:
            toks.append(Token("code", i, data[i:i + 1]))
            i += 1
            continue
        raise TokenError("unknown byte %02x at %x" % (b, i), i, toks)
    return toks


def tokenize_tail(data, start):
    """tokenize(), but a remainder the grammar can't read is kept whole as
    one opaque token, as long as no text follows in it (the scene code at
    the end of some files)."""
    try:
        return tokenize(data, start)
    except TokenError as ex:
        if not ex.toks:
            raise
        # back up to the last token boundary before the failure
        good = ex.toks
        pos = ex.pos
    rest = data[pos:]
    if SJIS3.search(rest):
        raise ValueError("unreadable scene code with text in it at %x" % pos)
    return good + [Token("code", pos, rest)]


def parse(data):
    """(header offsets, stream start, tokens).  The stream starts at the
    smallest header-table word that tokenizes cleanly with every target on a
    token boundary."""
    try:
        hdr = header(data)
    except struct.error:
        hdr = []
    if any(t >= len(data) for t in hdr):
        hdr = []
    words = set()
    order = sorted(hdr)
    for t, nxt in zip(order, order[1:] + [None]):
        end = nxt if nxt is not None else t
        for p in range(t, end, 2):
            if p + 1 < len(data):
                words.add(struct.unpack_from("<H", data, p)[0])
    hdr_end = max(hdr) if hdr else 0
    for s in sorted(w for w in words if hdr_end <= w < len(data)):
        try:
            toks = tokenize_tail(data, s)
        except (ValueError, IndexError):
            continue
        starts = {t.start for t in toks} | {len(data)}
        if all(tg in starts for t in toks for _o, tg in t.targets):
            return hdr, s, toks
    # some engines' scene files have no header: the stream starts at 0
    try:
        toks = tokenize_tail(data, 0)
        starts = {t.start for t in toks} | {len(data)}
        if all(tg in starts for t in toks for _o, tg in t.targets):
            return [], 0, toks
    except (ValueError, IndexError):
        pass
    raise ValueError("no clean stream start")


def table_words(data, hdr, stream):
    """(position, value) of the words in header tables 0 and 1 (entry
    points and blocks; the later tables are byte data and the scene's local
    flags) that point into the stream."""
    out = []
    for t, nxt in list(zip(hdr, hdr[1:] + [stream]))[:2]:
        for p in range(t, min(nxt, stream), 2):
            if p + 1 < stream:
                w = struct.unpack_from("<H", data, p)[0]
                if stream <= w <= len(data):
                    out.append((p, w))
    return out


def rebuild(data, texts):
    """Replace text tokens ({token start: new bytes}); every offset moved."""
    hdr, stream, toks = parse(data)
    starts = {t.start for t in toks}
    tw = [(p, w) for p, w in table_words(data, hdr, stream) if w in starts or w == len(data)]
    new_pos, out, pos = {}, bytearray(data[:stream]), stream
    for t in toks:
        new_pos[t.start] = len(out)
        raw = texts.get(t.start, t.raw) if t.kind == "text" else t.raw
        out += raw
    new_pos[len(data)] = len(out)
    for t in toks:                                   # goto operands
        for off, tg in t.targets:
            struct.pack_into("<H", out, new_pos[t.start] + off, new_pos[tg])
    for p, w in tw:                                  # header tables
        struct.pack_into("<H", out, p, new_pos[w])
    return bytes(out)


def messages(data):
    """[(token start, text bytes)] for the text runs."""
    _h, _s, toks = parse(data)
    return [(t.start, t.raw) for t in toks if t.kind == "text"]
