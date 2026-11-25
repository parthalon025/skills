#!/usr/bin/env python3
"""validate_3mf.py x1.0 -- fail-closed checks on a 3MF written by build_3mf.py (or any Bambu 3MF).

  python validate_3mf.py file.3mf [--manifest manifest.json] [--json out.json]

Checks (each reports PASS / FAIL / NOT RUN; NOT RUN never counts as PASS):
  C1 zip + required parts present            C6 config objects == model assembly objects
  C2 every XML part well-formed              C7 part ids == component ids of their object
  C3 lib3mf (3MF Consortium) reads the model C8 plate instances reference real objects, each once
  C4 resource ids unique, refs resolve       C9 extruder indices within filament count (needs manifest)
  C5 meshes: index range, no degenerate      C10 every object closed solid, inside its plate, on the bed
     triangles, watertight (trimesh)         C11 height ranges reference real objects, min<max
                                             C12 no project_settings.config in a non-Bambu-authored file
Exit 0 only if no FAIL.
"""
import argparse, json, re, sys, zipfile, math
import xml.etree.ElementTree as ET
import numpy as np

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
GAP = 1 / 5


def cols(n):
    v = math.sqrt(n); r = round(v)
    return int(r + 1 if v > r else r)


def main(path, manifest=None):
    R = []
    add = lambda cid, st, msg: R.append({"check": cid, "status": st, "detail": msg})
    man = json.load(open(manifest)) if manifest else None
    try:
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
    except Exception as e:
        add("C1", "FAIL", f"not a zip: {e}"); return R
    need = {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
    miss = need - names
    add("C1", "FAIL" if miss else "PASS", f"missing {sorted(miss)}" if miss else f"{len(names)} entries")
    bad = []
    trees = {}
    for n in names:
        if n.endswith((".model", ".config", ".rels", ".xml")) and not n.endswith("project_settings.config"):
            try: trees[n] = ET.fromstring(z.read(n))
            except ET.ParseError as e: bad.append(f"{n}: {e}")
    add("C2", "FAIL" if bad else "PASS", "; ".join(bad) or f"{len(trees)} XML parts parse")
    # C3 lib3mf
    try:
        import lib3mf
        w = lib3mf.get_wrapper(); m = w.CreateModel(); rd = m.QueryReader("3mf")
        rd.SetStrictModeActive(False); rd.ReadFromFile(path)
        nw = rd.GetWarningCount()
        warn = [rd.GetWarning(i)[0] for i in range(nw)]
        it = m.GetMeshObjects(); nm = 0
        while it.MoveNext(): nm += 1
        # 32935 'Invalid Attribute in namespace' = Bambu's printable="1" on build items (not core 3MF,
        # written by Bambu Studio itself). Expected; any other warning fails.
        other = [x for x in warn if x != 32935]
        add("C3", "FAIL" if other else "PASS", f"lib3mf {w.GetLibraryVersion()} read OK, {nm} mesh objects"
            + (f"; expected Bambu 'printable' attribute warning x{nw - len(other)}" if nw - len(other) else "")
            + (f"; unexpected warnings {other[:5]}" if other else ""))
    except ImportError:
        add("C3", "NOT RUN", "lib3mf not installed (pip install lib3mf)")
    except Exception as e:
        add("C3", "FAIL", f"lib3mf: {e}")
    root = trees.get("3D/3dmodel.model")
    if root is None:
        return R
    app = [e.text for e in root.findall("m:metadata", NS) if e.get("name") == "Application"]
    bbl = bool(app and app[0].startswith("BambuStudio-"))
    objs = {}
    dup = []
    for o in root.find("m:resources", NS).findall("m:object", NS):
        i = int(o.get("id"))
        if i in objs: dup.append(i)
        objs[i] = o
    comps = {i: [int(c.get("objectid")) for c in o.findall("m:components/m:component", NS)] for i, o in objs.items()}
    dangling = [(i, c) for i, cs in comps.items() for c in cs if c not in objs]
    items = [int(it.get("objectid")) for it in root.findall("m:build/m:item", NS)]
    dang_items = [i for i in items if i not in objs]
    st = "FAIL" if dup or dangling or dang_items else "PASS"
    add("C4", st, f"dup ids {dup}, dangling components {dangling}, dangling build items {dang_items}" if st == "FAIL"
        else f"{len(objs)} resources, {len(items)} build items")
    # C5 meshes
    meshes, mbad = {}, []
    try:
        import trimesh
        have_tm = True
    except ImportError:
        have_tm = False
    for i, o in objs.items():
        me = o.find("m:mesh", NS)
        if me is None: continue
        V = np.array([[float(v.get(a)) for a in "xyz"] for v in me.find("m:vertices", NS)])
        T = np.array([[int(t.get(a)) for a in ("v1", "v2", "v3")] for t in me.find("m:triangles", NS)])
        if T.size == 0 or T.min() < 0 or T.max() >= len(V): mbad.append(f"{i}: index out of range"); continue
        degen = int(((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2]) | (T[:, 0] == T[:, 2])).sum())
        if degen: mbad.append(f"{i}: {degen} degenerate triangles")
        meshes[i] = (V, T, o.get("type", "model"))
        if have_tm:
            tm = trimesh.Trimesh(V, T, process=False)
            if not (tm.is_watertight and tm.is_winding_consistent): mbad.append(f"{i}: not watertight/consistent")
            elif tm.volume <= 0: mbad.append(f"{i}: inverted (volume {tm.volume:.2f})")
    add("C5", "FAIL" if mbad else ("PASS" if have_tm else "NOT RUN"),
        "; ".join(mbad[:8]) or f"{len(meshes)} meshes closed and consistent")
    cfg = trees.get("Metadata/model_settings.config")
    if cfg is None:
        for c in ("C6", "C7", "C8", "C9", "C10", "C11"): add(c, "NOT RUN", "no model_settings.config")
    else:
        cobj = {int(o.get("id")): o for o in cfg.findall("object")}
        assemblies = {i for i, cs in comps.items() if cs}
        top = set(items)
        st = "PASS" if set(cobj) == top else "FAIL"
        add("C6", st, f"config objects {sorted(cobj)} vs build items {sorted(top)}" if st == "FAIL" else f"{len(cobj)} objects")
        p_bad = []
        for i, o in cobj.items():
            pid = [int(p.get("id")) for p in o.findall("part")]
            if comps.get(i) and pid != comps[i]: p_bad.append(f"object {i}: parts {pid} != components {comps[i]}")
        add("C7", "FAIL" if p_bad else "PASS", "; ".join(p_bad) or "part ids match components")
        plates = cfg.findall("plate")
        seen, pb = {}, []
        for pl in plates:
            pid = int([m.get("value") for m in pl.findall("metadata") if m.get("key") == "plater_id"][0])
            for mi in pl.findall("model_instance"):
                oid = int([m.get("value") for m in mi.findall("metadata") if m.get("key") == "object_id"][0])
                if oid not in cobj: pb.append(f"plate {pid}: unknown object {oid}")
                if oid in seen: pb.append(f"object {oid} on plates {seen[oid]} and {pid}")
                seen[oid] = pid
        unplaced = sorted(set(cobj) - set(seen)) if plates else []
        if unplaced: pb.append(f"objects on no plate: {unplaced}")
        add("C8", "FAIL" if pb else "PASS", "; ".join(pb) or f"{len(plates)} plates, {len(seen)} instances")
        ext = [int(m.get("value")) for m in cfg.iter("metadata") if m.get("key") == "extruder"]
        if man:
            nf = man["n_filaments"]; bad_e = sorted({e for e in ext if not 1 <= e <= nf})
            used = {f["slot"] for f in man["filaments"] if f["used"]}
            un = sorted({e for e in ext if e not in used})
            add("C9", "FAIL" if bad_e or un else "PASS",
                f"out of range {bad_e}, placeholder slots used {un}" if bad_e or un else f"extruders {sorted(set(ext))} of {nf}")
        else:
            add("C9", "NOT RUN", "no manifest: filament count unknown")
        # C10 placement
        if man and meshes:
            bw, bd, bh = man["bed"]; c = cols(len(plates)); pr = []
            for oid, pid in seen.items():
                row, col = divmod(pid - 1, c); ox, oy = col * bw * (1 + GAP), -row * bd * (1 + GAP)
                parts = [meshes[k] for k in comps.get(oid, [oid]) if k in meshes and meshes[k][2] == "model"]
                if not parts: continue
                V = np.vstack([p[0] for p in parts]); lo, hi = V.min(0), V.max(0)
                if lo[0] < ox - .01 or hi[0] > ox + bw + .01 or lo[1] < oy - .01 or hi[1] > oy + bd + .01:
                    pr.append(f"object {oid} outside plate {pid}")
                if abs(lo[2]) > 0.01: pr.append(f"object {oid} min z {lo[2]:.3f} (not on bed)")
                if hi[2] > bh + .01: pr.append(f"object {oid} too tall {hi[2]:.1f}")
            add("C10", "FAIL" if pr else "PASS", "; ".join(pr) or "all objects on bed, inside their plate")
        else:
            add("C10", "NOT RUN", "needs manifest (bed size)")
        rx = trees.get("Metadata/layer_config_ranges.xml")
        if rx is None:
            add("C11", "PASS", "no height ranges")
        else:
            rb = []
            for o in rx.findall("object"):
                if int(o.get("id")) not in cobj: rb.append(f"range on unknown object {o.get('id')}")
                for r in o.findall("range"):
                    if not float(r.get("min_z")) < float(r.get("max_z")): rb.append(f"object {o.get('id')}: min_z >= max_z")
            add("C11", "FAIL" if rb else "PASS", "; ".join(rb) or "ranges valid")
    has_ps = "Metadata/project_settings.config" in names
    authored = "Metadata/slice_info.config" in names or any(n.startswith("Metadata/plate_") and n.endswith(".json") for n in names)
    add("C12", "FAIL" if (has_ps and bbl and not authored) else "PASS",
        "project_settings.config present in a generated file (known Bambu Studio segfault)" if (has_ps and bbl and not authored)
        else ("no project_settings.config" if not has_ps else "project_settings.config from Bambu Studio"))
    return R


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--manifest"); ap.add_argument("--json")
    a = ap.parse_args()
    R = main(a.file, a.manifest)
    for r in R: print(f"{r['check']:>4} {r['status']:8} {r['detail']}")
    fail = [r for r in R if r["status"] == "FAIL"]
    print(f"RESULT: {'FAIL' if fail else 'PASS'} ({len(fail)} fail, {sum(r['status'] == 'NOT RUN' for r in R)} not run)")
    if a.json: json.dump(R, open(a.json, "w"), indent=2)
    sys.exit(1 if fail else 0)
