#!/usr/bin/env python3
"""Friends Bountiful remembers, and how to tag each of them on each platform.

friends.toml (in the project root) holds every friend's handle per platform. For a track or an album,
`share` writes one caption per platform into <folder>/share/<platform>.txt. A friend is @-tagged only
where they have a handle on that platform; elsewhere they're credited by name. Nothing is posted:
the captions are for you to paste.

    $PY bountiful/friends.py list
    $PY bountiful/friends.py add "C-Lizzy" --soundcloud clizzy --instagram c.lizzy [--role composer] [--always]
    $PY bountiful/friends.py remove "Name"
    $PY bountiful/friends.py share tracks/copper-bars [--with "Name, Name"]    (the track remembers who's on it)
    $PY bountiful/friends.py share albums/put-on-the-pixel
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credits import ARTIST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
from paths import DATA  # noqa: E402
FILE = DATA / "friends.toml"

# platform: (how a tag is written or None if it has no tags, profile URL, caption length limit or None)
PLATFORMS = {
    "soundcloud": ("@{h}", "https://soundcloud.com/{h}", None),
    "bandcamp": (None, "https://{h}.bandcamp.com", None),
    "youtube": ("@{h}", "https://www.youtube.com/@{h}", 5000),
    "instagram": ("@{h}", "https://www.instagram.com/{h}", 2200),
    "threads": ("@{h}", "https://www.threads.net/@{h}", 500),
    "tiktok": ("@{h}", "https://www.tiktok.com/@{h}", 2200),
    "x": ("@{h}", "https://x.com/{h}", 280),
    "bluesky": ("@{h}", "https://bsky.app/profile/{h}", 300),
    "mastodon": ("@{h}", None, 500),          # user@instance
    "twitch": ("@{h}", "https://www.twitch.tv/{h}", None),
    "facebook": (None, "https://www.facebook.com/{h}", None),
}
VALID = {"bluesky": r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "mastodon": r"[A-Za-z0-9_]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
         "bandcamp": r"[a-z0-9-]+"}


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def clean(platform: str, h: str) -> str:
    """A handle as stored: no leading @, no profile URL around it; checked against the platform's form."""
    h = h.strip()
    m = re.match(r"https?://(?:www\.)?([^/]+)/@?([^/?#]+)", h)
    if m:
        host, path = m.groups()
        h = host.split(".")[0] if platform == "bandcamp" and host.endswith("bandcamp.com") else path
    h = h.lstrip("@")
    if not re.fullmatch(VALID.get(platform, r"[A-Za-z0-9._-]+"), h):
        raise ValueError(f"{platform}: {h!r} doesn't look like a handle there")
    return h


def load() -> dict[str, dict]:
    return tomllib.loads(FILE.read_text()).get("friends", {}) if FILE.exists() else {}


def _q(s) -> str:
    if isinstance(s, bool):
        return "true" if s else "false"
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save(fr: dict[str, dict]):
    out = ["# Friends Bountiful remembers (bountiful/friends.py): handles per platform, used to tag them in share captions.",
           "# always = true: credited on every release.  Platforms: " + ", ".join(PLATFORMS)]
    for k, f in sorted(fr.items()):
        out += ["", f"[friends.{k}]", f"name = {_q(f['name'])}"]
        out += [f"{a} = {_q(f[a])}" for a in ("role", "always") if a in f]
        out += [f"{p} = {_q(f[p])}" for p in PLATFORMS if f.get(p)]
    FILE.write_text("\n".join(out) + "\n")


def find(fr: dict, name: str) -> str | None:
    k = key(name)
    return k if k in fr else next((x for x, f in fr.items() if f["name"].lower() == name.strip().lower()), None)


def tag(f: dict, platform: str) -> str:
    """'@handle' where the friend is on the platform and it has tags, else their name."""
    fmt = PLATFORMS[platform][0]
    return fmt.format(h=f[platform]) if fmt and f.get(platform) else f["name"]


def link(f: dict, platform: str) -> str | None:
    h = f.get(platform)
    if not h:
        return None
    if platform == "mastodon":
        user, host = h.split("@", 1)
        return f"https://{host}/@{user}"
    return PLATFORMS[platform][1].format(h=h)


# ------------------------------------------------------------------ captions

def release(folder: Path) -> dict:
    """Title, kind and who's on it, from a track folder (instruments.toml / source.json) or an album folder (README.md)."""
    folder = Path(folder)
    info = {"title": folder.name.replace("-", " ").title(), "kind": "track", "with": []}
    if (folder / "instruments.toml").exists():
        meta = tomllib.loads((folder / "instruments.toml").read_text()).get("meta", {})
        info["title"] = meta.get("title", info["title"])
        info["album"] = meta.get("album", "")
        info["genre"] = meta.get("genre", "")
    elif (folder / "README.md").exists():
        first = (folder / "README.md").read_text().splitlines()[0]
        info.update(title=first.lstrip("# ").strip(), kind="album")
    if (folder / "friends.json").exists():
        info["with"] = json.loads((folder / "friends.json").read_text())
    return info


def caption(info: dict, people: list[dict], platform: str) -> str:
    what = "the album" if info["kind"] == "album" else "new track"
    lines = [f"{info['title']} by {ARTIST}" + (f" ({what})" if info["kind"] == "album" else "")]
    if info.get("album"):
        lines[0] += f", from {info['album']}"
    by_role: dict[str, list[str]] = {}
    for f in people:
        by_role.setdefault(f.get("role", "greetz"), []).append(tag(f, platform))
    for role, names in by_role.items():
        label = {"composer": "composed by", "greetz": "greetz to", "feature": "feat.", "mix": "mixed by", "master": "mastered by",
                 "art": "artwork by", "vocals": "vocals by"}.get(role, role)
        lines.append(f"{label} {' & '.join(names)}")
    if not PLATFORMS[platform][0]:                     # no tags here: link the friends who are on this platform
        links = [f"{f['name']}: {link(f, platform)}" for f in people if link(f, platform)]
        if links:
            lines += [""] + links
    if info.get("genre"):
        words = [re.sub(r"[^A-Za-z0-9]", "", w) for w in info["genre"].split()]
        tags = ["#" + w for w in words if w and not w.isdigit()]
        if tags:
            lines += ["", " ".join(tags)]
    return "\n".join(lines)


def share(folder: Path, with_: list[str] | None = None, platforms: list[str] | None = None, log=print) -> dict[str, str]:
    """Write <folder>/share/<platform>.txt for every platform (or the given ones). Returns {platform: caption}.
    Unknown names are remembered as friends without handles, so you can add their handles later."""
    fr = load()
    folder = Path(folder)
    info = release(folder)
    names = list(dict.fromkeys(info["with"] + [n.strip() for n in (with_ or []) if n.strip()]))
    new = [n for n in names if not find(fr, n)]
    for n in new:
        fr[key(n)] = {"name": n}
    if new:
        save(fr)
        log(f"remembered new friend(s) without handles yet: {', '.join(new)} (add them: friends.py add NAME --instagram ...)")
    if with_:
        (folder / "friends.json").write_text(json.dumps(names, indent=1))
    people = [f for f in fr.values() if f.get("always")] + [fr[find(fr, n)] for n in names]
    people = list({f["name"]: f for f in people}.values())
    out = {}
    (folder / "share").mkdir(exist_ok=True)
    for p in platforms or PLATFORMS:
        text = caption(info, people, p)
        out[p] = text
        (folder / "share" / f"{p}.txt").write_text(text + "\n")
        lim = PLATFORMS[p][2]
        tagged = [f["name"] for f in people if PLATFORMS[p][0] and f.get(p)]
        log(f"  {p:10s} {len(text):4d} chars" + (f"  OVER the {lim} limit" if lim and len(text) > lim else "") +
            (f"  tags: {', '.join(tagged)}" if tagged else ""))
    return out


def main():
    ap = argparse.ArgumentParser(description="Friends Bountiful remembers, and their tags per platform.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--role", help="composer, feature, vocals, mix, master, art, greetz ...")
    a.add_argument("--always", action="store_true", help="credit them on every release")
    for p in PLATFORMS:
        a.add_argument(f"--{p}", metavar="HANDLE")
    r = sub.add_parser("remove")
    r.add_argument("name")
    s = sub.add_parser("share")
    s.add_argument("folder", type=Path)
    s.add_argument("--with", dest="with_", default="", help="comma-separated friends on this release")
    s.add_argument("--platforms", default="", help="comma-separated (default: all)")
    args = ap.parse_args()
    fr = load()
    if args.cmd == "list":
        for k, f in sorted(fr.items()):
            on = ", ".join(f"{p} {tag(f, p) if PLATFORMS[p][0] else f[p]}" for p in PLATFORMS if f.get(p)) or "no handles yet"
            print(f"{f['name']:20s} {f.get('role', ''):10s} {'always  ' if f.get('always') else '        '}{on}")
    elif args.cmd == "add":
        k = find(fr, args.name) or key(args.name)
        f = fr.setdefault(k, {"name": args.name})
        if args.role:
            f["role"] = args.role
        if args.always:
            f["always"] = True
        for p in PLATFORMS:
            h = getattr(args, p)
            if h:
                f[p] = clean(p, h)
        save(fr)
        print(f"{f['name']}: " + (", ".join(f"{p} {f[p]}" for p in PLATFORMS if f.get(p)) or "no handles yet"))
    elif args.cmd == "remove":
        k = find(fr, args.name)
        if not k:
            sys.exit(f"no friend called {args.name!r}")
        del fr[k]
        save(fr)
    elif args.cmd == "share":
        share(args.folder, [n for n in args.with_.split(",") if n.strip()], [p for p in args.platforms.split(",") if p.strip()] or None)


if __name__ == "__main__":
    main()
