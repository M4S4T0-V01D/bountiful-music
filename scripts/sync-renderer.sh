#!/usr/bin/env bash
# Copy the renderer Bountiful needs from the intelligent-jungle project into renderer/, so the app runs without it.
#   scripts/sync-renderer.sh [path/to/intelligent-jungle]
# Change the renderer there, then run this and commit renderer/: the diff is the change.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-${BOUNTIFUL_ENGINE:-$HERE/../intelligent-jungle}}"
DST="$HERE/renderer"
[ -f "$SRC/studio/render_midi.py" ] || { echo "no renderer in $SRC" >&2; exit 1; }

rm -rf "$DST.new"
mkdir -p "$DST.new/studio"
for d in engine presets profiles; do cp -r "$SRC/$d" "$DST.new/"; done
find "$DST.new" \( -name __pycache__ -o -name '*.bak*' \) -prune -exec rm -rf {} +
cp "$SRC/studio/render_midi.py" "$SRC/studio/midi_studio.py" "$DST.new/studio/"
cat > "$DST.new/README.md" <<EOF
# renderer

A copy of the renderer from the intelligent-jungle project (\`engine/\`, \`studio/render_midi.py\`, \`studio/midi_studio.py\`,
\`presets/\`, \`profiles/\`), so Bountiful runs on its own. Don't edit it here: change the original and run
\`scripts/sync-renderer.sh\`. paths.py uses this copy unless \`BOUNTIFUL_ENGINE\` or \`engine\` in the config names another.
EOF
rm -rf "$DST"
mv "$DST.new" "$DST"
echo "renderer/ from $SRC: $(find "$DST" -type f | wc -l) files, $(du -sh "$DST" | cut -f1)"
