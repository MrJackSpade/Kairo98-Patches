"""Japanese strings hard-coded in a game's engine program (menus, disk
prompts, item names, bonus texts): found, extracted and rewritten in place.

A string is a run of Shift-JIS, ASCII (with printf and %nnn fields) and
half-width kana between non-text bytes, mostly kana and Japanese
punctuation (kanji alone would let code bytes through).  Character tables
that the engine picks characters from by position (the name-entry grids:
rows of kana in groups of five) are not listed: English there would change
what the player types.

Short labels (menu items, names, items) are often kanji or full-width
letters only; those count as strings when they are C strings (a NUL on
each side, full-width characters and spaces only) that sit among other
strings (another within 48 bytes), since code bytes can look like kanji.

The English replaces the run in place, padded with spaces to its length, so
no offset in the program changes; a longer text is cut and reported (the
run's byte length is its limit: two letters per full-width cell).
"""
import re

_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]|[\xa1-\xdf]){4,}")
_CSTR = re.compile(rb"(?<=\x00)(?:[\x81-\x9f][\x40-\x7e\x80-\xfc]|\x20){2,40}(?=\x00)")
_JP = "、。！？・「」『』【】（）ー…〜～"


def _is_grid(text):
    """A character table: ten or more kana or full-width letters and digits,
    no kanji, in three or more groups of up to five split by full-width
    spaces."""
    body = [c for c in text if c not in " 　"]
    groups = [g for g in text.replace(" ", "").split("　") if g]
    table = all("぀" <= c <= "ヿ" or "！" <= c <= "～" or c in "☆★" for c in body)
    return len(body) >= 10 and table and len(groups) >= 3 and all(len(g) <= 5 for g in groups)


def char_at(raw, i):
    """(character, byte length) at raw[i]: Shift-JIS, ASCII, half-width
    kana, and the PC-98's own half-width letters 0x85 0x40-0x9e (row 9:
    ASCII 0x21-0x7e drawn from two bytes) and space 0x86 0x40 as the
    ASCII they show; None for anything else."""
    b = raw[i]
    if raw[i:i + 2] == b"\x86\x40":
        return " ", 2                   # (its half-width space)
    if b == 0x85 and i + 1 < len(raw) and 0x40 <= raw[i + 1] <= 0x9E and raw[i + 1] != 0x7F:
        t = raw[i + 1]
        return chr(0x21 + (t - 0x40 if t < 0x7F else t - 0x41)), 2
    if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
        try:
            return raw[i:i + 2].decode("cp932"), 2
        except UnicodeDecodeError:
            return None, 2
    try:
        return raw[i:i + 1].decode("cp932"), 1
    except UnicodeDecodeError:
        return None, 1


def decode(raw):
    """raw as text (see char_at), or None where a character is not one."""
    out, i = [], 0
    while i < len(raw):
        ch, n = char_at(raw, i)
        if ch is None or i + n > len(raw):
            return None
        out.append(ch)
        i += n
    return "".join(out)


def _mostly_japanese(text):
    k = sum(1 for c in text if "぀" <= c <= "ヿ" or c in _JP)
    return k >= 4 and k / len(text) > 0.4


def find(exe):
    """[(start, end, text)] of the Japanese strings in the program."""
    out = []
    for m in _RUN.finditer(exe):
        raw = m.group()
        # keep whole characters: a run may start on a trail byte of the previous one
        text = decode(raw)
        if text is None:
            continue
        s, e = m.start(), m.end()
        # trim ASCII noise at the ends (code bytes that happen to be printable; one byte each,
        # where a PC-98 half-width letter, two bytes, is text)
        while text and text[0] in " \t" + "".join(chr(c) for c in range(0x21, 0x7f)) and not text.startswith("%") \
                and exe[s] < 0x80:
            s += 1
            text = text[1:]
        while text and ord(text[-1]) < 0x80 and text[-1] not in "%sd0123456789 " and exe[e - 1] < 0x80 \
                and not (e >= 2 and exe[e - 2] == 0x85):
            e -= 1
            text = text[:-1]
        if not text or not _mostly_japanese(text) or _is_grid(text):
            continue
        out.append((s, e, text))
    kana = [(s, e) for s, e, _t in out]
    labels = []
    for m in _CSTR.finditer(exe):
        s, e = m.start(), m.end()
        if any(a <= s < b for a, b in kana):
            continue
        text = decode(m.group())
        if text is None:
            continue
        body = text.replace(" ", "").replace("\u3000", "")
        if len(body) < 2 or len(set(body)) == 1 or _is_grid(text):
            continue
        labels.append((s, e, text))
    spans = kana + [(s, e) for s, e, _t in labels]
    for s, e, text in labels:
        if any((a, b) != (s, e) and (abs(a - e) <= 48 or abs(s - b) <= 48) for a, b in spans):
            out.append((s, e, text))
    return sorted(out)


def apply(exe, runs, values):
    """Write the English (bytes, keyed by start offset) over the runs, padded
    with spaces; returns (program, [(start, needed, room)] for cut texts)."""
    exe = bytearray(exe)
    cut = []
    for s, e, _t in runs:
        v = values.get(s)
        if v is None:
            continue
        if len(v) > e - s:
            cut.append((s, len(v), e - s))
            v = v[:e - s]
        exe[s:e] = v.ljust(e - s, b" ")
    return bytes(exe), cut


# ---- batch files: the Japanese echo lines -------------------------------------------------
def batch_lines(data):
    """[(line number, text)] of the echo lines of a batch file that show
    Japanese (any kana or kanji)."""
    out = []
    for n, line in enumerate(data.decode("cp932", "replace").split("\r\n")):
        m = re.match(r"(?i)\s*echo[ .](.*)$", line)
        if m and re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", m.group(1)):
            out.append((n, m.group(1)))
    return out


def apply_batch(data, values):
    """Put the English (text, keyed by line number) into the echo lines."""
    lines = data.decode("cp932", "replace").split("\r\n")
    for n, text in values.items():
        m = re.match(r"(?i)(\s*echo[ .])", lines[n])
        lines[n] = m.group(1) + text
    return "\r\n".join(lines).encode("cp932", "replace")
