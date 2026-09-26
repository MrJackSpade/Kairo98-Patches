#!/bin/sh
# Boot every games/<g>/ filler build (test_<g>.hdi, or test_<g>.hdm for floppy
# games with the first scenario floppy "test_<g> - *.hdm" in drive 2) and
# capture screenshots: title/menu, message window after a few key presses,
# and a later scene.
#   sh tools/boot_all.sh [game ...]
cd "$(dirname "$0")/.." || exit 1
games="$*"; [ -z "$games" ] && games=$(ls games)
steps="25:shot,1:enter,4:shot,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot"
for g in $games; do
    if [ -f "test_$g.hdi" ]; then
        set -- -Hdi "test_$g.hdi"
    elif [ -f "test_$g.hdm" ]; then
        fd2=$(ls "test_$g - "*.hdm 2>/dev/null | head -1)
        if [ -n "$fd2" ]; then set -- -Fd1 "test_$g.hdm" -Fd2 "$fd2"; else set -- -Fd1 "test_$g.hdm"; fi
    else
        continue
    fi
    pwsh -NoProfile -File tools/emu_shot.ps1 "$@" -Out "emu/shots/boot_$g" -Steps "$steps" >/dev/null
    python tools/contact_sheet.py "emu/shots/sheet_$g.png" 5 emu/shots/boot_${g}_1.png emu/shots/boot_${g}_2.png emu/shots/boot_${g}_3.png emu/shots/boot_${g}_4.png emu/shots/boot_${g}_5.png
    echo "booted $g"
done
