#!/usr/bin/env python3
"""build_3mf.py x1.0 -- build a Bambu Studio 3MF bundle from a job spec (JSON).

  python build_3mf.py spec.json [--out DIR] [--offline]

Writes <out>/<name>_<version>/ (refuses to overwrite: bump the version):
  <name>_<ver>.3mf                     plates, objects, parts, filaments, per-object/part/range settings, thumbnails
  <name>_<ver>_geometry_only.3mf       same plates/parts/filaments, no settings, no ranges   (crash isolation)
  <name>_<ver>_first_object.3mf        plate 1, first object only, with settings             (crash isolation)
  presets/<..>.process.json, presets/<..>.filament_<slot>.json   user presets (inherit system, carry overrides)
  finalize_<ver>.ps1                   PC step: bake full project_settings + slice-check with bambu-studio CLI
  <name>_<ver>_settings_report.md      every setting, value, source, scope
  previews/<name>_<ver>_plate<N>.png   visual inspection images
  manifest.json                        inputs, hashes, checks, warnings

Format rules come from bambulab/BambuStudio src/libslic3r/Format/bbs_3mf.cpp and prior field use.
See references/format.md. project_settings.config is NOT written here (see SKILL.md, rule 1).
"""
import argparse, copy, hashlib, io, json, math, os, re, shutil, sys, zipfile
from xml.sax.saxutils import quoteattr, escape
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKILL_VERSION = "x1.0"
APP_TAG = "BambuStudio-02.08.02.61"   # proven loadable in prior sessions; marks file as Bambu-native
PLATE_GAP = 1.0 / 5.0                  # PartPlate.cpp LOGICAL_PART_PLATE_GAP
BED_TYPES = {"Default Plate", "Cool Plate", "Engineering Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate"}
SEQUENCES = {"by layer", "by object"}
MAP_MODES = {"Auto For Flush", "Auto For Match", "Manual", "Nozzle Manual", "Auto For Quality"}
PART_TYPES = {"normal_part", "negative_part", "modifier_part", "support_enforcer", "support_blocker"}
DEFAULTS = {"machine": "Bambu Lab H2D 0.4 nozzle", "process": "0.20mm Standard @BBL H2D", "profiles_ref": "master",
            "bed_type": "Textured PEI Plate", "print_sequence": "by layer", "spacing": 6.0, "edge_margin": 5.0}


class SpecError(RuntimeError):
    pass


# --------------------------------------------------------------------------- helpers
def colmajor_cols(n):
    """PartPlate.hpp compute_colum_count."""
    v = math.sqrt(n); r = round(v)
    return int(r + 1 if v > r else r)


def sval(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def slug(s):
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", s).strip("_")


def rotation_matrix(deg_xyz):
    rx, ry, rz = [math.radians(a) for a in deg_xyz]
    X = trimesh.transformations.rotation_matrix(rx, [1, 0, 0])
    Y = trimesh.transformations.rotation_matrix(ry, [0, 1, 0])
    Z = trimesh.transformations.rotation_matrix(rz, [0, 0, 1])
    return Z @ Y @ X   # X first, then Y, then Z


def load_mesh(path, allow_open, label, warnings):
    if not os.path.exists(path):
        raise SpecError(f"{label}: mesh file not found: {path}")
    if path.lower().endswith((".step", ".stp")):
        try:
            import cadquery as cq
        except ImportError:
            raise SpecError(f"{label}: STEP needs cadquery; export STL/3MF from CAD instead")
        tmp = path + ".tmp.stl"
        cq.exporters.export(cq.importers.importStep(path), tmp, tolerance=0.01, angularTolerance=0.1)
        path = tmp
    m = trimesh.load(path, force="mesh", process=False)
    n0 = len(m.faces)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(m)
    if len(m.faces) != n0:
        warnings.append(f"{label}: cleaned {n0 - len(m.faces)} degenerate/duplicate faces")
    ok = m.is_watertight and m.is_winding_consistent and m.volume > 0
    if not ok and not allow_open:
        raise SpecError(f"{label}: mesh not a closed solid (watertight={m.is_watertight}, "
                        f"winding={m.is_winding_consistent}, volume={m.volume:.3f}). Fix in CAD, or set allow_open.")
    return m


# --------------------------------------------------------------------------- settings validation
class Settings:
    """Validate keys against resolved system presets. Fail closed when profiles are reachable;
    when --offline, validation is reported as NOT RUN (never as a pass)."""

    def __init__(self, machine, process, ref, offline, warnings):
        self.ok = False
        self.warnings = warnings
        self.proc = self.mach = None
        self.fil = {}
        if offline:
            warnings.append("settings key validation NOT RUN (--offline)")
            return
        try:
            from profiles import Index, nozzle_variant_keys, key_catalog, SCALAR_TYPES
            self.cat, self.scalar = key_catalog(ref), SCALAR_TYPES
            self.ix = Index(ref)
            self.proc = self.ix.resolve(process)
            self.mach = self.ix.resolve(machine)
            self.variant = set(nozzle_variant_keys(self.proc))
            self.version = self.ix.version
            self.ok = True
        except Exception as e:
            warnings.append(f"settings key validation NOT RUN (profiles unavailable: {e})")

    def filament(self, name):
        if not self.ok:
            return None
        if name not in self.fil:
            self.fil[name] = self.ix.resolve(name)
        return self.fil[name]

    def _known(self, scope, k, v):
        """Key must exist in Bambu's PrintConfigDef; enum values must be legal."""
        c = self.cat.get(k)
        if c is None:
            raise SpecError(f"{scope}: unknown Bambu config key {k!r}")
        if c["enum"]:
            for x in (v if isinstance(v, list) else [v]):
                if sval(x) not in c["enum"]:
                    raise SpecError(f"{scope}: {k!r}={x!r} not in {c['enum']}")
        return c

    def check_local(self, scope, d):
        """object / part / range settings: scalar process keys only."""
        out = {}
        for k, v in (d or {}).items():
            if k in ("extruder", "filament"):
                raise SpecError(f"{scope}: set filament with the 'filament' field, not in settings")
            if isinstance(v, (list, dict)):
                raise SpecError(f"{scope}: {k!r} must be a scalar at this scope")
            if self.ok:
                c = self._known(scope, k, v)
                if c["type"] not in self.scalar or k in self.variant:
                    raise SpecError(f"{scope}: {k!r} is a per-nozzle multi-value key ({c['type']}) on this printer. "
                                    f"Object-level values are a known crash risk; put it in process_overrides.")
            out[k] = sval(v)
        return out

    def check_preset(self, scope, d, flat):
        out = {}
        for k, v in (d or {}).items():
            if self.ok:
                c = self._known(scope, k, v)
                n = len(flat[k]) if (flat is not None and isinstance(flat.get(k), list)) else None
                if c["type"] in self.scalar:
                    if isinstance(v, list):
                        raise SpecError(f"{scope}: {k!r} is scalar")
                    v = sval(v)
                else:
                    if n is None:
                        n = 1
                        self.warnings.append(f"{scope}: {k!r} not in preset chain; written as 1-value list")
                    v = [sval(x) for x in v] if isinstance(v, list) else [sval(v)] * n
                    if len(v) != n:
                        raise SpecError(f"{scope}: {k!r} needs {n} values (per nozzle/variant), got {len(v)}")
            else:
                v = [sval(x) for x in v] if isinstance(v, list) else sval(v)
            out[k] = v
        return out


# --------------------------------------------------------------------------- core build
class Job:
    def __init__(self, spec_path, out_root, offline):
        self.spec_path = os.path.abspath(spec_path)
        self.base = os.path.dirname(self.spec_path)
        self.spec = json.load(open(spec_path, encoding="utf-8"))
        self.warnings, self.checks = [], []
        s = self.spec
        for k in ("name", "version", "filaments", "plates"):
            if k not in s:
                raise SpecError(f"spec missing {k!r}")
        if not re.match(r"^x?\d+(\.\d+)*$", s["version"]):
            raise SpecError("version must look like x1.0 (unsettled design) or 1.0 (SKU)")
        self.name, self.ver = slug(s["name"]), s["version"]
        self.tag = f"{self.name}_{self.ver}"
        pr = {**{k: DEFAULTS[k] for k in ("machine", "process", "profiles_ref")}, **s.get("printer", {})}
        self.printer = pr
        self.opt = {**{k: DEFAULTS[k] for k in ("spacing", "edge_margin")}, **s.get("options", {})}
        self.out = os.path.join(os.path.abspath(out_root), self.tag)
        if os.path.exists(self.out):
            raise SpecError(f"output exists: {self.out}. Existing plates are never overwritten; bump 'version'.")
        self.S = Settings(pr["machine"], pr["process"], pr["profiles_ref"], offline, self.warnings)
        self._bed()
        self._filaments()
        self._plates()

    # ---- bed
    def _bed(self):
        m = self.S.mach if self.S.ok else None
        def poly(strs):
            pts = np.array([[float(a) for a in p.split("x")] for p in strs])
            return pts.min(0), pts.max(0)
        if m:
            lo, hi = poly(m["printable_area"])
            self.bed_w, self.bed_d = hi - lo
            self.bed_h = float(m.get("printable_height", 300))
            area_lo, area_hi = lo.copy(), hi.copy()
            for ea in m.get("extruder_printable_area", []) or []:   # H2D: zone both nozzles reach
                l2, h2 = poly(ea.split(","))
                area_lo, area_hi = np.maximum(area_lo, l2), np.minimum(area_hi, h2)
            self.area = (area_lo, area_hi)
            self.full = (lo, hi)
        else:
            b = self.spec.get("bed", {"w": 350, "d": 320, "h": 325})
            self.bed_w, self.bed_d, self.bed_h = b["w"], b["d"], b["h"]
            self.full = self.area = (np.array([0., 0.]), np.array([b["w"], b["d"]]))
            self.warnings.append(f"bed size from spec/defaults {self.bed_w}x{self.bed_d} (machine preset not resolved)")

    # ---- filaments: project index == slot number (gaps get placeholders)
    def _filaments(self):
        F = self.spec["filaments"]
        slots = [int(f["slot"]) for f in F]
        if len(set(slots)) != len(slots) or min(slots) < 1:
            raise SpecError("filament slots must be unique and >= 1")
        self.n_fil = max(slots)
        by = {int(f["slot"]): f for f in F}
        first = by[min(slots)]
        self.fils = []
        for i in range(1, self.n_fil + 1):
            f = by.get(i)
            used = f is not None
            f = copy.deepcopy(f or {"slot": i, "preset": first["preset"], "color": "#808080", "label": f"unused slot {i}"})
            if not re.match(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", f.get("color", "#808080")):
                raise SpecError(f"filament slot {i}: color must be #RRGGBB")
            flat = self.S.filament(f["preset"]) if self.S.ok else None
            f["overrides"] = self.S.check_preset(f"filament slot {i}", f.get("overrides"), flat)
            f["used"] = used
            self.fils.append(f)
        flat = self.S.proc if self.S.ok else None
        self.proc_over = self.S.check_preset("process_overrides", self.spec.get("process_overrides"), flat)

    def _fil(self, v, scope):
        v = int(v)
        if not 1 <= v <= self.n_fil or not self.fils[v - 1]["used"]:
            raise SpecError(f"{scope}: filament {v} is not a defined slot")
        return v

    # ---- plates / objects / parts
    def _plates(self):
        P = self.spec["plates"]
        if not P:
            raise SpecError("no plates")
        self.cols = colmajor_cols(len(P))
        self.plates = []
        next_id = 1
        for pi, p in enumerate(P):
            scope = f"plate {pi + 1}"
            bt = p.get("bed_type", DEFAULTS["bed_type"]); sq = p.get("print_sequence", DEFAULTS["print_sequence"])
            if bt not in BED_TYPES: raise SpecError(f"{scope}: bed_type must be one of {sorted(BED_TYPES)}")
            if sq not in SEQUENCES: raise SpecError(f"{scope}: print_sequence must be one of {sorted(SEQUENCES)}")
            mm = p.get("filament_map_mode")
            if mm and mm not in MAP_MODES: raise SpecError(f"{scope}: filament_map_mode must be one of {sorted(MAP_MODES)}")
            nmap = p.get("nozzle_map")
            maps = None
            if nmap:
                mm = "Manual"
                side = {"left": 1, "right": 2, "1": 1, "2": 2}
                maps = [1] * self.n_fil
                for k, v in nmap.items():
                    maps[self._fil(k, scope) - 1] = side[str(v).lower()]
                self.warnings.append(f"{scope}: nozzle_map written as filament_maps (1=left, 2=right). "
                                     f"VERIFY the left/right assignment in Bambu Studio before printing.")
            row, col = divmod(pi, self.cols)
            origin = np.array([col * self.bed_w * (1 + PLATE_GAP), -row * self.bed_d * (1 + PLATE_GAP)])
            objs = []
            for oi, o in enumerate(p.get("objects", [])):
                for c in range(int(o.get("copies", 1))):
                    ob, next_id = self._object(o, f"{scope} object {o.get('name', oi)}", c, next_id)
                    objs.append(ob)
            if not objs: raise SpecError(f"{scope}: no objects")
            self._arrange(objs, scope)
            for ob in objs:   # bake world coordinates (plate offset); proven loadable layout
                d = np.array([ob["xy"][0] - ob["c"][0] + origin[0], ob["xy"][1] - ob["c"][1] + origin[1], 0.0])
                for prt in ob["parts"]:
                    prt["mesh"].apply_translation(d)
            self.plates.append({"name": p.get("name", ""), "bed_type": bt, "seq": sq, "map_mode": mm, "maps": maps,
                                "origin": origin, "objects": objs, "locked": bool(p.get("locked", False))})

    def _object(self, o, scope, copy_i, next_id):
        parts_spec = list(o.get("parts", []))
        if o.get("mesh"):
            parts_spec.insert(0, {"name": o.get("name", "body"), "mesh": o["mesh"], "type": "normal_part"})
        if not parts_spec:
            raise SpecError(f"{scope}: needs 'mesh' or 'parts'")
        base_name = o.get("name") or os.path.splitext(os.path.basename(parts_spec[0]["mesh"]))[0]
        name = f"{base_name}_{self.ver}" if self.ver not in base_name else base_name
        if int(o.get("copies", 1)) > 1:
            name += f"_c{copy_i + 1}"
        T = np.eye(4)
        T[:3, :3] = rotation_matrix(o.get("rotate", [0, 0, 0]))[:3, :3] * float(o.get("scale", 1.0))
        obj_fil = self._fil(o.get("filament", self.fils[[f["used"] for f in self.fils].index(True)]["slot"]), scope)
        parts = []
        for k, ps in enumerate(parts_spec):
            t = ps.get("type", "normal_part")
            if t not in PART_TYPES: raise SpecError(f"{scope}: part type must be one of {sorted(PART_TYPES)}")
            label = f"{scope} part {ps.get('name', k)}"
            m = load_mesh(os.path.join(self.base, ps["mesh"]), ps.get("allow_open", False), label, self.warnings)
            m.apply_transform(T)
            pn = ps.get("name") or f"{base_name}_part{k + 1}"
            if self.ver not in pn: pn = f"{pn}_{self.ver}"
            parts.append({"name": pn, "type": t, "mesh": m,
                          "fil": self._fil(ps["filament"], label) if "filament" in ps else obj_fil,
                          "settings": self.S.check_local(label, ps.get("settings"))})
        normal = [p["mesh"] for p in parts if p["type"] == "normal_part"]
        if not normal: raise SpecError(f"{scope}: needs at least one normal_part")
        lo = np.min([m.bounds[0] for m in normal], 0); hi = np.max([m.bounds[1] for m in normal], 0)
        for p in parts:
            p["mesh"].apply_translation([0, 0, -lo[2]])
        hi[2] -= lo[2]; lo[2] = 0
        if hi[2] > self.bed_h: raise SpecError(f"{scope}: height {hi[2]:.1f} > printable height {self.bed_h}")
        ranges = []
        for r in o.get("height_ranges", []):
            if not 0 <= r["min_z"] < r["max_z"]: raise SpecError(f"{scope}: bad height range {r}")
            ranges.append({"min_z": float(r["min_z"]), "max_z": float(r["max_z"]),
                           "settings": self.S.check_local(f"{scope} range", r.get("settings"))})
        ob = {"id": None, "name": name, "fil": obj_fil, "parts": parts, "lo": lo, "hi": hi,
              "c": (lo[:2] + hi[:2]) / 2, "size": hi[:2] - lo[:2], "xy": o.get("position"),
              "settings": self.S.check_local(scope, o.get("settings")), "ranges": ranges}
        for p in parts:
            p["id"] = next_id; next_id += 1
        ob["id"] = next_id; next_id += 1
        return ob, next_id

    def _arrange(self, objs, scope):
        (alo, ahi), (flo, fhi) = self.area, self.full
        gap, mg = float(self.opt["spacing"]), float(self.opt["edge_margin"])
        x0, y0 = alo[0] + mg, alo[1] + mg
        x, y, row_h = x0, y0, 0.0
        auto = [o for o in objs if o["xy"] is None]
        for ob in sorted(auto, key=lambda o: -o["size"][1]):
            w, d = ob["size"]
            if x + w > ahi[0] - mg:
                x, y, row_h = x0, y + row_h + gap, 0.0
            if y + d > ahi[1] - mg:
                raise SpecError(f"{scope}: objects do not fit; move some to another plate")
            ob["xy"] = [x + w / 2, y + d / 2]; x += w + gap; row_h = max(row_h, d)
        if auto:   # centre the packed group in the shared-nozzle zone
            glo = np.min([np.array(o["xy"]) - o["size"] / 2 for o in auto], 0)
            ghi = np.max([np.array(o["xy"]) + o["size"] / 2 for o in auto], 0)
            shift = (alo + ahi) / 2 - (glo + ghi) / 2
            for o in auto: o["xy"] = list(np.array(o["xy"]) + shift)
        for ob in objs:
            lo2 = np.array(ob["xy"]) - ob["size"] / 2; hi2 = np.array(ob["xy"]) + ob["size"] / 2
            if (lo2 < flo - 1e-6).any() or (hi2 > fhi + 1e-6).any():
                raise SpecError(f"{scope}: {ob['name']} lies outside the printable area")
            if (lo2 < alo - 1e-6).any() or (hi2 > ahi + 1e-6).any():
                self.warnings.append(f"{scope}: {ob['name']} is outside the zone both nozzles reach; "
                                     f"only one nozzle can print it")
        boxes = [(np.array(o["xy"]) - o["size"] / 2, np.array(o["xy"]) + o["size"] / 2, o["name"]) for o in objs]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if (a[0] < b[1]).all() and (b[0] < a[1]).all():
                    self.warnings.append(f"{scope}: bounding boxes of {a[2]} and {b[2]} overlap")

    # ----------------------------------------------------------------------- writers
    def _model_xml(self, plates):
        out = io.StringIO(); w = out.write
        w('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
          'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">\n'
          f' <metadata name="Application">{APP_TAG}</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
          f' <metadata name="Title">{escape(self.tag)}</metadata>\n <metadata name="Designer">bambu-3mf skill {SKILL_VERSION}</metadata>\n'
          ' <resources>\n')
        items = []
        for pl in plates:
            for ob in pl["objects"]:
                for p in ob["parts"]:
                    t = "other" if p["type"] != "normal_part" else "model"
                    w(f'  <object id="{p["id"]}" name={quoteattr(p["name"])} type="{t}">\n   <mesh>\n    <vertices>\n')
                    w("".join(f'     <vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>\n' for a, b, c in p["mesh"].vertices))
                    w('    </vertices>\n    <triangles>\n')
                    w("".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in p["mesh"].faces))
                    w('    </triangles>\n   </mesh>\n  </object>\n')
                w(f'  <object id="{ob["id"]}" name={quoteattr(ob["name"])} type="model">\n   <components>\n')
                w("".join(f'    <component objectid="{p["id"]}"/>\n' for p in ob["parts"]))
                w('   </components>\n  </object>\n')
                items.append(ob["id"])
        w(' </resources>\n <build>\n' + "".join(f'  <item objectid="{i}" printable="1"/>\n' for i in items) + ' </build>\n</model>\n')
        return out.getvalue()

    def _config_xml(self, plates, with_settings):
        md = lambda k, v, ind: f'{ind}<metadata key="{k}" value={quoteattr(sval(v))}/>\n'
        out = ['<?xml version="1.0" encoding="UTF-8"?>\n<config>\n']
        ident = 1000
        for pl in plates:
            for ob in pl["objects"]:
                out.append(f'  <object id="{ob["id"]}">\n' + md("name", ob["name"], "    ") + md("extruder", ob["fil"], "    "))
                if with_settings:
                    out += [md(k, v, "    ") for k, v in ob["settings"].items()]
                for p in ob["parts"]:
                    out.append(f'    <part id="{p["id"]}" subtype="{p["type"]}">\n' + md("name", p["name"], "      ")
                               + md("extruder", p["fil"], "      "))
                    if with_settings:
                        out += [md(k, v, "      ") for k, v in p["settings"].items()]
                    out.append('    </part>\n')
                out.append('  </object>\n')
        for i, pl in enumerate(plates, 1):
            out.append('  <plate>\n' + md("plater_id", i, "    ") + md("plater_name", pl["name"], "    ")
                       + md("locked", "true" if pl["locked"] else "false", "    "))
            if with_settings:
                out += [md("bed_type", pl["bed_type"], "    "), md("print_sequence", pl["seq"], "    ")]
                if pl["map_mode"]: out.append(md("filament_map_mode", pl["map_mode"], "    "))
                if pl["maps"]: out.append(md("filament_maps", " ".join(map(str, pl["maps"])), "    "))
            out.append(md("thumbnail_file", f"Metadata/plate_{i}.png", "    "))
            for ob in pl["objects"]:
                ident += 1
                out.append('    <model_instance>\n' + md("object_id", ob["id"], "      ") + md("instance_id", 0, "      ")
                           + md("identify_id", ident, "      ") + '    </model_instance>\n')
            out.append('  </plate>\n')
        out.append('</config>\n')
        return "".join(out)

    def _ranges_xml(self, plates):
        objs = [ob for pl in plates for ob in pl["objects"] if ob["ranges"]]
        if not objs: return None
        s = '<?xml version="1.0" encoding="utf-8"?>\n<objects>\n'
        for ob in objs:
            s += f' <object id="{ob["id"]}">\n'
            for r in ob["ranges"]:
                s += f'  <range min_z="{r["min_z"]:.3f}" max_z="{r["max_z"]:.3f}">\n'
                s += "".join(f'   <option opt_key="{k}">{escape(v)}</option>\n' for k, v in r["settings"].items())
                s += '  </range>\n'
            s += ' </object>\n'
        return s + '</objects>\n'

    def _render(self, pl, idx, size_px, path=None):
        """Iso view (thumbnail). With path: iso + top view with labels and the dual-nozzle zone."""
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        TYPE_RGB = {"negative_part": [.9, .1, .1], "modifier_part": [.95, .75, .1],
                    "support_blocker": [.8, .2, .8], "support_enforcer": [.2, .6, .9]}
        ox, oy = pl["origin"]
        two = path is not None
        fig = plt.figure(figsize=((2 if two else 1) * size_px / 100, size_px / 100), dpi=100)
        ax = fig.add_subplot(1, 2 if two else 1, 1, projection="3d")
        bx = [ox, ox + self.bed_w, ox + self.bed_w, ox, ox]; by = [oy, oy, oy + self.bed_d, oy + self.bed_d, oy]
        ax.plot(bx, by, [0] * 5, color="#444", lw=1)
        for gx in np.arange(ox, ox + self.bed_w + 1e-6, 50): ax.plot([gx, gx], [oy, oy + self.bed_d], [0, 0], color="#bbb", lw=.4)
        for gy in np.arange(oy, oy + self.bed_d + 1e-6, 50): ax.plot([ox, ox + self.bed_w], [gy, gy], [0, 0], color="#bbb", lw=.4)
        light = np.array([0.35, -0.55, 0.75]); light /= np.linalg.norm(light)
        zmax = 1.0
        for ob in pl["objects"]:
            for p in ob["parts"]:
                m = p["mesh"]
                base = np.array(matplotlib.colors.to_rgb(self.fils[p["fil"] - 1]["color"][:7])) * 0.85
                if p["type"] in TYPE_RGB: base = np.array(TYPE_RGB[p["type"]])
                shade = 0.30 + 0.70 * np.clip(m.face_normals @ light, 0, 1)[:, None]
                ax.add_collection3d(Poly3DCollection(m.vertices[m.faces], facecolors=np.clip(base * shade, 0, 1),
                                                     alpha=1.0 if p["type"] == "normal_part" else 0.3,
                                                     edgecolor=(0, 0, 0, .15) if len(m.faces) < 1500 else "none",
                                                     linewidths=.15))
                zmax = max(zmax, m.bounds[1][2])
        span = max(self.bed_w, self.bed_d); zr = max(zmax * 1.1, span * 0.15)
        ax.set_xlim(ox, ox + span); ax.set_ylim(oy, oy + span); ax.set_zlim(0, zr)
        ax.set_box_aspect((1, 1, zr / span)); ax.view_init(elev=32, azim=-62); ax.set_axis_off()
        ax.set_title(f"{self.tag}  plate {idx}: {pl['name']}", fontsize=8)
        if two:
            a2 = fig.add_subplot(1, 2, 2); a2.set_aspect("equal")
            a2.plot(bx, by, color="#444", lw=1)
            (alo, ahi) = self.area
            a2.add_patch(plt.Rectangle((ox + alo[0], oy + alo[1]), ahi[0] - alo[0], ahi[1] - alo[1], fill=False, ls="--", ec="#888", lw=.8))
            for ob in pl["objects"]:
                for p in ob["parts"]:
                    m = p["mesh"]
                    c = TYPE_RGB.get(p["type"], matplotlib.colors.to_rgb(self.fils[p["fil"] - 1]["color"][:7]))
                    tri = m.vertices[m.faces][:, :, :2]
                    keep = m.face_normals[:, 2] > 1e-3 if p["type"] == "normal_part" else np.ones(len(tri), bool)
                    from matplotlib.collections import PolyCollection
                    a2.add_collection(PolyCollection(tri[keep], facecolors=[c], edgecolors="none",
                                                     alpha=1 if p["type"] == "normal_part" else .35))
                lo = np.array(ob["xy"]) - ob["size"] / 2 + pl["origin"]
                a2.add_patch(plt.Rectangle(lo, *ob["size"], fill=False, ec="#000", lw=.5))
                a2.text(lo[0], lo[1] + ob["size"][1] + 2, f"{ob['name']} [F{ob['fil']}]", fontsize=4, rotation=30)
            a2.set_xlim(ox - 5, ox + self.bed_w + 5); a2.set_ylim(oy - 5, oy + self.bed_d + 5)
            a2.set_title("top view (dashed: zone both nozzles reach)", fontsize=8); a2.tick_params(labelsize=6)
            a2.set_facecolor("#e9e9e9")
        buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white"); plt.close(fig)
        data = buf.getvalue()
        if path: open(path, "wb").write(data)
        return data

    def _pack(self, path, plates, with_settings, thumbs):
        ct = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
              ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
              ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
              ' <Default Extension="png" ContentType="image/png"/>\n <Default Extension="config" ContentType="text/xml"/>\n'
              ' <Default Extension="xml" ContentType="text/xml"/>\n</Types>\n')
        rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
                ' <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>\n'
                '</Relationships>\n')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct); z.writestr("_rels/.rels", rels)
            z.writestr("3D/3dmodel.model", self._model_xml(plates))
            z.writestr("Metadata/model_settings.config", self._config_xml(plates, with_settings))
            r = self._ranges_xml(plates) if with_settings else None
            if r: z.writestr("Metadata/layer_config_ranges.xml", r)
            for i, t in enumerate(thumbs, 1):
                z.writestr(f"Metadata/plate_{i}.png", t)

    def _presets(self):
        d = os.path.join(self.out, "presets"); os.makedirs(d)
        pv = self.S.version if self.S.ok else "02.00.00.00"
        proc_name = f"{self.printer['process']} {self.tag}"
        pj = {"type": "process", "name": proc_name, "inherits": self.printer["process"], "from": "User",
              "print_settings_id": proc_name, "version": pv, **self.proc_over}
        files = {"machine": self.printer["machine"], "process": f"presets/{self.tag}.process.json", "filaments": []}
        json.dump(pj, open(os.path.join(d, f"{self.tag}.process.json"), "w"), indent=2)
        for f in self.fils:
            fname = f"{f['preset']} {self.tag} slot{f['slot']}"
            fj = {"type": "filament", "name": fname, "inherits": f["preset"], "from": "User",
                  "filament_settings_id": [fname], "version": pv, "filament_colour": [f["color"][:7].upper()], **f["overrides"]}
            fp = f"presets/{self.tag}.filament_{f['slot']}.json"
            json.dump(fj, open(os.path.join(self.out, fp), "w"), indent=2)
            files["filaments"].append(fp)
        return files

    def _report(self, files):
        L = [f"# {self.tag} -- settings report", "",
             f"Generated by bambu-3mf skill {SKILL_VERSION}. Printer `{self.printer['machine']}`, process `{self.printer['process']}`"
             f"{', profiles ' + self.S.version if self.S.ok else ''}.", "",
             "Scope legend: **3MF-object / 3MF-part / 3MF-range / 3MF-plate** live in the 3MF. **preset** lives in the user preset JSON "
             "and enters the project when `finalize` bakes it. **system** is the system preset value (no override).", ""]
        L += ["## Filaments (project index = slot)", "", "| Slot | Label | Preset | Colour | Overrides |", "|---|---|---|---|---|"]
        for f in self.fils:
            L.append(f"| {f['slot']} | {f.get('label', '')}{'' if f['used'] else ' (placeholder)'} | {f['preset']} | {f['color']} | "
                     + (", ".join(f"`{k}`={','.join(v) if isinstance(v, list) else v}" for k, v in f["overrides"].items()) or "-") + " |")
        L += ["", "## Plates", ""]
        for i, pl in enumerate(self.plates, 1):
            L.append(f"### Plate {i}: {pl['name'] or '(unnamed)'}")
            L.append(f"bed_type `{pl['bed_type']}`, print_sequence `{pl['seq']}`, filament_map_mode `{pl['map_mode'] or 'printer default'}`"
                     + (f", filament_maps `{' '.join(map(str, pl['maps']))}`" if pl["maps"] else "") + ".")
            L += ["", "| Object | Part | Type | Filament | Settings (3MF) |", "|---|---|---|---|---|"]
            for ob in pl["objects"]:
                L.append(f"| **{ob['name']}** | - | object | {ob['fil']} | " + (", ".join(f"`{k}`={v}" for k, v in ob["settings"].items()) or "-") + " |")
                for p in ob["parts"]:
                    L.append(f"| | {p['name']} | {p['type']} | {p['fil']} | " + (", ".join(f"`{k}`={v}" for k, v in p["settings"].items()) or "-") + " |")
                for r in ob["ranges"]:
                    L.append(f"| | Z {r['min_z']:g}-{r['max_z']:g} | height range | - | " + ", ".join(f"`{k}`={v}" for k, v in r["settings"].items()) + " |")
            L.append("")
        L += ["## Process: every key in the preset chain", ""]
        if self.S.ok:
            L.append(f"Chain: {' <- '.join(self.S.proc['_chain'])}. Keys outside this chain take Bambu Studio internal defaults.")
            L += ["", "| Key | System value | Project value | Scope |", "|---|---|---|---|"]
            for k in sorted(x for x in self.S.proc if not x.startswith("_")):
                sv = self.S.proc[k]; ov = self.proc_over.get(k)
                fmt = lambda v: ("`" + ", ".join(v) + "`") if isinstance(v, list) else f"`{v}`"
                L.append(f"| {k} | {fmt(sv)} | {fmt(ov) if ov is not None else '='} | {'preset' if ov is not None else 'system'} |")
        else:
            L.append("NOT RUN: system presets were not resolved. Overrides only:")
            L += [f"- `{k}` = {','.join(v) if isinstance(v, list) else v}" for k, v in self.proc_over.items()]
        L += ["", "## Warnings", ""] + ([f"- {w}" for w in self.warnings] or ["- none"])
        open(os.path.join(self.out, f"{self.tag}_settings_report.md"), "w").write("\n".join(L) + "\n")

    def build(self):
        os.makedirs(os.path.join(self.out, "previews"))
        thumbs = [self._render(pl, i, 512) for i, pl in enumerate(self.plates, 1)]
        for i, pl in enumerate(self.plates, 1):
            self._render(pl, i, 1100, os.path.join(self.out, "previews", f"{self.tag}_plate{i}.png"))
        main = os.path.join(self.out, f"{self.tag}.3mf")
        self._pack(main, self.plates, True, thumbs)
        self._pack(os.path.join(self.out, f"{self.tag}_geometry_only.3mf"), self.plates, False, thumbs)
        p1 = dict(self.plates[0]); p1["objects"] = p1["objects"][:1]
        self._pack(os.path.join(self.out, f"{self.tag}_first_object.3mf"), [p1], True, thumbs[:1])
        files = self._presets()
        self._report(files)
        shutil.copy(os.path.join(HERE, "finalize.ps1"), os.path.join(self.out, f"finalize_{self.ver}.ps1"))
        spec_copy = os.path.join(self.out, f"{self.tag}_spec.json"); shutil.copy(self.spec_path, spec_copy)
        h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        man = {"skill": f"bambu-3mf {SKILL_VERSION}", "tag": self.tag, "printer": self.printer,
               "profiles_version": self.S.version if self.S.ok else None, "settings_validation": "run" if self.S.ok else "NOT RUN",
               "n_filaments": self.n_fil, "filaments": [{k: f[k] for k in ("slot", "preset", "color", "used")} | {"label": f.get("label", "")} for f in self.fils],
               "presets": files,
               "plates": [{"index": i, "name": pl["name"], "objects": [ob["name"] for ob in pl["objects"]],
                           "origin": [round(float(x), 3) for x in pl["origin"]]} for i, pl in enumerate(self.plates, 1)],
               "bed": [float(self.bed_w), float(self.bed_d), float(self.bed_h)],
               "files": {os.path.basename(p): h(p) for p in [main, spec_copy]}, "warnings": self.warnings}
        json.dump(man, open(os.path.join(self.out, "manifest.json"), "w"), indent=2)
        return self.out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("--out", default="/mnt/user-data/outputs"); ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    try:
        job = Job(a.spec, a.out, a.offline)
        out = job.build()
    except SpecError as e:
        print(f"SPEC ERROR: {e}"); sys.exit(2)
    print(f"built {out}")
    for w in job.warnings: print("WARN", w)
