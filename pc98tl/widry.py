"""Starcraft's Wizard and the Princess (WIDRY): its messages, and English at any length.

The disk is N88-DISK BASIC (pc98tl/n88disk.py); M98 (a protected BASIC program, pc98tl/n88prog.py)
BLOADs the engine WIDRY.ASM (a BSAVE image) into segment 1800h at 2100h and calls it.  The engine reads
a room's record (0A00h bytes) from RDA, a second record from MDA, by absolute sectors, into 1800h:0
(and 0A00h); a record's messages are runs "01h text 0", found by their order (`strings`).  The
engine prints a message (or one of its own, a span it names by two pointers: `engine_spans`) through
its span printer (`PRINT_SIG`): the span's start and end in two words, a new line first when the span
would pass column 79, the span itself sent to BASIC's console (int C4h) in one piece, a key waited for
after four lines.  A few of its own strings it prints with a length of its own (`engine_fixed`).

English at any length (`pool`, `patch_engine`): the span printer is made to jump to a helper put after
the engine (1800h:5100h), which looks the span's Japanese up in a table BLOADed by M98 at 3000h:0,
keyed by its length and two sums of its bytes (up to its first 0): a span with English is printed a
word at a time through the printer's own path (each word with its space, so the printer breaks lines
between words; \\n a new line), any other as it was.  The data stay as they are: the parser still
matches what the player types against the game's own words.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .illusion_font import _asm

POOL = 0x3000
HELPER_AT = 0x5100
SCRATCH = 0x5400
TEXT = frozenset(list(range(0x20, 0x7F)) + list(range(0xA1, 0xE0)))


def bsave(data):
    start, end = struct.unpack_from("<HH", data, 0)
    return start, data[4:4 + end - start]


def make_bsave(start, body):
    return struct.pack("<HH", start, start + len(body)) + body


def _kana(t):
    return any(0xA6 <= c <= 0xDF for c in t)


def strings(data):
    """[(start, end)] of a data file's messages: 01h, text, 0 (start..end the text)."""
    out = []
    for m in re.finditer(b"\x01([\x20-\x7e\xa1-\xdf]+)\x00", data):
        if _kana(m.group(1)):
            out.append(m.span(1))
    return out


RECORD = 0xA00
DESCRIPTION = 0x500
CHUNK = 0x4E


def descriptions(data):
    """[(start, end)] of a data file's room descriptions: each record's text at 500h, up to its 0 (the
    engine prints it in chunks of 78 bytes)."""
    out = []
    for r in range(0, len(data) - RECORD + 1, RECORD):
        s = r + DESCRIPTION
        e = data.find(b"\0", s, r + RECORD)
        if e > s and _kana(data[s:e]) and all(c in TEXT for c in data[s:e]):
            out.append((s, e))
    return out


def chunks(jp):
    """The pieces the engine prints a description in."""
    return [jp[k:k + CHUNK] for k in range(0, len(jp), CHUNK)]


SPAN_SIG = re.compile(b"\xb8(..)\xa3\xb7\x21\xb8(..)\xa3\xb9\x21", re.S)
FIXED_SIG = re.compile(b"\xbe(..)\xb9(..)\xe8", re.S)


def engine_spans(eng):
    """[(address, end)] of the engine's own messages printed by the span printer: mov ax, start /
    mov [start], ax / mov ax, end / mov [end], ax."""
    org, body = bsave(eng)
    out = []
    for m in SPAN_SIG.finditer(body):
        s, e = struct.unpack("<H", m.group(1))[0], struct.unpack("<H", m.group(2))[0]
        if org <= s < e <= org + len(body) and _kana(body[s - org:e - org]):
            out.append((s, e))
    return sorted(set(out))


def engine_fixed(eng):
    """[(address, length)] of the engine's strings printed with a length of their own: mov si, start /
    mov cx, length / call print."""
    org, body = bsave(eng)
    out = []
    for m in FIXED_SIG.finditer(body):
        s, n = struct.unpack("<H", m.group(1))[0], struct.unpack("<H", m.group(2))[0]
        t = body[s - org:s - org + n] if org <= s < org + len(body) else b""
        if 0 < n < 200 and len(t) == n and _kana(t) and all(c in TEXT for c in t):
            out.append((s, n))
    return sorted(set(out))


def key(b):
    """(length, sum, rotating sum) of a span's bytes up to its first 0."""
    t = b.split(b"\0", 1)[0]
    s1 = sum(t) & 0xFFFF
    s2 = 0
    for c in t:
        s2 = (((s2 << 1) | (s2 >> 15)) & 0xFFFF) ^ c
    return len(t), s1, s2


def encode(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
             "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    return bytes(ord(c) if 0x20 <= ord(c) < 0x7F or c == "\n" else ord("?") for c in s)


def pool(entries):
    """The table (BSAVE at POOL:0): a count, then (length, sum, rotating sum, place) for each span, then
    the English, each ended by a 0 (a new line a 0Ah).  entries: [(Japanese bytes, English bytes)]."""
    rows = {}
    for jp, en in entries:
        k = key(jp)
        if k in rows and rows[k][0] != jp.split(b"\0", 1)[0]:
            raise SystemExit("WIDRY: two messages share a key; the table cannot tell them apart")
        rows[k] = (jp.split(b"\0", 1)[0], en)
    head = 2 + 8 * len(rows)
    out = bytearray(struct.pack("<H", len(rows)))
    text = bytearray()
    for k in sorted(rows):
        out += struct.pack("<HHHH", k[0], k[1], k[2], head + len(text))
        text += rows[k][1] + b"\0"
    out += text
    if len(out) > 0xFFF0:
        raise SystemExit("WIDRY: the English takes %d bytes, a segment holds 65520" % len(out))
    return make_bsave(0, bytes(out))


# the span printer: mov al, [flag] / cmp al, FEh / jb words / (the new-line path)
PRINT_SIG = re.compile(b"\xa0(..)\x3c\xfe\x72(.)\xbb..\x8b\x07", re.S)
# the printer's new line: mov al, [lines] / inc al / mov [lines], al / cmp al, 4
NEWLINE_SIG = re.compile(b"\xa0(..)\xfe\xc0\xa2..\x3c\x04", re.S)

HELPER = """
hook:
    mov al, byte ptr [{flag}]
    cmp al, 0xfe
    jb h_look
    JMPN {cont}
h_look:
    push es
    push si
    push di
    push cx
    push dx
    push bx
    mov si, word ptr [{sstart}]
    mov cx, word ptr [{send}]
    sub cx, si
    xor bx, bx
    xor dx, dx
    xor di, di
h_sum:
    jcxz h_summed
    mov al, byte ptr [si]
    or al, al
    jz h_summed
    xor ah, ah
    add bx, ax
    rol dx, 1
    xor dl, al
    inc si
    inc di
    dec cx
    jmp h_sum
h_summed:
    mov ax, {pool}
    mov es, ax
    mov cx, word ptr es:[0]
    mov si, 2
h_find:
    jcxz h_none
    cmp di, word ptr es:[si]
    jne h_next
    cmp bx, word ptr es:[si + 2]
    jne h_next
    cmp dx, word ptr es:[si + 4]
    je h_found
h_next:
    add si, 8
    dec cx
    jmp h_find
h_none:
    pop bx
    pop dx
    pop cx
    pop di
    pop si
    pop es
    JMPN {words}
h_found:
    mov si, word ptr es:[si + 6]
h_word:
    mov di, {scratch}
h_copy:
    mov al, byte ptr es:[si]
    or al, al
    jz h_last
    cmp al, 0x0a
    je h_break
    inc si
    mov byte ptr [di], al
    inc di
    cmp al, 0x20
    jne h_copy
    CALLN h_print
    jmp h_word
h_break:
    inc si
    CALLN h_print
    push es
    push si
    CALLN {newline}
    pop si
    pop es
    jmp h_word
h_last:
    CALLN h_print
    pop bx
    pop dx
    pop cx
    pop di
    pop si
    pop es
    .byte 0xc3
h_print:
    cmp di, {scratch}
    je h_p_none
    mov word ptr [{sstart}], {scratch}
    mov word ptr [{send}], di
    push es
    push si
    CALLN {words}
    pop si
    pop es
h_p_none:
    .byte 0xc3
"""


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
    names = [t for t, _o, _x in fix] + sorted({x for _t, _o, x in fix if not x.startswith("0x")}) + ["hook"]
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org, sorted(set(names)))
    code = bytearray(code)
    for tag, op, target in fix:
        to = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = (b"\xe8" if op == "CALLN" else b"\xe9") + ((to - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("WIDRY: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def _one(sig, data, what):
    found = list(sig.finditer(data))
    if len(found) != 1:
        raise SystemExit("WIDRY.ASM: the %s's signature is found %d times, not once" % (what, len(found)))
    return found[0]


def patch_engine(eng):
    """The engine with its span printer jumping to the helper (put after it, the image made longer)."""
    org, body = bsave(eng)
    body = bytearray(body)
    p = _one(PRINT_SIG, body, "span printer")
    nl = _one(NEWLINE_SIG, body, "printer's new line")
    word = lambda m, k: struct.unpack("<H", m.group(k))[0]  # noqa: E731
    at = org + p.start()
    words = (at + 7 + struct.unpack("<b", p.group(2))[0]) & 0xFFFF
    # (the printer's new line starts at the instruction before its line count: the routine's entry)
    newline = org + nl.start()
    # the span's start and end: the words the printer's span path reads (mov bx, [start] / mov cx, [end])
    m = re.search(b"\x8b\x1e(..)\x8b\x0e(..)[\x2b]\xcb", bytes(body[words - org:words - org + 40]), re.S)
    if not m:
        raise SystemExit("WIDRY.ASM: the span printer's words are not laid out as expected")
    if org + len(body) > HELPER_AT:
        raise SystemExit("WIDRY.ASM: the engine runs past %Xh" % HELPER_AT)
    src = HELPER.format(flag=hex(word(p, 1)), cont=hex(at + 7), sstart=hex(word(m, 1)), send=hex(word(m, 2)),
                        pool=hex(POOL), words=hex(words), newline=hex(newline), scratch=hex(SCRATCH))
    code, addr = _asm16(src, HELPER_AT)
    if HELPER_AT + len(code) > SCRATCH:
        raise SystemExit("WIDRY: the helper runs into its scratch buffer")
    body[p.start():p.start() + 7] = b"\xe9" + struct.pack("<H", (HELPER_AT - (at + 3)) & 0xFFFF) + b"\x90" * 4
    body += bytes(HELPER_AT - (org + len(body))) + code
    return make_bsave(org, bytes(body))
