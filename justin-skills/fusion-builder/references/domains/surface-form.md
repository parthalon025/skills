# Surface and Form

Two different tools people lump together:

- **Surface** (Patch workspace) — untrimmed/trimmed NURBS surfaces: patch, loft, sweep,
  extend, trim, stitch, thicken. Fully scriptable.
- **Form** (T-Spline / sculpt) — subdivision modeling: boxes, faces, edges pushed and pulled
  into organic shapes. **Barely scriptable.**

That second point governs everything below. The API can create a base feature, convert, and
inspect T-Spline bodies, but the actual sculpting — insert edge, crease, pull, bridge — is an
interactive command set with no meaningful scripting surface. Don't promise to build a Form
body through the MCP; you'll produce a script that runs and makes nothing useful.

**Division of labour that works**: the user sculpts the organic bit in Form, you do
everything around it — the parametric mounting features, the surfacing, the trimming and
stitching, the measurement, the verification. Say this out loud at the spec gate rather than
discovering it three scripts in. Check `apiDocumentation` for `TSpline` against their installed
version before you commit either way; the surface has grown slowly and may have moved.

## When to reach for surfaces at all

Solid modeling first, always. Surfaces are for what solids can't do:

- a shape defined by its *boundaries* rather than by extruding a profile — a fairing, a
  cowling, a blended transition between two different sections
- a face you need to repair, replace, or trim before it can be a solid
- a silhouette-driven shape traced from an image (see `image-to-sketch-math.md`)

If a shape can be made with extrude/revolve/loft as a solid, do that. A surface model is
harder to edit, harder to constrain, and prints no better.

## The surface workflow

1. Build the defining curves — sketches, 3D sketches, projected curves. Parametric, as usual.
2. Create surfaces from them (loft, patch, sweep, extrude with `isSolid = False`).
3. Trim and extend until the pieces meet cleanly.
4. **Stitch** into a closed quilt.
5. Thicken (open quilt) or let the stitch produce a solid (closed quilt).
6. Back to solids for fillets, holes, and everything else.

Step 4 is where it fails, and it fails for one reason: a gap. Check it explicitly rather than
wondering.

```python
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    feats = root.features

    # surface from an open profile
    ext = feats.extrudeFeatures
    inp = ext.createInput(openProfile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.isSolid = False
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByString("body_len"))
    surf = ext.add(inp)
    surf.name = "SU_side"

    # stitch a set of surface bodies
    st = feats.stitchFeatures
    coll = adsk.core.ObjectCollection.create()
    for b in surface_bodies:
        coll.add(b)
    sinp = st.createInput(coll, adsk.core.ValueInput.createByString("0.01 mm"))  # tolerance
    sinp.operation = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    s = st.add(sinp)
    body = s.bodies.item(0)
    print("stitched: isSolid=%s faces=%d" % (body.isSolid, body.faces.count))
```

`isSolid == False` after a stitch means the quilt isn't closed. Raising the stitch tolerance
is the tempting fix and usually the wrong one — it welds over a real gap and leaves a
distorted face. Find the open edge instead:

```python
    for edge in body.edges:
        if edge.faces.count == 1:
            p = edge.startVertex.geometry
            print("open edge at (%.2f, %.2f, %.2f) len=%.2f mm" % (p.x*10, p.y*10, p.z*10, edge.length*10))
```

Then patch or extend that specific boundary.

## Feature collections worth knowing

| Need | Collection |
|---|---|
| fill a boundary | `features.patchFeatures` |
| blend between sections | `features.loftFeatures` (`isSolid = False` for a surface) |
| surface along a path | `features.sweepFeatures` |
| lengthen a surface to meet another | `features.extendFeatures` |
| cut a surface with another | `features.trimFeatures` |
| join surfaces into a quilt or solid | `features.stitchFeatures` |
| give a quilt wall thickness | `features.thickenFeatures` |
| offset a face | `features.offsetFeatures` |
| ruled surface off an edge (draft, flanges) | `features.ruledSurfaceFeatures` |
| surface between boundary curves | `features.boundaryFillFeatures` |
| split a face for local work | `features.splitFaceFeatures` |
| swap a face for a surface | `features.replaceFaceFeatures` |

## Form (T-Spline), honestly

What the API gives you: a T-Spline body exists as a `BRepBody`-adjacent object; you can
create a base feature, convert T-Spline to BRep, measure the result, and build parametric
features off the converted solid.

What it doesn't give you: creation and editing of the T-Spline cage. That is the whole of
Form modeling.

So the workflow for an organic part is:

1. You: parametric skeleton — mounting bosses, bore positions, overall envelope, as real
   parameters. Screenshot it.
2. User: sculpts the organic surface in Form against that skeleton, in the UI.
3. You: measure what they made (bounding box, volume, wall thickness sampling, overhang
   analysis), then add the parametric features back on, and verify.

Tell them which steps are theirs at G1. It's a better answer than a script that silently
does nothing.

## Verification for surface work

Screenshot-only inspection misses the problems that matter here — a surface that's 0.2 mm
off closure looks perfect. Check numerically after every stitch or thicken:

- `body.isSolid`
- open-edge scan (above)
- `body.volume` — a plausible number means the quilt actually closed
- face count against expectation; a stitch that silently split faces shows up here

Then screenshot, and specifically look at the *transitions* between surfaces at a glancing
angle, where a tangency break is visible and a normal view hides it.
