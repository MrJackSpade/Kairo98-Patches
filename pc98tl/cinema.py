"""Foster's CINEMA engine (Time Stripper Mako-chan): the FA1 archive, its compression, the scripts.

FA1 (A.FA1, B.FA1): "FA1\\0", a dword (the end of the members' data), a word (the number of
members), a word (flags); the members from offset 12, one after another, each starting at an even
offset (a byte after an odd-sized one: FAD.BIN finds a member by adding up the sizes so); zeros up to the directory (the data's end rounded
up to 400h, where FAD.BIN reads it), 20 bytes per member, every byte inverted: a name (8 bytes) and an extension (3, both space-padded), a
flag (1 compressed, 0 stored), the dword size in the archive and the dword size unpacked.  FAD.BIN,
the archive's own driver, is its first member (TSM.COM loads the archive's head and calls it).

Compression: a stream of 16-bit words of flags (low byte first, read from the top bit, a new word
when the last one runs out) and bytes, read in turn:
  1                  a byte, copied
  01 0 b             two bytes from b+1 back
  01 1 b xxx         two bytes from (b<<3|xxx) + 101h back; FFh 111 ends the stream (then 1) or,
                     with 0, only moves the output's segment on
  00 1 b x           a length (below) from (b<<1|x) + 1 back
  00 01 b x / 00 001 b xx / 00 0001 b xxx / 00 0000 b xxxx
                     a length from ((100h|b) << 1, 2, 3, 4 | the bits) + 1 back
  length: 1 = 3, 01 = 4, 001 x = 5+x, 0001 xx = 7+xx, 00001 xxxx = 11+xxxx, 00000 b = 27+b.

Scripts (TSM_nn.BIN, AUTOEXEC.BIN, STAFF.BIN; ESC.BIN, the escape menu, loaded at 7800h) are run by
CINEMA.BIN from offset 0, op by op, in a 32 KB buffer whose last 2 KB (7800h) hold ESC.BIN.  The ops'
lengths are CINEMA.BIN's (its table of 72 routines); the ones that take an address in the script:
  02 next cnt var(2) items(cnt)   a menu: its items' text addresses; the op ends at `next`
  03/09/0A/17/39 next ...         a message (09: text up to a NUL), a file to load (03 to an
                                  address, 0A, 17, 39): the op ends at `next`
  04 a                            goto; 32 a: gosub; 33 return
  05 var(2) a...                  switch on a variable: one address per value
  08 c var(2) v a                 if: goes to `a` when the comparison fails
  29 a / 00 a                     palette data / machine code in the script (AUTOEXEC.BIN only)
  3E (24 bytes) items             a menu: its items' text addresses (after the 24 bytes when the
                                  word at 16h is set, as many as the word at 14h)
A switch's table runs up to the code after it: the first address past the op, or a label.
Text: Shift-JIS, and bytes below 80h drawn half-width (MB3N.BIN's ANK glyphs); `\\` and a letter
with a decimal number after it is a command: \\f clears the window before the next letter, \\n is a
new line, \\t the delay between letters, \\s \\i \\k the window's settings.
"""
import re
import struct

DIR_ENTRY = 20


def w(d, i):
    return struct.unpack_from("<H", d, i)[0]


# --- FA1 ---------------------------------------------------------------------------------------

def decompress(src, i=0):
    """(the data unpacked from src[i:], the bytes read)"""
    out = bytearray()
    st = [i, 0, 0]  # position, flags word, bits left

    def bit():
        if st[2] == 0:
            st[1] = src[st[0]] | src[st[0] + 1] << 8
            st[0] += 2
            st[2] = 16
        st[2] -= 1
        b = st[1] >> 15 & 1
        st[1] = st[1] << 1 & 0xFFFF
        return b

    def byte():
        v = src[st[0]]
        st[0] += 1
        return v

    def bits(k, v):
        for _ in range(k):
            v = v << 1 | bit()
        return v
    while True:
        if bit():
            out.append(byte())
            continue
        if bit():
            if not bit():
                dist, ln = byte() + 1, 2
            else:
                ax = bits(3, byte()) + 0x100
                if ax >= 0x8FF:
                    if bit():
                        break
                    continue
                dist, ln = ax + 1, 2
        else:
            if bit():
                ax = bits(1, byte())
            elif bit():
                ax = bits(1, 0x100 | byte())
            elif bit():
                ax = bits(2, 0x100 | byte())
            elif bit():
                ax = bits(3, 0x100 | byte())
            else:
                ax = bits(4, 0x100 | byte())
            dist = ax + 1
            if bit():
                ln = 3
            elif bit():
                ln = 4
            elif bit():
                ln = 5 + bit()
            elif bit():
                ln = bits(2, 0) + 7
            elif bit():
                ln = bits(4, 0) + 11
            else:
                ln = byte() + 27
        for _ in range(ln):
            out.append(out[-dist])
    return bytes(out), st[0] - i


def compress(data):
    """`data` as a stream the program unpacks: every byte a literal (flag 1), then the end
    (0 1 1, FFh, 111, 1)."""
    out = bytearray()
    bits = [1] * len(data) + [0, 1, 1, 1, 1, 1, 1]
    lits = list(data) + [0xFF]
    # the bytes go out in the order the unpacker reads them: a flags word before the bits it holds
    k, li = 0, 0
    while k < len(bits):
        chunk = bits[k:k + 16]
        word = 0
        for j, b in enumerate(chunk):
            word |= b << (15 - j)
        out += bytes([word & 0xFF, word >> 8])
        for j, b in enumerate(chunk):
            pos = k + j
            if pos < len(data):
                out.append(lits[li])
                li += 1
            elif pos == len(data) + 2:
                out.append(0xFF)   # (the byte read after 0 1 1)
        k += 16
    return bytes(out)


def members(d):
    """(flags, [[name, flag, raw bytes, unpacked size, the byte after an odd-sized one]])"""
    if d[:4] != b"FA1\0":
        raise ValueError("not an FA1 archive")
    _end, n, flags = struct.unpack_from("<IHH", d, 4)
    at = len(d) - DIR_ENTRY * n
    out, pos = [], 12
    for k in range(n):
        e = bytes(255 - b for b in d[at + DIR_ENTRY * k:at + DIR_ENTRY * (k + 1)])
        name = e[:8].decode("ascii").rstrip() + "." + e[8:11].decode("ascii").rstrip()
        flag, size, full = e[11], *struct.unpack_from("<II", e, 12)
        out.append([name, flag, d[pos:pos + size], full, d[pos + size] if size & 1 else None])
        pos += size + (size & 1)
    return flags, out


def data(m):
    """A member's unpacked bytes."""
    _name, flag, raw, full, _pad = m
    if not flag:
        return raw
    out, _n = decompress(raw)
    if len(out) != full:
        raise ValueError("%s: unpacked %d bytes, the directory says %d" % (m[0], len(out), full))
    return out


def archive(flags, items):
    """The archive of `items` (as members() gives them; a changed member stored, flag 0)."""
    body = bytearray()
    ents = []
    for name, flag, raw, full, pad in items:
        body += raw
        if len(raw) & 1:
            body.append(pad or 0)
        stem, _, ext = name.partition(".")
        e = stem.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii") + bytes([flag]) + \
            struct.pack("<II", len(raw), full)
        ents.append(bytes(255 - b for b in e))
    end = 12 + len(body)
    at = (end + 0x3FF) & ~0x3FF
    return b"FA1\0" + struct.pack("<IHH", end, len(items), flags) + bytes(body) + \
        bytes(at - end) + b"".join(ents)


# --- scripts -----------------------------------------------------------------------------------

FIX = {0x00: 3, 0x01: 1, 0x04: 3, 0x06: 1, 0x07: 4, 0x08: 7, 0x0B: 5, 0x0C: 1, 0x0D: 1, 0x0E: 1, 0x0F: 1,
       0x10: 1, 0x11: 1, 0x12: 2, 0x13: 3, 0x14: 4, 0x15: 3, 0x18: 1, 0x19: 1, 0x1A: 2, 0x1B: 3, 0x1C: 3,
       0x1D: 1, 0x1E: 3, 0x1F: 1, 0x20: 1, 0x21: 4, 0x22: 4, 0x23: 7, 0x24: 7, 0x25: 2, 0x26: 5, 0x27: 3,
       0x28: 2, 0x29: 3, 0x2A: 3, 0x2B: 1, 0x2C: 3, 0x2D: 1, 0x2E: 2, 0x2F: 4, 0x30: 2, 0x31: 1, 0x32: 3,
       0x33: 1, 0x34: 3, 0x35: 3, 0x36: 2, 0x37: 1, 0x38: 1, 0x3A: 1, 0x3B: 5, 0x3C: 1, 0x3D: 1, 0x3F: 1,
       0x40: 1, 0x41: 1, 0x42: 1, 0x43: 4, 0x44: 7, 0x45: 3, 0x46: 10, 0x47: 7}
NEXT = {0x02, 0x03, 0x09, 0x0A, 0x17, 0x39}
FLOW_END = {0x01, 0x04, 0x05, 0x16, 0x33}
ESC_AT = 0x7800      # ESC.BIN's place in the script's buffer
BUFFER_END = 0x8000


class Script:
    """A script's ops, walked from its start: ops {addr: (op, end)}, items {addr: owner op} (the menus'
    text), fields {addr of a word: kind} (the words that hold an address in the script)."""

    def __init__(self, d, base=0):
        self.d, self.base = d, base
        labels = set()
        for _ in range(64):
            ok = self._walk(labels)
            if self.found == labels:
                if not ok:
                    raise ValueError("script: %s" % "; ".join(self.errs[:3]))
                return
            labels = self.found
        raise ValueError("script: the switch tables do not settle")

    def inside(self, a):
        return self.base <= a < self.base + len(self.d)

    def b(self, a):
        return self.d[a - self.base]

    def w(self, a):
        return w(self.d, a - self.base)

    def _walk(self, labels):
        d = self.d
        self.ops, self.items, self.fields, self.found, self.errs = {}, {}, {}, set(), []
        todo = [self.base]
        end = self.base + len(d)
        while todo:
            i = todo.pop()
            while i not in self.ops and self.inside(i):
                op = self.b(i)
                if i + max(FIX.get(op, 3), 1) > end or (op not in FIX and i + 3 > end):
                    self.errs.append("end at %x" % i)
                    break
                fields = []
                jump = None
                if op in NEXT:
                    e = self.w(i + 1)
                    fields.append(i + 1)
                    if op == 0x09 and not i < e <= end:
                        # (a message that goes on somewhere else: one the English put after the end)
                        jump, e = e, d.index(0, i + 3 - self.base) + 1 + self.base
                        self.found.add(jump)
                        todo.append(jump)
                    if op == 0x02:
                        for k in range(self.b(i + 3)):
                            a = self.w(i + 6 + 2 * k)
                            fields.append(i + 6 + 2 * k)
                            self.items[a] = i
                elif op == 0x16:
                    e = d.index(0, i + 1 - self.base) + 1 + self.base
                elif op == 0x3E:
                    cnt = self.w(i + 0x15) if self.w(i + 0x17) else 0
                    e = i + 25 + 2 * cnt
                    for k in range(cnt):
                        fields.append(i + 25 + 2 * k)
                        self.items[self.w(i + 25 + 2 * k)] = i
                elif op == 0x05:
                    j, lo = i + 3, end
                    while j < lo and j + 2 <= end:
                        t = self.w(j)
                        if t > i:
                            lo = min(lo, t)
                        j += 2
                    e = min([x for x in labels if x >= i + 5] + [j])
                    for j in range(i + 3, min(e, end - 1), 2):
                        fields.append(j)
                        self.found.add(self.w(j))
                        todo.append(self.w(j))
                elif op in FIX:
                    e = i + FIX[op]
                else:
                    self.errs.append("op %02x at %x" % (op, i))
                    break
                if e <= i or e > end:
                    self.errs.append("op %02x at %x ends at %x" % (op, i, e))
                    break
                if op in (0x04, 0x32, 0x29, 0x00):
                    fields.append(i + 1)
                if op == 0x08:
                    fields.append(i + 5)
                for f in fields:
                    self.fields[f] = op
                for t in ([self.w(i + 5)] if op == 0x08 else [self.w(i + 1)] if op in (0x04, 0x32) else []):
                    self.found.add(t)
                    todo.append(t)
                self.ops[i] = (op, e)
                if op in FLOW_END or jump is not None:
                    break
                i = e
        return not self.errs


ESCAPE = re.compile(rb"\\([a-z])([0-9,]*)")


def split_text(raw):
    """(prefix, visible, suffix): the commands before and after the visible text; inside it, a new
    line (\\n) is kept as a newline character.  None when another command is inside the text."""
    parts, i = [], 0
    while i < len(raw):
        m = ESCAPE.match(raw, i)
        if m:
            parts.append(("c", m.group(0)))
            i = m.end()
            continue
        n = 2 if (0x81 <= raw[i] <= 0x9F or 0xE0 <= raw[i] <= 0xFC) else 1
        parts.append(("t", raw[i:i + n]))
        i += n
    a = 0
    while a < len(parts) and parts[a][0] == "c":
        a += 1
    b = len(parts)
    while b > a and parts[b - 1][0] == "c":
        b -= 1
    mid = parts[a:b]
    if any(k == "c" and v != b"\\n" for k, v in mid):
        return None
    prefix = b"".join(v for _k, v in parts[:a])
    suffix = b"".join(v for _k, v in parts[b:])
    visible = b"".join(b"\n" if k == "c" else v for k, v in mid)
    return prefix, visible.decode("cp932"), suffix


def texts(sc):
    """[(addr, kind, (start, end))]: the op 09 messages' and the menus' text (end: its NUL)."""
    out = []
    for a, (op, e) in sorted(sc.ops.items()):
        if op == 0x09:
            out.append((a, "msg", (a + 3, e - 1)))
    for a in sorted(sc.items):
        if sc.inside(a):
            s = a - sc.base
            out.append((a, "item", (a, sc.base + sc.d.index(0, s))))
    return out


def encode(text):
    """English as the engine draws it: ASCII a byte (half-width), another character full-width in
    Shift-JIS when it has one, else `?`; a backslash (the commands' mark) as `/`."""
    out = bytearray()
    for ch in text:
        if ch == "\\":
            out += b"/"
        elif " " <= ch <= "~":
            out += ch.encode("ascii")
        else:
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def rebuild(sc, new_text, pages, limit):
    """The script with new text, every address moved with it.  new_text {text start: bytes (NUL not
    included)}; pages {op 09 addr: [bytes per page]}: a message split over key waits (each page but
    the last its own op 09 ending in \\f, then op 3Fh).  limit: the address the script may not reach."""
    d, base = sc.d, sc.base
    old_end = base + len(d)
    order = sorted(sc.ops)
    # the spans: ops, and the bytes no op covers (copied as they are)
    spans, at = [], base
    for a in order:
        if a > at:
            spans.append((at, a, None))
        spans.append((a, sc.ops[a][1], a))
        at = max(at, sc.ops[a][1])
    if at < old_end:
        spans.append((at, old_end, None))
    starts = {}
    for t, kind, (s, e) in texts(sc):
        starts[s] = e
    # pass 1: sizes and the new address of every boundary
    pos = base
    moved = {}
    pieces = []
    for s, e, a in spans:
        moved[s] = pos
        if a is not None and a in pages:
            parts = pages[a]
            size = sum(3 + len(p) + 1 + 1 for p in parts[:-1]) + 3 + len(parts[-1]) + 1
            pieces.append(("pages", s, e, a, parts))
            pos += size
            continue
        segs, i = [], s
        while i < e:
            if i in starts and i in new_text:
                moved[i] = pos + sum(len(x) for x in segs)
                segs.append(new_text[i] + b"\0")
                i = starts[i] + 1
                continue
            if i in starts:
                moved[i] = pos + sum(len(x) for x in segs)
            j = i + 1
            while j < e and j not in starts:
                j += 1
            segs.append(d[i - base:j - base])
            i = j
        pieces.append(("bytes", s, e, a, segs))
        pos += sum(len(x) for x in segs)
    moved[old_end] = pos
    if pos > limit:
        raise OverflowError(pos)

    def where(old):
        """The new place of old byte `old` inside a span that was copied with its header unchanged."""
        if old in moved:
            return moved[old]
        s = max(k for k in moved if k <= old)
        return moved[s] + old - s

    def fix(v):
        if not sc.inside(v) and v != old_end:
            return v
        if v in moved:
            return moved[v]
        if any(s <= v < e for s, e, a in spans if a is None):
            return where(v)    # (op 29h's palette, in the bytes after the last op)
        raise ValueError("an address into the middle of something: %x" % v)
    out = bytearray()
    for kind, s, e, a, body in pieces:
        if kind == "pages":
            for k, p in enumerate(body):
                last = k == len(body) - 1
                nxt = fix(e) if last else base + len(out) + 3 + len(p) + 1
                out += b"\x09" + struct.pack("<H", nxt) + p + b"\0"
                if not last:
                    out += b"\x3F"
            continue
        out += b"".join(body)
        if a is None:
            continue
        for f in sc.fields:
            if s <= f < e:
                p = where(f) - base
                struct.pack_into("<H", out, p, fix(w(out, p)))
    return bytes(out)


def redirect(sc, new_text, pages, limit):
    """The script with new text, the code where it was (AUTOEXEC.BIN runs machine code from its own
    bytes): a text that fits is written in its place; a longer one is put after the script's end, a
    message by an op 04h to it (its op 09 there going on to the old one's end), a menu's item by its
    address."""
    d, base = bytearray(sc.d), sc.base
    tail = bytearray()
    end0 = base + len(d)
    for a, kind, (s, e) in texts(sc):
        t = new_text.get(s)
        if kind == "msg" and a in pages:
            parts = pages[a]
        elif t is not None:
            parts = [t]
        else:
            continue
        if len(parts) == 1 and len(parts[0]) <= e - s:
            d[s - base:e - base + 1] = parts[0] + bytes(e - s + 1 - len(parts[0]))
            continue
        here = end0 + len(tail)
        if kind == "item":
            tail += parts[0] + b"\0"
            for f in sc.fields:
                if sc.w(f) == s and sc.fields[f] in (0x02, 0x3E):
                    struct.pack_into("<H", d, f - base, here)
            continue
        old_next = sc.w(a + 1)
        for k, p in enumerate(parts):
            last = k == len(parts) - 1
            at = end0 + len(tail)
            nxt = old_next if last else at + 3 + len(p) + 1
            tail += b"\x09" + struct.pack("<H", nxt) + p + b"\0"
            if not last:
                tail += b"\x3F"
        d[a - base:a - base + 3] = b"\x04" + struct.pack("<H", here)
    if end0 + len(tail) > limit:
        raise OverflowError(end0 + len(tail))
    return bytes(d + tail)
