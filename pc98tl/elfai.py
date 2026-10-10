"""Elf's early AI engine (PC-98: De-Ja, 1990): AI.EXE and its MES scripts.

A MES file is run from its first byte, loaded at DS:2000h (the word at DS:1A5Fh); the engine finds a
block's end by counting braces, so nothing in a script is an address and a script may grow and
shrink.  Its tokens (as the engine reads them when it skips a block):

* 81h-98h xx: a Shift-JIS character, drawn full-width; "％" (81 93) starts a new line.  A kanji with
  a lead byte from E0h is never in a script: C0h-EFh are dictionary codes.
* 22h ... 22h: a string: a file name as an argument; in a statement's place it is drawn a byte to a
  half-width letter.
* 00h-1Fh: a number: x & 7 not 0: (x & 7) - 1; 10h n: n; 18h hi lo: the word.
* 99h-BFh: a statement (op), its arguments expressions (numbers, variables 40h-5Ah, operators),
  strings and blocks { ... } joined by ",": A1 {items, ...} a menu; A4 n,{...} a dictionary entry
  (code C0h + n runs it in place); A6 waits for a key; A7 l,t,r,b the text window (columns 0-79,
  rows in dots); A8 x,y the cursor; A9 c the colour; AA clears the window; AC v draws the text a
  variable points to (the hero's names, kept as text ended by "}"); B1 v,{...} sets such a text (the
  Shift-JIS pairs and string bytes in it, ended by the number after them); 9B @,i,v sets a system
  word (i = 5: the line height); 9D cond={...},{...} an if; A2/A3 "x.mes" jump to or call a script.
* C0h-EFh: a dictionary entry, run in place.

The text window draws a character at the cursor and moves it on, starting a new line at the window's
right edge and the window over at its top when a line would pass the bottom (no new page).  A
script's own messages wait (A6) and clear (AA) themselves.

Pictures are loaded where the script is (the engine reads the script again after one); the
animations (9B @,30-33: DS:8000h and up, set by START.MES; SAIGO.MES lower) and the music (DS:B000h)
are loaded above it, so a script may take ROOM bytes, or less where it names a lower buffer.

English (`patch_exe`): AI.EXE is unpacked from EXEPACK and given a helper at the end of its code:
statement BBh (unused) followed by a number draws a line of half-width letters from the English
segment (64 KB past the program's memory, which it grows by as much) at that offset, a byte to a
letter, as a string is drawn; when a script is loaded, NAME.ENG next to it is read into the segment
(scripts without English have none).
"""
import re
import struct

from . import exepack
from .adl import _asm16

ROOM = 0x8000 - 0x2000           # up to the first animation buffer START.MES sets
BUFFER_END = 0xC302              # the engine's variables
NAME_CELLS = 12                  # a hero's name: six full-width characters (KPUT.COM's limit)
ITEM_CELLS = 14                  # a menu's box
FAR = 0xBB                       # the helper's statement
OPS = range(0x99, 0xC0)
DICT = range(0xC0, 0xF0)
NEWLINE = b"\x81\x93"            # ％
OPERATORS = b"|\\^<=>!#%&*+-/"


def tokens(d):
    """[(kind, start, end)]: "sj" (a Shift-JIS pair), "str", "num", "byte"."""
    out, i = [], 0
    while i < len(d):
        b = d[i]
        if 0x81 <= b <= 0x98:
            n = 2
            kind = "sj"
        elif b == 0x22:
            n = d.index(0x22, i + 1) + 1 - i
            kind = "str"
        elif b < 0x20:
            n = 1 if b & 7 else (2 if not b & 8 else 3)
            kind = "num"
        else:
            n, kind = 1, "byte"
        out.append((kind, i, i + n))
        i += n
    return out


def numval(d, tok):
    kind, a, b = tok
    x = d[a]
    if x & 7:
        return (x & 7) - 1
    return d[a + 1] if b - a == 2 else (d[a + 1] << 8) | d[a + 2]


def number(v):
    """A number's bytes."""
    if v < 7:
        return bytes([0x11 + v])
    if v < 0x100:
        return bytes([0x10, v])
    return bytes([0x18, v >> 8, v & 0xFF])


def is_expr_byte(b):
    return b < 0x20 or b == 0x3F or 0x40 <= b <= 0x5A or b in OPERATORS


class Script:
    """A script's tokens, its dictionary, its blocks' openers and its text runs."""

    def __init__(self, d):
        self.d = d
        self.t = t = tokens(d)
        n = len(t)
        self.close = {}
        self.opener = {}
        stack = []
        last_op, last_closed = None, None
        for k, (kind, a, b) in enumerate(t):
            c = d[a] if kind == "byte" else None
            if kind == "byte" and c in OPS:
                last_op = (k, c)
            if c == 0x7B:
                prev = t[k - 1] if k else None
                if prev and prev[0] == "byte" and d[prev[1]] == 0x2C and k >= 2 and \
                        t[k - 2][0] == "byte" and d[t[k - 2][1]] == 0x7D and last_closed is not None:
                    op = self.opener[last_closed]            # (an else block: its if's)
                else:
                    op = last_op
                stack.append(k)
                self.opener[k] = op
            elif c == 0x7D and stack:
                o = stack.pop()
                self.close[o] = k
                last_closed = o
        # the dictionary: A4 n , { body }
        self.entries = {}                   # token index of the A4 -> (code, first body token, end)
        for k, (kind, a, b) in enumerate(t):
            if kind == "byte" and d[a] == 0xA4 and k + 3 < n and t[k + 1][0] == "num" \
                    and d[t[k + 2][1]] == 0x2C and d[t[k + 3][1]] == 0x7B:
                o = k + 3
                self.entries[k] = (0xC0 + numval(d, t[k + 1]), o + 1, self.close[o])
        self.code_entry = {}
        for k, (code, s, e) in sorted(self.entries.items()):
            if code in self.code_entry:
                raise ValueError("dictionary code %02x defined twice" % code)
            self.code_entry[code] = (s, e)
        # text entries: Shift-JIS, text entries, AC v only
        text = set(self.code_entry)
        while True:
            keep = {c for c in text if self._plain(*self.code_entry[c], text)}
            if keep == text:
                break
            text = keep
        self.text_codes = text
        self.defs = {}                      # body token range of a text entry's definition
        for k, (code, s, e) in self.entries.items():
            if code in text:
                self.defs[s] = e

    def _plain(self, s, e, text):
        d, t = self.d, self.t
        k = s
        while k < e:
            kind, a, b = t[k]
            if kind == "sj" or (kind == "byte" and d[a] in text):
                k += 1
            elif kind == "byte" and d[a] == 0xAC and k + 1 < e and 0x40 <= d[t[k + 1][1]] <= 0x5A:
                k += 2
            else:
                return False
        return True

    def texty(self, k):
        """Tokens a text run takes at k: 0 when none."""
        d, t = self.d, self.t
        kind, a, b = t[k]
        if kind == "sj":
            return 1
        if kind == "byte" and d[a] in self.text_codes:
            return 1
        if kind == "byte" and d[a] == 0xAC and k + 1 < len(t) and t[k + 1][0] == "byte" \
                and 0x40 <= d[t[k + 1][1]] <= 0x5A:
            return 2
        return 0

    def block(self, k):
        """The innermost block around token k: its "{" token, or None."""
        best = None
        for o, c in self.close.items():
            if o < k < c and (best is None or o > best):
                best = o
        return best

    def enclosing(self, k):
        """The op opening the innermost block around token k (code), or None."""
        best = self.block(k)
        return self.opener[best][1] if best is not None and self.opener.get(best) else None

    def _commas(self, o):
        """The block opened at token o has "," at its own level (a list: a menu's items)."""
        d, t = self.d, self.t
        depth = 0
        for k in range(o + 1, self.close[o]):
            kind, a, b = t[k]
            if kind != "byte":
                continue
            if d[a] == 0x7B:
                depth += 1
            elif d[a] == 0x7D:
                depth -= 1
            elif d[a] == 0x2C and not depth:
                return True
        return False

    def runs(self):
        """[(first token, end token, kind)] of the text runs (the dictionary's text entries' own
        definitions left out): kind msg, item (in a menu), tag (in a dictionary entry that does more
        than draw text), name (a text B1 sets)."""
        out, k, t = [], 0, self.t
        self.in_entry = set()
        inside = sorted(self.defs.items())
        while k < len(t):
            hit = next((e for s, e in inside if s <= k < e), None)
            if hit is not None:
                k = hit
                continue
            n = self.texty(k)
            if not n:
                k += 1
                continue
            s = k
            while k < len(t) and self.texty(k):
                k += self.texty(k)
            op = self.enclosing(s)
            kind = {0xA1: "item", 0xB1: "name"}.get(op, "msg")
            if op == 0xA4:
                # (in a dictionary entry that does more than draw text: a list is a menu's items, a
                # name in brackets a speaker's tag, else a message drawn after the entry clears the
                # window)
                if self._commas(self.block(s)):
                    kind = "item"
                elif re.fullmatch(r"【[^】]*】", self.render(s, k)):
                    kind = "tag"
                else:
                    self.in_entry.add(s)
            out.append((s, k, kind))
        return out

    def render(self, s, e, depth=0):
        """A run's text as on screen: ％ as a line break, AC v as {N<v - 40h>}."""
        d, t = self.d, self.t
        out, k = "", s
        while k < e:
            kind, a, b = t[k]
            if kind == "sj":
                out += "\n" if d[a:b] == NEWLINE else d[a:b].decode("cp932", "replace")
                k += 1
            elif d[a] == 0xAC:
                out += "{N%d}" % (d[t[k + 1][1]] - 0x40)
                k += 2
            else:
                es, ee = self.code_entry[d[a]]
                if depth > 8:
                    raise ValueError("dictionary entries nested too deep")
                out += self.render(es, ee, depth + 1)
                k += 1
        return out


def text_cells(text):
    """Cells a rendered run takes on one line (a name: NAME_CELLS)."""
    n = 0
    for part in re.split(r"(\{N\d+\})", text):
        if re.fullmatch(r"\{N\d+\}", part):
            n += NAME_CELLS
        else:
            n += sum(2 if ord(ch) > 0x7F and not 0xFF61 <= ord(ch) <= 0xFF9F else 1 for ch in part)
    return n


def room(d):
    """Bytes the script may take: up to the lowest buffer it sets above DS:2000h (9B @,i,v with i 1 or
    30-33: the music's and the animations'; AE "file",v: a file loaded there), ROOM at most."""
    t = tokens(d)
    low = 0x2000 + ROOM

    def byte(k, c):
        return 0 <= k < len(t) and t[k][0] == "byte" and d[t[k][1]] == c
    for k, tok in enumerate(t):
        if tok[0] != "num" or tok[2] - tok[1] != 3:
            continue
        v = numval(d, tok)
        if not 0x2000 < v < BUFFER_END:
            continue
        sysword = byte(k - 1, 0x2C) and t[k - 2][0] == "num" and byte(k - 3, 0x2C) and byte(k - 4, 0x40)             and byte(k - 5, 0x9B) and numval(d, t[k - 2]) in (1, 30, 31, 32, 33)
        loaded = byte(k - 1, 0x2C) and t[k - 2][0] == "str" and byte(k - 3, 0xAE)
        if sysword or loaded:
            low = min(low, v)
    return low - 0x2000


# ---- the program ------------------------------------------------------------------------------

DRAW_SIG = re.compile(rb"\x50\x8b\x1e(..)\x8b\x16(..)\xe8(..)\x8a\x36(..)\x8a\x16(..)\x58\x80\x3e(..)\x00"
                      rb"\x75\x08\xe8(..)\xe8(..)\xeb\x09\xe8(..)\xe8(..)\xe8(..)\x8b\x0e(..)\xe8(..)\xeb", re.S)
DISP_SIG = re.compile(rb"\x8a\x04\x46\x3c\xc0\x72\x07\x3c\xf0\x73\x03\xe9(..)\xb4\x00\x2c\x99", re.S)
DICT_SIG = re.compile(rb"\xe8(..)\x46\x03\xc0\x05(..)\x8b\xd8\x89\x37\xe8(..)\xe9(..)", re.S)
LOAD_SIG = re.compile(rb"\x8b\x1e\x5f\x1a\xe8(..)", re.S)
RESIZE_SIG = re.compile(rb"\xb4\x4a\xbb(..)\xcd\x21", re.S)

HELPER = """
farop:
    CALLN {expr}
    mov word ptr cs:[{ptr}], ax
fo_loop:
    push ds
    mov ax, cs
    add ax, {delta}
    mov ds, ax
    mov bx, word ptr cs:[{ptr}]
    mov al, byte ptr [bx]
    pop ds
    or al, al
    jz fo_done
    inc word ptr cs:[{ptr}]
    push ax
    mov bx, word ptr [{curx}]
    mov dx, word ptr [{cury}]
    CALLN {pos}
    mov dh, byte ptr [{col1}]
    mov dl, byte ptr [{col2}]
    pop ax
    cmp byte ptr [{wide}], 0
    jne fo_wide
    CALLN {draw1}
    CALLN {adv}
    jmp fo_delay
fo_wide:
    CALLN {draw2}
    CALLN {adv}
    CALLN {adv}
fo_delay:
    mov cx, word ptr [{delay}]
    CALLN {wait}
    jmp fo_loop
fo_done:
    JMPN {loop}
dispatch:
    cmp al, {far}
    jne d_not
    JMPN farop
d_not:
    cmp al, 0xc0
    jb disp_tbl
    cmp al, 0xf0
    jae disp_tbl
    JMPN {dictrun}
disp_tbl:
    JMPN {table}
load:
    CALLN {loader}
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    cld
    mov si, {namebuf}
    mov di, {name}
    push cs
    pop es
ld_copy:
    lodsb
    cmp al, 0x2e
    je ld_ext
    or al, al
    je ld_ext
    stosb
    cmp di, {name_end}
    jb ld_copy
ld_ext:
    mov ax, 0x452e
    stosw
    mov ax, 0x474e
    stosw
    xor al, al
    stosb
    push cs
    pop ds
    mov dx, {name}
    mov ax, 0x3d00
    int 0x21
    jc ld_out
    mov bx, ax
    mov ax, cs
    add ax, {delta}
    mov ds, ax
    xor dx, dx
    mov cx, 0xffff
    mov ah, 0x3f
    int 0x21
    mov ah, 0x3e
    int 0x21
ld_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    .byte 0xc3
"""


def _rel(at, g):
    """The target of a near call or jump whose rel16 (g) ends at `at`."""
    return (at + struct.unpack("<h", g)[0]) & 0xFFFF


def patch_exe(packed):
    """AI.EXE unpacked, with the helper (see the module's docstring)."""
    exe = bytearray(exepack.unpack(packed)) if exepack.is_packed(packed) else bytearray(packed)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytearray(exe[hdr:])
    cs = struct.unpack_from("<H", exe, 0x16)[0]
    base = cs * 16
    seg = img[base:]
    found = [list(p.finditer(seg)) for p in (DRAW_SIG, DISP_SIG, RESIZE_SIG)]
    if any(len(f) != 1 for f in found):
        raise SystemExit("AI.EXE: the patch sites are found %s times, once each expected" % [len(f) for f in found])
    dm, sm, rm = (f[0] for f in found)
    # (the dictionary's statement and the menu's share their shape: the expression routine and the
    # statement loop they go to)
    ams = list(DICT_SIG.finditer(seg))
    if not ams or len({(_rel(m.start() + 3, m.group(1)), _rel(m.end(), m.group(4))) for m in ams}) != 1:
        raise SystemExit("AI.EXE: the expression routine not found")
    am = ams[0]
    loads = list(LOAD_SIG.finditer(seg))
    if not loads or len({_rel(m.end(), m.group(1)) for m in loads}) != 1:
        raise SystemExit("AI.EXE: the script loads not found")
    u = lambda g: hex(struct.unpack("<H", g)[0])          # noqa: E731
    a0 = dm.start()
    at = len(seg)                                          # the helper: after the code
    ptr, name = at + 0x200, at + 0x202
    name_end = name + 64
    helper_paras = (0x202 + 72 + 15) // 16
    image_paras = (len(img) + helper_paras * 16 + 15) // 16
    psp_paras = struct.unpack("<H", rm.group(1))[0]       # the memory the program keeps
    eng = max(psp_paras, image_paras + 0x10)               # (the English segment, from the PSP)
    delta = eng - 0x10 - cs
    src = HELPER.format(
        expr=hex(_rel(am.start() + 3, am.group(1))), ptr=hex(ptr), delta=hex(delta),
        curx=u(dm.group(1)), cury=u(dm.group(2)), pos=hex(_rel(a0 + 12, dm.group(3))),
        col1=u(dm.group(4)), col2=u(dm.group(5)), wide=u(dm.group(6)),
        draw1=hex(_rel(a0 + 31, dm.group(7))), adv=hex(_rel(a0 + 34, dm.group(8))),
        draw2=hex(_rel(a0 + 39, dm.group(9))), delay=u(dm.group(12)), wait=hex(_rel(a0 + 52, dm.group(13))),
        loop=hex(_rel(am.end(), am.group(4))), far=hex(FAR),
        dictrun=hex(_rel(sm.start() + 14, sm.group(1))), table=hex(sm.start() + 14),
        loader=hex(_rel(loads[0].end(), loads[0].group(1))), namebuf="0x1a01", name=hex(name),
        name_end=hex(name_end))
    code, labels = _asm16(src, at, ("dispatch", "load"))
    if len(code) > 0x200:
        raise SystemExit("AI.EXE: the helper is %d bytes, its room 512" % len(code))
    # the dispatch: a statement byte goes to the helper first
    s = sm.start() + 3
    seg[s:s + 3] = b"\xe9" + struct.pack("<H", (labels["dispatch"] - (s + 3)) & 0xFFFF)
    for m in loads:
        s = m.end() - 3
        seg[s:s + 3] = b"\xe8" + struct.pack("<H", (labels["load"] - (s + 3)) & 0xFFFF)
    s = rm.start() + 3
    seg[s:s + 2] = struct.pack("<H", eng + 0x1000)
    seg += code + bytes(helper_paras * 16 - len(code))
    img[base:] = seg
    out = bytearray(exe[:hdr]) + img
    size = len(out)
    struct.pack_into("<HH", out, 2, size % 512, (size + 511) // 512)
    return bytes(out)
