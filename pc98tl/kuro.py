"""Abogado Powers' Kuro no Danshou - The Literary Fragment (KURODAN\\GAME.EXE): its scenes and the program's text.

The scenes: SCENE.SCN, ASCENE.SCN and CSCENE.SCN hold the scene blocks end to end, every byte XORed with
AAh (as SCNDAT.TBL is).  SCNDAT.TBL: a byte, six words (the second the scene count), then a 21-byte entry
a scene (the file's name, 13 bytes, then the block's place and length, two dwords), other tables after.
GAME.EXE loads a scene's block whole, into a buffer the block's length and 400h more.

A block (`parse`, `build`): a word, the header's length; a byte n1, a byte n2, a byte nw; n1 3-byte
records, n2 5-byte records (the menus: they name entries of the next table by number); nw words, places
in the script (the offsets' table: the menus' objects and verbs, the replies, the jump targets); then the
script.  The script (`tokens`): commands `!` and a letter (b, g, j: a 2-byte argument; x: 2 bytes, `=`,
a byte; s, m, r, c, p: a parenthesised list, p's starting with a 2-byte type: 4 a caption `x,y,text`, 7 a
ruby reading in half-width kana for the word after it), conditions `[` 2 bytes `]` and an operator and a
byte (Es no Houteishiki's scripts also: `#i(` conditions `)` an if, `#l` its else, `#n` its end, and a
label's conditions in parentheses), `:` and a 2-byte argument (or, after a label, its condition), `"`, `,` and `&`, and Shift-JIS text
(`_r` a click and a new page, `_n` a new line in a caption, a 0Ah byte a new line).  Text outside quotes
is a label: an object's name and its verbs, written end to end, each starting where the offsets' table
points (GAME.EXE copies each into a 21-byte slot and matches them by string); the text between a label's
quotes is its reply.

English at any length: a block is written again with its text replaced and every offset in its table
moved with the text it points at (`build`); the scene files are written again and SCNDAT.TBL's entries
set (`rebuild`).  ASCII is drawn half-width by GAME.EXE itself; its message window breaks a line after
67 letters, at any letter, and pages itself after 4 rows.

The program's own text (`exe_strings`, `patch_program`): Japanese strings in its data segment (DGROUP),
passed as far pointers to its text renderer, to puts, printf and sprintf.  Each of those four is made to
jump, at a point after its frame is set, to a helper put in a segment of its own before DGROUP (the
segments after it moved up, pc98tl/adl5.py _move_up): the helper looks the string argument up in its
table and, for a string with English, points it at the English kept in the helper's segment; then it runs
the instructions it took the place of and jumps back.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .adl5 import _move_up
from .illusion_font import _asm

KEY = 0xAA
SCENE_FILES = ("SCENE.SCN", "ASCENE.SCN", "CSCENE.SCN")
ENTRY = 21
LIMIT = 0x10000 - 0x400 - 0x20          # a block's longest (16-bit places, the buffer's 400h more)


def xor(data):
    return bytes(c ^ KEY for c in data)


# ---- SCNDAT.TBL ------------------------------------------------------------------------------------
def table(tbl):
    """[(file name, place, length)] of the scenes in SCNDAT.TBL (decoded)."""
    count = struct.unpack_from("<H", tbl, 3)[0]
    out = []
    for i in range(count):
        k = 13 + ENTRY * i
        name = tbl[k:k + 13].split(b"\0")[0].decode("ascii").upper()
        off, ln = struct.unpack_from("<II", tbl, k + 13)
        out.append((name, off, ln))
    return out


def set_table(tbl, entries):
    out = bytearray(tbl)
    for i, (_name, off, ln) in enumerate(entries):
        struct.pack_into("<II", out, 13 + ENTRY * i + 13, off, ln)
    return bytes(out)


# ---- a block ---------------------------------------------------------------------------------------
def parse(b):
    """(head bytes before the offsets' table, offsets, script)."""
    hl = struct.unpack_from("<H", b, 0)[0]
    n1, n2, nw = b[2], b[3], b[4]
    p = 5 + 3 * n1 + 5 * n2
    if p + 2 * nw != hl:
        raise ValueError("a scene block's header is not laid out as expected")
    return bytes(b[:p]), list(struct.unpack_from("<%dH" % nw, b, p)), bytes(b[hl:])


def keys(head, offsets):
    """The places of the objects' names.  The 3-byte records map the picture's regions (by number) to
    menu records (their word at +1); a menu record (5 bytes) names its label by the offsets' table entry
    in its word at +3.  The records a region names are the objects: an object's name is matched by
    string with the region names loaded with the picture and never shown, so it is kept as it is; the
    other records are the verbs under them, shown in the menu."""
    n1, n2 = head[2], head[3]
    p = 5 + 3 * n1
    out = set()
    for j in range(n1):
        r = struct.unpack_from("<H", head, 5 + 3 * j + 1)[0]
        if r < n2:
            k = struct.unpack_from("<H", head, p + 5 * r + 3)[0]
            if k < len(offsets):
                out.add(offsets[k])
    return out


def join(head, offsets, script):
    return head + struct.pack("<%dH" % len(offsets), *offsets) + script


LEAD = set(range(0x81, 0xA0)) | set(range(0xE0, 0xF0))
KANA = set(range(0xA1, 0xE0))
DELIM = set(b'"()[]&:,=')


def _is_cmd(s, k):
    return s[k] == 0x21 and k + 1 < len(s) and 0x61 <= s[k + 1] <= 0x7A


def _is_block(s, k):
    """#i(...) an if, #l its else, #n its end (Es no Houteishiki's scripts)."""
    return s[k] == 0x23 and k + 1 < len(s) and s[k + 1] in b"iln"


def _texty(s, j):
    c = s[j]
    return c == 0x0A or c in KANA or (0x20 <= c < 0x7F and c not in DELIM and not _is_cmd(s, j)
                                      and not _is_block(s, j))


def tokens(s):
    """[(kind, start, end, extra)]: text, cmd (extra: the letter), open (a parenthesised command; extra:
    the letter, and for p its type), close, quote, comma, ruby, cond, colon, amp."""
    out = []
    k, n = 0, len(s)
    while k < n:
        c = s[k]
        if _is_cmd(s, k):
            L = chr(s[k + 1])
            if L in "bgj":
                out.append(("cmd", k, k + 4, L)); k += 4; continue
            if L == "x":
                if s[k + 4] != 0x3D:
                    raise ValueError("!x at %x is not laid out as expected" % k)
                out.append(("cmd", k, k + 6, L)); k += 6; continue
            if k + 2 < n and s[k + 2] == 0x28:
                if L == "p":
                    if s[k + 3] == 7:
                        e = s.index(b")", k + 5)
                        out.append(("ruby", k, e + 1, None)); k = e + 1; continue
                    out.append(("open", k, k + 5, ("p", s[k + 3]))); k += 5; continue
                out.append(("open", k, k + 3, (L, None))); k += 3; continue
            raise ValueError("a command at %x is not laid out as expected" % k)
        if _is_block(s, k):
            if s[k + 1] == 0x69:
                if s[k + 2] != 0x28:
                    raise ValueError("#i at %x is not laid out as expected" % k)
                out.append(("open", k, k + 3, ("i", None))); k += 3; continue
            out.append(("cmd", k, k + 2, chr(s[k + 1]))); k += 2; continue
        if c == 0x5B:
            if k + 5 < n and s[k + 3] == 0x5D and s[k + 4] in b"=+-<>}":
                out.append(("cond", k, k + 6, None)); k += 6; continue
            raise ValueError("a condition at %x is not laid out as expected" % k)
        if c == 0x28:
            # (a label's conditions in parentheses: Es no Houteishiki)
            out.append(("open", k, k + 1, ("(", None))); k += 1; continue
        if c == 0x29:
            out.append(("close", k, k + 1, None)); k += 1; continue
        if c == 0x3A:
            m = 1 if s[k + 1:k + 2] == b"[" else 3
            out.append(("colon", k, k + m, None)); k += m; continue
        if c == 0x22:
            out.append(("quote", k, k + 1, None)); k += 1; continue
        if c == 0x2C:
            out.append(("comma", k, k + 1, None)); k += 1; continue
        if c == 0x26:
            out.append(("amp", k, k + 1, None)); k += 1; continue
        if c in LEAD or _texty(s, k):
            j = k
            while j < n:
                if s[j] in LEAD and j + 1 < n:
                    j += 2
                elif _texty(s, j):
                    j += 1
                else:
                    break
            out.append(("text", k, j, None)); k = j; continue
        raise ValueError("an unknown byte %02x at %x" % (c, k))
    return out


def _japanese(b):
    k = 0
    while k < len(b):
        if b[k] in LEAD:
            return True
        if b[k] in KANA:
            return True
        k += 1
    return False


def units(s, offsets, names=()):
    """[(kind, start, end, parts)] of the script's translatable text: kind m (a message: inside !s(...) or
    a label's reply), u (a label piece after the object's name: a verb), c (a choice of !m(...)), n (a
    caption's text, !p(04 ..) after its x and y).  parts: [(kind, start, end)] with kind text, ruby or
    effect (a !p(...) inside a message with no text of its own), the unit starting and ending with text."""
    T = tokens(s)
    marks = set(offsets)
    # (text split where the offsets' table points)
    toks = []
    for t in T:
        if t[0] == "text":
            cuts = sorted(o for o in marks if t[1] < o < t[2])
            a = t[1]
            for o in cuts + [t[2]]:
                toks.append(("text", a, o, None))
                a = o
        else:
            toks.append(t)
    out = []
    stack = []                      # [kind, commas]
    quote = False
    cur = None                      # [kind, parts, depth]
    i = 0

    def close():
        nonlocal cur
        if cur:
            parts = cur[1]
            while parts and parts[-1][0] != "text":
                parts.pop()
            if parts and any(_japanese(s[a:e]) for k, a, e in parts if k == "text"):
                out.append((cur[0], parts[0][1], parts[-1][2], parts))
        cur = None

    while i < len(toks):
        kind, a, e, x = toks[i]
        ctx = stack[-1][0] if stack else ("label" if not quote else "reply")
        if kind == "text":
            cls = {"msg": "m", "reply": "m", "label": "u", "choice": "c"}.get(ctx)
            if ctx == "label" and a in names:
                cls = None
            if ctx == "card":
                cls = "n" if stack[-1][1] >= 2 else None
            if cls is None:
                close()
            elif cur and cur[0] == cls and cur[2] == len(stack) and a not in marks:
                cur[1].append(("text", a, e))
            else:
                close()
                cur = [cls, [("text", a, e)], len(stack)]
            i += 1
            continue
        if kind == "ruby" and cur and cur[0] == "m":
            cur[1].append(("ruby", a, e)); i += 1; continue
        if kind == "ruby":
            close()
            # (a ruby before a message's first word: the unit starts with it)
            cls = "m" if ctx in ("msg", "reply") else None
            if cls:
                cur = ["m", [("ruby", a, e)], len(stack)]
            i += 1
            continue
        if kind == "open" and x[0] == "p" and x[1] != 4 and ctx in ("msg", "reply"):
            # (an effect inside a message: kept in its place, as one part)
            depth, j = 1, i + 1
            while depth:
                if toks[j][0] == "open":
                    depth += 1
                elif toks[j][0] == "close":
                    depth -= 1
                j += 1
            end = toks[j - 1][2]
            if cur and cur[0] == "m" and cur[2] == len(stack):
                cur[1].append(("effect", a, end))
            else:
                close()
            i = j
            continue
        close()
        if kind == "open":
            L, typ = x
            stack.append([{"s": "msg", "m": "choice"}.get(L, "card" if (L == "p" and typ == 4) else "arg"), 0])
        elif kind == "close":
            if stack:
                stack.pop()
        elif kind == "quote" and not stack:
            quote = not quote
        elif kind == "comma" and stack:
            stack[-1][1] += 1
        i += 1
    close()
    return out


CODES = {b"_r": "{r}", b"_n": "{n}", b"_w": "{w}", b"_s": "{s}"}


def show(s, parts):
    """The unit's text: Japanese as itself, codes as {r} {n} {w} {s}, a 0Ah as a new line, a ruby as
    {R1}.., an effect as {C1}.."""
    out, r, c = "", 0, 0
    for kind, a, e in parts:
        if kind == "ruby":
            r += 1
            out += "{R%d}" % r
            continue
        if kind == "effect":
            c += 1
            out += "{C%d}" % c
            continue
        out += show_text(s[a:e])
    return out


def show_text(b):
    out, k = "", 0
    while k < len(b):
        if b[k] in LEAD and k + 1 < len(b):
            # (86A2h: NEC's long dash, written twice as a dash)
            out += "―" if b[k:k + 2] == b"\x86\xa2" else b[k:k + 2].decode("cp932", "replace")
            k += 2
        elif b[k:k + 2] in CODES:
            out += CODES[b[k:k + 2]]
            k += 2
        elif b[k] == 0x0A:
            out += "\n"
            k += 1
        else:
            out += bytes([b[k]]).decode("cp932", "replace")
            k += 1
    return out


def ruby_text(s, part):
    return s[part[1] + 5:part[2] - 1].decode("cp932", "replace")


def build(block, replace):
    """The block with unit text replaced: replace {start: bytes} (the unit starting there, as found by
    `units`, its whole span), offsets moved with what they point at."""
    head, offsets, s = parse(block)
    spans = {}
    for kind, a, e, _parts in units(s, offsets, keys(head, offsets)):
        if a in replace:
            spans[a] = (e, replace[a])
    out = bytearray()
    shift = []                      # (old start, old end, new start, new length)
    k = 0
    for a in sorted(spans):
        e, new = spans[a]
        out += s[k:a]
        shift.append((a, e, len(out), len(new)))
        out += new
        k = e
    out += s[k:]

    def move(o):
        d = 0
        for a, e, na, nl in shift:
            if o < a:
                break
            if o == a:
                return na
            if o < e:
                raise ValueError("an offset points inside replaced text")
            d = na + nl - e
        return o + d
    new = join(head, [move(o) for o in offsets], bytes(out))
    if len(new) > LIMIT:
        raise ValueError("%d bytes" % len(new))
    return new


def scenes(files, tbl):
    """[(index, file name, block bytes)] (decoded)."""
    return [(i, name, files[name][off:off + ln]) for i, (name, off, ln) in enumerate(table(tbl))]


def rebuild(files, tbl, blocks):
    """(files, table) with the scene blocks (in their table order) written again: each file's blocks laid
    end to end in the order of their old places."""
    ent = table(tbl)
    new_files, new_ent = {}, list(ent)
    for name in files:
        order = sorted((off, i) for i, (n, off, _l) in enumerate(ent) if n == name)
        out = bytearray()
        for off, i in order:
            new_ent[i] = (name, len(out), len(blocks[i]))
            out += blocks[i]
        new_files[name] = bytes(out)
    return new_files, set_table(tbl, new_ent)


# ---- GAME.EXE --------------------------------------------------------------------------------------
def _exe(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    img = bytearray(exe[hdr:])
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    return hdr, rel_at, img, fixups


# the entry: mov dx, DGROUP / mov cs:[x], dx
ENTRY_SIG = re.compile(rb"\xba(..)\x2e\x89\x16", re.S)


def dgroup(exe):
    _h, _r, img, _f = _exe(exe)
    m = ENTRY_SIG.match(bytes(img[:8]))
    if not m:
        raise SystemExit("GAME.EXE: the entry is not laid out as expected")
    return struct.unpack("<H", m.group(1))[0]


def exe_strings(exe):
    """[(offset in DGROUP, bytes)] of the program's Japanese strings: 0-ended runs in its initialized data
    with Shift-JIS in them and no control byte but 0Ah."""
    _h, _r, img, _f = _exe(exe)
    base = dgroup(exe) * 16
    out = []
    p = base
    while p < len(img):
        e = img.find(b"\0", p)
        if e < 0:
            break
        t = bytes(img[p:e])
        if len(t) >= 4 and re.search(rb"[\x81-\x9f\xe0-\xef][\x40-\xfc]", t) and \
                not re.search(rb"[\x00-\x09\x0b-\x1f\x7f]", t):
            try:
                t.decode("cp932")
                ok = True
            except UnicodeDecodeError:
                ok = all(0x81 <= t[k] <= 0x9F or 0xE0 <= t[k] <= 0xEF or 0x20 <= t[k] < 0x7F or t[k] in (0x0A,)
                         or 0xA1 <= t[k] <= 0xDF or (k and t[k - 1] >= 0x81) for k in range(len(t)))
            if ok and _sjis_ok(t):
                out.append((p - base, t))
        p = e + 1
    return out


def _sjis_ok(t):
    """Every byte a whole character: Shift-JIS pairs, ASCII, half-width kana, 0Ah."""
    k = 0
    while k < len(t):
        c = t[k]
        if c in LEAD:
            if k + 1 >= len(t) or not 0x40 <= t[k + 1] <= 0xFC or t[k + 1] == 0x7F:
                return False
            k += 2
        elif 0x20 <= c < 0x7F or c in KANA or c == 0x0A:
            k += 1
        else:
            return False
    return True


# the sites: (name, signature, the group the jump goes at, the far pointer's place from BP)
SITES = (
    # the text renderer: enter 0, 0 / push ds / push es / push di / push si / mov ax, DGROUP / mov ds, ax /
    # les si, [bp+0Ah] / mov bx, [bp+6]
    ("renderer", re.compile(rb"\xc8\x00\x00\x00\x1e\x06\x57\x56\xb8..\x8e\xd8(\xc4\x76\x0a\x8b\x5e\x06)", re.S), 0x0A),
    # puts: push bp / mov bp, sp / push si / mov ax, [bp+6] / or ax, [bp+8]
    ("puts", re.compile(rb"\x55\x8b\xec\x56(\x8b\x46\x06\x0b\x46\x08)\x75\x04\x33\xc0", re.S), 0x06),
    # printf: push bp / mov bp, sp / mov ax, (its writer) / push ax / push ds
    ("printf", re.compile(rb"\x55\x8b\xec(\xb8..\x50\x1e)\xb8..\x50\xff\x76\x08\xff\x76\x06", re.S), 0x06),
    # sprintf and vsprintf: push bp / mov bp, sp / les bx, [bp+6] / mov byte es:[bx], 0 / ... / then
    # lea ax, [bp+0Eh] (the arguments) or push word [bp+0Eh] (the list)
    ("sprintf", re.compile(rb"\x55\x8b\xec(\xc4\x5e\x06\x26\xc6\x07\x00)\xb8..\x50\x16\x8d\x46\x06\x50"
                           rb"\xff\x76\x0c\xff\x76\x0a\x8d\x46\x0e", re.S), 0x0A),
    ("vsprintf", re.compile(rb"\x55\x8b\xec(\xc4\x5e\x06\x26\xc6\x07\x00)\xb8..\x50\x16\x8d\x46\x06\x50"
                            rb"\xff\x76\x0c\xff\x76\x0a\xff\x76\x0e", re.S), 0x0A),
)

HELPER_SITE = """
site{n}:
    push di
    mov di, {k}
    CALLN rewrite
    pop di
    .byte {displaced}
    .byte 0xea
    .word {back}
seg{n}:
    .word 0
"""

HELPER_REWRITE = """
rewrite:
    push ax
    push cx
    push dx
    push si
    mov dx, cs
    add dx, {paras}
    cmp word ptr ss:[bp + di + 2], dx
    jne rw_done
    mov ax, word ptr ss:[bp + di]
    mov cx, word ptr cs:[{table}]
    mov si, {table} + 2
rw_find:
    jcxz rw_done
    cmp ax, word ptr cs:[si]
    je rw_hit
    add si, 4
    dec cx
    jmp rw_find
rw_hit:
    mov ax, word ptr cs:[si + 2]
    mov word ptr ss:[bp + di], ax
    mov word ptr ss:[bp + di + 2], cs
rw_done:
    pop si
    pop dx
    pop cx
    pop ax
    .byte 0xc3
"""


def _asm16(src, org, names):
    lines, calls = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("CALLN "):
            tag = "__call%d" % len(calls)
            calls.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org,
                      [t for t, _x in calls] + sorted({x for _t, x in calls} | set(names)))
    code = bytearray(code)
    for tag, target in calls:
        at = addr[tag] - org
        code[at:at + 3] = b"\xe8" + ((addr[target] - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("GAME.EXE: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def patch_program(exe, english):
    """GAME.EXE with its strings' English: english {DGROUP offset: bytes} (see the module's docstring)."""
    hdr, rel_at, img, fixups = _exe(exe)
    dg = dgroup(exe)
    fixset = set()
    for f in fixups:
        fixset |= {f, f + 1}
    sites = []
    for name, sig, k in SITES:
        found = list(sig.finditer(bytes(img[:dg * 16])))
        if len(found) != 1:
            raise SystemExit("GAME.EXE: the %s's signature is found %d times, not once" % (name, len(found)))
        a, e = found[0].span(1)
        if e - a < 5 or any(p in fixset for p in range(a, e)):
            raise SystemExit("GAME.EXE: the %s's place is not laid out as expected" % name)
        seg = max(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v * 16 <= a)
        sites.append((name, a, e, k, seg))
    # the helper's segment: its code, the table (count, then offset / English place), the English
    entries = sorted(english.items())

    def source(table, paras):
        src = "".join(HELPER_SITE.format(n=n, k=hex(k), displaced=", ".join(hex(c) for c in img[a:e]),
                                         back=hex(e - seg * 16))
                      for n, (_name, a, e, k, seg) in enumerate(sites))
        return src + HELPER_REWRITE.format(table=hex(table), paras=hex(paras))
    names = ["site%d" % n for n in range(len(sites))] + ["seg%d" % n for n in range(len(sites))]
    code, _a = _asm16(source(0x1000, 0x100), 0, names)
    table_at = len(code)
    body = bytearray(struct.pack("<H", len(entries)))
    text = bytearray()
    text_at = table_at + 2 + 4 * len(entries)
    for off, en in entries:
        body += struct.pack("<HH", off, text_at + len(text))
        text += en + b"\0"
    size = table_at + len(body) + len(text)
    paras = -(-size // 16)
    if size > 0xFFF0:
        raise SystemExit("GAME.EXE: the program's English takes %d bytes, more than a segment holds" % size)
    code, addr = _asm16(source(table_at, paras), 0, names)
    if len(code) != table_at:
        raise SystemExit("GAME.EXE: the helper's length changed")
    room = code + bytes(body) + bytes(text)
    # each site: jmp far helper:site (the segment word a new relocation entry)
    for n, (_name, a, e, _k, _seg) in enumerate(sites):
        img[a:e] = b"\xea" + struct.pack("<HH", addr["site%d" % n], dg) + b"\x90" * (e - a - 5)
    out = bytearray(_move_up(exe, hdr, img, fixups, rel_at, dg, paras, room, "GAME.EXE"))
    # (the helper's jumps back name their code segments: set after the move, those segments did not move)
    for n, (_name, _a, _e, _k, seg) in enumerate(sites):
        struct.pack_into("<H", out, hdr + dg * 16 + addr["seg%d" % n], seg)
    new_rel = [(a + 3 - seg * 16, seg) for (_n, a, _e, _k, seg) in sites] + \
        [(addr["seg%d" % n], dg) for n in range(len(sites))]
    nrel = struct.unpack_from("<H", out, 6)[0]
    if rel_at + 4 * (nrel + len(new_rel)) > hdr:
        raise SystemExit("GAME.EXE: no room in the header for the new relocation entries")
    for j, (o, sg) in enumerate(new_rel):
        struct.pack_into("<HH", out, rel_at + 4 * (nrel + j), o, sg)
    struct.pack_into("<H", out, 6, nrel + len(new_rel))
    return bytes(out)
