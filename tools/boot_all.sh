#!/bin/sh
# Boot every games/<g>/ filler build (test_<g>.hdi, or test_<g>.hdm/.d88 for
# floppy games with the first extra disk "test_<g> - *" in drive 2) and
# capture screenshots: title/menu, message window after a few inputs, and a
# later scene.  A game can set its own input sequence in game.json
# ("boot_steps", see tools/emu_shot.ps1), e.g. mouse clicks for mouse-driven games.
#   sh tools/boot_all.sh [game ...]
cd "$(dirname "$0")/.." || exit 1
games="$*"; [ -z "$games" ] && games=$(ls games)
default="25:shot,1:enter,4:shot,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot,1:enter,1:enter,1:enter,1:enter,1:enter,1:enter,4:shot"
for g in $games; do
    steps=$(python -c "import json;print(json.load(open('games/$g/game.json',encoding='utf-8')).get('boot_steps','$default'))" 2>/dev/null)
    [ -z "$steps" ] && steps=$default
    if [ -f "test_$g.hdi" ]; then
        set -- -Hdi "test_$g.hdi"
    else
        main=$(ls "test_$g".hdm "test_$g".d88 2>/dev/null | head -1)
        [ -z "$main" ] && continue
        fd2=$(ls "test_$g - "* 2>/dev/null | head -1)
        if [ -n "$fd2" ]; then set -- -Fd1 "$main" -Fd2 "$fd2"; else set -- -Fd1 "$main"; fi
    fi
    dip=$(python -c "import json;print(json.load(open('games/$g/game.json',encoding='utf-8')).get('dipsw',''))" 2>/dev/null)
    [ -n "$dip" ] && set -- "$@" -Dip "$dip"
    rm -f emu/shots/boot_${g}_*.png
    pwsh -NoProfile -File tools/emu_shot.ps1 "$@" -Out "emu/shots/boot_$g" -Steps "$steps" >/dev/null
    shots=$(ls emu/shots/boot_${g}_*.png | sort -V)
    python tools/contact_sheet.py "emu/shots/sheet_$g.png" $(echo "$shots" | wc -l) $shots
    echo "booted $g"
done
