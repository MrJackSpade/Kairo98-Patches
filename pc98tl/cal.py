"""Birdy Soft's Cal (ADOS, pc98tl/ados.py): the scripts, and English drawn half-width.

The game's program (an ADOS file loaded at segment 1000h) runs scripts, ADOS files 10h + n, each loaded
whole into its own segment at 74A4h (the game's flags start at D5E8h: 24 sectors at most).  A script
(`tokens`) is a run of commands:
* FFh and a code: FF FF n and n 3-byte conditions (an if), FF FE (else), FF FD (end if), FF FC v / FF FB
  v / FF FA / FF F9 (a switch on a flag, its cases, a case's end, the switch's end), FF F8 and a 3-byte
  condition / FF F7 (while), FF F6 / FF F5 (a loop), FF EF and FF EE with a word (a jump and a call,
  14-bit signed, from the byte after them), FF EC (return), FF ED, FF EB n (go to script n), FF E9 n,
  FF E8 n, FF E0 n, FF E6 w, FF E4 w, the others alone.
* a byte under 20h: a command with 0, 1 or 2 bytes after it; 03 n is a choice menu's items (each up to
  its 0, the list up to a byte under 20h or FFh, which is not part of it), 0D n a name (up to "!": the
  name letters A-Z insert in text), 0A waits for a click, 1D clears the window.
* anything else starts a text line, up to "$": Shift-JIS characters (two bytes), and single-byte codes:
  0-7 a colour, A-Z a name, # the text's indent (after a speaker's name), \\ a new line.
The program writes text to the text layer, a full-width character two cells; its window is 70 cells by
4 rows.

English (`encode`): ASCII is written one byte a letter, in the bytes text never uses (80h, A0h-DFh,
F0h-FEh, `MAP`); the program (`patch_program`) is given a helper, put where the script buffer started
(the buffer moved up), that reads such a byte as one character and draws it as one cell of the text
layer (its ANK character), the column moved on by one.  Lines are broken between words by the patcher;
a message longer than the window is ended and continued after a click.  A script that outgrows the
buffer is split (`split`): its rest goes into a script of its own that the first ends by going to.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .illusion_font import _asm

FF_ARGS = {0xFC: 1, 0xFB: 1, 0xEB: 1, 0xE9: 1, 0xE8: 1, 0xE0: 1, 0xF8: 3, 0xEF: 2, 0xEE: 2, 0xE6: 2, 0xE4: 2}
CTL_ARGS = {0x01: 1, 0x04: 1, 0x07: 1, 0x08: 1, 0x09: 1, 0x0C: 1, 0x10: 2, 0x11: 2, 0x12: 2, 0x13: 2, 0x14: 2,
            0x15: 2, 0x16: 2, 0x17: 1, 0x18: 1, 0x19: 1, 0x1A: 1, 0x1B: 1, 0x1C: 1}
OPEN = {0xFF, 0xFC, 0xF8, 0xF6}
CLOSE = {0xFD, 0xF9, 0xF7, 0xF5}

# the bytes English uses, in order: a letter's byte is MAP's place of it
CHARS = (" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"-:;()&/%*+")
CODES = [0x80] + list(range(0xA0, 0xE0)) + list(range(0xF0, 0xFF))
MAP = dict(zip(CHARS, CODES))
UNMAP = {v: k for k, v in MAP.items()}


def tokens(s, gram=None):
    """[(kind, start, end)]: text (a line, its $ included), choice (03 n and its items), name (0D n ... !),
    jump (FF EF / FF EE), cmd.  gram: the program's commands' arguments (`grammar`; Cal's by default)."""
    ff_args = gram["ff"] if gram else FF_ARGS
    ctl_args = gram["ctl"] if gram else CTL_ARGS
    out, k, n = [], 0, len(s)
    while k < n:
        b = s[k]
        if b == 0xFF:
            x = s[k + 1]
            if x == 0xFF:
                e = k + 3 + 3 * s[k + 2]
            else:
                e = k + 2 + ff_args.get(x, 0)
            out.append(("jump" if x in (0xEF, 0xEE) else "cmd", k, e))
            k = e
        elif b == 0x03:
            j = k + 2
            while j < n and not (s[j] < 0x20 and s[j] != 0 or s[j] == 0xFF):
                if s[j] == 0:
                    j += 1
                elif 0x41 <= s[j] <= 0x5A:
                    j += 1
                else:
                    j += 2
            out.append(("choice", k, j))
            k = j
        elif b == 0x0D:
            j = s.index(b"!", k + 2) + 1
            out.append(("name", k, j))
            k = j
        elif b < 0x20:
            e = k + 1 + ctl_args.get(b, 0)
            out.append(("cmd", k, e))
            k = e
        else:
            j = k
            while s[j] != 0x24:
                j += 2 if s[j] >= 0x80 else 1
            out.append(("text", k, j + 1))
            k = j + 1
    if k != n:
        raise ValueError("a script runs past its end")
    return out


def jump_target(s, a):
    """Where FF EF / FF EE at a goes: its word holds 14 bits, the low 7 of each byte (lodsw / shl al, 1 /
    shl ax, 1 / sar ax, 1 / sar ax, 1), signed, from the byte after it."""
    w = struct.unpack_from("<H", s, a + 2)[0]
    v = ((w >> 8) & 0x7F) << 7 | (w & 0x7F)
    if v & 0x2000:
        v -= 0x4000
    return a + 4 + v


def jump_word(delta):
    if not -0x2000 <= delta < 0x2000:
        raise ValueError("a jump of %d bytes" % delta)
    v = delta & 0x3FFF
    return struct.pack("<BB", v & 0x7F, v >> 7)


# ---- text lines ------------------------------------------------------------------------------------
def text_parts(s, a, e):
    """(prefix, body, suffix) of a text line: the leading codes (colour digits, name letters, #), the
    text, the trailing \\ and $ (as bytes)."""
    k = a
    while k < e and (0x30 <= s[k] <= 0x37 or 0x41 <= s[k] <= 0x5A or s[k] == 0x23):
        k += 1
    j = e - 1
    if j > k and s[j - 1] == 0x5C:
        j -= 1
    return bytes(s[a:k]), bytes(s[k:j]), bytes(s[j:e])


def show(b):
    """A text body as shown: Japanese as itself, a colour as {c7}, a name as {A}.., \\ as a new line,
    English bytes as their letters."""
    out, k = "", 0
    while k < len(b):
        c = b[k]
        if c in UNMAP:
            out += UNMAP[c]
            k += 1
        elif c >= 0x80:
            out += b[k:k + 2].decode("cp932", "replace")
            k += 2
        elif 0x30 <= c <= 0x37:
            out += "{c%d}" % (c - 0x30)
            k += 1
        elif 0x41 <= c <= 0x5A:
            out += "{%s}" % chr(c)
            k += 1
        elif c == 0x5C:
            out += "\n"
            k += 1
        elif c == 0x23:
            out += "{#}"
            k += 1
        else:
            out += "{x%02X}" % c
            k += 1
    return out


def has_japanese(b):
    k = 0
    while k < len(b):
        if b[k] >= 0x80:
            return True
        k += 1
    return False


def choice_items(s, a, e):
    """[(start, end)] of a choice command's items (each without its 0)."""
    out, j = [], a + 2
    while j < e:
        st = j
        while j < e and s[j] != 0:
            j += 1 if 0x41 <= s[j] <= 0x5A else 2
        out.append((st, j))
        j += 1
    return out


def name_text(s, a, e):
    return a + 2, e - 1


def encode_chars(text):
    """English as its bytes: letters by MAP, a name {A}..{Z} and a colour {c0}..{c7} as their codes,
    anything else as ?."""
    import re
    out = bytearray()
    for m in re.finditer(r"\{([A-Z])\}|\{c([0-7])\}|(.)", text, re.S):
        if m.group(1):
            out.append(ord(m.group(1)))
        elif m.group(2):
            out.append(0x30 + int(m.group(2)))
        else:
            ch = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-",
                  "–": "-", "…": "..."}.get(m.group(3), m.group(3))
            for c in ch:
                out.append(MAP.get(c, MAP["?"]))
    return bytes(out)


# ---- the program -----------------------------------------------------------------------------------
BUFFER = 0x74A4
FLAGS = 0xD5E8
HELPER_ROOM = 0x250

HELPER = """
fetch:
    xor ah, ah
    lodsb
    or al, al
    jns f_ret
    CALLN start
f_ret:
    .byte 0xc3
start:
    cmp al, 0x80
    je s_one
    cmp al, 0xa0
    jb s_two
    cmp al, 0xe0
    jb s_one
    cmp al, 0xf0
    jb s_two
    cmp al, 0xff
    je s_two
s_one:
    xor ah, ah
    .byte 0xc3
s_two:
    mov ah, al
    lodsb
    .byte 0xc3
draw:
    or ah, ah
    jz d_one
    JMPN {orig}
d_one:
    cmp al, 0x80
    jae d_go
    JMPN {orig}
d_go:
    push bx
    push dx
    push di
    push es
    mov bl, al
    xor bh, bh
    mov al, byte ptr cs:[bx + {table} - 0x80]
    mov di, 0xa000
    mov es, di
    mov di, word ptr cs:[{row}]
    mov dl, byte ptr cs:[{winy}]
    xor dh, dh
    add di, dx
    shl di, 4
    mov dx, di
    shl di, 2
    add di, dx
    add di, word ptr cs:[{col}]
    mov dl, byte ptr cs:[{winx}]
    xor dh, dh
    add di, dx
    shl di, 1
    mov dl, byte ptr cs:[{color}]
    ror dl, 3
    or dl, 1
    mov byte ptr es:[di + 0x2000], dl
    xor ah, ah
    stosw
    mov ax, word ptr cs:[{col}]
    mov dx, word ptr cs:[{row}]
    inc ax
    cmp al, byte ptr cs:[{width}]
    jne d_store
    mov ax, word ptr cs:[{left}]
    inc dx
    cmp dl, byte ptr cs:[{height}]
    jne d_store
    dec dx
    mov word ptr cs:[{action}], 0x16
d_store:
    mov word ptr cs:[{col}], ax
    mov word ptr cs:[{row}], dx
    mov byte ptr cs:[{flag}], 0
    pop es
    pop di
    pop dx
    pop bx
    .byte 0xc3
g_conv:
    cmp dh, 0x80
    je g_map
    cmp dh, 0xa0
    jb g_norm
    cmp dh, 0xe0
    jb g_map
    cmp dh, 0xf0
    jb g_norm
    cmp dh, 0xff
    je g_norm
    jmp g_map
g_norm:
    mov byte ptr cs:[g_flag], 0
    sub dh, 0x81
    cmp dh, 0x6f
    .byte 0xcb
g_map:
    push ax
    push bx
    push cx
    push dx
    mov bl, dh
    xor bh, bh
    mov al, byte ptr cs:[bx + {table} - 0x80]
    mov cx, g_b1
    CALLN g_glyph
    pop dx
    push dx
    mov al, 0x20
    cmp dl, 0x80
    jb g_l2
    mov bl, dl
    xor bh, bh
    mov al, byte ptr cs:[bx + {table} - 0x80]
g_l2:
    mov cx, g_b2
    CALLN g_glyph
    mov byte ptr cs:[g_flag], 1
    pop dx
    pop cx
    pop bx
    pop ax
    pop word ptr cs:[g_tmp]
    pop word ptr cs:[g_seg]
    pop word ptr cs:[g_tmp]
    push word ptr cs:[g_seg]
    push word ptr cs:[g_tmp]
    clc
    .byte 0xcb
g_glyph:
    cmp al, 0x21
    jb g_space
    mov dl, al
    mov dh, 0x80
    mov bx, cs
    mov ah, 0x14
    int 0x18
    .byte 0xc3
g_space:
    mov bx, cx
    mov cx, 9
g_clear:
    mov word ptr cs:[bx + 2], 0
    add bx, 2
    loop g_clear
    .byte 0xc3
g_row:
    cmp byte ptr cs:[g_flag], 0
    jne r_map
    mov al, cl
    out 0xa5, al
    in al, 0xa9
    mov ah, al
    mov al, cl
    or al, 0x20
    out 0xa5, al
    in al, 0xa9
    mov dx, ax
    .byte 0xcb
r_map:
    push bx
    mov bl, cl
    xor bh, bh
    mov al, byte ptr cs:[bx + g_b1 + 2]
    mov ah, byte ptr cs:[bx + g_b2 + 2]
    pop bx
    mov dx, ax
    .byte 0xcb
g_b1:
    .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
g_b2:
    .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
g_flag:
    .byte 0
g_tmp:
    .word 0
g_seg:
    .word 0
"""


# the text routine's character writer: push dx / push di / push es / push A000h / pop es / mov di, cs:[row] /
# mov dl, cs:[win y] / ... / add di, cs:[col] / mov dl, cs:[win x] / ... / mov dl, cs:[colour] / ror dl, 3
DRAW_SIG = re.compile(rb"\x52\x57\x06\x68\x00\xa0\x07\x2e\x8b\x3e(..)\x2e\x8a\x16(..)\x32\xf6\x03\xfa\xc1\xe7\x04"
                      rb"\x8b\xd7\xc1\xe7\x02\x03\xfa\x2e\x03\x3e(..)\x2e\x8a\x16(..)\x32\xf6\x03\xfa\xd1\xe7"
                      rb"\x2e\x8a\x16(..)\xc0\xca\x03", re.S)
# its column's advance: mov ax, cs:[col] / mov dx, cs:[row] / add ax, 2 / cmp al, cs:[width] / jne / mov ax,
# cs:[left] / inc dx / cmp dl, cs:[height] / jne / dec dx / mov word cs:[action], 16h / ... / mov byte cs:[flag], 0
ADVANCE_SIG = re.compile(rb"\x2e\xa1(..)\x2e\x8b\x16(..)\x05\x02\x00\x2e\x3a\x06(..)\x75\x14\x2e\xa1(..)\x42"
                         rb"\x2e\x3a\x16(..)\x75\x08\x4a\x2e\xc7\x06(..)\x16\x00\x2e\xa3..\x2e\x89\x16..\x2e\xc6\x06(..)\x00",
                         re.S)
# the text routine's fetches: xor ah, ah / lodsb / or al, al / jns +5 / mov ah, al / lodsb / jmp +0 (then
# mov [char], ax), and xor ah, ah / lodsb / or al, al / js +3 / jmp back / mov ah, al / lodsb / jmp back
FETCH1_SIG = re.compile(rb"\x32\xe4\xac\x0a\xc0\x79\x05\x8a\xe0\xac\xeb\x00\xa3", re.S)
FETCH2_SIG = re.compile(rb"\x32\xe4\xac\x0a\xc0\x78\x03\xe9(..)\x8a\xe0\xac\xe9..", re.S)
# a line's start: mov ah, al / lodsb / mov word [handler], text routine
START_SIG = re.compile(rb"\x8a\xe0\xac\xc7\x06..(..)\xa3", re.S)
# the writer's call: pop ax / call writer / (fetch)
CALL_SIG = re.compile(rb"\x58\xe8(..)\x32\xe4\xac\x0a\xc0\x79\x05", re.S)
# the script's load: mov ah, 0 (disk A) / add al, 10h / int 49h
LOAD_SIG = re.compile(rb"\xb4\x00\x04\x10\xcd\x49")
# the script buffer: mov bx, buffer / mov [script pointer], bx
BUFFER_SIG = re.compile(rb"\xbb(..)\x89\x1e..\xa1..\xe8", re.S)


def _one(sig, data, what):
    found = list(sig.finditer(data))
    if len(found) != 1:
        raise SystemExit("Cal program: the %s's signature is found %d times, not once" % (what, len(found)))
    return found[0]


def _asm16(src, org):
    lines, fix = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("CALLN ") or t.startswith("JMPN "):
            tag = "__f%d" % len(fix)
            fix.append((tag, t.split()[0], t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    labels = [t for t, _o, _x in fix] + sorted({x for _t, _o, x in fix if not x.startswith("0x")}) + \
        ["fetch", "start", "draw", "g_conv", "g_row"]
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org, sorted(set(labels)))
    code = bytearray(code)
    for tag, op, target in fix:
        to = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = (b"\xe8" if op == "CALLN" else b"\xe9") + ((to - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("Cal program: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def patch_program(prog, disk_b=True):  # noqa: C901
    """The program with the helper (see the module's docstring) at the script buffer's old start, the
    buffer moved up past it, and (disk_b) the scripts read from disk B."""
    g = bytearray(prog)
    word = lambda m, k: struct.unpack("<H", m.group(k))[0]  # noqa: E731
    d = _one(DRAW_SIG, g, "character writer")
    a = _one(ADVANCE_SIG, g, "column's advance")
    buf = _one(BUFFER_SIG, g, "script buffer")
    old = word(buf, 1)
    if len(g) > old:
        raise SystemExit("Cal program: the program runs into its script buffer")
    v = dict(row=word(d, 1), winy=word(d, 2), col=word(d, 3), winx=word(d, 4), color=word(d, 5),
             width=word(a, 3), left=word(a, 4), height=word(a, 5), action=word(a, 6), flag=word(a, 7))
    if word(a, 1) != v["col"] or word(a, 2) != v["row"]:
        raise SystemExit("Cal program: the writer and its advance do not agree")
    call = _one(CALL_SIG, g, "writer's call")
    orig = (call.start() + 4 + struct.unpack("<h", call.group(1))[0]) & 0xFFFF
    if orig != d.start():
        raise SystemExit("Cal program: the writer's call is not the writer")
    org = old
    src = lambda table: HELPER.format(table=hex(table), orig=hex(orig), **{k: hex(x) for k, x in v.items()})
    code, _ad = _asm16(src(org + 0x100), org)
    code, ad = _asm16(src(org + len(code)), org)
    table = bytes(ord(UNMAP.get(c, "?")) for c in range(0x80, 0xFF))
    helper = code + table
    if len(helper) > HELPER_ROOM:
        raise SystemExit("Cal program: the helper takes %d bytes, room for %d" % (len(helper), HELPER_ROOM))
    # the sites
    f1 = _one(FETCH1_SIG, g, "first fetch")
    f2 = _one(FETCH2_SIG, g, "second fetch")
    st = _one(START_SIG, g, "line start")
    rel = lambda at, to: struct.pack("<H", (to - (at + 3)) & 0xFFFF)  # noqa: E731
    back = (f2.start() + 10 + struct.unpack("<h", f2.group(1))[0]) & 0xFFFF
    g[f1.start():f1.start() + 12] = b"\xe8" + rel(f1.start(), ad["fetch"]) + b"\x90" * 9
    g[f2.start():f2.start() + 16] = b"\xe8" + rel(f2.start(), ad["fetch"]) + b"\xe9" + rel(f2.start() + 3, back) + \
        b"\x90" * 10
    g[st.start():st.start() + 3] = b"\xe8" + rel(st.start(), ad["start"])
    g[call.start() + 1:call.start() + 4] = b"\xe8" + rel(call.start() + 1, ad["draw"])
    struct.pack_into("<H", g, buf.start(1), old + HELPER_ROOM)
    if disk_b:
        ld = _one(BASE_SIG, g, "script load")
        g[ld.start() + 7] = 1
    g += bytes(old - len(g)) + helper
    return bytes(g), {k: ad[k] for k in ("g_conv", "g_row")}


def buffer_sectors(prog):
    """Whole sectors the moved script buffer holds (up to the flags)."""
    old = struct.unpack("<H", _one(BUFFER_SIG, prog, "script buffer").group(1))[0]
    return (flags_at(prog) - (old + HELPER_ROOM)) // 1024


def split(n, data, limit, spare, base=0x10, gram=None):
    """{script file: bytes}: the script whole, or (longer than `limit`) cut where nothing is open (no if,
    switch, while or loop, no choice menu waiting for its switch) right after a window is cleared, the
    first part ended by FF EB going to the rest, put in a spare script number (recursively)."""
    if len(data) <= limit:
        return {n: data}
    best = None
    depth, pending = 0, False
    T = tokens(data, gram)
    for i, (kind, a, e) in enumerate(T):
        if i and depth == 0 and not pending and T[i - 1][0] == "cmd" and data[T[i - 1][1]] == 0x1D \
                and a + 3 <= limit:
            best = a
        if kind == "cmd" and data[a] == 0xFF:
            x = data[a + 1]
            if x in OPEN:
                depth += 1
            elif x in CLOSE:
                depth -= 1
            if x == 0xF9:
                pending = False
        elif kind == "choice":
            pending = True
        elif kind == "cmd" and data[a] == 0x02:
            pending = False
    if best is None or not spare:
        raise SystemExit("script %02Xh: %d bytes, the buffer holds %d, and no place to split it" % (n, len(data), limit))
    m = spare.pop(0)
    out = {n: data[:best] + bytes([0xFF, 0xEB, m - base])}
    out.update(split(m, data[best:], limit, spare, base, gram))
    return out


# the kernel's Shift-JIS to JIS: sub dh, 81h / cmp dh, 6Fh / jae / cmp dh, 1Fh
CONV_SIG = re.compile(rb"\x80\xee\x81\x80\xfe\x6f\x73.\x80\xfe\x1f", re.S)
# its glyph reader's row: mov al, cl / out A5h, al / in al, A9h / mov ah, al / mov al, cl / or al, 20h /
# out A5h, al / in al, A9h / mov dx, ax
ROW_SIG = re.compile(rb"\x8a\xc1\xe6\xa5\xe4\xa9\x8a\xe0\x8a\xc1\x0c\x20\xe6\xa5\xe4\xa9\x8b\xd0")
GAME_SEG = 0x1000


def patch_kernel(kernel, addr):
    """The ADOS kernel with its character drawing able to draw a cell of two English letters: its
    conversion of a character's code and its glyph reader's row read made far calls to the helper in
    the program (segment 1000h, where the kernel loads it)."""
    k = bytearray(kernel)
    c = _one(CONV_SIG, k, "kernel's code conversion")
    r = _one(ROW_SIG, k, "kernel's glyph row")
    far = lambda off: b"\x9a" + struct.pack("<HH", off, GAME_SEG)  # noqa: E731
    k[c.start():c.start() + 6] = far(addr["g_conv"]) + b"\x90"
    k[r.start():r.start() + 18] = far(addr["g_row"]) + b"\x90" * 13
    return bytes(k)


def _sjis_only(t):
    k = 0
    while k < len(t):
        if not (0x81 <= t[k] <= 0x9F or 0xE0 <= t[k] <= 0xEF) or k + 1 >= len(t) or t[k + 1] < 0x40:
            return False
        k += 2
    return True


def program_strings(prog):
    """[(start, end)] of the program's own strings (menus, chapter names, the name prompt, the music
    test, the credits): runs of full-width characters ended by a 0, not only spaces, at least three
    characters, drawn by the kernel a character a 16-dot cell."""
    out = []
    e = prog.find(b"\0")
    while e >= 0:
        k = e
        while k >= 2 and (0x81 <= prog[k - 2] <= 0x84 or 0x88 <= prog[k - 2] <= 0x9F or 0xE0 <= prog[k - 2] <= 0xEA) \
                and 0x40 <= prog[k - 1] <= 0xFC and prog[k - 1] != 0x7F:
            k -= 2
        t = bytes(prog[k:e])
        if len(t) >= 6 and t.replace(b"\x81\x40", b""):
            try:
                t.decode("cp932")
                out.append((k, e))
            except UnicodeDecodeError:
                pass
        e = prog.find(b"\0", e + 1)
    return out


# the kernel's disk prompt: the disk's and the drive's letters written at its bytes 10 and 30
DISK_PROMPT = "ＤＩＳＫ　？　を　ＤＲＩＶＥ　？　に入れてください".encode("cp932")
PROMPT_SLOTS = (10, 30)


def encode_pairs(text, room):
    """English for a string the kernel draws: two letters a 16-dot cell (MAP's bytes, a pair a
    character), padded with spaces to `room` bytes."""
    b = encode_chars(text)
    if len(b) > room:
        b = b[:room]
    return b + bytes([MAP[" "]]) * (room - len(b))


# the interpreter's tables: cmp al, 20h / jb +3 / jmp text / shl ax, 1 / mov bx, ax / jmp [bx+table]; and
# for FFh: lodsb / not al / shl ax, 1 / mov bx, ax / jmp [bx+table]
CTL_TABLE_SIG = re.compile(rb"\x3c\x20\x72\x03\xe9..\xd1\xe0\x8b\xd8\xff\xa7(..)", re.S)
FF_TABLE_SIG = re.compile(rb"\xac\xf6\xd0\xd1\xe0\x8b\xd8\xff\xa7(..)", re.S)
# the flags: a command's mov bx, flags / add bx, ax / lodsb / mov [bx], al
FLAGS_SIG = re.compile(rb"\xac\xbb(..)\x03\xd8\xac\x88\x07", re.S)
# the script load's base: mov ah, 0 / add al, base / int 49h
# (after mov word [x], 0)
BASE_SIG = re.compile(rb"\xc7\x06..\x00\x00\xb4\x00\x04(.)\xcd\x49", re.S)


def _handler_args(prog, a):
    """Bytes a command's handler reads from the script before it jumps on: its lodsb and lodsw, and a
    condition's 3 (mov cl, 1 / call)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    n = 0
    prev = None
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(prog[a:a + 80], a):
        if ins.mnemonic == "lodsb":
            n += 1
        elif ins.mnemonic == "lodsw":
            n += 2
        elif ins.mnemonic == "call" and prev == ("mov", "cl, 1"):
            n += 3
        if ins.mnemonic in ("jmp", "ret"):
            break
        prev = (ins.mnemonic, ins.op_str)
    return n


def grammar(prog):
    """{"ctl": {byte: arguments}, "ff": {code: arguments}} of a program's interpreter (03, 0D and FF FF
    read lists of their own)."""
    c = _one(CTL_TABLE_SIG, prog, "interpreter's command table")
    f = _one(FF_TABLE_SIG, prog, "interpreter's FFh table")
    ct, ft = struct.unpack("<H", c.group(1))[0], struct.unpack("<H", f.group(1))[0]
    ctl = {i: _handler_args(prog, struct.unpack_from("<H", prog, ct + 2 * i)[0]) for i in range(0x20)}
    ff = {0xFF - i: _handler_args(prog, struct.unpack_from("<H", prog, ft + 2 * i)[0]) for i in range(0x20)}
    return {"ctl": ctl, "ff": ff}


def flags_at(prog):
    return struct.unpack("<H", _one(FLAGS_SIG, prog, "flags").group(1))[0]


def script_base(prog):
    return _one(BASE_SIG, prog, "script load").group(1)[0]
