"""Linear executables (LE: DOS/4GW programs, e.g. EQAP32.EXE: Love Escalator).

`load` reads the objects (each its base address, flags and its bytes, the pages laid end to end and
padded to its size with zeros) and the fixups: (object, offset in it, kind, target object, target
offset), kind 7 a 32-bit offset, 8 a 32-bit relative, 2 a selector, 5 a 16-bit offset, 6 a 16:32
pointer, 3 a 16:16 one.  `address(le, obj, off)` is a place's linear address in the image as loaded at
the objects' bases (the fixups applied: `image`).
"""
import struct


def _hdr(exe):
    at = struct.unpack_from("<I", exe, 0x3C)[0]
    if exe[at:at + 2] != b"LE":
        raise ValueError("not an LE program")
    return at


def load(exe):
    at = _hdr(exe)
    h = lambda o: struct.unpack_from("<I", exe, at + o)[0]
    page_size, last = h(0x28), h(0x2C)
    obj_tab, nobj, page_tab = at + h(0x40), h(0x44), at + h(0x48)
    fix_pages, fix_recs = at + h(0x68), at + h(0x6C)
    data_off, npages = h(0x80), h(0x14)
    pages = []
    for k in range(npages):
        b = exe[page_tab + 4 * k:page_tab + 4 * k + 4]
        num = (b[0] << 16) | (b[1] << 8) | b[2]
        size = last if k == npages - 1 else page_size
        pages.append((data_off + (num - 1) * page_size, size))
    objs = []
    for n in range(nobj):
        vsize, base, flags, first, count, _r = struct.unpack_from("<6I", exe, obj_tab + 24 * n)
        data = bytearray()
        places = []
        for p in range(first - 1, first - 1 + count):
            places.append(pages[p][0])
            data += exe[pages[p][0]:pages[p][0] + pages[p][1]]
            if p != npages - 1:
                data += bytes(page_size - pages[p][1])
        data = data[:max(vsize, len(data))] + bytes(max(0, vsize - len(data)))
        objs.append({"base": base, "flags": flags, "size": vsize, "first": first, "count": count,
                     "data": data, "pages": places})
    fixups = []
    for n, o in enumerate(objs):
        for p in range(o["count"]):
            g = o["first"] - 1 + p
            a, b = struct.unpack_from("<2I", exe, fix_pages + 4 * g)
            i = fix_recs + a
            while i < fix_recs + b:
                src, flags = exe[i], exe[i + 1]
                i += 2
                if src & 0x20:
                    cnt = exe[i]
                    i += 1
                else:
                    offs = [struct.unpack_from("<h", exe, i)[0]]
                    i += 2
                if flags & 3 != 0:
                    raise ValueError("an imported or entry fixup (flags %02X)" % flags)
                if flags & 0x40:
                    tobj = struct.unpack_from("<H", exe, i)[0]
                    i += 2
                else:
                    tobj = exe[i]
                    i += 1
                kind = src & 0x0F
                toff = 0
                if kind != 2:
                    if flags & 0x10:
                        toff = struct.unpack_from("<I", exe, i)[0]
                        i += 4
                    else:
                        toff = struct.unpack_from("<H", exe, i)[0]
                        i += 2
                if src & 0x20:
                    offs = list(struct.unpack_from("<%dh" % cnt, exe, i))
                    i += 2 * cnt
                for s in offs:
                    fixups.append((n, p * page_size + s, kind, tobj - 1, toff))
    return {"objects": objs, "fixups": fixups, "page_size": page_size, "header": at,
            "eip": (h(0x18) - 1, h(0x1C)), "esp": (h(0x20) - 1, h(0x24))}


def image(le):
    """{object: bytes}: each object's bytes with its 32-bit offset fixups applied (as loaded at the
    objects' bases)."""
    objs = le["objects"]
    out = {n: bytearray(o["data"]) for n, o in enumerate(objs)}
    for n, off, kind, tobj, toff in le["fixups"]:
        if not 0 <= off <= len(out[n]) - 4:
            continue
        if kind == 7:
            struct.pack_into("<I", out[n], off, objs[tobj]["base"] + toff)
        elif kind == 8:
            struct.pack_into("<i", out[n], off, objs[tobj]["base"] + toff - (objs[n]["base"] + off + 4))
    return out


def address(le, obj, off):
    return le["objects"][obj]["base"] + off


def poke(exe, le, obj, off, data):
    """Write `data` at `off` in object `obj` of the program's bytes (a bytearray), through its pages."""
    o, size = le["objects"][obj], le["page_size"]
    for k, b in enumerate(data):
        p, q = divmod(off + k, size)
        if p >= len(o["pages"]):
            raise ValueError("past object %d's pages" % obj)
        exe[o["pages"][p] + q] = b


def set_size(exe, le, obj, size):
    """Set object `obj`'s size (within its pages)."""
    if size > le["objects"][obj]["count"] * le["page_size"]:
        raise ValueError("object %d's pages hold %d bytes" % (obj, le["objects"][obj]["count"] * le["page_size"]))
    at = le["header"] + struct.unpack_from("<I", exe, le["header"] + 0x40)[0] + 24 * obj
    struct.pack_into("<I", exe, at, size)
