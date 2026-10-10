"""D.O.'s ADL engine (ADL.EXE: DOR Part 1 and 2, 1993; addresses below are Part 2's): the EDT scripts, the name
and command tables, and the half-width patch to ADL.EXE.

The first script is named on AIF.TXT's first line; 50h and 61h load the
next.  A script (*.EDT) is read whole into a 64 KB segment: 1000h bytes of
entries (big-endian words, offsets from 1000h: the targets of 43h's
gotos, 10h's menus and 11h's items), then statements from 1000h until FFh
or the end of the file.  The interpreter (ADL.EXE 2990h, seg 80h) steps
over a statement as STMT_LEN gives, except:

* 33h, 38h, 50h, 51h, 61h, 64h: a NUL-ended file name and a byte.
* 46h: a byte, then entries until FFh: a byte, a length, that many bytes.
* 43h hi lo: goto the entry (3 bytes).
* 70h, text: items until a 00 or a byte of 09h-0Eh or 10h and up (the next
  statement).  Items: 0Fh, then characters until 00 (a run of text); 01-08
  the window's controls (01 c the colour; 02 a key wait (a blinking mark);
  03 the window cleared; 04 n speaker n's name, from the name table, and
  the text indented 80 dots after it; 05 the picture redrawn; 06 a new
  line; 07 n and 08 n an animation on and off).  A 00 straight after a
  control also moves the cursor to the window's left edge and drops the
  name's indent; a 00 after a run of text only ends the statement.
* 71h x y w h (big-endian words, dots): the text window.

Characters (ADL.EXE 19FCh): a byte of 80h and up and the next are a
Shift-JIS character; 00-7Fh is one from a table (KANA, at cs:1A8Dh:
punctuation, digits, hiragana, katakana); 20h (a blank there) is skipped.
Each is drawn to the text VRAM, two cells (16 dots), the cursor then
wrapping at the window's right edge, and paging (the key-wait mark, then
the window cleared) when the next line would reach its bottom row.

The name table (NAME_Fn.EDT, n the scenario) and the command table
(KOM_Fn.EDT: the save/load and menu items 11h's first byte picks): a mark
and coded bytes (TABLE_CODES; Part 2's 95 97, each byte rotated right
twice), until 1Ah: NUL-ended Shift-JIS
strings, a 9-byte slot (names) or a 17-byte slot (commands) each once
loaded.  Names are drawn by 19B2h (to the text VRAM, 20h one cell);
commands and the save slots' names (ADL.EXE's own) by 18D4h, to the
graphics planes through the GRCG (20h one 8-dot column).

The patch (patch_exe, on ADL.EXE; it is not packed):

* The helper's room: ROOM paragraphs put in at the end of the code
  segment (segment 80h, before the data segment: 4C4h in Part 2, 474h in
  Part 1, the lowest segment the relocations hold past 80h).  Every segment
  after it moves up by as many: the data segment and the work segments
  (707h and up, past the file's end), whose every use is a relocated
  constant (the relocations are all in the code segment); the file's size
  in the header grows with it, and the memory DOS gives past the file's
  end (the header's minimum) is the same.  The room starts with a jump
  over itself, for a routine that runs on past the code segment's end into
  the bytes that moved.
* In a run of text, 20h switches to half-width letters (until 20h again or
  the run's end): 21h-7Eh are ASCII, 7Fh a space and 0Ah a new line, each
  one cell (8 dots); bytes of 80h and up are still Shift-JIS.  The run's
  drawing loop goes to the helper, which draws them, waits as for other
  characters and wraps (pages) at the window's edges; a full-width
  character that would cross the right edge goes to the next line first.
* The new-line control (06) waits for a key before it clears a full
  window when text was drawn since the last wait (02) or clear (03);
  without the patch it clears it at once (no game text reaches it, an
  English line can).
* Name strings and the command and slot names take ASCII (each byte below
  80h one cell; the graphics planes' from the BIOS 8x16 font, int 18h AH=14h).

Every site is found by its byte signature; a program that does not match is
refused.
"""
import re
import struct

STMT_LEN = {0x10: 4, 0x11: 4, 0x12: 7, 0x13: 2, 0x14: 1, 0x15: 1, 0x20: 2, 0x21: 2, 0x30: 1, 0x31: 1,
            0x32: 1, 0x34: 1, 0x35: 1, 0x36: 9, 0x37: 11, 0x39: 1, 0x40: 5, 0x41: 5, 0x42: 4, 0x43: 3,
            0x44: 3, 0x45: 4, 0x47: 1, 0x60: 1, 0x62: 1, 0x63: 1, 0x65: 3, 0x71: 9, 0x80: 1, 0x81: 1,
            0x82: 9, 0x90: 10}
FILE_OPS = {0x33, 0x38, 0x50, 0x51, 0x61, 0x64}
LIST_OP = 0x46                  # a byte, then entries until FFh (ADL2's 4Ah)
# ADL2 (ADL2.EXE, Hoshi no Suna Monogatari 1-2: its walker at 36C0h): ADL's script with other opcodes
# (ADL5's numbering, but ADL's text and windows): a name and a byte after 16h, 33h, 38h, 50h, 51h, 61h,
# 64h, 84h, 87h; the list 4Ah; the goto 28h; the rest as its table at cs:2FA7h gives
ADL2_LEN = {0x10: 4, 0x11: 4, 0x12: 7, 0x13: 2, 0x14: 1, 0x15: 1, 0x17: 2, 0x20: 2, 0x21: 2, 0x28: 3,
            0x29: 1, 0x30: 1, 0x31: 1, 0x32: 1, 0x34: 1, 0x35: 1, 0x36: 13, 0x37: 11, 0x39: 1, 0x40: 5,
            0x41: 5, 0x42: 4, 0x43: 6, 0x48: 3, 0x49: 4, 0x4B: 3, 0x60: 1, 0x62: 1, 0x63: 1, 0x65: 3, 0x71: 9,
            0x72: 2, 0x80: 1, 0x81: 1, 0x82: 9, 0x83: 3, 0x85: 2, 0x86: 6, 0x90: 10}
_BASE = (dict(STMT_LEN), set(FILE_OPS), LIST_OP)


def set_variant(name):
    """The engine's build: "adl" (ADL.EXE, ADL'.EXE) or "adl2" (ADL2.EXE)."""
    global STMT_LEN, FILE_OPS, LIST_OP
    STMT_LEN, FILE_OPS, LIST_OP = dict(_BASE[0]), set(_BASE[1]), _BASE[2]
    if name == "adl2":
        STMT_LEN = dict(ADL2_LEN)
        FILE_OPS = {0x16, 0x33, 0x38, 0x50, 0x51, 0x61, 0x64, 0x84, 0x87}
        LIST_OP = 0x4A


ENTRIES = 0x800
BASE = 0x1000
CTRL_ARG = {1, 4, 7, 8}


TEXT_MARK = 0x0F                # a run of text's mark (ADL5's FFh)
WINDOW_OP = 0x71                # the text window (ADL5's 82h)


class Bad(Exception):
    pass


def decode(raw):
    """(how a script is coded: not at all, the script)."""
    return None, raw


def encode(how, d):
    return d


def ctrl_len(b):
    """A control's bytes, its argument with it."""
    return 2 if b in CTRL_ARG else 1


def window(d, s):
    """(x, the text's width in dots) of 71h at s."""
    x, _y, w, _h = struct.unpack_from(">4H", d, s + 1)
    return x, w


def set_window_width(d, s, width):
    """71h at s with its text widened to width dots."""
    x, y, _w, h = struct.unpack_from(">4H", d, s + 1)
    return d[s:s + 1] + struct.pack(">4H", x, y, width, h)


def statement(d, i):
    """The end of the statement at i."""
    op = d[i]
    if op in FILE_OPS:
        return d.index(0, i + 1) + 2
    if op == LIST_OP:
        j = i + 2
        while d[j] != 0xFF:
            j += 2 + d[j + 1]
        return j + 1
    if op == 0x70:
        j = i + 1
        while True:
            b = d[j]
            j += 1
            if b == 0:
                return j
            if b in CTRL_ARG:
                j += 1
            elif b == 0x0F:
                j = d.index(0, j) + 1
            elif b >= 9:
                return j - 1
    if op not in STMT_LEN:
        raise Bad("opcode %02X at %x" % (op, i))
    return i + STMT_LEN[op]


def resync(d, start, ents, step):
    """[(start, end)] of a script's statements read straight through from start (step(d, i): the end of
    the statement at i), the walk picked up again at an entry wherever it meets bytes no statement
    starts with or a statement would run across an entry (tables the walker never steps onto, reached
    by the entries); the bytes skipped move with the statements around them (rebuild_pieces)."""
    ents = sorted(v for v in ents if v < len(d))
    out, i = [], start
    while i < len(d) and d[i] != 0xFF:
        nxt = next((v for v in ents if v > i), None)
        try:
            j = step(d, i)
            ok = j <= len(d) and (nxt is None or j <= nxt)
        except (Bad, IndexError, ValueError):
            ok = False
        if ok:
            out.append((i, j))
            i = j
            continue
        # (the next entry after the last statement's start: a statement it falls inside is dropped)
        after = out[-1][0] if out else start - 1
        e = next((v for v in ents if v > after and v != i), None)
        if e is None:
            break
        if e < i:
            while out and out[-1][1] > e:
                out.pop()
        i = e
    return out


def rebuild_pieces(d, toks, new, start, ents):
    """(the script with the statements in new ({start: bytes}) replaced, the bytes between statements
    kept; {entry: its new offset}).  An entry inside bytes kept as they are moves with them; one inside
    a rebuilt statement is refused."""
    out = bytearray(d[:start])
    pieces, pos = [], start
    for s, e in toks:
        if s > pos:
            pieces.append((pos, s, len(out), True))
            out += d[pos:s]
        pieces.append((s, e, len(out), s not in new))
        out += new.get(s, d[s:e])
        pos = e
    pieces.append((pos, len(d), len(out), True))
    out += d[pos:]
    moved = {}
    for k, at in ents.items():
        if at >= len(d):
            moved[k] = at - len(d) + len(out)
            continue
        piece = next(p for p in pieces if p[0] <= at < p[1] or p[0] == at)
        if at != piece[0] and not piece[3]:
            raise Bad("entry %d (%x) is inside a rebuilt statement" % (k, at))
        moved[k] = piece[2] + (at - piece[0])
    return out, moved


def _linear(d):
    out, i = [], BASE
    while i < len(d) and d[i] != 0xFF:
        j = statement(d, i)
        if j > len(d):
            raise Bad("statement at %x runs past the end" % i)
        out.append((i, j))
        i = j
    return out


def tokenize(d):
    """[(start, end)] of the statements: read straight through, or, where that meets bytes no
    statement starts with or an entry inside a statement, picked up again at the entries (resync)."""
    try:
        out = _linear(d)
        starts = {a for a, _b in out}
        if all(v in starts or v >= len(d) for v in entries(d).values()):
            return out
    except (Bad, IndexError, ValueError):
        pass
    return resync(d, BASE, entries(d).values(), statement)


def entries(d):
    """{entry number: offset in the file} of the entries in use."""
    return {k: BASE + struct.unpack_from(">H", d, 2 * k)[0] for k in range(ENTRIES)
            if struct.unpack_from(">H", d, 2 * k)[0]}


def items(d, s, e):
    """The items of a text statement: ("text", start, end) for a run's
    characters (after its 0Fh, before its 00), ("ctrl", start, end) for a
    control and its argument, ("end", s, e) for the 00 that ends it."""
    out, j = [], s + 1
    while j < e:
        b = d[j]
        if b == 0x0F:
            k = d.index(0, j + 1)
            out.append(("text", j + 1, k))
            j = k + 1
        elif b == 0:
            out.append(("end", j, j + 1))
            j += 1
        else:
            n = 2 if b in CTRL_ARG else 1
            out.append(("ctrl", j, j + n))
            j += n
    return out


def rebuild(d, toks, new):
    """The script with the statements in new ({start: bytes}) replaced, the
    entries moved with the statements.  (A script longer than its 64 KB
    segment comes back as it is built, its entries past 64 KB cut to 16
    bits: the caller refuses it by its size.)"""
    out, moved = rebuild_pieces(d, toks, new, BASE, entries(d))
    for k, to in moved.items():
        struct.pack_into(">H", out, 2 * k, (to - BASE) & 0xFFFF)
    return bytes(out)


# ---- characters

def kana_table(img):
    """The 128 two-byte characters of the single-byte codes, read off ADL.EXE's load image."""
    at = img.find(bytes.fromhex("8140814081418142814581488149816981" "6a81758176824f"))
    if at < 0:
        raise SystemExit("ADL.EXE: the character table is not found")
    return [img[at + 2 * k:at + 2 * k + 2] for k in range(128)]


def text_of(raw, table):
    """A run's characters as text (the table's codes as the characters they draw; 20h left out)."""
    out, i = "", 0
    while i < len(raw):
        b = raw[i]
        if b >= 0x80:
            out += raw[i:i + 2].decode("cp932", "replace")
            i += 2
        else:
            if b != 0x20:
                out += table[b].decode("cp932", "replace")
            i += 1
    return out


def encode_ascii(text):
    """English for a run of text: 20h, then ASCII (7Fh a space, 0Ah a new
    line); a character outside ASCII as its Shift-JIS, else ?."""
    out = bytearray(b"\x20")
    for c in text:
        if c == " ":
            out.append(0x7F)
        elif c == "\n":
            out.append(0x0A)
        elif 0x21 <= ord(c) < 0x7F:
            out.append(ord(c))
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


# ---- the name and command tables

# the engine's coded text files (ADL.EXE 2823h): a two-byte mark, then each byte coded until 1Ah
# (coded): 95 97 rotated right twice, 97 D1 inverted, 89 CE xored with the byte after the mark
TABLE_CODES = (b"\x95\x97", b"\x97\xd1", b"\x89\xce")


def _decode(raw):
    """(the mark and key, the decoded bytes) of a coded file."""
    mark = raw[:2]
    if mark == b"\x95\x97":
        return mark, bytes(((b >> 2) | (b << 6)) & 0xFF for b in raw[2:])
    if mark == b"\x97\xd1":
        return mark, bytes(b ^ 0xFF for b in raw[2:])
    if mark == b"\x89\xce":
        return raw[:3], bytes(b ^ raw[2] for b in raw[3:])
    raise Bad("not a coded table (95 97, 97 D1 or 89 CE)")


def _encode(head, dec):
    if head == b"\x95\x97":
        return head + bytes(((b << 2) | (b >> 6)) & 0xFF for b in dec)
    if head == b"\x97\xd1":
        return head + bytes(b ^ 0xFF for b in dec)
    return head + bytes(b ^ head[2] for b in dec)


def table_read(raw):
    """(the strings of a NAME_Fn / KOM_Fn file, what follows them (the coding and the 1Ah end))."""
    head, dec = _decode(raw)
    end = dec.index(0x1A)
    parts = dec[:end].split(b"\x00")
    if parts[-1] != b"":
        raise Bad("the table does not end in NUL")
    return parts[:-1], (head, dec[end:])


def table_write(parts, tail):
    head, rest = tail
    return _encode(head, b"".join(p + b"\x00" for p in parts) + rest)


# ---- ADL.EXE

CODE_SEG = 0x80
ROOM = 0x30                     # paragraphs put in at the end of the code segment for the helper

# the run-of-text loop (19FCh): mov dh, es:[si] / inc si / or dh, dh / je / cmp dh, 20h / je (the loop's
# start: here, or ADL2's call before it) / cmp dh, 80h
TEXT_SIG = re.compile(rb"\x26\x8a\x34\x46\x0a\xf6\x74.\x80\xfe\x20\x74(.)\x80\xfe\x80\x73\x13", re.S)
# the new-line control's override (only where the build's page routine clears without a key wait)
NEWLINE_PART = """newline:
    mov ax, word ptr [{left}]
    mov word ptr [{x}], ax
    add word ptr [{y}], 0x14
    mov ax, word ptr [{bottom}]
    sub ax, 0x14
    cmp ax, word ptr [{y}]
    jne n2
    mov ax, word ptr [{top}]
    mov word ptr [{y}], ax
    cmp byte ptr cs:[{dirty}], 0
    je n1
    CALLN {keywait}
n1:
    mov byte ptr cs:[{dirty}], 0
    CALLN {clear}
n2:
    .byte 0xc3

waitkey:
    mov byte ptr cs:[{dirty}], 0
    JMPN {keywait}

clearwin:
    mov byte ptr cs:[{dirty}], 0
    JMPN {clear}


"""
# the controls' loop (1B8Dh) and its table: mov al, es:[si] / inc si / or al, al / je / cmp al, 9 / jae /
# xor ah, ah / dec al / shl ax, 1 / mov bx, table
CTRL_SIG = re.compile(rb"\x26\x8a\x04\x46\x0a\xc0\x74\x16\x3c\x09\x73\x1f\x32\xe4\xfe\xc8\xd1\xe0\xbb(..)", re.S)
# the name drawer (19B2h) at its two-byte character: mov dh, al / lodsb / mov dl, al / mov cl, es:[colour]
NAME_SIG = re.compile(rb"\x8a\xf0\xac\x8a\xd0\x26\x8a\x0e..", re.S)
# the graphics-plane drawer (18D4h) at its two-byte character: lodsb / mov dl, al / call / jmp
GRAPH_SIG = re.compile(rb"\x3c\x0d\x74\x08\xac\x8a\xd0\xe8(..)\xeb\xe6", re.S)

HELPER = """
fallthrough:
    JMPN {after}

text:
    mov dh, byte ptr es:[si]
    inc si
    or dh, dh
    jnz t0
    mov byte ptr cs:[{ank}], 0
    .byte 0xc3
t0:
    cmp dh, 0x20
    jne t1
    xor byte ptr cs:[{ank}], 1
    JMPN {loop}
t1:
    cmp dh, 0x80
    jae sj
    test byte ptr cs:[{ank}], 1
    jnz ak
    mov bl, dh
    xor bh, bh
    shl bx, 1
    mov dh, byte ptr cs:[bx + {kana}]
    mov dl, byte ptr cs:[bx + {kana1}]
    jmp kj
sj:
    mov dl, byte ptr es:[si]
    inc si
kj:
    mov ax, word ptr [{x}]
    add ax, 16
    cmp ax, word ptr [{right}]
    jbe kdraw
    CALLN wrap
kdraw:
    mov ax, word ptr [{x}]
    mov bx, word ptr [{y}]
    CALLN {xy}
    mov di, ax
    mov cl, byte ptr [{color}]
    CALLN {kanji}
    mov cx, 16
    jmp adv
ak:
    cmp dh, 0x0a
    jne a1
    mov ax, word ptr [{x}]
    cmp ax, word ptr [{left}]
    je text
    CALLN wrap
    JMPN {loop}
a1:
    cmp dh, 0x7f
    jne a2
    mov dh, 0x20
a2:
    mov ax, word ptr [{x}]
    mov bx, word ptr [{y}]
    CALLN {xy}
    mov di, ax
    mov al, dh
    mov cl, byte ptr [{color}]
    CALLN putank
    mov cx, 8
adv:
    mov byte ptr cs:[{dirty}], 1
    push cx
{fast}    mov ah, 5
    int 0x33
    mov dl, 1
    test al, 3
    jnz d1
{skip}    mov dl, 3
d1:
    mov al, dl
    CALLN {settimer}
    CALLN {waittimer}
d2:
    pop cx
    mov ax, word ptr [{x}]
    add ax, cx
    mov word ptr [{x}], ax
    cmp ax, word ptr [{right}]
    jae a3
    JMPN {loop}
a3:
    CALLN wrap
    JMPN {loop}

wrap:
    add word ptr [{y}], 0x14
    CALLN {page}
    mov ax, word ptr [{left}]
    mov word ptr [{x}], ax
    .byte 0xc3

putank:
    push es
    push ax
    mov ax, 0xa000
    mov es, ax
    pop ax
    xor ah, ah
    mov word ptr es:[di], ax
    mov ax, 0xa200
    mov es, ax
    mov al, cl
    ror al, 3
    or al, 1
    mov byte ptr es:[di], al
    pop es
    .byte 0xc3

{newline_part}
name:
    cmp al, 0x80
    jb nm1
    mov dh, al
    lodsb
    mov dl, al
    mov cl, byte ptr es:[{color}]
    CALLN {kanji}
    add di, 4
    JMPN {nameloop}
nm1:
    mov cl, byte ptr es:[{color}]
    CALLN putank
    add di, 2
    JMPN {nameloop}

graph:
    cmp al, 0x80
    jb g1
    lodsb
    mov dl, al
    CALLN {cgkanji}
    JMPN {graphloop}
g1:
    pusha
    push ds
    push es
    mov dl, al
    mov dh, 0x80
    mov bx, es
    mov cx, 0x2f
    mov ah, 0x14
    int 0x18
    mov ds, bx
    mov ax, 0x0f
    cli
    CALLN {grcg_on}
    mov ax, 0xa800
    mov es, ax
    mov si, 0x31
    mov cx, 16
g2:
    lodsb
    mov byte ptr es:[di], al
    add di, 0x50
    loop g2
    CALLN {grcg_off}
    sti
    pop es
    pop ds
    popa
    inc di
    JMPN {graphloop}

"""


def _asm16(src, org, want):
    """Keystone for 16-bit code: CALLN and JMPN x (a label or a 0x address) as
    3-byte near calls and jumps; (code, {label: address}) for want."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    from .illusion_font import _asm
    lines, jumps = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("JMPN "):
            tag = "__jmp%d" % len(jumps)
            jumps.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    targets = [x for _t, x in jumps if not x.startswith("0x")]
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org,
                      list(want) + [t for t, _x in jumps] + targets)
    code = bytearray(code)
    for tag, target in jumps:
        t = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = b"\xe9" +((t - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] in (0x66, 0x67):
            raise SystemExit("ADL.EXE: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def _code_end(img, boundary, name):
    """Where a code segment's code ends, for the room put in after it: the boundary (the next segment's
    start, a paragraph) when the code before it ends there (a ret or jmp, or zero padding), else the end
    of the routine that runs on past it (DOR Special Edition '93's ADL5.EXE: 13 bytes into its data
    segment; Yuu Disk Vol. 4's ADL98.EXE: an instruction across the boundary, 11 bytes into a library
    segment, whose own code starts after them).  The bytes up to it stay where they are."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    if bytes(img[boundary - 3:boundary]) == bytes(3):
        return boundary
    term = ("ret", "retf", "iret", "jmp", "ljmp")
    start = max(0, boundary - 0x80)
    ins = list(Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(img[start:boundary + 0x40]), start))
    before = [i for i in ins if i.address < boundary]
    if not before:
        raise SystemExit("%s: the code before the next segment does not decode" % name)
    last = before[-1]
    if last.address + last.size == boundary and last.mnemonic in term:
        return boundary
    for i in ins:
        if i.address >= last.address and i.mnemonic in term:
            return i.address + i.size
    raise SystemExit("%s: the code segment's last routine does not end within 64 bytes of the next segment"
                     % name)


def _once(img, sig, what, lo=0, hi=None):
    hi = len(img) if hi is None else hi
    if isinstance(sig, re.Pattern):
        found = [m for m in sig.finditer(img, lo, hi)]
        if len(found) != 1:
            raise SystemExit("ADL.EXE: the %s signature is found %d times, not once" % (what, len(found)))
        return found[0]
    found = [m.start() for m in re.finditer(re.escape(sig), img[lo:hi])]
    if len(found) != 1:
        raise SystemExit("ADL.EXE: the %s signature is found %d times, not once" % (what, len(found)))
    return lo + found[0]


def _call_target(img, at):
    """The target of the near call (E8) at at (cs offsets)."""
    if img[at] != 0xE8:
        raise SystemExit("ADL.EXE: a call is not where expected at %x" % at)
    return (at + 3 + struct.unpack_from("<h", img, at + 1)[0]) & 0xFFFF


def patch_exe(exe):
    """ADL.EXE with the half-width helper (see the module's docstring)."""
    if exe[:2] != b"MZ":
        raise SystemExit("ADL.EXE: not an MZ program")
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    if struct.unpack_from("<H", exe, 0x16)[0] != CODE_SEG:
        raise SystemExit("ADL.EXE: the entry is not in segment 80h")
    img = bytearray(exe[hdr:])
    cs0 = CODE_SEG * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    # (the data segment: the lowest segment past the code's in the relocations; the code segment ends at it)
    data_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > CODE_SEG)
    seg = bytearray(img[cs0:data_seg * 16])
    tm = _once(seg, TEXT_SIG, "text loop")
    text = tm.start()
    loop = (text + 13 + struct.unpack("b", tm.group(1))[0]) & 0xFFFF
    # the table lookup and the draw path, read off the loop: mov bl, dh / xor bh, bh / shl bx, 1 / add bx, table
    look = seg.find(bytes.fromhex("8ade32ffd1e381c3"), text, text + 0x40)
    if look < 0:
        raise SystemExit("ADL.EXE: the text loop's table lookup is not found")
    kana = struct.unpack_from("<H", seg, look + 8)[0]
    # (the draw path: mov ax, [x] / mov bx, [y] / call xy / mov di, ax / mov cl, [colour] / call kanji)
    m = re.compile(rb"\xa1(..)\x8b\x1e(..)\xe8..\x8b\xf8\x8a\x0e(..)\xe8", re.S).search(seg, text, text + 0x40)
    if not m:
        raise SystemExit("ADL.EXE: the text loop's draw path is not found")
    draw = m.start()
    var_x, var_y, var_color = (struct.unpack("<H", g)[0] for g in m.groups())
    xy = _call_target(seg, draw + 7)
    kanji = _call_target(seg, draw + 16)
    # (the speed wait after it: mov ah, 5 / int 33h / mov dl, 1 / test al, 3 / jne, then in later builds
    # call skipkey / test al, 10h / jne; mov dl, 3 / mov al, dl / call settimer / call waittimer / call advance)
    wait = seg.find(bytes.fromhex("b405cd33b201a80375"), draw, draw + 0x50)
    # (ADL2's: cmp [fast], 0 / jne / mov ax, 40Eh / int 18h / test ah, 4 / jne, before it)
    fm = re.compile(rb"\x80\x3e(..)\x00\x75.\xb8\x0e\x04\xcd\x18\xf6\xc4\x04\x75.", re.S).search(seg, draw, max(draw, wait))
    fast = ("    cmp byte ptr [%s], 0\n    jne d2\n    mov ax, 0x40e\n    int 0x18\n    test ah, 4\n    jne d2\n"
            % hex(struct.unpack("<H", fm.group(1))[0])) if fm else ""
    if wait < 0 or seg[wait:wait + 9] != bytes.fromhex("b405cd33b201a80375"):
        raise SystemExit("ADL.EXE: the text loop's speed wait is not laid out as expected")
    at = wait + 10
    skip = ""
    if seg[at] == 0xE8:
        if seg[at + 3:at + 6] != bytes.fromhex("a81075"):
            raise SystemExit("ADL.EXE: the text loop's speed wait is not laid out as expected")
        skip = "    CALLN %s\n    test al, 0x10\n    jnz d1\n" % hex(_call_target(seg, at))
        at += 7
    if seg[at:at + 4] != bytes.fromhex("b2038ac2"):
        raise SystemExit("ADL.EXE: the text loop's speed wait is not laid out as expected")
    settimer = _call_target(seg, at + 4)
    waittimer = _call_target(seg, at + 7)
    advance = _call_target(seg, at + 10)
    # (the advance: mov ax, [x] / add ax, 10h / cmp ax, [right] / jne / add [y], 14h / call page / mov ax, [left])
    m = re.compile(rb"\xa1(..)\x05\x10\x00\x3b\x06(..)\x75\x0b\x83\x06(..)\x14\xe8..\xa1(..)", re.S).match(seg, advance)
    if not m or struct.unpack("<H", m.group(1))[0] != var_x or struct.unpack("<H", m.group(3))[0] != var_y:
        raise SystemExit("ADL.EXE: the text loop's advance is not laid out as expected")
    var_right, var_left = struct.unpack("<H", m.group(2))[0], struct.unpack("<H", m.group(4))[0]
    page = _call_target(seg, advance + 17)
    # (the page: mov ax, [bottom] / sub ax, 14h / cmp ax, [y] / jne / mov ax, [top]; ADL2's: mov ax, [y] /
    # cmp ax, [bottom] / jb / call its new line, which waits for a key itself: no override then)
    m = re.compile(rb"\xa1(..)\x2d\x14\x00\x3b\x06(..)\x75.\xa1(..)", re.S).match(seg, page)
    m2 = re.compile(rb"\xa1(..)\x3b\x06(..)\x72\x03\xe8", re.S).match(seg, page)
    if m and struct.unpack("<H", m.group(2))[0] == var_y:
        var_bottom, var_top = struct.unpack("<H", m.group(1))[0], struct.unpack("<H", m.group(3))[0]
        override = True
    elif m2 and struct.unpack("<H", m2.group(1))[0] == var_y:
        var_bottom, var_top, override = struct.unpack("<H", m2.group(2))[0], 0, False
    else:
        raise SystemExit("ADL.EXE: the paging routine is not laid out as expected")
    m = _once(seg, CTRL_SIG, "controls' loop")
    table = struct.unpack_from("<H", m.group(1))[0]
    ctrl = list(struct.unpack_from("<8H", seg, table))
    keywait, clear = ctrl[1], ctrl[2]
    name = _once(seg, NAME_SIG, "name drawer").start()
    if seg[name + 13:name + 16] != b"\x83\xc7\x04" or seg[name + 16] != 0xEB:
        raise SystemExit("ADL.EXE: the name drawer is not laid out as expected")
    nameloop = name + 18 + struct.unpack("b", seg[name + 17:name + 18])[0]
    g = _once(seg, GRAPH_SIG, "graphics drawer")
    gat = g.start() + 4
    cgkanji = _call_target(seg, gat + 3)
    graphloop = gat + 8 + struct.unpack("b", seg[gat + 7:gat + 8])[0]
    # (the GRCG on and off the CG drawer calls: mov al, 0Fh / cli / call on / ... / call off / sti)
    cgk = seg.find(bytes.fromhex("32e4b00ffae8"), cgkanji, cgkanji + 0x30)
    if cgk < 0 or seg[cgk + 17] != 0xFB:
        raise SystemExit("ADL.EXE: the CG drawer is not laid out as expected")
    grcg_on = _call_target(seg, cgk + 5)
    grcg_off = _call_target(seg, cgk + 14)
    # (the room: at the end of the code segment's code, the data segment and all after it moved up)
    split = _code_end(img, data_seg * 16, "ADL.EXE")
    at = split - CODE_SEG * 16
    helper_at, flags = at, (at + ROOM * 16 - 2, at + ROOM * 16 - 1)
    newline_part = NEWLINE_PART if override else ""
    src = HELPER.replace("{newline_part}", newline_part).format(
                        kana=hex(kana), kana1=hex(kana + 1), xy=hex(xy), kanji=hex(kanji), skip=skip,
                        loop="text" if loop == text else hex(loop), fast=fast,
                        settimer=hex(settimer), waittimer=hex(waittimer), page=hex(page), keywait=hex(keywait),
                        clear=hex(clear), nameloop=hex(nameloop), cgkanji=hex(cgkanji), graphloop=hex(graphloop),
                        grcg_on=hex(grcg_on), grcg_off=hex(grcg_off), ank=hex(flags[0]), dirty=hex(flags[1]),
                        x=hex(var_x), y=hex(var_y), color=hex(var_color), left=hex(var_left), top=hex(var_top),
                        right=hex(var_right), bottom=hex(var_bottom), after=hex(at + ROOM * 16))
    code, labels = _asm16(src, helper_at, ("text", "name", "graph") + (("waitkey", "clearwin", "newline")
                                                                        if override else ()))
    if len(code) > ROOM * 16 - 2:
        raise SystemExit("ADL.EXE: the helper is %d bytes, the room %d" % (len(code), ROOM * 16 - 2))

    def jmp(at, to, n):
        seg[at:at + n] = b"\xe9" + struct.pack("<H", (to - (at + 3)) & 0xFFFF) + b"\x90" * (n - 3)
    jmp(text, labels["text"], 3)
    jmp(name, labels["name"], 5)
    jmp(gat, labels["graph"], 3)
    if override:
        ctrl[1], ctrl[2], ctrl[5] = labels["waitkey"], labels["clearwin"], labels["newline"]
        struct.pack_into("<8H", seg, table, *ctrl)
    img[cs0:cs0 + len(seg)] = seg
    # no segment fixup may fall in what was changed
    for lo, n in ((text, 3), (name, 5), (gat, 3), (table, 16)):
        if any(cs0 + lo - 1 <= f < cs0 + lo + n for f in fixups):
            raise SystemExit("ADL.EXE: a segment fixup falls in a patched range")
    # the room put in, the segments after it moved up
    if any(f >= split for f in fixups):
        raise SystemExit("ADL.EXE: a segment fixup is past the code segment")
    for f in fixups:
        v = struct.unpack_from("<H", img, f)[0]
        if v >= data_seg:
            struct.pack_into("<H", img, f, v + ROOM)
        elif v != CODE_SEG:
            raise SystemExit("ADL.EXE: a fixup holds segment %x, before the data segment" % v)
    room = bytearray(ROOM * 16)
    room[:len(code)] = code
    img[split:split] = room
    out = bytearray(exe[:hdr]) + img
    struct.pack_into("<HH", out, 2, len(out) % 512, -(-len(out) // 512))
    return bytes(out)
