"""Tile screenshots into one image:  python tools/contact_sheet.py OUT.png COLS img1 img2 ..."""
import sys
from PIL import Image, ImageDraw

out, cols, paths = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
ims = [Image.open(p).convert("RGB") for p in paths]
w, h = 330, 235
rows = (len(ims) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * (h + 14)), "white")
d = ImageDraw.Draw(sheet)
for i, (im, p) in enumerate(zip(ims, paths)):
    x, y = (i % cols) * w, (i // cols) * (h + 14)
    sheet.paste(im.resize((w, h)), (x, y + 14))
    d.text((x + 3, y + 1), p.replace("\\", "/").split("/")[-1], fill="black")
sheet.save(out)
