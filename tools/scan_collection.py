"""Deep scan of C:\\PC98: every disk image, its content hash, and the files inside it.

    python tools/scan_collection.py [C:\\PC98]

Resumable: results are cached per publisher archive (keyed by name, size and
mtime) in index/scan/<archive>.json, so re-running only processes archives
that are new or changed.  Archives that can't be opened yet (still copying)
are skipped and reported.

Content IDs match Kairo98: "sha256-hdi-v1:" / "sha256-fd-v1:" + SHA-256 of the
extracted image bytes.
"""
import hashlib
import io
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pc98tl.disk import DiskImage  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "index", "scan")
HDD = (".hdi", ".nhd", ".thd", ".hdd")
CD = (".iso", ".bin", ".cue", ".ccd", ".img.ccd", ".mds", ".mdf", ".chd", ".toc", ".sub", ".wav")
FDD = (".hdm", ".fdi", ".d88", ".88d", ".d98", ".98d", ".nfd", ".fdd", ".dcp", ".dcu", ".xdf", ".tfd", ".img")
MAX_LIST = 4000  # files listed per image


def list_image(data):
    try:
        img = DiskImage(data)
    except Exception as e:  # noqa: BLE001 - any parse failure is just "not listable"
        return None, "parse error: %s" % e
    if not img.volumes:
        return None, "no FAT volume (raw, copy-protected or non-DOS disk)"
    files = []
    for vi, vol in enumerate(img.volumes):
        try:
            for path, ent in vol.walk():
                if not path.endswith("/"):
                    files.append([path if vi == 0 else "%d:%s" % (vi, path), ent["size"]])
                if len(files) >= MAX_LIST:
                    break
        except Exception as e:  # noqa: BLE001
            return files, "walk error: %s" % e
    return files, None


def scan_inner(zbytes, inner_name):
    images = []
    try:
        z = zipfile.ZipFile(io.BytesIO(zbytes))
    except zipfile.BadZipFile as e:
        return [{"inner": inner_name, "error": "bad zip: %s" % e}]
    for info in z.infolist():
        low = info.filename.lower()
        kind = "hdi" if low.endswith(HDD) else "fd" if low.endswith(FDD) else None
        if low.endswith(".img") and info.file_size > 4 << 20:
            kind = None  # CD image (with .ccd/.cue), not a floppy
        if info.is_dir():
            continue
        if not kind:
            # CD tracks and everything else: name, size and CRC only (no full read)
            images.append({"inner": inner_name, "image": info.filename, "size": info.file_size,
                           "crc32": "%08x" % info.CRC, "kind": "cd" if low.endswith(CD) else "other"})
            continue
        data = z.read(info)
        rec = {"inner": inner_name, "image": info.filename, "size": len(data), "kind": kind,
               "content_id": "sha256-%s-v1:%s" % (kind, hashlib.sha256(data).hexdigest())}
        # FAT listing works on HDI and raw 2HD (hdm); other floppy formats are hashed only
        if low.endswith((".hdi", ".hdm", ".img")):
            files, err = list_image(data)
            rec["files"] = files
            if err:
                rec["list_error"] = err
        images.append(rec)
    return images


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else r"C:\PC98"
    os.makedirs(OUT, exist_ok=True)
    skipped, done, cached = [], 0, 0
    for name in sorted(os.listdir(src)):
        if not name.lower().endswith(".zip"):
            continue
        path = os.path.join(src, name)
        st = os.stat(path)
        stamp = {"size": st.st_size, "mtime": int(st.st_mtime)}
        out = os.path.join(OUT, name + ".json")
        if os.path.exists(out):
            prev = json.load(open(out, encoding="utf-8"))
            if prev.get("stamp") == stamp and not prev.get("partial"):
                cached += 1
                continue
        if time.time() - st.st_mtime < 120:
            skipped.append((name, "modified in the last 2 minutes (still copying?)"))
            continue
        try:
            outer = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            skipped.append((name, str(e)))
            continue
        t0 = time.time()
        images, errors = [], []
        for info in outer.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".zip"):
                continue
            try:
                images += scan_inner(outer.read(info), info.filename)
            except Exception as e:  # noqa: BLE001 - record and keep going
                errors.append([info.filename, str(e)])
        json.dump({"archive": name, "stamp": stamp, "images": images, "errors": errors},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False)
        done += 1
        print("%-40s %5d images %6.1fs%s" % (name, len(images), time.time() - t0,
              "  (%d errors)" % len(errors) if errors else ""), flush=True)
    print("scanned %d, cached %d, skipped %d" % (done, cached, len(skipped)))
    for n, why in skipped:
        print("  skipped %s: %s" % (n, why))


if __name__ == "__main__":
    main()
