"""Build the Windows installer or the macOS disk image: a standalone Python (from uv) with the app's packages and the
code at HEAD, like scripts/appimage.sh does for Linux, and FluidSynth's library for the SoundFont voices (on Windows
from the official build whose fluidsynth.exe is on PATH, on macOS Homebrew's, relinked by dylibbundler). LMMS stays a
separate, optional program. Sound packs are downloaded by the app, not bundled.

  python scripts/bundle.py            build dist/Bountiful-<version>-windows-x86_64-setup.exe  (on Windows)
                                      or    dist/Bountiful-<version>-macos-<arch>.dmg          (on macOS)
  python scripts/bundle.py --dir      only lay out build/bundle/ (no installer or image)

Needs uv and git; on Windows also Inno Setup 6 (ISCC.exe on PATH or in Program Files), on macOS iconutil, hdiutil and
dylibbundler (brew install fluidsynth dylibbundler).
The bundle in build/bundle/ can be tried before packaging:  <bundle python> <bundle app>/bountiful/daw/main.py --smoke
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ID = "dev.m4s4t0.bountiful"
REPO = "M4S4T0-V01D/bountiful-music"
OUT = HERE / "build" / "bundle"
DIST = HERE / "dist"
WINDOWS, MACOS = sys.platform == "win32", sys.platform == "darwin"
ARCH = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
# Qt modules the app never loads (the same list as the AppImage's)
QT_UNUSED = ("Qml", "Quick", "Designer", "Help", "Pdf", "LabsStyleKit", "ShaderTools", "Sql", "Test", "UiTools",
             "StateMachine", "Xml", "Concurrent")


def run(*cmd, **kw) -> str:
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw).stdout.strip()


def git_version() -> tuple[str, str, str]:
    commit = run("git", "rev-parse", "--short", "HEAD", cwd=HERE)
    try:
        tag = run("git", "describe", "--tags", "--match", "v[0-9]*", cwd=HERE)
    except subprocess.CalledProcessError:
        tag = ""
    if run("git", "status", "--porcelain", "--untracked-files=no", cwd=HERE):
        print(f"note: uncommitted changes are not in the build (it packs {commit})")
    return tag[1:] if tag else f"0.0.0-{commit}", commit, run("git", "log", "-1", "--format=%cs", cwd=HERE)


def layout() -> dict:
    """Where the Python, the code and the icon go inside the bundle."""
    if MACOS:
        root = OUT / "Bountiful.app"
        res = root / "Contents" / "Resources"
        return {"root": root, "python": res / "python", "app": res / "app", "icon": res / "bountiful.icns",
                "exe": res / "python" / "bin" / "python3", "lib": res / "python" / "lib" / "python3.13"}
    root = OUT / "Bountiful"
    py = root / "python"
    lib = py / "Lib" if WINDOWS else py / "lib" / "python3.13"
    return {"root": root, "python": py, "app": root / "app", "icon": root / "bountiful.ico",
            "exe": py / ("python.exe" if WINDOWS else "bin/python3"), "lib": lib}


def copy_python(L: dict):
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    run(uv, "python", "install", "3.13")
    found = run(uv, "python", "find", "--managed-python", "--no-project", "3.13")
    root = Path(run(found, "-c", "import sys; print(sys.base_prefix)"))
    if "uv" not in root.parts or "python" not in root.parts:
        sys.exit(f"expected a uv-managed Python, got {root}")
    shutil.copytree(root, L["python"], symlinks=True)
    (L["lib"] / "EXTERNALLY-MANAGED").unlink(missing_ok=True)
    run(uv, "pip", "install", "--quiet", "--python", L["exe"], "--break-system-packages", "-r", HERE / "requirements.txt")


def rm(*paths: Path):
    for p in paths:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        elif p.exists() or p.is_symlink():
            p.unlink()


def prune(L: dict):
    lib = L["lib"]
    # (tkinter stays: the MIDI Studio is a Tk app, and the core uses its TOML writer)
    rm(*(lib / d for d in ("test", "idlelib", "turtledemo", "ensurepip", "lib2to3")),
       L["python"] / "include", L["python"] / "share")
    sp = lib / "site-packages"
    rm(sp / "pip", *sp.glob("pip-*"))
    ps = sp / "PySide6"
    qt = ps / "Qt" if (ps / "Qt").is_dir() else ps   # Windows wheels keep Qt's files next to the bindings
    rm(*(ps / d for d in ("include", "glue", "doc", "typesystems", "scripts")),
       *(qt / d for d in ("qml", "translations", "metatypes", "libexec")),
       *(qt / "plugins" / d for d in ("designer", "qmltooling", "sqldrivers")), *ps.glob("*.pyi"))
    for tool in ("assistant", "designer", "linguist", "lrelease", "lupdate", "qmlformat", "qmllint", "qmlls"):
        rm(ps / tool, ps / f"{tool}.exe", *ps.glob(f"{tool.capitalize()}*.app"))
    for m in QT_UNUSED:
        rm(*ps.glob(f"Qt{m}*.pyd"), *ps.glob(f"Qt{m}*.abi3.so"), *ps.glob("pyside6qml*"),
           *qt.glob(f"Qt6{m}*.dll"), *(qt / "lib").glob(f"Qt{m}*.framework"))
    for d in list(L["python"].rglob("__pycache__")):
        rm(d)


def add_code(L: dict, version: str, commit: str, date: str):
    tar = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=HERE, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(L["app"], filter="data")
    rm(L["app"] / "tests")
    (L["app"] / "bountiful" / "VERSION").write_text(f"{version} {commit} {date}\n")
    # (a few files in the packages are templates that don't compile; that's fine)
    subprocess.run([str(L["exe"]), "-m", "compileall", "-q", "-j0", str(L["app"] / "bountiful"),
                    str(L["lib"] / "site-packages")], capture_output=True)


def add_fluidsynth(L: dict):
    """FluidSynth (LGPL-2.1-or-later, unmodified) in a fluidsynth/ folder, where engine.share.find_libfluidsynth looks
    first, with its licence and where its source is"""
    exe = shutil.which("fluidsynth")
    if WINDOWS:
        dest = L["root"] / "fluidsynth" / "bin"
        src = Path(exe).parent if exe else None
        if not src or not (src / "libfluidsynth-3.dll").is_file():
            print("note: no FluidSynth build on PATH; SoundFont voices will need LMMS or a FluidSynth install")
            return
        dest.mkdir(parents=True)
        for dll in src.glob("*.dll"):
            shutil.copy(dll, dest)
        roots = [src.parent, src.parent.parent]
    elif MACOS:
        lib = next((p for p in (Path("/opt/homebrew/lib/libfluidsynth.3.dylib"), Path("/usr/local/lib/libfluidsynth.3.dylib"))
                    if p.is_file()), None)
        if not lib or not shutil.which("dylibbundler"):
            print("note: Homebrew's fluidsynth or dylibbundler is missing; SoundFont voices will need a FluidSynth install")
            return
        dest = L["app"].parent / "fluidsynth" / "lib"
        dest.mkdir(parents=True)
        shutil.copy(lib.resolve(), dest / lib.name)
        (dest / lib.name).chmod(0o755)
        run("dylibbundler", "-of", "-b", "-x", dest / lib.name, "-d", dest, "-p", "@loader_path/")
        for d in dest.glob("*.dylib"):
            run("codesign", "--force", "--sign", "-", d)
        roots = [Path(run("brew", "--prefix", "fluidsynth"))]
    else:
        return
    top = dest.parent
    lic = next((f for r in roots for n in ("LICENSE", "COPYING", "LICENSE.txt", "COPYING.txt") for f in [r / n] if f.is_file()), None)
    if lic:
        shutil.copy(lic, top / "LICENSE.txt")
    elif shutil.which("gh"):
        (top / "LICENSE.txt").write_text(run("gh", "api", "-H", "Accept: application/vnd.github.raw",
                                             "repos/FluidSynth/fluidsynth/contents/LICENSE"), encoding="utf-8")
    try:
        version = run(exe, "--version").splitlines()[0]
    except (subprocess.CalledProcessError, OSError, IndexError, TypeError):
        version = "FluidSynth"
    (top / "README.txt").write_text(f"{version}\nhttps://www.fluidsynth.org - LGPL-2.1-or-later (LICENSE.txt), unmodified.\n"
                                    "Source: https://github.com/FluidSynth/fluidsynth\n", encoding="utf-8")
    print(f"bundled {version} ({sum(f.stat().st_size for f in dest.iterdir()) / 2**20:.0f} MB)")


def render_icons(L: dict, sizes) -> Path:
    d = OUT / "icons"
    rm(d)
    run(L["exe"], HERE / "scripts" / "icons.py", d, "--sizes", ",".join(map(str, sizes)),
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    return d


def png(icons: Path, n: int) -> bytes:
    return (icons / f"{n}x{n}" / "apps" / f"{ID}.png").read_bytes()


def write_ico(icons: Path, out: Path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    images = [png(icons, n) for n in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = len(head) + 16 * len(images)
    entries = b""
    for n, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(head + entries + b"".join(images))


def windows(L: dict, version: str):
    icons = render_icons(L, (16, 24, 32, 48, 64, 128, 256))
    write_ico(icons, L["icon"])
    shutil.copy(HERE / "LICENSE", L["root"] / "LICENSE.txt")
    iscc = shutil.which("iscc") or next((str(p) for p in (
        Path(os.environ.get(v, "")) / "Inno Setup 6" / "ISCC.exe"
        for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")) if p.is_file()), None)
    if not iscc:
        sys.exit("Inno Setup 6 is needed for the installer (winget install JRSoftware.InnoSetup, or choco install innosetup)")
    name = f"Bountiful-{version}-windows-{ARCH}-setup"
    launch = r'Filename: "{app}\python\pythonw.exe"; Parameters: "-E -s ""{app}\app\bountiful\daw\main.py"""'
    iss = OUT / "bountiful.iss"
    iss.write_text(f"""\
[Setup]
AppId={ID}
AppName=Bountiful
AppVersion={version}
AppPublisher=M4S4T0-V01D
AppPublisherURL=https://github.com/{REPO}
AppUpdatesURL=https://github.com/{REPO}/releases
DefaultDirName={{autopf}}\\Bountiful
DefaultGroupName=Bountiful
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={L["root"] / "LICENSE.txt"}
SetupIconFile={L["icon"]}
UninstallDisplayIcon={{app}}\\bountiful.ico
OutputDir={DIST}
OutputBaseFilename={name}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: desktopicon; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[InstallDelete]
; an update replaces the code and the Python whole, so files a new version dropped don't linger
Type: filesandordirs; Name: "{{app}}\\app"
Type: filesandordirs; Name: "{{app}}\\python"

[Files]
Source: "{L["root"]}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}\\app"
Type: filesandordirs; Name: "{{app}}\\python"

[Icons]
Name: "{{autoprograms}}\\Bountiful"; {launch}; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\bountiful.ico"; AppUserModelID: "{ID}"
Name: "{{autodesktop}}\\Bountiful"; {launch}; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\bountiful.ico"; AppUserModelID: "{ID}"; Tasks: desktopicon

[Run]
{launch}; Description: "{{cm:LaunchProgram,Bountiful}}"; Flags: nowait postinstall skipifsilent
""", encoding="utf-8")
    run(iscc, "/Q", iss)
    return DIST / f"{name}.exe"


def macos(L: dict, version: str, commit: str):
    contents = L["root"] / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    launcher = contents / "MacOS" / "Bountiful"
    # apps opened from Finder get a bare PATH; Homebrew's is where LMMS and its helpers live
    launcher.write_text("""#!/bin/sh
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec "$RES/python/bin/python3" "$RES/app/bountiful/daw/main.py" "$@"
""")
    launcher.chmod(0o755)
    short = version.split("-")[0]
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleName": "Bountiful", "CFBundleDisplayName": "Bountiful", "CFBundleIdentifier": ID,
                       "CFBundleExecutable": "Bountiful", "CFBundleIconFile": "bountiful", "CFBundlePackageType": "APPL",
                       "CFBundleShortVersionString": short, "CFBundleVersion": f"{short}.{int(commit, 16) % 65536}",
                       "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
                       "LSApplicationCategoryType": "public.app-category.music"}, f)
    icons = render_icons(L, (16, 32, 64, 128, 256, 512, 1024))
    iconset = OUT / "bountiful.iconset"
    rm(iconset)
    iconset.mkdir()
    for n in (16, 32, 128, 256, 512):
        (iconset / f"icon_{n}x{n}.png").write_bytes(png(icons, n))
        (iconset / f"icon_{n}x{n}@2x.png").write_bytes(png(icons, n * 2))
    run("iconutil", "-c", "icns", "-o", L["icon"], iconset)
    stage = OUT / "dmg"
    rm(stage)
    stage.mkdir()
    shutil.move(str(L["root"]), stage / "Bountiful.app")
    (stage / "Applications").symlink_to("/Applications")
    dmg = DIST / f"Bountiful-{version}-macos-{ARCH}.dmg"
    rm(dmg)
    run("hdiutil", "create", "-volname", "Bountiful", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    shutil.move(str(stage / "Bountiful.app"), L["root"])
    return dmg


def main() -> int:
    only_dir = "--dir" in sys.argv[1:]
    version, commit, date = git_version()
    print(f"Bountiful {version}")
    L = layout()
    rm(L["root"])
    L["root"].mkdir(parents=True)
    DIST.mkdir(exist_ok=True)
    copy_python(L)
    prune(L)
    add_code(L, version, commit, date)
    add_fluidsynth(L)
    if only_dir:
        print(f"bundle in {L['root']}\n  python {L['exe']}\n  app    {L['app']}")
        return 0
    if WINDOWS:
        out = windows(L, version)
    elif MACOS:
        out = macos(L, version, commit)
    else:
        sys.exit("on Linux, scripts/appimage.sh builds the AppImage (--dir lays out a bundle here for testing)")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    Path(f"{out}.sha256").write_text(f"{digest}  {out.name}\n")
    print(f"built {out} ({out.stat().st_size / 2**20:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
