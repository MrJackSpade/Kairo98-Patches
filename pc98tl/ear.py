"""The EAR archive of the EQAP32 engine (LOVE.EAR: Love Escalator).

A dword, the count of files; then for each a 24-byte entry: its name (16 bytes, NUL-padded), its place
in the archive and its length (dwords); then the files.  The entries are in name order.  `read` gives
[(name, bytes)]; `write` lays an archive out again, its entries sorted by name and the files in that
order.
"""
import struct


def read(d):
    n = struct.unpack_from("<I", d, 0)[0]
    out = []
    for k in range(n):
        name, at, size = struct.unpack_from("<16sII", d, 4 + 24 * k)
        out.append((name.rstrip(b"\0").decode("ascii"), d[at:at + size]))
    return out


def write(files):
    files = sorted(files, key=lambda f: f[0].encode("ascii"))
    head = bytearray(struct.pack("<I", len(files)))
    at = 4 + 24 * len(files)
    body = []
    for name, data in files:
        nm = name.encode("ascii")
        if len(nm) > 15:
            raise ValueError("%s: a name past 15 bytes" % name)
        head += struct.pack("<16sII", nm, at, len(data))
        body.append(data)
        at += len(data)
    return bytes(head) + b"".join(body)
