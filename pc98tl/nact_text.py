"""Half-width English for Abunai Tengu Densetsu (N88-BASIC "nact" engine).

The game runs on N88-BASIC(86); messages are drawn by the machine-code module
NAC3.MAC (loaded at A100:0600, in unused text VRAM).  Its message loop maps a
script byte A1-DF through a 63-entry table to a Shift-JIS code and calls a
drawer that writes the character into text VRAM as two cells.

The patch
* sets the table entries for A1-DE to 00nn, nn = an ASCII letter (same
  letters as System 3's one-byte alphabet, shifted to start at A1, since A0 is
  not a message byte this loop accepts);
* hooks the drawer's first call: a code with high byte 0 is written as one
  ASCII cell (with the current attribute) and the cursor moves one cell;
  anything else goes through the original code.
The hook is appended to the module, and the BSAVE header's end address grows
to cover it.  All sites are found by byte signature.
"""
import re

from . import alice3_font
from .text import encode_fullwidth

ONE_BYTE = alice3_font.ONE_BYTE          # 62 characters -> A1..DE
FIRST = 0xA1
BYTE_OF = {c: FIRST + i for i, c in enumerate(ONE_BYTE)}


def encode(s, fallback=encode_fullwidth):
    out = bytearray()
    for ch in s:
        ch = alice3_font._SUBST.get(ch, ch)
        for c in ch:
            out += bytes([BYTE_OF[c]]) if c in BYTE_OF else fallback(c)
    return bytes(out)


def cells(s):
    n = 0
    for ch in s:
        ch = alice3_font._SUBST.get(ch, ch)
        n += sum(1 if c in BYTE_OF else 2 for c in ch)
    return (n + 1) // 2


def kana_table(mac):
    """The module's A1-DF table as displayed characters, for extraction (A0 first)."""
    at = mac.find(bytes.fromhex("42817581768141814581"))
    if at < 0:
        return None
    words = [mac[at + 2 * i:at + 2 * i + 2][::-1] for i in range(63)]
    return ["　"] + [w.decode("cp932", "replace") for w in words]


def build(mac):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    mac = bytearray(mac)
    org = int.from_bytes(mac[0:2], "little")             # BSAVE header: start, end
    body = mac[4:]
    at = bytes(body).find(bytes.fromhex("42817581768141814581"))
    if at < 0:
        raise ValueError("NAC3 kana table not found")
    for i, c in enumerate(ONE_BYTE):
        body[at + 2 * i:at + 2 * i + 2] = bytes([ord(c), 0])
    m = re.search(rb"\x56\x57\x1e\x06(\xe8..)\xfc\xb8\x60\x00\x8e\xd8\xb8\x00\xa0\x8e\xc0"
                  rb"\x2e\x8b\x1e(..)\x2e\xa1(..)\xba\xa0\x00\xf7\xe2\x01\xdb\x01\xd8\x89\xc7", bytes(body), re.S)
    if not m:
        raise ValueError("NAC3 drawer not found")
    call = m.start(1)
    rel = int.from_bytes(body[call + 1:call + 3], "little", signed=True)
    orig = org + call + 3 + rel
    xvar = int.from_bytes(m.group(2), "little")
    yvar = int.from_bytes(m.group(3), "little")
    attr = re.compile(rb"\xa0(..)\x4f\x4f\xab\xab", re.S).search(bytes(body), m.end())
    tail = re.compile(rb"\x07\x1f\x5f\x5e\xc3", re.S).search(bytes(body), m.end())
    if not attr or not tail:
        raise ValueError("NAC3 drawer: attribute or exit not found")
    attr_var = int.from_bytes(attr.group(1), "little")
    exit_at = org + tail.start()
    end = int.from_bytes(mac[2:4], "little")
    code_at = max(end, org + len(body))
    code_at += code_at & 1
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    asm = """
        or ah, ah
        jz ascii
        nop
        nop
        nop
    ascii:
        pop bx
        cld
        push ax
        mov ax, 0x60
        mov ds, ax
        mov ax, 0xa000
        mov es, ax
        mov bx, word ptr cs:[{x}]
        mov ax, word ptr cs:[{y}]
        mov dx, 0xa0
        mul dx
        add bx, bx
        add ax, bx
        mov di, ax
        pop ax
        xor ah, ah
        mov word ptr es:[di], ax
        mov ax, 0xa200
        mov es, ax
        xor ax, ax
        mov al, byte ptr [{attr}]
        mov word ptr es:[di], ax
        mov bx, word ptr cs:[{x}]
        mov ax, word ptr cs:[{y}]
        inc bx
        cmp bx, 0x50
        jb store
        cmp ax, 0x18
        je store
        inc ax
    store:
        mov word ptr cs:[{x}], bx
        mov word ptr cs:[{y}], ax
        nop
        nop
        nop
    """.format(x=xvar, y=yvar, attr=attr_var)
    code = bytearray(ks.asm(asm, code_at)[0])
    # the two 3-byte nop slots become near jumps: to the original routine, and to the exit
    j1 = code.find(b"\x90\x90\x90")
    code[j1:j1 + 3] = b"\xe9" + ((orig - (code_at + j1 + 3)) & 0xFFFF).to_bytes(2, "little")
    j2 = len(code) - 3
    code[j2:j2 + 3] = b"\xe9" + ((exit_at - (code_at + j2 + 3)) & 0xFFFF).to_bytes(2, "little")
    body[call + 1:call + 3] = ((code_at - (org + call + 3)) & 0xFFFF).to_bytes(2, "little")
    body = body.ljust(code_at - org, b"\0") + code
    new_end = org + len(body)
    if new_end > 0xA00:
        raise ValueError("NAC3 hook would run past the free text VRAM area")
    return bytes(mac[0:2]) + new_end.to_bytes(2, "little") + bytes(body)
