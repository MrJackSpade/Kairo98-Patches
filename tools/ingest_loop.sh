#!/bin/sh
# Keep ingesting E:\PC98 while archives are still arriving:
# scan new zips -> extract + verify + delete -> rebuild index, every 10 minutes,
# until no publisher zips remain (or 12 hours pass).
#   sh tools/ingest_loop.sh [root]
cd "$(dirname "$0")/.." || exit 1
ROOT="${1:-E:\\PC98}"
export PYTHONIOENCODING=utf-8
end=$(( $(date +%s) + 12 * 3600 ))
while [ "$(date +%s)" -lt "$end" ]; do
    echo "=== $(date '+%H:%M:%S') pass"
    python -u tools/scan_collection.py "$ROOT" | grep -v "^ *skipped .*modified in the last"
    python -u tools/extract_collection.py --root "$ROOT"
    python tools/build_index.py
    left=$(ls "$ROOT"/*.zip 2>/dev/null | wc -l)
    echo "=== zips remaining: $left"
    [ "$left" -eq 0 ] && { echo "=== all archives ingested"; exit 0; }
    sleep 600
done
echo "=== stopped after 12 hours; zips remaining: $(ls "$ROOT"/*.zip 2>/dev/null | wc -l)"
