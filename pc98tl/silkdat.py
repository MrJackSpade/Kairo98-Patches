"""Silky's data archives for its AI5 engine (SIL.EXE: Nonomura Byouin no
Hitobito, the SILK0.DAT ... SILK4.DAT made by "mdataX.exe ver 1.02"):

* a text header and zeros up to 1F4h;
* a dword, the directory's size;
* the directory: 24-byte entries, a name (16 bytes, NUL padded), the
  member's offset from the end of the directory and its size (dwords),
  encrypted: every byte XORed with the encrypted byte before it, the first
  with a key (SIL.EXE DS:0058h, AAh; every archive's first member is
  DISKNO, which checks it);
* the members, stored as they are.
"""
import struct

KEY = 0xAA
HEAD = 0x1F4


class Archive:
    def __init__(self, raw):
        self.raw = raw
        n = struct.unpack_from("<I", raw, HEAD)[0]
        enc = raw[HEAD + 4:HEAD + 4 + n]
        dec = bytearray(enc)
        dec[0] ^= KEY
        for i in range(n - 1, 0, -1):
            dec[i] = enc[i] ^ enc[i - 1]
        self.base = HEAD + 4 + n
        self.entries = []
        for k in range(n // 24):
            e = dec[24 * k:24 * k + 24]
            name = bytes(e[:16]).split(b"\0")[0].decode("ascii", "replace")
            off, size = struct.unpack_from("<II", e, 16)
            self.entries.append((name, off, size, bytes(e[:16])))
        if not self.entries or self.entries[0][0] != "DISKNO":
            raise ValueError("not a Silky's data archive (its directory does not open with DISKNO)")

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
        enc[0] = dec[0] ^ KEY
        for i in range(1, len(dec)):
            enc[i] = dec[i] ^ enc[i - 1]
        return bytes(self.raw[:HEAD]) + struct.pack("<I", len(dec)) + bytes(enc) + bytes(body)
