"""D.O.'s ARQ98.EXE (Arquelphos 1994, Yuu Disk Vol. 9): its messages, held in the program.

The program draws text with ADL5's run (pc98tl/adl5.py patches it: RUN_SIG_ARQ) and keeps its
messages in its data segment:

* A top table of word offsets, one per group (a scene); each points to the group's own table of
  word offsets, one per message, followed by the group's messages (the next group's table right
  after them).  All offsets are from the data segment's start.
* The routine that shows messages (al: the group, bx: the first message, cx: how many) reads the
  tables through ds (the data segment: push es / mov dx, seg / mov es, dx / mov dx, ax /
  xor ah, ah / add ax, ax / mov si, top / add si, ax / mov si, [si] / add bx, bx / add si, bx /
  push cx / push si / mov si, [si] / call run / pop si / pop cx / add si, 2 / loop / pop es / ret)
  and runs each message with es:si.
* A message: controls (01h-0Bh, one byte each: 02 a key wait, 03 the window cleared, 06 a new line,
  07h and 08h an animation...), then FFh and a run of text (ADL's characters: Shift-JIS, a byte
  under 80h a kana by the program's table) up to 00, again and again; a 00 after the controls (or
  a byte of 0Ch and up that is not FFh) ends it.

The patch rebuilds the whole block (the top table, the group tables, the messages) in a segment of
its own, put in after the program's image (the work segments after it move up), and rewrites the
routine in its own bytes to read the tables through es as well (the top table at 0: mov si, ax
where it added the table's offset; es: before both reads): the messages may grow to 64 KB.  The
block in the data segment stays as it was, unread.
"""
import re
import struct

TEXT_MARK = 0xFF
CTRL_END = 0x0C
# the routine that shows messages: push es / mov dx, seg / mov es, dx / mov dx, ax / xor ah, ah /
# add ax, ax / mov si, top / add si, ax / mov si, [si] / add bx, bx / add si, bx
SHOW_SIG = re.compile(rb"\x06\xba(..)\x8e\xc2\x8b\xd0\x32\xe4\x03\xc0\xbe(..)\x03\xf0\x8b\x34\x03\xdb\x03\xf3"
                      rb"\x51\x56\x8b\x34\xe8(..)\x5e\x59\x83\xc6\x02\xe2\xf2\x07\xc3", re.S)
ROOM_MAX = 0x10000


class Bad(Exception):
    pass


def _image(exe):
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    return hdr, exe[hdr:]


def find(exe):
    """(the data segment (paragraph, as in the image), the top table's offset, the routine's offset in
    the image (the signature's start))."""
    hdr, img = _image(exe)
    found = list(SHOW_SIG.finditer(img))
    if len(found) != 1:
        raise SystemExit("ARQ98.EXE: the message routine is found %d times, not once" % len(found))
    m = found[0]
    return struct.unpack("<H", m.group(1))[0], struct.unpack("<H", m.group(2))[0], m.start()


def parse_end(d, start):
    """The end of the message at start (just past the 00 or byte that ends it)."""
    j = start
    while True:
        if d[j] == 0:
            return j + 1
        while True:
            b = d[j]
            j += 1
            if b == 0 or b >= CTRL_END:
                break
        if b == TEXT_MARK:
            j = d.index(0, j) + 1
            continue
        return j


def groups(exe):
    """[(the group table's offset, [(message start, end)])] (offsets in the data segment)."""
    hdr, img = _image(exe)
    seg, top, _at = find(exe)
    d = img[seg * 16:]
    tops = []
    at = top
    while True:
        t = struct.unpack_from("<H", d, at)[0]
        if tops and t <= tops[-1] or t >= len(d):
            break
        tops.append(t)
        at += 2
    out = []
    for g, t in enumerate(tops):
        first = struct.unpack_from("<H", d, t)[0]
        offs = [struct.unpack_from("<H", d, t + 2 * k)[0] for k in range((first - t) // 2)]
        if any(offs[k] >= offs[k + 1] for k in range(len(offs) - 1)):
            raise SystemExit("ARQ98.EXE: group %d's messages are not in order" % g)
        ends = offs[1:] + [tops[g + 1] if g + 1 < len(tops) else parse_end(d, offs[-1])]
        msgs = list(zip(offs, ends))
        for s, e in msgs:
            if parse_end(d, s) > e:
                raise SystemExit("ARQ98.EXE: the message at %x runs past %x" % (s, e))
        out.append((t, msgs))
    return out


def runs(d, s, e):
    """[(run start, run end)] of the message d[s:e]: the text after each FFh, up to its 00."""
    out, j = [], s
    while j < e:
        if d[j] == TEXT_MARK:
            k = d.index(0, j + 1)
            out.append((j + 1, k))
            j = k + 1
        else:
            j += 1
    return out


def data(exe):
    seg, _top, _at = find(exe)
    hdr, img = _image(exe)
    return img[seg * 16:]


def build(exe, new):
    """The block (top table, group tables, messages) with new ({(group, index): bytes}) in place of the
    messages it names; offsets from the block's start."""
    d = data(exe)
    gs = groups(exe)
    out = bytearray(2 * len(gs))
    for g, (_t, msgs) in enumerate(gs):
        struct.pack_into("<H", out, 2 * g, len(out))
        table = len(out)
        out += bytes(2 * len(msgs))
        for k, (s, e) in enumerate(msgs):
            struct.pack_into("<H", out, table + 2 * k, len(out))
            out += new.get((g, k), d[s:e])
    if len(out) > ROOM_MAX:
        raise Bad("the messages take %d bytes, their segment 65536" % len(out))
    return bytes(out)


def place(exe, block, move_up):
    """The program with block in a segment of its own after its image (move_up: pc98tl/adl5.py
    _move_up), the message routine pointed at it."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytearray(exe[hdr:])
    _seg, _top, at = find(exe)
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    if at + 2 not in fixups:
        raise SystemExit("ARQ98.EXE: the message routine's segment is not relocated")
    split_seg = -(-len(img) // 16)
    img += bytes(split_seg * 16 - len(img))
    paras = -(-len(block) // 16)
    out = bytearray(move_up(exe, hdr, img, fixups, rel_at, split_seg, paras, block, "ARQ98.EXE"))
    # (the routine rewritten in its 39 bytes: the tables read through es, the relocated segment word
    # where it was)
    call = at + 0x1E + struct.unpack_from("<h", exe, hdr + at + 0x1C)[0]
    code = bytearray(b"\x06\xba" + struct.pack("<H", split_seg) + b"\x8e\xc2\x8b\xd0\x32\xe4\x03\xc0"
                     b"\x8b\xf0\x26\x8b\x34\x03\xdb\x03\xf3\x51\x56\x26\x8b\x34\xe8")
    code += struct.pack("<h", call - (at + len(code) + 2))
    loop = len(code) + 7
    code += b"\x5e\x59\x83\xc6\x02\xe2" + struct.pack("b", 0x15 - loop) + b"\x07\xc3"
    code += b"\x90" * (0x27 - len(code))
    if len(code) != 0x27:
        raise SystemExit("ARQ98.EXE: the message routine does not fit its bytes")
    out[hdr + at:hdr + at + 0x27] = code
    return bytes(out)


def far_strings(exe):
    """[(start, end)] (file offsets, end past the NUL) of the strings the data segment's far-pointer
    tables point at (three or more offset:segment pairs in a row, the segment the data segment's, each
    to a NUL-ended Shift-JIS string in it): the save and load messages."""
    seg, _top, _at = find(exe)
    hdr, img = _image(exe)
    d = img[seg * 16:]
    sjis = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+\x00", re.S)

    def target(o):
        return o < len(d) and sjis.match(d, o)
    out, i = [], 0
    while i + 4 <= len(d):
        k = i
        while k + 4 <= len(d) and struct.unpack_from("<H", d, k + 2)[0] == seg and target(struct.unpack_from("<H", d, k)[0]):
            k += 4
        if (k - i) // 4 >= 3:
            for j in range(i, k, 4):
                o = struct.unpack_from("<H", d, j)[0]
                m = sjis.match(d, o)
                out.append((hdr + seg * 16 + o, hdr + seg * 16 + m.end()))
            i = k
        else:
            i += 1
    return sorted(set(out))
