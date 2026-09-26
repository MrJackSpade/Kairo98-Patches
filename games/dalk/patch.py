"""Apply strings.json to a copy of the Dalk HDI.

    python patch.py "Dalk (v1.08) (uncensored).hdi" "Dalk (English).hdi"
    python patch.py IN.hdi OUT.hdi --pseudo   # stress test with filler text
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.disk import DiskImage  # noqa: E402
from pc98tl.alice_sys2_tl import Sys2Game, sha256  # noqa: E402
import advhack  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = "DALK"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "pseudo" if "--pseudo" in sys.argv else "en"
    src, dst = args
    doc = json.load(open(os.path.join(HERE, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    game = Sys2Game(img.volumes[0], GAME_DIR, config=doc["config"])
    report = game.patch(doc, mode=mode)
    vol = img.volumes[0]
    adv = vol.read(GAME_DIR + "/ADV.COM")
    texts = {int(e["refs"][0][4:], 16): e["en"] for e in doc["strings"] if e["kind"] == "exe" and e["en"]}
    adv, warn = advhack.apply_exe_strings(adv, texts, game.enc.encode)
    report += warn
    vol.write(GAME_DIR + "/ADV.COM", advhack.build(adv))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)


if __name__ == "__main__":
    main()
