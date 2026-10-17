"""Misty Blue's bonus game (disk B: MAIN.EXE runs the .MES scripts): the scripts' text, and English
drawn half-width.

A script is read into the program's data segment at 2000h and run statement by statement (the
program's statement loop); the script itself puts its music at 3500h and its map at 4000h, so a
script keeps to its own length.

* 81h-98h and a byte: a two-byte Shift-JIS character, drawn from CG ROM (full width, two columns);
  8193h (％) a new line;
* 22h ... 22h: a quoted string, each byte drawn as a half-width glyph (one column);
* 99h-EFh: commands (7Bh/7Dh brace their blocks; A1h {a,b} a menu, its choices in boxes of a fixed
  width);
* 00h xx, 10h xx: a variable, a byte constant; 08h xx xx, 18h xx xx: a word constant; 40h-5Ah a
  variable letter; other bytes one each.

`texts` finds the runs of characters (`lex` reads the tokens).  B1h addr,{...} fills a string
buffer (16 bytes) from its block, run later as statements: a hero's or a monster's name.

English (`ref`, `patch_engine`): each run is replaced by a reference, a quoted string holding 01h
and the English's number (two bytes 23h-FEh, never a quote); the English itself is in a table put,
with a helper, after the program's image (pc98tl/exepack.py `pack`'s extra; the program's own block
has 128 KB unused past its image).  A name's block holds its reference with the quotes as byte
constants (10h 22h), so the buffer gets the reference, which the statement loop then draws.  The
program's string loop is made to go through the helper, which draws a referenced English ('|' a new
line), breaking a line before a word that would pass the window's right edge (and skipping a space
at a line's start); and the line feed's wrap to the window's top, while an English is being drawn,
is made to wait for the Return key and clear the window first (as the scripts' own A6h (wait) and
AAh (clear) do).  A reference's room past its number, up to its closing quote, is skipped (the
program's own texts are written as references in place, padded).
"""
import re
import struct

from . import exepack
from .misty import _asm16, _one

NEWLINE = b"\x81\x93"
REF = 0x01
REF_BASE, REF_SPAN = 0x23, 0xDC         # a number's bytes: 23h-FEh


def lex(data):
    """[(kind, start, end)]: kind text (a two-byte character), str (a quoted string), or tok."""
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if 0x81 <= b <= 0x98 and i + 1 < len(data):
            n, kind = 2, "text"
        elif b == 0x22:
            e = data.find(b'"', i + 1)
            n, kind = (e + 1 - i if e >= 0 else len(data) - i), "str"
        elif b in (0x00, 0x10):
            n, kind = 2, "tok"
        elif b in (0x08, 0x18):
            n, kind = 3, "tok"
        else:
            n, kind = 1, "tok"
        out.append((kind, i, min(i + n, len(data))))
        i += n
    return out


def texts(data):
    """[(start, end, kind)] of the runs of characters: kind name (in a B1h block), choice (in an A1h
    menu's block) or msg."""
    out, run, depth, block, want = [], None, 0, None, None
    for kind, s, e in lex(data):
        if kind == "text":
            run = (run[0], e) if run else (s, e)
            continue
        if run:
            out.append((run[0], run[1], block[1] if block else "msg"))
            run = None
        if kind != "tok":
            continue
        b = data[s]
        if b in (0xB1, 0xA1) and block is None:
            want = "name" if b == 0xB1 else "choice"     # its block is the next one
        elif b == 0x7B:
            depth += 1
            if want:
                block, want = (depth, want), None
        elif b == 0x7D:
            if block and block[0] == depth:
                block = None
            depth -= 1
    if run:
        out.append((run[0], run[1], "msg"))
    return [(s, e, k) for s, e, k in out if data[s:e].replace(NEWLINE, b"")]


def show(b):
    return b.decode("cp932", "replace").replace("％", "\n")


def cols(b):
    """A run's columns: a character two."""
    return len(b)


def _ascii(text):
    subst = {"’": "'", "‘": "'", "“": "'", "”": "'", '"': "'", "—": "-", "–": "-", "…": "...", "|": "/"}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if c == "\n" or 0x20 <= ord(c) < 0x7F else "?" for c in s)


def ascii_text(text, newline=" "):
    """English as single bytes (the text screen's, DOS's or the table's letters)."""
    return _ascii(text).replace("\n", newline).encode("ascii")


def ref(n, room=0):
    """English number n as a script holds it: a quoted string, 01h and the number (padded to `room`
    bytes)."""
    if n >= REF_SPAN * REF_SPAN:
        raise SystemExit("Misty Blue (disk B): %d English texts, the references hold %d" % (n + 1, REF_SPAN ** 2))
    b = bytes([0x22, REF, REF_BASE + n % REF_SPAN, REF_BASE + n // REF_SPAN])
    return b + b" " * max(0, room - len(b) - 1) + b'"'


def name(n):
    """A name's reference as its B1h block holds it: the quotes as byte constants (10h 22h)."""
    return b'\x10"' + ref(n) + b'\x10"'


def rebuild(data, new):
    """`data` with each run {start: (end, bytes)} replaced."""
    out, last = bytearray(), 0
    for s in sorted(new):
        e, b = new[s]
        out += data[last:s] + b
        last = e
    return bytes(out + data[last:])


# --- the program ---------------------------------------------------------------------------------

# the string statement: inc si / lodsb / cmp al, '"' / jne draw / jmp loop
QUOTE_SIG = re.compile(rb"\x46\xac\x3c\x22\x75\x03\xe9(..)", re.S)
# the line feed: x = left; y += line height; past the bottom: y = top
LINEFEED_SIG = re.compile(rb"\xa1(..)\xa3(..)\xa1(..)\x03\x06(..)\x3b\x06(..)\x73\x04\xa3..\xc3"
                          rb"\xa1(..)\xa3..\xc3", re.S)
# the column step: x == right? line feed : x++
STEP_SIG = re.compile(rb"\xa1(..)\x3b\x06(..)\x74\x05\x40\xa3..\xc3", re.S)
# A6h's wait: the frame's work, then Return pressed and let go (key group 6 or 3 by a setting)
WAIT_SIG = re.compile(rb"\xe8(..)\xe8(..)\x80\x3e(..)\x02\x75\x1a\xb8\x06\x04\xcd\x18\xf6\xc4\x10"
                      rb"\x74.\xb8\x06\x04\xcd\x18\xf6\xc4\x10\x75.\xe8(..)", re.S)
# AAh's clear: the window's box filled with the background colour
CLEAR_SIG = re.compile(rb"\x8a\x36(..)\xeb\x05\xe8..\x8a\xf0\x52\x8b\x1e..\x8b\x16..\xe8(..)\x5a\x8b\x1e..\x2b\x1e..\x43"
                       rb"\x8b\x0e..\x2b\x0e..\x41\x8b\xc1\x83\x3e(..)\x00\x74\x02\x03\xc0\x8b\xc8"
                       rb"\xe8(..)", re.S)
# the string statement's double-width setting: cmp byte [w], 0 (after the glyph's place)
WIDE_SIG = re.compile(rb"\x58\x80\x3e(..)\x00\x75\x08", re.S)

VARS = ["v_on", "v_far", "v_last", "v_ptr"]
HELPER = """
v_on: .byte 0
v_far: .byte 0
v_last: .byte 0
v_ptr: .word 0
q_loop:
    cmp byte ptr cs:[{v_far}], 0
    jne q_far
    lodsb
    cmp al, 0x22
    jne q_ref
q_end:
    mov byte ptr cs:[{v_on}], 0
    JMPN {loop}
q_ref:
    cmp al, {ref}
    jne q_plain
    cmp byte ptr [si - 2], 0x22
    jne q_plain
    lodsb
    sub al, {base}
    mov cl, al
    lodsb
    sub al, {base}
    mov ah, 0
    mov dx, {span}
    mul dx
    mov ch, 0
    add ax, cx
    shl ax, 1
    mov bx, ax
    mov ax, word ptr cs:[bx + {table}]
    mov word ptr cs:[{v_ptr}], ax
    mov byte ptr cs:[{v_far}], 1
    mov byte ptr cs:[{v_on}], 1
    mov byte ptr cs:[{v_last}], 0x20
    jmp q_loop
q_plain:
    JMPN {draw}
q_again:
    jmp q_loop
q_far:
    mov bx, word ptr cs:[{v_ptr}]
    mov al, byte ptr cs:[bx]
    inc word ptr cs:[{v_ptr}]
    or al, al
    jne q_ch
    mov byte ptr cs:[{v_far}], 0
q_skip:
    lodsb
    cmp al, 0x22
    jne q_skip
    jmp q_end
q_ch:
    mov ah, byte ptr cs:[{v_last}]
    mov byte ptr cs:[{v_last}], al
    cmp al, 0x7c
    jne q_sp
    CALLN {linefeed}
    jmp q_again
q_sp:
    cmp al, 0x20
    jne q_wd
    mov bx, word ptr [{x}]
    cmp bx, word ptr [{left}]
    je q_again
    JMPN {draw}
q_wd:
    cmp ah, 0x20
    je q_chk
    cmp ah, 0x7c
    je q_chk
    JMPN {draw}
q_chk:
    push ax
    mov bx, word ptr cs:[{v_ptr}]
    dec bx
    xor cx, cx
q_len:
    mov ah, byte ptr cs:[bx]
    cmp ah, 0x20
    je q_e
    cmp ah, 0x7c
    je q_e
    or ah, ah
    je q_e
    inc cx
    inc bx
    jmp q_len
q_e:
    cmp byte ptr [{wide}], 0
    je q_one
    shl cx, 1
q_one:
    mov ax, word ptr [{x}]
    cmp ax, word ptr [{left}]
    je q_ok
    add ax, cx
    dec ax
    cmp ax, word ptr [{right}]
    jbe q_ok
    CALLN {linefeed}
q_ok:
    pop ax
    JMPN {draw}
p_chk:
    cmp byte ptr cs:[{v_on}], 0
    je p_top
    CALLN page
p_top:
    mov ax, word ptr [{top}]
    mov word ptr [{y}], ax
    .byte 0xc3
page:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
pw1:
    CALLN {frame1}
    CALLN {frame2}
    cmp byte ptr [{keyset}], 2
    jne pk3
    mov ax, 0x406
    int 0x18
    test ah, 0x10
    je pw1
pw2:
    mov ax, 0x406
    int 0x18
    test ah, 0x10
    jne pw2
    jmp pwd
pk3:
    mov ax, 0x403
    int 0x18
    test ah, 0x10
    je pw1
pw4:
    mov ax, 0x403
    int 0x18
    test ah, 0x10
    jne pw4
pwd:
    CALLN {waited}
    mov dh, byte ptr [{bg}]
    push dx
    mov bx, word ptr [{left}]
    mov dx, word ptr [{top}]
    CALLN {place}
    pop dx
    mov bx, word ptr [{right}]
    sub bx, word ptr [{left}]
    inc bx
    mov cx, word ptr [{bottom}]
    sub cx, word ptr [{top}]
    inc cx
    mov ax, cx
    cmp word ptr [{tall}], 0
    je pc1
    add ax, ax
pc1:
    mov cx, ax
    CALLN {fill}
    mov ax, word ptr [{left}]
    mov word ptr [{x}], ax
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    .byte 0xc3
"""


def _w(m, n):
    return struct.unpack("<H", m.group(n))[0]


def _rel(m, n, at):
    """The target of a near call/jump whose rel16 is group n, the instruction ending at `at`."""
    return (at + _w(m, n)) & 0xFFFF


def code_segment(exe):
    plain = exepack.unpack(exe)
    h = struct.unpack_from("<14H", plain, 0)
    image = plain[h[4] * 16:]
    return plain, image, h[11] * 16


def table_bytes(english):
    """The English as the helper reads it: each one's place (a word each, from the table's start
    `at`, filled in by `patch_engine`), then each one's letters and a 0."""
    return [ascii_text(t, "|") + b"\0" for t in english]


def patch_engine(exe, english):
    """Disk B's MAIN.EXE with the helper and the table of `english` (still EXEPACK-packed)."""
    _plain, image, cs = code_segment(exe)
    img = bytearray(image)
    seg = bytes(img[cs:])
    q = _one(QUOTE_SIG, seg, "string statement")[0]
    lf = _one(LINEFEED_SIG, seg, "line feed")[0]
    st = _one(STEP_SIG, seg, "column step")[0]
    wt = _one(WAIT_SIG, seg, "key wait")[0]
    cl = _one(CLEAR_SIG, seg, "window clear")[0]
    wd = _one(WIDE_SIG, seg[q.start():q.start() + 0x40], "double width")[0]
    base = len(img) - cs
    var = {k: base + n for n, k in enumerate(VARS)}
    w, c = wt.start(), cl.start()

    def build(table):
        src = HELPER.format(
            loop=hex(_rel(q, 1, q.start() + 9)), draw=hex(q.start() + 9), linefeed=hex(lf.start()),
            x=hex(_w(lf, 2)), left=hex(_w(lf, 1)), y=hex(_w(lf, 4)), top=hex(_w(lf, 6)), bottom=hex(_w(lf, 5)),
            right=hex(_w(st, 2)), wide=hex(_w(wd, 1)), ref=hex(REF), base=hex(REF_BASE), span=REF_SPAN,
            table=hex(table), frame1=hex(_rel(wt, 1, w + 3)), frame2=hex(_rel(wt, 2, w + 6)),
            keyset=hex(_w(wt, 3)), waited=hex(_rel(wt, 4, wt.end())), bg=hex(_w(cl, 1)),
            place=hex(_rel(cl, 2, c + 0x17)), tall=hex(_w(cl, 3)), fill=hex(_rel(cl, 4, cl.end())),
            **{k: hex(v) for k, v in var.items()})
        return _asm16(src, base, ["q_loop", "p_chk"] + VARS)

    code, addr = build(0x1000)
    table = base + len(code)
    code, addr = build(table)
    if any(addr[k] != v for k, v in var.items()):
        raise SystemExit("Misty Blue (disk B): the helper's variables are not where they were taken to be")
    body = table_bytes(english)
    places, at = bytearray(), table + 2 * len(body)
    for b in body:
        places += struct.pack("<H", at)
        at += len(b)
    if at > 0xFFF0:
        raise SystemExit("Misty Blue (disk B): the English takes %d bytes, the program's segment has %d; "
                         "shorten the bonus game's English" % (at - table, 0xFFF0 - table))
    extra = bytearray(code + places + b"".join(body))
    extra += bytes(-len(extra) % 16)
    # the string statement's loop (after its inc si) goes to the helper
    k = q.start() + 1
    img[cs + k:cs + k + 8] = b"\xe9" + struct.pack("<H", (addr["q_loop"] - (k + 3)) & 0xFFFF) + b"\x90" * 5
    # the line feed's wrap to the window's top
    k = lf.end() - 7
    img[cs + k:cs + k + 7] = b"\xe9" + struct.pack("<H", (addr["p_chk"] - (k + 3)) & 0xFFFF) + b"\x90" * 4
    return exepack.pack(exe, bytes(img), bytes(extra))
