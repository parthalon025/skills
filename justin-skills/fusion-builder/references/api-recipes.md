# Fusion API recipes

Copy-adapt these. Verify anything you're unsure of with
`fusion_mcp_read{queryType:"apiDocumentation", apiCategory:"all", searchPattern:"<name>", filter:"adsk.fusion.<Class>"}`
before sending a script — a doc lookup costs one call, a wrong guess costs an undo plus a rebuild.

## Contents
1. Units — the #1 source of silently wrong models
2. Preflight script
3. User parameters, guard expressions, and the component
4. Sketches, constraints, dimensions
5. Features
6. Stable selection of faces and edges
7. Verification script
8. Export
9. Canvas (tracing a reference image)
10. Parametric sweep (the regression test)
11. Build-script template

---

## 1. Units

**Internal API units are centimetres and radians, regardless of the document's display units.**
`extrudeInput.setDistanceExtent(False, adsk.core.ValueInput.createByReal(25))` gives 25 **cm**, not 25 mm.

Rule: use `createByString` with an explicit unit or a parameter name everywhere a length or angle is set.

```python
vi = adsk.core.ValueInput.createByString("25 mm")     # correct
vi = adsk.core.ValueInput.createByString("wall * 2")  # correct, parametric
vi = adsk.core.ValueInput.createByReal(2.5)           # 2.5 cm — only for deliberate raw values
```

Values you *read back* (`body.volume`, `boundingBox`, `point.x`) are in cm and cm³. Convert for reporting:

```python
mm = lambda v: v * 10.0
print("bbox mm: %.2f x %.2f x %.2f" % (mm(dx), mm(dy), mm(dz)))
```

Sketch point coordinates you pass to `Point3D.create(x, y, z)` are also cm. Build sketch geometry roughly, then let dimensions drive it exactly — that is the parametric way and it sidesteps the unit trap.

Display unit of the document:

```python
design.unitsManager.defaultLengthUnits          # 'mm', 'in', ...
design.unitsManager.convert(1.0, 'mm', 'cm')
design.unitsManager.formatInternalValue(v, 'mm', True)
```

---

## 2. Preflight script

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        print("ERROR: active product is not a Design (check workspace)")
        return
    root = design.rootComponent
    print("doc: %s" % doc.name)
    print("designType: %s" % ("Parametric" if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else "DIRECT (no timeline)"))
    print("units: %s" % design.unitsManager.defaultLengthUnits)
    print("root: %s  bodies=%d sketches=%d components=%d" % (
        root.name, root.bRepBodies.count, root.sketches.count, design.allComponents.count))
    print("timeline: %d" % design.timeline.count)
    for i in range(design.timeline.count):
        it = design.timeline.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            print("  UNHEALTHY [%d] %s: %s" % (i, it.name, it.errorOrWarningMessage))
    for p in design.userParameters:
        print("param: %s = %s (%s)" % (p.name, p.expression, p.unit))
```

Send with `readOnly: true`.

---

## 3. User parameters, guard expressions, and the component

```python
def upsert(design, name, expr, unit, comment=""):
    p = design.userParameters.itemByName(name)
    if p:
        p.expression = expr
        return p
    return design.userParameters.add(
        name, adsk.core.ValueInput.createByString(expr), unit, comment)

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    specs = [
        ("wall",      "2.0 mm", "mm", "min printable wall"),
        ("bore_dia",  "6.5 mm", "mm", "from caliper photo"),
        ("body_len",  "48 mm",  "mm", ""),
        ("draft_ang", "3 deg",  "deg", ""),
    ]
    for n, e, u, c in specs:
        upsert(design, n, e, u, c)
    for p in design.userParameters:
        print("%s = %s  -> %s" % (p.name, p.expression, p.value))
```

Names: lower_snake_case, no spaces, no leading digits. Fusion rejects names colliding with built-in functions (`pi`, `abs`, `min`, `max`, `length`).

Expressions may reference other parameters: `"bore_dia/2 + wall"`.

### Driving vs derived

Split the table. **Driving** parameters hold literals and are the only ones the user edits.
**Derived** parameters hold expressions and nothing else. A number that appears in two rows is
a defect — it means an edit to one will silently fail to move the other, and the sweep in §10
is what will prove it.

```python
driving = [
    ("bore_dia", "6.35 mm", "mm", "measured 6.37, snapped to 1/4in"),
    ("wall",     "2.0 mm",  "mm", "min printable wall"),
]
derived = [
    ("boss_od",  "bore_dia + 2*wall", "mm", ""),
    ("edge_r",   "min(1.5 mm; wall/2 - 0.1 mm)", "mm", "guard: never exceeds the wall"),
]
```

### Guard expressions

Fusion's expression language has `min()` and `max()`. Use them wherever a parameter could be
driven into a value that kills a feature. This converts the two most common failures in the
whole workflow from something you debug once into something that cannot happen:

| Failure | Guard |
|---|---|
| fillet radius exceeds the wall it sits on | `edge_r = min(edge_r_nom; wall/2 - 0.1 mm)` |
| shell thickness exceeds the smallest local radius | `shell_t = min(wall; min_rad - 0.2 mm)` |
| rib thinner than the extruder can print | `rib_t = max(rib_nom; 2 * nozzle)` |
| boss wall vanishes as the bore grows | `boss_od = bore_dia + 2 * wall` |

Argument separator: Fusion expressions use **`;`** inside `min()` / `max()`, not `,`. If a
guard expression is rejected, that is the first thing to check.

A guard makes the geometry survive; it does not make it correct. State the clamp in the spec
so the user knows `edge_r` will stop tracking their number once `wall` drops below 3.2 mm.

### The component

Model into a named component, not into root (non-negotiable 5).

```python
def new_component(root, name):
    m = adsk.core.Matrix3D.create()
    occ = root.occurrences.addNewComponent(m)      # identity: at the parent origin
    occ.component.name = name
    return occ.component

comp = new_component(root, "Comp_clip")
sk   = comp.sketches.add(comp.xYConstructionPlane)   # comp.*, never root.*, from here on
ext  = comp.features.extrudeFeatures
```

Every later recipe in this file that says `root.` should read `comp.` in a real build. The
component carries its own origin and construction planes, so `comp.xYConstructionPlane` is the
right datum, not the root's.

---

## 4. Sketches, constraints, dimensions

### Create and name

```python
sk = root.sketches.add(root.xYConstructionPlane)   # or xZ, yZ, or a BRepFace, or a construction plane
sk.name = "SK_profile"
sk.isComputeDeferred = True    # big speedup while adding many curves; set False at the end
```

Planes: `root.xYConstructionPlane`, `xZConstructionPlane`, `yZConstructionPlane`. On a face: `root.sketches.add(face)` — but see §6 about picking that face stably.

### Geometry

```python
P = adsk.core.Point3D.create
lines   = sk.sketchCurves.sketchLines
circles = sk.sketchCurves.sketchCircles
arcs    = sk.sketchCurves.sketchArcs

rect = lines.addTwoPointRectangle(P(0,0,0), P(4.8, 2.0, 0))       # cm!
c    = circles.addByCenterRadius(P(0.5, 1.0, 0), 0.325)
a    = arcs.addByThreePoints(P(0,0,0), P(0.5,0.5,0), P(1,0,0))
```

### The API gives you no automatic constraints

In the UI, drawing a rectangle adds horizontal, vertical and coincident constraints as you
draw. Through the API it does not. `addTwoPointRectangle` returns four bare lines sharing
corner points and nothing else, so a "rectangle" with only two dimensions on it will skew
into a parallelogram on the first rebuild. Verified on a live build, not theory.

Also: `addCenterPointRectangle` does **not** leave a persistent sketch point at the centre.
There is nothing there to constrain to the origin, and searching `sk.sketchPoints` for a point
at (0,0) finds only the origin itself.

### Centering idiom (the reliable one)

Project the construction axes into the sketch and constrain symmetry to them:

```python
ax = sk.project(root.xConstructionAxis).item(0)
ay = sk.project(root.yConstructionAxis).item(0)
lines = [L for L in sk.sketchCurves.sketchLines if not L.isReference]   # skip projected axes
horiz = sorted([L for L in lines if abs(L.startSketchPoint.geometry.y - L.endSketchPoint.geometry.y) < 1e-6],
               key=lambda L: L.startSketchPoint.geometry.y)
vert  = sorted([L for L in lines if abs(L.startSketchPoint.geometry.x - L.endSketchPoint.geometry.x) < 1e-6],
               key=lambda L: L.startSketchPoint.geometry.x)
gc.addSymmetry(vert[0], vert[1], ay)
gc.addSymmetry(horiz[0], horiz[1], ax)
```

Filter out projected axes with `isReference` or they end up in your line lists.

### Constrain incrementally, and stop when it is determined

A centred rectangle with two dimensions and two symmetry constraints needs exactly **one**
horizontal and **one** vertical — the symmetry pairs carry the rest. The second horizontal
throws `VCS_SKETCH_OVER_CONSTRAINTS`.

```python
for L in (horiz[0], vert[0]):
    if sk.isFullyConstrained:
        break
    gc.addHorizontal(L) if L in horiz else gc.addVertical(L)
```

Same arithmetic for a set of identical features: **n circles need n−1 symmetry constraints in
a tree, not a loop.** Four circles constrained in a ring is one redundant constraint and fails
with `VCS_SKETCH_SOLVING_FAILED`. Fix one circle with its dimensions, then chain the other
three off it.

### Don't dimension with compute deferred

`isComputeDeferred = True` speeds up bulk curve creation, but adding **dimensions** while it is
set produces spurious `VCS_SKETCH_OVER_CONSTRAINTS` errors on dimensions that are perfectly
valid — the same three dimensions succeed with deferral off. Defer for geometry, turn it off
before dimensioning.

### Geometric constraints

```python
gc = sk.geometricConstraints
gc.addCoincident(lines.item(0).endSketchPoint, lines.item(1).startSketchPoint)
gc.addHorizontal(lines.item(0))
gc.addVertical(lines.item(1))
gc.addTangent(arc, line)
gc.addConcentric(circleA, circleB)
gc.addSymmetry(lineA, lineB, sk.originPoint)   # or a construction line
```

Anchor the sketch to the origin — `gc.addCoincident(pt, sk.originPoint)` — or the profile floats and later edits move the part.

### Dimensions driven by parameters

```python
dims = sk.sketchDimensions
d = dims.addDistanceDimension(
        lines.item(0).startSketchPoint, lines.item(0).endSketchPoint,
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
        P(2.0, -0.5, 0))          # text position
d.parameter.expression = "body_len"

r = dims.addRadialDimension(c, P(1.0, 1.5, 0))
r.parameter.expression = "bore_dia / 2"

dims.addDiameterDimension(c, P(1.0, 1.5, 0)).parameter.expression = "bore_dia"
dims.addAngularDimension(lineA, lineB, P(1,1,0)).parameter.expression = "draft_ang"
```

### Check before extruding

```python
sk.isComputeDeferred = False
print("%s: curves=%d profiles=%d fullyConstrained=%s" % (
    sk.name, sk.sketchCurves.count, sk.profiles.count, sk.isFullyConstrained))
for i, pr in enumerate(sk.profiles):
    pp = pr.areaProperties()
    print("  profile %d area=%.3f cm^2 centroid=(%.2f, %.2f)" % (i, pp.area, pp.centroid.x, pp.centroid.y))
```

`profiles=0` means an open loop. Find the gap before going further — usually a missing coincident constraint at a corner.

Pick profiles by **area or centroid**, not by index:

```python
outer = max(sk.profiles, key=lambda p: p.areaProperties().area)
```

---

## 5. Features

### Extrude

```python
ext = root.features.extrudeFeatures
inp = ext.createInput(outer, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
inp.setDistanceExtent(False, adsk.core.ValueInput.createByString("wall"))     # one side
# symmetric about the sketch plane:
inp.setSymmetricExtent(adsk.core.ValueInput.createByString("body_len"), True)  # True = full length
f = ext.add(inp)
f.name = "EX_body"
body = f.bodies.item(0)
body.name = "Body_main"
```

Operations: `NewBodyFeatureOperation`, `JoinFeatureOperation`, `CutFeatureOperation`, `IntersectFeatureOperation`, `NewComponentFeatureOperation`.

Through-all cut:

```python
inp = ext.createInput(boreProfile, adsk.fusion.FeatureOperations.CutFeatureOperation)
inp.setAllExtent(adsk.fusion.ExtentDirections.SymmetricExtentDirection)
inp.participantBodies = [body]
ext.add(inp).name = "CU_bore"
```

Taper on an extrude: `inp.taperAngle = adsk.core.ValueInput.createByString("draft_ang")` (on the extent definition in newer API — verify with a doc lookup if it errors).

### Revolve

```python
rev = root.features.revolveFeatures
inp = rev.createInput(profile, axisLineOrConstructionAxis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
inp.setAngleExtent(False, adsk.core.ValueInput.createByString("360 deg"))
rev.add(inp).name = "RV_body"
```

### Fillet / chamfer

```python
fil = root.features.filletFeatures
edges = adsk.core.ObjectCollection.create()
for e in selected_edges:
    edges.add(e)
inp = fil.createInput()
inp.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByString("edge_r"), True)
fil.add(inp).name = "FI_outer"
```

Chamfer: `root.features.chamferFeatures`, `inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, vi, True)`.

### Shell

```python
sh = root.features.shellFeatures
faces = adsk.core.ObjectCollection.create(); faces.add(openFace)
inp = sh.createInput(faces, False)
inp.insideThickness = adsk.core.ValueInput.createByString("wall")
sh.add(inp).name = "SH_cavity"
```

### Hole (prefer over a cut when it's a real hole — it carries intent)

```python
holes = root.features.holeFeatures
inp = holes.createSimpleInput(adsk.core.ValueInput.createByString("bore_dia"))
inp.setPositionBySketchPoint(sketchPoint)
inp.setAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
holes.add(inp).name = "HO_bore"
```

### Patterns and mirror

```python
mir = root.features.mirrorFeatures
coll = adsk.core.ObjectCollection.create(); coll.add(body)
mir.add(mir.createInput(coll, root.yZConstructionPlane)).name = "MI_half"
```

`rectangularPatternFeatures` / `circularPatternFeatures` follow the same create-input pattern; look up the exact signature before use.

### Construction geometry

```python
planes = root.constructionPlanes
inp = planes.createInput()
inp.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByString("body_len/2"))
pl = planes.add(inp); pl.name = "PL_mid"
```

---

## 6. Stable selection of faces and edges

Indices change when the timeline rebuilds. Never hard-code `body.faces.item(3)` in anything the user will edit later.

**By geometry:**

```python
def faces_by_normal(body, nx, ny, nz, tol=1e-6):
    out = []
    for f in body.faces:
        g = f.geometry
        if isinstance(g, adsk.core.Plane):
            n = g.normal
            if abs(n.x-nx) < 1e-3 and abs(n.y-ny) < 1e-3 and abs(n.z-nz) < 1e-3:
                out.append(f)
    return out

top = max(faces_by_normal(body, 0,0,1), key=lambda f: f.area)     # highest-area +Z face
```

Other discriminators: `f.area`, `f.boundingBox`, `f.pointOnFace`, `f.centroid` (via `f.evaluator`), cylindrical faces by `isinstance(f.geometry, adsk.core.Cylinder)` and `g.radius`.

**Edges by length / direction:**

```python
verticals = [e for e in body.edges
             if isinstance(e.geometry, adsk.core.Line3D)
             and abs(e.geometry.direction.z) > 0.99]
long_ones = sorted(body.edges, key=lambda e: -e.length)[:4]
```

**By attribute** — tag once, find later across rebuilds:

```python
face.attributes.add("fb", "role", "mount_face")
found = design.findAttributes("fb", "role")
mount = [a.parent for a in found if a.value == "mount_face"]
```

**Tag the faces and edge sets you'll need again, in the same script as the feature that
creates them.** This is non-negotiable 6, and the reason is that the geometric heuristics above
are only reliable at the moment you write them: "highest-area +Z face" is unambiguous on a
plate and ambiguous the moment a pocket splits it in two. The tag survives rebuilds, parameter
changes and inserted features; the heuristic does not.

```python
f = ext.add(inp); f.name = "EX_body"
body = f.bodies.item(0); body.name = "Body_main"
top = max(faces_by_normal(body, 0, 0, 1), key=lambda x: x.area)
top.attributes.add("fb", "role", "mount_face")          # tag now, select later
for e in sorted(body.edges, key=lambda e: -e.length)[:4]:
    e.attributes.add("fb", "role", "outer_fillet")
```

Retrieve with `design.findAttributes("fb", "role")` and filter on `.value`. Print the count you
found and compare it to what you tagged — a silent drop from four edges to three is a feature
that changed topology upstream, and it is better caught here than in a failed fillet.

---

## 7. Verification script (`readOnly: true`)

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    mm = lambda v: v * 10.0

    bad = 0
    for i in range(design.timeline.count):
        it = design.timeline.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad += 1
            print("UNHEALTHY [%d] %s: %s" % (i, it.name, it.errorOrWarningMessage))
    print("timeline: %d features, %d unhealthy" % (design.timeline.count, bad))

    print("bodies: %d" % root.bRepBodies.count)
    for b in root.bRepBodies:
        bb = b.boundingBox
        print("  %s vol=%.3f cm^3 bbox=%.2f x %.2f x %.2f mm faces=%d" % (
            b.name, b.volume,
            mm(bb.maxPoint.x-bb.minPoint.x), mm(bb.maxPoint.y-bb.minPoint.y),
            mm(bb.maxPoint.z-bb.minPoint.z), b.faces.count))
        if b.physicalProperties:
            print("    mass=%.2f g material=%s" % (b.physicalProperties.mass * 1000.0, b.material.name))

    for p in design.userParameters:
        print("param %s = %s" % (p.name, p.expression))
```

---

## 8. Export

Only when asked, and only to a path the user supplies.

```python
em = design.exportManager
opts = em.createSTLExportOptions(root, "/path/out.stl")
opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
em.execute(opts)
```

Also available: `createSTEPExportOptions`, `create3MFExportOptions`, `createFusionArchiveExportOptions`.

---

## 9. Canvas (tracing a reference image)

If the user gives a **local file path** to the reference image, attach it as a canvas and trace over it in a sketch:

```python
img_path = "/absolute/path/to/img.png"          # must exist on the machine running Fusion
inp = comp.canvases.createInput(img_path, comp.xYConstructionPlane)
canvas = comp.canvases.add(inp)
canvas.name = "CV_ref"
```

Verify the exact `createInput` signature via `apiDocumentation` (`filter: "adsk.fusion.Canvases"`) before sending — it has changed across releases. Then calibrate the canvas scale against a known dimension, and dimension the traced sketch normally; the canvas is a visual guide, not geometry.

If the image only exists in the chat (no path on the Fusion machine), skip the canvas and work from the measured spec instead — see `image-to-spec.md`.

---

## 10. Parametric sweep (the regression test)

Run at G6, after the verification script. Drives every **driving** parameter to the `min` and
`max` declared in the spec, recomputes, records timeline health and key measurements, and
restores the nominals.

This is what makes the word "parametric" a claim rather than a decoration. It catches:

- a fillet or shell that computes at nominal and dies at the lower bound of the wall
- a feature that never tracked its datum at all (bore stays put while the plate grows), which
  a single-value spot check will miss whenever the spot check happens to move the bore
- a derived parameter that was typed as a literal

Not `readOnly` — it modifies the design. Scripts are transactional, so a sweep that throws
leaves nothing behind; a sweep that completes must restore the nominals itself, which the final
print verifies.

```python
import adsk.core, adsk.fusion

SWEEP = [
    # (parameter, min, max)
    ("wall",     "1.6 mm", "4.0 mm"),
    ("bore_dia", "6.2 mm", "6.6 mm"),
    ("body_len", "40 mm",  "60 mm"),
]

def measure(design, root):
    b = root.bRepBodies.item(0) if root.bRepBodies.count else None
    if not b:
        for c in design.allComponents:
            if c.bRepBodies.count:
                b = c.bRepBodies.item(0); break
    bad = []
    for i in range(design.timeline.count):
        it = design.timeline.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad.append("%s(%s)" % (it.name, it.errorOrWarningMessage))
    bb = b.boundingBox
    mm = lambda v: v * 10.0
    return (b.volume,
            (mm(bb.maxPoint.x-bb.minPoint.x), mm(bb.maxPoint.y-bb.minPoint.y), mm(bb.maxPoint.z-bb.minPoint.z)),
            bad)

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    nominal = {}
    for name, _lo, _hi in SWEEP:
        p = design.userParameters.itemByName(name)
        if not p:
            print("MISSING PARAM %s — sweep aborted" % name)
            return
        nominal[name] = p.expression

    v, bb, bad = measure(design, root)
    print("NOMINAL   vol=%.3f cm^3 bbox=%.2f x %.2f x %.2f  unhealthy=%d" % (v, bb[0], bb[1], bb[2], len(bad)))

    fails = 0
    for name, lo, hi in SWEEP:
        p = design.userParameters.itemByName(name)
        for label, expr in (("min", lo), ("max", hi)):
            p.expression = expr
            design.computeAll()
            v, bb, bad = measure(design, root)
            status = "OK" if not bad else "UNHEALTHY: " + "; ".join(bad)
            fails += 1 if bad else 0
            print("%-10s %-3s %-8s vol=%.3f bbox=%.2f x %.2f x %.2f  %s"
                  % (name, label, expr, v, bb[0], bb[1], bb[2], status))
        p.expression = nominal[name]
        design.computeAll()

    v, bb, bad = measure(design, root)
    print("RESTORED  vol=%.3f cm^3 bbox=%.2f x %.2f x %.2f  unhealthy=%d" % (v, bb[0], bb[1], bb[2], len(bad)))
    for n, e in nominal.items():
        print("  %s = %s" % (n, design.userParameters.itemByName(n).expression),
              "RESTORE MISMATCH" if design.userParameters.itemByName(n).expression != e else "")
    print("SWEEP %s (%d failing steps)" % ("PASS" if fails == 0 else "FAIL", fails))
```

Reading it:

- **Any unhealthy step is a fail.** Fix by tightening a guard expression (`api-recipes.md` §3)
  or by narrowing the declared range with the user, not by deleting the step.
- **A bbox that doesn't move when a length parameter does** means that dimension isn't driving
  anything. That is the dumb-solid failure and it is the whole reason this script exists.
- **A volume that doesn't move when a bore diameter does** means the cut is dimensioned
  numerically, not to the parameter.
- `design.computeAll()` forces the rebuild. Without it, health is read from stale state.

Sweep bounds one parameter at a time. Corner cases (min wall *and* max bore together) are worth
a third pass only when two parameters interact in one feature, which the guard expressions
usually already encode.

---

## 11. Build-script template

`build_<part>.py` lives in the working directory and regenerates the part in an empty document.
Append each accepted increment as its own labelled block (see "The build script" in SKILL.md).

```python
# build_clip.py — regenerates Comp_clip from an empty parametric document.
# Increment blocks are appended at each accepted gate. Verified metrics at the bottom.
import adsk.core, adsk.fusion

VI = adsk.core.ValueInput.createByString

def upsert(design, name, expr, unit, comment=""):
    p = design.userParameters.itemByName(name)
    if p:
        p.expression = expr
        return p
    return design.userParameters.add(name, VI(expr), unit, comment)

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        print("ERROR: direct design — this script needs a parametric document")
        return
    root = design.rootComponent

    # --- G2: parameters --------------------------------------------------
    for n, e, u, c in [
        ("wall",     "2.0 mm",                        "mm", "min printable wall"),
        ("bore_dia", "6.35 mm",                       "mm", "measured 6.37, snapped 1/4in"),
        ("edge_r",   "min(1.5 mm; wall/2 - 0.1 mm)",  "mm", "guard: never exceeds wall"),
    ]:
        upsert(design, n, e, u, c)

    # --- G2: component ---------------------------------------------------
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = "Comp_clip"

    # --- G3: SK_profile --------------------------------------------------
    # <paste the accepted sketch script here, verbatim>

    # --- G4: EX_body -----------------------------------------------------
    # <paste the accepted extrude script here, verbatim>

    print("build_clip: components=%d timeline=%d" % (design.allComponents.count, design.timeline.count))
```

Run it in an empty document, then run the §7 verification script. The measurements must match
the ones accepted at G6. If they don't, the build script is wrong, not the document — something
was accepted in the session that never made it into the file.
