"""The "LZ96" packing of K. Hoshino's AVG and ANIME SYSTEM (ANI.EXE: Rookies), its scripts (*.SCP).

"LZ96", the unpacked length (a dword), then a bit stream read from the top bit of big-endian words
(`unpack`, the program's 7912h-7AFEh): a 0 bit and 8 bits a byte; a 1 bit a copy: its distance back
in as many bits as the output's length has (14 once it is 4000h or more), its length 2 and one more
for each 0 bit before a 1 bit, a sixth 0 bit ending the run and 8 bits giving the length instead.
`pack` writes it (the longest earlier match within the distance's reach, else a byte).
"""
import struct

MAGIC = b"LZ96"


def unpack(src):
    if src[:4] != MAGIC:
        raise ValueError("not LZ96")
    size = struct.unpack_from("<I", src, 4)[0]
    data = src[8:]
    pos = 0

    def bits(n):
        nonlocal pos
        v = 0
        for _k in range(n):
            i = (pos >> 4) * 2
            w = (data[i] << 8 | data[i + 1]) if i + 1 < len(data) else (data[i] << 8 if i < len(data) else 0)
            v = (v << 1) | ((w >> (15 - (pos & 15))) & 1)
            pos += 1
        return v
    out = bytearray()
    while len(out) < size:
        if not bits(1):
            out.append(bits(8))
            continue
        p = len(out)
        dist = bits(p.bit_length() if p < 0x4000 else 14)
        ln = 2
        while not bits(1):
            ln += 1
            if ln == 8:
                ln = bits(8)
                break
        for _k in range(ln):
            out.append(out[len(out) - dist])
    return bytes(out[:size])


def pack(data):
    out_bits = []

    def put(v, n):
        for k in range(n - 1, -1, -1):
            out_bits.append((v >> k) & 1)
    chains, i, n = {}, 0, len(data)

    def add(p):
        if p + 2 <= n:
            chains.setdefault(data[p:p + 2], []).append(p)
    while i < n:
        reach = (1 << i.bit_length()) - 1 if i < 0x4000 else 0x3FFF
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 2], [])[-64:]):
            if i - j > reach:
                break
            k = 0
            while k < 255 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 255:
                    break
        if best >= 2:
            put(1, 1)
            put(i - at, i.bit_length() if i < 0x4000 else 14)
            if best < 8:
                put(1, best - 1)                # (best - 2 zero bits, then a 1)
            else:
                put(0, 6)
                put(best, 8)
            for p in range(i, i + best):
                add(p)
            i += best
        else:
            put(0, 1)
            put(data[i], 8)
            add(i)
            i += 1
    while len(out_bits) % 16:
        out_bits.append(0)
    body = bytearray()
    for k in range(0, len(out_bits), 8):
        b = 0
        for bit in out_bits[k:k + 8]:
            b = (b << 1) | bit
        body.append(b)
    return MAGIC + struct.pack("<I", n) + bytes(body)
