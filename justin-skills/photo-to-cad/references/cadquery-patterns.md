# CadQuery patterns for reverse-engineered parts

Install: `pip install cadquery --break-system-packages` (works offline-free, ~1 min).

Contents:
1. Constant-section sweep
2. Variable-section loft (taper, curve)
3. Section wires: the export-size trap
4. Confining cuts
5. Features positioned on a swept surface
6. Sanity checks

---

## 1. Constant-section sweep

Sweep needs the profile on a plane at the path start, normal to the path tangent there.

```python
path = (cq.Workplane("YZ").moveTo(-Rc, -L).lineTo(-Rc, 0)
        .radiusArc((Rc, 0), Rc).lineTo(Rc, -Ls))
prof = cq.Workplane("XY", origin=(0, -Rc, -L)).polyline(pts).close()
solid = prof.sweep(path, isFrenet=False, transition="transformed")
```

`isFrenet=True` and `transition="round"/"right"` frequently raise `ValueError` on paths
with a straight-arc-straight sequence. `isFrenet=False` with `transition="transformed"`
is the combination that survives.

Arc direction: `radiusArc(end, R)` vs `radiusArc(end, -R)` chooses which side the arc
bulges. Getting it backwards produces a valid solid whose bounding box is wrong — check
the bbox against the expected overall length immediately.

## 2. Variable-section loft

For taper, transverse curvature that changes, or a centerline that bows, sweep can't
help. Sample the centerline, build one wire per station in the local frame, loft.

```python
def centerline(p):
    """Return [(Vector point, distance-from-datum, segment-name), ...]."""
    ...

for i, (pt, dc, seg) in enumerate(cl):
    tan = (cl[min(i+1, n)][0] - cl[max(i-1, 0)][0]).normalized()
    nrm = Vector(0, tan.z, -tan.y).normalized()   # in-plane normal, path in YZ
    wires.append(section_wire(pt, tan, nrm, dc, seg))

body = cq.Workplane(obj=cq.Solid.makeLoft(wires, False))   # False = not ruled
```

Sign convention for `nrm` decides which way a channel opens. Pick it so the normal points
"inward" at the first station; swept around a 180° bend it flips automatically, which is
usually what you want for a clip whose two legs face each other.

A quadratic bow is a clean way to model a gentle curve that must stay tangent to a
straight or an arc at one end:

```python
y = -Rc + BOW * (1 - s / L) ** 2      # drift BOW at s=0, tangent-continuous at s=L
```

~25 stations per segment is plenty. More just inflates the export.

## 3. Section wires: the export-size trap

**Polygon wires** (`cq.Wire.makePolygon`) loft into a faceted solid. 480 sections of
50-point polygons produced a **70 MB STEP** — unusable.

**Periodic splines** (`cq.Edge.makeSpline(pts, periodic=True)`) are worse: **113 MB**, and
they round off the sharp corners of a channel section, changing the volume by 30%. Also
note `makeSpline(..., periodic=True)` must NOT get a repeated closing point or it raises
`Standard_OutOfRange: BSplCLib::Interpolate`.

**Exact arcs and lines** are the answer — build each section from its true geometry:

```python
edges = [cq.Edge.makeThreePointArc(ia, mid_inner, ib),
         cq.Edge.makeLine(ib, oa),
         cq.Edge.makeThreePointArc(oa, mid_outer, ob),
         cq.Edge.makeLine(ob, ia)]
wire = cq.Wire.assembleEdges(edges)
```

Same part, same station count: **400-500 KB STEP**, smooth surfaces, correct volume.
Every section must have the same edge count and consistent ordering or the loft will
twist.

## 4. Confining cuts

A large cutting box rotated about the origin sweeps through space you didn't intend. When
an angled cut belongs to one leg of a two-leg part, intersect the cutter with a half-space
first:

```python
half = cq.Workplane(obj=cq.Solid.makeBox(40, 30, 80, cq.Vector(-20, 0.2, -70)))
cut  = cq.Workplane(obj=box).rotate((0,0,0), (1,0,0), b).translate(tip).intersect(half)
```

Symptom of getting this wrong: the part builds and exports fine, but a render shows a
whole limb missing. Volume drops sharply — watch for it.

## 5. Features positioned on a swept surface

Keep the frames (point, normal, station, segment) from the loft so you can place bosses,
teeth, and bores on the surface afterward:

```python
f = min((g for g in frames if g[3] == "short"), key=lambda g: abs(g[2] - station))
base = f[0] + Vector(1, 0, 0) * u + f[1] * v      # offset across width, then onto surface
cone = cq.Solid.makeCone(r_base, r_tip, h, base, f[1])
```

If the feature must *reach* another surface, compute `h` from the geometry (leg
separation minus both surface offsets) rather than fixing it. Then a later change to the
bow or the radius updates it for free.

For an axial bore along a local tangent, recover the tangent from the stored normal:
`tan = Vector(0, -nrm.z, nrm.y)`.

## 6. Sanity checks

Print on every build:

```python
bb = s.val().BoundingBox()
print("bbox %.2f %.2f %.2f  vol %.1f" % (bb.xlen, bb.ylen, bb.zlen, s.val().Volume()))
```

- bbox disagrees with measured overall size → wrong arc direction or wrong scale
- volume dropped by a third after adding a cut → the cut escaped its region
- volume rose after a cut → you unioned instead of cutting
- bbox grew slightly after a thickness change → expected; the outer apex moved

Export both formats every run:

```python
cq.exporters.export(s, "out/part.step")
cq.exporters.export(s, "out/part.stl", tolerance=0.008, angularTolerance=0.1)
```
