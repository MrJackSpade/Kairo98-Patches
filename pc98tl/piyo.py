"""MicroCabin's PIYO engine (Maison Ikkoku - Omoide no Photograph: PIYO.EXE
running the compiled script PIYO.LDY, its messages in PIYO.LBC).

PIYO.LBC: the messages, one after another, each ended by a 0 byte.  A
message's bytes are coded by the byte before them in the message (the
first by 0): a byte is the text's byte rotated left by the previous text
byte's low three bits (`decode`, `encode`).  The text is Shift-JIS, 0Ah a
new line.  PIYO.EXE keeps the file in memory as one segment, so it may
take 65535 bytes.

PIYO.LDY: a header of 12 words, then tables whose sizes the header gives
(PIYO.EXE's loader), the strings, the procedures' names and the script's
code.  Read here:
* header[6] words at 18h + 2 * (header[11] + header[5]): each message's
  place in PIYO.LBC;
* header[0] words, the commands' strings (the menu: 部屋を出る, 話す ...),
  and after them header[1] words, the things' and people's names (財布,
  管理人さん ...): each the string's place in PIYO.LDY, the strings ended
  by a 0.  The script names a string by its number, so a string may be put
  anywhere in the file (`build` puts a changed one at the end; the file
  is read into one segment, 65535 bytes).
* a few strings inside the script's code (`inline`): written in place,
  their bytes the room.
"""
import re
import struct

HEADER = 12
SEGMENT = 0xFFFF


def decode(data, pos):
    """(text, end) of the message at `pos` in PIYO.LBC."""
    out, prev = bytearray(), 0
    while data[pos]:
        c, s = data[pos], prev & 7
        o = ((c >> s) | (c << (8 - s))) & 0xFF
        out.append(o)
        prev = o
        pos += 1
    return bytes(out), pos + 1


def encode(text):
    """The message's bytes (with its ending 0) for `text` (no 0 byte in it)."""
    out, prev = bytearray(), 0
    for o in text:
        if not o:
            raise ValueError("PIYO: a message cannot hold a 0 byte")
        s = prev & 7
        out.append(((o << s) | (o >> (8 - s))) & 0xFF)
        prev = o
    return bytes(out) + b"\0"


def layout(ldy):
    """{name: (place, count)} of the tables in PIYO.LDY."""
    h = struct.unpack_from("<%dH" % HEADER, ldy, 0)
    pos = 2 * HEADER
    a = pos + 2 * h[11]                     # (two tables PIYO.EXE reads first)
    msgs = a + 2 * h[5]
    pos = msgs + 2 * h[6]
    pos += 2 * h[7]
    pos += 2 * h[3] * h[8] + 2 * h[4] * h[9] + 2 * h[5] * h[10] + 2 * h[3] + 2 * h[4]
    menu = pos
    names = menu + 2 * h[0]
    strings = names + 2 * h[1]
    return {"messages": (msgs, h[6]), "menu": (menu, h[0]), "names": (names, h[1]), "strings": strings}


def table(ldy, name):
    place, count = layout(ldy)[name]
    return list(struct.unpack_from("<%dH" % count, ldy, place))


def messages(ldy, lbc):
    """[text] of the messages, by number."""
    return [decode(lbc, p)[0] for p in table(ldy, "messages")]


def strings(ldy, name):
    """[(place, text)] of the menu's or the names' strings, by number."""
    return [(p, ldy[p:ldy.index(b"\0", p)]) for p in table(ldy, name)]


INLINE = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){2,}")


def code_start(ldy):
    """Where the script's code begins: after the strings and the procedures'
    names (ASCII, each ended by a 0)."""
    end = max(ldy.index(b"\0", p) for name in ("menu", "names") for p in table(ldy, name)) + 1
    while True:
        m = re.match(rb"[\x20-\x7e]+\x00", ldy[end:])
        if not m:
            return end
        end += m.end()


def inline(ldy):
    """[(start, end)] of the Japanese strings inside the script's code: from
    the first Shift-JIS character to the 0 ending the string (a 0Ah before
    it kept out)."""
    out = []
    for m in INLINE.finditer(ldy, code_start(ldy)):
        s = m.start()
        if out and s < out[-1][1]:
            continue
        e = ldy.index(b"\0", s)
        while e > s and ldy[e - 1] == 0x0A:
            e -= 1
        out.append((s, e))
    return out


def build_lbc(texts):
    """PIYO.LBC from [text] and [place] of each message (identical texts
    share their place)."""
    out, places, seen = bytearray(), [], {}
    for t in texts:
        if t not in seen:
            seen[t] = len(out)
            out += encode(t)
        places.append(seen[t])
    if len(out) > SEGMENT:
        raise ValueError("PIYO.LBC: %d bytes, the segment holds %d" % (len(out), SEGMENT))
    return bytes(out), places


def build_ldy(ldy, places, new_strings, inline_texts):
    """PIYO.LDY with the messages' places, the changed strings ({(table,
    number): text}, put at the file's end) and the inline strings ({start:
    bytes}, the same length) written."""
    out = bytearray(ldy)
    lay = layout(ldy)
    struct.pack_into("<%dH" % len(places), out, lay["messages"][0], *places)
    for start, text in inline_texts.items():
        out[start:start + len(text)] = text
    for (name, k), text in sorted(new_strings.items()):
        place = len(out)
        out += text + b"\0"
        struct.pack_into("<H", out, lay[name][0] + 2 * k, place)
    if len(out) > SEGMENT:
        raise ValueError("PIYO.LDY: %d bytes, the segment holds %d" % (len(out), SEGMENT))
    return bytes(out)
