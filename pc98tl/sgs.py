"""Sogna's SGS (SGS.COM: Viper V6, V8, V10, V12, their RS editions, Animahjong X): the .SIL scripts
and the half-width English patch.

SGS.COM reads a script (NAME.SIL, at most 4000h bytes; LOAD_SIG: the read's count and address,
8000h in V6, V10 and Animahjong X, 9000h in the RS editions of V8 and V10 and in V12, 6000h in V8)
into its own segment (the pictures' buffer after it) and runs it op by op: its table of routines
(DISPATCH) by the op's number.  The ops' lengths are read off the routines; each build of the
program has its own table, so an op is known by its routine's code (RULES: a hash of the routine's
first instructions, the numbers left out, to its rule): a fixed length, a string ended by NUL after
the op's first bytes, or one of the ops with lists (a menu, a message, ...).  The ops that go
somewhere (the goto, the conditional jumps, the call) and the ops that set where ESC goes back to
hold a word, the script offset; nothing else in a script is an address, so a script may grow and
shrink when those words move with it.

A message (op 02, and op 72's: the program keeps its address and draws it from the timer while the
ops after it run; it skips the op to its NUL) is JIS pairs (7-bit, two bytes a character) up to a
NUL: 216F "￥" a new line, 2174 "＃" a key wait, 2130 a clear, 2175 a pause, 2177 / 2173 / 2170 and
two bytes the colour, an inserted string (a speaker's name: op 26 sets the strings, by slot, and
2173's second byte less 41h is the slot) and the speed; a byte with its top bit set starts an
inline picture (it and six bytes: a word and a picture op's four).  V10 RS has 2143 and two bytes
too, the two drawn as a character; V8 has no 2175.  A build's commands are read off its message
loop (the words it compares a pair with, after MSG_SIG).  The window (op 03: its left column, top
row, width in characters and rows; the program keeps it from script to script) breaks the line at
its right edge and scrolls.  A menu (op 00) is a count and items of variants (a flag and JIS
text); op 1B sets a system message (disk prompts).  The program's own lines (`console`) are
Shift-JIS it prints through DOS before the game starts.

The patch (`patch_program`): a helper at the end of the script's room (the program's own image runs
up to the script's address, and past it in Animahjong X), so every script is written with the
helper at that place, after zeros, and a script may take the room less the helper.  In a message
(and a menu's item) 7Fh, which no JIS pair starts with, turns half-width letters on and off:
between two 7Fh each byte is an ASCII letter, written to the text VRAM as one cell (the program's
own pairs take two) in the message's colour; the column moves on by one and the line breaks at the
window's edge as for the program's characters.  V10 RS's writer draws through a routine with the
pair and the colour pushed, which can draw into the graphics instead (op 9A sets that; no script
uses it), so the helper writes the text VRAM there too.
"""
import hashlib
import re
import struct

from .adl import _asm16

DISPATCH = re.compile(rb"\xac\x8a\xd8\x32\xff\xd1\xe3\xff\xa7(..)", re.S)
HALF = 0x7F
# the script's read: mov ah, 3Fh / mov cx, count / mov dx, address / int 21h
LOAD_SIG = re.compile(rb"\xb4\x3f\xb9(..)\xba(..)\xcd\x21", re.S)
# the message loop's head: lodsb / or al, al / jne +3 / jmp end / jns +3 / jmp picture; then mov ah,
# al / lodsb and the commands' compares (cmp ax, word / jne +3 / jmp, or je)
MSG_SIG = re.compile(rb"\xac\x0a\xc0\x75\x03\xe9(..)\x79\x03\xe9(..)", re.S)
# the commands' operand bytes (the others have none)
OPERANDS = {0x2177: 2, 0x2173: 2, 0x2170: 2, 0x2143: 2}
COMMANDS = {0x2174, 0x2130, 0x216F, 0x2175} | set(OPERANDS)
# a menu's text loop: lodsb / or al, al / je +8 / mov ah, al / lodsb / call writer / jmp short back
MENU_SIG = re.compile(rb"\xac\x0a\xc0\x74\x08\x8a\xe0\xac\xe8(..)\xeb\xf3", re.S)
# the message's character writer: row, column, colour (written to the text VRAM here, or by a routine
# the pair and the colour are pushed for, V10 RS); then the column moved on by two, the window's edge
# (width * 2 + left) and the jumps to the loop and to the new line (a short one in V8)
_WRITER_HEAD = rb"\xa0(?P<row>..)\xb1\xa0\xf6\xe1\x8a\x16(?P<col>..)\x32\xf6\xd1\xe2\x03\xc2\x8b\xf8"
_WRITER_TAIL = (rb"\x80\x06(?P=col)\x02\xa0(?P<wid>..)\xd0\xe0\x02\x06(?P<left>..)\x3a\x06(?P=col)\x74\x03"
                rb"\xe9(?P<loop>..)(?:\xe9(?P<nl>..)|\xeb(?P<nls>.))")
WRITER_SIGS = [
    re.compile(_WRITER_HEAD + rb"\xa0(?P<attr>..)\x26\x88\x85\x00\x20\x26\x88\x85\x02\x20\x58\x2c\x20\x24"
               rb"\x7f\xab\x0c\x80\xab" + _WRITER_TAIL, re.S),
    re.compile(_WRITER_HEAD + rb"\x5a\xa0(?P<attr>..)\x50\x52\xe8.." + _WRITER_TAIL, re.S),
]

# routine hash: rule.  An int is the op's length; ("jmp", length, at) an op with a script offset at
# `at` (("call", ...) the call, which "ret" returns from); ("str", n) a NUL-ended string after the
# op's first n bytes; a name an op with lists.
RULES = {
    # Viper V6 (SGS.COM 26749 bytes)
    '8817f6900b90': 'menu',
    '8b95bda64009': 5,
    'd785cd17711c': 'msg',
    'b8790b651569': 5,
    'c8ef1059cbc3': 3,
    '2f458bd6df8d': ('jmp', 3, 1),
    'c3a02e24085c': ('str', 3),
    '78c79b28eec5': ('str', 4),
    'ee5a866d5129': 2,
    '0166b4ed7515': 3,
    '0d8de63c48ae': 2,
    '551f8c61c7dc': 1,
    '9eb561121041': 'op0c',
    '0bf57a79aa08': 3,
    '05cb4a3ac606': 1,
    'b886fbdcf202': ('str', 3),
    '372d6765bccc': 1,
    'c7ea64ba4a0d': 2,
    '3d6bb68204d3': ('jmp', 5, 3),
    '08013921a9a9': ('jmp', 5, 3),
    '6865495f1953': 2,
    '36bde37219ce': ('jmp', 4, 2),
    'e9d0877b1d2a': 3,
    'a0f951352695': ('jmp', 3, 1),
    '1a1d569f5ebb': 1,
    'cf12c5fff82e': 3,
    '09e817a7b91e': 1,
    '010ba0f3ce45': ('str', 2),
    '2dfba4d12b6e': 6,
    '412d1eff5b43': 'op1f',
    '851004f01742': ('str', 3),
    '9bf3d3d73590': ('str', 3),
    'd2e53316ec65': 3,
    'ee523c833832': ('call', 3, 1),
    '47d85d19e358': 'ret',
    'cf74592a0019': 1,
    '57e99b248ea6': 'op26',
    'd7e0d10ed50f': 5,
    'c8685d1cd4b9': 4,
    'dd63f8aee0c9': 'pairs3',
    'ab6567b7dcc4': 1,
    '09c4b25752b5': 1,
    '38ab32fee106': 1,
    '79442e0a0f10': 1,
    'e80b1d82e26a': 7,
    'd91b523e38e4': ('str', 5),
    '840498adbdcf': 1,
    'dd2df8f15f88': 3,
    'cd3cfbda656b': 1,
    'a81c61848311': 3,
    '373a4e3e5198': 2,
    'f663ff62430a': 1,
    '3129e7963b01': 7,
    '99ad51eced10': 1,
    'd48b76be39b7': 2,
    '03d634bd3968': ('str', 4),
    'a2a4376802d5': 2,
    '1327168599eb': 1,
    '5b4b0d7aa379': 3,
    '40ef3c5617aa': 1,
    'f58cd8e97c98': 1,
    'c7b7977c4bfb': ('jmp', 5, 3),
    '09ec338c601a': ('jmp', 5, 3),
    '70e6f21617ad': 3,
    '352fe2f729db': 2,
    'ded2b13159d4': 1,
    '7ef9f098ef6b': 3,
    '66b2001fde49': 1,
    'b5e021e0c6cb': 3,
    'ca490a0ee565': ('jmp', 3, 1),
    'b6993628660b': 1,
    '4eccb6646e17': 5,
    '3e0c2f2dd440': 2,
    'a9757378f151': 3,
    '51ee670db9d1': 3,
    'fc9332503746': 2,
    '22c5f4a179b6': 1,
    '127da34d9532': 2,
    'a66701a269b6': 2,
    'e7a75f932b18': 9,
    'e91cbc268cfd': 1,
    'afea898a6ecc': 15,
    'eda727fa46e6': 1,
    '36929022107b': 4,
    'b03fcd477ea5': 9,
    'c6cabc864511': 'pairs4',
    '307195fa2ee4': 2,
    '7882b2c65d81': 1,
    '55daaa1c1d49': 16,
    '3cca11447a2d': 1,
    '9f46c9a890b1': 1,
    'bfdc49d16055': 2,
    'eeb79abdae99': 10,
    'd44da7d850a3': 2,
    'ed4a7a154f6c': 2,
    '2ad79fc933aa': 'bgmsg',
    'de449e159286': 1,
    '0eb6bd9ba1fe': 3,
    '4c4946c6421c': 3,
    '7295f5952df3': 2,
    'd6e3d046ff98': 65,
    'fe310c4941e3': 2,
    '63e44f418652': 2,
    # the other builds (Viper V6 RS, V8, V8 RS, V10, V10 RS, V12, Animahjong X)
    '95b54724d9db': 1,
    '780d26370128': 1,
    '3342cfcb740b': ('jmp', 4, 2),
    'd764eee1ca5a': 'menu',
    '68406161717c': 3,
    'e78099834f52': ('str', 3),
    '5e00eea53b3d': 1,
    '9a2553e56040': 9,
    '63f4af533709': 5,
    'fb754c7504ac': 2,
    'b442de424290': 1,
    'a0f417a3f55b': ('str', 3),
    'd39b833a7230': 1,
    '9e213d5a534b': 4,
    '0d41e6b4dd80': 'msg',
    '3513556f3341': 1,
    '9eb9174a97fe': 3,
    '06f875a6afa4': 1,
    'c3c4e3a0fb72': 2,
    '93c7e376dbfc': 3,
    '7d14e519acec': 9,
    '2ec098a385ba': ('str', 4),
    '9a72f268f939': 2,
    'f320f143d075': 3,
    '558dc7cc432d': 5,
    'b591b01a90c5': 10,
    '82c17c38a3f1': 'pairs4',
    'b1841b6089cf': 11,
    '26c7ffc91ae8': 7,
    'e5165fb8d87b': 'op0c',
    '595f57bf4bfd': 1,
    '30323b3e8622': ('list', 2, 4, 3),
    '582a3ab1b6f1': 3,
    'b67e29ebd391': ('until0', 1, 3),
    'b6586aeb5e5e': 1,
    '1e19719c85ae': 'pairs3',
    'd430ea06c811': 3,
    '1f04eaf114c3': 3,
    '70764a613eb7': 2,
    '5a5143123318': 2,
    '714770eea3bf': 10,
    '4d15898ae3ef': 1,
    '2efa99acc5f7': 1,
    '56cd4c0b36cb': 1,
    '1b6833c1ba42': 9,
    '0c375ac82b66': 'pairs3',
    'c34f8f706122': 12,
    '7e78876620bc': 10,
    'b9bfd8152e6b': 1,
    '8414d06ad5f4': 3,
    'dd9223a52d0d': ('str', 2),
    '955ef1231a0b': ('jmp', 3, 1),
    '944fda960bc5': ('str', 4),
    '0f60e350b2e4': 'menu',
    'f6d91aace7c2': 'pairs3',
    '419d2c8c03d7': 1,
    '07d1253baf8d': ('lenlist', 3, 4, 4),
    'c01a80534200': 2,
    '28cccc64b6a6': 8,
    '5192c1028a5a': 2,
    '67f3c9b7576c': 10,
    '9a4d45c57c2b': ('str', 4),
    'f664ec6e0fdf': 5,
    '4cc6af097f9f': 9,
    '4481d56edbe4': 5,
    '84c9be7aee65': 19,
    '4f40c8cfc0e5': 2,
    '29d39d6517e0': 2,
    '00ce11185ca0': 'pairs3',
    '76f601830265': 1,
    '379623ca2c59': 'op0c',
    'd83e85f4539d': 2,
    '59e5b9732757': 1,
    '1e5b6233d087': ('str', 3),
    '19ce628633bd': 5,
    '80c678b40434': 1,
    'e00e9fe5f66d': 'msg',
    '4fa65aa945ab': 15,
    'f8f498a382bd': 1,
    '2daf716c6544': 'pairs4',
    '2889daf9bf84': 2,
}


def _routine_hash(prog, a):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    out = []
    if not 0x100 <= a < 0x100 + len(prog):
        return None
    for i in Cs(CS_ARCH_X86, CS_MODE_16).disasm(prog[a - 0x100:a - 0x100 + 160], a):
        out.append(i.mnemonic + " " + re.sub(r"0x[0-9a-f]+", "N", i.op_str))
        if len(out) >= 40 or i.mnemonic in ("ret", "retf", "jmp"):
            break
    return hashlib.sha1("\n".join(out).encode()).hexdigest()[:12]


class Build:
    """A build of SGS.COM: its ops' rules, read off their routines."""

    def __init__(self, prog):
        m = DISPATCH.search(prog)
        if m is None:
            raise ValueError("SGS.COM: the ops' table not found")
        self.prog, self.table = prog, struct.unpack("<H", m.group(1))[0]
        self.rules = {}
        ml = list(LOAD_SIG.finditer(prog))
        if len(ml) != 1:
            raise ValueError("SGS.COM: the script's read found %d times" % len(ml))
        self.room, self.base = struct.unpack("<HH", ml[0].group(1) + ml[0].group(2))
        mm = list(MSG_SIG.finditer(prog))
        if len(mm) != 1:
            raise ValueError("SGS.COM: the message loop found %d times" % len(mm))
        self.msg_site = mm[0]
        i = mm[0].end()
        if prog[i:i + 3] != b"\x8a\xe0\xac":
            raise ValueError("SGS.COM: the message loop's compares not found")
        i += 3
        self.cmds = {}
        while prog[i] == 0x3D:
            w = struct.unpack_from("<H", prog, i + 1)[0]
            if w not in COMMANDS:
                raise ValueError("SGS.COM: a message command %04x not known" % w)
            self.cmds[w] = OPERANDS.get(w, 0)
            if prog[i + 3:i + 6] == b"\x75\x03\xe9":
                i += 8
            elif prog[i + 3] == 0x74:
                i += 5
            else:
                raise ValueError("SGS.COM: the message loop's compare at %x not known" % (i + 0x100))

    def rule(self, op):
        if op not in self.rules:
            a = struct.unpack_from("<H", self.prog, self.table - 0x100 + 2 * op)[0]
            h = _routine_hash(self.prog, a)
            if h not in RULES:
                raise ValueError("SGS.COM: op %02x (routine %04x, %s) not known" % (op, a, h))
            self.rules[op] = RULES[h]
        return self.rules[op]


def _strend(d, i):
    return d.index(0, i) + 1


def message_end(d, i, cmds):
    """The end (after its NUL) of JIS text starting at i: cmds {command: its operands' bytes}, a
    message's (None: a menu's item, pairs only)."""
    while True:
        b = d[i]
        if b == 0:
            return i + 1
        if b == HALF:
            i += 1
            while d[i] != HALF and d[i] != 0:
                i += 1
            if d[i] == HALF:
                i += 1
            continue
        if b & 0x80 and cmds is not None:
            i += 7
            continue
        w = b << 8 | d[i + 1]
        i += 2
        if cmds:
            i += cmds.get(w, 0)


def op_end(d, i, rule, cmds):
    if isinstance(rule, int):
        return i + rule
    if rule[0] in ("jmp", "call"):
        return i + rule[1]
    if rule == "ret":
        return i + 1
    if rule[0] == "str":
        return _strend(d, i + rule[1])
    if rule[0] == "until0":
        # ("until0", the bytes before the entries, an entry's size after its nonzero first byte); a 0 ends
        j = i + rule[1]
        while d[j]:
            j += 1 + rule[2]
        return j + 1
    if rule[0] == "lenlist":
        # ("lenlist", where the count is, the bytes before the entries, the size of each unit): each
        # entry a byte L and L units
        j = i + rule[2]
        for _ in range(d[i + rule[1]]):
            j += 1 + rule[3] * d[j]
        return j
    if rule[0] == "list":
        # ("list", where the count is, an entry's size, the bytes before the entries)
        return i + rule[3] + rule[2] * d[i + rule[1]]
    if rule == "msg":
        return message_end(d, i + 1, cmds)
    if rule == "bgmsg":
        return _strend(d, i + 1)
    if rule == "menu":
        cnt = d[i + 2]
        j = i + 3
        for _ in range(cnt):
            n = d[j]
            j += 1
            for _ in range(n):
                j = message_end(d, j + 1, None)
        return j
    if rule == "op0c":
        return i + 6 + 4 * d[i + 5]
    if rule == "op1f":
        return i + (12 if d[i + 1] else 8)
    if rule == "op26":
        j = i + 2
        while True:
            b = d[j]
            j += 1
            if b == 0xFF:
                j += 4
            elif b == 0:
                return j
    if rule in ("pairs3", "pairs4"):
        j = i + (3 if rule == "pairs3" else 4)
        while True:
            b = d[j]
            j += 1
            if b == 0:
                return j
            j += 1
    raise ValueError("rule %r" % (rule,))


def walk(d, build):
    """[(addr, op, end, rule)]: the script's ops, one after another up to its end (EOF bytes 1Ah at
    the end left out)."""
    end = len(d)
    while end and d[end - 1] == 0x1A:
        end -= 1
    out, i = [], 0
    while i < end:
        op = d[i]
        rule = build.rule(op)
        e = op_end(d, i, rule, build.cmds)
        if e > end:
            raise ValueError("op %02x at %x runs past the end" % (op, i))
        out.append((i, op, e, rule))
        i = e
    return out


def texts(d, ops):
    """[(addr of the op, kind, start, end)]: the text in the script (end: its NUL): "msg" a message,
    "item" a menu's item, "system" a system message (op 1B), "var" a string op 26 sets."""
    out = []
    for a, op, e, rule in ops:
        if rule in ("msg", "bgmsg"):
            out.append((a, "msg", a + 1, e - 1))
        elif rule == "menu":
            j = a + 3
            for _ in range(d[a + 2]):
                n = d[j]
                j += 1
                for _ in range(n):
                    k = message_end(d, j + 1, None)
                    out.append((a, "item", j + 1, k - 1))
                    j = k
        elif rule == "op26":
            out.append((a, "var", a + 2, e - 1))
        elif rule == ("str", 2) and op == 0x1B:
            out.append((a, "system", a + 2, e - 1))
    return out


def rebuild(d, ops, new, limit):
    """The script with new text: new {(start, end): bytes} (the text's place without its NUL); the
    jumps' offsets moved.  OverflowError past limit bytes."""
    starts = sorted(new)
    moved, out, pos = {}, bytearray(), 0
    k = 0
    for a, op, e, rule in ops:
        moved[a] = len(out)
        i = a
        while k < len(starts) and starts[k][0] < e:
            s, t = starts[k]
            out += d[i:s] + new[(s, t)]
            i = t
            k += 1
        out += d[i:e]
    end = ops[-1][2] if ops else 0
    moved[end] = len(out)
    out += d[end:]
    for a, op, e, rule in ops:
        if not isinstance(rule, int) and rule[0] in ("jmp", "call"):
            at = moved[a] + rule[2]
            t = struct.unpack_from("<H", d, a + rule[2])[0]
            if t not in moved:
                raise ValueError("a jump at %x to %x, not an op" % (a, t))
            struct.pack_into("<H", out, at, moved[t])
    if len(out) > limit:
        raise OverflowError(len(out))
    return bytes(out)


def patch_program(prog):
    """(SGS.COM patched, the helper): the helper's bytes go at the end of the script's room, every
    script written with them there (`helper_at`)."""
    build = Build(prog)
    prog = bytearray(prog)
    mn = list(MENU_SIG.finditer(prog))
    mw = [m for sig in WRITER_SIGS for m in sig.finditer(prog)]
    if len(mn) != 2 or len(mw) != 1:
        raise SystemExit("SGS.COM: the menus' loops and the writer found %d, %d times (2, 1 expected)" % (
            len(mn), len(mw)))
    site = build.msg_site.start() + 0x100
    end = (site + 8 + struct.unpack("<h", build.msg_site.group(1))[0]) & 0xFFFF
    w = mw[0]
    u = lambda g: struct.unpack("<H", w.group(g))[0]     # noqa: E731
    row, col, attr, wid, left = u("row"), u("col"), u("attr"), u("wid"), u("left")
    loop = (w.start("loop") + 0x102 + struct.unpack("<h", w.group("loop"))[0]) & 0xFFFF
    if w.group("nl") is not None:
        newline = (w.start("nl") + 0x102 + struct.unpack("<h", w.group("nl"))[0]) & 0xFFFF
    else:
        newline = (w.start("nls") + 0x101 + struct.unpack("<b", w.group("nls"))[0]) & 0xFFFF

    src = """
msg:
    test byte ptr cs:[{flag}], 1
    jnz mhalf
    lodsb
    or al, al
    jne m1
    JMPN {end}
m1:
    cmp al, {half}
    jne m2
    mov byte ptr cs:[{flag}], 1
    JMPN {loop}
m2:
    or al, al
    JMPN {cont}
mhalf:
    lodsb
    or al, al
    jne mh1
    mov byte ptr cs:[{flag}], 0
    JMPN {end}
mh1:
    cmp al, {half}
    jne mh2
    mov byte ptr cs:[{flag}], 0
    JMPN {loop}
mh2:
    push ax
    mov al, byte ptr [{row}]
    mov cl, 0xa0
    mul cl
    mov dl, byte ptr [{col}]
    xor dh, dh
    shl dx, 1
    add ax, dx
    mov di, ax
    mov al, byte ptr [{attr}]
    mov byte ptr es:[di + 0x2000], al
    pop ax
    xor ah, ah
    stosw
    inc byte ptr [{col}]
    mov al, byte ptr [{wid}]
    shl al, 1
    add al, byte ptr [{left}]
    cmp al, byte ptr [{col}]
    je mnl
    JMPN {loop}
mnl:
    JMPN {newline}
""".format(flag="FLAG", half=hex(HALF), end=hex(end), loop=hex(loop), cont=hex(site + 8), row=hex(row),
           col=hex(col), attr=hex(attr), wid=hex(wid), left=hex(left), newline=hex(newline))
    for k, m in enumerate(mn):
        s = m.start() + 0x100
        src += """
menu{k}:
    test byte ptr cs:[{flag}], 1
    jnz n{k}half
    lodsb
    or al, al
    jne n{k}1
    JMPN {done}
n{k}1:
    cmp al, {half}
    jne n{k}2
    mov byte ptr cs:[{flag}], 1
    JMPN {head}
n{k}2:
    JMPN {cont}
n{k}half:
    lodsb
    or al, al
    jne n{k}h1
    mov byte ptr cs:[{flag}], 0
    JMPN {done}
n{k}h1:
    cmp al, {half}
    jne n{k}h2
    mov byte ptr cs:[{flag}], 0
    JMPN {head}
n{k}h2:
    push ax
    mov al, byte ptr [{attr}]
    mov byte ptr es:[di + 0x2000], al
    pop ax
    xor ah, ah
    stosw
    JMPN {head}
""".format(k=k, flag="FLAG", half=hex(HALF), done=hex(s + 13), head=hex(s), cont=hex(s + 5), attr=hex(attr))
    # (the flag's byte goes after the code: its address a number, which keystone takes as 16-bit, where
    # a label it does not know yet comes out as a 32-bit address; the code's size the same for any)
    code, _l = _asm16(src.replace("FLAG", "0x7777"), build.base, ["msg"])
    org = build.base + build.room - len(code) - 1
    code, labs = _asm16(src.replace("FLAG", hex(org + len(code))), org, ["msg", "menu0", "menu1"])
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(code, org):
        pre = bytes(ins.bytes).lstrip(b"\x26\x2e\x36\x3e")
        if pre[:1] in (b"\x66", b"\x67"):
            raise SystemExit("SGS.COM: a 32-bit prefix in the helper at %x" % ins.address)
    helper = code + b"\0"

    def jmp(at, to):
        prog[at - 0x100:at - 0x100 + 5] = b"\xe9" + struct.pack("<H", (to - (at + 3)) & 0xFFFF) + b"\x90\x90"
    jmp(site, labs["msg"])
    for k, m in enumerate(mn):
        jmp(m.start() + 0x100, labs["menu%d" % k])
    return bytes(prog), helper


CONSOLE_REF = re.compile(rb"\xba(..)", re.S)
CONSOLE_TEXT = re.compile(rb"(?:[\x07\x0a\x0d\x20-\x7e]|[\x81-\x9f\xe0-\xfc][\x40-\xfc])*?\$", re.S)


def console(prog):
    """[(start, end)]: the program's own lines, printed through DOS (function 09h: mov dx, the text /
    int 21h within the next bytes, past a short jump to a shared one) before the game starts (its
    mode, a memory or a missing file): Shift-JIS up to a "$" (end: the "$"'s offset), image
    offsets."""
    out = set()
    for m in CONSOLE_REF.finditer(prog):
        if b"\xcd\x21" not in prog[m.end():m.end() + 10]:
            continue
        s = struct.unpack("<H", m.group(1))[0] - 0x100
        if not 0 <= s < len(prog):
            continue
        t = CONSOLE_TEXT.match(prog, s)
        if t and re.search(rb"[\x81-\x9f\xe0-\xfc]", t.group()):
            out.add((s, t.end() - 1))
    return sorted(out)


def helper_at(build, d, helper):
    """A script with the helper at the end of its room (zeros between); ValueError when it does not
    leave the room."""
    room = build.room - len(helper)
    if len(d) > room:
        raise ValueError(len(d))
    return d + bytes(room - len(d)) + helper
