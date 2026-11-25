#!/usr/bin/env python3
"""archmap.py - one architecture spec (JSON) -> draw.io + SVG/PNG previews + HTML package.

Commands
  check  SPEC                 Check the spec against the method rules. Exit 1 on errors.
  build  SPEC --out DIR       Write <slug>_architecture_<version>.drawio / .html and previews/*.svg|png.
                              Refuses to overwrite existing files (new version = new files);
                              --replace-draft rebuilds a status=Draft package not yet delivered.
  import DRAWIO --out SPEC    Turn an existing .drawio file into a draft spec for review/update.
  icons  [FILTER]             List icon keys (azure:*, aws:*, gcp:*, generic:*).

Spec format: see references/spec.md.
"""
import argparse, base64, html, json, os, re, shutil, subprocess, sys, urllib.parse, zlib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = json.load(open(os.path.join(HERE, "icons.json")))["icons"]

# ----------------------------------------------------------------- constants
CELL_W, CELL_H = 240, 170
ICON = 56
BOX_W, BOX_H = 150, 60
PAD, HEAD = 14, 24
TOP = 120          # room for title block
LEFT = 30

VIEW_TYPES = {
    "executive_outcome": "Executive outcome map",
    "system_context": "System context map",
    "logical_capability": "Logical capability map",
    "technology": "Technology map",
    "network_deployment": "Network and deployment map",
    "identity_security": "Identity and security map",
    "data_flow": "Data and knowledge flow map",
    "sequence": "Sequence map",
    "operations": "Observability and operations map",
    "resilience": "Resilience and recovery map",
}
VIEW_ORDER = ["executive_outcome", "system_context", "logical_capability", "technology",
              "identity_security", "network_deployment", "data_flow", "sequence",
              "operations", "resilience"]
EDGE_TYPES = {  # colour, dashed, width
    "request": ("#1F4E79", "", 1.5), "response": ("#1F4E79", "8 4", 1.5),
    "data": ("#2E7D32", "", 1.5), "event": ("#E65100", "8 4", 1.5),
    "command": ("#6A1B9A", "", 1.5), "admin": ("#6A1B9A", "8 4", 1.5),
    "replication": ("#00838F", "", 2.5), "telemetry": ("#757575", "2 3", 1.5),
}
BOUNDARY_KINDS = {  # stroke, fill, dashed
    "tenant": ("#37474F", "none", ""), "organization": ("#37474F", "none", ""),
    "management_group": ("#5D4037", "none", ""), "account": ("#B8860B", "none", ""),
    "subscription": ("#B8860B", "none", ""), "project": ("#B8860B", "none", ""),
    "resource_group": ("#757575", "none", "6 3"), "region": ("#00838F", "none", "6 3"),
    "availability_zone": ("#00838F", "none", "2 3"), "vnet": ("#6A1B9A", "#F7F2FB", ""),
    "subnet": ("#6A1B9A", "#FFFFFF", "6 3"), "trust": ("#C62828", "none", "10 4"),
    "application": ("#1565C0", "#F3F8FD", ""), "environment": ("#455A64", "none", ""),
    "external": ("#757575", "#F5F5F5", "6 3"), "on_premises": ("#4E342E", "#FBF8F6", ""),
    "layer": ("#90A4AE", "#FAFBFC", ""),
}
NODE_KINDS = {"actor", "service", "paas", "compute", "data", "external", "capability",
              "outcome", "network", "security", "endpoint", "note"}
STATUSES = ["Draft", "Proposed", "Under review", "Approved", "Implemented", "Superseded", "Retired"]
REGISTER_TYPES = ["Risk", "Assumption", "Dependency", "Constraint", "Open question",
                  "Decision required", "Proof of concept", "Security review", "Compliance review"]
VENDOR_COL = {"azure": "#0078D4", "gcp": "#4285F4", "generic": "#607D8B"}
KIND_FILL = {"capability": "#E3F2FD", "outcome": "#E8F5E9", "actor": "#FFFFFF", "note": "#FFFDE7",
             "external": "#F5F5F5", "data": "#FFF3E0", "security": "#FFEBEE"}
DATA_FLOW_FIELDS = ["flow", "data_type", "from", "to", "protocol", "classification", "owner",
                    "storage", "retention", "encryption"]
ADR_FIELDS = ["id", "decision", "requirement", "options", "selected", "reason", "tradeoffs", "risks",
              "assumptions", "evidence", "owner", "date", "review_date"]
REG_FIELDS = ["id", "type", "description", "impact", "owner", "target_date", "validation", "status"]
META_FIELDS = ["workload", "version", "status", "date", "owner", "reviewers", "environment"]
VALIDATION_QUESTIONS = [
    "Does the architecture answer the intended stakeholder question?", "Is the scope clear?",
    "Are all users, systems, and dependencies represented?", "Are the arrows directional and labeled?",
    "Are trust boundaries visible?", "Is the deployment model technically accurate?",
    "Are identity and authorization flows clear?", "Are data flows and classifications documented?",
    "Are failure paths represented?", "Are monitoring and support responsibilities clear?",
    "Are major decisions supported by requirements?", "Are risks, assumptions, and unknowns visible?",
    "Does the architecture reflect the actual implementation?", "What evidence is still needed before approval?"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "workload"


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# ----------------------------------------------------------------- layout
def node_size(n):
    if n.get("icon") and ICONS.get(n["icon"], {}).get("kind") in ("image", "aws4"):
        return ICON, ICON
    return n.get("w", BOX_W), n.get("h", BOX_H)


def layout_view(v):
    """Return dict id -> (x, y, w, h) for nodes and boundaries (absolute)."""
    geo = {}
    for n in v.get("nodes", []):
        w, h = node_size(n)
        if "x" in n and "y" in n:
            x, y = n["x"], n["y"]
        else:
            col, row = n.get("col", 0), n.get("row", 0)
            x = LEFT + PAD * 6 + col * CELL_W + (CELL_W - w) / 2
            y = TOP + PAD * 6 + row * CELL_H + (CELL_H - h - (30 if h == ICON else 0)) / 2
        geo[n["id"]] = (x, y, w, h)
    bounds = {b["id"]: b for b in v.get("boundaries", [])}
    kids = {b: [] for b in bounds}
    for n in v.get("nodes", []):
        if n.get("in") in kids:
            kids[n["in"]].append(("n", n["id"], n))
    for b in bounds.values():
        if b.get("parent") in kids:
            kids[b["parent"]].append(("b", b["id"], b))

    def box(bid, seen=()):
        if bid in geo:
            return geo[bid]
        if bid in seen:
            return None
        xs = []
        for t, cid, obj in kids[bid]:
            if t == "n":
                x, y, w, h = geo[cid]
                extra = 30 if h == ICON else 0  # label under icon
                xs.append((x - 30 if h == ICON else x, y, x + w + (30 if h == ICON else 0), y + h + extra))
            else:
                g = box(cid, seen + (bid,))
                if g:
                    xs.append((g[0], g[1], g[0] + g[2], g[1] + g[3]))
        if not xs:
            return None
        x0 = min(a[0] for a in xs) - PAD; y0 = min(a[1] for a in xs) - PAD - HEAD
        x1 = max(a[2] for a in xs) + PAD; y1 = max(a[3] for a in xs) + PAD
        b = bounds[bid]
        need = 6.6 * len(f"{b.get('label', '')}  ({b.get('kind', '')})") + 20
        x1 = max(x1, x0 + need)
        geo[bid] = (x0, y0, x1 - x0, y1 - y0)
        return geo[bid]

    for bid in bounds:
        box(bid)
    return geo


def depth(bounds, bid):
    d, cur, seen = 0, bounds.get(bid), set()
    while cur and cur.get("parent") and cur["parent"] not in seen:
        seen.add(cur["parent"]); d += 1; cur = bounds.get(cur["parent"])
    return d


def overlaps(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def ancestors(bounds, bid):
    out, cur = set(), bounds.get(bid)
    while cur and cur.get("parent") and cur["parent"] not in out:
        out.add(cur["parent"]); cur = bounds.get(cur["parent"])
    return out


# ----------------------------------------------------------------- check
def check(spec):
    errs, warns = [], []
    E, W = errs.append, warns.append
    meta = spec.get("meta", {})
    for f in META_FIELDS:
        if not meta.get(f):
            E(f"meta.{f} is missing (section 8: every map carries it)")
    if meta.get("version") and not re.fullmatch(r"\d+\.\d+(\.\d+)?", str(meta["version"])):
        E(f"meta.version '{meta['version']}' is not semver (e.g. 0.1, 1.0, 1.2.0)")
    if meta.get("status") and meta["status"] not in STATUSES:
        E(f"meta.status '{meta['status']}' not in {STATUSES}")
    q = meta.get("question", {})
    for f in ["audience", "system", "determine", "scope"]:
        if not q.get(f):
            E(f"meta.question.{f} is missing (section 1: architecture question)")
    inp = spec.get("inputs", {})
    for f in ["business_outcome", "actors", "scope_in", "scope_out", "constraints", "quality_targets",
              "decisions", "unknowns"]:
        if f not in inp:
            W(f"inputs.{f} not recorded (section 1). Ask the user or log an Open question.")
    views = spec.get("views", [])
    if not views:
        E("no views")
    vids = set()
    reg_text = json.dumps(spec.get("register", []))
    for v in views:
        vid = v.get("id", "?")
        if vid in vids:
            E(f"view id '{vid}' repeated")
        vids.add(vid)
        t = v.get("type")
        if t not in VIEW_TYPES:
            E(f"[{vid}] type '{t}' not in {list(VIEW_TYPES)}")
        if not v.get("question"):
            E(f"[{vid}] no 'question' (each view answers one stakeholder question)")
        if t == "sequence":
            parts = {p["id"] for p in v.get("participants", [])}
            for i, s in enumerate(v.get("steps", []), 1):
                for end in ("from", "to"):
                    if s.get(end) not in parts:
                        E(f"[{vid}] step {i}: '{s.get(end)}' is not a participant")
                if not s.get("label"):
                    E(f"[{vid}] step {i}: no label")
                if not s.get("protocol"):
                    E(f"[{vid}] step {i}: no protocol (section 2.8: label direction and protocol)")
            continue
        bounds = {b["id"]: b for b in v.get("boundaries", [])}
        for b in bounds.values():
            if b.get("kind") not in BOUNDARY_KINDS:
                E(f"[{vid}] boundary '{b['id']}' kind '{b.get('kind')}' is not a meaningful boundary kind")
            if b.get("parent") and b["parent"] not in bounds:
                E(f"[{vid}] boundary '{b['id']}' parent '{b['parent']}' missing")
            if not b.get("label"):
                E(f"[{vid}] boundary '{b['id']}' has no label")
        nids = {}
        for n in v.get("nodes", []):
            if n["id"] in nids:
                E(f"[{vid}] node id '{n['id']}' repeated")
            nids[n["id"]] = n
            if not n.get("label"):
                E(f"[{vid}] node '{n['id']}' has no label (name goes next to every icon)")
            if n.get("in") and n["in"] not in bounds:
                E(f"[{vid}] node '{n['id']}' in unknown boundary '{n['in']}'")
            if n.get("icon") and n["icon"] not in ICONS:
                E(f"[{vid}] node '{n['id']}' icon '{n['icon']}' unknown. Run `archmap.py icons`. "
                  "Omit icon for a plain labelled box; never borrow another product's icon.")
            if n.get("kind") and n["kind"] not in NODE_KINDS:
                W(f"[{vid}] node '{n['id']}' kind '{n['kind']}' not in {sorted(NODE_KINDS)}")
            if t == "technology" and n.get("kind") not in ("actor", "external", "note") and not n.get("requirement"):
                E(f"[{vid}] node '{n['id']}' has no 'requirement' (2.4: tie every service to a requirement or ADR)")
            if t in ("logical_capability", "executive_outcome") and n.get("icon") and not n["icon"].startswith("generic:"):
                W(f"[{vid}] node '{n['id']}' uses a product icon in a {t} view; use functional names here")
            if n.get("kind") == "paas" and n.get("in"):
                chain = {n["in"]} | ancestors(bounds, n["in"])
                if any(bounds[c].get("kind") == "subnet" for c in chain if c in bounds) and not n.get("vnet_injected"):
                    E(f"[{vid}] PaaS node '{n['id']}' is drawn inside a subnet. Put the private endpoint in the "
                      "subnet and the PaaS resource outside (2.5). Set vnet_injected:true only if it truly is.")
            if n.get("assumption") and n["id"] not in reg_text and n.get("label", "") not in reg_text:
                E(f"[{vid}] node '{n['id']}' is marked assumption but no register item mentions it (section 6)")
        pairs = set()
        for i, e in enumerate(v.get("edges", []), 1):
            tag = f"[{vid}] edge {i} {e.get('from')}->{e.get('to')}"
            if e.get("from") not in nids or e.get("to") not in nids:
                E(f"{tag}: endpoint is not a node in this view")
            if not e.get("label"):
                E(f"{tag}: no label (every connection states a relationship)")
            if e.get("type") not in EDGE_TYPES:
                E(f"{tag}: type '{e.get('type')}' not in {list(EDGE_TYPES)}")
            if e.get("bidirectional") or "↔" in str(e.get("label", "")) or "<->" in str(e.get("label", "")):
                E(f"{tag}: two-way arrow. Split into one edge per direction (section 3)")
            if e.get("type") in ("request", "data", "command", "replication") and not e.get("protocol"):
                W(f"{tag}: no protocol; add one unless the relationship is obvious")
            pairs.add((e.get("from"), e.get("to")))
        geo0 = layout_view(v)
        for i, e in enumerate(v.get("edges", []), 1):
            if e.get("from") in geo0 and e.get("to") in geo0:
                x0, y0, x1, y1 = edge_points(geo0, e, False)
                if abs(x1 - x0) >= abs(y1 - y0) and 5.6 * len(edge_label(e)) > ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 - 10:
                    W(f"[{vid}] edge {i} {e['from']}->{e['to']}: label longer than the edge; leave an empty col/row "
                      "between the nodes or shorten the label")
        if t == "identity_security" and not any(b.get("kind") == "trust" for b in bounds.values()):
            E(f"[{vid}] identity/security view has no 'trust' boundary (2.6: label each trust boundary)")
        if t == "network_deployment":
            kinds = {b.get("kind") for b in bounds.values()}
            if not kinds & {"vnet", "region"}:
                W(f"[{vid}] network view shows no region or vnet boundary")
        # layout checks
        geo = layout_view(v)
        blist = list(bounds)
        for i, a in enumerate(blist):
            for b in blist[i + 1:]:
                if a in geo and b in geo and a not in ancestors(bounds, b) and b not in ancestors(bounds, a):
                    if overlaps(geo[a], geo[b]):
                        E(f"[{vid}] boundaries '{a}' and '{b}' overlap on the canvas. Leave an empty col/row "
                          "between sibling boundaries, or give explicit x/y.")
        for b in blist:
            if b not in geo:
                W(f"[{vid}] boundary '{b}' contains nothing and will not be drawn")
        nl = list(nids)
        for i, a in enumerate(nl):
            for b in nl[i + 1:]:
                if overlaps(geo[a], geo[b]):
                    E(f"[{vid}] nodes '{a}' and '{b}' overlap (same col/row?)")
        for nid, n in nids.items():
            mine = ({n["in"]} | ancestors(bounds, n["in"])) if n.get("in") else set()
            for bid in bounds:
                if bid in geo and bid not in mine and overlaps(geo[nid], geo[bid]):
                    E(f"[{vid}] node '{nid}' sits on top of boundary '{bid}' it does not belong to")
    for i, d in enumerate(spec.get("data_flows", []), 1):
        miss = [f for f in DATA_FLOW_FIELDS if not d.get(f)]
        if miss:
            E(f"data_flows[{i}] missing {miss} (2.7)")
    for d in spec.get("decisions", []):
        miss = [f for f in ADR_FIELDS if not d.get(f)]
        if miss:
            W(f"decision {d.get('id', '?')} missing {miss} (section 4). Use 'TBD' + a register item if unknown.")
    for r in spec.get("register", []):
        if r.get("type") not in REGISTER_TYPES:
            E(f"register {r.get('id', '?')} type '{r.get('type')}' not in {REGISTER_TYPES}")
        miss = [f for f in REG_FIELDS if not r.get(f)]
        if miss:
            W(f"register {r.get('id', '?')} missing {miss}")
    if spec.get("views") and not spec.get("register"):
        W("no register. Record risks, assumptions and open questions (section 6)")
    return errs, warns


# ----------------------------------------------------------------- draw.io
def style_for_node(n):
    ic = ICONS.get(n.get("icon", ""))
    base = "html=1;whiteSpace=wrap;fontSize=11;"
    if ic and ic["kind"] == "image":
        return ("image;aspect=fixed;" + base + "verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=#ffffff;"
                "image=" + ic["image"] + ";")
    if ic and ic["kind"] == "aws4":
        return ("sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;"
                "verticalAlign=top;align=center;aspect=fixed;labelBackgroundColor=#ffffff;" + base +
                f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{ic['res']};fillColor={ic['fill']};")
    fill = KIND_FILL.get(n.get("kind"), "#FFFFFF")
    shape = ic["style"] if ic else "rounded=1;"
    dash = "dashed=1;" if n.get("assumption") else ""
    return f"{shape}{base}fillColor={fill};strokeColor=#546E7A;{dash}"


def edge_label(e):
    s = (f"{e['step']}. " if e.get("step") else "") + str(e.get("label", ""))
    if e.get("protocol"):
        s += f" [{e['protocol']}]"
    return s


def title_html(spec, v):
    m = spec["meta"]
    rev = ", ".join(m.get("reviewers", [])) if isinstance(m.get("reviewers"), list) else m.get("reviewers", "")
    return (f"<b style='font-size:15px'>{esc(v.get('title') or VIEW_TYPES.get(v['type'], ''))}</b><br>"
            f"<span style='font-size:10px'>Workload: {esc(m.get('workload'))} | Type: {esc(VIEW_TYPES.get(v['type'], ''))} | "
            f"Env: {esc(m.get('environment'))} | v{esc(m.get('version'))} | Updated: {esc(m.get('date'))} | "
            f"Owner: {esc(m.get('owner'))} | Reviewers: {esc(rev)} | Status: {esc(m.get('status'))}<br>"
            f"<i>Question: {esc(v.get('question'))}</i></span>")


class Cells:
    def __init__(self):
        self.out, self.n = [], 2

    def nid(self):
        self.n += 1
        return f"c{self.n}"

    def vertex(self, value, style, x, y, w, h, cid=None):
        cid = cid or self.nid()
        self.out.append(f'<mxCell id="{esc(cid)}" value="{esc(value)}" style="{esc(style)}" vertex="1" parent="1">'
                        f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>')
        return cid

    def edge(self, value, style, src=None, tgt=None, p0=None, p1=None):
        cid = self.nid()
        a = (f' source="{esc(src)}"' if src else "") + (f' target="{esc(tgt)}"' if tgt else "")
        pts = ""
        if p0:
            pts += f'<mxPoint x="{p0[0]:.0f}" y="{p0[1]:.0f}" as="sourcePoint"/>'
        if p1:
            pts += f'<mxPoint x="{p1[0]:.0f}" y="{p1[1]:.0f}" as="targetPoint"/>'
        self.out.append(f'<mxCell id="{cid}" value="{esc(value)}" style="{esc(style)}" edge="1" parent="1"{a}>'
                        f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')


def edge_style(t, orth=True):
    col, dash, w = EDGE_TYPES.get(t, ("#000000", "", 1.5))
    s = (f"html=1;rounded=1;endArrow=block;endFill=1;strokeColor={col};strokeWidth={w};fontSize=10;"
         "labelBackgroundColor=#ffffff;fontColor=#263238;")
    if orth:
        s += "edgeStyle=orthogonalEdgeStyle;"
    if dash:
        s += f"dashed=1;dashPattern={dash};"
    return s


def seq_geometry(v):
    parts = v.get("participants", [])
    cx = {p["id"]: LEFT + 100 + i * 200 for i, p in enumerate(parts)}
    steps = v.get("steps", [])
    head_y = TOP + 10
    life_end = head_y + 60 + (len(steps) + 1) * 46
    return parts, cx, steps, head_y, life_end


def drawio_page(spec, v, page_no):
    c = Cells()
    c.vertex(title_html(spec, v), "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;", LEFT, 20, 900, 80)
    used = set()
    if v["type"] == "sequence":
        parts, cx, steps, hy, le = seq_geometry(v)
        for p in parts:
            c.vertex(p.get("label", p["id"]), "rounded=1;html=1;whiteSpace=wrap;fillColor=#ECEFF1;strokeColor=#546E7A;fontSize=11;fontStyle=1;",
                     cx[p["id"]] - 75, hy, 150, 50)
            c.edge("", "html=1;endArrow=none;dashed=1;strokeColor=#90A4AE;archmap=lifeline;", p0=(cx[p["id"]], hy + 50), p1=(cx[p["id"]], le))
        for i, s in enumerate(steps, 1):
            y = hy + 60 + i * 46
            t = s.get("type", "request"); used.add(t)
            x0, x1 = cx.get(s["from"], 0), cx.get(s["to"], 0)
            if x0 == x1:
                x1 = x0 + 60
            c.edge(f"{i}. {s.get('label', '')} [{s.get('protocol', '')}]", edge_style(t, orth=False) + "verticalAlign=bottom;",
                   p0=(x0, y), p1=(x1, y))
        right = max(cx.values(), default=0) + 140
    else:
        geo = layout_view(v)
        bounds = {b["id"]: b for b in v.get("boundaries", [])}
        for bid in sorted([b for b in bounds if b in geo], key=lambda b: depth(bounds, b)):
            b = bounds[bid]; x, y, w, h = geo[bid]
            st, fi, da = BOUNDARY_KINDS.get(b.get("kind"), ("#999999", "none", ""))
            style = (f"rounded=0;html=1;whiteSpace=wrap;fillColor={fi};strokeColor={st};fontColor={st};verticalAlign=top;"
                     f"align=left;spacingLeft=8;fontSize=11;fontStyle=1;container=0;strokeWidth=1.5;")
            if da:
                style += f"dashed=1;dashPattern={da};"
            c.vertex(f"{b['label']}  ({b.get('kind', '').replace('_', ' ')})", style, x, y, w, h, cid=f"b_{bid}")
        for n in v.get("nodes", []):
            x, y, w, h = geo[n["id"]]
            lab = esc(n["label"] + (" (assumed)" if n.get("assumption") else ""))
            if n.get("detail"):
                lab += f"<br><span style='font-size:9px;color:#546E7A'>{esc(n['detail'])}</span>"
            c.vertex(lab, style_for_node(n), x, y, w, h, cid=f"n_{n['id']}")
        pairs = {(e.get("from"), e.get("to")) for e in v.get("edges", [])}
        for e in v.get("edges", []):
            used.add(e.get("type"))
            st = edge_style(e.get("type"))
            if (e["to"], e["from"]) in pairs:
                a, b = geo[e["from"]], geo[e["to"]]
                first = e["from"] < e["to"]; k = 0.3 if first else 0.7
                if abs((b[0] + b[2] / 2) - (a[0] + a[2] / 2)) >= abs((b[1] + b[3] / 2) - (a[1] + a[3] / 2)):
                    st += f"exitX={1 if b[0] > a[0] else 0};exitY={k};entryX={0 if b[0] > a[0] else 1};entryY={k};"
                else:
                    st += f"exitY={1 if b[1] > a[1] else 0};exitX={k};entryY={0 if b[1] > a[1] else 1};entryX={k};"
            c.edge(esc(edge_label(e)), st, src=f"n_{e['from']}", tgt=f"n_{e['to']}")
        right = max([g[0] + g[2] for g in geo.values()] + [600]) + 40
    # legend
    used = [t for t in EDGE_TYPES if t in used]
    if used:
        c.vertex("<b>Legend</b>", "text;html=1;align=left;verticalAlign=top;fontSize=11;", right, TOP, 160, 20)
        for i, t in enumerate(used):
            y = TOP + 30 + i * 22
            c.edge("", edge_style(t, orth=False) + "archmap=legend;", p0=(right, y), p1=(right + 50, y))
            c.vertex(t, "text;html=1;align=left;verticalAlign=middle;fontSize=10;", right + 58, y - 9, 100, 18)
    notes = v.get("notes") or []
    if notes:
        c.vertex("<b>Notes</b><br>" + "<br>".join("• " + esc(x) for x in notes),
                 "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=10;fillColor=#FFFDE7;strokeColor=#FBC02D;",
                 right, TOP + 40 + len(used) * 22, 260, 30 + 16 * len(notes))
    name = f"{page_no} {v.get('title') or VIEW_TYPES.get(v['type'])}"
    body = "".join(c.out)
    return (f'<diagram id="{esc(v["id"])}" name="{esc(name)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" '
            f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" '
            f'pageHeight="1169" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}'
            f'</root></mxGraphModel></diagram>')


def ordered_views(spec):
    return sorted(spec["views"], key=lambda v: (VIEW_ORDER.index(v["type"]) if v["type"] in VIEW_ORDER else 99))


def write_drawio(spec, path):
    pages = [drawio_page(spec, v, i) for i, v in enumerate(ordered_views(spec), 1)]
    xml = f'<mxfile host="archmap" version="{esc(spec["meta"]["version"])}">' + "".join(pages) + "</mxfile>"
    ET.fromstring(xml)  # well-formed check
    open(path, "w").write(xml)


# ----------------------------------------------------------------- SVG preview
def clip(box, tx, ty):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    s = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    return cx + dx * s, cy + dy * s


def edge_points(geo, e, paired):
    a, b = geo[e["from"]], geo[e["to"]]
    x0, y0 = clip(a, b[0] + b[2] / 2, b[1] + b[3] / 2); x1, y1 = clip(b, a[0] + a[2] / 2, a[1] + a[3] / 2)
    if paired:
        dx, dy = x1 - x0, y1 - y0; L = max((dx * dx + dy * dy) ** 0.5, 1)
        ox, oy = dy / L * 7, -dx / L * 7
        x0, y0, x1, y1 = x0 + ox, y0 + oy, x1 + ox, y1 + oy
    return x0, y0, x1, y1


def svg_view(spec, v):
    o = []
    m = spec["meta"]
    used = set()
    if v["type"] == "sequence":
        parts, cx, steps, hy, le = seq_geometry(v)
        W_ = max(cx.values(), default=400) + 340; H_ = le + 40
        for p in parts:
            x = cx[p["id"]]
            o.append(f'<rect x="{x-75}" y="{hy}" width="150" height="50" rx="8" fill="#ECEFF1" stroke="#546E7A"/>'
                     f'<text x="{x}" y="{hy+29}" text-anchor="middle" font-weight="bold">{esc(p.get("label", p["id"]))}</text>'
                     f'<line x1="{x}" y1="{hy+50}" x2="{x}" y2="{le}" stroke="#90A4AE" stroke-dasharray="6 4"/>')
        for i, s in enumerate(steps, 1):
            y = hy + 60 + i * 46; t = s.get("type", "request"); used.add(t)
            col, dash, w = EDGE_TYPES.get(t, ("#000", "", 1.5))
            x0, x1 = cx.get(s["from"], 0), cx.get(s["to"], 0)
            if x0 == x1:
                x1 = x0 + 60
            o.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{col}" stroke-width="{w}" '
                     f'stroke-dasharray="{dash}" marker-end="url(#a_{t})"/>'
                     f'<text x="{(x0+x1)/2}" y="{y-5}" text-anchor="middle" font-size="10">{i}. {esc(s.get("label"))} [{esc(s.get("protocol"))}]</text>')
        right = max(cx.values(), default=0) + 140
    else:
        geo = layout_view(v)
        bounds = {b["id"]: b for b in v.get("boundaries", [])}
        for bid in sorted([b for b in bounds if b in geo], key=lambda b: depth(bounds, b)):
            b = bounds[bid]; x, y, w, h = geo[bid]
            st, fi, da = BOUNDARY_KINDS.get(b.get("kind"), ("#999", "none", ""))
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fi}" stroke="{st}" stroke-width="1.5" stroke-dasharray="{da}"/>'
                     f'<text x="{x+8}" y="{y+16}" fill="{st}" font-weight="bold" font-size="11">{esc(b["label"])} ({esc(b.get("kind","").replace("_"," "))})</text>')
        nodes = {n["id"]: n for n in v.get("nodes", [])}
        pairs = {(e.get("from"), e.get("to")) for e in v.get("edges", [])}
        lines = []
        for e in v.get("edges", []):
            if e.get("from") not in geo or e.get("to") not in geo:
                continue
            t = e.get("type"); used.add(t)
            col, dash, w = EDGE_TYPES.get(t, ("#000", "", 1.5))
            x0, y0, x1, y1 = edge_points(geo, e, (e["to"], e["from"]) in pairs)
            o.append(f'<line x1="{x0:.0f}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y1:.0f}" stroke="{col}" stroke-width="{w}" '
                     f'stroke-dasharray="{dash}" marker-end="url(#a_{t})"/>')
            lines.append((e, x0, y0, x1, y1))
        for e, x0, y0, x1, y1 in lines:  # labels on top, pushed to the side of the line
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            dx, dy = x1 - x0, y1 - y0; L = max((dx * dx + dy * dy) ** 0.5, 1)
            nx, ny = dy / L, -dx / L
            if (e["to"], e["from"]) in pairs:
                mx, my = mx + nx * 9, my + ny * 9
            elif abs(dx) >= abs(dy):
                my -= 9
            lab = esc(edge_label(e)); tw = 5.6 * len(edge_label(e))
            o.append(f'<rect x="{mx-tw/2-2:.0f}" y="{my-9:.0f}" width="{tw+4:.0f}" height="13" fill="#fff" opacity="0.9"/>'
                     f'<text x="{mx:.0f}" y="{my+1:.0f}" text-anchor="middle" font-size="10">{lab}</text>')
        for n in nodes.values():
            x, y, w, h = geo[n["id"]]
            ic = ICONS.get(n.get("icon", ""), {})
            lab = esc(n["label"] + (" (assumed)" if n.get("assumption") else ""))
            if ic.get("kind") in ("image", "aws4"):
                vendor = n["icon"].split(":")[0]
                col = ic.get("fill") or VENDOR_COL.get(vendor, "#607D8B")
                if ic.get("image", "").startswith("data:"):
                    o.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="data:image/svg+xml;base64,{ic["image"][19:]}"/>')
                else:
                    abbr = "".join(p[0] for p in n["icon"].split(":")[1].split("-"))[:3].upper()
                    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{col}"/>'
                             f'<text x="{x+w/2}" y="{y+h/2+5}" text-anchor="middle" fill="#fff" font-weight="bold" font-size="14">{esc(abbr)}</text>')
                o.append(f'<text x="{x+w/2}" y="{y+h+14}" text-anchor="middle" font-size="11">{lab}</text>')
                if n.get("detail"):
                    o.append(f'<text x="{x+w/2}" y="{y+h+27}" text-anchor="middle" font-size="9" fill="#546E7A">{esc(n["detail"])}</text>')
            else:
                fill = KIND_FILL.get(n.get("kind"), "#FFFFFF")
                da = ' stroke-dasharray="5 3"' if n.get("assumption") else ""
                shape = n.get("icon", "")
                if shape in ("generic:database", "generic:storage"):
                    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{w/2}" ry="10" fill="{fill}" stroke="#546E7A"{da}/>')
                elif shape in ("generic:user", "generic:users"):
                    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" fill="#fff" stroke="#546E7A"{da}/>')
                else:
                    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="#546E7A"{da}/>')
                o.append(f'<text x="{x+w/2}" y="{y+h/2+(0 if n.get("detail") else 4)}" text-anchor="middle" font-size="11">{lab}</text>')
                if n.get("detail"):
                    o.append(f'<text x="{x+w/2}" y="{y+h/2+16}" text-anchor="middle" font-size="9" fill="#546E7A">{esc(n["detail"])}</text>')
        right = max([g[0] + g[2] for g in geo.values()] + [600]) + 40
        W_ = right + 300
        H_ = max([g[1] + g[3] for g in geo.values()] + [400]) + 60
    used = [t for t in EDGE_TYPES if t in used]
    o.append(f'<text x="{right}" y="{TOP+12}" font-weight="bold" font-size="11">Legend</text>')
    for i, t in enumerate(used):
        col, dash, w = EDGE_TYPES[t]; y = TOP + 30 + i * 22
        o.append(f'<line x1="{right}" y1="{y}" x2="{right+50}" y2="{y}" stroke="{col}" stroke-width="{w}" stroke-dasharray="{dash}" marker-end="url(#a_{t})"/>'
                 f'<text x="{right+58}" y="{y+4}" font-size="10">{t}</text>')
    notes = v.get("notes") or []
    ny = TOP + 50 + len(used) * 22
    for i, nt in enumerate(notes):
        o.append(f'<text x="{right}" y="{ny + i*15}" font-size="10">• {esc(nt)[:60]}</text>')
    H_ = max(H_, ny + 15 * len(notes) + 20)
    rev = ", ".join(m.get("reviewers", [])) if isinstance(m.get("reviewers"), list) else m.get("reviewers", "")
    head = (f'<text x="{LEFT}" y="38" font-size="16" font-weight="bold">{esc(v.get("title") or VIEW_TYPES.get(v["type"]))}</text>'
            f'<text x="{LEFT}" y="58" font-size="10">Workload: {esc(m.get("workload"))} | Type: {esc(VIEW_TYPES.get(v["type"]))} | '
            f'Env: {esc(m.get("environment"))} | v{esc(m.get("version"))} | Updated: {esc(m.get("date"))} | Owner: {esc(m.get("owner"))} | '
            f'Reviewers: {esc(rev)} | Status: {esc(m.get("status"))}</text>'
            f'<text x="{LEFT}" y="76" font-size="10" font-style="italic">Question: {esc(v.get("question"))}</text>')
    markers = "".join(f'<marker id="a_{t}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                      f'<path d="M0,0 L10,5 L0,10 z" fill="{c[0]}"/></marker>' for t, c in EDGE_TYPES.items())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_:.0f} {H_:.0f}" width="{W_:.0f}" height="{H_:.0f}" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif"><defs>{markers}</defs>'
            f'<rect width="100%" height="100%" fill="#fff"/>{head}{"".join(o)}</svg>')


# ----------------------------------------------------------------- HTML
CSS = """body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:0;color:#263238;background:#fafafa}
header{background:#263238;color:#fff;padding:20px 32px}header h1{margin:0 0 6px;font-size:22px}
.meta{font-size:13px;opacity:.9}main{padding:16px 32px;max-width:1500px}nav{columns:3;font-size:13px;margin:8px 0 20px}
nav a{color:#1565C0;text-decoration:none;display:block}section{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:16px 20px;margin:16px 0}
h2{font-size:18px;margin:0 0 8px;border-bottom:2px solid #eceff1;padding-bottom:6px}h3{font-size:15px;margin:14px 0 6px}
.q{background:#E3F2FD;border-left:4px solid #1565C0;padding:10px 14px;font-size:15px}
.diagram{overflow:auto;border:1px solid #eceff1;margin:10px 0}.diagram svg{max-width:100%;height:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:6px 0}th,td{border:1px solid #e0e0e0;padding:5px 7px;text-align:left;vertical-align:top}
th{background:#ECEFF1}.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}
.met,.yes{background:#C8E6C9}.gap,.no,.high{background:#FFCDD2}.unknown,.partial,.medium{background:#FFF9C4}.low{background:#E0E0E0}
ul{margin:4px 0 4px 18px;padding:0}.small{font-size:12px;color:#546E7A}@media print{section{break-inside:avoid}nav{display:none}}"""


def table(rows, cols, heads=None):
    if not rows:
        return "<p class='small'>None recorded.</p>"
    h = "".join(f"<th>{esc(x)}</th>" for x in (heads or cols))
    body = ""
    for r in rows:
        cells = []
        for c in cols:
            val = r.get(c, "")
            if isinstance(val, list):
                val = "; ".join(map(str, val))
            cls = str(val).lower() if c in ("status", "result", "severity") else ""
            cells.append(f"<td><span class='pill {esc(cls)}'>{esc(val)}</span></td>" if cls in
                         ("met", "gap", "unknown", "yes", "no", "partial", "high", "medium", "low") else f"<td>{esc(val)}</td>")
        body += "<tr>" + "".join(cells) + "</tr>"
    return f"<table><tr>{h}</tr>{body}</table>"


def lst(x):
    if not x:
        return "<span class='small'>Not recorded</span>"
    if isinstance(x, str):
        return esc(x)
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in x) + "</ul>"


def write_html(spec, path, svgs):
    m, q, inp = spec["meta"], spec["meta"].get("question", {}), spec.get("inputs", {})
    secs, nav = [], []

    def sec(sid, title, body):
        nav.append(f"<a href='#{sid}'>{esc(title)}</a>")
        secs.append(f"<section id='{sid}'><h2>{esc(title)}</h2>{body}</section>")

    sec("question", "Architecture question",
        f"<p class='q'>For <b>{esc(q.get('audience'))}</b>, this architecture map explains <b>{esc(q.get('system'))}</b> "
        f"so they can determine <b>{esc(q.get('determine'))}</b>, within <b>{esc(q.get('scope'))}</b>.</p>"
        + table([{"Input": k.replace('_', ' ').capitalize(), "Value": v} for k, v in
                 [(k, inp.get(k)) for k in ["business_outcome", "actors", "scope_in", "scope_out", "constraints",
                                            "quality_targets", "decisions", "unknowns"]]], ["Input", "Value"]))
    if spec.get("review"):
        r = spec["review"]
        sec("review", "Review findings",
            f"<p>{esc(r.get('summary', ''))}</p><p class='small'>Source: {esc(r.get('source', ''))}</p>"
            + table(r.get("findings", []), ["id", "severity", "rule", "location", "finding", "fix"]))
    for i, v in enumerate(ordered_views(spec), 1):
        body = (f"<p class='small'><b>Question answered:</b> {esc(v.get('question'))}</p>"
                f"<div class='diagram'>{svgs[v['id']]}</div>")
        if v.get("notes"):
            body += "<h3>Notes</h3>" + lst(v["notes"])
        if v["type"] == "sequence":
            body += table([{"#": j, "From": s["from"], "To": s["to"], "Interaction": s.get("label"),
                            "Protocol": s.get("protocol"), "Type": s.get("type", "request")}
                           for j, s in enumerate(v.get("steps", []), 1)], ["#", "From", "To", "Interaction", "Protocol", "Type"])
        if v["type"] == "resilience" and v.get("targets"):
            body += table([{"Item": k.replace('_', ' '), "Value": val} for k, val in v["targets"].items()], ["Item", "Value"])
        sec(f"v-{v['id']}", f"{i}. {v.get('title') or VIEW_TYPES[v['type']]}", body)
    if spec.get("data_flows"):
        sec("flows", "Data flow register", table(spec["data_flows"], DATA_FLOW_FIELDS,
            ["Flow", "Data type", "From", "To", "Protocol", "Classification", "Owner", "Storage", "Retention", "Encryption"]))
    if spec.get("decisions"):
        sec("adr", "Architecture decisions", "".join(
            f"<h3>{esc(d.get('id'))}: {esc(d.get('decision'))}</h3>" + table([d], ADR_FIELDS[2:],
                ["Requirement", "Options considered", "Selected", "Reason", "Tradeoffs", "Risks", "Assumptions",
                 "Evidence required", "Owner", "Date", "Review date"]) for d in spec["decisions"]))
    if spec.get("waf"):
        w = spec["waf"]
        body = f"<p class='small'>Framework: {esc(w.get('framework', ''))}</p>"
        for pillar, items in w.items():
            if pillar == "framework":
                continue
            body += f"<h3>{esc(pillar.replace('_', ' ').title())}</h3>" + table(items, ["q", "a", "status"], ["Question", "Answer / evidence", "Status"])
        sec("waf", "Well-Architected review", body)
    sec("register", "Risks, assumptions, dependencies and open questions", table(spec.get("register", []), REG_FIELDS,
        ["ID", "Type", "Description", "Architecture impact", "Owner", "Target date", "Validation", "Status"]))
    if spec.get("validation"):
        sec("validation", "Validation checklist", table(spec["validation"], ["n", "question", "result", "evidence"],
            ["#", "Question", "Result", "Evidence"]))
    if spec.get("related") or spec.get("changelog"):
        sec("maint", "Maintenance", "<h3>Related documents</h3>" + lst(spec.get("related")) + "<h3>Change log</h3>"
            + table(spec.get("changelog", []), ["version", "date", "change"]))
    rev = ", ".join(m.get("reviewers", [])) if isinstance(m.get("reviewers"), list) else m.get("reviewers", "")
    doc = (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{esc(m['workload'])} architecture v{esc(m['version'])}</title><style>{CSS}</style></head><body>"
           f"<header><h1>{esc(m['workload'])} — architecture package</h1><div class='meta'>Version {esc(m['version'])} · "
           f"{esc(m.get('status'))} · {esc(m.get('environment'))} · Updated {esc(m.get('date'))} · Owner {esc(m.get('owner'))} · "
           f"Reviewers {esc(rev)}</div></header><main><nav>{''.join(nav)}</nav>{''.join(secs)}"
           f"<p class='small'>The maps show what connects. The decisions explain why. The Well-Architected review tests whether "
           f"the choices are defensible.</p></main></body></html>")
    open(path, "w").write(doc)


# ----------------------------------------------------------------- import
def decode_diagram(d):
    if len(d) and d.find("mxGraphModel") is not None:
        return d.find("mxGraphModel")
    txt = (d.text or "").strip()
    if not txt:
        return None
    try:
        raw = zlib.decompress(base64.b64decode(txt), -15).decode()
        return ET.fromstring(urllib.parse.unquote(raw))
    except Exception:
        return None


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def import_drawio(path):
    root = ET.parse(path).getroot()
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root]
    views, findings = [], []
    for di, d in enumerate(diagrams, 1):
        model = decode_diagram(d) if root.tag == "mxfile" else d
        if model is None:
            findings.append(f"page {di}: could not decode")
            continue
        cells = model.iter("mxCell")
        verts, edges = {}, []
        for c in cells:
            st = c.get("style", "") or ""
            if c.get("vertex") == "1":
                g = c.find("mxGeometry")
                gx = [float(g.get(k, 0)) if g is not None else 0 for k in ("x", "y", "width", "height")]
                icon = (re.search(r"image=([^;]+)", st) or re.search(r"resIcon=([^;]+)", st))
                verts[c.get("id")] = {"id": c.get("id"), "label": strip_html(c.get("value")), "style": st,
                                      "icon_ref": icon.group(1)[:80] if icon else None, "geo": gx,
                                      "parent": c.get("parent")}
            elif c.get("edge") == "1":
                if "archmap=" in st:
                    continue
                bidir = ("startArrow=" in st and "startArrow=none" not in st) or "dir=both" in st
                edges.append({"_id": c.get("id"), "from": c.get("source"), "to": c.get("target"), "label": strip_html(c.get("value")),
                              "bidirectional": bidir, "dashed": "dashed=1" in st,
                              "no_arrow": "endArrow=none" in st and not bidir})
        # edge labels stored as child cells of the edge
        edge_ids = {c.get("id") for c in model.iter("mxCell") if c.get("edge") == "1"}
        for c in model.iter("mxCell"):
            if c.get("edge") == "1" and not strip_html(c.get("value")):
                kid = [v for v in verts.values() if v["parent"] == c.get("id") and v["label"]]
                if kid:
                    for e in edges:
                        if e.get("_id") == c.get("id"):
                            e["label"] = kid[0]["label"]
        for k in [k for k, v in verts.items() if v["parent"] in edge_ids]:
            verts.pop(k)
        containers = []
        for vid_, v in verts.items():
            x, y, w, h = v["geo"]
            inside = [o for o in verts.values() if o is not v and o["geo"][2] and
                      o["geo"][0] >= x and o["geo"][1] >= y and o["geo"][0] + o["geo"][2] <= x + w and o["geo"][1] + o["geo"][3] <= y + h]
            if inside and not v["icon_ref"]:
                containers.append({"id": vid_, "label": v["label"], "contains": [o["id"] for o in inside]})
        views.append({"page": d.get("name", f"page {di}"), "vertices": list(verts.values()), "edges": edges,
                      "containers": containers,
                      "stats": {"vertices": len(verts), "edges": len(edges),
                                "unlabeled_edges": sum(1 for e in edges if not e["label"]),
                                "bidirectional_edges": sum(1 for e in edges if e["bidirectional"]),
                                "undirected_edges": sum(1 for e in edges if e["no_arrow"]),
                                "dangling_edges": sum(1 for e in edges if not e["from"] or not e["to"]),
                                "icons_without_label": sum(1 for v in verts.values() if v["icon_ref"] and not v["label"])}})
    return {"source": os.path.basename(path), "pages": views, "decode_problems": findings,
            "_next": "Read this, then write a full spec (references/spec.md) that describes the same design, "
                     "add review.findings, and run check/build."}


# ----------------------------------------------------------------- build
def build(spec, out, replace_draft=False):
    errs, warns = check(spec)
    for w in warns:
        print("WARN ", w)
    if errs:
        for e in errs:
            print("ERROR", e)
        sys.exit("Fix errors before build.")
    m = spec["meta"]
    stem = f"{slug(m['workload'])}_architecture_{m['version']}"
    os.makedirs(out, exist_ok=True)
    dpath, hpath = os.path.join(out, stem + ".drawio"), os.path.join(out, stem + ".html")
    pdir = os.path.join(out, stem + "_previews")
    exists = [p for p in (dpath, hpath, pdir) if os.path.exists(p)]
    if exists:
        if not (replace_draft and m.get("status") == "Draft"):
            sys.exit(f"{exists[0]} exists. Bump meta.version for a change; never overwrite a published version. "
                     "(--replace-draft rebuilds a Draft that has not been handed to anyone yet.)")
        for p in exists:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(pdir)
    svgs = {}
    for i, v in enumerate(ordered_views(spec), 1):
        s = svg_view(spec, v); svgs[v["id"]] = s
        sp = os.path.join(pdir, f"{i:02d}_{v['id']}.svg")
        open(sp, "w").write(s)
        if shutil.which("rsvg-convert"):
            subprocess.run(["rsvg-convert", "-o", sp[:-4] + ".png", sp], check=False)
    write_drawio(spec, dpath)
    write_html(spec, hpath, svgs)
    json.dump(spec, open(os.path.join(out, stem + ".spec.json"), "w"), indent=1)
    print("OK", dpath); print("OK", hpath); print("OK", pdir, "(inspect the PNGs)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("check"); a.add_argument("spec")
    a = sp.add_parser("build"); a.add_argument("spec"); a.add_argument("--out", required=True)
    a.add_argument("--replace-draft", action="store_true", help="rebuild an undelivered Draft of the same version")
    a = sp.add_parser("import"); a.add_argument("drawio"); a.add_argument("--out", required=True)
    a = sp.add_parser("icons"); a.add_argument("filter", nargs="?", default="")
    args = ap.parse_args()
    if args.cmd == "icons":
        for k in sorted(ICONS):
            if args.filter in k:
                print(k)
    elif args.cmd == "check":
        errs, warns = check(json.load(open(args.spec)))
        for w in warns:
            print("WARN ", w)
        for e in errs:
            print("ERROR", e)
        print(f"{len(errs)} errors, {len(warns)} warnings")
        sys.exit(1 if errs else 0)
    elif args.cmd == "build":
        build(json.load(open(args.spec)), args.out, args.replace_draft)
    elif args.cmd == "import":
        json.dump(import_drawio(args.drawio), open(args.out, "w"), indent=1)
        print("OK", args.out)


if __name__ == "__main__":
    main()
