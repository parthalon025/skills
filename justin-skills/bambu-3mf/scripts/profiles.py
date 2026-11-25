#!/usr/bin/env python3
"""profiles.py x1.0 -- resolve Bambu Studio system presets to flat key/value dicts.

Source: bambulab/BambuStudio resources/profiles/BBL (index BBL.json -> sub_path).
Resolution follows "inherits" (child wins) and "include" (template files, child wins).
Results cache in ~/.cache/bambu-3mf/<ref>/.

Use: key validation, the settings report, and per-nozzle-key detection.
Do NOT treat the result as a project_settings.config. Bambu Studio builds that itself
(finalize step on the PC, with the installed *_full presets).

CLI:  python profiles.py process "0.20mm Standard @BBL H2D" [--ref master] [--out flat.json]
"""
import json, os, sys, urllib.parse, urllib.request, argparse

RAW = "https://raw.githubusercontent.com/bambulab/BambuStudio/{ref}/resources/profiles/BBL{path}"
META = {"name", "inherits", "from", "setting_id", "instantiation", "include", "type", "description",
        "filament_id", "version", "is_custom_defined"}


class ProfileError(RuntimeError):
    pass


def _cache_dir(ref):
    d = os.path.join(os.path.expanduser("~"), ".cache", "bambu-3mf", ref)
    os.makedirs(d, exist_ok=True)
    return d


def _get(ref, path):
    cp = os.path.join(_cache_dir(ref), path.strip("/").replace("/", "__"))
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    url = RAW.format(ref=ref, path=urllib.parse.quote(path))
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except Exception as e:  # fail closed: caller decides
        raise ProfileError(f"fetch failed {url}: {e}")
    open(cp, "wb").write(data)
    return json.loads(data)


class Index:
    def __init__(self, ref="master"):
        self.ref = ref
        d = _get(ref, ".json")
        self.version = d.get("version")
        self.paths = {}
        for k in ("machine_model_list", "machine_list", "process_list", "filament_list"):
            for x in d.get(k, []):
                self.paths[x["name"]] = "/" + x["sub_path"]

    def raw(self, name):
        if name not in self.paths:
            raise ProfileError(f"preset not in BBL index ({self.ref}): {name!r}")
        return _get(self.ref, self.paths[name])

    def resolve(self, name, _seen=None):
        """Flat dict; '_chain' lists the inheritance order (leaf first)."""
        _seen = _seen or []
        if name in _seen:
            raise ProfileError(f"inheritance cycle: {_seen + [name]}")
        p = self.raw(name)
        flat, chain = {}, []
        if p.get("inherits"):
            parent = self.resolve(p["inherits"], _seen + [name])
            chain = parent.pop("_chain")
            flat.update(parent)
        for inc in p.get("include", []) or []:
            sub = self.resolve(inc, _seen + [name])
            sub.pop("_chain")
            flat.update(sub)
        flat.update({k: v for k, v in p.items() if k not in META})
        flat["_chain"] = [name] + chain
        return flat

    def find(self, text, kind=None, limit=20):
        t = text.lower()
        out = [n for n, sp in self.paths.items() if t in n.lower() and (kind is None or sp.startswith(f"/{kind}/"))]
        return out[:limit]


def nozzle_variant_keys(flat_process):
    """Keys whose value is a list in the process preset. On the H2D these are per-nozzle /
    per-extruder-variant arrays. Prior lesson: a malformed per-object value of such a key is a
    crash risk, so build_3mf refuses them at object/part/range scope."""
    return sorted(k for k, v in flat_process.items() if isinstance(v, list) and not k.startswith("_")
                  and k not in ("compatible_printers", "compatible_prints", "different_settings_to_system"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["machine", "process", "filament", "find"])
    ap.add_argument("name")
    ap.add_argument("--ref", default="master")
    ap.add_argument("--out")
    a = ap.parse_args()
    ix = Index(a.ref)
    if a.kind == "find":
        print("\n".join(ix.find(a.name)))
        sys.exit(0)
    flat = ix.resolve(a.name)
    print(f"{a.name}: {len(flat) - 1} keys; chain {' <- '.join(flat['_chain'])}; profiles {ix.version}")
    if a.out:
        json.dump(flat, open(a.out, "w"), indent=1, sort_keys=True)


SRC = "https://raw.githubusercontent.com/bambulab/BambuStudio/{ref}/src/libslic3r/PrintConfig.cpp"
SCALAR_TYPES = {"coFloat", "coInt", "coBool", "coString", "coEnum", "coPercent", "coFloatOrPercent", "coPoint"}


def parse_key_catalog(src_text):
    """{key: {"type": coX, "enum": [...]}} from PrintConfigDef (CLI option defs excluded)."""
    import re
    cut = src_text.find("CLIActionsConfigDef::CLIActionsConfigDef")
    s = src_text[:cut] if cut > 0 else src_text
    adds = list(re.finditer(r'def\s*=\s*this->add(?:_nullable)?\("([a-z0-9_]+)",\s*(co[A-Za-z]+)\)', s))
    cat = {}
    for i, m in enumerate(adds):
        block = s[m.end(): adds[i + 1].start() if i + 1 < len(adds) else len(s)]
        ev = re.findall(r'enum_values\.push_back\("([^"]*)"\)', block)
        cat.setdefault(m.group(1), {"type": m.group(2), "enum": ev})
    return cat


def key_catalog(ref="master"):
    cp = os.path.join(_cache_dir(ref), "key_catalog.json")
    if os.path.exists(cp):
        return json.load(open(cp))
    try:
        txt = urllib.request.urlopen(SRC.format(ref=ref), timeout=90).read().decode("utf-8", "replace")
        cat = parse_key_catalog(txt)
    except Exception as e:
        snap = sorted(f for f in os.listdir(os.path.join(os.path.dirname(__file__), "..", "assets")) if f.startswith("key_catalog"))
        if not snap:
            raise ProfileError(f"key catalog unavailable: {e}")
        cat = json.load(open(os.path.join(os.path.dirname(__file__), "..", "assets", snap[-1])))
    json.dump(cat, open(cp, "w"))
    return cat
