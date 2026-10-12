"""ZyX's engine (PC-98: Ikazuchi no Senshi Raidy 2, ZVA98.EXE): its archives, scripts and text.

Archives (ZSD00 the scripts; ZEG00, ZMZ00, MOG00 ... the same layout): a word, the directory's size
in bytes, then 16-byte entries (a name of 12 bytes, NUL-padded, and a dword offset from the file's
start), the last with an empty name and the file's end.

A script (NAME.ZSD) is loaded at the start of a segment of its own (64 KB) and run from the
big-endian word at its start, the code's offset; the words between are its labels (big-endian,
from the code's start).  A statement is a byte (the op); ZVA98.EXE's main loop finds the next one
from a table of lengths (one byte for each op) or, for about 40 ops, a routine (a string ended by
NUL, a message, a list ...), and its dispatcher runs the op by its high nibble's table.  28h hi lo
goes to label hi lo, 2Bh hi lo calls it (91h returns); 92h returns to a place the game saved (the
bytes after it run only through a label).  Nothing else in a script is an address, so a script
may grow when its labels move with it.

A message (op 70h; 71h with 4 bytes first) is a run of commands up to a 00 (or a byte from 0Eh
up, which is the next op): 01 c the colour, 02 a key and a new page, 03, 05, 06 a new line, 04 n,
07 n, 08 n, 0B n the window, 0C n a name, 09 / 0A x y z an inserted name or number, 0D ..., and FF
then text up to a NUL.  Text: a byte below 80h is a character from the program's table (02h
"、", 04h "・", 09h/0Ah "「」", hiragana and katakana; 20h is skipped), 80h and up the lead of a
Shift-JIS pair.  The window draws each character 16 dots wide from the kanji ROM, breaks the line
at its right edge and, past its bottom, waits for a key and starts over.

English (`patch_exe`): 80h (not a character) turns half-width letters on and off: between two 80h,
a byte is an ASCII letter, drawn 8 dots wide from the ROM's ANK font through the program's own
drawing (its colour and outline effects, its delay between letters); at a space the line is
broken when the next word would pass the window's edge, with the program's own new line (and new
page).  The helper goes in at the end of the code segment, the segments after it moved up.
"""
import re
import struct

from .adl import _asm16
from .adl5 import _move_up

SCRIPT_MAX = 0xFFFF


# ---- archives ---------------------------------------------------------------------------------

def members(arc):
    """[(name, data)]"""
    n = struct.unpack_from("<H", arc, 0)[0] // 16
    ents = [(arc[2 + 16 * k:14 + 16 * k].split(b"\x00")[0].decode("ascii"), struct.unpack_from("<I", arc, 14 + 16 * k)[0])
            for k in range(n)]
    if ents[-1][0] or ents[-1][1] != len(arc):
        raise ValueError("archive: the directory does not end at the file's end")
    return [(name, arc[a:ents[k + 1][1]]) for k, (name, a) in enumerate(ents[:-1])]


def archive(items):
    """The archive of [(name, data)] (the same directory layout)."""
    head = 2 + 16 * (len(items) + 1)
    out, at = bytearray(struct.pack("<H", 16 * (len(items) + 1))), head
    for name, data in items:
        out += name.encode("ascii").ljust(12, b"\x00") + struct.pack("<I", at)
        at += len(data)
    out += bytes(12) + struct.pack("<I", at)
    for name, data in items:
        out += data
    return bytes(out)


# ---- members coded (Ring Out!!'s ZVA21F.EXE: a member starting with a zero word is decoded) -----------

CODED = (b"\x95\x97", b"\x97\xd1", b"\x89\xce")


def _decode(raw):
    """A coded file's bytes: its first word says how (9597h each byte rotated right twice, 97D1h each
    byte inverted, 89CEh XORed with the byte after it)."""
    head = raw[:2]
    if head == b"\x95\x97":
        return bytes(((b >> 2) | (b << 6)) & 0xFF for b in raw[2:])
    if head == b"\x97\xd1":
        return bytes(b ^ 0xFF for b in raw[2:])
    if head == b"\x89\xce":
        k = raw[2]
        return bytes(b ^ k for b in raw[3:])
    raise ValueError("a coded file of an unknown kind (%s)" % head.hex())


def script_data(member):
    """A script as the program runs it: a member whose first word is 0 is coded after its fourth
    byte (the program decodes it when it loads it); one written back is written plain."""
    if member[:2] == b"\x00\x00":
        return _decode(member[4:])
    return member


# ---- the speakers' names (a coded member op 19h n "NAME" loads) -------------------------------------

def _encode(head, dec):
    if head == b"\x95\x97":
        return head + bytes(((b << 2) | (b >> 6)) & 0xFF for b in dec)
    if head == b"\x97\xd1":
        return head + bytes(b ^ 0xFF for b in dec)
    raise ValueError("a coded file of an unknown kind (%s)" % head.hex())


def name_tables(members_):
    """{member: the least n of the ops 19h n "STEM" that load it} (the names are copied 2n + 1 bytes
    apart, so a name may take 2n)."""
    out = {}
    names_ = {n.rsplit(".", 1)[0].encode("ascii"): n for n, m in members_ if m[:2] in CODED}
    for _n, m in members_:
        try:
            d = script_data(m)
        except ValueError:
            continue
        if not is_script(d):
            continue
        for x in re.finditer(rb"\x19(.)([A-Z0-9_]+)\x00", d, re.S):
            name = names_.get(x.group(2))
            if name:
                out[name] = min(out.get(name, 255), x.group(1)[0])
    return out


def names(d):
    """(the names (Shift-JIS, ended by NUL in the file), the rest (1Ah ...), the coding's word)"""
    dec = _decode(d)
    end = dec.index(0x1A)
    return dec[:end].split(b"\x00")[:-1], dec[end:], d[:2]


def names_file(items, tail, head):
    return _encode(head, b"".join(n + b"\x00" for n in items) + tail)


# ---- the program: its tables ---------------------------------------------------------------------

LEN_SIG = re.compile(rb"\x32\xe4\xbb(..)\x03\xd8\x2e\x8a\x07\x32\xe4\x03\xf0", re.S)
SPEC_SIG = re.compile(rb"\xbb(..)\x32\xf6\x2e\x8a\x17\x43\xfe\xc6\x0a\xd2\x74.\x3a\xc2\x75.\xfe\xce\x8a\xde"
                      rb"\x32\xff\x03\xdb\x81\xc3(..)\x2e\x8b\x17\xf8\xc3", re.S)
KANA_SIG = re.compile(rb"\x8a\xde\x32\xff\xd1\xe3\x81\xc3(..)\x2e\x8a\x37\x2e\x8a\x57\x01", re.S)

# the main loop's routines for an op, by their code (call/jump targets masked): what they skip
KINDS = {
    "ac 0ac0 j* ac c3": "str1",                     # op, a string, NUL, a byte
    "ac 0ac0 j* ac 3c02 j* ad ad c3": "str_b4",     # op, a string, NUL, b, 4 more when b >= 2
    "ac ac ac 3cff j* ac 32e4 03f0 j*": "recs",     # op, a byte, records (key, n, n bytes) to FF
    "ac ac 0ac0 j* 3c01 j* 3c04 j* 3c07 j* 3c08 j* 3c09": "msg",
    "83c605 j*": "msg5",                            # 4 bytes, then a message
    "83c602 ac 0ac0 j* c3": "skip2_nul",
    "ac 0ac0 j* c3": "nul",
    "c* ac c3": "str1+1",
    "c* 83c606 c3": "str1+6",
    "c* 83c603 c3": "str1+3",
    "c* 83c605 c3": "str1+5",
    "83c60d j*": "13+str1",
    "83c603 j*": "3+str1",
    "ac ad 803c04 j* 83c603 j*": "triples",
    "83c606 ac 3cff j* 0ac0 j* fec8 j* j*": "list99",
    "83c605 ac 0ac0 j* 3c01 j* 46 j*": "list76",
    "ac ad f6e4 f60402 j* 03c0 40 03f0 j*": "grid",
    "ad c* j*": "2+str1",
    "26803e693000 j* 268b366530 8bee j*": "one",    # back to a loop's start
}


def _fingerprint(cs, a):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    out = []
    for i in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(cs[a:a + 24]), a):
        out.append(i.mnemonic[0] + "*" if i.mnemonic in ("call", "jmp") or i.mnemonic.startswith("j")
                   else bytes(i.bytes).hex())
        if i.mnemonic in ("ret", "jmp"):
            break
    return " ".join(out)


class Program:
    """ZVA98.EXE's tables: op lengths, the ops with routines (and what they skip), the characters."""

    def __init__(self, exe):
        self.exe = exe
        self.hdr = struct.unpack_from("<H", exe, 8)[0] * 16
        cs = exe[self.hdr:]
        self.cs = cs
        m = [p.search(cs) for p in (LEN_SIG, SPEC_SIG, KANA_SIG)]
        if not all(m):
            raise ValueError("ZVA98.EXE: the op tables or the character table not found")
        at = struct.unpack("<H", m[0].group(1))[0]
        self.len = cs[at:at + 0xF0]
        lst = struct.unpack("<H", m[1].group(1))[0]
        tab = struct.unpack("<H", m[1].group(2))[0]
        ops = cs[lst:cs.index(b"\x00", lst)]
        self.kind = {}
        for k, op in enumerate(ops):
            r = struct.unpack_from("<H", cs, tab + 2 * k)[0]
            if cs[r] == 0xE8:
                r = (r + 3 + struct.unpack_from("<h", cs, r + 1)[0]) & 0xFFFF
            fp = _fingerprint(cs, r)
            if fp.startswith("268936") or (fp.startswith("26803e") and "2689" in fp):
                self.kind[op] = "fixed"         # (a loop's start: noted, then its length)
            elif fp.startswith("26803e") and "268b36" in fp:
                self.kind[op] = "one"           # (back to a loop's start)
            elif fp in KINDS:
                self.kind[op] = KINDS[fp]
            else:
                raise ValueError("ZVA98.EXE: op %02x's routine not known (%s)" % (op, fp))
        kana = struct.unpack("<H", m[2].group(1))[0]
        self.kana = [cs[kana + 2 * b:kana + 2 * b + 2].decode("cp932", "replace") for b in range(0x80)]

    def step(self, d, i):
        """(the next op, [(start, end) of text runs]) for the op at i."""
        op = d[i]
        k = self.kind.get(op)
        if k is None:
            if op in (0x28, 0x2B):
                return i + 3, []
            if op == 0x92:
                return i + 1, []
            if not self.len[op] if op < len(self.len) else True:
                raise ValueError("op %02x of no length at %x" % (op, i))
            return i + self.len[op], []
        if k == "str1":
            return _nul(d, i) + 1, []
        if k == "str_b4":
            j = _nul(d, i)
            return j + 1 + (4 if d[j] >= 2 else 0), []
        if k == "recs":
            j = i + 2
            while d[j] != 0xFF:
                j += 2 + d[j + 1]
            return j + 1, []
        if k == "msg":
            return message(d, i + 1)
        if k == "msg5":
            return message(d, i + 5)
        if k == "fixed":
            return i + self.len[op], []
        if k == "one":
            return i + 1, []
        if k == "skip2_nul":
            return _nul(d, i + 2), []
        if k == "nul":
            return _nul(d, i), []
        if k.startswith("str1+"):
            return _nul(d, i) + 1 + int(k[5:]), []
        if k.endswith("+str1"):
            return _nul(d, i + int(k.split("+")[0])) + 1, []
        if k == "triples":
            j = i + 3
            while d[j] != 4:
                j += 3
            return j + 1, []
        if k == "list99":
            j = i + 6
            while True:
                b = d[j]
                j += 1
                if b == 0xFF:
                    return j, []
                j += 2 if b == 0 else 3 if b == 1 else 5
        if k == "list76":
            j = i + 5
            while True:
                b = d[j]
                j += 1
                if b == 0:
                    return j, []
                if b == 1:
                    j += 1
                    continue
                while d[j] >= 0xA:
                    j += 1
        if k == "grid":
            n = d[i + 2] * d[i + 3]
            if d[i + 4] & 2:
                n *= 2
            return i + 4 + n + 1, []
        raise ValueError(k)

    def decode(self, raw):
        """A text run as on screen."""
        out, i = "", 0
        while i < len(raw):
            b = raw[i]
            if b >= 0x80:
                out += raw[i:i + 2].decode("cp932", "replace")
                i += 2
            else:
                if b != 0x20:
                    out += self.kana[b]
                i += 1
        return out


def _nul(d, i):
    """The byte after the first NUL from i."""
    return d.index(0, i) + 1


def message(d, i):
    """(the end of the message whose commands start at i, its text runs)"""
    runs = []
    while True:
        b = d[i]
        i += 1
        if b == 0:
            return i, runs
        if b in (1, 4, 7, 8, 0xB, 0xC):
            i += 1
        elif b in (9, 0xA):
            i += 3
        elif b == 0xD:
            while True:
                c = d[i]
                i += 1
                if c == 0xA:
                    i += 4
                    break
                if c == 0:
                    break
        elif b == 0xFF:
            e = d.index(0, i)
            runs.append((i, e))
            i = e + 1
        elif b >= 0xE:
            return i - 1, runs


FLOW_END = {0xFF, 0x92, 0x28, 0x91, 0x15}


def code_start(d):
    return struct.unpack_from(">H", d, 0)[0]


def is_script(d):
    return len(d) > 2 and 2 <= code_start(d) < len(d) and code_start(d) % 2 == 0


def labels(d):
    c = code_start(d)
    return [c + struct.unpack_from(">H", d, k)[0] for k in range(2, c, 2)]


def runs(prog, d):
    return walk(prog, d)[0]


def menus(prog, d):
    """[(first, end)] of the choice menus: from an op 72h n (n not 0) to the next 72h 00; the text
    runs between are the menu's items, drawn in its box."""
    ops = walk(prog, d)[1]
    out, start = [], None
    for i in sorted(ops):
        if d[i] == 0x72:
            if d[i + 1]:
                start = i
            elif start is not None:
                out.append((start, i))
                start = None
    return out


def walk(prog, d):
    """[(start, end)] of every text run, the script walked from its start and every label.  Past a
    jump or return the walk goes on while its bytes are statements (a jump a statement before skips
    is followed by more code), its text runs kept when it reaches a label, a place walked already
    or the script's end, and dropped when it meets bytes that are no statement (dead bytes before
    the next label)."""
    c = code_start(d)
    seen, out, ops = set(), set(), set()
    starts = set(labels(d))
    for s in [c] + labels(d):
        if s >= len(d):
            continue
        if s > c and d[s - 1] == 0xFF and s not in seen:
            # (a label at a text run: the game draws from it)
            e = d.index(0, s)
            out.add((s, e))
            seen.update(range(s, e + 1))
            continue
        i, guess, pending, covered = s, False, [], []
        while i < len(d):
            if i in seen or (guess and i in starts):
                break
            op = d[i]
            if op == 0xFF:
                seen.add(i)
                break
            try:
                j, t = prog.step(d, i)
            except (ValueError, IndexError):
                if guess:
                    pending, covered = [], []
                    break
                raise ValueError("a statement not understood at %x" % i)
            if guess:
                pending += t
                covered.append((i, j))
            else:
                seen.update(range(i, j))
                out.update(t)
                ops.add(i)
            if op in FLOW_END:
                guess = True
            i = j
        out.update(pending)
        for a, b in covered:
            seen.update(range(a, b))
            ops.add(a)
    return sorted(out), ops


def rebuild(d, values):
    """The script with its text runs replaced ({start: bytes}), its labels moved with them."""
    c = code_start(d)
    edits = sorted(values.items())
    ends = {s: d.index(0, s) for s, _b in edits}
    out, at, shift = bytearray(), 0, []
    for s, b in edits:
        out += d[at:s] + b
        shift.append((s, len(b) - (ends[s] - s)))
        at = ends[s]
    out += d[at:]

    def moved(p):
        return p + sum(dd for s, dd in shift if s < p)
    for k in range(2, c, 2):
        old = c + struct.unpack_from(">H", d, k)[0]
        if old < len(d):        # (an unused label, FFFFh, stays as it is)
            if moved(old) - c > 0xFFFF:
                raise OverflowError("a label past 64 KB")
            struct.pack_into(">H", out, k, moved(old) - c)
    return bytes(out)


# ---- the program: the patch -------------------------------------------------------------------------

HOOK_SIG = re.compile(rb"\x80\xfe\x20\x74(.)\x80\xfe\x80\x73(.)\x8a\xde\x32\xff\xd1\xe3", re.S)
DRAW_SIG = re.compile(rb"\xa0(..)\x32\xe4\xbf(..)\x03\xf8\x8b\x05\x52\xe8(..)\x5a\x8b\x5d\x02\xe8(..)\x8b\xf8"
                      rb"\x8a\x0e(..)\xe8(..)\x80\x3e(..)\x00\x75.\xb0\x0c\xe8(..)\x0a\xc0\x75.\xb8\x0e\x04\xcd\x18"
                      rb"\xf6\xc4\x04\x75.\xb4\x05\xcd\x33\xb2\x01\xa8\x03\x75.\xe8(..)\xa8\x10\x75.\xb2\x03\x8a\xc2"
                      rb"\xe8(..)\xe8(..)", re.S)
GLYPH_SIG = re.compile(rb"\x53\x56\x57\x55\x1e\x06\xb8(..)\x8e\xd8\x8e\xc0\xe8(..)\xe8(..)\xe8(..)\xe8(..)\x32\xe4"
                       rb"\xa0(..)\xfa\xe8(..)\xbe(..)\xe8(..)\xe8(..)\xfb", re.S)
NEWLINE_SIG = re.compile(rb"\x83\x45\x02\x14\xe8(..)\x8b\x45\x04\x89\x05\xc3", re.S)
PLACED_SIG = re.compile(rb"\x80\x3e(..)\x00\x74.\x8b\x3e(..)\x8a\x0e", re.S)
# the speakers' names' loop: lodsb, Shift-JIS pairs, 20h half a cell, 0Dh a new line
PLATE_SIG = re.compile(rb"\xac\x8a\xf0\x0a\xf6\x74.\x3c\x20\x75\x03\x47\xeb.\x3c\x0d", re.S)

HELPER = """
hook:
    cmp dh, 0x80
    jne h1
    xor byte ptr cs:[{mode}], 1
    JMPN {loop}
h1:
    test byte ptr cs:[{mode}], 1
    jnz half
    cmp dh, 0x20
    jne h2
    JMPN {loop}
h2:
    cmp dh, 0x80
    jb h3
    JMPN {sjis}
h3:
    JMPN {kana}
half:
    cmp byte ptr [{placed}], 0
    je hnorm
    mov di, word ptr [{placedat}]
    CALLN ank
    inc word ptr [{placedat}]
    JMPN {loop}
hnorm:
    mov al, byte ptr [{win}]
    xor ah, ah
    mov bx, {curs}
    add bx, ax
    cmp dh, 0x20
    jne hfit
    push si
    xor cx, cx
mw:
    mov al, byte ptr es:[si]
    cmp al, 0x21
    jb mwe
    cmp al, 0x80
    je mwe
    inc cx
    inc si
    jmp mw
mwe:
    pop si
    shl cx, 1
    shl cx, 1
    shl cx, 1
    add cx, word ptr [bx]
    add cx, 8
    cmp cx, word ptr [bx + 8]
    jbe hfit
    CALLN nl
    JMPN {loop}
hfit:
    mov ax, word ptr [bx]
    add ax, 7
    cmp ax, word ptr [bx + 8]
    jb hdraw
    CALLN nl
hdraw:
    cmp dh, 0x20
    je hadv
    push bx
    mov ax, word ptr [bx]
    mov bx, word ptr [bx + 2]
    CALLN {vram}
    mov di, ax
    CALLN ank
    pop bx
hadv:
    add word ptr [bx], 8
    CALLN delay
    JMPN {loop}
nl:
    add word ptr [bx + 2], 0x14
    push di
    mov di, bx
    CALLN {page}
    pop di
    mov ax, word ptr [bx + 4]
    mov word ptr [bx], ax
    .byte 0xc3
plate:
    cmp al, 0x80
    jne p1
    xor byte ptr cs:[{mode}], 1
    JMPN {ploop}
p1:
    test byte ptr cs:[{mode}], 1
    jz p2
    cmp al, 0x20
    je p3
    CALLN ank
p3:
    inc di
    JMPN {ploop}
p2:
    cmp al, 0x20
    jne p4
    inc di
    JMPN {ploop}
p4:
    JMPN {pnext}
ank:
    push ds
    mov ds, word ptr cs:[{dsimm}]
    push bx
    push cx
    push si
    push di
    push es
    push ds
    pop es
    mov al, 0x0b
    out 0x68, al
    xor al, al
    out 0xa1, al
    mov al, dh
    out 0xa3, al
    mov bx, {buf}
    xor cx, cx
ak1:
    mov al, cl
    or al, 0x20
    out 0xa5, al
    in al, 0xa9
    mov byte ptr [bx], al
    mov byte ptr [bx + 1], 0
    add bx, 2
    inc cx
    cmp cx, 16
    jb ak1
    mov al, 0x0a
    out 0x68, al
    CALLN {fx1}
    CALLN {fx2}
    xor ah, ah
    mov al, byte ptr [{colour}]
    cli
    CALLN {grcg}
    mov si, {buf}
    CALLN {blit}
    CALLN {grcgoff}
    sti
    pop es
    pop di
    pop si
    pop cx
    pop bx
    pop ds
    .byte 0xc3
delay:
    cmp byte ptr [{fast}], 0
    jne dl9
    mov al, 0x0c
    CALLN {keyq}
    or al, al
    jne dl3
    mov ax, 0x40e
    int 0x18
    test ah, 4
    jne dl9
    mov ah, 5
    int 0x33
    mov dl, 1
    test al, 3
    jne dl1
    CALLN {joy}
    test al, 0x10
    jne dl1
dl3:
    mov dl, 3
dl1:
    mov al, dl
    CALLN {wait1}
    CALLN {wait2}
dl9:
    .byte 0xc3
"""
ROOM_PARAS = 0x30


def _rel(at, g):
    """The target of a jump or call whose rel8/rel16 (g) ends at `at`."""
    return (at + struct.unpack("<b" if len(g) == 1 else "<h", g)[0]) & 0xFFFF


def patch_exe(exe):
    """ZVA98.EXE with the helper (see the module's docstring)."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytearray(exe[hdr:])
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 0x18)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    if struct.unpack_from("<H", exe, 0x16)[0] != 0:
        raise SystemExit("ZVA98.EXE: its code is not the first segment")
    segs = sorted({struct.unpack_from("<H", img, f)[0] for f in fixups})
    split_seg = min(s for s in segs if s > 0)
    split = split_seg * 16
    seg = img[:split]
    found = [list(p.finditer(seg)) for p in (HOOK_SIG, DRAW_SIG, GLYPH_SIG, NEWLINE_SIG, PLACED_SIG, PLATE_SIG)]
    if any(len(f) != 1 for f in found):
        raise SystemExit("ZVA98.EXE: the patch sites are found %s times, once each expected" % [len(f) for f in found])
    hm, dm, gm, nm, pm, lm = (f[0] for f in found)
    km = KANA_SIG.search(seg)
    u = lambda g: hex(struct.unpack("<H", g)[0])      # noqa: E731
    h0, d0, g0 = hm.start(), dm.start(), gm.start()
    at = split
    mode = at + ROOM_PARAS * 16 - 2
    src = HELPER.format(
        mode=hex(mode), loop=hex(_rel(h0 + 5, hm.group(1))), sjis=hex(_rel(h0 + 10, hm.group(2))),
        kana=hex(h0 + 10), placed=u(pm.group(1)), placedat=u(pm.group(2)),
        win=u(dm.group(1)), curs=u(dm.group(2)), vram=hex(_rel(d0 + 23, dm.group(4))), colour=u(gm.group(6)),
        fast=u(dm.group(7)), keyq=hex(_rel(d0 + 44, dm.group(8))), joy=hex(_rel(d0 + 71, dm.group(9))),
        wait1=hex(_rel(d0 + 82, dm.group(10))), wait2=hex(_rel(d0 + 85, dm.group(11))),
        page=hex(_rel(nm.start() + 7, nm.group(1))),
        fx1=hex(_rel(g0 + 22, gm.group(4))), fx2=hex(_rel(g0 + 25, gm.group(5))),
        grcg=hex(_rel(g0 + 34, gm.group(7))), buf=u(gm.group(8)), blit=hex(_rel(g0 + 40, gm.group(9))),
        grcgoff=hex(_rel(g0 + 43, gm.group(10))), dsimm=hex(g0 + 7),
        ploop=hex(lm.start()), pnext=hex(lm.start() + 14))
    code, labs = _asm16(src, at, ("hook", "plate"))
    if len(code) > ROOM_PARAS * 16 - 2:
        raise SystemExit("ZVA98.EXE: the helper is %d bytes, its room %d" % (len(code), ROOM_PARAS * 16 - 2))
    if km is None or km.start() != h0 + 10:
        raise SystemExit("ZVA98.EXE: the character routine not where it was expected")
    seg[h0:h0 + 10] = b"\xe9" + struct.pack("<H", (labs["hook"] - (h0 + 3)) & 0xFFFF) + b"\x90" * 7
    p0 = lm.start() + 7
    seg[p0:p0 + 7] = b"\xe9" + struct.pack("<H", (labs["plate"] - (p0 + 3)) & 0xFFFF) + b"\x90" * 4
    img[:split] = seg
    return _move_up(exe, hdr, img, fixups, rel_at, split_seg, ROOM_PARAS, code, "ZVA98.EXE")


# ---- English ----------------------------------------------------------------------------------------

SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3", "　": " "}


def encode(text):
    """English as a text run's bytes: ASCII between two 80h (half-width); another character in
    Shift-JIS when it has one (full-width), else "?"."""
    out, half = bytearray(), False
    for c in "".join(SUBST.get(c, c) for c in text):
        if c == "\n":
            c = " "
        if 0x20 <= ord(c) < 0x7F:
            if not half:
                out.append(0x80)
                half = True
            out.append(ord(c))
            continue
        try:
            b = c.encode("cp932")
        except UnicodeEncodeError:
            b = b"?"
        if len(b) == 2 and b[0] >= 0x81:
            if half:
                out.append(0x80)
                half = False
            out += b
        else:
            if not half:
                out.append(0x80)
                half = True
            out += b"?"
    if half:
        out.append(0x80)
    return bytes(out)
