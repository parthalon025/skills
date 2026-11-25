---
name: "photo-to-cad"
description: Reverse-engineer a physical object into a parametric CAD model from photographs taken against a scale reference (cutting mat, ruler, calipers, coin). Produces a STEP/STL solid, a sketch-first Fusion 360 script, and rendered orthographic views for visual comparison against the photos. Use this skill whenever a user uploads photos of a real object and wants it modeled, measured, reproduced, scanned, "made into a 3D model," turned into CAD, turned into a printable part, or reverse-engineered — and also when they mention Fusion, STEP, STL, "pixel matching," a scale mat, or ask for dimensions of a part from pictures, even if they never say the words "reverse engineer" or "CAD." Also covers angled photos, heights from two photos, and matching the model to a photo from its own camera.
---

# Photo to CAD

Turn photographs of a physical part into a parametric solid model, then iterate with the
user until the model matches the object.

The core difficulty is not CAD. It is that photographs underdetermine geometry: you will
be wrong about some features, and the user will correct you several times. Structure the
work so corrections are cheap — one parameter block, one rebuild command, one visual
check — and so that each correction propagates to everything derived from it.

## Workflow

1. **Inventory the inputs** — find the images, establish whether you can compute on them.
2. **Ask a small number of blocking questions**, then build anyway.
3. **Calibrate scale** off the reference object and measure. For angled shots, rectify the plane or solve the camera.
4. **Build a parametric solid** from a single parameter block.
5. **Render and look** before presenting anything: orthographic views for shape, plus renders from each photo's solved camera to verify.
6. **Present files every turn.**
7. **Iterate** on user corrections, recomputing dependent dimensions rather than patching. Change the channel when the same feature is corrected twice.

---

## 1. Inventory the inputs

Uploaded images are not always on disk. Check first:

```bash
ls -la /mnt/user-data/uploads
```

If the directory has the files, you can compute on pixels (see `scripts/calibrate.py`).
If it is **empty but images appear in the conversation**, you can still see them — measure
visually against the scale reference and say plainly that you are doing so rather than
claiming pixel analysis you did not run. Never fabricate a measurement pipeline you
didn't execute; the user will calibrate their trust in your numbers based on what you
claim about them.

Then classify every photo before measuring anything. For each, decide:

- **Which view is it?** Name the plane (e.g. "bend plane," "face on," "end on").
- **Is the part flat in the reference plane?** Only these are usable for dimensions.
- **Is it a macro shot with the part elevated off the mat?** The grid behind it is at a
  different depth, so its scale does not apply to the part. Use these for *shape, feature
  presence, and proportion only* — never for length. Say so out loud.

- **How much should it be trusted?** A real photo, a macro shot, a drawing or an AI-generated image each own different things (plan, height, topology). See `references/camera-and-multiview.md` §1.

Getting this classification wrong is the single most common source of a badly scaled
model. Two photos of the same object can disagree by 60% on apparent width if one of them
is a close-up.

## 2. Ask, then build anyway

Ask only questions whose answers change what you build, and keep it to about three:

- What is the part and what does it mate with? (decides which dimensions are critical)
- Can they take caliper readings? Name the 3-4 dimensions that drive everything else.
- What deliverable — STEP to import, a Fusion script with a feature tree, or both?

Then **build a first version without waiting**. A wrong model with named parameters is
far more useful to the user than a list of questions, because pointing at a render is
easier than describing a shape in words. Every correction they give you is worth more
than an answer to a question they had to imagine the answer to.

**The exception is topology**: which way a lip bends, whether a fold goes over or under,
whether a boss is hollow. Photos underdetermine it, and a wrong guess wastes a whole rev.
When topology is ambiguous, still build, but make the interpretation explicit in the first
rev: say which reading you chose, name the alternatives so a one-word answer settles it,
and show your reading as a numbered trace on the photo. See
`references/operating-principles.md` §3–4.

## 3. Calibrate scale and measure

Establish px/mm from the reference, then measure everything in those units.

- Prefer the **largest available baseline** — count across ten grid squares, not one.
  Tick-to-tick error is divided by the number of squares you span.
- Measure the **same dimension in two photos** where possible and reconcile.
- Use a **known total** as a check: if overall length measured in a plan view disagrees
  with the sum of the segment lengths you measured, something is misclassified.
- For angles, prefer rise/run against the grid over protractor-by-eye. Many cutting mats
  also print an angle fan (10/20/30/45/60/80°) — use it when an edge runs near one.
- Standoff error: a part sitting 5 mm above the mat photographed from ~300 mm is
  magnified under 2%. Ignore it. A macro shot is a different story entirely — see above.

**Angled shots and raised features.** A 2-point scale is only right square-on and on the
plane. With ≥ 4 known mat points in view:
- `scripts/rectify_plane.py` gives an exact top view in mm for everything on the plane.
- `scripts/solve_camera.py` solves the full camera, so features at a known height become
  measurable (macro shots included), and two solved photos triangulate heights.

See `references/camera-and-multiview.md`.

If `scripts/calibrate.py` is usable (images on disk), it converts pixel distances to mm
given two reference points. Otherwise do the arithmetic explicitly in your reasoning and
report the baseline you used, so the user can sanity-check your scale.

**Report each dimension with its source and confidence.** A table of value / which photo /
high-medium-low is worth more than a list of numbers, because it tells the user where to
spend their caliper time.

## 4. Build a parametric solid

Use CadQuery (`pip install cadquery --break-system-packages`) for the authoritative solid.
It builds and exports in seconds, which is what makes the iteration loop fast.

Structure the model file as:

```python
P = dict(OAL=43.0, WALL_T=2.2, ...)   # every dimension, one place, with units in comments

def derived(p): ...                    # dimensions computed from P, never hardcoded
def build(p=P): ...                    # returns the solid
if __name__ == "__main__":             # export STEP + STL, print bbox and volume
```

Rules that make iteration cheap:

- **No magic numbers in the body.** If a number appears in `build()`, it belongs in `P`.
- **Derive, don't duplicate.** If a tooth must reach a facing surface, compute its height
  from the gap; don't hardcode it and then forget to update it when the gap changes.
  This is what makes a one-line correction from the user cost one line of work.
- **Print `bbox` and `volume` on every build.** They catch failures no render will: a
  missing cut, a doubled union, a bevel that ate half the part.
- **Check self-consistency.** If a wall thickness and a bend radius imply the two legs of
  a clip intersect, the numbers are wrong even if each was measured carefully. Say which
  one you are adjusting and why.

For variable cross-sections (taper, curve, twist), sample the centerline, build one wire
per station, and loft. Parts that fold or overlap themselves (straps, curled ribbons, looped hoses) and blended
organic solids (grips, knobs, handles) are beyond a loft: build them procedurally or as
signed-distance solids and deliver a mesh (`references/organic-parts.md`). See
`references/cadquery-patterns.md` for the loft pattern and
for the export-size traps — a naive implementation produces a 70-100 MB STEP that chokes
on import, and the fix is not obvious.

## 5. Render and look

Visual inspection is the test method. Before presenting anything, render orthographic
views and actually view the image:

```bash
python scripts/render_views.py out/clip.stl out/views.png
```

Then open it with the `view` tool and compare against the photos. Title each panel with
the photo it corresponds to ("loop plane (cf. IMG_4198)") so the comparison is direct for
both of you.

When a photo's camera is solved, also render the model **from that camera** and look at the
blend and outline panels. Orthographic renders against perspective photos make camera error
look like model error:

```bash
python scripts/render_matched.py out/clip.stl IMG_4198.jpg cam_4198.json out/clip_matched_4198.png
```

This catches errors that build cleanly and export fine: a bevel cut that removed the
wrong leg, teeth that hang off the edge of the surface they're supposed to touch, a bend
that curves the wrong way. All of these produce valid solids with plausible bounding
boxes. Only looking finds them.

## 6. Present files every turn

Stage deliverables in `/mnt/user-data/outputs/` and call `present_files`. A file that is
written but never presented does not exist as far as the user is concerned — on mobile
there is no file card at all. Do this on every revision, not just the first.

Standard deliverable set:

| File | Purpose |
|---|---|
| `<part>.step` | authoritative geometry, imports into Fusion |
| `<part>.stl` | mesh for printing or quick viewing |
| `<part>_views.png` | rendered orthographic views for comparison |
| `<part>_model.py` | CadQuery source — the parameter block the user edits |
| `<part>_fusion.py` | Fusion 360 script for a native feature tree |

## 7. Iterate

Each round: apply the correction, rebuild, render, look, present, and report what changed
**and what it forced**. Corrections are coupled — a user who tells you a strap is wider
than you thought has also told you the channel radius must grow, or the part
self-intersects. Surfacing that reasoning is most of the value you add over a drafting
service.

Label revisions (rev A, rev B, ...) so both of you can refer to versions unambiguously.

**Two corrections on the same feature: stop rebuilding it and change the channel.** Use a
numbered traced reading on the photo, the user's sketch or strokes, a second photo from the
angle that shows it, or named markers. A third guess in the same channel is usually wrong in
the same way (`references/operating-principles.md` §4). Keep `session_state.md` (rev,
dimension table, decisions verbatim, open questions) so the work survives a long session.

When a dimension is inferred rather than measured — chosen because it makes the rest
consistent — say so explicitly and name the parameter. That's the one the user should
check with calipers.

---

## The Fusion 360 deliverable

If the user wants a feature tree rather than an imported body, generate a Fusion script.

**Build it sketch-first**: create sketches, then create solids from those sketches. Fusion
users expect to open the timeline and find editable sketches driving the geometry. A
script that produces a body with no sketch history is much less useful to them, even if
the shape is identical.

`references/fusion-api-patterns.md` has the API patterns that work — construction planes
from three points, `modelToSketchSpace` for placing 3D points, lofting through sketch
profiles, tapered extrudes for conical features, and the cm-vs-mm unit trap that silently
produces a model 10x too large.

**If the Autodesk Fusion connector is available** (`fusion_mcp_execute` in your tools),
build natively and test it: use the fusion-builder skill, generate the parameters from `P`,
and keep every script under about 6 KB. Larger data goes through verified chunks (see
fusion-builder's `references/large-payloads-and-meshes.md`).

**Without the connector**, you cannot test a Fusion script from here. Say that plainly, and
point the user at the STEP as the verified geometry. Either way, generate the Fusion
script's numbers from `P`; never hand-copy them.

---

## Common failure modes

**Claiming pixel analysis you didn't run.** Check the uploads directory first, and say
which method you used.

**Trusting a macro shot for scale.** See §1. If two photos disagree wildly on a
dimension, one of them is a close-up with the part off the reference plane.

**Patching instead of deriving.** The user says the teeth are too tall. If you shorten
them by a fixed amount instead of computing the gap, the next correction to the bend
radius silently breaks them again.

**Silent geometry corruption.** A cut solid positioned by rotation about the origin can
extend into a neighboring feature. Confine cuts to the region they belong to (intersect
the cutting solid with a half-space) and verify with bbox and volume.

**Over-smoothing a section.** Fitting a periodic spline through sampled profile points
rounds off the sharp corners of a channel and changes both the shape and the volume. Use
exact arcs and lines for section wires.

**Forgetting to present.** See §6.

**Comparing orthographic renders to perspective photos.** Differences that are really the
camera get "fixed" in the model. Solve the camera and use `render_matched.py`.

**Guessing topology repeatedly.** Clean revs with the wrong fold direction pass bbox,
volume and IoU. Confirm topology with a traced diagram and change channel after two
corrections.

**Measuring from an AI-generated or edited image.** It's useful for topology and intent,
not dimensions. Weight it low and say so.

**Hand-maintained Fusion numbers.** A Fusion script typed separately from `P` drifts at the
first correction. Generate it from `P`.

## References and scripts

| File | Use |
|---|---|
| `references/cadquery-patterns.md` | sweeps, lofts, section wires, confining cuts, sanity checks |
| `references/fusion-api-patterns.md` | sketch-first Fusion script patterns, units |
| `references/camera-and-multiview.md` | image grading, plane rectification, camera solving, heights from two views, matched renders, markers, fitting `P` to measurements, thresholds |
| `references/organic-parts.md` | folding and curling parts beyond a loft; mesh deliverable |
| `references/operating-principles.md` | definition of done, source of truth, uncertainty layers, loop breaker, evidence, decision log, continuity |
| `scripts/calibrate.py` | 2-point scale / grid pitch |
| `scripts/rectify_plane.py` | homography → true top view in mm; measure on the plane |
| `scripts/solve_camera.py` | PnP camera solve from known points; marker overlay |
| `scripts/render_matched.py` | model rendered from a photo's camera: blend, outline, IoU |
| `scripts/render_views.py` | orthographic panels |
| `scripts/ribbon_kit.py` | procedural strips and folds, thick shell, clash test |
| `scripts/sdf_kit.py` | blended organic solids from named primitives → watertight mesh |
| `scripts/mesh_to_fusion.py` | any mesh → verified chunks + a safe Fusion mesh-body build script |
| `evals/evals.json` | starter evals; add a case per new failure mode |
