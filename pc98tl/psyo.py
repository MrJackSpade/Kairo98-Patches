"""T&E Soft's Psy-O-Blade: its messages, and English at any length.

The program disk (2HD, 1024-byte sectors, 8 a track, track = cylinder * 2 + head) holds the main
program at PROGRAM_AT, loaded at 2000h:0 (code, data, then zeros the program uses as buffers; the
start-up overlay at AEC0h).  The program loads overlays (code with the text inline) to 2000h:AEC0h
through three tables of 12-byte entries (`overlays`): drive, track, sector, 0, length, address.

Text (`parse`): each byte stored is the character less 60h.  Characters below 20h are commands
(`ARGS`: how many bytes follow; three take a word read as it is: E calls a routine, 11h prints a
number, 14h prints another message), 0 ends the message, 1 is a new line; 20h-7Fh are drawn
half-width, one column; 80h-9Fh lead a Shift-JIS pair; A0h and up are half-width kana drawn
full-width ('[' and ']' switch between hiragana and katakana).  Every message goes through one
routine (`ENTRY_SIG`), which takes it at SI; messages are found by any word that points at one
(`messages`), and by following one another.

English at any length (`patch_program`): the English is in a table (`pool`) read at start-up from
free tracks at the end of the disk into 6000h:0 by a stub put in the program's zeros (the program's
first call goes to it).  The stub also puts small routines at 2000h:FA40h, past the largest
overlay.  The message routine is made to look its message up there by its bytes (length and two
sums); when it has English, the routine's fetch reads the English from the table's segment, breaking
lines between words (a space whose word would pass the window's right edge becomes a new line), and
the routine returns past the Japanese.  The commands that read a word, and the one that prints
another message, are made to read from the right segment.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from .illusion_font import _asm

SECTOR = 1024
TRACK = 8 * SECTOR
PROGRAM_SIZE = 0xF800
OVERLAY_AT = 0xAEC0
POOL = 0x6000
POOL_END = 0xA000
STUB_AT = 0xFA40
STUB_ROOM = 0x2C0
INIT_AT = 0xA000
INIT_ROOM = 0x200
EMPTY = 0xE5

ARGS = {0: 0, 1: 0, 2: 2, 3: 4, 4: 1, 5: 2, 6: 1, 7: 1, 8: 0, 9: 0, 0xA: 0, 0xB: 0, 0xC: 1, 0xD: 1,
        0xE: -2, 0xF: 0, 0x10: 1, 0x11: -2, 0x12: 0, 0x13: 0, 0x14: -2}


def program(disk, at):
    return disk[at:at + PROGRAM_SIZE]


# mov si, table1 / or ah, ah / je / mov si, table2 / dec ah / je / mov si, table3
TABLES_SIG = re.compile(b"\xbe(..)\x0a\xe4\x74.\xbe(..)\xfe\xcc\x74.\xbe(..)", re.S)


def overlays(prog):
    """{disk offset: (length, address)} of the overlays the program loads."""
    m = TABLES_SIG.search(prog)
    if not m:
        raise SystemExit("Psy-O-Blade: the overlay tables are not found")
    out = {}
    for g in (1, 2, 3):
        t = struct.unpack("<H", m.group(g))[0]
        for k in range(64):
            drive, track, sector, zero, length, dest = struct.unpack_from("<6H", prog, t + 12 * k)
            if drive != 1 or zero or not 1 <= sector <= 8 or not 0 < length <= 0x5000 or dest != OVERLAY_AT:
                break
            out[(track * 8 + sector - 1) * SECTOR] = (length, dest)
    return out


def start_overlay_end(prog):
    """Where the start-up overlay in the program ends: at the first run of filler (E5h) after it."""
    k = prog.find(bytes([EMPTY]) * 64, OVERLAY_AT)
    return k if k > 0 else len(prog)


# the loader: mov bp, es / mov ax, ds / mov es, ax / mov di, control block / mov ax, 1 / stosw
LOADER_SIG = re.compile(b"\x8c\xc5\x8c\xd8\x8e\xc0\xbf..\xb8\x01\x00\xab", re.S)


def blocks(disk, prog):
    """{disk offset: (length, address)} of what the program loads from its own disk above its
    buffers: the overlays, and what they load in turn (a mov si at an entry, then a call of the
    loader or of its retrying caller; the pictures, loaded into the buffers, are left out)."""
    loader = _one(LOADER_SIG, prog[:OVERLAY_AT], "loader").start()
    calls = {loader}
    for k in range(OVERLAY_AT - 5):
        if prog[k] == 0xE8 and _rel(prog, k) == loader and prog[k + 3:k + 6] == bytes.fromhex("72fbc3"):
            calls.add(k)
    out = dict(overlays(prog))
    todo = [(disk[o:o + n], d) for o, (n, d) in out.items()]
    while todo:
        body, dst = todo.pop()
        for k in range(len(body) - 5):
            if body[k] != 0xBE or body[k + 3] != 0xE8:
                continue
            if (dst + k + 6 + struct.unpack_from("<h", body, k + 4)[0]) & 0xFFFF not in calls:
                continue
            x = struct.unpack_from("<H", body, k + 1)[0]
            ent = body[x - dst:x - dst + 12] if dst <= x <= dst + len(body) - 12 else prog[x:x + 12]
            if len(ent) < 12:
                continue
            drive, track, sector, zero, length, dest = struct.unpack("<6H", ent)
            off = (track * 8 + sector - 1) * SECTOR
            if (drive != 1 or zero or not 1 <= sector <= 8 or not 0 < length <= 0x5000 or dest < OVERLAY_AT - 0x80
                    or off + length > len(disk) or off in out):
                continue
            out[off] = (length, dest)
            todo.append((disk[off:off + length], dest))
    return out


def parse(b, p, lim):
    """(end, command list, characters) of the message at b[p], or None."""
    cmds, chars = [], 0
    while p < lim:
        c = (b[p] + 0x60) & 0xFF
        p += 1
        if c < 0x20:
            if c not in ARGS:
                return None
            cmds.append(c)
            if c == 0:
                return p, cmds, chars
            p += abs(ARGS[c])
        elif c < 0x80:
            chars += 1
        elif c < 0xA0:
            p += 1
            chars += 1
        else:
            chars += 1
    return None


def _text(b, s, e):
    """Whether b[s:e] reads as the game's text: Shift-JIS pairs that decode, kana and punctuation
    (A1h-DFh), and no more ASCII letters than those (twice as many with commands); at least four of them without a command unless there is no ASCII (code bytes
    taken for text fail one of these)."""
    p, wide, ascii_, cmds = s, 0, 0, 0
    while p < e:
        c = (b[p] + 0x60) & 0xFF
        p += 1
        if c < 0x20:
            p += abs(ARGS[c])
            cmds += c != 0
        elif c < 0x80:
            if c in (0x60, 0x7F):
                return False
            ascii_ += c not in (0x20, 0x5B, 0x5D)
        elif c < 0xA0:
            t = (b[p] + 0x60) & 0xFF
            p += 1
            if c < 0x81 or not 0x40 <= t <= 0xFC or t == 0x7F:
                return False
            try:
                bytes([c, t]).decode("cp932")
            except UnicodeDecodeError:
                return False
            wide += 1
        elif 0xA1 <= c < 0xE0:
            wide += 1
        else:
            return False
    if cmds:
        return wide >= 2 and ascii_ <= 2 * wide
    return wide >= 4 and ascii_ <= wide or wide >= 2 and not ascii_


def _valid(body, t):
    r = parse(body, t, len(body))
    return r[0] if r and _text(body, t, r[0]) else None


def _trim(b, s, e):
    """A start that some stray word points at: when ASCII comes before the first command, the
    message is taken to start at that command (the bytes before are the code's)."""
    p, stray = s, False
    while p < e:
        c = (b[p] + 0x60) & 0xFF
        if c < 0x20:
            return p if stray and c else s
        if 0x20 < c < 0x80:
            stray = True
        p += 2 if 0x80 <= c < 0xA0 else 1
    return s


def messages(body, dst):
    """[(start, end)] of a body's messages.  A start is a place some word points at; where several
    share an end, those a mov si points at are kept (else the first that starts with a command, else
    the first).  Then the messages that follow a message (at its end, or a command one or two bytes
    on)."""
    cand, by_si = {}, set()
    for k in range(len(body) - 1):
        t = struct.unpack_from("<H", body, k)[0] - dst
        if 0 <= t < len(body):
            if k and body[k - 1] == 0xBE:
                by_si.add(t)
            if t not in cand:
                e = _valid(body, t)
                if e:
                    cand[t] = e
    ends = {}
    for t, e in cand.items():
        ends.setdefault(e, []).append(t)
    ms = {}
    for e, starts in ends.items():
        starts.sort()
        si = [t for t in starts if t in by_si]
        if si:
            keep = si
        else:
            cmd = [t for t in starts if (body[t] + 0x60) & 0xFF < 0x20]
            keep = [cmd[0] if cmd else _trim(body, starts[0], e)]
        for t in keep:
            ms[t] = e
    todo = sorted(set(ms.values()))
    while todo:
        e = todo.pop()
        for d in (0, 1, 2):
            t = e + d
            if t in ms or t >= len(body) or (d and (body[t] + 0x60) & 0xFF >= 0x20):
                continue
            if any(s < t < ee for s, ee in ms.items()):
                break
            r = parse(body, t, len(body))
            if not r:
                continue
            if _text(body, t, r[0]):
                ms[t] = r[0]
            todo.append(r[0])
            break
    return sorted(ms.items())


def key(b):
    """(length, sum, rotating sum) of a message's bytes as stored, up to and with its end."""
    s1 = s2 = 0
    for c in b:
        s1 = (s1 + c) & 0xFFFF
        s2 = (((s2 << 1) | (s2 >> 15)) & 0xFFFF) ^ c
    return len(b), s1, s2


# --- the text as shown, and English ---------------------------------------------------------------

# push bx / mov bx, table / mov ah, 0 / add bx, ax / mov dl, cs:[bx]: the full-width form of a byte A0h+
KANA_SIG = re.compile(b"\x53\xbb(..)\xb4\x00\x03\xd8\x2e\x8a\x17", re.S)


def kana_table(prog):
    t = struct.unpack("<H", _one(KANA_SIG, prog, "kana table").group(1))[0]
    return prog[t:t + 256]


def _wide(c, kata, table):
    """The Shift-JIS character the game draws for byte c (A0h and up), as its routine works it out."""
    dl, dh = table[c], 0x81
    if 0xA6 <= c < 0xDE and c != 0xB0:
        dh = 0x83
        if not kata:
            dh = 0x82
            dl = (dl + 0x5F) & 0xFF
            if dl >= 0xDE:
                dl -= 1
    return bytes([dh, dl]).decode("cp932", "replace")


def show(b, table):
    """The message as the screen shows it: commands as {XX} or {XX:args} (hex), 1 as a new line."""
    out, p, kata = [], 0, False
    while p < len(b):
        c = (b[p] + 0x60) & 0xFF
        p += 1
        if c < 0x20:
            if c == 0:
                break
            if c == 1:
                out.append("\n")
                continue
            n = abs(ARGS.get(c, 0))
            if ARGS.get(c, 0) < 0:
                arg = b[p:p + n]
            else:
                arg = bytes((x + 0x60) & 0xFF for x in b[p:p + n])
            p += n
            out.append("{%02X%s}" % (c, ":" + arg.hex().upper() if n else ""))
        elif c == 0x5B:
            kata = True
        elif c == 0x5D:
            kata = False
        elif c < 0x80:
            out.append(chr(c))
        elif c < 0xA0:
            pair = bytes([c, (b[p] + 0x60) & 0xFF])
            p += 1
            out.append(pair.decode("cp932", "replace"))
        else:
            out.append(_wide(c, kata, table))
    return "".join(out)


TOKEN = re.compile(r"\{([0-9A-Fa-f]{2})(?::([0-9A-Fa-f]*))?\}")


def tokens(text):
    return [m.group(0).upper() for m in TOKEN.finditer(text)]


def encode(text):
    """English as the table holds it (values as fetched: characters, commands and their bytes),
    ended by 0; anything outside ASCII written as '?', '[' and ']' (the kana switches) as '(' ')'."""
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "[": "(", "]": ")"}
    out = bytearray()
    pos = 0
    for m in list(TOKEN.finditer(text)) + [None]:
        seg = text[pos:m.start() if m else len(text)]
        for ch in seg:
            ch = subst.get(ch, ch)
            for x in ch:
                if x == "\n":
                    out.append(1)
                elif 0x20 <= ord(x) < 0x7F and x not in "[]":
                    out.append(ord(x))
                else:
                    out.append(ord("?"))
        if m is None:
            break
        c = int(m.group(1), 16)
        arg = bytes.fromhex(m.group(2) or "")
        if c == 0 or c >= 0x20 or c not in ARGS or len(arg) != abs(ARGS[c]):
            raise ValueError("bad command %s" % m.group(0))
        out.append(c)
        out += arg
        pos = m.end()
    return bytes(out) + b"\0"


# --- the program's routines --------------------------------------------------------------------

# mov byte [choice count], 0 / mov [substrings], dx / xor al, al / mov [kana], al
ENTRY_SIG = re.compile(b"\xc6\x06(..)\x00\x89\x16..\x32\xc0\xa2", re.S)
FETCH_SIG = re.compile(b"\xac\x04\x60\xc3")
# mov dx, [bx + commands] / xchg bx, ax / jmp dx
DISPATCH_SIG = re.compile(b"\x8b\x97(..)\x93\xff\xe2", re.S)
# the first call: three segments set ("add ax, 1000h / mov [x], ax"), then call
START_SIG = re.compile(b"\x05\x00\x10\xa3..\x05\x00\x10\xa3..\x05\x00\x10\xa3..\xe8(..)", re.S)


def _one(sig, data, what):
    found = list(sig.finditer(data))
    if len(found) != 1:
        raise SystemExit("Psy-O-Blade: the %s's signature is found %d times, not once" % (what, len(found)))
    return found[0]


def _rel(prog, at):
    return (at + 3 + struct.unpack_from("<h", prog, at + 1)[0]) & 0xFFFF


def sites(prog):
    """The addresses the patch needs, found in the program's code (before its overlay area)."""
    prog = prog[:OVERLAY_AT]
    e = _one(ENTRY_SIG, prog, "message routine")
    f = _one(FETCH_SIG, prog, "fetch")
    fetch = f.start()
    d = _one(DISPATCH_SIG, prog, "command dispatch")
    table = struct.unpack("<H", d.group(1))[0]
    handler = lambda c: struct.unpack_from("<H", prog, table + 2 * c)[0]  # noqa: E731
    loop = None
    for k in range(e.start(), e.start() + 0x60):
        if prog[k] == 0xE8 and _rel(prog, k) == fetch and prog[k + 3:k + 5] == b"\x3c\x20":
            loop = k
            break
    if loop is None:
        raise SystemExit("Psy-O-Blade: the message routine's loop is not found")
    out = {"entry": e.start(), "count": struct.unpack("<H", e.group(1))[0], "fetch": fetch, "loop": loop}
    h11, h0e, h14 = handler(0x11), handler(0x0E), handler(0x14)
    if prog[h11:h11 + 5] != b"\x8b\x14\x83\xc6\x02":
        raise SystemExit("Psy-O-Blade: command 11h does not read its word as expected")
    if prog[h0e:h0e + 7] != b"\x53\x51\x8b\x14\x83\xc6\x02":
        raise SystemExit("Psy-O-Blade: command 0Eh does not read its word as expected")
    if prog[h14:h14 + 8] != b"\x83\xc6\x02\x56\x8b\x74\xfe\xeb":
        raise SystemExit("Psy-O-Blade: command 14h does not read its word as expected")
    sub = (h14 + 9 + struct.unpack_from("<b", prog, h14 + 8)[0]) & 0xFFFF
    if prog[sub] != 0xE8 or _rel(prog, sub) != loop or prog[sub + 3:sub + 5] != b"\x5e\xc3":
        raise SystemExit("Psy-O-Blade: the other-message call is not laid out as expected")
    out.update(w11=h11, w0e=h0e + 2, w14=h14 + 4, sub=sub)
    # the new line (command 1: jmp to it): mov ch, [di+5] / add cl, 10 / cmp cl, [di+6] / jae scroll /
    # jmp ... ; the scroll begins sub cl, 10
    h1 = handler(1)
    nl = (h1 + 3 + struct.unpack_from("<h", prog, h1 + 1)[0]) & 0xFFFF if prog[h1] == 0xE9 else h1
    if (prog[nl:nl + 11] != bytes.fromhex("8a6d0580c10a3a4d067303") or prog[nl + 11] != 0xE9
            or prog[nl + 14:nl + 17] != bytes.fromhex("80e90a")):
        raise SystemExit("Psy-O-Blade: the new line is not laid out as expected")
    out.update(scroll=nl + 14, wait=handler(8), clear=handler(9))
    s = _one(START_SIG, prog, "start-up")
    out["start"] = s.end() - 3
    out["first"] = _rel(prog, out["start"])
    return out


# --- the patch -----------------------------------------------------------------------------------

STUB = """
v_flag: .byte 0
v_pad: .byte 0
v_seg: .word 0
v_end: .word 0
t_found: .word 0
t_end: .word 0
fetch:
    cmp byte ptr [{v_flag}], 0
    jne f_far
    lodsb
    add al, 0x60
    .byte 0xc3
f_far:
    push ds
    .byte 0x8e, 0x1e
    .word {v_seg}
    lodsb
    pop ds
    cmp al, 0x20
    jne f_ret
    push bp
    mov bp, sp
    cmp word ptr [bp + 2], {loopret}
    pop bp
    jne f_ret
    push ax
    push si
    push dx
    push ds
    .byte 0x8e, 0x1e
    .word {v_seg}
    xor dx, dx
f_len:
    lodsb
    cmp al, 0x21
    jb f_lend
    cmp al, 0x80
    jae f_lend
    inc dx
    jmp f_len
f_lend:
    pop ds
    mov al, ch
    xor ah, ah
    add ax, dx
    inc ax
    mov dl, byte ptr [di + 7]
    xor dh, dh
    cmp ax, dx
    pop dx
    pop si
    pop ax
    jbe f_ret
    mov al, 1
f_ret:
    .byte 0xc3
w_dx:
    cmp byte ptr [{v_flag}], 0
    jne wd_far
    mov dx, word ptr [si]
    add si, 2
    .byte 0xc3
wd_far:
    push ds
    .byte 0x8e, 0x1e
    .word {v_seg}
    mov dx, word ptr [si]
    pop ds
    add si, 2
    .byte 0xc3
w_si:
    cmp byte ptr [{v_flag}], 0
    jne ws_far
    mov si, word ptr [si - 2]
    .byte 0xc3
ws_far:
    push ds
    .byte 0x8e, 0x1e
    .word {v_seg}
    mov si, word ptr [si - 2]
    pop ds
    .byte 0xc3
m_hook:
    push word ptr [{v_flag}]
    push word ptr [{v_seg}]
    push word ptr [{v_end}]
    mov byte ptr [{v_flag}], 0
    .byte 0x9a
    .word {lookup}
    .word {pool}
    push word ptr [{v_flag}]
    push word ptr [{v_end}]
    mov byte ptr [{count}], 0
    CALLN {body}
    pop word ptr [{t_end}]
    pop word ptr [{t_found}]
    pushf
    cmp byte ptr [{t_found}], 0
    je m_keep
    mov si, word ptr [{t_end}]
m_keep:
    popf
    pop word ptr [{v_end}]
    pop word ptr [{v_seg}]
    pop word ptr [{v_flag}]
    .byte 0xc3
sub_hook:
    push word ptr [{v_flag}]
    push word ptr [{v_seg}]
    push word ptr [{v_end}]
    mov byte ptr [{v_flag}], 0
    .byte 0x9a
    .word {lookup}
    .word {pool}
    CALLN {loop}
    pop word ptr [{v_end}]
    pop word ptr [{v_seg}]
    pop word ptr [{v_flag}]
    pop si
    .byte 0xc3
page:
    sub cl, 0x0a
    cmp byte ptr [{v_flag}], 0
    jne p_far
    JMPN {scroll}
p_far:
    CALLN {wait}
    JMPN {clear}
"""

LOOKUP = """
lookup:
    push ax
    push bx
    push cx
    push dx
    push di
    mov word ptr cs:[l_start], si
    xor bx, bx
    xor dx, dx
l_loop:
    mov ax, si
    sub ax, word ptr cs:[l_start]
    cmp ax, 0x3000
    ja l_fail
    CALLN l_byte
    mov ah, al
    add ah, 0x60
    cmp ah, 0x20
    jae l_chr
    or ah, ah
    jz l_end
    push bx
    mov bl, ah
    xor bh, bh
    mov ch, byte ptr cs:[bx + l_args]
    pop bx
l_arg:
    or ch, ch
    jz l_loop
    CALLN l_byte
    dec ch
    jmp l_arg
l_chr:
    cmp ah, 0x80
    jb l_loop
    cmp ah, 0xa0
    jae l_loop
    CALLN l_byte
    jmp l_loop
l_end:
    mov ax, si
    sub ax, word ptr cs:[l_start]
    mov cx, word ptr cs:[{index}]
    mov di, {index} + 2
l_find:
    jcxz l_fail
    cmp ax, word ptr cs:[di]
    jne l_next
    cmp bx, word ptr cs:[di + 2]
    jne l_next
    cmp dx, word ptr cs:[di + 4]
    je l_hit
l_next:
    add di, 10
    dec cx
    jmp l_find
l_hit:
    mov word ptr [{v_end}], si
    mov ax, word ptr cs:[di + 6]
    mov word ptr [{v_seg}], ax
    mov si, word ptr cs:[di + 8]
    mov byte ptr [{v_flag}], 1
    jmp l_ret
l_fail:
    mov si, word ptr cs:[l_start]
l_ret:
    pop di
    pop dx
    pop cx
    pop bx
    pop ax
    .byte 0xcb
l_byte:
    lodsb
    push ax
    xor ah, ah
    add bx, ax
    rol dx, 1
    xor dl, al
    pop ax
    .byte 0xc3
l_start: .word 0
l_args: .byte {args}
"""

INIT = """
init:
    push ds
    push es
    push bp
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov ax, {pool}
    mov es, ax
    mov si, {track}
    mov di, {count}
i_track:
    mov bp, 0
    mov word ptr cs:[i_tries], 6
i_read:
    mov ax, si
    mov cl, al
    shr cl, 1
    mov dh, al
    and dh, 1
    mov dl, 1
    mov ch, 3
    mov bx, 0x2000
    mov ax, 0xd690
    int 0x1b
    jnc i_next
    dec word ptr cs:[i_tries]
    jz i_done
    mov ax, 0x0790
    int 0x1b
    jmp i_read
i_next:
    mov ax, es
    add ax, 0x200
    mov es, ax
    inc si
    dec di
    jnz i_track
    mov ax, {pool}
    mov ds, ax
    mov ax, cs
    mov es, ax
    mov si, {stub_src}
    mov di, {stub_at}
    mov cx, {stub_len}
    cld
    rep movsb
i_done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    pop es
    pop ds
    JMPN {first}
i_tries: .word 0
"""


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
    names = list(want) + [t for t, _x in fix] + [x for _t, x in fix if not x.startswith("0x")]
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org, list(dict.fromkeys(names)))
    code = bytearray(code)
    for tag, target in fix:
        to = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = b"\xe9" + ((to - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("Psy-O-Blade: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code), addr


def free_tracks(disk, used_end):
    """(first, count) of the longest run of empty tracks (every byte E5h, as formatted) past
    `used_end` (the end of everything the program loads)."""
    empty = bytes([EMPTY]) * TRACK
    best, run_at, run = (0, 0), None, 0
    for t in range(-(-used_end // TRACK), len(disk) // TRACK):
        if disk[t * TRACK:(t + 1) * TRACK] == empty:
            run_at = t if run == 0 else run_at
            run += 1
            if run > best[1]:
                best = (run_at, run)
        else:
            run = 0
    return best


def build(disk, at, entries):
    """The disk with the English: entries [(Japanese bytes as stored, English bytes as encode()
    gives)].  Raises SystemExit when the English does not fit."""
    disk = bytearray(disk)
    prog = bytearray(program(disk, at))
    s = sites(bytes(prog))
    ovs = blocks(bytes(disk), bytes(prog))
    used_end = max([o + n for o, (n, _d) in ovs.items()] + [at + PROGRAM_SIZE])
    if max(n + d for n, d in ovs.values()) > STUB_AT:
        raise SystemExit("Psy-O-Blade: a block the program loads runs past %Xh" % STUB_AT)
    if any(prog[INIT_AT:INIT_AT + INIT_ROOM]):
        raise SystemExit("Psy-O-Blade: the program's room for the start-up stub is not empty")
    names = ["v_flag", "v_seg", "v_end", "fetch", "w_dx", "w_si", "m_hook", "sub_hook", "page"]
    # (LOOKUP is the table's first routine: POOL:0)
    # (keystone writes a label's address with a 32-bit prefix: the variables are given as numbers)
    var = {v: hex(STUB_AT + 2 * k)
           for k, v in enumerate(["v_flag", "v_seg", "v_end", "t_found", "t_end"])}
    stub, sa = _asm16(STUB.format(lookup="0", loopret=hex(s["loop"] + 3), pool=hex(POOL), count=hex(s["count"]),
                                  body=hex(s["entry"] + 5), loop=hex(s["loop"]), scroll=hex(s["scroll"] + 3),
                                  wait=hex(s["wait"]), clear=hex(s["clear"]), **var), STUB_AT, names)
    if any(sa[v] != int(var[v], 16) for v in ("v_flag", "v_seg", "v_end")):
        raise SystemExit("Psy-O-Blade: the routines' variables are not where they were taken to be")
    if len(stub) > STUB_ROOM:
        raise SystemExit("Psy-O-Blade: the routines at %Xh take %d bytes" % (STUB_AT, len(stub)))
    rows = {}
    for jp, en in entries:
        k = key(jp)
        if k in rows and rows[k][0] != jp:
            raise SystemExit("Psy-O-Blade: two messages share a key; the table cannot tell them apart")
        rows[k] = (jp, en)
    index_at = 0x400
    look, la = _asm16(LOOKUP.format(index=hex(index_at), v_end=hex(sa["v_end"]), v_seg=hex(sa["v_seg"]),
                                    v_flag=hex(sa["v_flag"]),
                                    args=", ".join(str(abs(ARGS.get(c, 0))) for c in range(32))), 0, ["lookup"])
    assert la["lookup"] == 0
    stub_src = len(look)
    if stub_src + len(stub) > index_at:
        raise SystemExit("Psy-O-Blade: the table's routines run past %Xh" % index_at)
    head = bytearray(look + stub)
    head += bytes(index_at - len(head))
    index = bytearray(struct.pack("<H", len(rows)))
    pages = [bytearray()]
    first_page = index_at + 2 + 10 * len(rows)
    for k in sorted(rows):
        en = rows[k][1]
        page = len(pages) - 1
        base = first_page if page == 0 else 0
        if base + len(pages[page]) + len(en) > 0x10000:
            pages.append(bytearray())
            page, base = page + 1, 0
        index += struct.pack("<HHHHH", k[0], k[1], k[2], POOL + 0x1000 * page, base + len(pages[page]))
        pages[page] += en
    blob = bytearray(head + index + pages[0])
    for p in pages[1:]:
        blob += bytes(-len(blob) % 0x10000) + p
    blob += bytes(-len(blob) % TRACK)
    ntracks = len(blob) // TRACK
    first, free = free_tracks(bytes(disk), used_end)
    if ntracks > free or len(blob) > (POOL_END - POOL) * 16:
        raise SystemExit("Psy-O-Blade: the English takes %d tracks; the disk has %d free and memory room for %d"
                         % (ntracks, free, (POOL_END - POOL) * 16 // TRACK))
    disk[first * TRACK:(first + ntracks) * TRACK] = blob
    init, _ia = _asm16(INIT.format(pool=hex(POOL), track=hex(first), count=hex(ntracks), stub_src=hex(stub_src),
                                   stub_at=hex(STUB_AT), stub_len=hex(len(stub)), first=hex(s["first"])),
                       INIT_AT)
    if len(init) > INIT_ROOM:
        raise SystemExit("Psy-O-Blade: the start-up stub takes %d bytes" % len(init))
    prog[INIT_AT:INIT_AT + len(init)] = init

    def jmp(at, to, size, op=0xE9):
        prog[at:at + size] = bytes([op]) + struct.pack("<H", (to - (at + 3)) & 0xFFFF) + b"\x90" * (size - 3)

    jmp(s["start"], INIT_AT, 3, 0xE8)
    jmp(s["entry"], sa["m_hook"], 5)
    jmp(s["fetch"], sa["fetch"], 4)
    jmp(s["w11"], sa["w_dx"], 5, 0xE8)
    jmp(s["w0e"], sa["w_dx"], 5, 0xE8)
    jmp(s["w14"], sa["w_si"], 3, 0xE8)
    jmp(s["sub"], sa["sub_hook"], 3)
    jmp(s["scroll"], sa["page"], 3)
    disk[at:at + PROGRAM_SIZE] = prog
    return bytes(disk), ntracks
