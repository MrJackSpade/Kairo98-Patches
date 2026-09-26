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
KANA = re.compile("[ぁ-ヿＡ-Ｚａ-ｚ【】]")
# rows of the name-entry character grid (the cells' positions matter; not text)
GRID = re.compile("ＡＢＣ|ＨＩＪ|ＯＰＱ|ＶＷＸ|ａｂｃ|ｈｉｊ|ｏｐｑ|ｖｗｘ|０１２３|あかさたな|アカサタナ|"
                  "ゝゞ〃|〔〕|▲◆●|▽□☆|【削除】")


def find_strings(adv, add=(), skip=()):
    out = []
    for m in RUN.finditer(adv):
        raw = m.group()
        if raw.startswith(b" "):
            continue
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        addr = ORG + m.start()
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


def apply_strings(adv, texts, encode, sizes):
    """texts: {address: english}; sizes: {address: max_bytes}.  Returns (bytes, warnings)."""
    adv = bytearray(adv)
    warn = []
    for addr, text in texts.items():
        n = sizes[addr]
        enc = encode(text)
        if len(enc) > n:
            warn.append("ADV.COM string %04x: %d bytes, only %d fit (truncated)" % (addr, len(enc), n))
            cut = 0
            while cut < len(enc):  # cut on a character boundary
                step = 2 if (0x80 <= enc[cut] <= 0x9F or enc[cut] >= 0xE0) else 1
                if cut + step > n:
                    break
                cut += step
            enc = enc[:cut]
        o = addr - ORG
        term = adv[o + n]
        adv[o:o + n] = enc.ljust(n, bytes([term]))
    return bytes(adv), warn
