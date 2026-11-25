# Fusion 360 script patterns

For generating a native feature tree rather than importing a STEP body. Run via
Utilities > ADD-INS > Scripts and Add-Ins > Scripts > + > Run.

## Units: the silent 10x

Fusion's API works in **centimetres** internally. Every raw number passed to
`Point3D.create` or `ValueInput.createByReal` is cm. Keep the parameter block in mm and
convert at the boundary:

```python
MM = 0.1
def P3(t):
    return adsk.core.Point3D.create(t[0] * MM, t[1] * MM, t[2] * MM)
```

`ValueInput.createByString("43 mm")` takes units and is safer for user parameters.

## Sketch-first structure

Fusion users expect editable sketches in the timeline driving the geometry. Build:
sketches → loft/sweep → feature operations. Not: mesh import, not bodies with no history.

```python
def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    ...
```

Wrap everything in try/except and surface the traceback with `ui.messageBox` — otherwise
a failure is silent.

## Placing a sketch on an arbitrary plane

Three coplanar points from the section you're about to draw:

```python
def plane_from(root, a, b, c):
    sk = root.sketches.add(root.xYConstructionPlane)
    p1, p2, p3 = (sk.sketchPoints.add(P3(a)), sk.sketchPoints.add(P3(b)),
                  sk.sketchPoints.add(P3(c)))
    ci = root.constructionPlanes.createInput()
    ci.setByThreePoints(p1, p2, p3)
    pl = root.constructionPlanes.add(ci)
    sk.isVisible = False
    return pl
```

Then draw in that sketch using `sk.modelToSketchSpace(P3(global_point))` so you never have
to reason about the sketch's local axes. This is the single most useful trick in the API
for generated geometry.

## Loft through generated sections

```python
loft = root.features.loftFeatures.createInput(
    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
for pts in sections:
    pl = plane_from(root, pts[0], pts[len(pts)//2], pts[-1])
    sk = root.sketches.add(pl)
    col = adsk.core.ObjectCollection.create()
    for q in pts:
        col.add(sk.modelToSketchSpace(P3(q)))
    spline = sk.sketchCurves.sketchFittedSplines.add(col)
    spline.isClosed = True
    loft.loftSections.add(sk.profiles.item(0))
loft.isSolid = True
body = root.features.loftFeatures.add(loft).bodies.item(0)
```

Keep the section count modest (~10 per segment). Each section is a sketch in the timeline,
and 300 sketches makes the file miserable to work with.

## Cones and tapered features

Extrude a circle with a taper angle rather than constructing a cone:

```python
taper = -math.degrees(math.atan((r_base - r_tip) / h))
ei = root.features.extrudeFeatures.createInput(
    sk.profiles.item(0), adsk.fusion.FeatureOperations.JoinFeatureOperation)
de = adsk.fusion.DistanceExtentDefinition.create(
    adsk.core.ValueInput.createByReal(h * MM))
ei.setOneSideExtent(de, adsk.fusion.ExtentDirections.PositiveExtentDirection,
                    adsk.core.ValueInput.createByString("%g deg" % taper))
ei.participantBodies = [body]
root.features.extrudeFeatures.add(ei)
```

Negative taper narrows toward the extrude direction. Always set `participantBodies` on
join and cut operations or the feature may hit the wrong body.

## Cuts

```python
ci = root.features.extrudeFeatures.createInput(
    sk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
ci.setSymmetricExtent(adsk.core.ValueInput.createByReal(12 * MM), True)
ci.participantBodies = [body]
```

A prismatic cut (one that sweeps straight through) is easiest to sketch on the plane it's
prismatic in — e.g. an angled end cut on a part whose section is constant across its width
is a simple polygon sketched on the side plane, extruded symmetrically.

## User parameters

Writing the dimensions into `des.userParameters` documents the model, but does **not**
make generated geometry parametric — nothing is dimensionally constrained to them. Say so
in a header comment: the parameter block at the top of the script is the source of truth,
edit and re-run to regenerate.

```python
des.userParameters.add("part_oal", adsk.core.ValueInput.createByString("43 mm"),
                       "mm", "reverse-engineered")
```

Wrap in try/except — re-running the script raises on a duplicate name.

## Untestable from outside Fusion

You cannot execute or verify this script from a sandbox. State that when delivering it,
and point the user to the STEP file as the geometry that was actually verified.
