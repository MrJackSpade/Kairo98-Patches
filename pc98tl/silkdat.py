"""Silky's data archives for its AI5 engine (SIL.EXE: Nonomura Byouin no
Hitobito, the SILK0.DAT ... SILK4.DAT made by "mdataX.exe ver 1.02"):

* a text header and zeros up to 1F4h;
* a dword, the directory's size;
* the directory: 24-byte entries, a name (16 bytes, NUL padded), the
  member's offset from the end of the directory and its size (dwords),
  encrypted: every byte XORed with the encrypted byte before it, the first
  with a key (a byte of SIL.EXE, read off it: key_of);
* the members, stored as they are.
"""
import re
import struct

HEAD = 0x1F4


def key_of(exe):
    """The directory key in SIL.EXE (unpacked): the byte its archive code
    XORs the directory's first byte with (mov al, [k] / xor [si] or [bx], al), k in
    the archive code's data segment, which starts at the paragraph of the
    archive names (silk0.dat ...).  AAh in Nonomura Byouin no Hitobito,
    2Ah in Kawarazakike no Ichizoku."""
    at = [struct.unpack("<H", m.group(1))[0] for m in re.finditer(rb"\xa0(..)(?:\x8b\x5e.)?\x30[\x04\x07]", exe, re.S)]
    names = [m.start() for m in re.finditer(rb"silk0\.dat\x00", exe, re.I)]
    if len(set(at)) != 1 or len(names) != 1:
        raise SystemExit("SIL.EXE: the archive key is not found once")
    return exe[(names[0] & ~15) + at[0]]


class Archive:
    def __init__(self, raw, key):
        self.key = key
        self.raw = raw
        n = struct.unpack_from("<I", raw, HEAD)[0]
        enc = raw[HEAD + 4:HEAD + 4 + n]
        dec = bytearray(enc)
        dec[0] ^= key
        for i in range(n - 1, 0, -1):
            dec[i] = enc[i] ^ enc[i - 1]
        self.base = HEAD + 4 + n
        self.entries = []
        for k in range(n // 24):
            e = dec[24 * k:24 * k + 24]
            name = bytes(e[:16]).split(b"\0")[0].decode("ascii", "replace")
            off, size = struct.unpack_from("<II", e, 16)
            self.entries.append((name, off, size, bytes(e[:16])))
        if not self.entries or any(n and not re.fullmatch(r"[!-~]+", n) for n, *_ in self.entries):
            raise ValueError("a Silky's data archive whose directory does not decode (a wrong key?)")

    def names(self):
        return [e[0] for e in self.entries if e[0]]

    def read(self, name):
        for n, off, size, _raw in self.entries:
            if n == name:
                return self.raw[self.base + off:self.base + off + size]
        raise KeyError(name)

    def rebuilt(self, changed):
        """The archive with the members in changed ({name: bytes}) put in,
        every member laid out anew in its order."""
        body = bytearray()
        dec = bytearray()
        for name, off, size, raw_name in self.entries:
            data = changed.get(name, self.raw[self.base + off:self.base + off + size]) if name else b""
            # (the closing entry, with no name, holds where the data ends)
            dec += raw_name + struct.pack("<II", len(body), len(data))
            body += data
        enc = bytearray(dec)
        enc[0] = dec[0] ^ self.key
        for i in range(1, len(dec)):
            enc[i] = dec[i] ^ enc[i - 1]
        return bytes(self.raw[:HEAD]) + struct.pack("<I", len(dec)) + bytes(enc) + bytes(body)
