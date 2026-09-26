import zipfile, os, sys, json
src = r"C:\PC98"
out = {}
bad = []
for f in sorted(os.listdir(src)):
    if not f.lower().endswith(".zip"): continue
    p = os.path.join(src, f)
    try:
        with zipfile.ZipFile(p) as z:
            out[f] = [(i.filename, i.file_size) for i in z.infolist()]
    except Exception as e:
        bad.append((f, str(e)))
json.dump({"ok": out, "bad": bad}, open("inventory.json","w",encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out), "ok;", len(bad), "unreadable:", [b[0] for b in bad])
