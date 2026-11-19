"""LMMS as a sound engine: any part can be played by an LMMS instrument (ZynAddSubFX presets, the
stock .xpf presets for Organic / Vibed / Kicker / Xpressive / Monstro / ..., or a built-in plugin such
as Mallets STK with its settings). The engine writes the notes into an LMMS project, LMMS renders each
track headless (`lmms rendertracks`), and the audio comes back as a stem for the normal mix chain.

Voice spec in song.toml:
    [voices.pad]
    backend = "lmms"
    zyn = "Strings/0024-Dark Strings.xiz"          # a ZynAddSubFX preset (relative to its bank folder)
    # or: xpf = "Organic/organ_risingsun.xpf"     # any LMMS instrument preset
    # or: plugin = "malletsstk"  attrs = { preset = 13 }   # a plugin with explicit settings
    vol = 100                                      # LMMS track volume
    transpose = 0                                  # semitones, if a patch sits in the wrong octave
"""
from __future__ import annotations

import gzip
import re
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np
import soundfile as sf

from .share import PRESETS, SAMPLES, lmms_bin
ZYN = PRESETS / "ZynAddSubFX"
TEMPLATE = Path(__file__).resolve().parent / "data" / "zyn_master_template.xml"
TPB = 48   # LMMS ticks per beat
CATALOG = Path(__file__).resolve().parent / "data" / "lmms_catalog.json"
SHORT = {"calf": "http://calf.sourceforge.net/plugins/", "lsp": "http://lsp-plug.in/plugins/lv2/"}
_cat = None


def catalog() -> dict:
    global _cat
    if _cat is None:
        import json
        _cat = json.loads(CATALOG.read_text())
    return _cat


def lv2_uri(name: str) -> str:
    """'calf:Reverb' / 'lsp:room_builder_stereo' / full URI -> URI"""
    if "://" in name:
        return name
    pre, _, local = name.partition(":")
    return SHORT[pre] + local


def lv2_preset(uri: str, preset: str) -> dict:
    for p in catalog()["lv2_presets"]:
        if p["plugin"] == uri and p["name"].replace(" ", "").lower() == preset.replace(" ", "").lower():
            return dict(p["values"])
    raise KeyError(f"no LV2 preset '{preset}' for {uri}")


def _models(values: dict) -> str:
    return "<models " + " ".join(f'{k}="{v}"' for k, v in values.items()) + "/>"


def effect_xml(e: dict) -> str:
    """One LMMS effect from a spec:
    {builtin="reverbsc", wet=0.3} | {ladspa="tap_tubewarmth" or "file:label", controls={"Drive": 4}} |
    {lv2="calf:TapeSimulator", preset="...", controls={"level_in": 1.2}}   (wet 0..1, default 1)"""
    head = f'<effect name="{{}}" on="1" wet="{e.get("wet", 1.0)}" gate="0" autoquit="1" autoquit_numerator="4" autoquit_denominator="4" autoquit_syncmode="0">'
    if "builtin" in e:
        return head.format(e["builtin"]) + "<key/></effect>"
    if "ladspa" in e:
        file, _, label = e["ladspa"].partition(":")
        label = label or file
        plug = next((p for p in catalog()["effects"]["ladspa"] if p["label"] == label and (p["file"] == file or file == label)), None)
        if plug is None:
            raise KeyError(f"LADSPA plugin not found: {e['ladspa']}")
        ctl = ""
        if e.get("controls"):
            chans = 2 if plug["audio_in"] == 1 else 1     # LMMS runs mono plugins twice for stereo
            vals = {c["index"]: e["controls"].get(c["name"]) for c in plug["controls"]}
            ports = "".join(f'<port{ch}{i} data="{v}" link="1"/>' for ch in range(chans) for i, v in vals.items() if v is not None)
            ctl = f'<ladspacontrols ports="{chans * len(plug["controls"])}" link="1">{ports}</ladspacontrols>'
        return (head.format("ladspaeffect") + ctl +
                f'<key><attribute name="file" value="{plug["file"]}"/><attribute name="plugin" value="{label}"/></key></effect>')
    if "lv2" in e:
        uri = lv2_uri(e["lv2"])
        vals = lv2_preset(uri, e["preset"]) if e.get("preset") else {}
        vals.update(e.get("controls", {}))
        ctl = f"<lv2controls>{_models(vals)}</lv2controls>" if vals else ""
        return head.format("lv2effect") + ctl + f'<key><attribute name="uri" value="{uri}"/></key></effect>'
    raise ValueError(f"effect spec needs builtin, ladspa or lv2: {e}")


def fx_chain(effects: list[dict]) -> str:
    if not effects:
        return ""
    return f'<fxchain numofeffects="{len(effects)}" enabled="1">' + "".join(effect_xml(e) for e in effects) + "</fxchain>"


def _find(base: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute() and p.exists():
        return p
    if not base.is_dir():
        raise FileNotFoundError(f"LMMS preset {rel}: {base} doesn't exist; install LMMS or set LMMS_SHARE")
    if (base / rel).exists():
        return base / rel
    hits = list(base.rglob(Path(rel).name))
    if not hits:   # tolerate missing/wrong number prefixes: "Rhodes/FM Rhodes 3" finds "Rhodes/0015-FM Rhodes 3.xiz"
        strip = lambda n: re.sub(r"^\d+-", "", Path(n).stem).strip().lower()
        want, folder = strip(rel), Path(rel).parent.name.lower()
        hits = [f for f in base.rglob("*.*") if strip(f.name) == want and (not folder or f.parent.name.lower() == folder)]
    if not hits:
        raise FileNotFoundError(f"LMMS preset not found: {rel}")
    return hits[0]


def instrument_xml(v: dict) -> str:
    """The <instrumenttrack> element for a voice spec (with its LMMS effect chain, `fx`)."""
    it = _instrument_xml(v)
    chain = fx_chain(v.get("fx", []))
    if chain:
        if "<fxchain" in it:      # a preset's own effects stay; ours are appended after them
            m = re.search(r'<fxchain numofeffects="(\d+)"[^>]*?(/?)>', it)
            if m.group(2):
                it = it[:m.start()] + chain + it[m.end():]
            else:
                inner = chain[chain.index(">") + 1:chain.rindex("</fxchain>")]
                n = int(m.group(1)) + len(v["fx"])
                end = it.index("</fxchain>", m.end())
                it = it[:m.start()] + f'<fxchain numofeffects="{n}" enabled="1">' + it[m.end():end] + inner + it[end:]
        else:
            it = it[:it.rindex("</instrumenttrack>")] + chain + "</instrumenttrack>"
    return it


def sample_root(path: Path) -> int:
    """MIDI pitch of a one-shot instrument sample (autocorrelation on its steady part)."""
    import soundfile as sf
    x, sr = sf.read(str(path), always_2d=True)
    m = x.mean(1)
    seg = m[int(0.05 * sr): int(0.05 * sr) + int(0.5 * sr)]
    seg = seg - seg.mean()
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo, hi = int(sr / 2000), int(sr / 40)
    hz = sr / (lo + int(np.argmax(ac[lo:hi])))
    return int(round(69 + 12 * np.log2(hz / 440)))


def _instrument_xml(v: dict) -> str:
    vol = v.get("vol", 100)
    head = f'<instrumenttrack vol="{vol}" pan="0" basenote="{57 - v.get("transpose", 0)}" pitch="0" pitchrange="1" mixch="0" usemasterpitch="1">'
    if "zyn" in v:
        raw = _find(ZYN, v["zyn"]).read_bytes()
        inst = (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf8", "replace")   # .xiz: gzip or plain XML
        body = inst[inst.index("<INSTRUMENT>"):inst.index("</INSTRUMENT>") + len("</INSTRUMENT>")]
        tmpl = TEMPLATE.read_text()
        a, b = tmpl.index("<INSTRUMENT>"), tmpl.index("</INSTRUMENT>") + len("</INSTRUMENT>")
        return head + tmpl[:a] + body + tmpl[b:] + "</instrumenttrack>"
    if "xpf" in v:
        x = _find(PRESETS, v["xpf"]).read_text()
        a = re.search(r"<instrumenttrack[\s>]", x).start()
        b = x.index("</instrumenttrack>") + len("</instrumenttrack>")
        it = x[a:b]
        it = re.sub(r'(<instrumenttrack[^>]*?)\bvol="[^"]*"', rf'\1vol="{vol}"', it, count=1)
        if v.get("transpose"):
            it = re.sub(r'(<instrumenttrack[^>]*?)\bbasenote="[^"]*"', rf'\1basenote="{57 - v["transpose"]}"', it, count=1)
        return it
    if "sample" in v:   # a recorded one-shot played chromatically by AudioFileProcessor (a 90s sampler, basically)
        path = _find(SAMPLES, v["sample"])
        root = v.get("root") or sample_root(path)
        a = {"src": str(path), "reversed": 0, "looped": v.get("looped", 0), "sframe": v.get("start", 0), "eframe": v.get("end", 1),
             "amp": v.get("amp", 100), "stutter": 0, "interp": 2}
        attrs = " ".join(f'{k}="{val}"' for k, val in a.items())
        head = head.replace(f'basenote="{57 - v.get("transpose", 0)}"', f'basenote="{root - 12 - v.get("transpose", 0)}"')
        env = ""
        if v.get("release"):   # a soft release instead of the sample cutting off at note-off
            env = (f'<eldata fcut="14000" fwet="0" ftype="0" fres="0.5"><elvol att="0" hold="0" dec="0" sustain="1" rel="{v["release"]}" amt="1" '
                   'pdel="0" lpdel="0" lspd="0.1" lamt="0" x100="0" ctlenvamt="0" lshp="0" userwavefile=""/></eldata>')
        return head + f'<instrument name="audiofileprocessor"><audiofileprocessor {attrs}/></instrument>{env}</instrumenttrack>'
    if "lv2" in v:   # an LV2 instrument (Calf Organ / Monosynth / Wavetable ...) with an optional factory preset
        uri = lv2_uri(v["lv2"])
        pname = v.get("lv2preset") or (v.get("preset") if v.get("preset") and not str(v["preset"]).endswith(".json") else None)
        vals = lv2_preset(uri, pname) if pname else {}
        vals.update(v.get("controls", {}))
        return (head + f'<instrument name="lv2instrument"><lv2instrument>{_models(vals) if vals else ""}</lv2instrument>'
                f'<key><attribute name="uri" value="{uri}"/></key></instrument></instrumenttrack>')
    if "plugin" in v:
        name = v["plugin"]
        attrs = " ".join(f'{k}="{val}"' for k, val in v.get("attrs", {}).items())
        return head + f'<instrument name="{name}"><{name} {attrs}/></instrument></instrumenttrack>'
    raise ValueError(f"LMMS voice needs zyn, xpf or plugin: {v}")


def note_xml(notes: list[tuple[int, int, int, int]]) -> str:
    """notes: (tick, length_ticks, lmms_key, vol)"""
    return "".join(f'<note pos="{p}" len="{max(1, l)}" key="{k}" vol="{v}" pan="0"/>' for p, l, k, v in notes)


def project_xml(bpm: float, tracks: list[tuple[str, str, list, bool]], length_ticks: int) -> str:
    """tracks: (name, instrumenttrack xml, notes (tick, len, key, vol), muted)"""
    out = ['<?xml version="1.0"?>', "<!DOCTYPE lmms-project>", '<lmms-project version="31" creator="LMMS" type="song">',
           f'<head bpm="{bpm:g}" timesig_numerator="4" timesig_denominator="4" mastervol="100" masterpitch="0"/>',
           "<song>", '<trackcontainer type="song">']
    for name, it, notes, muted in tracks:
        out.append(f'<track type="0" name={quoteattr(name)} muted="{int(muted)}" solo="0">{it}'
                   f'<midiclip type="1" pos="0" len="{length_ticks}" name={quoteattr(name)} muted="0" steps="16">'
                   f"{note_xml(notes)}</midiclip></track>")
    out += ["</trackcontainer>", "</song>", "</lmms-project>"]
    return "\n".join(out)


def to_lmms_notes(notes, beat_s: float, seconds_of) -> list[tuple[int, int, int, int]]:
    """Engine notes -> LMMS (tick, len, key, vol), keeping the performed timing (swing, push, humanise)
    at LMMS's resolution of 48 ticks per beat."""
    out = []
    for n in notes:
        t = seconds_of(n)
        tick = max(0, int(round(t / beat_s * TPB)))
        length = max(1, int(round(n.dur * TPB)))
        vol = int(np.clip(40 + 120 * n.vel, 1, 200))
        out.append((tick, length, int(n.pitch) - 12, vol))
    return out


def render_parts(parts: dict[str, tuple[dict, list]], bpm: float, n_samples: int, sr: int, workdir: Path | None = None,
                 timeout: float = 3600) -> dict[str, np.ndarray]:
    """Render several parts with their LMMS instruments in one headless LMMS run.
    parts: name -> (voice spec, lmms notes). Returns name -> stereo float32 array of n_samples."""
    length_ticks = int(np.ceil(n_samples / sr / (60 / bpm) * TPB)) + TPB * 4
    names = list(parts)
    with tempfile.TemporaryDirectory(dir=workdir) as d:
        d = Path(d)
        tracks = [(f"p{i:02d}", instrument_xml(parts[nm][0]), parts[nm][1], False) for i, nm in enumerate(names)]
        (d / "parts.mmp").write_text(project_xml(bpm, tracks, length_ticks))
        (d / "out").mkdir()
        r = subprocess.run(["nice", "-n", "15", lmms_bin(), "rendertracks", str(d / "parts.mmp"), "-o", str(d / "out"),
                            "-f", "wav", "-a", "-s", str(sr)], capture_output=True, text=True, timeout=timeout)
        files = sorted((d / "out").glob("*.wav"), key=lambda f: int(f.name.split("_", 1)[0]))
        if len(files) != len(names):
            raise RuntimeError(f"LMMS rendered {len(files)} of {len(names)} tracks:\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        out = {}
        for nm, f in zip(names, files):   # rendertracks numbers files in track order: 1_p00.wav, 2_p01.wav, ...
            x, fsr = sf.read(str(f), dtype="float32", always_2d=True)
            if x.shape[1] == 1:
                x = np.repeat(x, 2, 1)
            x = x[:n_samples]
            if len(x) < n_samples:
                x = np.pad(x, ((0, n_samples - len(x)), (0, 0)))
            out[nm] = x.astype(np.float32)
        return out
