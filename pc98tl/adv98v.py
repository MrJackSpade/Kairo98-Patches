"""ides' Adv98V script engine (Cocktail Soft / Fairytale games): MES
bytecode tokenizer.

The byte grammar (worked out from the files, with tomyun's juice decompiler
as a reference for the structure):

* 00-0F x        register (flag) test or set
* 10-1F x        variable test or set (10-1F x y with the later engines'
                 extended opcodes)
* 20             space (separates a sound command's type from its numbers)
* 21 ... 00|FF   an ASCII/SJIS string printed as it is
* 22 ... 22      a quoted argument (file names, command strings)
* 23-27          the numbers 0-4; 28 x a byte; 29-2C x y a 14-bit number
* 2D-7F          one hiragana (SJIS 82 9F + n-2D)
* 80-9F,E0-EF x  a two-byte SJIS character; 81 6F / 81 70 open and close a
                 loop, 81 90 waits for a key, 81 97 is a no-op
* A0-A4          block marks (A2 begin, A3 end, A4 separator, A0/A1 item list)
* A5-DF          commands (A5 text break, A6 text frame, A8 text colour,
                 AA text reset, BA call a procedure, ...), followed by their
                 numbers, arguments and blocks
* FF FF          end of a segment; FF FE end of the file

A few commands take operands the lexer must know about: D0 (sound) is
followed by its type letters and spaces, B4 (branch on a variable) and B6
by a variable letter, C8 (load to memory) by an argument and an optional
unquoted zero-ended name.
"""

TEXT_CTRL = {b"\x81\x6f", b"\x81\x70", b"\x81\x90", b"\x81\x97"}


def _sjis_lead(b):
    return 0x80 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def decrypt(data, key):
    """D5's encrypted segment tail: each byte's nibbles swapped, then XOR key."""
    return bytes((((c & 0xF0) >> 4) | ((c & 0x0F) << 4)) ^ key for c in data)


def encrypt(data, key):
    return bytes((((c ^ key) & 0xF0) >> 4) | (((c ^ key) & 0x0F) << 4) for c in data)


def tokenize(data, extraop=False):
    """[(kind, start, end)] covering every byte of the file.  Kinds: reg,
    var, spc, str (21 string), arg (22 string), num, chr1, chr2, ctrl
    (the four control characters), mark, cmd, sndtype, varname, argz,
    crypt (an encrypted segment tail, up to its FF FF), eos, eom, byte
    (anything else).  extraop: the later engines' opcodes (3-byte
    variables, CA, D5)."""
    out, i, n = [], 0, len(data)

    def add(kind, j):
        nonlocal i
        out.append((kind, i, j))
        i = j

    pending = None          # operand context after a command
    while i < n:
        b = data[i]
        if pending == "sound":
            j = i
            while j < n and (0x30 <= data[j] <= 0x39 or 0x41 <= data[j] <= 0x5A or 0x61 <= data[j] <= 0x7A):
                j += 1
            while j < n and data[j] == 0x20:
                j += 1
            pending = None
            if j > i:
                add("sndtype", j)
            continue
        if pending == "decrypt":
            pending = None
            if 0x23 <= b <= 0x2C:
                j = i + (1 if b <= 0x27 else 2 if b == 0x28 else 3)
                key = _num(data, i)
                add("num", j)
                if key:
                    k = data.find(b"\xff\xff", i)
                    add("crypt", k if k >= 0 else n)
                continue
        if pending == "varname":
            pending = None
            if 0x41 <= b <= 0x5A:
                add("varname", i + 1)
                continue
        if pending == "loadmem":
            # an argument, then a number or an unquoted zero-ended name
            if b == 0x22:
                j = data.index(0x22, i + 1) + 1
                add("arg", j)
                nb = data[i] if i < n else 0
                if not (0x23 <= nb <= 0x2C):
                    j = data.index(0, i) + 1
                    if j - 1 > i:
                        add("argz", j)
                pending = None
                continue
            pending = None
        if b <= 0x0F:
            add("reg", i + 2)
        elif b <= 0x1F:
            add("var", i + (3 if extraop else 2))
        elif b == 0x20:
            add("spc", i + 1)
        elif b == 0x21:
            j = i + 1
            while j < n and data[j] not in (0x00, 0xFF):
                j += 2 if _sjis_lead(data[j]) else 1
            add("str", min(j + 1, n) if j < n and data[j] == 0 else j)
        elif b == 0x22:
            add("arg", data.index(0x22, i + 1) + 1)
        elif 0x23 <= b <= 0x27:
            add("num", i + 1)
        elif b == 0x28:
            add("num", i + 2)
        elif 0x29 <= b <= 0x2C:
            add("num", i + 3)
        elif 0x2D <= b <= 0x7F:
            add("chr1", i + 1)
        elif _sjis_lead(b):
            add("ctrl" if bytes(data[i:i + 2]) in TEXT_CTRL else "chr2", i + 2)
        elif 0xA0 <= b <= 0xA4:
            add("mark", i + 1)
        elif 0xA5 <= b <= 0xDF:
            add("cmd", i + 1)
            if b == 0xD0:
                pending = "sound"
            elif b in (0xB4, 0xB6) or (extraop and b == 0xCA):
                pending = "varname"
            elif extraop and b == 0xD5:
                pending = "decrypt"
            elif b == 0xC8:
                pending = "loadmem"
        elif b == 0xFF and i + 1 < n and data[i + 1] == 0xFF:
            add("eos", i + 2)
        elif b == 0xFF and i + 1 < n and data[i + 1] == 0xFE:
            add("eom", i + 2)
        else:
            add("byte", i + 1)
    return out


def _num(data, i):
    b = data[i]
    if b <= 0x27:
        return b - 0x23
    if b == 0x28:
        return data[i + 1]
    return (b - 0x29) * 0x4000 + data[i + 1] * 0x80 + (data[i + 2] & 0x7F)


def char_text(data, kind, s, e):
    """A text token as a character."""
    if kind == "chr1":
        return bytes([0x82, 0x72 + data[s]]).decode("cp932")
    return bytes(data[s:e]).decode("cp932", "replace")
