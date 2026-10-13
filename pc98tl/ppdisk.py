"""PP Disk (Mediax / P's PSYTEC, 1994): the disk magazine's viewer, PPDISK.EXE ("月刊ＰＰディスク
Version 2.0", the same program on every disk), and its two files on each disk.

PPDISK.SCR, the menus (read whole at start):
  header: ten words, the counts of the sections that follow it, in this order (the last one the
  string pool's size in bytes):
    menus          count * 42h: a title (pool offset) and 8 items of 8 bytes: label (pool offset,
                   negative: none), type, argument (a dword)
    balloons       0Bh * 0Ch, fixed: Pia's speech balloons, 6 lines each (pool offsets, negative:
                   no line), drawn 16 letters wide at x=500
    c8e            count * 8      b20   count * 4      b16  count * 24h
    lists          count * 4: {entries, first}, into the next section
    entries        count * 6: {type, argument (a dword)}: type 1 shows a page of PPDISK.TXT (the
                   dword its offset), type 2 a picture (a pool offset: the file name)
    b18            count * 16h    b1a   count * 4      b14  count * 30h
    pool           the strings, NUL-terminated: menu titles and labels, balloon lines, file names
  A menu item of type 3 shows an article (the dword its offset in PPDISK.TXT), type 7 a list,
  type 2 another menu.  The program relocates every pool offset to the pool's address when it
  loads it (it is malloc'd, its size the header's last word), so the pool can grow.

PPDISK.TXT, the text: records of a word (n) and n bytes, lines each ended by NUL.  A record is read
into a buffer of 32 KB (DS:2438h) and 0FFh put after it.  Two viewers:
  articles (menu type 3)     a box 46 letters wide (x=48h), 8 lines to a page
  pages (list type 1, and record 0: the replay mode's help)   the whole screen, 80 x 24
Both note where each page starts in a table of 32 entries on the stack.  The patch moves the tables
to the buffer's last 200h bytes (256 pages), every read into the buffer stopping short of them
(7E00h instead of 8000h), so a record may take 7DFFh bytes.

The program's own messages are in its data segment, NUL-terminated; ASCII (20h-7Fh) is drawn
half-width by its text routine, Shift-JIS full-width.
"""
import struct

BUF = 0x2438
BUF_END = 0xA438
PAGE_TABLE = BUF_END - 0x200          # 256 page starts
RECORD_MAX = PAGE_TABLE - BUF - 1      # the 0FFh after a record stays below the table
ARTICLE = (46, 8)                      # letters to a line, lines to a page
PAGE = (80, 24)
BALLOON = (16, 6)
TITLE_CELLS = 36                       # a menu's title box: x=20h to 140h
LABEL_CELLS = 46                       # a menu item: x=48h to the box's edge at 1B8h

SECTIONS = [("menus", 0x42), ("balloons", None), ("c8e", 8), ("b20", 4), ("b16", 0x24),
            ("lists", 4), ("entries", 6), ("b18", 0x16), ("b1a", 4), ("b14", 0x30)]

# reads into the buffer: push 8000h; push 2438h (or mov ax, 2438h)
READ_SIGS = (bytes.fromhex("680080683824"), bytes.fromhex("680080b83824"))
# the viewers' page tables: lea dx,[bp-t]; lea ax,[bp-e] (filling it), lea bx,[bp+di-t];
# mov si,ss:[bx+di] (reading it)
TABLES = ((bytes.fromhex("8d56b68d46f6"), bytes.fromhex("8d5bb6368b31")),     # articles
          (bytes.fromhex("8d56b88d46f8"), bytes.fromhex("8d5bb8368b31")))     # pages


def sections(scr):
    h = struct.unpack_from("<10H", scr, 0)
    counts = dict(zip(["menus", "c8e", "b20", "b16", "lists", "entries", "b18", "b1a", "b14", "pool"], h))
    at, o = {}, 0x14
    for name, size in SECTIONS:
        n = 0x84 if size is None else counts[name] * size
        at[name] = (o, n)
        o += n
    at["pool"] = (o, counts["pool"])
    if o + counts["pool"] != len(scr):
        raise ValueError("PPDISK.SCR: sections end at %x, the file at %x" % (o + counts["pool"], len(scr)))
    for name in ("b16", "b18"):
        if counts[name]:
            raise ValueError("PPDISK.SCR: a %s section (not in this game's disks)" % name)
    return at


def menus(scr):
    """[(menu, title offset pos, [(item, label pos, type, arg pos)])]"""
    at = sections(scr)
    o, n = at["menus"]
    out = []
    for m in range(n // 0x42):
        b = o + m * 0x42
        items = [(k, b + 2 + 8 * k, struct.unpack_from("<H", scr, b + 4 + 8 * k)[0], b + 6 + 8 * k)
                 for k in range(8)]
        out.append((m, b, items))
    for m, b, items in out:
        for k, lp, t, ap in items:
            if t in (4, 5):
                raise ValueError("PPDISK.SCR: menu %d item %d of type %d (not in this game's disks)" % (m, k, t))
    return out


def word(scr, pos):
    return struct.unpack_from("<h", scr, pos)[0]


def balloons(scr):
    """[[line pos (6)] for each balloon]"""
    o = sections(scr)["balloons"][0]
    return [[o + 12 * b + 2 * k for k in range(BALLOON[1])] for b in range(11)]


def txt_fields(scr):
    """[(pos of the dword, viewer)]: every PPDISK.TXT offset the menus and lists name."""
    out = []
    for m, b, items in menus(scr):
        for k, lp, t, ap in items:
            if t == 3:
                out.append((ap, "article"))
    o, n = sections(scr)["entries"]
    for e in range(n // 6):
        if struct.unpack_from("<H", scr, o + 6 * e)[0] == 1:
            out.append((o + 6 * e + 2, "page"))
    return out


def records(txt):
    """[(offset, record bytes)]"""
    out, q = [], 0
    while q < len(txt):
        n = struct.unpack_from("<H", txt, q)[0]
        out.append((q, txt[q + 2:q + 2 + n]))
        q += 2 + n
    if q != len(txt):
        raise ValueError("PPDISK.TXT: a record runs past the file's end")
    return out


def lines(rec):
    if rec and rec[-1:] != b"\x00":
        raise ValueError("PPDISK.TXT: a record not ended by NUL")
    return rec[:-1].split(b"\x00") if rec else []


def viewers(scr, txt):
    """{record offset: "article" | "page"}, every record but 0 named by the menus; record 0 is the
    replay mode's help (a page)."""
    seen = {}
    for pos, v in txt_fields(scr):
        off = struct.unpack_from("<I", scr, pos)[0]
        if seen.get(off, v) != v:
            raise ValueError("PPDISK.TXT %x: shown by both viewers" % off)
        seen[off] = v
    offs = [o for o, r in records(txt)]
    missing = [hex(o) for o in offs if o and o not in seen]
    stray = [hex(o) for o in seen if o not in offs]
    if missing or stray:
        raise ValueError("PPDISK.SCR names records %s that are not, and not %s that are" % (stray, missing))
    seen.setdefault(0, "page")
    return seen


def pool_strings(scr):
    """{pool offset: bytes} for every string the menus and balloons name."""
    at = sections(scr)
    po, pn = at["pool"]
    pool = scr[po:]
    out = {}

    def take(off):
        if off >= 0:
            out[off] = pool[off:pool.index(b"\x00", off)]
    for m, b, items in menus(scr):
        take(word(scr, b))
        for k, lp, t, ap in items:
            take(word(scr, lp))
    for bl in balloons(scr):
        for p in bl:
            take(word(scr, p))
    return out


def patch_exe(exe):
    """The page tables moved out of the stack (see the docstring); refuses an unknown program."""
    out = bytearray(exe)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    n = 0
    for sig in READ_SIGS:
        at = exe.find(sig, hdr)
        while at >= 0:
            struct.pack_into("<H", out, at + 1, PAGE_TABLE - BUF)
            n += 1
            at = exe.find(sig, at + 1)
    if n != 4:
        raise SystemExit("PPDISK.EXE: %d reads into the text buffer found, 4 expected" % n)
    for fill, read in TABLES:
        for sig in (fill, read):
            if exe.count(sig) != 1:
                raise SystemExit("PPDISK.EXE: a viewer's page table not found")
        at = exe.find(fill)
        out[at:at + 6] = b"\xba" + struct.pack("<H", PAGE_TABLE) + b"\xb8" + struct.pack("<H", PAGE_TABLE + 0x200)
        at = exe.find(read)
        out[at:at + 6] = b"\x89\xfb\x8b\xb1" + struct.pack("<H", PAGE_TABLE)
    return bytes(out)
