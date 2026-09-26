#!/bin/sh
# Boot every games/<g>/ filler build (test_<g>.hdi) and capture screenshots:
# title/menu, message window after a few key presses, and a later scene.
#   sh tools/boot_all.sh [game ...]
cd "$(dirname "$0")/.." || exit 1
games="$*"; [ -z "$games" ] && games=$(ls games)
steps="25:shot,1:enter,4:shot,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot"
for g in $games; do
    [ -f "test_$g.hdi" ] || continue
    pwsh -NoProfile -File tools/emu_shot.ps1 -Hdi "test_$g.hdi" -Out "emu/shots/boot_$g" -Steps "$steps" >/dev/null
    python tools/contact_sheet.py "emu/shots/sheet_$g.png" 5 emu/shots/boot_${g}_1.png emu/shots/boot_${g}_2.png emu/shots/boot_${g}_3.png emu/shots/boot_${g}_4.png emu/shots/boot_${g}_5.png
    echo "booted $g"
done
