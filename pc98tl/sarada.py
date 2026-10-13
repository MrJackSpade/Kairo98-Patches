"""Hudson's Salad no Kuni no Tomato-hime (1984, N88-DISK BASIC floppy): its text, and English at any length.

The disk: START (an N88-BASIC(86) program, a plain binary save, pc98tl/n88prog.py) BLOADs SARADA.P0 at
0500h:0 and CALLs it; P0 moves itself to segment 0180h (its offsets 200h-1FFFh kept) and runs the game,
loading a chapter (SARADA.P1-P4, BLOADed by START's *P1-*P4 at 0180h:3000h) when one is needed.  Each
SARADA.P* file is a BSAVE image: its load and end offsets (two words), then the bytes.  The chapters are
x86 code with their text in it: half-width katakana (and ASCII), each string ended by a 0, CR LF a new
line.  P0's routine at 61Ch prints the string at BX (up to its 0, BX left past it); its entries 239h,
23Ch and 23Fh print the string written right after their call (`inline`), and the chapters' message
tables and immediates pass BX to 61Ch.  P0 also holds the parser's word list (`vocabulary`): records
of a word number and a word, English words among them, so the player can type English already.

English at any length (`pool`, `patch_p0`, `patch_chapter`): the routine at 61Ch is made a far call to a
helper loaded with a table at 2600h:0 (`POOL`, memory neither BASIC nor the game uses), the far call's
stub back to P0's character writer put in the routine's last bytes.  The helper looks BX up in the
table: a string with English is printed from there instead, BX set past the Japanese one, so every way
the game reaches a string (an inline call, a table, an immediate) goes on as before; any other string
prints as it was.  The English is broken between words where a word would reach the screen's last
column (from the cursor's real column, wherever the string starts), CR LF in it a new line.  The game
shows only the text layer's last 4 rows (WINDOW) under its picture and scrolls the whole layer: P0's
scroll is made to wait for a key before it would move a line not yet seen out of the window (one
the game printed since it last read a key, which a line counter in the helper tracks), so text of any
length can be read, Japanese or English.  The chapters' inventory
prints its names a character at a time: it is made to print each through 61Ch.  START loads P0's table
(SARADA.T0) before CALLing P0, and each chapter's (P0's strings and the chapter's, SARADA.T1-T4) with
the chapter (`patch_start`).
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .illusion_font import _asm
from . import n88prog as N

POOL = 0x2600
SEG = 0x180
INLINE = (0x239, 0x23C, 0x23F)
TEXT = frozenset(list(range(0x20, 0x7F)) + list(range(0xA1, 0xE0)) + [0x0D, 0x0A])


def bsave(data):
    """(load offset, bytes) of a BSAVE image."""
    start, end = struct.unpack_from("<HH", data, 0)
    return start, data[4:4 + end - start]


def make_bsave(start, body):
    return struct.pack("<HH", start, start + len(body)) + body


def _org(name, start):
    return 0 if name.upper().endswith(".P0") else start


def _refs(body):
    """The words in the file, at any byte (the addresses its tables and immediates name)."""
    return {struct.unpack_from("<H", body, k)[0] for k in range(len(body) - 1)}


def _texty(t, loose=False):
    """Most of the bytes katakana, punctuation, words of capitals or digits, spaces or line breaks;
    code and pattern data that happen to be printable bytes are not.  `loose` (a run not after a 0
    or a record's 01) needs a space among them too: the game's text puts one between its phrases."""
    word = [0x41 <= c <= 0x5A or 0x30 <= c <= 0x39 for c in t]
    good = sum(1 for k, c in enumerate(t) if 0xA1 <= c <= 0xDF or
               word[k] and (k and word[k - 1] or k + 1 < len(t) and word[k + 1]) or
               c in (0x20, 0x21, 0x3F, 0x28, 0x29, 0x2E, 0x2C, 0x2D, 0x0D, 0x0A))
    lone_lf = any(c == 0x0A and (k == 0 or t[k - 1] != 0x0D) for k, c in enumerate(t))
    return len(t) >= 3 and good * 10 >= len(t) * 9 and (0x20 in t or not loose) and not lone_lf


def vocabulary(body):
    """[(start, end)] of P0's word list's records (number and word): runs of records 00 / number /
    word, the numbers rising, eight or more together."""
    recs = [m for m in re.finditer(rb"\x00([\x00-\x7f])([\x20-\x7e\xa1-\xdf]{1,20})(?=\x00)", body)]
    out, run = [], []
    for m in recs:
        if run and m.start() == run[-1].end() and m.group(1)[0] >= run[-1].group(1)[0]:
            run.append(m)
        else:
            if len(run) >= 8:
                out += [(r.start(1), r.end(2)) for r in run]
            run = [m]
    if len(run) >= 8:
        out += [(r.start(1), r.end(2)) for r in run]
    return out


def strings(name, data):
    """[(address, start, end)] of a file's strings (start..end in the BSAVE body, the 0 not counted):
    runs of text with katakana in them, not P0's word list.  An inline string starts right after its
    call (the call's last bytes may read as text); one after a 0 (the strings of a table lie end to
    end) or after an object record's 01 starts at the run's start; any other at the first byte of the
    run the file names (a table's first string right after the table), if it reads as text."""
    start, body = bsave(data)
    org = _org(name, start)
    lo = 0x200 if org == 0 else 0
    voc = {p for s, e in vocabulary(body) for p in range(s, e)} if org == 0 else set()
    named = _refs(body)
    inline = set(INLINE)
    if org == 0:
        # (P0 calls the routines its entries jump to)
        inline |= {(e + 3 + struct.unpack_from("<h", body, e + 1)[0]) & 0xFFFF for e in INLINE if body[e] == 0xE9}
    out = []
    k = lo
    n = len(body)
    while k < n:
        if body[k] not in TEXT:
            k += 1
            continue
        s = k
        while k < n and body[k] in TEXT:
            k += 1
        if k >= n or body[k] != 0:
            continue
        e = k
        first = None
        # (an inline string: the call ends inside the run's first bytes)
        for c in range(max(s - 3, lo), min(s + 3, e)):
            if body[c] == 0xE8:
                t = (org + c + 3 + struct.unpack_from("<h", body, c + 1)[0]) & 0xFFFF
                if t in inline and c + 3 >= s:
                    first = c + 3
        if first is None:
            loose = body[s - 1] not in (0x00, 0x01)
            first = next((p for p in range(s, e) if org + p in named), e) if loose else s
            if first >= e or not _texty(body[first:e], loose):
                continue
        if first >= e or first in voc:
            continue
        text = body[first:e]
        if sum(1 for c in text if 0xA6 <= c <= 0xDF) < 2:
            continue
        out.append((org + first, first, e))
    return out


def show(b):
    return b.replace(b"\r\n", b"\n").decode("cp932", "replace")


def encode(text):
    """ASCII (anything else ?, | too: the game prints it as another character), \\n as CR LF."""
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
             "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    out = bytearray()
    for ch in s:
        if ch == "\n":
            out += b"\r\n"
        elif 0x20 <= ord(ch) < 0x7F and ch != "|":
            out.append(ord(ch))
        else:
            out.append(ord("?"))
    return bytes(out)


WINDOW = 4

# the helper, at POOL:0 (the table after it).  Entered with a far call from P0's string routine, DS:BX
# the string; returns (far) with BX past the string's 0 and AL 0, as the routine did.  English is
# printed a word at a time, a line broken before a word that would reach the last column (the cursor's
# column from the text layer's place in P0's word at CURSOR).  (P0's character writer keeps every
# register but SI, which its scroll uses.)
# h_scroll, called from the start of P0's scroll, counts the lines the text has moved up since the
# game last read a key (h_key, P0's key read made a jump here: the count set to 0, the key read, then
# back to a ret in P0); before the line that would move the first of the window's WINDOW rows out of
# sight it waits for a key.  (The game shows the text layer's last WINDOW rows under its picture.)
HELPER = """
    push si
    push di
    push cx
    push dx
    mov cx, word ptr cs:[{table}]
    mov si, {table} + 2
h_find:
    jcxz h_plain
    cmp bx, word ptr cs:[si]
    je h_found
    add si, 6
    dec cx
    jmp h_find
h_plain:
    mov al, byte ptr [bx]
    inc bx
    or al, al
    jz h_done
    CALLN h_outc
    jmp h_plain
h_found:
    add bx, word ptr cs:[si + 4]
    inc bx
    mov si, word ptr cs:[si + 2]
h_word:
    mov di, si
    xor dx, dx
h_meas:
    mov al, byte ptr cs:[di]
    or al, al
    jz h_measd
    cmp al, 0x20
    je h_measd
    cmp al, 0x0d
    je h_measd
    inc di
    inc dx
    jmp h_meas
h_measd:
    or dx, dx
    jz h_sep
    CALLN h_column
    or ax, ax
    jz h_put
    add ax, dx
    cmp ax, {last}
    jbe h_put
    CALLN h_newline
h_put:
    mov al, byte ptr cs:[si]
    inc si
    CALLN h_outc
    dec dx
    jnz h_put
h_sep:
    mov al, byte ptr cs:[si]
    or al, al
    jz h_done
    inc si
    cmp al, 0x0d
    jne h_space
    inc si
    CALLN h_newline
    jmp h_word
h_space:
    CALLN h_outc
    jmp h_word
h_done:
    pop dx
    pop cx
    pop di
    pop si
    xor al, al
    .byte 0xcb
h_newline:
    mov al, 0x0d
    CALLN h_outc
    mov al, 0x0a
    CALLN h_outc
    .byte 0xc3
h_outc:
    push si
    .byte 0x9a
    .word {stub}
    .word {seg}
    pop si
    .byte 0xc3
h_column:
    push bx
    push dx
    mov ax, word ptr [{cursor}]
    xor dx, dx
    mov bx, 0xa0
    div bx
    mov ax, dx
    shr ax, 1
    pop dx
    pop bx
    .byte 0xc3
h_scroll:
    inc byte ptr cs:[h_count]
    cmp byte ptr cs:[h_count], {window}
    jb h_go
    mov byte ptr cs:[h_count], 1
    push ax
    xor ah, ah
    int 0x18
    pop ax
h_go:
    mov di, 0
    mov si, 0xa0
    .byte 0xcb
h_key:
    mov byte ptr cs:[h_count], 0
    xor ah, ah
    int 0x18
    .byte 0xea
    .word {ret}
    .word {seg}
h_count:
    .byte 0
"""

# P0's string routine: (619h:) call putc / (61Ch:) mov al, [bx] / lahf / inc bx / sahf / or al, al /
# jne 619h / ret
STRING_SIG = re.compile(rb"\xe8(..)\x8a\x07\x9f\x43\x9e\x0a\xc0\x75\xf4\xc3", re.S)
# P0's key read: mov ah, 0 / int 18h / ret
KEY_SIG = re.compile(rb"\xb4\x00\xcd\x18\xc3")
# P0's scroll: mov di, 0 / mov si, A0h / push ds
SCROLL_SIG = re.compile(rb"\xbf\x00\x00\xbe\xa0\x00\x1e")
# P0's character writer: mov cx, A000h / mov es, cx / mov bx, [cursor]
CURSOR_SIG = re.compile(rb"\xb9\x00\xa0\x8e\xc1\x8b\x1e(..)", re.S)
# a chapter's inventory: each name printed a character at a time (mov al, [bx] / (lahf) inc bx (sahf) /
# or al, al / je +5 / call putc / jmp back / mov al, 20h / call putc / jmp next)
NAMES_SIG = re.compile(rb"\x8a\x07(?:\x9f\x43\x9e|\x43)\x0a\xc0\x74\x05\xe8..\xeb.\xb0\x20\xe8(..)\xeb(.)", re.S)


def _asm16(src, org, names=()):
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
            raise SystemExit("SARADA: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def _string_routine(p0_body):
    found = list(STRING_SIG.finditer(p0_body))
    if len(found) != 1:
        raise SystemExit("SARADA.P0: the string routine's signature is found %d times, not once" % len(found))
    m = found[0]
    putc = (m.start() + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
    return m.start() + 3, putc


def _one(sig, body, what):
    found = list(sig.finditer(body))
    if len(found) != 1:
        raise SystemExit("SARADA.P0: the %s's signature is found %d times, not once" % (what, len(found)))
    return found[0].start()


def _cursor(p0_body):
    found = list(CURSOR_SIG.finditer(p0_body))
    if len(found) != 1:
        raise SystemExit("SARADA.P0: the character writer's signature is found %d times, not once" % len(found))
    return struct.unpack("<H", found[0].group(1))[0]


def helper(p0):
    """(code, {label: offset}) of the helper (for POOL:0), the table's offset after it."""
    _s, body = bsave(p0)
    at, _putc = _string_routine(body)
    src = lambda table: HELPER.format(table=hex(table), last=hex(79), window=WINDOW, stub=hex(at + 6),
                                      ret=hex(at + 5), seg=hex(SEG), cursor=hex(_cursor(body)))
    code, _a = _asm16(src(0x100), 0)
    return _asm16(src(len(code)), 0, ("h_scroll", "h_key"))


def pool(p0, entries):
    """A table file (BSAVE at POOL:0): the helper, a count, then (address, place, length) for each
    string, then the English strings, each ended by a 0.  entries: [(address, Japanese length,
    English bytes)]."""
    code, _a = helper(p0)
    entries = sorted(entries)
    head = len(code) + 2 + 6 * len(entries)
    out = bytearray(code + struct.pack("<H", len(entries)))
    text = bytearray()
    for addr, jlen, en in entries:
        out += struct.pack("<HHH", addr, head + len(text), jlen)
        text += en + b"\0"
    out += text
    if len(out) > 0xFFFF:
        raise SystemExit("SARADA: the English for a chapter takes %d bytes, the table's segment 65535" % len(out))
    return make_bsave(0, bytes(out))


def patch_p0(p0):
    """P0 with its string routine a far call to the helper (then ret), and after it the stub the helper
    prints a character through (call putc / retf); its scroll starting with a far call to h_scroll,
    its key read a far jump to h_key."""
    start, body = bsave(p0)
    at, putc = _string_routine(body)
    _code, addr = helper(p0)
    scroll, key = _one(SCROLL_SIG, body, "scroll"), _one(KEY_SIG, body, "key read")
    body = bytearray(body)
    stub = at + 6
    new = b"\x9a" + struct.pack("<HH", 0, POOL) + b"\xc3" + b"\xe8" + struct.pack("<H", (putc - (stub + 3)) & 0xFFFF) + b"\xcb"
    body[at:at + len(new)] = new
    body[scroll:scroll + 6] = b"\x9a" + struct.pack("<HH", addr["h_scroll"], POOL) + b"\x90"
    body[key:key + 5] = b"\xea" + struct.pack("<HH", addr["h_key"], POOL)
    return make_bsave(start, bytes(body))


def patch_chapter(data):
    """A chapter with its inventory printing each name through P0's string routine (so the helper
    puts in English): call 233h / mov al, 20h / call putc / jmp next."""
    start, body = bsave(data)
    found = list(NAMES_SIG.finditer(body))
    if len(found) != 1:
        raise SystemExit("SARADA chapter: the inventory's signature is found %d times, not once" % len(found))
    m = found[0]
    putc = (start + m.end(1) + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
    nxt = (start + m.end() + struct.unpack("<b", m.group(2))[0]) & 0xFFFF
    a = start + m.start()
    new = b"\xe8" + struct.pack("<H", (0x233 - (a + 3)) & 0xFFFF) + b"\xb0\x20" + b"\xe8" + \
        struct.pack("<H", (putc - (a + 8)) & 0xFFFF)
    rel = nxt - (a + len(new) + 2)
    new += b"\xeb" + struct.pack("<b", rel)
    body = bytearray(body)
    body[m.start():m.end()] = new + b"\x90" * (m.end() - m.start() - len(new))
    return make_bsave(start, bytes(body))


def _defseg(seg):
    return b"\x01\x98\x01\xe4\xf1\x0c" + struct.pack("<H", seg)


def _bload(name):
    return b"\x01\x82\x01\x22" + name.encode("ascii") + b"\x22"


def patch_start(start, chapters):
    """START with SARADA.T0 loaded before P0 is CALLed, and SARADA.Tn with each chapter (its line
    '*Pn: BLOAD "SARADA.Pn": RETURN')."""
    lines, tail = N.read(start, protected=False)
    out = []
    p0_line = next((num for num, body in lines if b'"SARADA.P0' in body), None)
    if p0_line is None:
        raise SystemExit("START: no line BLOADs SARADA.P0")
    ret = b"\x01\x3a\x01\xc6"
    for num, body in lines:
        for n in chapters:
            if ('"SARADA.P%d' % n).encode("ascii") in body and body.endswith(ret):
                body = body[:-len(ret)] + b"\x3a" + _defseg(POOL) + b"\x3a" + _bload("SARADA.T%d" % n) + \
                    b"\x3a" + _defseg(SEG) + ret
        out.append((num, body))
        if num == p0_line:
            # (P0 BLOADed with DEF SEG=&H500: P0's table, then DEF SEG=&H500 again for the CALL)
            nxt = num + 5
            if any(n2 == nxt for n2, _b in lines):
                raise SystemExit("START: no free line number after %d" % num)
            out.append((nxt, _defseg(POOL)[1:] + b"\x3a" + _bload("SARADA.T0") + b"\x3a" + _defseg(0x500)))
    if sum(1 for _n, b in out if b'"SARADA.T' in b) != len(chapters) + 1:
        raise SystemExit("START: a chapter's line is not laid out as expected")
    return N.write(out, tail, protected=False)
