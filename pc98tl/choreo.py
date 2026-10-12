"""The scenario files (*.SCE) of Arigata-ya's "Choreographer Inter-Book View Finder" (CHOREOV.EXE: Tenkousei).

The program reads CHOREO_V.INI, which names the game's INI ("SI\tTENKOU.ini"); that INI's FILE section
numbers the scenario files (`files`).  A scenario is bytecode for a stack machine, read from its start;
the operations' lengths are the interpreter's (its handlers at 28C:0F0 on):

* one byte: 12, 15, 16, 1A, 1B, 1C, 40-43, 48, 4C (return), C0-FE (on the stack), 00 (end);
* three bytes (an operation and a word): 08-0D, 10-14, 18, 19, 20-24, 28-2C, 30-32, 34-36, 38, 39, 3C,
  3D; 13 is a string, its word the length of the bytes that follow (the text and its NUL);
  49 (a jump when the test failed) and 4A (a jump) take the place in the file to go to;
* 4B, four bytes: a call, the scenario's number (in the FILE section) and the place in it.

A message is a string op 13 followed by CA, added to a text box ("11 var 1B 13 len text 1B CA 12"): a
box takes several such pieces, each going on where the last ended; the program breaks its lines at the
box's edge and pages a full box.  A choice's text is followed by D0, a menu's by C3.  Text is Shift-JIS,
0Ah a new line.

`parse` splits a file into its operations; `build` writes all the files again with new strings, the jumps
and calls moved to where their operations now are.
"""
import struct

ONE = {0x00, 0x12, 0x15, 0x16, 0x1A, 0x1B, 0x1C, 0x40, 0x41, 0x42, 0x43, 0x48, 0x4C,
       0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xD0, 0xD1,
       0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE8, 0xE9, 0xEC, 0xFE}
THREE = {0x08, 0x09, 0x0C, 0x0D, 0x10, 0x11, 0x13, 0x14, 0x18, 0x19, 0x20, 0x21, 0x22, 0x23, 0x24,
         0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x30, 0x31, 0x32, 0x34, 0x35, 0x36, 0x38, 0x39, 0x3C, 0x3D,
         0x49, 0x4A}
STR, JUMPS, CALL = 0x13, (0x49, 0x4A), 0x4B
KIND = {0xCA: "msg", 0xD0: "choice", 0xC3: "menu"}


def files(ini):
    """{number: file name (upper case)} from the game INI's FILE section."""
    out, sec = {}, None
    for line in ini.decode("cp932").splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" not in line:
            sec = line.upper()
            continue
        if sec == "FILE":
            f = line.split("\t")
            out[int(f[0])] = f[1].upper()
    return out


def parse(d):
    """[(place, op, bytes)]."""
    i, out = 0, []
    while i < len(d):
        op = d[i]
        if op in ONE:
            n = 1
        elif op in THREE:
            n = 3 + (struct.unpack_from("<H", d, i + 1)[0] if op == STR else 0)
        elif op == CALL:
            n = 4
        else:
            raise ValueError("unknown operation %02X at %X" % (op, i))
        out.append((i, op, d[i:i + n]))
        i += n
    if i != len(d):
        raise ValueError("an operation past the file's end")
    return out


def strings(ops):
    """[(index in ops, kind, text bytes without the NUL, variable, box)]: the strings a kind's
    operation uses.  The text goes to a box held in a variable ("11 var" before it); the box is made by
    "0C window 14 type 18 var" (a message: window 0 the message window, 1 the date's box), so the
    variable's last such store gives the box, (window, type) (None if the file made none: a choice's
    box is made by a routine of TENKOU00.SCE's)."""
    out, win = [], {}
    for k, (_a, op, b) in enumerate(ops):
        if op == 0x18 and k >= 2 and ops[k - 1][1] == 0x14 and ops[k - 2][1] == 0x0C:
            win[b[1:]] = (struct.unpack_from("<H", ops[k - 2][2], 1)[0],
                          struct.unpack_from("<H", ops[k - 1][2], 1)[0])
        if op != STR:
            continue
        nxt = next((o for _p, o, _b in ops[k + 1:k + 4] if o != 0x1B), None)
        if nxt in KIND:
            j = k - 1                           # (back over 1B and a number pushed with the text)
            while j > 0 and ops[j][1] in (0x1B, 0x10):
                j -= 1
            var = ops[j][2][1:] if ops[j][1] == 0x11 else None
            out.append((k, KIND[nxt], b[3:].rstrip(b"\0"), var, win.get(var)))
    return out


def build(scripts, new):
    """scripts {number: bytes}; new {(number, index in ops): text bytes}.  {number: bytes}, the files
    whose strings changed or whose calls' places moved written again (the rest as they were)."""
    ops = {n: parse(d) for n, d in scripts.items()}
    moved = {}
    for n, p in ops.items():
        at, m = 0, {}
        for k, (a, op, b) in enumerate(p):
            m[a] = at
            at += 3 + len(new[(n, k)]) + 1 if (n, k) in new else len(b)
        m[len(scripts[n])] = at
        moved[n] = m
    out = {}
    for n, p in ops.items():
        buf = bytearray()
        for k, (a, op, b) in enumerate(p):
            if (n, k) in new:
                s = new[(n, k)] + b"\0"
                if len(s) > 0xFFFF:
                    raise ValueError("a string past 65535 bytes")
                buf += bytes([STR]) + struct.pack("<H", len(s)) + s
            elif op in JUMPS:
                buf += bytes([op]) + struct.pack("<H", moved[n][struct.unpack_from("<H", b, 1)[0]])
            elif op == CALL:
                buf += b[:2] + struct.pack("<H", moved[b[1]][struct.unpack_from("<H", b, 2)[0]])
            else:
                buf += b
        if len(buf) > 0xFFFF:
            raise ValueError("scenario %d past 65535 bytes" % n)
        out[n] = bytes(buf)
    return out
