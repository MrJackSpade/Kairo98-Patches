"""Unpack E:\\PC98\\<Publisher>.zip into one folder per game, verify, delete the zip.

    python tools/extract_collection.py [--root E:\\PC98] [--keep-zips] [--only X.zip]

Layout:   <root>\\<Game>\\<Variant>\\<files>     e.g. Dalk\\Dalk [HD]\\Dalk (v1.08) (uncensored).hdi
Catalog:  index/catalog/<Publisher>.zip.json   one record per extracted file with
          title, publisher, variant, relative path, size, content_id (disk images)
          or crc32 (everything else).

A publisher zip is processed only when its deep scan (tools/scan_collection.py)
is current, so every disk image has a known content hash to verify against.
Every written file is re-read and checked (SHA-256 for images, CRC-32 for the
rest).  Only when all files of a publisher zip verify is the zip deleted.
Re-running skips finished archives and files that already verify.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
import zlib
import io

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCAN = os.path.join(ROOT_DIR, "index", "scan")
CATALOG = os.path.join(ROOT_DIR, "index", "catalog")
FOLDERS = os.path.join(ROOT_DIR, "index", "folders.json")
HOMEBREW = "doujinHomebrew.zip"
MIN_FREE = 8 << 30  # stop if extracting would leave less than 8 GB free
HDD = (".hdi", ".nhd", ".thd", ".hdd")
FDD = (".hdm", ".fdi", ".d88", ".88d", ".d98", ".98d", ".nfd", ".fdd", ".dcp", ".dcu", ".xdf", ".tfd", ".img")


def safe(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return name or "_"


def long_path(p):
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def game_of(zname, inner):
    """(publisher, title, variant) for an inner zip path 'Publisher/Title/Variant.zip'."""
    parts = inner.split("/")
    publisher, title = parts[0], parts[1]
    variant = parts[-1][:-4] if parts[-1].lower().endswith(".zip") else parts[-1]
    if zname == HOMEBREW:  # "<Creator>/<Creator> (<Game>) [FD].zip"
        m = re.match(re.escape(parts[1]) + r" \((.+)\)((?: \[[^\]]*\])+)\.zip$", parts[-1])
        if m:
            publisher, title = parts[1], m.group(1)
            variant = title + m.group(2)
    if len(parts) > 3:  # deeper nesting ([Utility] set): keep the extra levels in the variant
        variant = "/".join(safe(x) for x in parts[2:-1] + [variant])
    return publisher, title, variant


def file_hash(path, image):
    h = hashlib.sha256() if image else None
    crc = 0
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            if image:
                h.update(chunk)
            else:
                crc = zlib.crc32(chunk, crc)
    return h.hexdigest() if image else "%08x" % crc


def main():
    lock = os.path.join(ROOT_DIR, "index", "extract.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit("another extract_collection.py is running (delete %s if it isn't)" % lock)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        run()
    finally:
        os.remove(lock)


def run():
    args = sys.argv[1:]
    root = args[args.index("--root") + 1] if "--root" in args else r"E:\PC98"
    only = args[args.index("--only") + 1] if "--only" in args else None
    keep = "--keep-zips" in args
    os.makedirs(CATALOG, exist_ok=True)
    folders = json.load(open(FOLDERS, encoding="utf-8")) if os.path.exists(FOLDERS) else {}
    used = {v.lower(): k for k, v in folders.items()}

    def folder_for(zname, publisher, title):
        key = "%s/%s" % (zname, title)
        if key not in folders:
            name = safe(title)
            if name.lower() in used and used[name.lower()] != key:
                name = safe("%s (%s)" % (title, publisher))
            n = 2
            base = name
            while name.lower() in used and used[name.lower()] != key:
                name, n = "%s %d" % (base, n), n + 1
            folders[key] = name
            used[name.lower()] = key
        return folders[key]

    totals = {"archives": 0, "deleted": 0, "files": 0, "bytes": 0, "problems": []}
    for zname in sorted(os.listdir(root)):
        if not zname.lower().endswith(".zip") or (only and zname != only):
            continue
        zpath = os.path.join(root, zname)
        st = os.stat(zpath)
        scan_path = os.path.join(SCAN, zname + ".json")
        if not os.path.exists(scan_path):
            continue
        scan = json.load(open(scan_path, encoding="utf-8"))
        if scan["stamp"] != {"size": st.st_size, "mtime": int(st.st_mtime)} or scan.get("errors"):
            totals["problems"].append((zname, "scan stale or had errors; rescan first"))
            continue
        need = sum(i.get("size", 0) for i in scan["images"])
        free = shutil.disk_usage(root).free
        if free - need < MIN_FREE:
            totals["problems"].append((zname, "needs %.1f GB, only %.1f GB free" % (need / 2**30, free / 2**30)))
            print("stopping: not enough free space for", zname, flush=True)
            break
        expect = {(i["inner"], i["image"]): i for i in scan["images"]}
        t0 = time.time()
        records, bad = [], []
        with zipfile.ZipFile(zpath) as outer:
            for info in outer.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".zip"):
                    continue
                publisher, title, variant = game_of(zname, info.filename)
                dest = os.path.join(root, folder_for(zname, publisher, title), *variant.split("/"))
                inner = zipfile.ZipFile(io.BytesIO(outer.read(info)))
                for ie in inner.infolist():
                    if ie.is_dir():
                        continue
                    rel = [safe(x) for x in ie.filename.split("/")]
                    out = os.path.join(dest, *rel)
                    low = ie.filename.lower()
                    # .img is also a CD image format; floppies are never over a few MB
                    image = low.endswith(HDD + FDD) and not (low.endswith(".img") and ie.file_size > 4 << 20)
                    exp = expect.get((info.filename, ie.filename))
                    if image and (not exp or "content_id" not in exp):
                        bad.append((out, "no scan hash"))
                        continue
                    want = exp["content_id"].split(":", 1)[1] if image else "%08x" % ie.CRC
                    if not (os.path.exists(long_path(out)) and os.path.getsize(long_path(out)) == ie.file_size
                            and file_hash(out, image) == want):
                        os.makedirs(long_path(os.path.dirname(out)), exist_ok=True)
                        with inner.open(ie) as src, open(long_path(out), "wb") as dst:
                            shutil.copyfileobj(src, dst, 1 << 20)
                        if file_hash(out, image) != want:
                            bad.append((out, "hash mismatch after write"))
                            continue
                    rec = {"title": title, "publisher": publisher, "variant": variant,
                           "path": os.path.relpath(out, root), "size": ie.file_size}
                    if image:
                        rec["content_id"] = exp["content_id"]
                        if exp.get("files") is not None:
                            rec["files"] = exp["files"]
                    else:
                        rec["crc32"] = want
                    records.append(rec)
        json.dump({"archive": zname, "records": records, "problems": bad},
                  open(os.path.join(CATALOG, zname + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(folders, open(FOLDERS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        totals["archives"] += 1
        totals["files"] += len(records)
        totals["bytes"] += sum(r["size"] for r in records)
        if bad:
            totals["problems"].append((zname, "%d files failed verification; zip kept" % len(bad)))
            status = "KEPT (%d problems)" % len(bad)
        elif keep:
            status = "verified, kept"
        else:
            os.remove(zpath)
            totals["deleted"] += 1
            status = "verified, zip deleted"
        print("%-40s %6d files %8.1f MB %6.1fs  %s" % (zname, len(records), sum(r["size"] for r in records) / 2**20,
              time.time() - t0, status), flush=True)
    print("done: %(archives)d archives, %(files)d files, %(bytes)d bytes, %(deleted)d zips deleted" % totals)
    for z, why in totals["problems"]:
        print("  problem %s: %s" % (z, why))


if __name__ == "__main__":
    main()
