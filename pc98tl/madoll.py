"""FairyDust's Ma Doll (MADOU\\MDMAIN.EXE, an EXEPACK'd MS C program): its scripts and English.

A script (STY_nn.SCR): "SCR1", a word n (records), a word n2 (the second block's records), n + n2 records
of 6 bytes (an op word and two operand words, a and b), then a word, the text's length, and the text,
NUL-ended strings, every byte XOR 7Fh.  A record names a string by its place in the text
(`load` keeps two bytes before the text, so in what it returns the string is 2 further on; `strings`): an op whose low byte is 02 its message in b (0002 the opening's and the
narration's window, 0102 the messages', 0202 a message under a speaker's line), the second block's
records (op 0000) a choice in a, an op whose low byte is 09 a picture's name in a (shared with 0011 and
0013, whose a is only sometimes a place: so the text area's strings never move).

A text (`show`): 00 its end; 01; 02 and a byte X puts in the string the program keeps at DS:[70h + 2X]
(the hero's name, the cast's and their 【】 tags: `inserts`); 0Ah a new line; 5Ch and a byte that byte
drawn as one character; else the table at DS:0802h (`table`): a byte with an entry stands for it (half-
width kana bytes for hiragana; ASCII bytes for full-width letters and some kanji), with none it starts
a two-byte Shift-JIS character.  The window is 4 lines; the program breaks a line at 58 cells (62 for
closing punctuation) and scrolls up a line when the window is full, so a message may be any length.

English (`patch_program`, `msg_file`): the table's entries for 20h-7Eh are made the letters themselves
(an entry of a letter and 0 is drawn as one half-width cell, as the program already does for " ' / :),
so English is ASCII, a byte a letter, broken between words at 58 letters; a Japanese text that stays is
written with its ASCII-byte kanji spelled out in Shift-JIS.  The messages outgrow the text area (the
program loads it at segment 0962h, 86D0h bytes below its data), so they go into a file of their own,
STY_nn.MSG, each from a paragraph's start, and a message's b becomes its paragraph: the script loader's
call of the text reader (0341h) is made a call of a helper that reads the text area as before, then the
.MSG file into memory it asks DOS for once (the size of the largest .MSG); each of the two message
readers (0FE6h the window's, 0EA0h the log's) adds the message's paragraph to that memory's segment into
DS:2F34h (otherwise the text area's segment, used only by them) where it added the text's base, and
reads its segment from there where it loaded 0962h.  The helpers sit at the end of the text area's room
(the text area keeps under 430 bytes: its messages are no longer in it).  The program is written back
unpacked.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from . import exepack

DS_PARA = 0x11CF                  # DGROUP, relative to the load image
TABLE = 0x802                     # DS: the one-byte characters' table (256 words)
INSERTS = 0x70                    # DS: the strings 02 X puts in (pointers, by X)
WIDTH = 58                        # a line's cells
MSG_OPS_LOW = 0x02
PICTURE_OPS_LOW = 0x09
CHOICE_OP = 0x0000
TEXT_SEG = 0x962                  # (relocated) the text area's segment, from the image's start
HELPERS = 0xFC00                  # where the helpers go (near the text area's end, in the code segment)

# byte signatures of the places patched (each found once in the unpacked image)
SIG_LOAD = re.compile(rb"\x8b\x5e\xfe\xe8(..)\x0b\xc0\x75\x0f\x6b\x1e\xbc\x00\x06", re.S)
SIG_WIN = re.compile(rb"\x8b\x46\x04\x03\x06\x24\x06\x89\x46\xfa")
SIG_LOG = re.compile(rb"\x8e\x06\x34\x2f\x8b\xf0\x03\x36\x24\x06")


def unpack_program(exe):
    return exepack.unpack(exe) if exepack.is_packed(exe) else bytes(exe)


def _ds(img):
    return DS_PARA * 16


def table(img):
    return img[_ds(img) + TABLE:_ds(img) + TABLE + 512]


def inserts(img):
    """{X byte: (DS place, bytes up to the NUL)} of the strings 02 X puts in ('0'-'d')."""
    out = {}
    for x in range(0x30, 0x65):
        p = struct.unpack_from("<H", img, _ds(img) + INSERTS + 2 * x)[0]
        s = img[_ds(img) + p:img.index(b"\0", _ds(img) + p)]
        out[x] = (p, bytes(s))
    return out


def load(data):
    """(n, n2, records [[op, a, b]], the text area: two bytes (where its length word was) and the text,
    so that a record's place plus 2 is its string's place in it)."""
    n, n2 = struct.unpack_from("<HH", data, 4)
    recs = [list(struct.unpack_from("<HHH", data, 8 + 6 * k)) for k in range(n + n2)]
    t = 8 + 6 * (n + n2)
    return n, n2, recs, bytes(data[t:t + 2]) + bytes(b ^ 0x7F for b in data[t + 2:])


def save(data, recs, area):
    """The script with these records and text area (its length word set; the text XOR 7Fh)."""
    out = bytearray(data[:8])
    for op, a, b in recs:
        out += struct.pack("<HHH", op, a, b)
    return bytes(out) + struct.pack("<H", len(area) - 2) + bytes(b ^ 0x7F for b in area[2:])


def text_end(area, s):
    return area.index(b"\0", s)


def strings(data):
    """[(kind, field index k, 'a' or 'b', place in the area)] of the messages and choices."""
    n, _n2, recs, _area = load(data)
    out = []
    for k, (op, a, b) in enumerate(recs):
        if k < n and op & 0xFF == MSG_OPS_LOW and b != 0xFFFF:
            out.append(("msg", k, "b", b + 2))
        elif k >= n and op == CHOICE_OP and a != 0xFFFF:
            out.append(("choice", k, "a", a + 2))
    return out


def show(raw, tab):
    """A text as strings.json shows it: \\n a new line, {Nx} what 02 x puts in."""
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if b == 1:
            out.append("{01}")
            i += 1
        elif b == 2:
            out.append("{N%s}" % chr(raw[i + 1]))
            i += 2
        elif b == 0x0A:
            out.append("\n")
            i += 1
        elif b == 0x5C:
            out.append(bytes([raw[i + 1]]).decode("cp932", "replace"))
            i += 2
        elif tab[2 * b]:
            out.append(bytes(tab[2 * b:2 * b + 2]).rstrip(b"\0").decode("cp932", "replace"))
            i += 1
        else:
            out.append(raw[i:i + 2].decode("cp932", "replace"))
            i += 2
    return "".join(out)


def spell_out(raw, tab):
    """A Japanese text's bytes with its ASCII-byte characters written as Shift-JIS (the table's ASCII
    entries become the letters themselves)."""
    out, i = bytearray(), 0
    while i < len(raw):
        b = raw[i]
        if b == 2 or b == 0x5C:
            out += raw[i:i + 2]
            i += 2
        elif b in (1, 0x0A):
            out.append(b)
            i += 1
        elif tab[2 * b]:
            if 0x20 <= b < 0x7F:
                ch = bytes(tab[2 * b:2 * b + 2])
                out += ch if ch[1] else b"\\" + ch[:1]
            else:
                out.append(b)
            i += 1
        else:
            out += raw[i:i + 2]
            i += 2
    return bytes(out)


TOKEN = re.compile(r"\{N(.)\}|\{01\}")
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\\": "/", "　": " ",
         "「": '"', "」": '"', "『": '"', "』": '"', "【": "[", "】": "]"}


def _ascii(text):
    t = "".join(SUBST.get(c, c) for c in text)
    return "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in t)


def _cells(piece, names):
    m = TOKEN.fullmatch(piece)
    if m:
        return len(names.get(m.group(1), "")) if m.group(1) else 0
    return len(piece)


def english(text, names=None, width=WIDTH):
    """A message's English as its bytes: ASCII, lines broken between words at width cells (0Ah between
    them), {Nx} as 02 x."""
    names = names or {}
    lines = []
    for para in text.split("\n"):
        cur, w = [], 0
        for word in para.split(" "):
            ww = sum(_cells(p, names) for p in re.findall(r"\{N.\}|\{01\}|[^{]+|\{", word))
            if cur and w + 1 + ww > width:
                lines.append(" ".join(cur))
                cur, w = [], 0
            cur.append(word)
            w += ww + (1 if len(cur) > 1 else 0)
        lines.append(" ".join(cur))
    out = bytearray()
    for k, ln in enumerate(lines):
        if k:
            out.append(0x0A)
        for p in re.findall(r"\{N.\}|\{01\}|[^{]+|\{", ln):
            m = TOKEN.fullmatch(p)
            if m:
                out += bytes([2, ord(m.group(1))]) if m.group(1) else b"\x01"
            else:
                out += _ascii(p).encode("ascii")
    return bytes(out)


def msg_file(texts):
    """(the .MSG file's bytes, [each text's paragraph]): each text and its NUL from a paragraph's start."""
    out, paras = bytearray(), []
    for t in texts:
        paras.append(len(out) // 16)
        out += t + b"\0"
        out += bytes(-len(out) % 16)
    return bytes(out), paras


# ---- the program ----

def _asm(src, org):
    code, _n = Ks(KS_ARCH_X86, KS_MODE_16).asm(src, org)
    return bytes(code)


def patch_program(exe, need_paras):
    """MDMAIN.EXE unpacked, with the table's ASCII entries the letters themselves and the helpers that
    read the messages from STY_nn.MSG (need_paras: the paragraphs the largest takes)."""
    u = bytearray(unpack_program(exe))
    base = struct.unpack_from("<H", u, 8)[0] * 16
    img = bytearray(u[base:])
    ds = _ds(img)
    for c in range(0x20, 0x7F):
        if c != 0x5C:
            img[ds + TABLE + 2 * c:ds + TABLE + 2 * c + 2] = bytes([c, 0])

    def once(sig, what):
        hits = list(sig.finditer(bytes(img[:TEXT_SEG * 16])))
        if len(hits) != 1:
            raise SystemExit("MDMAIN.EXE: the %s is found %d times, not once" % (what, len(hits)))
        return hits[0]
    m = once(SIG_LOAD, "script loader's call of the text reader")
    call = m.start() + 3
    reader = (call + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
    win = once(SIG_WIN, "message window's text place").start() + 3
    log = once(SIG_LOG, "log's text place").start() + 6
    if not TEXT_SEG * 16 + 0x200 < HELPERS < 0x10000 - 0x100:
        raise SystemExit("MDMAIN.EXE: no room for the helpers")
    mbase, name = HELPERS, HELPERS + 2
    load_src = """
            push ax
            push bx
            push cx
            push dx
            push si
            push di
            push es
            push ds
            push cs
            pop es
            mov di, 0x%x
            lea si, [bp - 0x4a]
        copy:
            mov al, ss:[si]
            inc si
            cmp al, 0x2e
            je ext
            or al, al
            je ext
            stosb
            jmp copy
        ext:
            mov al, 0x2e
            stosb
            mov al, 0x4d
            stosb
            mov al, 0x53
            stosb
            mov al, 0x47
            stosb
            xor al, al
            stosb
            mov ax, cs:[0x%x]
            or ax, ax
            jne have
            mov ah, 0x48
            mov bx, 0x%x
            int 0x21
            jc done
            mov cs:[0x%x], ax
        have:
            push cs
            pop ds
            mov dx, 0x%x
            mov ax, 0x3d00
            int 0x21
            jc done
            mov bx, ax
            mov ax, cs:[0x%x]
            mov ds, ax
        more:
            xor dx, dx
            mov cx, 0x8000
            mov ah, 0x3f
            int 0x21
            jc shut
            cmp ax, 0x8000
            jne shut
            mov dx, ds
            add dx, 0x800
            mov ds, dx
            jmp more
        shut:
            mov ah, 0x3e
            int 0x21
        done:
            pop ds
            pop es
            pop di
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            .byte 0xc3
    """
    win_src = """
            add ax, cs:[0x%x]
            mov word ptr [0x2f34], ax
            xor ax, ax
            .byte 0xc3
    """ % mbase
    log_src = """
            add ax, cs:[0x%x]
            mov word ptr [0x2f34], ax
            mov es, ax
            xor si, si
            .byte 0xc3
    """ % mbase
    at = HELPERS + 0x60
    load_at = at
    # (keystone makes a near call and ret 32-bit: the call to the reader is written by hand, ret as C3h)
    load = bytes([0xE8]) + struct.pack("<H", (reader - (load_at + 3)) & 0xFFFF)
    load += _asm(load_src % (name, mbase, need_paras, mbase, name, mbase), load_at + 3)
    win_at = load_at + len(load)
    winc = _asm(win_src, win_at)
    log_at = win_at + len(winc)
    logc = _asm(log_src, log_at)
    code = load + winc + logc
    if log_at + len(logc) > 0x10000 or 0x66 in code:
        raise SystemExit("MDMAIN.EXE: no room for the helpers")
    img[HELPERS:HELPERS + 0x60] = bytes(0x60)
    img[load_at:load_at + len(code)] = code
    struct.pack_into("<H", img, call + 1, (load_at - (call + 3)) & 0xFFFF)
    img[win:win + 4] = bytes([0xE8]) + struct.pack("<H", (win_at - (win + 3)) & 0xFFFF) + bytes([0x90])
    img[log:log + 4] = bytes([0xE8]) + struct.pack("<H", (log_at - (log + 3)) & 0xFFFF) + bytes([0x90])
    # (the readers' loads of the text's segment, 0962h, read from [2F34h]; their fixups taken out)
    lo, hi = log - 0x20, win + 0x200
    seg = struct.pack("<H", TEXT_SEG)
    sites = [k for k in range(lo, hi) if img[k] == 0xB8 and img[k + 1:k + 3] == seg]
    if len(sites) != 4:
        raise SystemExit("MDMAIN.EXE: the readers load the text's segment %d times, not 4" % len(sites))
    for k in sites:
        img[k:k + 3] = bytes([0xA1, 0x34, 0x2F])
    hdr = list(struct.unpack_from("<14H", u, 0))
    relocs = [struct.unpack_from("<HH", u, hdr[12] + 4 * r) for r in range(hdr[3])]
    keep = [(o, sg) for o, sg in relocs if sg * 16 + o not in {k + 1 for k in sites}]
    if len(keep) != len(relocs) - 4:
        raise SystemExit("MDMAIN.EXE: the readers' segment loads are not each fixed up once")
    head = bytearray(u[:base])
    for r, (o, sg) in enumerate(keep + [(0, 0)] * (len(relocs) - len(keep))):
        struct.pack_into("<HH", head, hdr[12] + 4 * r, o, sg)
    hdr[3] = len(keep)
    struct.pack_into("<14H", head, 0, *hdr)
    return bytes(head + img)
