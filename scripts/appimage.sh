#!/usr/bin/env bash
# Build dist/Bountiful-<version>-x86_64.AppImage: a standalone Python (from uv) with the app's packages and the code
# at HEAD, in one file that runs on any recent x86_64 Linux. LMMS, FluidSynth, Node, PortAudio (and LAME) stay
# system programs; the app's Setup dialog says how to install whichever are missing. Sound packs are downloaded by
# the app, not bundled.
#
#   scripts/appimage.sh            build (uncommitted changes are not included: it packs HEAD)
#
# Needs uv and git; appimagetool is taken from $APPIMAGETOOL, PATH, or downloaded once into build/appimage/tools/.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ID=dev.m4s4t0.bountiful
OUT="$HERE/build/appimage"
APPDIR="$OUT/AppDir"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
cd "$HERE"

TAG="$(git describe --tags --match 'v[0-9]*' 2>/dev/null || true)"
COMMIT="$(git rev-parse --short HEAD)"
VERSION="${TAG#v}"
VERSION="${VERSION:-0.0.0-$COMMIT}"
[ -n "$(git status --porcelain --untracked-files=no)" ] && echo "note: uncommitted changes are not in the build (it packs $COMMIT)"
echo "Bountiful $VERSION"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr" "$HERE/dist"

# Python: uv's standalone builds are relocatable, so the whole install is copied in
"$UV" python install 3.13 >/dev/null
PYEXE="$("$UV" python find --managed-python --no-project 3.13)"
PYROOT="$("$PYEXE" -c 'import sys; print(sys.base_prefix)')"
case "$PYROOT" in */uv/python/*) ;; *) echo "expected a uv-managed Python, got $PYROOT" >&2; exit 1 ;; esac
cp -a "$PYROOT" "$APPDIR/usr/python"
PY="$APPDIR/usr/python/bin/python3"
rm -f "$APPDIR/usr/python/lib/python3.13/EXTERNALLY-MANAGED"
"$UV" pip install --quiet --python "$PY" --break-system-packages -r requirements.txt

# trim what the app never loads
LIB="$APPDIR/usr/python/lib/python3.13"
rm -rf "$LIB"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3} "$LIB"/lib-dynload/_tkinter* \
       "$APPDIR/usr/python/lib"/{libtcl,libtk,tcl,tk,itcl,thread}* "$APPDIR/usr/python/include" "$APPDIR/usr/python/share"
SP="$LIB/site-packages"
PS="$SP/PySide6"
rm -rf "$SP"/pip "$SP"/pip-* "$PS"/{assistant,designer,linguist,lrelease,lupdate,qmlformat,qmllint,qmlls,include,glue,doc,typesystems} \
       "$PS"/Qt/{qml,translations,metatypes,libexec} "$PS"/Qt/plugins/{designer,qmltooling,sqldrivers}
find "$PS" -maxdepth 1 -name '*.pyi' -delete
for m in Qml Quick Designer Help Pdf LabsStyleKit ShaderTools Sql Test UiTools StateMachine Xml Concurrent; do
    rm -f "$PS"/Qt$m*.abi3.so "$PS"/Qt/lib/libQt6$m*.so* "$PS"/libpyside6qml*
done
find "$APPDIR/usr/python" -name __pycache__ -type d -prune -exec rm -rf {} +

# the code, as committed, with its version
mkdir -p "$APPDIR/usr/app"
git archive HEAD | tar -x -C "$APPDIR/usr/app"
rm -rf "$APPDIR/usr/app/tests"
echo "$VERSION $COMMIT $(git log -1 --format=%cs)" > "$APPDIR/usr/app/bountiful/VERSION"
"$PY" -m compileall -q -j0 "$APPDIR/usr/app/bountiful" "$SP" >/dev/null || true

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
exec "$HERE/usr/python/bin/python3" "$HERE/usr/app/bountiful/daw/main.py" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

mkdir -p "$APPDIR/usr/share/icons/hicolor" "$APPDIR/usr/share/applications"
"$PY" scripts/icons.py "$APPDIR/usr/share/icons/hicolor" >/dev/null
cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/$ID.png" "$APPDIR/$ID.png"
ln -sf "$ID.png" "$APPDIR/.DirIcon"
cat > "$APPDIR/usr/share/applications/$ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bountiful
GenericName=Music maker
Comment=Make songs from a Bounty, and play the Electronium
Exec=bountiful %F
Icon=$ID
Terminal=false
Categories=AudioVideo;Audio;Midi;Sequencer;Music;
EOF
cp "$APPDIR/usr/share/applications/$ID.desktop" "$APPDIR/$ID.desktop"

# appimagetool
TOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [ -z "$TOOL" ]; then
    TOOL="$OUT/tools/appimagetool-x86_64.AppImage"
    if [ ! -x "$TOOL" ]; then
        mkdir -p "$OUT/tools"
        curl -fsSL -o "$TOOL.part" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
        chmod 755 "$TOOL.part" && mv "$TOOL.part" "$TOOL"
    fi
fi

IMG="$HERE/dist/Bountiful-$VERSION-x86_64.AppImage"
rm -f "$IMG"
ARCH=x86_64 "$TOOL" --no-appstream "$APPDIR" "$IMG" >"$OUT/appimagetool.log" 2>&1 || { tail -n 20 "$OUT/appimagetool.log"; exit 1; }
(cd "$HERE/dist" && sha256sum "$(basename "$IMG")" > "$(basename "$IMG").sha256")
echo "built $IMG ($(du -h "$IMG" | cut -f1))"
