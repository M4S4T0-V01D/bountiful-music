#!/usr/bin/env bash
# Install Bountiful for this user: the app (a git clone, so it can update itself), its own Python, the launcher,
# the start-menu entry and the icons. Your music stays where it is (config: ~/.config/bountiful/config.toml).
#
#   scripts/install.sh              install, or reinstall, from this repository
#   scripts/install.sh --refresh    dependencies, launcher, menu entry, icons (the updater runs this after a pull)
#   scripts/install.sh --uninstall  remove the app, launcher, menu entry and icons (not your music, not the config)
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
ROOT="${BOUNTIFUL_HOME:-$HOME/.local/lib/bountiful}"
APP="$ROOT/app"
VENV="$ROOT/venv"
BIN="$HOME/.local/bin"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
ID="dev.m4s4t0.bountiful"
UV="$(command -v uv || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
mode="${1:-install}"

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

menu_refresh() {
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$SHARE/applications" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$SHARE/icons/hicolor" 2>/dev/null || true
    command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
}

case "$mode" in
--uninstall)
    say "removing Bountiful (your music and config stay)"
    rm -f "$BIN/bountiful" "$SHARE/applications/$ID.desktop"
    find "$SHARE/icons/hicolor" -name "$ID.*" -delete 2>/dev/null || true
    rm -rf "$ROOT"
    menu_refresh
    exit 0
    ;;
install)
    command -v git >/dev/null || { echo "git is needed"; exit 1; }
    mkdir -p "$ROOT"
    if [ -d "$APP/.git" ]; then
        say "updating the app in $APP"
        git -C "$APP" remote set-url origin "$HERE"
        git -C "$APP" pull --ff-only --quiet
    else
        say "installing the app into $APP (updates come from $HERE)"
        git clone --quiet "$HERE" "$APP"
    fi
    BOUNTIFUL_SOURCE="$HERE" exec bash "$APP/scripts/install.sh" --refresh
    ;;
--refresh) ;;
*) echo "usage: $0 [--refresh|--uninstall]"; exit 2 ;;
esac

# ---- --refresh: everything but the code
cd "$HERE"
if [ ! -x "$VENV/bin/python" ]; then
    say "making Bountiful's own Python in $VENV"
    if [ -n "$UV" ]; then
        "$UV" venv -q -p 3.13 "$VENV"
    else
        python3 -m venv "$VENV"
    fi
fi
say "installing its dependencies"
if [ -n "$UV" ]; then
    "$UV" pip install -q -p "$VENV/bin/python" -r "$HERE/requirements.txt"
else
    "$VENV/bin/python" -m pip install -q -r "$HERE/requirements.txt"
fi

say "launcher: $BIN/bountiful"
mkdir -p "$BIN"
cat > "$BIN/bountiful" <<EOF
#!/usr/bin/env bash
# Bountiful (installed by $HERE/scripts/install.sh)
exec "$VENV/bin/python" "$HERE/bountiful/daw/main.py" "\$@"
EOF
chmod +x "$BIN/bountiful"

say "icons"
"$VENV/bin/python" "$HERE/scripts/icons.py" "$SHARE/icons/hicolor" >/dev/null

say "start-menu entry"
mkdir -p "$SHARE/applications"
cat > "$SHARE/applications/$ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bountiful
GenericName=Music Workstation
Comment=Songs from a Bounty: the Electronium live, arrange, edit, mix and render
Exec=$BIN/bountiful %F
Icon=$ID
Terminal=false
StartupNotify=true
Categories=AudioVideo;Audio;Midi;Sequencer;Music;
Keywords=music;daw;electronium;midi;compose;synth;bounty;
EOF

if [ -n "${BOUNTIFUL_SOURCE:-}" ]; then
    "$VENV/bin/python" - "$BOUNTIFUL_SOURCE" "$HERE" <<'EOF'
import sys
from pathlib import Path
src, app = sys.argv[1], sys.argv[2]
sys.path.insert(0, str(Path(app) / "bountiful"))
import paths
c = paths.config()
changes = {}
if not c.get("data") and (Path(src) / "tracks").exists():
    changes["data"] = src
if not c.get("engine") and (paths.ENGINE / "studio" / "render_midi.py").exists():
    changes["engine"] = str(paths.ENGINE)
if changes:
    paths.save_config(**changes)
    print("config:", ", ".join(f"{k} = {v}" for k, v in changes.items()))
EOF
fi

menu_refresh
say "done: Bountiful is in your start menu (Multimedia), or run: bountiful"
