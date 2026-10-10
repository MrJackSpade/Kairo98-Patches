"""Silky's data archives for its AI5 engine (SIL.EXE: Nonomura Byouin no
Hitobito, Kawarazakike no Ichizoku, Ai Shimai; SILK0.DAT ... made by
"mdataX.exe ver 1.02"):

* a text header and zeros up to 1F4h;
* a dword, the directory's size;
* the directory: 24-byte entries, a name (16 bytes, NUL padded), the
  member's offset from the end of the directory and its size (dwords),
  encrypted: every byte XORed with the encrypted byte before it, the first
  with a key (where the game keeps it differs: a byte of SIL.EXE, or of the
  archive's header);
* the members, stored as they are.

Only the directory's first byte, the first letter of the first member's
name, needs the key; it is read as "?", and taken from a name the scripts
give where one fits (name_first: Kawarazakike's SILK1.DAT opens with
START.MES); a rebuilt directory keeps that byte as it was, so every other
byte re-encrypts exactly without the key.
"""
import re
import struct

HEAD = 0x1F4


class Archive:
    def __init__(self, raw):
        self.raw = raw
        n = struct.unpack_from("<I", raw, HEAD)[0]
        enc = raw[HEAD + 4:HEAD + 4 + n]
        dec = bytearray(enc)
        dec[0] = ord("?")
        for i in range(n - 1, 0, -1):
            dec[i] = enc[i] ^ enc[i - 1]
        self.first = enc[0]
        self.base = HEAD + 4 + n
        self.entries = []
        for k in range(n // 24):
            e = dec[24 * k:24 * k + 24]
            name = bytes(e[:16]).split(b"\0")[0].decode("ascii", "replace")
            off, size = struct.unpack_from("<II", e, 16)
            self.entries.append((name, off, size, bytes(e[:16])))
        if not self.entries or any(n and not re.fullmatch(r"[!-~]+", n) for n, *_ in self.entries):
            raise ValueError("not a Silky's data archive (its directory does not decode)")

    def name_first(self, known):
        """The first member's name, its first letter taken from the names
        in known that fit the rest of it."""
        name, off, size, raw_name = self.entries[0]
        fits = {k.upper() for k in known if len(k) == len(name) and k[1:].upper() == name[1:].upper()}
        if len(fits) == 1:
            self.entries[0] = (fits.pop(), off, size, raw_name)

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
        enc[0] = self.first
        for i in range(1, len(dec)):
            enc[i] = dec[i] ^ enc[i - 1]
        return bytes(self.raw[:HEAD]) + struct.pack("<I", len(dec)) + bytes(enc) + bytes(body)


class DiskArchive:
    """Silky's other data archive (SIL.EXE: Mobius Roid, Jack, Valentine
    Kiss 2; DISK_A ... DISK_E): a word, the count; that many 20-byte
    entries (a name, 14 bytes NUL padded; the offset from the end of the
    directory, a dword; the size, a word), every byte of them XORed with
    its offset in the file plus a constant (97h in these games, read off
    the first name's padding); the members, stored as they are."""

    def __init__(self, raw):
        self.raw = raw
        n = struct.unpack_from("<H", raw, 0)[0]
        # (the first name's last byte is padding: 0 once decoded)
        self.k = (raw[2 + 13] - (2 + 13)) & 0xFF
        dec = bytes(raw[i] ^ ((i + self.k) & 0xFF) for i in range(2, 2 + 20 * n))
        self.base = 2 + 20 * n
        self.entries = []
        for j in range(n):
            e = dec[20 * j:20 * j + 20]
            off, size = struct.unpack_from("<IH", e, 14)
            self.entries.append((e[:14].split(b"\0")[0].decode("ascii", "replace"), off, size, e[:14]))
        if not self.entries or any(not re.fullmatch(r"[!-~]+", n) for n, *_ in self.entries):
            raise ValueError("not a Silky's DISK_ archive (its directory does not decode)")

    def name_first(self, known):
        pass

    def names(self):
        return [e[0] for e in self.entries]

    def read(self, name):
        for n, off, size, _raw in self.entries:
            if n == name:
                return self.raw[self.base + off:self.base + off + size]
        raise KeyError(name)

    def rebuilt(self, changed):
        """The archive with the members in changed put in, laid out anew.
        A member keeps its whole span (up to the next member, or the end of
        the file: a member past 64 KB has only its size's low word in the
        directory, and some archives end with a few bytes more)."""
        body = bytearray()
        dec = bytearray()
        offs = sorted({off for _n, off, _s, _r in self.entries}) + [len(self.raw) - self.base]
        for name, off, size, raw_name in self.entries:
            if name in changed:
                data = changed[name]
                if len(data) > 0xFFFF:
                    raise SystemExit("%s: %d bytes, a DISK_ archive member holds 65535" % (name, len(data)))
                size = len(data)
            else:
                data = self.raw[self.base + off:self.base + offs[offs.index(off) + 1]]
            dec += raw_name + struct.pack("<IH", len(body), size)
            body += data
        head = bytearray(self.raw[:2])
        head += bytes(b ^ ((i + 2 + self.k) & 0xFF) for i, b in enumerate(dec))
        return bytes(head + body)
