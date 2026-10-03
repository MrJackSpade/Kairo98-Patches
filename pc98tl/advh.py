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
its own unpacker, pc98tl/exepack.py):

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

Every site is found by its byte signature; a program that does not match
is refused.
"""
import re
import struct

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

from . import exepack
from .illusion_font import _asm

# the text loop: cmp ax, 81A8h / jne draw / mov ax, [cursor x]
LOOP_SIG = bytes.fromhex("3da881751fa1fdc2")
# the disk-change command's wait loop (mov al, cs:[drive] / call read id / cmp al, cs:[want] / je done);
# the variables' and the reader's addresses differ between the games' builds
DISK_SIG = re.compile(rb"\x2e\xa0..\xe8..\x2e\x3a\x06..\x74", re.S)


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


def patch(orig):
    """The program with half-width letters (85 xx): unpacked, patched and
    packed again with the original unpacker (an unpacked ADVH.EXE fails to
    restart when ADVSHELL runs it again)."""
    exe = exepack.unpack(orig) if exepack.is_packed(orig) else orig
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytearray(exe[hdr:])
    loop = _find_once(bytes(img), LOOP_SIG, "text loop")
    disk = _find_once(bytes(img), DISK_SIG, "disk check")
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
    cave, cave_end = _cave(bytes(img), disk)
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
        xor dh, dh
        mov cx, 0xc2d9
        mov bx, ds
        mov ah, 0x14
        int 0x18
        mov ax, 0x50
        mul word ptr [0xc2ff]
        add ax, word ptr [0xc2fd]
        mov di, ax
        mov bx, word ptr [0xc301]
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
        mov cx, word ptr [0xc305]
        cmp cx, 0
        je adv
        CALLN {delay}
    adv:
        mov ax, word ptr [0xc2fd]
        inc ax
        mov word ptr [0xc2fd], ax
        cmp ax, word ptr [0xc30d]
        jbe next
        mov ax, word ptr [0xc309]
        mov word ptr [0xc2fd], ax
        JMPN {newline}
    next:
        JMPN {head}
    plane:
        mov es, ax
        push di
        mov si, 0xc2db
        mov cx, 16
    line:
        movsb
        add di, 0x4f
        loop line
        pop di
        .byte 0xc3
    """
    # the text speed wait the draw path calls (call near after "mov cx, [speed]; cmp cx, 0; je")
    after = img.find(bytes.fromhex("8b0e05c383f9007403e8"), draw)
    if after < 0 or after > draw + 0x40:
        raise SystemExit("ADVH.EXE: the text speed wait is not found")
    delay = after + 9 + 3 + struct.unpack_from("<h", img, after + 10)[0]
    code = asm.format(advance=hex(advance), draw=hex(draw), newline=hex(newline), head=hex(head), delay=hex(delay))
    enc = _asm16(code, cave)
    if cave + len(enc) > cave_end:
        raise SystemExit("ADVH.EXE: the helper is %d bytes, the room %d" % (len(enc), cave_end - cave))
    img[cave:cave + len(enc)] = bytes(enc)
    jmp = b"\xe9" + struct.pack("<h", cave - (loop + 3))
    img[loop:loop + 5] = jmp + b"\x90\x90"
    # the disk-change wait: jump to its end (its je target)
    end = disk + 14 + img[disk + 13]
    img[disk:disk + 2] = bytes([0xEB, end - (disk + 2)])
    # no segment fixup may fall in what was changed
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    for lo, hi in ((loop, loop + 5), (disk, disk + 2), (cave, cave + len(enc))):
        if any(lo - 1 <= f < hi for f in fixups):
            raise SystemExit("ADVH.EXE: a segment fixup falls in a patched range")
    if exepack.is_packed(orig):
        return exepack.pack(orig, bytes(img))
    return bytes(exe[:hdr]) + bytes(img)


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
