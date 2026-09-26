"""Japanese strings hard-coded in an Alice Soft ADV.COM.

The engine's string drawer stops at the first byte below 0x80 that isn't a
space, so a string can be replaced in place with anything up to its original
length, padded with its original terminator byte.

find_strings() locates player-visible strings: runs of Shift-JIS characters
that contain kana, full-width Latin letters or brackets, end in a terminator
the drawer honours (00 or 1B), and aren't the name-entry character grid.  A
game can adjust the result with "exe_add" / "exe_skip" (addresses) in game.json.
"""
import re

ORG = 0x100
RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|\x20){3,}(?=[\x00\x1b])")
RUN_KANA = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|[\x20\xa1-\xdf]){3,}(?=[\x00\x1b])")
KANA = re.compile("[ぁ-ヿＡ-Ｚａ-ｚ【】]")
# rows of the name-entry character grid (the cells' positions matter; not text)
GRID = re.compile("ＡＢＣ|ＨＩＪ|ＯＰＱ|ＶＷＸ|ａｂｃ|ｈｉｊ|ｏｐｑ|ｖｗｘ|０１２３|あかさたな|アカサタナ|"
                  "ゝゞ〃|〔〕|▲◆●|▽□☆|【削除】")


def _chars(raw):
    """Split a run into characters (1 or 2 bytes each)."""
    out, i = [], 0
    while i < len(raw):
        n = 2 if (0x81 <= raw[i] <= 0x9F or 0xE0 <= raw[i] <= 0xEA) else 1
        out.append(raw[i:i + n])
        i += n
    return out


def decode(raw, kana=None):
    """Text as displayed: with `kana` (the program's 64-entry A0-DF table),
    half-width kana bytes show as the table's full-width characters."""
    if not kana:
        return raw.decode("cp932")
    return "".join(kana[c[0] - 0xA0] if len(c) == 1 and 0xA0 <= c[0] <= 0xDF else c.decode("cp932")
                   for c in _chars(raw))


def widen(raw, kana_words):
    """Untranslated text for a program whose kana table was remapped to
    English: half-width kana bytes become their full-width codes."""
    return b"".join(kana_words[c[0] - 0xA0] if len(c) == 1 and 0xA1 <= c[0] <= 0xDF else c
                    for c in _chars(raw))


def find_strings(adv, add=(), skip=(), kana=None):
    """kana: the program's A0-DF table when its drawer converts half-width
    kana (System 3).  Runs may then also mix kana bytes with Shift-JIS, as in
    the opening demos' narration.  Such a run is taken only if it starts with
    a 2-byte character, holds at least two, uses only common (JIS level 1)
    codes and includes full-width punctuation or kana (leads 81-83), since
    code and data bytes easily look like kana plus kanji;
    it replaces the plain matches inside it.  A weaker run (any start, one
    2-byte char or three kana bytes) is also taken when it sits right next to
    an accepted string, since narration is stored as one block of strings."""
    found = [(m.start(), m.group()) for m in RUN.finditer(adv)]
    if kana:
        strong, weak = [], []
        for m in RUN_KANA.finditer(adv):
            cs = _chars(m.group())
            two = [c for c in cs if len(c) == 2]
            nkana = sum(1 for c in cs if len(c) == 1 and c != b" ")
            if not nkana or any(c[0] > 0x9F for c in two):
                continue
            if len(cs[0]) == 2 and len(two) >= 2 and any(c[0] <= 0x83 for c in two):
                strong.append((m.start(), m.group()))
            elif two or nkana >= 3:
                weak.append((m.start(), m.group()))
        # a lone byte just before a plain string is code (e.g. a ret), not text
        plain = {a for a, r in found}
        weak = [(a, r) for a, r in weak if not (r[0] >= 0xA0 and a + 1 in plain)]
        edges = {a for a, r in found} | {a + len(r) + 1 for a, r in found}
        edges |= {a for a, r in strong} | {a + len(r) + 1 for a, r in strong}
        grew = True
        while grew:
            grew = False
            for a, r in list(weak):
                if a in edges or a + len(r) + 1 in edges:
                    strong.append((a, r))
                    weak.remove((a, r))
                    edges |= {a, a + len(r) + 1}
                    grew = True
        for s, raw in strong:
            e = s + len(raw)
            found = [(a, r) for a, r in found if not (s <= a < e)] + [(s, raw)]
    out = []
    for start, raw in sorted(found):
        if raw.startswith(b" "):
            continue
        try:
            text = decode(raw, kana)
        except UnicodeDecodeError:
            continue
        addr = ORG + start
        if addr in skip:
            continue
        core = text.replace("　", "").replace(" ", "").strip("【】")
        if not core or GRID.search(text):
            continue
        if not KANA.search(text) and addr not in add:
            continue
        out.append({"addr": addr, "max_bytes": len(raw), "jp": text})
    for a in add:
        if not any(s["addr"] == a for s in out):
            o = a - ORG
            end = o
            while end < len(adv) and (adv[end] >= 0x80 or adv[end] == 0x20):
                end += 2 if (0x81 <= adv[end] <= 0x9F or 0xE0 <= adv[end] <= 0xEA) else 1
            out.append({"addr": a, "max_bytes": end - o, "jp": adv[o:end].decode("cp932", "replace")})
    return sorted(out, key=lambda s: s["addr"])


def _cut(enc, n):
    """Longest prefix of enc that fits in n bytes, on a character boundary."""
    cut = 0
    while cut < len(enc):
        step = 2 if (0x80 <= enc[cut] <= 0x9F or enc[cut] >= 0xE0) else 1
        if cut + step > n:
            break
        cut += step
    return enc[:cut]


def _groups(adv, sizes):
    """Runs of strings stored back to back (each right after the previous
    one's terminator) where only the first is addressed from code: programs
    walk such a run string by string (the demos' narration), so the run is
    rewritten as a unit.  A string whose address appears in the file starts
    its own run, so it keeps its address."""
    groups = []
    for addr in sorted(sizes):
        prev = groups[-1][-1] if groups else None
        if (prev is not None and prev + sizes[prev] + 1 == addr
                and adv.count(addr.to_bytes(2, "little")) == 0):
            groups[-1].append(addr)
        else:
            groups.append([addr])
    return groups


def _mov_refs(src, addr):
    """Offsets of "mov r16, addr" immediates (B8-BF) in the program."""
    w = addr.to_bytes(2, "little")
    return [i + 1 for i in range(len(src) - 2) if 0xB8 <= src[i] <= 0xBF and src[i + 1:i + 3] == w]


def apply_strings(adv, texts, encode, sizes, label="ADV.COM", keep=None, spill=None):
    """texts: {address: english}; sizes: {address: max_bytes} for every string
    found (translated or not).  Each run of consecutive strings (see _groups)
    is repacked in its own bytes: strings keep their order and terminators,
    and the space left after the last terminator is filled with the byte that
    followed the run (an end marker, if the program walks the run) or, when
    that byte is text, the terminator.  `keep` rewrites untranslated strings
    in a run being repacked (see widen).

    spill = (address, limit): free memory after the end of the program.  A run
    that doesn't fit and is loaded by "mov reg, address" is written there in
    full, as one stream with the runs the program walks on into (up to the
    next run with its own load, control bytes copied as they are), and those
    loads are pointed at the copy; the run is still repacked in place
    (truncated) for any other reference.  Returns (bytes, warnings), with the
    spilled streams appended to the bytes."""
    src = bytes(adv)
    adv = bytearray(adv)
    warn = []
    groups = _groups(src, sizes)
    cursor = spill[0] if spill else None
    extra = bytearray()

    def text_of(a):
        o = a - ORG
        orig = src[o:o + sizes[a]]
        return encode(texts[a]) if a in texts else (keep(orig) if keep else orig)

    def stream(gi):
        """Bytes of the stream starting at groups[gi], rewritten in full."""
        out, j = bytearray(), gi
        while True:
            g = groups[j]
            for a in g:
                o = a - ORG
                out += text_of(a) + src[o + sizes[a]:o + sizes[a] + 1]
            end = g[-1] - ORG + sizes[g[-1]] + 1
            nxt = groups[j + 1] if j + 1 < len(groups) else None
            if nxt is None or nxt[0] - ORG - end > 64 or _mov_refs(src, nxt[0]):
                return bytes(out + src[end:end + 1]), j
            out += src[end:nxt[0] - ORG]          # control bytes between runs
            j += 1

    covered = set()                               # runs whose full text was spilled
    for gi, group in enumerate(groups):
        if not any(a in texts for a in group) and (
                keep is None or all(keep(src[a - ORG:a - ORG + sizes[a]]) == src[a - ORG:a - ORG + sizes[a]]
                                    for a in group)):
            continue
        start = group[0] - ORG
        end = group[-1] - ORG + sizes[group[-1]] + 1      # past the last terminator
        room = end - start - len(group)                    # bytes for text
        parts = []
        for a in group:
            o = a - ORG
            orig = src[o:o + sizes[a]]
            parts.append([encode(texts[a]) if a in texts else (keep(orig) if keep else orig), src[o + sizes[a]]])
        need = sum(len(p) for p, _t in parts)
        refs = _mov_refs(src, group[0]) if need > room and spill else []
        if refs:
            data, last = stream(gi)
            if cursor + len(data) <= spill[1]:
                for r in refs:
                    adv[r:r + 2] = cursor.to_bytes(2, "little")
                extra += data
                cursor += len(data)
                covered.update(range(gi, last + 1))
        if need > room:
            if gi not in covered:
                warn.append("%s strings %04x-%04x: %d bytes, only %d fit (truncated)"
                            % (label, group[0], group[-1], need, room))
            while sum(len(p) for p, _t in parts) > room:   # trim the longest first
                longest = max(parts, key=lambda pt: len(pt[0]))
                longest[0] = _cut(longest[0], len(longest[0]) - 1)
        block = b"".join(p + bytes([t]) for p, t in parts)
        after = src[end] if end < len(src) else 0
        fill = after if after < 0x80 and after != 0x20 else parts[-1][1]
        adv[start:end] = block.ljust(end - start, bytes([fill]))
    if extra:
        adv += b"\0" * (spill[0] - ORG - len(adv)) + extra
    return bytes(adv), warn
