"""Room for hook code in an Alice Soft .COM program.

Each program sets its stack near the top of what it uses and (usually) shrinks
its DOS memory block to just above that with one AH=4Ah call, sized from a
"mov bx, end" immediate:  bx = (end >> 4) + paragraphs, or (end + bytes) >> 4.
The font/text patches put their hook just above the old stack top and move
the stack up 4 KB past it, so the block has to grow by 4 KB too.  Adding
0x1000 to "end" does that in every shape seen (the add may be an imm8 that
can't hold the difference).
"""
import re

# mov bx,end ; any of shr bx,4 / mov cl,4 + shr bx,cl / add bx,imm16 / add bx,imm8 /
# mov si,bx / mov di,bx ; with "mov ah,4Ah" before or after ; int 21h
_RESIZE = re.compile(rb"(\xb4\x4a)?\xbb(..)"
                     rb"(?:\xc1\xeb\x04|\xb1\x04\xd3\xeb|\x81\xc3..|\x83\xc3.|\x8b\xf3|\x8b\xfb)+"
                     rb"(\xb4\x4a)?\xcd\x21", re.S)


def stack_top(data):
    """The stack pointer a program sets at startup (None if not found)."""
    m = re.search(rb"\xb8(..)\x05(..)\x8b\xe0|\xb8(..)\x8b\xe0|\xbc(..)", data[:0x40], re.S)
    if m:
        if m.group(1):
            return int.from_bytes(m.group(1), "little") + int.from_bytes(m.group(2), "little")
        return int.from_bytes(m.group(3) or m.group(4), "little")
    m = re.match(rb"\x8c\xc8\x8e\xd0\xbb(..)\xb1\x04\xd3\xeb\x81\xc3(..)", data, re.S)
    if m:
        return ((int.from_bytes(m.group(1), "little") >> 4) + int.from_bytes(m.group(2), "little")) << 4
    return None


def grow_block(adv, data, grow=0x1000):
    """Grow the program's DOS memory block by `grow` bytes (patches `adv` in
    place).  Returns False for a program that never shrinks its block (it owns
    all memory already)."""
    hits = [m for m in _RESIZE.finditer(data) if bool(m.group(1)) != bool(m.group(3))]
    calls = [m for m in re.finditer(rb"\xb4\x4a", data) if data.find(b"\xcd\x21", m.start(), m.start() + 16) >= 0]
    if not hits:
        if calls:
            raise ValueError("memory resize at %04x: unknown shape" % (0x100 + calls[0].start()))
        return False
    if len(hits) > 1:
        raise ValueError("memory resize: expected 1 match, found %d" % len(hits))
    end = int.from_bytes(hits[0].group(2), "little")
    if end + grow > 0xFFFF:
        raise ValueError("memory resize: block cannot grow")
    adv[hits[0].start(2):hits[0].start(2) + 2] = (end + grow).to_bytes(2, "little")
    return True
