"""Illusion (tmexec engine) message files: plain Shift-JIS text records.

    #00151<CR><LF>
    text, possibly several lines separated by CR LF$<CR><LF>

The engine finds a message by its number, so records can grow freely.  The
file may have blank lines between records and ends with ^Z (1A).  parse()
keeps every byte outside the message texts (numbers, separators, blank lines,
the EOF mark) so rebuild() with unchanged texts reproduces the file exactly.
"""
import re

RECORD = re.compile(rb"#(\d{5})\r\n(.*?)\$", re.S)


def is_message_file(data):
    return bool(RECORD.search(data)) and data.count(b"$") >= 1


def parse(data):
    """[(number, text bytes, start, end)] with start/end the text's span."""
    return [(int(m.group(1)), m.group(2), m.start(2), m.end(2)) for m in RECORD.finditer(data)]


def rebuild(data, texts):
    """texts: {number: new text bytes}.  Unlisted records keep their bytes."""
    out, pos = bytearray(), 0
    for num, text, s, e in parse(data):
        out += data[pos:s]
        out += texts.get(num, text)
        pos = e
    out += data[pos:]
    return bytes(out)
