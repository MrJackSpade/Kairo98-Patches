"""CPX "One-Pass SD" files (Active's Sakura no Mori: its *.HGO scripts).

A header of 1Eh bytes: "CPX One-Pass SD" padded with spaces to 20 bytes, a word, a word, the unpacked
size (a word at 18h), a word, the method (a byte at 1Ch: 0 the data stored as it is) and the escape
byte (1Dh); then the data.  Packed, the data is bytes as they are but for the escape: the escape and
00h is the escape itself, the escape, a distance d (1-FFh) and a byte n copy n+3 bytes from d back in
what is unpacked so far (MAIN.EXE's unpacker, a near loop of lodsb/stosb/rep movsb).

The program loads a file into its script buffer and unpacks it there only when it has this header; a
file without it is used as it is, so a changed script is written back unpacked.
"""
import struct

MAGIC = b"CPX One-Pass SD"
HEAD = 0x1E


def is_cpx(data):
    return data[:len(MAGIC)] == MAGIC


def unpack(data):
    """The file's data, unpacked (a file without the header as it is)."""
    if not is_cpx(data):
        return bytes(data)
    size = struct.unpack_from("<H", data, 0x18)[0]
    if data[0x1C] == 0:
        return bytes(data[HEAD:HEAD + size])
    esc = data[0x1D]
    out, i = bytearray(), HEAD
    while len(out) < size:
        b = data[i]
        i += 1
        if b != esc:
            out.append(b)
            continue
        dist = data[i]
        i += 1
        if dist == 0:
            out.append(esc)
            continue
        for _k in range(data[i] + 3):
            out.append(out[-dist])
        i += 1
    if len(out) != size:
        raise ValueError("CPX: %d bytes unpacked, the header says %d" % (len(out), size))
    return bytes(out)
