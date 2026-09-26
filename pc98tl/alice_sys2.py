"""Alice Soft System 2 scenario (ADISK.DAT) disassembler / reassembler.

Opcode lengths follow the reference interpreter in kichikuou/system3-sdl2
(src/sys/nact_sys2.cpp, NACT_Sys2::cmd_branch skip table + nact.cpp).

A page is a byte string: [default_addr:u16] [commands...].  All in-page jump
targets are absolute byte offsets into the page, so after text is resized we
re-layout the page and rewrite every address field.  Page jumps/calls use page
numbers (via expressions) and are unaffected by resizing.
"""
import struct


class Sys2Error(Exception):
    pass


def is_message(c):
    return c == 0x20 or c & 0x80


def mblen(c):
    # Same rule as ADV.COM's lead-byte test (Dalk: CS:1A19): 80-9F and E0-FF.
    return 2 if (0x80 <= c <= 0x9F or c >= 0xE0) else 1


class Op:
    """One instruction. `parts` is a list of bytes objects and ('addr', old) tuples."""
    __slots__ = ("addr", "cmd", "parts", "text")

    def __init__(self, addr, cmd, parts, text=None):
        self.addr, self.cmd, self.parts, self.text = addr, cmd, parts, text

    def size(self):
        n = 0
        for p in self.parts:
            n += 2 if isinstance(p, tuple) else len(p)
        return n

    def targets(self):
        return [p[1] for p in self.parts if isinstance(p, tuple)]


class Page:
    def __init__(self, index, data, game="dalk"):
        self.index = index
        self.raw = data
        self.game = game
        self.default_addr = struct.unpack_from("<H", data, 0)[0]
        self.ops, self.tail_addr = self._disasm(data)

    # -- decoding helpers --------------------------------------------------
    def _disasm(self, d):
        ops = []
        p = 2
        n = len(d)
        menu_open = False

        def cali(p):
            s = p
            while True:
                if p >= n:
                    raise Sys2Error("expr runs off page")
                b = d[p]
                if b == 0x7F:
                    return p + 1
                if 0xC0 <= b or b <= 0x3F:
                    p += 2
                else:
                    p += 1

        # Code ends where the zero padding of the last sector begins.  Find the
        # last non-zero byte; everything after is padding.
        end = n
        while end > 2 and d[end - 1] == 0:
            end -= 1

        while p < end:
            a = p
            c = d[p]
            if c == 0x1A:  # DOS EOF marker terminates the page's code
                self.eof_tail = bytes(d[p:end])
                return ops, p
            p += 1
            ch = chr(c)
            if is_message(c):
                q = a
                while q < n and is_message(d[q]):
                    q += mblen(d[q])
                ops.append(Op(a, "text", [bytes(d[a:q])], text=bytes(d[a:q])))
                p = q
                continue
            if ch == "!":
                idx = d[p]; p += 1
                if not (0x80 <= idx <= 0xBF):
                    p += 1
                p = cali(p)
            elif ch == "{":
                p = cali(p)
            elif ch in "}]AFKR":
                pass
            elif ch in "@\\":
                t = struct.unpack_from("<H", d, p)[0]
                ops.append(Op(a, ch, [bytes([c]), ("addr", t)]))
                p += 2
                continue
            elif ch in "&%G":
                p = cali(p)
            elif ch == "$":
                if not menu_open:
                    t = struct.unpack_from("<H", d, p)[0]
                    ops.append(Op(a, "$", [b"$", ("addr", t)]))
                    p += 2
                    menu_open = True
                else:
                    ops.append(Op(a, "$end", [b"$"]))
                    menu_open = False
                continue
            elif ch == "[":
                vb = bytes(d[p:p + 2])
                t = struct.unpack_from("<H", d, p + 2)[0]
                ops.append(Op(a, "[", [b"[", vb, ("addr", t)]))
                p += 4
                continue
            elif ch == ":":
                q = cali(p)
                vb = bytes(d[q:q + 2])
                t = struct.unpack_from("<H", d, q + 2)[0]
                ops.append(Op(a, ":", [bytes(d[a:q]), vb, ("addr", t)]))
                p = q + 4
                continue
            elif ch == "B":
                for _ in range(7): p = cali(p)
            elif ch == "D":
                for _ in range(8): p = cali(p)
            elif ch in "ETOW":
                for _ in range({"E": 3, "T": 3, "O": 3, "W": 4}[ch]): p = cali(p)
            elif ch == "H":
                p += 1
                p = cali(p)
            elif ch == "I":
                for _ in range(3): p = cali(p)
            elif ch in "JNUYZ":
                p = cali(p); p = cali(p)
            elif ch in "LPQSX":
                p += 1
            elif ch == "M":
                q = p
                while d[q] != ord(":"):
                    q += mblen(d[q])
                ops.append(Op(a, "M", [b"M", bytes(d[p:q]), b":"], text=bytes(d[p:q])))
                p = q + 1
                continue
            elif ch == "V":
                p += 1
                for _ in range(29): p = cali(p)
            else:
                raise Sys2Error("page %d: unknown command %r at %04x" % (self.index, ch, a))
            ops.append(Op(a, ch, [bytes(d[a:p])]))
        self.eof_tail = b""
        return ops, p

    # -- analysis -----------------------------------------------------------
    def all_targets(self):
        t = {self.default_addr}
        for op in self.ops:
            t.update(x for x in op.targets() if x)  # '\\' 0 == return
        return t

    def validate(self):
        starts = {op.addr for op in self.ops}
        bad = [t for t in self.all_targets() if t not in starts and t != self.tail_addr]
        return bad

    def assemble(self, replace=None):
        """Re-emit the page. `replace` maps op index -> new list of parts."""
        replace = replace or {}
        ops = [(i, replace.get(i, op.parts), op.addr) for i, op in enumerate(self.ops)]
        # layout
        newaddr = {}
        pos = 2
        for i, parts, old in ops:
            newaddr.setdefault(old, pos)
            pos += sum(2 if isinstance(p, tuple) else len(p) for p in parts)
        newaddr.setdefault(self.tail_addr, pos)
        out = bytearray(struct.pack("<H", newaddr[self.default_addr]))
        for i, parts, old in ops:
            for p in parts:
                if isinstance(p, tuple):
                    t = p[1]
                    out += struct.pack("<H", newaddr[t] if t else 0)
                else:
                    out += p
        return bytes(out + self.eof_tail)


class ADisk:
    """ADISK.DAT (single-disk HD layout)."""

    def __init__(self, data):
        self.data = data
        link_sector, data_sector = struct.unpack_from("<HH", data, 0)
        lt = data[(link_sector - 1) * 256:(data_sector - 1) * 256]
        self.link_sector, self.data_sector = link_sector, data_sector
        self.links = []
        for i in range(len(lt) // 2):
            disk, li = lt[i * 2], lt[i * 2 + 1]
            self.links.append((disk, li))
        self.page_data = []
        for disk, li in self.links:
            if disk == 0 or disk == 0x1A:
                self.page_data.append(None)
                continue
            if disk != 1:
                raise Sys2Error("multi-disk ADISK not supported (disk %d)" % disk)
            s, e = struct.unpack_from("<HH", data, li * 2)
            self.page_data.append(data[(s - 1) * 256:(e - 1) * 256] if e > s else None)

    def build(self, pages):
        """Rebuild the file with new page bytes (list aligned with self.links)."""
        # The header, pointer table and link table are kept verbatim up to the
        # first page body; bodies are re-packed sector-aligned and their
        # (start, end) sector words at li*2 rewritten.
        firsts = []
        for disk, li in self.links:
            if disk == 1:
                firsts.append(struct.unpack_from("<H", self.data, li * 2)[0])
        sector = min(firsts)
        body_start = (sector - 1) * 256
        head = bytearray(self.data[:body_start])
        body = bytearray()
        cur = sector
        order = sorted({li for d, li in self.links if d == 1})
        li_to_page = {li: i for i, (d, li) in enumerate(self.links) if d == 1}
        for li in order:
            pg = pages[li_to_page[li]]
            pg = pg or b""
            nsec = (len(pg) + 255) // 256
            struct.pack_into("<HH", head, li * 2, cur, cur + nsec)
            body += pg.ljust(nsec * 256, b"\0")
            cur += nsec
        return bytes(head + body)
