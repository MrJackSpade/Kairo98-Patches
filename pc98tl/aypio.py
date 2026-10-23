"""Aypio's UK2 engine (Sex: SEX\\UK2.EXE, run under its driver NAX.COM): its archives, its scripts, and
English drawn half-width.

DLB archives (`dlb`, `dlb_bytes`; DATALIB1-4.DLB): "<< dlb file Ver1.00>>" and 0, a word (the count),
then 21-byte entries (a name of 13 bytes, the place and the size, dwords), then the members in turn.

A script (*.MES, "<< UK2 TEXT Ver1.00 >>" and 0, `Script`): commands run from byte 17h: 00 a block's end;
01 a value, an expression (set); 02 an address, a block; 03/04 a value (less/more by one); 'R' and a digit
(return); else a command of two letters (`GRAMMAR`: A0-A6, D0-D1, F0-FK, I0-I2, J0-J3, L0-L5, M0-M5, T0-T1,
U0-UK, W1-WL), its arguments as UK2.EXE reads them:
* a value: a byte, its top 3 bits the kind and the low 5 an index: 0 a register (1Fh: a word follows),
  1, 2, 6 a variable, 3 a string (bytes up to 0; 05h n and 06h n insert a word of a table), 4 an indexed
  one (an expression follows), 5 a byte follows;
* an expression: an operator byte (its low 7 bits, 1-7; 0 ends it empty) and a value, until an operator
  with bit 7 set;
* a condition: an expression, a comparison byte, an expression, then 0 (end), 1 (and) or 2 (or) and more;
* an address: a word, a place in the script (gotos, calls, the ifs' and loops' ends).
`Script` walks a whole script and finds every address and every string (`strings`); `rebuild` writes it
again with strings of other lengths, every address moved with what it points at.

Text: 01 C0h sets the message buffer (2002 bytes), the call (J1) after it shows it; T0 sets the inserted
words (05h n), T1 the names (06h n), U2 shows pages, W8 a menu's choices.  The bytes are the program's own
code: two-byte Shift-JIS, and single bytes as the characters of its table (`kana_table`, in UK2.EXE);
`\\` and a letter a command: \\r a new line, \\Cn a colour, \\Wnnn a wait, \\K the table's characters, \\k
bytes as themselves (ASCII drawn half-width by the program, so the English needs no program patch).
The program breaks a line at the window's edge by itself; a message's window shows 4 rows (the speaker's
row and 3), more are lost: the patcher breaks the English between words and puts a longer message's rest
in more messages, each shown by the same call.
"""
import re
import struct

HEAD = b"<< UK2 TEXT Ver1.00 >>\0"
BS = 0x5C
LIMIT = 0x88B8              # the scripts' room: a script and the ones that called it (UK2.EXE's check)
ROOM_MAX = 0xFFF0           # the room grown (`set_room`): its check adds 16-bit sizes
ROOM_ALLOC = re.compile(rb"\x6a\x00\x68(..)\x6a\x00\x6a\x00\x9a", re.S)     # push 0, room; push 0, 0; call
ROOM_CHECK = re.compile(rb"\x3d(..)\x76", re.S)                         # cmp ax, room; jbe


def set_room(img, room):
    """UK2.EXE's image with the scripts' room (its allocation and its check) made `room` bytes."""
    img = bytearray(img)
    for pat in (ROOM_ALLOC, ROOM_CHECK):
        at = [m.start(1) for m in pat.finditer(img) if struct.unpack("<H", m.group(1))[0] == LIMIT]
        if len(at) != 1:
            raise ScriptError("UK2.EXE: the scripts' room is found %d times, not once" % len(at))
        struct.pack_into("<H", img, at[0], room)
    return bytes(img)
MEMBER = 0xEA60             # a script's longest

GRAMMAR = {
    "A0": "V", "A1": "", "A2": "nV:6", "A3": "nE:20", "A4": "nE:20", "A5": "V", "A6": "",
    "D0": "", "D1": "E E",
    "F0": "V", "F1": "E V", "F5": "E", "F6": "V", "F7": "V", "F8": "E", "F9": "nE:3", "FA": "nE:5",
    "FB": "nE:5", "FC": "nE:2", "FD": "nE:2", "FE": "V", "FG": "V", "FH": "nE:2 V V V V V", "FI": "V",
    "FJ": "nE:3", "FK": "",
    "I0": "", "I1": "", "I2": "E",
    "J0": "A", "J1": "A", "J2": "V", "J3": "V",
    "L0": "C A", "L1": "C A", "L2": "A", "L3": "V E E E A", "L4": "C A", "L5": "C A",
    "M0": "V", "M1": "", "M2": "", "M3": "", "M4": "", "M5": "nE:2",
    "T0": "E*", "T1": "E*",
    "U0": "E", "U1": "nE:2", "U2": "E E*", "U3": "nE:2 V", "U4": "E E", "U5": "V E", "U6": "E E", "U7": "E",
    "U8": "nE:2", "U9": "V", "UA": "V", "UB": "V V", "UD": "E V", "UE": "E E*", "UF": "V E", "UG": "V",
    "UH": "E", "UI": "nE:6", "UJ": "E V", "UK": "E",
    "W1": "nE:7", "W2": "", "W3": "E", "W4": "nE:2", "W5": "V E", "W6": "E V E", "W7": "E", "W8": "V E*",
    "W9": "E", "WA": "E", "WB": "nE:2", "WC": "E", "WD": "E", "WE": "E", "WF": "E", "WG": "", "WH": "nE:5",
    "WI": "E", "WJ": "V E V", "WK": "nE:6", "WL": "nE:4",
}
# Sex 2's build (SEX2\UK2.EXE): commands gone, new ones, and others reading other arguments
GRAMMAR_2 = dict(GRAMMAR)
for _n in ("D0", "F6", "F7", "L5", "U4", "UA", "UF", "UG", "WJ"):
    del GRAMMAR_2[_n]
GRAMMAR_2.update({
    "I0": "nE:6", "I1": "V nE:6", "I2": "V V V", "M1": "nE:1", "M5": "nE:1",
    "F2": "", "F4": "V V V E V V", "I3": "V V V", "I4": "nE:4", "I5": "V", "I6": "", "M6": "V",
    "UC": "V E*", "UL": "E", "UM": "V V", "UN": "nE:3", "UO": "E", "UP": "nE:2 V V",
})
GRAMMARS = (GRAMMAR, GRAMMAR_2)
NAMES = re.compile(rb"A0(?:[A-Z][0-9A-Z])+")      # the program's table of its commands' names


def grammar(exe):
    """The grammar of the program's build: the one whose commands are its table's."""
    m = NAMES.search(exe)
    names = {m.group()[i:i + 2].decode() for i in range(0, len(m.group()), 2)} if m else set()
    for g in GRAMMARS:
        if set(g) == names:
            return g
    raise ScriptError("UK2.EXE: its commands' table matches no known build")


# ---- DLB --------------------------------------------------------------------------------------------------

def dlb(data):
    """[(name, place, size)]."""
    n = struct.unpack_from("<H", data, 22)[0]
    out = []
    for k in range(n):
        e = data[24 + 21 * k:45 + 21 * k]
        name = e[:13].split(b"\0")[0].decode("cp932", "replace")
        at, size = struct.unpack_from("<II", e, 13)
        out.append((name, at, size))
    return out


def dlb_bytes(data, members):
    """The archive with members replaced ({name: bytes})."""
    ents = dlb(data)
    head = bytearray(data[:24 + 21 * len(ents)])
    first = min(at for _n, at, _s in ents)
    body, pos = bytearray(data[24 + 21 * len(ents):first]), first
    for k, (name, at, size) in enumerate(ents):
        b = members.get(name, data[at:at + size])
        struct.pack_into("<II", head, 24 + 21 * k + 13, pos, len(b))
        body += b
        pos += len(b)
    return bytes(head) + bytes(body)


# ---- scripts ----------------------------------------------------------------------------------------------

class ScriptError(ValueError):
    pass


class Script:
    """A script walked: cmds [(place, name)], addrs [place of an address word], strings [(start, end)]
    (a string value's bytes, its 0 at end), each string's command (`owner`)."""

    def __init__(self, d, grammar=GRAMMAR):
        self.grammar = grammar
        if not d.startswith(HEAD):
            raise ScriptError("not a UK2 TEXT script")
        self.d, self.k = d, len(HEAD)
        self.cmds, self.addrs, self.strings = [], [], []
        self.owner = {}
        self._cmd = None
        while self.k < len(d):
            self._command()
        starts = {a for a, _c in self.cmds}
        for a in self.addrs:
            t = self.w(a)
            if t not in starts and t != len(d):
                raise ScriptError("an address at %x to %x, not a command" % (a, t))

    def w(self, a):
        return self.d[a] | self.d[a + 1] << 8

    def _b(self):
        if self.k >= len(self.d):
            raise ScriptError("the script ends inside a command at %x" % self.k)
        v = self.d[self.k]
        self.k += 1
        return v

    def _value(self):
        at = self.k
        c = self._b()
        t, i = c >> 5, c & 31
        if t == 0:
            if i == 0x1F:
                self.k += 2
        elif t == 3:
            s = self.k
            while True:
                x = self._b()
                if x == 0:
                    break
                if x in (5, 6):
                    self.k += 1
            self.strings.append((s, self.k - 1))
            self.owner[s] = self._cmd
        elif t == 4:
            self._expr()
        elif t == 5:
            self.k += 1
        elif t == 7:
            raise ScriptError("a value %02x at %x" % (c, at))

    def _expr(self):
        first = True
        while True:
            c = self._b()
            if c & 0x7F == 0:
                return not first
            if c & 0x7F > 7:
                raise ScriptError("an operator %02x at %x" % (c, self.k - 1))
            self._value()
            first = False
            if c & 0x80:
                return True

    def _cond(self):
        while True:
            self._expr()
            self._b()
            self._expr()
            j = self._b()
            if j == 0:
                return
            if j not in (1, 2):
                raise ScriptError("a condition's join %02x at %x" % (j, self.k - 1))

    def _addr(self):
        self.addrs.append(self.k)
        self.k += 2

    def _args(self, spec):
        for a in spec.split():
            if a == "V":
                self._value()
            elif a == "E":
                self._expr()
            elif a == "E*":
                while self._expr():
                    pass
            elif a == "A":
                self._addr()
            elif a == "C":
                self._cond()
            elif a.startswith("nE:"):
                for _ in range(int(a[3:])):
                    if not self._expr():
                        break
            elif a.startswith("nV:"):
                for _ in range(int(a[3:])):
                    self._value()

    def _command(self):
        at = self.k
        c = self._b()
        if c == 0:
            name = "00"
        elif c == 1:
            name = "01"
            self._cmd = (at, name)
            self._value()
            self._expr()
        elif c == 2:
            name = "02"
            self._addr()
        elif c in (3, 4):
            name = "%02x" % c
            self._cmd = (at, name)
            self._value()
        elif c == 0x52:
            name = "R"
            self._b()
        else:
            name = bytes([c, self._b()]).decode("latin-1")
            if name not in self.grammar:
                raise ScriptError("a command %r at %x" % (name, at))
            self._cmd = (at, name)
            self._args(self.grammar[name])
        self.cmds.append((at, name))

    def next_command(self, a):
        """The command after the one at `a`."""
        later = [x for x in self.cmds if x[0] > a]
        return min(later) if later else None


def rebuild(sc, new):
    """The script with strings replaced: new {string start: [bytes or ("addr", old address)]} (the 0 after
    the string kept); every address moved with what it points at."""
    d = sc.d
    pieces, shifts, k = [], [], 0
    extra = []                                    # (offset in the output piece, old address)
    for s, e in sorted(sc.strings):
        if s not in new:
            continue
        pieces.append(d[k:s])
        body = bytearray()
        for part in new[s]:
            if isinstance(part, tuple):
                extra.append((s, len(body), part[1]))
                body += b"\0\0"
            else:
                body += part
        pieces.append(bytes(body))
        shifts.append((s, e, len(body) - (e - s)))
        k = e
    pieces.append(d[k:])
    out = bytearray(b"".join(pieces))
    if len(out) > MEMBER:
        raise ScriptError("%d bytes with the English, a script holds %d" % (len(out), MEMBER))

    def moved(a):
        return a + sum(dl for s, e, dl in shifts if e <= a)

    def moved_string(s):
        return s + sum(dl for s2, e, dl in shifts if e <= s)
    for a in sc.addrs:
        v = moved(sc.w(a))
        p = moved(a)
        out[p:p + 2] = bytes([v & 0xFF, v >> 8])
    for s, off, old in extra:
        v = moved(old)
        p = moved_string(s) + off
        out[p:p + 2] = bytes([v & 0xFF, v >> 8])
    return bytes(out)


# ---- text -------------------------------------------------------------------------------------------------

TABLE_SIG = re.compile(rb"\x82\x4f\x82\x50\x82\x51\x82\x52\x82\x53\x2a\x2a\x82\x54")
FILE_RE = re.compile(rb"[0-9A-Za-z_\-]+\.[0-9A-Za-z]{3}\d?")
CODE_RE = re.compile(rb"\\(?:[CW]\d+|[rKk]|[^\x81-\x9f\xe0-\xfc])")


def kana_table(exe):
    """[256 characters (str, "" for none)] the program's single-byte codes stand for."""
    m = list(TABLE_SIG.finditer(exe))
    if len(m) != 1:
        raise ScriptError("UK2.EXE: the characters' table is found %d times" % len(m))
    base = m[0].start() - 0x40
    out = []
    for b in range(256):
        p = exe[base + 2 * b:base + 2 * b + 2]
        try:
            out.append("" if p == b"**" or len(p) < 2 else p.decode("cp932"))
        except UnicodeDecodeError:
            out.append("")
    return out


def is_file(b):
    return FILE_RE.fullmatch(b) is not None


def lead(c):
    return 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC


SPEC = re.compile(rb"%[-+ 0#]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]")     # a C format's place for a value


def show(b, table, specs=False):
    """A string as strings.json shows it: codes as {r} {C7} {W100} {k} {K}, inserts {N1} (a name) and
    {S1} (a word), a new line (\\r) as a new line; with `specs` (a text given to a C format: a page, U2, or
    a format, UC) a value's place (%d, %s..) as itself in either mode."""
    out, k, raw = [], 0, False
    while k < len(b):
        c = b[k]
        m = SPEC.match(b, k) if specs and c == 0x25 else None
        if m:
            out.append(m.group().decode("ascii"))
            k = m.end()
            continue
        if c == BS:
            m = CODE_RE.match(b, k)
            if m:
                code = m.group()[1:].decode("ascii")
                out.append("\n" if code == "r" else "{%s}" % code)
                raw = code == "k" or (raw and code != "K")
                k = m.end()
                continue
        if c in (5, 6) and k + 1 < len(b):
            out.append("{%s%d}" % ("S" if c == 5 else "N", b[k + 1]))
            k += 2
            continue
        if lead(c) and k + 1 < len(b):
            out.append(b[k:k + 2].decode("cp932", "replace"))
            k += 2
            continue
        out.append(chr(c) if raw else (table[c] or chr(c)))
        k += 1
    return "".join(out)


def visible(b):
    return any(not (c in (5, 6) or c < 0x20) for c in CODE_RE.sub(b"", b)) and not is_file(b)


SPEAKER = re.compile(rb"((?:\\C\d)*)(\x81\x6d\x06.\x05\x02)?", re.S)


def speaker(b):
    """(the message's leading codes and speaker (a bracket, a name, the inserted end), the rest)."""
    m = SPEAKER.match(b)
    return b[:m.end()], b[m.end():], m.group(2) is not None


def ascii_text(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "「": '"', "」": '"',
             "『": '"', "』": '"', "【": "[", "】": "]", "［": "[", "］": "]", "（": "(", "）": ")", "　": " ",
             "\\": "/"}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if 0x20 <= ord(c) < 0x7F or c == "\n" else "?" for c in s)


# (a format's %s takes a name in the program's own characters: it goes in \K like an insert)
TOKEN = re.compile(r"\{([NS])(\d+)\}|\{([CW]\d+)\}|(%-?\d*s)|\n|[ ]+|[^ \n{%]+|\{|%")
INSERT_WIDTH = 8            # letters a name or a word put in may take


def tokens(text):
    out = []
    for m in TOKEN.finditer(ascii_text(text)):
        g = m.group()
        if m.group(1):
            out.append(("ins", bytes([5 if m.group(1) == "S" else 6, int(m.group(2))])))
        elif m.group(3):
            out.append(("code", b"\\" + m.group(3).encode("ascii")))
        elif m.group(4):
            out.append(("ins", g.encode("ascii")))
        elif g == "\n":
            out.append(("break", None))
        elif g.isspace():
            out.append(("space", None))
        else:
            out.append(("word", g.encode("ascii")))
    return out


def lines(text, width):
    """[[token]] of English broken between words at `width` letters."""
    out, cur, n = [], [], 0
    for kind, val in tokens(text):
        if kind == "break":
            out.append(cur)
            cur, n = [], 0
            continue
        if kind == "space":
            if cur:
                cur.append(("space", None))
                n += 1
            continue
        w = INSERT_WIDTH if kind == "ins" else len(val) if kind == "word" else 0
        if n + w > width and n:
            while cur and cur[-1][0] == "space":
                cur.pop()
            out.append(cur)
            cur, n = [], 0
        cur.append((kind, val))
        n += w
    while cur and cur[-1][0] == "space":
        cur.pop()
    out.append(cur)
    return out


def encode(line_list):
    """Lines as the program's bytes: ASCII in \\k (bytes as themselves), an insert in \\K (the table's)."""
    out, raw = bytearray(), False
    for n, line in enumerate(line_list):
        if n:
            out += b"\\r"
        for kind, val in line:
            if kind == "ins":
                if raw:
                    out += b"\\K"
                    raw = False
                out += val
            elif kind == "code":
                out += val
            else:
                if not raw:
                    out += b"\\k"
                    raw = True
                out += b" " if kind == "space" else val
    if raw:
        out += b"\\K"
    return bytes(out)
