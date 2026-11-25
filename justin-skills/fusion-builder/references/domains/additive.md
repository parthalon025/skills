# Manufacture: FFF 3D printing

FFF additive is included in personal use — Manufacture workspace additive setups, plus
STL/3MF/OBJ export and slicer handoff. 2 and 3-axis milling, turning and cutting are also
included; multi-axis is not (`personal-use-limits.md`).

Most of the value here is not in the Manufacture workspace. It's in **catching the geometry
problems before the print**, which is ordinary BRep analysis and fully scriptable. Do that
first; the export is the easy part.

## Ask three things before analyzing

Printability is meaningless without them. Propose defaults so one word answers:

1. Nozzle diameter and layer height (0.4 mm / 0.2 mm default)
2. Material (PLA default; PETG/ABS/ASA/nylon change tolerance and warp behaviour)
3. Build orientation — which face is on the plate

Orientation is the one people skip and it changes everything downstream: what overhangs, what
needs support, and where the part breaks. Layer adhesion is the weak axis; a part loaded
across the layers fails at a fraction of its in-plane strength.

## Print-readiness analysis (read-only script)

### Overhangs

Any face whose normal tilts more than ~45° from the build direction needs support. With +Z
as the build direction:

```python
import math, adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    body = design.rootComponent.bRepBodies.item(0)
    limit_deg = 45.0
    total, overhang, down = 0.0, 0.0, 0.0
    for f in body.faces:
        ok, normal = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if not ok:
            continue
        a = math.degrees(math.acos(max(-1.0, min(1.0, normal.z))))
        total += f.area
        if a > 90.0:                      # normal points downward: it is a down-facing face
            down += f.area
            if (a - 90.0) > (90.0 - limit_deg):
                overhang += f.area
    print("faces total %.2f cm^2, down-facing %.2f, needing support %.2f (%.1f%%)"
          % (total, down, overhang, 100.0 * overhang / max(total, 1e-9)))
```

Report support area as a fraction. Above ~15% is worth a conversation about reorienting or
splitting the part — support on a functional surface costs finish and time.

### Thin walls and small features

Anything below roughly two extrusion widths (0.8 mm on a 0.4 nozzle) won't print as a solid
wall. Sample the body's thickness rather than trusting the parameters, because a taper or a
fillet can thin a nominally 2 mm wall locally.

The cheap version: check the parameters named `wall`, `rib`, `thickness` against
`2 × nozzle`. The thorough version: ray-cast across the body at intervals and measure the
solid span — heavier, worth it only when the user has been surprised by a failed print.

### Holes and fit

Printed bores come out undersize — elephant foot at the first layers, plus the inward pull of
the perimeter on a curve. Budget 0.1–0.3 mm on diameter for a 0.4 nozzle, more for a small
hole.

The right fix is a parameter, not a hard-coded number:

```
bore_nominal = 6.0 mm
print_clear  = 0.2 mm
bore_dia     = bore_nominal + print_clear
```

Now they tune `print_clear` once after a test print and every hole in the model follows.
Same pattern for press fits (negative clearance) and clearance holes on fasteners.

### Bridges, knife edges, first-layer area

- Unsupported horizontal spans over ~10 mm sag; chamfer the underside of a hole to 45° rather
  than bridging it flat.
- Knife edges — faces meeting below ~20° — print as a ragged nothing. Put a 0.4 mm flat on it.
- Small footprint plus tall part means it falls over or warps off the plate. Report the
  footprint area and the height:footprint ratio; suggest a brim or a reorientation, not a
  geometry change, when the part is otherwise right.

## Export

```python
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    em = design.exportManager
    opts = em.createSTLExportOptions(root, "/path/part.stl")
    opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    opts.isBinaryFormat = True
    em.execute(opts)
    print("exported")
```

- **3MF over STL** when the slicer takes it: units are unambiguous, it carries multiple bodies
  and colours, and the files are smaller. Look up `create3MFExportOptions` /
  `createC3MFExportOptions` on the installed version — the name has varied — before relying on it.
- Mesh refinement High for curved functional parts; Medium is visibly faceted on a small bore.
- Export the **component or body**, not the root, when the user wants one part out of an
  assembly.
- Path must be valid on the machine running Fusion. Ask for it; never invent one. And this is
  a G7 action — exporting writes a file, so it waits for an instruction.

## Print orientation, verification, and batch plates

**Orient by moving the bodies, not by modelling sideways.** Model in the frame the part wants;
at export, add one temporary move feature that rotates the print axis to +Z and drops the flat
face to Z = 0, export, then delete the move in a `finally` block so the design goes back to its
modelling frame:

```python
m = adsk.core.Matrix3D.create()
m.setToRotation(math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
t = adsk.core.Matrix3D.create(); t.translation = adsk.core.Vector3D.create(0, 0, drop_cm); m.transformBy(t)
mi = root.features.moveFeatures.createInput2(bodies); mi.defineAsFreeMove(m)
mv = root.features.moveFeatures.add(mi)
try:
    ...export...
finally:
    mv.deleteMe(); design.timeline.moveToEnd()
```

**Verify the file, not the export call.** `em.execute()` returning True says a file was
written. Open it and check: a 3MF is a zip — read `3D/3dmodel.model` and count `<object`,
confirm every vertex `z >= 0` and the Z extent matches the part height; a binary STL carries
its triangle count at byte 80. Export of a body that is still at its layout offset is a common
silent error — the mesh is fine but sits 45 mm off the plate.

**Batch plates.** For a print farm, one clip per plate wastes the bed. Fill it with a nested
layout rather than a grid: rows side by side with alternate rows turned 180° typically gains
10-15% on a hooked or tapered outline. Nesting math doesn't belong in Fusion — export one part
per variant as STL, then build the plate file outside with a script that rasterizes the
footprint on a ~0.25 mm grid, searches the row offset that minimises row pitch, places rows
inside the usable area, and **checks the real clearance between every neighbouring pair** before
writing the 3MF. Report the count, the achieved minimum gap, and the plate extents.

Two machine facts to pin down before nesting: the usable area for the job (a dual-nozzle job on
a two-nozzle machine is narrower than the single-nozzle area) and where the purge/prime tower
goes — put it in the strip the layout can't use anyway, and it costs nothing.

For a multi-material part, write each clip into the plate as **one object with one part per
material**, so the slicer sees objects to assign filament to rather than hundreds of loose
bodies. Confirm the filament mapping survives the import on the first plate; slicer-specific
metadata is not guaranteed to be read.

## Additive setups in the Manufacture workspace

Personal use includes FFF additive setups: choose machine and print settings, arrange on the
plate, generate support, and hand off to the slicer. The `adsk.cam` API covers setups and
operations, but additive coverage is thinner than milling and varies by version — query
`apiDocumentation` for `adsk.cam` before scripting anything here, and be willing to say
"do this part in the UI, it's four clicks." Automating a thing that takes four clicks is not
a win.

For a Bambu, Prusa, or similar, most users skip the Fusion additive setup entirely and export
3MF straight to their own slicer. Ask which they do before building anything around it.

## Report format at G6

For a print job, the verification gate should read:

```
Geometry     : 1 body, watertight, 42.1 x 18.0 x 6.0 mm, 3.84 cm^3
Orientation  : +Z as modeled, nose flat on plate
Support      : 6.2% of surface area needs support (below the 15% threshold)
Min wall     : 2.0 mm (wall) = 5 extrusions at 0.4 nozzle - fine
Bores        : bore_dia 6.2 mm = 6.0 nominal + 0.2 print_clear
Watch        : the 8 mm bridge under the bore - chamfer it or expect sag
```

Numbers, then the one thing to watch. That's what makes the next print succeed.
