"""ADVH (Fairytale / Cocktail Soft's engine before Adv98V: ADVH.EXE run by
ADVSHELL.COM): half-width English.

ADVH's scripts are the same bytecode as Adv98V's earliest builds
(pc98tl/adv98v.py, without the extended opcodes), but the engine has no
ASCII string command (21 ... 00 makes it reject the file), and it draws
every character as a 16x16 glyph from the BIOS font (int 18h AH=14h) into
the graphics planes, two 8-dot columns a character.  After each character
it runs a stored two-byte pseudo character, 81 A8, that moves the cursor
two columns on (and to the next line at the frame's right edge).

The patch (made on the EXEPACK-unpacked program, then packed again with
its own unpacker, pc98tl/exepack.py; the earliest builds are not packed
and are written back as they are):

* English letters are written as 85 xx, xx the ASCII code: Shift-JIS lead
  85 (NEC's row 9-10) is used by none of the ADVH games' scripts, and the
  text loop already reads it as a two-byte character.
* The text loop's test for 81 A8 jumps to a helper put in place of the
  disk-change command's message printer and disk-id reader (dead code once
  that command goes straight on): for an 85 xx character it reads the 8x16 ASCII glyph from the
  BIOS font (int 18h AH=14h, DX = 00xx), draws it one byte wide into the
  planes of the current colour, waits the text speed as for other
  characters, and moves the cursor one column on with the same right-edge
  wrap; anything else goes on as before.
* The disk-change command (wait until the floppy drive holds disk X) goes
  straight on: laid out on a hard disk, every disk's files are there.
* The earliest build draws its glyphs squeezed to ten rows (its lines are
  11 rows apart); the helper squeezes the letters the same way.
* A build with no disk-change command (the earliest, for a one-disk game,
  unpacked) has the helper put after the end of its image instead, which
  is the end of the text loop's code segment; the header's size grows with
  it, and the program's own memory request (the file's size) with that.
* A packed build with no disk-change command (Hare Nochi Oosawagi!: two
  floppies, each disk's files read from its own drive) has the helper put
  at the end of its animation driver's second file buffer, within the text
  loop's code segment's reach: the driver (its segment's code after two
  5000h-byte buffers at 404h and 5404h) only reads its files into them
  (int 21h AH=3Fh, CX = 5000h) and draws from them, so past the largest
  animation file the game has the buffer is never written.  The patch is
  refused when the helper would not fit after that file.

Every site is found by its byte signature; a program that does not match
is refused.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from . import exepack
from .illusion_font import _asm

# the text loop: cmp ax, 81A8h / jne draw / mov ax, [cursor x]
# (the cursor variable's address, the last two bytes, moves between builds;
# the other variables the helper uses sit at fixed distances from it)
LOOP_SIG = re.compile(rb"\x3d\xa8\x81\x75\x1f\xa1..", re.S)
# the disk-change command's wait loop (mov al, cs:[drive] / call read id / cmp al, cs:[want] / je done);
# the variables' and the reader's addresses differ between the games' builds
DISK_SIG = re.compile(rb"\x2e\xa0..\xe8..\x2e\x3a\x06..\x74", re.S)
# the earliest build's glyph writer, which squeezes the 16 rows into 10
# (its lines are 11 rows apart): mov si, glyph / mov cx, 2 / movsw /
# mov ax, [si] / inc si / inc si / or es:[di-2], ax; it ORs rows 0+1, 2+3,
# 6+7, 8+9, 10+11 and 14+15 and copies 4, 5, 12 and 13
SQUEEZE_SIG = re.compile(rb"\xbe..\xb9\x02\x00\xa5\x8b\x04\x46\x46\x26\x09\x45\xfe", re.S)
SQUEEZE_MAP = 0b1001110011   # the ten rows written, low bit first: set = two glyph rows ORed
# the animation driver's file loader: mov si, 5404h / mov di, 204h / dec cl / je +6 /
# mov si, 404h / mov di, 4 / mov word ptr [di], 0 / ... open ... / mov cx, 5000h / mov ah, 3Fh
ANIM_SIG = re.compile(rb"\xbe\x04\x54\xbf\x04\x02\xfe\xc9\x74\x06\xbe\x04\x04\xbf\x04\x00\xc7\x05\x00\x00"
                      rb".{8,24}?\xb9\x00\x50\xb4\x3f\xcd\x21", re.S)
ANIM_END = 0x5404 + 0x5000   # the second buffer's end, in the driver's segment


def _find_once(img, sig, what):
    found = [m.start() for m in sig.finditer(img)] if isinstance(sig, re.Pattern) else [k for k in range(len(img)) if img.startswith(sig, k)]
    if len(found) != 1:
        raise SystemExit("ADVH.EXE: the %s signature is found %d times, not once" % (what, len(found)))
    return found[0]


def _cave(img, disk):
    """(start, end) of the room for the helper: the disk-change command's
    message printer and disk-id reader, which only its wait loop calls and
    which the patch makes dead code, up to the reader's own data (its FCB,
    the address its first "mov byte ptr cs:[x], 0ffh" writes)."""
    if img[disk + 4] != 0xE8 or img[disk + 20] != 0xE8:
        raise SystemExit("ADVH.EXE: the disk-change wait loop is not laid out as expected")
    reader = disk + 7 + struct.unpack_from("<h", img, disk + 5)[0]
    printer = disk + 23 + struct.unpack_from("<h", img, disk + 21)[0]
    at = img.find(bytes([0x2E, 0xC6, 0x06]), reader, reader + 0x30)
    if at < 0 or img[at + 5] != 0xFF:
        raise SystemExit("ADVH.EXE: the disk-id reader is not laid out as expected")
    fcb = struct.unpack_from("<H", img, at + 3)[0]
    if not printer < reader < fcb:
        raise SystemExit("ADVH.EXE: the disk-change routines are not laid out as expected")
    return printer, fcb


def _asm16(src, org):
    """Keystone for 16-bit code: "CALLN x" and "JMPN x" (a label or a 0x
    address) become 3-byte near calls and jumps (keystone gives them a
    32-bit form)."""
    lines, jumps = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("JMPN "):
            tag = "__jmp%d" % len(jumps)
            jumps.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    code, addr = _asm(Ks(KS_ARCH_X86, KS_MODE_16), "\n".join(lines), org, [t for t, _x in jumps])
    code = bytearray(code)
    for tag, target in jumps:
        t = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = b"\xe9" + ((t - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise SystemExit("ADVH.EXE: a 32-bit prefix in the helper at %x" % ins.address)
    return bytes(code)


# an XOR layer some releases wrap around the EXEPACK program: mov ax, seed /
# mov bx, mult / mov di, 100h / mov cx, count / mul bx / add ax, add /
# xor [di], dl / inc di / loop; then the original bytes it overwrote are
# put back from cs:1EEh (a word to cs:6, three bytes to cs:E6h, 12h bytes
# to the entry) and it jumps to EXEPACK's entry, cs:10h
WRAP_SIG = re.compile(rb"\xb8(..)\xbb(..)\xbf\x00\x01\xb9(..)\xf7\xe3\x05(..)\x30\x15\x47\xe2\xf6", re.S)


def _unwrap_tc0(exe, hdr, base, entry):
    """The "TC0" wrapper (Disk Bishoujo Daizukan): after its signature,
    seed, byte count, start offset in the loaded image (+0x100 from the
    PSP), the real entry ip:cs and sp:ss (both relative to the image);
    each byte is XORed with bits 8-15 of the seed rotated left twice,
    the seed stepping by *0x2711 + 0x3619.  The wrapper's code follows
    the image, which keeps its size."""
    seed, count, start, ip, cs, sp, ss = struct.unpack_from("<7H", exe, entry + 6)
    img = bytearray(exe[base:])
    at = start - 0x100
    for k in range(count):
        seed = (seed * 0x2711 + 0x3619) & 0xFFFF
        img[at + k] ^= ((seed << 2 | seed >> 14) & 0xFFFF) >> 8
    hdr[10], hdr[11], hdr[8], hdr[7] = ip, cs, sp, ss
    out = bytearray(exe[:base]) + img
    struct.pack_into("<14H", out, 0, *hdr)
    out = bytes(out)
    inner = base + cs * 16 + ip
    if out[inner:inner + 6] == b"\xe8\x11\x00TC0":
        # (wrapped more than once: each layer opens the next)
        return _unwrap_tc0(out, hdr, base, inner)
    if not exepack.is_packed(out):
        raise SystemExit("ADVH.EXE: the TC0 wrapper does not hold an EXEPACK program")
    return out


def unwrap(exe):
    """The plain EXEPACK program inside an XOR-wrapped ADVH.EXE (the
    program as it is when it is not wrapped, packed or not)."""
    if exepack.is_packed(exe):
        return exe
    hdr = list(struct.unpack_from("<14H", exe, 0))
    base = hdr[4] * 16
    ip, cs = hdr[10], hdr[11]
    entry = base + cs * 16 + ip
    if exe[entry:entry + 6] == b"\xe8\x11\x00TC0":
        return _unwrap_tc0(exe, hdr, base, entry)
    m = WRAP_SIG.match(exe, entry)
    if not m:
        # (a plain program: the earliest builds, Doki Doki Shutter Chance's,
        # are neither packed nor wrapped; anything else fails the
        # signatures patch looks for)
        return exe
    ax, bx, count, add = (struct.unpack("<H", g)[0] for g in m.groups())
    img = bytearray(exe[base:])
    for k in range(count):
        prod = ax * bx
        img[k] ^= (prod >> 16) & 0xFF
        ax = (prod + add) & 0xFFFF
    seg = cs * 16
    after = m.end() - base - seg             # (the wrapper's code after its loop, in its segment)
    if img[seg + after] == 0xE9 and (after + 3 + struct.unpack_from("<h", img, seg + after + 1)[0]) & 0xFFFF == 0x10:
        # (Hare Nochi Oosawagi!'s wrapper: straight on to EXEPACK's entry, nothing put back)
        pass
    else:
        src = seg + 0x1EE
        img[seg + 6:seg + 8] = img[src:src + 2]
        img[seg + 0xE6:seg + 0xE9] = img[src + 2:src + 5]
        img[seg + ip:seg + ip + 0x12] = img[src + 5:src + 0x17]
    hdr[10] = 0x10
    out = bytearray(exe[:base]) + img
    struct.pack_into("<14H", out, 0, *hdr)
    out = bytes(out)
    if not exepack.is_packed(out):
        raise SystemExit("ADVH.EXE: the XOR wrapper does not hold an EXEPACK program")
    return out


def patch(orig, fixes=(), anim_max=None):
    """The program with half-width letters (85 xx): unpacked, patched and
    packed again with the original unpacker (an unpacked ADVH.EXE fails to
    restart when ADVSHELL runs it again).  A program in a wrapper is
    written back without it.  fixes: [{"find", "replace", "why"}] (hex,
    the same length), applied to the unpacked program, each found once:
    what a wrapper did to the program at run time (a release's crack).
    anim_max: the size of the game's largest animation file (*.MDA,
    *.ADA), for a build whose helper goes into the animation driver's
    buffer (see above)."""
    orig = unwrap(orig)
    exe = exepack.unpack(orig) if exepack.is_packed(orig) else orig
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytearray(exe[hdr:])
    for fix in fixes:
        find, repl = bytes.fromhex(fix["find"]), bytes.fromhex(fix["replace"])
        if bytes(img).count(find) != 1 or len(find) != len(repl):
            raise SystemExit("ADVH.EXE: the signature for '%s' is not found once" % fix["why"])
        at = bytes(img).index(find)
        img[at:at + len(find)] = repl
    loop = _find_once(bytes(img), LOOP_SIG, "text loop")
    cur = struct.unpack_from("<H", img, loop + 6)[0]     # the cursor column (0xc2fd in most builds)
    disk = _find_once(bytes(img), DISK_SIG, "disk check") if DISK_SIG.search(bytes(img)) else None
    # the loop's targets, read off its code: jne +1F after the 5-byte
    # compare, the advance path right after it, the loop head from the
    # jmp at the end of the advance path
    draw = loop + 5 + img[loop + 4]                 # jne target (draw a character)
    advance = loop + 5                              # mov ax, [cursor x] ...
    newline_jmp = draw - 2                          # jmp short newline (eb xx) before draw
    if img[newline_jmp] != 0xEB:
        raise SystemExit("ADVH.EXE: the text loop is not laid out as expected")
    newline = newline_jmp + 2 + struct.unpack("b", bytes([img[newline_jmp + 1]]))[0]
    head = advance + 0x0F + 3 + struct.unpack_from("<h", img, advance + 0x10)[0]   # jmp near loop head
    if img[advance + 0x0F] != 0xE9:
        raise SystemExit("ADVH.EXE: the text loop's advance path is not laid out as expected")
    anim = None
    if disk is not None:
        cave, cave_end = _cave(bytes(img), disk)
        seg = 0
    elif exepack.is_packed(orig) and ANIM_SIG.search(bytes(img)):
        # (no disk-change command, packed: at the end of the animation driver's second buffer,
        # its segment the highest relocated one at or below its loader)
        anim = _find_once(bytes(img), ANIM_SIG, "animation loader")
        nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
        bases = {16 * struct.unpack_from("<H", img, struct.unpack_from("<H", exe, rel_at + 4 * k)[0]
                                         + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0])[0]
                 for k in range(nrel)}
        base = max(b for b in bases | {0} if b <= anim)
        if anim_max is None:
            raise SystemExit("ADVH.EXE: the helper goes after the largest animation file, and its size is not given")
        seg = 0
        cave_end = base + ANIM_END
        cave = cave_end - 0x200
        if cave_end > 0x10000 or loop >= 0x10000:
            raise SystemExit("ADVH.EXE: the animation driver's buffer is out of the text loop's reach")
    else:
        # (no disk-change command: after the image, in the text loop's code segment, the entry's)
        seg = struct.unpack_from("<H", exe, 0x16)[0] * 16
        if exepack.is_packed(orig) or not seg <= loop < len(img):
            raise SystemExit("ADVH.EXE: no disk-change command, and the text loop is not in the image's last segment")
        cave, cave_end = len(img), seg + 0x10000
        img += bytes(0x100)
    asm = """
        cmp ax, 0x81a8
        jne notadv
        JMPN {advance}
    notadv:
        cmp ah, 0x85
        je half
        JMPN {draw}
    half:
        push si
        push es
        mov dl, al
        mov dh, 0x80
        mov cx, {glyph}
        mov bx, ds
        mov ah, 0x14
        int 0x18
        mov ax, 0x50
        mul word ptr [{cury}]
        add ax, word ptr [{curx}]
        mov di, ax
        mov bx, word ptr [{color}]
        test bl, 1
        jz p2
        mov ax, 0xa800
        CALLN plane
    p2:
        test bl, 2
        jz p3
        mov ax, 0xb000
        CALLN plane
    p3:
        test bl, 4
        jz drawn
        mov ax, 0xb800
        CALLN plane
    drawn:
        pop es
        pop si
        mov cx, word ptr [{speed}]
        cmp cx, 0
        je adv
        CALLN {delay}
    adv:
        mov ax, word ptr [{curx}]
        inc ax
        mov word ptr [{curx}], ax
        cmp ax, word ptr [{right}]
        jbe next
        mov ax, word ptr [{left}]
        mov word ptr [{curx}], ax
        JMPN {newline}
    next:
        JMPN {head}
    plane:
        mov es, ax
        push di
        mov si, {glyphb}
    """
    if SQUEEZE_SIG.search(bytes(img)):
        # (the letter squeezed as the engine squeezes its glyphs: two rows ORed into one where the
        # map's bit is set, low bit first, ten rows for the lines' 11-row pitch)
        asm += """
        mov dx, %s
        mov cx, 10
    line:
        lodsb
        shr dx, 1
        jnc single
        or al, byte ptr [si]
        inc si
    single:
        stosb
        add di, 0x4f
        loop line
        pop di
        .byte 0xc3
    """ % hex(SQUEEZE_MAP)
    else:
        asm += """
        mov cx, 16
    line:
        movsb
        add di, 0x4f
        loop line
        pop di
        .byte 0xc3
    """
    # the text speed wait the draw path calls (call near after "mov cx, [speed]; cmp cx, 0; je")
    after = img.find(b"\x8b\x0e" + struct.pack("<H", cur + 8) + bytes.fromhex("83f9007403e8"), draw)
    if after < 0 or after > draw + 0x40:
        raise SystemExit("ADVH.EXE: the text speed wait is not found")
    delay = after + 9 + 3 + struct.unpack_from("<h", img, after + 10)[0]
    # (code addresses as offsets in the segment: the assembler's are 16-bit)
    code = asm.format(advance=hex(advance - seg), draw=hex(draw - seg), newline=hex(newline - seg),
                      head=hex(head - seg), delay=hex(delay - seg),
                      curx=hex(cur), cury=hex(cur + 2), color=hex(cur + 4), speed=hex(cur + 8), left=hex(cur + 0xC),
                      right=hex(cur + 0x10), glyph=hex(cur - 0x24), glyphb=hex(cur - 0x22))
    enc = _asm16(code, cave - seg)
    if anim is not None:
        # (put at the buffer's very end: assembled again where it lands)
        while cave + len(enc) != cave_end:
            cave = cave_end - len(enc)
            enc = _asm16(code, cave - seg)
        if cave < base + 0x5404 + anim_max:
            raise SystemExit("ADVH.EXE: the helper is %d bytes, the animation buffer's room past the largest file %d"
                             % (len(enc), cave_end - (base + 0x5404 + anim_max)))
        if any(img[cave:cave_end]):
            raise SystemExit("ADVH.EXE: the animation buffer's end is not empty")
    if cave + len(enc) > cave_end:
        raise SystemExit("ADVH.EXE: the helper is %d bytes, the room %d" % (len(enc), cave_end - cave))
    img[cave:cave + len(enc)] = bytes(enc)
    jmp = b"\xe9" + struct.pack("<H", (cave - (loop + 3)) & 0xFFFF)
    img[loop:loop + 5] = jmp + b"\x90\x90"
    if disk is not None:
        # the disk-change wait: jump to its end (its je target)
        end = disk + 14 + img[disk + 13]
        img[disk:disk + 2] = bytes([0xEB, end - (disk + 2)])
    elif anim is None:
        del img[cave + len(enc):]
    # no segment fixup may fall in what was changed
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    for lo, hi in ((loop, loop + 5), (cave, cave + len(enc))) + (((disk, disk + 2),) if disk is not None else ()):
        if any(lo - 1 <= f < hi for f in fixups):
            raise SystemExit("ADVH.EXE: a segment fixup falls in a patched range")
    if exepack.is_packed(orig):
        return exepack.pack(orig, bytes(img))
    out = bytearray(exe[:hdr]) + img
    struct.pack_into("<HH", out, 2, len(out) % 512, -(-len(out) // 512))
    return bytes(out)


def encode(text):
    """A line of English for ADVH: ASCII as 85 xx, anything else as
    Shift-JIS (full width)."""
    out = b""
    for ch in text:
        if 0x20 <= ord(ch) < 0x7F:
            out += bytes([0x85, ord(ch)])
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                out += bytes([0x85, ord("?")])
    return out


# the opening program's per-character step (Hare Nochi Oosawagi!'s HARE.EXE),
# called before each character of a text record is drawn: mov bp, seg /
# mov ds, bp / mov al, [speed] / mov bp, seg / mov ds, bp / push ax ... es /
# cmp word ptr [si], 2020h; and its end: pop es ... ax / add bx, 2 / ret /
# cmp word ptr [bx], 2020h (bx the record's control field, a two-letter
# code at each character's place)
STEP_SIG = re.compile(rb"\xbd..\x8e\xdd\xa0..\xbd..\x8e\xdd\x50\x53\x51\x52\x55\x57\x56\x1e\x06\x81\x3c\x20\x20", re.S)
# the control code's first digit: cmp al, 'A' / jb digit / sub al, 37h / jmp second / digit:
# cmp al, '0' / jb skip / sub al, '0'
CODE_SIG = re.compile(rb"\x3c\x41\x72\x04\x2c\x37\xeb\x06\x3c\x30\x72(.)\x2c\x30", re.S)
STEP_END_SIG = re.compile(rb"\x07\x1f\x5e\x5f\x5d\x5a\x59\x5b\x58\x83\xc3\x02\xc3\x81\x3f\x20\x20")


def patch_opening(exe):
    """The opening program (plain MZ) with its text records' control
    fields kept in step with half-width letters.

    Its record player draws a record's text a character at a time (a
    single byte as one half-width cell, which the text layer draws by
    itself), and before each runs the two-letter code in the record's
    control field at that character's place, the field's pointer stepping
    2 a character: English letters, one byte each, would run it past the
    field into the next record.  The step becomes the character's bytes (1
    below 80h, else 2), so a code applies at its text's byte offset, as
    the Japanese laid them out.  It is put in place of the step routine's
    first 13 bytes, which only load a byte it does not use and set DS and
    BP to the text segment they already hold (its one caller set them);
    the two segment fixups in them are taken out of the header's table.

    A letter at an odd byte offset now reads the field across two codes
    ("0205" read from its second byte is "20"): every code the game has is
    01h-0Fh, so a code whose first digit is not 0 is passed over, as a
    blank one is (the dispatch table has no entry past 0Fh)."""
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    img = bytearray(exe[base:])
    step = _find_once(bytes(img), STEP_SIG, "opening's character step")
    end = _find_once(bytes(img), STEP_END_SIG, "opening's character step end") + 9
    if not 0 < end - step < 0x80:
        raise SystemExit("HARE.EXE: the character step is not laid out as expected")
    # jmp short past the old prologue / cmp byte ptr [si], 80h / sbb bx, -2 / ret
    img[step:step + 13] = bytes([0xEB, 0x0B]) + bytes.fromhex("803c8083dbfec3") + b"\x90" * 4
    rel = (step + 2) - (end + 2)
    img[end:end + 2] = bytes([0xEB, rel & 0xFF])
    img[end + 2] = 0x90
    code = _find_once(bytes(img), CODE_SIG, "opening's control code reader")
    skip = code + 14 + struct.unpack("b", bytes([img[code + 11]]))[0] - 2   # (the jb's target, from its end)
    # cmp al, '0' / jne skip / sub al, '0' (then its jmp to the second digit)
    img[code:code + 6] = bytes([0x3C, 0x30, 0x75, (skip - (code + 4)) & 0xFF, 0x2C, 0x30])
    relocs = [struct.unpack_from("<HH", exe, hdr[12] + 4 * k) for k in range(hdr[3])]
    keep = [(o, s) for o, s in relocs if s * 16 + o not in (step + 1, step + 9)]
    if len(keep) != len(relocs) - 2 or any(lo - 1 <= s * 16 + o < hi for o, s in keep
                                           for lo, hi in ((step, step + 13), (end, end + 3))):
        raise SystemExit("HARE.EXE: the character step's segment fixups are not where expected")
    out = bytearray(exe[:base]) + img
    struct.pack_into("<H", out, 6, len(keep))
    table = b"".join(struct.pack("<HH", o, s) for o, s in keep) + bytes(8)
    out[hdr[12]:hdr[12] + len(table)] = table
    return bytes(out)
