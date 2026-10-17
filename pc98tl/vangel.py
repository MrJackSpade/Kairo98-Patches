"""Crystal Soft's Virgin Angel (V_ANGEL\\M.EXE, `m cmd00.scb gdata.lib`): its text (CMD00.TXB), and English
drawn half-width.

CMD00.TXB (`decode`, `encode`): "CRTX", then every byte complemented: the texts end to end, each ended by
1Ah (M.EXE finds each one's place by reading through the file; the count is CMD00.SCB's, which is kept).
A text is lines, each ended by 00h:

* a line of 12h alone: the page ends (a wait, the window cleared);
* a line 13h and a name: a speaker's lines follow, up to the line ending with \\e; the program draws the
  first as name「line and the others under it;
* an empty line: a blank line;
* text: Shift-JIS, and single bytes M.EXE expands: A0h-DFh and 41h-5Ah the 64 and 26 most frequent
  characters (`KANA`, a table in M.EXE, read by `kana_table`).

The message window's lines are as the text breaks them; the program centres each line on the screen.

English (`text`, `patch_program`): two letters a character, as two-byte codes whose lead is one of the
26 Shift-JIS leads no text uses (`LEADS`); the program's glyph routines (int 18h AH=14h after converting
the code to JIS) are made to call, in place of that BIOS call, a helper in a segment put in before
DGROUP (pc98tl/adl5.py `_move_up`) that draws such a code from two 8x16 BIOS glyphs.  The patcher
breaks the English between words (`WIDTH` letters a line, less a speaker's name), pads a page's lines
to one length (so they are centred as one), and starts a new page after `PAGE` lines (a speaker's lines
going on under their name again).  M.EXE is written unpacked.
"""
import re
import struct

from .adl5 import _move_up
from .kuro import _asm16, _exe
from . import exepack

HEAD = b"CRTX"
LETTERS = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,'!?-"
LEADS = [0x84, 0x85, 0x86, 0x87, 0xE0, 0xE2, 0xE6, 0xEA] + list(range(0xEB, 0xFD))
TRAILS = [t for t in range(0x40, 0xFD) if t != 0x7F]
WIDTH = 56                  # letters a line (28 characters)
PAGE = 4                    # lines a page
LIMIT = 0x1FFF              # a text's longest (M.EXE's text buffer)
PAGE_LINE, SPEAKER, END = b"\x12", b"\x13", b"\\e"
assert len(LETTERS) ** 2 <= len(LEADS) * len(TRAILS)


def decode(data):
    if not data.startswith(HEAD):
        raise ValueError("not a CRTX file")
    return bytes(~b & 0xFF for b in data[4:])


def encode(t):
    return HEAD + bytes(~b & 0xFF for b in t)


def texts(t):
    """The texts (each without its 1Ah) and what follows the last one."""
    parts = t.split(b"\x1a")
    return parts[:-1], parts[-1]


def join(parts, tail):
    return b"".join(p + b"\x1a" for p in parts) + tail


# the expansion table: 90 Shift-JIS characters (M.EXE: mov ax, seg / mov es, ax / shl bx, 1 /
# mov ax, es:[bx-140h], for A0h-DFh)
KANA_SIG = re.compile(rb"\xb8(..)\x8e\xc0\xd1\xe3\x26\x8b\x87\xc0\xfe", re.S)


def kana_table(image):
    m = KANA_SIG.search(image)
    if not m:
        raise SystemExit("M.EXE: the expansion table's signature is not found")
    at = struct.unpack("<H", m.group(1))[0] * 16
    return [image[at + 2 * k:at + 2 * k + 2] for k in range(90)]


def is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def expand(line, kana):
    """A line's Shift-JIS (its single-byte characters expanded)."""
    out, i = bytearray(), 0
    while i < len(line):
        b = line[i]
        if is_lead(b) and i + 1 < len(line):
            out += line[i:i + 2]
            i += 2
            continue
        if 0xA0 <= b <= 0xDF:
            out += kana[b - 0xA0]
        elif 0x41 <= b <= 0x5A:
            out += kana[64 + b - 0x41]
        else:
            out.append(b)
        i += 1
    return bytes(out)


def show(line, kana):
    """A line as strings.json shows it (#, $ and %, the long dash's start, middle and end, as ー)."""
    t = expand(line, kana)
    t = re.sub(rb"[#$%]", "ー".encode("cp932"), t)
    return t.decode("cp932", "replace").replace(chr(9), "")


def is_control(line):
    """A line of control bytes only (14h...): kept as it is, no line of the window."""
    return bool(line) and all(b < 0x20 for b in line) and line != PAGE_LINE


def units(text):
    """[(kind, [line numbers])] of a text: name (a speaker's), dlg (the speaker's lines, up to \\e), msg
    (narration: lines up to a blank line, a page's end or a speaker)."""
    lines = text.split(b"\0")
    out, run, speech = [], [], None
    for n, line in enumerate(lines):
        if speech is not None:
            speech.append(n)
            if line.endswith(END):
                out.append(("dlg", speech))
                speech = None
            continue
        if line == PAGE_LINE or line == b"" or line.startswith(SPEAKER) or is_control(line):
            if run:
                out.append(("msg", run))
                run = []
            if line.startswith(SPEAKER):
                out.append(("name", [n]))
                speech = []
            continue
        run.append(n)
    if run:
        out.append(("msg", run))
    if speech:
        out.append(("dlg", speech))
    return out


def unit_bytes(text, kind, nums):
    """A unit's Japanese: its lines joined (a name without its 13h, a speech without its \\e)."""
    lines = text.split(b"\0")
    if kind == "name":
        return lines[nums[0]][1:]
    b = b"".join(lines[n] for n in nums)
    if kind == "dlg" and b.endswith(END):
        b = b[:-2]
    return b


def _normal(text):
    subst = {"’": "'", "‘": "'", "“": "'", "”": "'", '"': "'", "—": "-", "–": "-", "…": "...",
             ":": ",", ";": ",", "(": "-", ")": "-"}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if c in LETTERS or c == "\n" else "?" for c in s)


def pairs(letters):
    if len(letters) % 2:
        letters += " "
    out = bytearray()
    for k in range(0, len(letters), 2):
        n = LETTERS.index(letters[k]) * len(LETTERS) + LETTERS.index(letters[k + 1])
        out += bytes([LEADS[n // len(TRAILS)], TRAILS[n % len(TRAILS)]])
    return bytes(out)


def wrap(text, width):
    """English broken between words into lines of at most `width` letters (\\n a new line)."""
    lines = []
    for para in _normal(text).split("\n"):
        line = ""
        for word in para.split():
            while len(word) > width:
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def text(old, english, kana):
    """A text written again with English: english {(kind, first line number): English}.  A unit with
    English is broken into lines (a speaker's lines narrower by the name), padded to one length on each
    page and paged after PAGE lines (a speaker's lines going on under the name again); the rest is kept."""
    lines = old.split(b"\0")
    plan = units(old)
    starts = {nums[0]: (kind, nums) for kind, nums in plan}
    name_line = {}
    for k, (kind, nums) in enumerate(plan):
        if kind == "name" and k + 1 < len(plan) and plan[k + 1][0] == "dlg":
            name_line[plan[k + 1][1][0]] = nums[0]
    out, count, speaker, n = [], 0, None, 0

    def emit(seg, end):
        w = max(len(x) for x in seg)
        for k, x in enumerate(seg):
            out.append(pairs(x.ljust(w)) + (END if end and k == len(seg) - 1 else b""))

    while n < len(lines):
        line = lines[n]
        unit = starts.get(n)
        en = english.get((unit[0], n)) if unit else None
        if unit and unit[0] == "name":
            if count >= PAGE:
                out.append(PAGE_LINE)
                count = 0
            speaker = SPEAKER + pairs(_normal(en)) if en else line
            out.append(speaker)
            n += 1
            continue
        if unit and en:
            kind, nums = unit
            width = WIDTH
            if kind == "dlg":
                nl = name_line.get(n)
                nm = english.get(("name", nl)) if nl is not None else None
                cells = ((len(_normal(nm)) + 1) // 2 if nm else
                         len(expand(lines[nl][1:], kana)) // 2 if nl is not None else 0)
                width = max(8, WIDTH - 2 * (cells + 1))
            seg = []
            for piece in wrap(en, width):
                if count >= PAGE:
                    if seg:
                        emit(seg, kind == "dlg")
                        seg = []
                    out.append(PAGE_LINE)
                    count = 0
                    if kind == "dlg" and speaker:
                        out.append(speaker)
                seg.append(piece)
                count += 1
            if seg:
                emit(seg, kind == "dlg")
            n = nums[-1] + 1
            continue
        if line == PAGE_LINE:
            count = 0
        elif not line.startswith(SPEAKER) and not is_control(line):
            count += 1
        out.append(line)
        n += 1
    return b"\0".join(out)


# ---- M.EXE ---------------------------------------------------------------------------------------------

# the glyph routines' BIOS call: mov dx, ax (the JIS code; or mov dx, [bp+6]) / mov bx, ss /
# lea cx, [bp+d] / mov ah, 14h / int 18h
GLYPH_SIG = re.compile(rb"(\x8b\xd0|\x8b\x56\x06)\x8c\xd3\x8d(?:\x4e(.)|\x8e(..))\xb4\x14\xcd\x18", re.S)
# the entry's data segment: mov di, DGROUP (MS C's startup)
ENTRY_SIG = re.compile(rb"\xb4\x30\xcd\x21\x3c\x02\x73\x05\x33\xc0\x06\x50\xcb\xbf(..)", re.S)

SITE = """
site{n}:
    {load}
    mov bx, ss
    lea cx, [bp {disp}]
    jmp common
"""

COMMON = """
common:
    push ax
    push si
    mov al, dh
    sub al, 0x21
    mov ah, al
    shr al, 1
    add al, 0x81
    cmp al, 0x9f
    jbe c_lead
    add al, 0x40
c_lead:
    test ah, 1
    mov ah, dl
    jnz c_even
    add ah, 0x1f
    cmp ah, 0x7f
    jb c_trail
    inc ah
    jmp c_trail
c_even:
    add ah, 0x7e
c_trail:
    xor bh, bh
    mov bl, al
    mov bl, byte ptr cs:[bx + {leadix}]
    cmp bl, 0xff
    jne pair
    mov bx, ss
    pop si
    pop ax
    mov ah, 0x14
    int 0x18
    .byte 0xcb
pair:
    push cx
    push dx
    push di
    mov si, cx
    mov dl, ah
    mov al, bl
    mov ah, {ntrail}
    mul ah
    xor dh, dh
    mov bx, dx
    add al, byte ptr cs:[bx + {trailix}]
    adc ah, 0
    mov cl, {nletter}
    div cl
    push ax
    xor bh, bh
    mov bl, al
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov bx, cs
    mov cx, {g1}
    mov ah, 0x14
    int 0x18
    pop ax
    xor bh, bh
    mov bl, ah
    mov dl, byte ptr cs:[bx + {letters}]
    mov dh, 0x80
    mov bx, cs
    mov cx, {g2}
    mov ah, 0x14
    int 0x18
    mov byte ptr ss:[si], 2
    mov byte ptr ss:[si + 1], 2
    xor di, di
    mov cx, 16
fill:
    mov al, byte ptr cs:[di + {g1} + 2]
    mov byte ptr ss:[si + 2], al
    mov al, byte ptr cs:[di + {g2} + 2]
    mov byte ptr ss:[si + 3], al
    inc di
    add si, 2
    loop fill
    pop di
    pop dx
    pop cx
    mov bx, ss
    pop si
    pop ax
    .byte 0xcb
"""


def dgroup(img):
    for k in range(0, len(img) - 16):
        m = ENTRY_SIG.match(bytes(img[k:k + 16]))
        if m:
            return struct.unpack("<H", m.group(1))[0]
    raise SystemExit("M.EXE: the startup's DGROUP is not found")


def plain(exe):
    """M.EXE as a plain MZ program (EXEPACK undone)."""
    return exepack.unpack(exe) if exepack.is_packed(exe) else exe


def patch_program(exe, places):
    """M.EXE, unpacked, with its strings' English (places [(image offset, bytes)]) and the half-width
    helper (see the module's docstring)."""
    exe = bytearray(plain(exe))
    hdr, rel_at, _img, fixups = _exe(bytes(exe))
    if rel_at + 4 * (len(fixups) + 4) > hdr:
        # (the header made a paragraph longer for the four relocation entries the calls add)
        exe[hdr:hdr] = bytes(16)
        struct.pack_into("<H", exe, 8, hdr // 16 + 1)
    hdr, rel_at, img, fixups = _exe(bytes(exe))
    for at, b in places:
        img[at:at + len(b)] = b
    dg = dgroup(img)
    sites = []
    for m in GLYPH_SIG.finditer(bytes(img[:dg * 16])):
        disp = struct.unpack("b", m.group(2))[0] if m.group(2) is not None else struct.unpack("<h", m.group(3))[0]
        load = "mov dx, ax" if m.group(1) == b"\x8b\xd0" else "mov dx, word ptr [bp + 6]"
        sites.append((m.start(), m.end(), disp, load))
    if len(sites) != 4:
        raise SystemExit("M.EXE: %d glyph routines found, not 4" % len(sites))
    letters = LETTERS.encode("ascii")
    leadix = bytes(LEADS.index(b) if b in LEADS else 0xFF for b in range(256))
    trailix = bytes(TRAILS.index(b) if b in TRAILS else 0 for b in range(256))

    def source(base):
        src = "".join(SITE.format(n=n, load=load, disp=("+ %d" % d if d >= 0 else "- %d" % -d))
                      for n, (_a, _e, d, load) in enumerate(sites))
        return src + COMMON.format(leadix=hex(base), trailix=hex(base + 256), letters=hex(base + 512),
                                   g1=hex(base + 512 + 70), g2=hex(base + 512 + 70 + 0x14),
                                   ntrail=len(TRAILS), nletter=len(LETTERS))
    names = ["site%d" % n for n in range(len(sites))]
    code, _a = _asm16(source(0x400), 0, names)
    base = len(code) + (-len(code) % 16)
    code, addr = _asm16(source(base), 0, names)
    room = code + bytes(base - len(code)) + leadix + trailix + letters.ljust(70, b"\0") + bytes(0x28)
    paras = -(-len(room) // 16)
    new_rel = []
    for n, (a, e, _d, _l) in enumerate(sites):
        seg = max(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v * 16 <= a)
        img[a:e] = b"\x9a" + struct.pack("<HH", addr["site%d" % n], dg) + b"\x90" * (e - a - 5)
        new_rel.append((a + 3 - seg * 16, seg))
    out = bytearray(_move_up(bytes(exe), hdr, img, fixups, rel_at, dg, paras, room, "M.EXE"))
    nrel = struct.unpack_from("<H", out, 6)[0]
    if rel_at + 4 * (nrel + len(new_rel)) > hdr:
        raise SystemExit("M.EXE: no room in the header for the new relocation entries")
    for j, (o, sg) in enumerate(new_rel):
        struct.pack_into("<HH", out, rel_at + 4 * (nrel + j), o, sg)
    struct.pack_into("<H", out, 6, nrel + len(new_rel))
    return bytes(out)


# M.EXE's own strings: 0-ended Shift-JIS with kana or kanji in them, after its code; console ones (printed
# by DOS before the graphics start, or on a fatal error) are ASCII, the others drawn as text is
CONSOLE = ("初期化に失敗", "指定して", "Warning", "マウスを使用", "ロード中", "不足", "変です")
STRING = re.compile(rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x0a\x0d]){3,}(?=\x00)")


def program_strings(image, kana_at):
    """[(offset, end, console)] of M.EXE's strings: from the first one with kana (after a 0) on, past its
    code (the expansion table at kana_at skipped)."""
    out = []
    start = None
    for m in STRING.finditer(image):
        try:
            t = image[m.start():m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        if image[m.start() - 1] == 0 and sum(1 for c in t if "ぁ" <= c <= "ヶ") >= 3:
            start = m.start()
            break
    if start is None:
        raise SystemExit("M.EXE: its strings are not found")
    for m in STRING.finditer(image, start):
        s, e = m.start(), m.end()
        if kana_at <= s < kana_at + 180:
            continue
        try:
            t = image[s:e].decode("cp932")
        except UnicodeDecodeError:
            continue
        if sum(1 for c in t if "぀" <= c <= "ヿ" or "一" <= c <= "鿿") < 2:
            continue
        out.append((s, e, any(w in t for w in CONSOLE)))
    return out
