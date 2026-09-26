"""Alice Soft System 1-3 scenario disassembler / reassembler (table driven).

Argument layouts follow the reference interpreter kichikuou/system3-sdl2
(src/sys/nact.cpp, nact_sys2.cpp, nact_sys3.cpp).

A page is [default_addr:u16] [commands...].  In-page jump targets are absolute
byte offsets, so after text changes size the page is re-laid out and every
address field rewritten.  Page jumps/calls use page numbers and are unaffected.

Argument codes: e = expression (ends at 0x7F), b = byte, a = in-page address
(u16), S = string up to ':'.
"""
import struct


class SysError(Exception):
    pass


def mblen(c):
    # Same rule as ADV.COM's lead-byte test: 80-9F and E0-FF start 2-byte chars.
    return 2 if (0x80 <= c <= 0x9F or c >= 0xE0) else 1


def is_message(c):
    return c == 0x20 or c & 0x80


COMMON = {"}": "", "]": "", "A": "", "F": "", "K": "", "R": "", "@": "a", "\\": "a",
          "&": "e", "%": "e", "[": "bba", ":": "ebba", "M": "S", "S": "b", "X": "b"}
TABLES = {
    1: dict(COMMON, **{"{": "e", "G": "b", "L": "b", "P": "b", "Q": "b", "U": "bb",
                       "Y": "ee", "Z": "ee"}),
    2: dict(COMMON, **{"{": "e", "G": "e", "B": "eeeeeee", "D": "eeeeeeee", "E": "eee",
                       "T": "eee", "O": "eee", "W": "eeee", "H": "be", "I": "eee", "J": "ee",
                       "N": "ee", "U": "ee", "Y": "ee", "Z": "ee", "L": "b", "P": "b", "Q": "b",
                       "V": "b" + "e" * 29}),
    3: dict(COMMON, **{"{": "ea", "B": "beeeeee", "E": "eeeeee", "G": "e", "H": "be",
                       "I": "eeeeee", "J": "ee", "K": "b", "L": "e", "N": "bee", "O": "ee",
                       "P": "eeee", "Q": "e", "T": "ee", "U": "ee", "V": "ee", "W": "eee",
                       "Y": "ee", "Z": "ee"}),
}


class Op:
    """One instruction. `parts` is a list of bytes objects and ('addr', old) tuples."""
    __slots__ = ("addr", "cmd", "parts", "text")

    def __init__(self, addr, cmd, parts, text=None):
        self.addr, self.cmd, self.parts, self.text = addr, cmd, parts, text

    def targets(self):
        return [p[1] for p in self.parts if isinstance(p, tuple)]


class Page:
    def __init__(self, index, data, version=2):
        self.index = index
        self.version = version
        self.table = TABLES[version]
        self.default_addr = struct.unpack_from("<H", data, 0)[0]
        self.eof_tail = b""
        self.ops, self.tail_addr = self._disasm(data, set())
        # A branch can end inside what looks like one text run (System 3:
        # "{cond: A} B" shows A only when cond holds).  Split runs at targets.
        if self.validate():
            self.ops, self.tail_addr = self._disasm(data, self.all_targets())

    def _disasm(self, d, splits):
        n = len(d)
        end = n
        while end > 2 and d[end - 1] == 0:
            end -= 1

        def expr(p):
            while True:
                if p >= n:
                    raise SysError("page %d: expression runs off the page" % self.index)
                b = d[p]
                if b == 0x7F:
                    return p + 1
                p += 2 if (b >= 0xC0 or b <= 0x3F) else 1

        ops, p, menu_open = [], 2, False
        while p < end:
            a, c = p, d[p]
            if c == 0x1A:  # DOS EOF marker ends the page's code
                self.eof_tail = bytes(d[p:end])
                return ops, p
            if is_message(c):
                q = a
                while q < n and is_message(d[q]) and (q == a or q not in splits):
                    q += mblen(d[q])
                ops.append(Op(a, "text", [bytes(d[a:q])], text=bytes(d[a:q])))
                p = q
                continue
            ch = chr(c)
            p += 1
            if ch == "!":
                p += 1 if 0x80 <= d[p] <= 0xBF else 2
                p = expr(p)
                ops.append(Op(a, ch, [bytes(d[a:p])]))
                continue
            if ch == "$":
                if not menu_open:
                    ops.append(Op(a, "$", [b"$", ("addr", struct.unpack_from("<H", d, p)[0])]))
                    p += 2
                else:
                    ops.append(Op(a, "$end", [b"$"]))
                menu_open = not menu_open
                continue
            spec = self.table.get(ch)
            if spec is None:
                raise SysError("page %d: unknown command %r at %04x" % (self.index, ch, a))
            if spec == "S":
                q = p
                while d[q] != 0x3A:
                    q += mblen(d[q])
                ops.append(Op(a, "M", [b"M", bytes(d[p:q]), b":"], text=bytes(d[p:q])))
                p = q + 1
                continue
            parts, start = [], a
            for code in spec:
                if code == "e":
                    p = expr(p)
                elif code == "b":
                    p += 1
                elif code == "a":
                    parts.append(bytes(d[start:p]))
                    parts.append(("addr", struct.unpack_from("<H", d, p)[0]))
                    p += 2
                    start = p
            if start < p or not parts:
                parts.append(bytes(d[start:p]))
            ops.append(Op(a, ch, parts))
        return ops, p

    def all_targets(self):
        t = {self.default_addr}
        for op in self.ops:
            t.update(x for x in op.targets() if x)  # '\\' 0 == return
        return t

    def validate(self):
        starts = {op.addr for op in self.ops}
        return [t for t in self.all_targets() if t not in starts and t != self.tail_addr]

    def assemble(self, replace=None):
        """Re-emit the page. `replace` maps op index -> new list of parts."""
        replace = replace or {}
        ops = [(replace.get(i, op.parts), op.addr) for i, op in enumerate(self.ops)]
        newaddr, pos = {}, 2
        for parts, old in ops:
            newaddr.setdefault(old, pos)
            pos += sum(2 if isinstance(x, tuple) else len(x) for x in parts)
        newaddr.setdefault(self.tail_addr, pos)
        out = bytearray(struct.pack("<H", newaddr[self.default_addr]))
        for parts, _old in ops:
            for x in parts:
                if isinstance(x, tuple):
                    out += struct.pack("<H", newaddr[x[1]] if x[1] else 0)
                else:
                    out += x
        return bytes(out + self.eof_tail)


class ADisk:
    """Scenario container: ADISK.DAT holds the link table; pages may live in
    ADISK/BDISK/... .DAT (disk number 1, 2, ... in the link table)."""

    def __init__(self, files):
        """files: {disk number: bytes}, disk 1 = ADISK.DAT."""
        self.files = files
        a = files[1]
        self.link_sector, self.data_sector = struct.unpack_from("<HH", a, 0)
        lt = a[(self.link_sector - 1) * 256:(self.data_sector - 1) * 256]
        self.links = [(lt[i * 2], lt[i * 2 + 1]) for i in range(len(lt) // 2)]
        # A disk's pointer table holds strictly increasing sector numbers; the
        # shared link table can list more pages than a given scenario disk has
        # (Super D.P.S), so stop at the first entry that breaks the sequence.
        self.valid = {}
        for disk, data in files.items():
            n, li = len(data) // 256, 1
            while (li + 1) * 2 + 2 <= len(data):
                s_, e_ = struct.unpack_from("<HH", data, li * 2)
                if not (1 <= s_ < e_ and e_ - 1 <= n):
                    break
                li += 1
            self.valid[disk] = li - 1  # entries 1..valid are real pages
        self.page_data = []
        for disk, li in self.links:
            if disk in (0, 0x1A) or disk not in files or li > self.valid.get(disk, 0):
                self.page_data.append(None)
                continue
            s, e = struct.unpack_from("<HH", files[disk], li * 2)
            self.page_data.append(files[disk][(s - 1) * 256:(e - 1) * 256] if e > s else None)

    def build(self, pages):
        """Rebuild every disk file with new page bytes (aligned with self.links)."""
        out = {}
        for disk, data in self.files.items():
            linked = {li: i for i, (d, li) in enumerate(self.links) if d == disk}
            if not linked:
                out[disk] = data
                continue
            # every pointer-table entry is repacked; entries no link points to
            # (orphan pages) keep their original bytes
            entries = range(1, self.valid.get(disk, 0) + 1)
            first = min(struct.unpack_from("<H", data, li * 2)[0] for li in entries)
            last_end = max(struct.unpack_from("<H", data, li * 2 + 2)[0] for li in entries)
            slack = data[(last_end - 1) * 256:]  # bytes after the last page (kept as-is)
            head = bytearray(data[:(first - 1) * 256])
            body, cur = bytearray(), first
            for li in entries:
                if li in linked:
                    pg = pages[linked[li]] or b""
                else:
                    s_, e_ = struct.unpack_from("<HH", data, li * 2)
                    pg = data[(s_ - 1) * 256:(e_ - 1) * 256]
                nsec = (len(pg) + 255) // 256
                struct.pack_into("<HH", head, li * 2, cur, cur + nsec)
                body += pg.ljust(nsec * 256, b"\0")
                cur += nsec
            out[disk] = bytes(head + body) + slack
        return out
