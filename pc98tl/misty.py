"""Enix's Misty Blue: the scenario's text bundles (*.BUN), their text code, and English drawn half-width.

The game boots its own DOS (ENIX.DOS) and runs MAIN.EXE (EXEPACK, pc98tl/exepack.py; disks A and C
each have their own), which loads scene modules and, for each scene, a text bundle into its data
segment at B000h (room up to FC00h, `BUNDLE_ROOM`).  A bundle is records, each a length (a word) and
the record; the scene code finds a record by counting.  A record is controls and text: a control is a
byte below 20h or FFh (01 a new page, its parameters, 02 the end; bytes 05h-1Fh are never text), the
text is drawn by the engine's text routine (`text`), one character a byte or two:

* 20h-48h: JIS row 21h (punctuation), column b+1;
* 49h-AAh: two bytes, Shift-JIS (lead, trail);
* ABh-FEh: hiragana (JIS row 24h, column b-0Ch-7Eh), or katakana after 86h (until 85h);
* 6Ch: a new line; 85h, 86h: hiragana, katakana.

The routine wraps at its window's width (a cell a character) and draws each glyph from CG ROM by its
JIS code (`DRAW_ROW_SIG`).

English (`encode`, `patch_main`): two letters a cell, as two-byte codes whose lead is 49h-6Bh (bytes
no Japanese uses): the decoder's two-byte path is made to go through a helper that marks the cell as
a pair, and the glyph drawer to draw it from two 8x16 BIOS glyphs (int 18h, AH=14h) instead of CG
ROM.  Words are padded to whole cells (a word and its space an even number of letters), and the
helper breaks a line before a word that would pass the window's edge.  The English's most frequent
words (`dictionary`) are a code each: the helper copies the word's pairs to the data segment's free
room (`SCRATCH`), reads them there and comes back (the bundles must fit B000h-FC00h).  The helper and
the dictionary are put after the program's image, in its code segment's unused end (the image made
longer, pc98tl/exepack.py).
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .illusion_font import _asm
from . import exepack

BUNDLE_ROOM = 0x4C00
LETTERS = (" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
           ".,'\"!?-:;()")
PAIR_LEAD = 0x49
PAIR_LEADS = 35                     # 49h-6Bh
TRAILS = [t for t in range(0x40, 0xFD) if t != 0x7F]    # 188
PAIRS = len(LETTERS) ** 2           # codes 0..PAIRS-1: two letters
RET = PAIR_LEADS * len(TRAILS) - 1  # the last code: back from a dictionary word
WORDS = RET - PAIRS                 # codes PAIRS..RET-1: dictionary words
SCRATCH = 0xA000                    # (the data segment's 9C00h-AC00h is unused) a word's pairs
NEWLINE = 0x6C
KATA, HIRA = 0x86, 0x85


# --- bundles -------------------------------------------------------------------------------------

def records(data):
    """[record bytes] of a bundle (up to its zero padding)."""
    out, p = [], 0
    while p + 2 <= len(data):
        n = struct.unpack_from("<H", data, p)[0]
        if n == 0:
            break
        out.append(data[p + 2:p + 2 + n])
        p += 2 + n
    return out


def bundle(recs, size=0):
    """A bundle of records, padded with zeros to its old size, or to whole 256-byte units less 4 (the
    files' sizes) when it grows."""
    out = bytearray()
    for r in recs:
        out += struct.pack("<H", len(r)) + r
    out += bytes(2)
    pad = size if len(out) <= size else -(-(len(out) + 4) // 256) * 256 - 4
    return bytes(out + bytes(pad - len(out)))


def _is_ctl(c):
    return c < 0x20 or c == 0xFF


def pieces(rec):
    """[(kind, bytes)] of a record: "ctl" (controls and their parameters) and "text"."""
    out, i = [], 0
    while i < len(rec):
        j = i
        if _is_ctl(rec[i]):
            while j < len(rec) and _is_ctl(rec[j]):
                j += 1
            out.append(("ctl", rec[i:j]))
        else:
            while j < len(rec) and not _is_ctl(rec[j]):
                j += 2 if PAIR_LEAD <= rec[j] < 0xAB and rec[j] not in (NEWLINE, KATA, HIRA) else 1
            j = min(j, len(rec))
            out.append(("text", rec[i:j]))
        i = j
    return out


# --- the text code ---------------------------------------------------------------------------------

def _jis_to_sjis(r, c):
    s1 = (r + 1) // 2 + (0x70 if r <= 0x5E else 0xB0)
    if r % 2:
        s2 = c + 0x1F + (1 if c + 0x1F >= 0x7F else 0)
    else:
        s2 = c + 0x7E
    return bytes([s1, s2])


def _jis(b, kata):
    """The JIS code the decoder makes of a one-byte character (its own arithmetic)."""
    if b < 0x49:
        dh, al = 0x21, b + 0x20
    elif kata:
        dh, al = 0x25, (b - 0x0C - 0x5F) & 0xFF
    else:
        dh, al = 0x23, b - 0x0C
    if al >= 0x9F:
        return dh + 1, al - 0x7E
    if al & 0x80:
        al -= 1
    return dh, al - 0x1F


def show(text):
    """The text as the screen shows it; a new line as \\n."""
    out, i, kata = [], 0, False
    while i < len(text):
        b = text[i]
        i += 1
        if b == NEWLINE:
            out.append("\n")
        elif b == KATA:
            kata = True
        elif b == HIRA:
            kata = False
        elif b < 0x49 or b >= 0xAB:
            out.append(_jis_to_sjis(*_jis(b, kata)).decode("cp932", "replace"))
        else:
            out.append(bytes([b, text[i]]).decode("cp932", "replace"))
            i += 1
    return "".join(out)


def _code(k):
    lead, trail = divmod(k, len(TRAILS))
    return bytes([PAIR_LEAD + lead, TRAILS[trail]])


def _normal(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if c in LETTERS or c == "\n" else "?" for c in s)


def tokens(line):
    """A line's letters in cells' worth: the leading spaces (even), then each word with the space
    after it, padded to an even number of letters (so each word starts a cell)."""
    lead = len(line) - len(line.lstrip(" "))
    out = [" " * (lead + lead % 2)] if lead else []
    for word in re.findall(r"\S+\s*", line):
        w = word.rstrip(" ") + " "
        out.append(w + " " * (len(w) % 2))
    if out:
        last = out[-1].rstrip(" ")
        out[-1] = last + " " * (len(last) % 2)
    return [t for t in out if t]


def _pairs(t):
    return b"".join(_code(LETTERS.index(t[k]) * len(LETTERS) + LETTERS.index(t[k + 1]))
                    for k in range(0, len(t), 2))


def dictionary(texts):
    """[word token] of the English's most frequent words (each worth more than its code), at most
    WORDS of them."""
    count = {}
    for text in texts:
        for line in _normal(text).split("\n"):
            for t in tokens(line):
                if len(t) >= 4 and t.endswith(" "):
                    count[t] = count.get(t, 0) + 1
    ranked = sorted(count, key=lambda t: (-(count[t] * (len(t) - 2)), t))
    return [t for t in ranked if count[t] > 1][:WORDS]


def encode(text, words=()):
    """English as the bundle holds it: letters two a cell (`_pairs`), a word of `words` (the
    dictionary) one code; \\n a new line; anything outside LETTERS written as '?'."""
    index = {t: n for n, t in enumerate(words)}
    out = bytearray()
    for n, line in enumerate(_normal(text).split("\n")):
        if n:
            out.append(NEWLINE)
        for t in tokens(line):
            out += _code(PAIRS + index[t]) if t in index else _pairs(t)
    return bytes(out)


def pairs(text):
    """English as letters two a cell, without the dictionary (the program's prompts)."""
    return encode(text)


def dictionary_bytes(words):
    """The dictionary as the helper reads it: a word's place (a word each), then each word: its
    length in bytes, its pairs."""
    table, body = bytearray(), bytearray()
    head = 2 * len(words)
    for t in words:
        table += struct.pack("<H", head + len(body))
        b = _pairs(t)
        body += bytes([len(b)]) + b
    return bytes(table + body)


# --- the program ---------------------------------------------------------------------------------

# the decoder's loop: mov al, [bx] / cmp al, 5 / jae / ret / inc bx / cmp al, 6Ch
LOOP_SIG = re.compile(rb"\x8a\x07\x3c\x05\x73\x01\xc3\x43\x3c\x6c", re.S)
# the decoder's two-byte path: mov dl, [bx] / inc bx / cmp al, 97h / jne
PAIR_SIG = re.compile(rb"\x8a\x17\x43\x3c\x97\x75", re.S)
# the line's end: mov bx, [line start] / mov cx, [stride] / add bx, cx / mov [cursor], bx
NEWLINE_SIG = re.compile(rb"\x53\x8b\x1e(..)\x8b\x0e(..)\x03\xd9\x89\x1e(..)[\x5b]\xe9", re.S)
# the line's room: mov al, [left] / dec al / dec al / mov [left], al
LEFT_SIG = re.compile(rb"\xa0(..)\xfe\xc8\xfe\xc8\xa2..\x78", re.S)
# the glyph drawer: sub ax, 2000h / out A1h, al / mov al, ah / out A3h, al
DRAW_START_SIG = re.compile(rb"\x2d\x00\x20\xe6\xa1\x8a\xc4\xe6\xa3")
# a row: the left half (port A5h the row) and the right (row | 20h) from port A9h
DRAW_ROW_SIG = re.compile(rb"\xb0\x10\x2a\xc1\xe6\xa5\xe4\xa9\x8a\xe0\xb0\x10\x2a\xc1\x0c\x20\xe6\xa5\xe4\xa9")

HELPER = """
v_pf: .byte 0
v_act: .byte 0
v_lead: .byte 0
v_trail: .byte 0
v_prev: .byte 0
v_pad: .byte 0
v_saved: .word 0
pair:
    cmp al, 0x49
    jb p_orig
    cmp al, 0x6c
    jb p_go
p_orig:
    mov byte ptr cs:[{v_prev}], 0
    mov dl, byte ptr [bx]
    inc bx
    cmp al, 0x97
    JMPN {cont}
p_go:
    mov dl, byte ptr [bx]
    inc bx
    push ax
    push cx
    push si
    push di
    mov ah, al
    mov al, dl
    CALLN index
    cmp ax, {ret}
    jne p_code
    mov bx, word ptr cs:[{v_saved}]
    mov byte ptr cs:[{v_prev}], 1
    pop di
    pop si
    pop cx
    pop ax
    JMPN {loop}
p_code:
    mov si, ax
    mov cx, ax
    mov al, byte ptr [{left}]
    cmp al, byte ptr [{width}]
    je p_fits
    cmp cx, {pairs}
    jae p_check
    cmp byte ptr cs:[{v_prev}], 0
    je p_fits
p_check:
    push bx
    push si
    sub bx, 2
    CALLN cells
    pop si
    pop bx
    shl cx, 1
    mov al, byte ptr [{left}]
    xor ah, ah
    cmp cx, ax
    jbe p_fits
    pop di
    pop si
    pop cx
    pop ax
    sub bx, 2
    mov byte ptr cs:[{v_prev}], 0
    JMPN {newline}
p_fits:
    cmp si, {pairs}
    jae p_word
    mov ax, si
    xor dx, dx
    mov cx, {nletter}
    div cx
    mov byte ptr cs:[{v_prev}], 0
    or dx, dx
    jnz p_sp
    mov byte ptr cs:[{v_prev}], 1
p_sp:
    mov byte ptr cs:[{v_lead}], al
    mov byte ptr cs:[{v_trail}], dl
    mov byte ptr cs:[{v_pf}], 1
    pop di
    pop si
    pop cx
    pop ax
    mov dx, 0x2121
    JMPN {draw}
p_word:
    sub si, {pairs}
    shl si, 1
    mov si, word ptr cs:[si + {dict}]
    add si, {dict}
    xor cx, cx
    mov cl, byte ptr cs:[si]
    inc si
    mov di, {scratch}
p_copy:
    mov al, byte ptr cs:[si]
    mov byte ptr [di], al
    inc si
    inc di
    loop p_copy
    mov byte ptr [di], {ret_lead}
    mov byte ptr [di + 1], {ret_trail}
    mov word ptr cs:[{v_saved}], bx
    mov bx, {scratch}
    mov byte ptr cs:[{v_prev}], 0
    pop di
    pop si
    pop cx
    pop ax
    JMPN {loop}
index:
    push bx
    push dx
    push cx
    mov bl, ah
    sub bl, 0x49
    xor bh, bh
    mov cx, {ntrail}
    mov dx, bx
    mov bx, ax
    mov ax, dx
    mul cx
    mov dl, bl
    xor dh, dh
    sub dl, 0x40
    cmp bl, 0x7f
    jb ix_t
    dec dl
ix_t:
    add ax, dx
    pop cx
    pop dx
    pop bx
    .byte 0xc3
cells:
    xor cx, cx
c_next:
    mov al, byte ptr [bx]
    cmp al, 0x49
    jb c_done
    cmp al, 0x6c
    jae c_done
    mov ah, al
    mov al, byte ptr [bx + 1]
    add bx, 2
    CALLN index
    cmp ax, {ret}
    je c_done
    cmp ax, {pairs}
    jae c_word
    inc cx
    xor dx, dx
    push cx
    mov cx, {nletter}
    div cx
    pop cx
    or dx, dx
    jz c_done
    jmp c_next
c_word:
    sub ax, {pairs}
    shl ax, 1
    mov si, ax
    mov si, word ptr cs:[si + {dict}]
    add si, {dict}
    mov al, byte ptr cs:[si]
    shr al, 1
    xor ah, ah
    add cx, ax
c_done:
    .byte 0xc3
start:
    mov byte ptr cs:[{v_act}], 0
    cmp byte ptr cs:[{v_pf}], 0
    je st_x
    mov byte ptr cs:[{v_pf}], 0
    mov byte ptr cs:[{v_act}], 1
    push ax
    push bx
    push cx
    push dx
    mov bl, byte ptr cs:[{v_lead}]
    xor bh, bh
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov cx, {g1}
    mov bx, cs
    mov ah, 0x14
    int 0x18
    mov bl, byte ptr cs:[{v_trail}]
    xor bh, bh
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov cx, {g2}
    mov bx, cs
    mov ah, 0x14
    int 0x18
    pop dx
    pop cx
    pop bx
    pop ax
st_x:
    sub ax, 0x2000
    .byte 0xc3
row:
    cmp byte ptr cs:[{v_act}], 0
    jne r_pair
    mov al, 0x10
    sub al, cl
    out 0xa5, al
    in al, 0xa9
    mov ah, al
    mov al, 0x10
    sub al, cl
    or al, 0x20
    out 0xa5, al
    in al, 0xa9
    .byte 0xc3
r_pair:
    push si
    mov al, 0x10
    sub al, cl
    xor ah, ah
    mov si, ax
    mov al, byte ptr cs:[si + {g1} + 2]
    mov ah, byte ptr cs:[si + {g2} + 2]
    pop si
    .byte 0xc3
"""

VARS = ["v_pf", "v_act", "v_lead", "v_trail", "v_prev", "v_pad", "v_saved"]


def _asm16(src, org, want=()):
    lines, fix = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("JMPN "):
            tag = "__j%d" % len(fix)
            fix.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    names = list(want) + [t for t, _x in fix]
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org, list(dict.fromkeys(names)))
    code = bytearray(code)
    for tag, target in fix:
        to = int(target, 16)
        at = addr[tag] - org
        code[at:at + 3] = b"\xe9" + ((to - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] in (0x66, 0x67):
            raise SystemExit("Misty Blue: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def _one(sig, data, what, n=1):
    """The signature's matches: exactly n of them (n=0: one or more)."""
    found = list(sig.finditer(data))
    if (len(found) != n) if n else not found:
        raise SystemExit("MAIN.EXE: the %s's signature is found %d times" % (what, len(found)))
    return found


# a scene module's text-screen writer (disk prompts, the bonus game's start-up): Shift-JIS from ds:si
# to text VRAM es:di, a character a word, up to a word 0
VRAM_SIG = re.compile(rb"\x8a\x24\x8a\x44\x01\x3d\x00\x00(\x74\x4e|\x75\x01\xc3)\x8b\xd0"
                      rb"(\x8a\xc6\x2c\x70.{35})\x26\x88\x25\x26\x88\x65\x02\x26\x88\x45\x01\x04\x80"
                      rb"\x26\x88\x45\x03\x26\xc6\x85\x00\x20\xe1\x26\xc6\x85\x02\x20\xe1\x46\x46\x47\x47\x47\x47"
                      rb"\xeb.", re.S)


def vram_writer(m, org):
    """The writer at `org` (its match `m`) written again in its own bytes: a byte below 80h a
    half-width character (a column), a byte 0 the end (the rest as it was)."""
    called = m.group(1) == b"\x75\x01\xc3"
    room = m.end() - m.start()
    conv = ", ".join("0x%02x" % b for b in m.group(2))
    end = "w_ret" if called else hex(org + room)
    src = """
    cld
w_loop:
    lodsb
    or al, al
    je {end}
    cmp al, 0x80
    jb w_ank
    mov ah, al
    lodsb
    mov dx, ax
    .byte {conv}
    xchg al, ah
    stosw
    or ah, 0x80
    stosw
    mov byte ptr es:[di + 0x1ffc], 0xe1
    mov byte ptr es:[di + 0x1ffe], 0xe1
    jmp w_loop
w_ank:
    mov ah, 0
    stosw
    mov byte ptr es:[di + 0x1ffe], 0xe1
    jmp w_loop
w_ret:
    .byte 0xc3
""".format(end=end, conv=conv)
    code, _addr = _asm16(src, org)
    if len(code) > room:
        raise SystemExit("Misty Blue: the text-screen writer takes %d bytes, it has %d" % (len(code), room))
    return code + b"\x90" * (room - len(code))


def vram_texts(data, base=0x1000):
    """[(writer match, [text start])] of a scene module's text-screen writers and the texts each is
    given (mov si, text before the writer, or before each call of it)."""
    out = []
    for m in VRAM_SIG.finditer(data):
        at = m.start()
        if m.group(1) == b"\x75\x01\xc3":
            sites = [c.start() for c in re.finditer(rb"\xe8..", data, re.S)
                     if (c.start() + 3 + struct.unpack_from("<h", data, c.start() + 1)[0]) & 0xFFFF == at]
        else:
            sites = [at]
        starts = []
        for s in sites:
            k = data.rfind(b"\xbe", max(0, s - 12), s)
            if k < 0:
                continue
            a = struct.unpack_from("<H", data, k + 1)[0] - base
            if 0 <= a < len(data):
                starts.append(a)
        out.append((m, starts))
    return out


def code_segment(exe):
    """(unpacked program, image, code segment's place in the image)."""
    plain = exepack.unpack(exe)
    h = struct.unpack_from("<14H", plain, 0)
    image = plain[h[4] * 16:]
    return plain, image, h[11] * 16


def patch_main(exe, words=()):
    """MAIN.EXE with the helper and the dictionary `words` (still EXEPACK-packed)."""
    _plain, image, cs = code_segment(exe)
    img = bytearray(image)
    seg = bytes(img[cs:cs + 0x10000])
    loop = _one(LOOP_SIG, seg, "decoder's loop")[0].start()
    at = _one(PAIR_SIG, seg, "decoder's two-byte path")[0].start()
    nl = _one(NEWLINE_SIG, seg, "line end")[0]
    lf = _one(LEFT_SIG, seg, "line room")[0]
    left = struct.unpack("<H", lf.group(1))[0]
    width = left - 1
    # (the decoder's draw path: the push bx after the JIS conversion's mov dl, al)
    draw = seg.find(b"\x8a\xd0\x53", at) + 2
    if draw < 2 or draw - at > 0x60:
        raise SystemExit("MAIN.EXE: the decoder's draw path is not where it was expected")
    starts = _one(DRAW_START_SIG, seg, "glyph drawer", 0)
    rows = _one(DRAW_ROW_SIG, seg, "glyph row", 0)
    if len(rows) != len(starts):
        raise SystemExit("MAIN.EXE: %d glyph drawers and %d row readers" % (len(starts), len(rows)))
    # the helper and the dictionary go after the image (the code segment's end, unused): the image
    # made longer (pc98tl/exepack.py `pack`'s extra)
    base = len(img) - cs
    letters = LETTERS.encode("ascii")
    tbl = base
    g1, g2 = tbl + len(letters), tbl + len(letters) + 0x24
    code_at = g2 + 0x24
    ret = _code(RET)
    var = {k: code_at + n for n, k in enumerate(VARS)}
    dict_b = dictionary_bytes(words)

    def build(dict_at):
        src = HELPER.format(left=hex(left), width=hex(width), newline=hex(nl.start()), draw=hex(draw),
                            cont=hex(at + 5), loop=hex(loop), ntrail=len(TRAILS), nletter=len(LETTERS),
                            pairs=PAIRS, ret=RET, ret_lead=hex(ret[0]), ret_trail=hex(ret[1]),
                            letters=hex(tbl), g1=hex(g1), g2=hex(g2), dict=hex(dict_at), scratch=hex(SCRATCH),
                            **{k: hex(v) for k, v in var.items()})
        return _asm16(src, code_at, ["pair", "start", "row"] + VARS)

    code, addr = build(0x1000)
    dict_at = code_at + len(code)
    code, addr = build(dict_at)
    if any(addr[k] != v for k, v in var.items()):
        raise SystemExit("Misty Blue: the helper's variables are not where they were taken to be")
    extra = bytearray(letters + bytes(0x48) + code + dict_b)
    extra += bytes(-len(extra) % 16)
    if base + len(extra) > 0xFFF0:
        raise SystemExit("Misty Blue: the helper and the dictionary take %d bytes, the code segment has %d"
                         % (len(extra), 0xFFF0 - base))
    img[cs + at:cs + at + 5] = b"\xe9" + struct.pack("<H", (addr["pair"] - (at + 3)) & 0xFFFF) + b"\x90\x90"
    for m in starts:
        k = m.start()
        img[cs + k:cs + k + 3] = b"\xe8" + struct.pack("<H", (addr["start"] - (k + 3)) & 0xFFFF)
    for m in rows:
        k = m.start()
        img[cs + k:cs + k + 20] = b"\xe8" + struct.pack("<H", (addr["row"] - (k + 3)) & 0xFFFF) + b"\x90" * 17
    return exepack.pack(exe, bytes(img), bytes(extra))
