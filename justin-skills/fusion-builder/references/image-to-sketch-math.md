# Image → sketch: tools and math

Eyeballing a photo produces a model that looks right and measures wrong. This is the
measurement path: recover a small set of primitives with real numbers, then build the
sketch from those numbers.

Two scripts do the heavy lifting, both in `scripts/`, both running in the local Python
environment (not inside Fusion):

| Script | In | Out |
|---|---|---|
| `trace_image.py` | photo / drawing + a scale reference | `spec.json` (lines, arcs, circles in mm), `overlay.png`, `fusion_sketch.py` |
| `compare_silhouette.py` | Fusion screenshot + reference image | IoU, contour deviation, Hausdorff, bbox delta, `diff.png` |

Available libraries: `cv2` (OpenCV), `numpy`, `scipy`, `skimage`, `PIL`, `matplotlib`.
`ezdxf` is not installed by default — `pip install ezdxf --break-system-packages` if the
DXF route is wanted.

## Contents
1. Decide whether to trace at all
2. Scale and perspective — the two things that ruin dimensions
3. Segmentation
4. Contour → primitives (the fitting math)
5. Symmetry, holes, datums
6. Getting geometry into Fusion: three routes
7. Verification metrics
8. Worked sequence

---

## 1. Decide whether to trace at all

| Situation | Route |
|---|---|
| Drawing with dimensions printed on it | Don't trace. Read the numbers, build parametrically. Tracing a dimensioned drawing throws away exactness. |
| Prismatic part (lines, arcs, holes) from a photo | Trace to **get the numbers**, then hand-build a parametric sketch from them. |
| Organic profile (a grip, a fairing, a cam curve) | Trace to geometry — fitted spline through decimated points. |
| Napkin sketch | Don't trace. Extract intent, ask for dimensions, build parametrically. |
| Fusion screenshot of a problem | Don't trace. Inspect with a read-only script. |

The default for functional parts is **trace to numbers, build by hand**. A traced sketch is
a dead sketch: hundreds of points, no constraints, nothing editable. The numbers from the
trace feed `bore_dia = 6.5 mm`, and that is the deliverable.

## 2. Scale and perspective

**Scale.** Nothing is dimensional until one length is pinned. `trace_image.py` takes it as
`--cal-mm M --cal-px P` (a known M mm spanning P px) or `--mm-per-px`. Sources, best first:
a user-stated dimension, a caliper/ruler in frame, a standard object (coin, M3 screw head,
graph paper), a standard feature (1/4-20 thread, bearing OD).

Propagate the error, don't hide it: a 1 px reading error on a 40 px calibration span is
2.5%, which on a 48 mm part is 1.2 mm. Report derived dimensions with that band and round
to something manufacturable.

**Perspective.** A photo shot off-axis maps the part through a homography; proportions read
off it are wrong in a way no amount of careful measuring fixes. Symptom: a rectangle whose
opposite edges are not parallel in the image.

Fix, in order:
1. Ask for a straight-on shot. Cheapest and best.
2. Rectify: four points of a known rectangle in frame → `--rect-px x1,y1,...,x4,y4 --rect-mm WxH`.
   This is a 4-point DLT homography (`cv2.getPerspectiveTransform`); after warping, pixels
   are square and metric and scale comes free.
3. If neither, say the numbers are proportional estimates only and get one real measurement
   per axis from the user.

Also correct for lens barrel distortion only if the image is from a wide-angle phone lens at
close range and edges visibly bow; otherwise it is below the noise floor of the whole process.

## 3. Segmentation

Goal: a clean binary mask of the part. `trace_image.py` uses Otsu thresholding plus a
morphological open/close to kill speckle, then takes the largest external contour, with
inner contours (holes) via `RETR_CCOMP` hierarchy.

When it fails:
- part lighter than background → `--invert`
- busy background → crop first, or shoot the part on a plain contrasting sheet
- soft shadows merging into the part → reshoot with diffuse light; a shadow becomes geometry
- glare blowing out an edge → the contour will cut the corner; visible in `overlay.png`

Backstop if thresholding can't separate: Canny edges (`cv2.Canny`) plus `cv2.findContours`,
or `skimage.segmentation.felzenszwalb`. Both need more hand-holding; try lighting first.

## 4. Contour → primitives

This is the part that matters. A raw contour is ~1000 points; the part was drawn with maybe
six entities. Recovering those six is what makes the result a CAD model instead of a trace.

**Arc-length resampling.** Uniform resampling first, so a tolerance in mm means the same
thing everywhere on the contour.

**Incremental grow-and-break fitting.** Walk the contour; extend the current segment while a
primitive still fits within tolerance; break when it doesn't; start a new one. Superior to
curvature-threshold corner detection on real parts, where fillets make every corner a
gradual bend and thresholds either miss corners or invent them.

**Line fit — total least squares.** Centroid, then SVD of the centred points; the first
right-singular vector is the direction, and the residual is the perpendicular distance.
Ordinary least squares is wrong here: it minimises vertical error, so it degrades as the
line approaches vertical.

**Circle fit — algebraic (Kasa).** Minimise |x² + y² − 2ax − 2by − c| over (a, b, c), a
linear least-squares problem; then centre = (a, b), r = √(c + a² + b²). Fast and stable for
arcs sweeping more than ~30°. For short, noisy arcs it biases the radius small — Taubin or
Pratt fits are the upgrade, and a Levenberg–Marquardt refinement on geometric distance is
the gold standard when the radius actually matters (a bore, a bearing seat).

**Line vs arc.** Compare fit residuals, and use the **sagitta** — maximum deviation from the
chord — as the tie-breaker. A shallow arc can fit a line within tolerance; if the sagitta is
below tolerance too, it *is* a line for all practical purposes, and calling it a line keeps
the sketch clean.

**Splines.** Whatever fits neither becomes a fitted spline through decimated points. Keep the
point count low — 8 to 15 for a profile. A spline with 200 points is unusable downstream:
it ripples, it slows rebuilds, and no one can edit it.

**Tolerance.** Set `--tol-mm` to the real precision of the source: 0.1–0.2 mm for a good
straight-on photo with a caliper reference, 0.3–0.5 mm for a handheld shot, tighter only for
a rectified scan. Too tight fragments smooth curves into dozens of stubby arcs; too loose
eats real features.

## 5. Symmetry, holes, datums

**Symmetry** by PCA: principal axes of the contour, reflect the points about each candidate
axis, measure nearest-neighbour deviation (`scipy.spatial.cKDTree`). Mean deviation well
under tolerance means the part is symmetric — then **sketch half and mirror**, which halves
the constraint work and makes the symmetry a property of the model rather than a coincidence
of two hand-placed halves.

**Holes** from inner contours, circle-fitted. Roundness is the standard deviation of the
radial distances over the mean; under ~6% it is a circle, above that it is a slot or a
pocket and gets reported as a polygon for a human to interpret.

Report hole positions relative to a **datum feature**, not to the image frame: distance from
the nose arc centre, offset from the symmetry axis. Those are the numbers that become
parameters and survive a change in overall length.

**Datum choice** falls out of the same analysis — origin on the symmetry axis, at a bore
centre or a mounting face. `--origin centroid|bbox-min|bbox-center` sets what the exported
coordinates are relative to.

## 6. Getting geometry into Fusion: three routes

**(a) Numbers → hand-built parametric sketch. Default for functional parts.**
Take radii, lengths, hole diameters and centres from `spec.json`, round them to intent
(29.35 mm and 30.24 mm on two ends of a symmetric part means R30), declare them as user
parameters, and write the sketch as in `api-recipes.md`. Fully constrained, fully editable.

**(b) Generated trace script.** `fusion_sketch.py` from the trace rebuilds the outline as
lines, arcs and splines with coincident constraints. Use for organic profiles, or as a
reference underlay to sketch over. It is unconstrained apart from endpoint coincidence —
say so when you use it.

**(c) DXF import.** Fusion's `importManager.createDXF2DImportOptions(path, plane)` pulls a
DXF straight onto a sketch plane, which is the cleanest route for complex 2D outlines.
Requires the DXF file to exist **on the machine running Fusion** — a file in this Python
environment is not visible to Fusion unless the user moves it. Ask before assuming.

The same caveat applies to canvas images (`root.canvases`): local path on the Fusion machine,
calibrate against a known dimension before tracing, and remember the canvas is a guide, not
geometry.

## 7. Verification metrics

After each build increment, screenshot with `transparentBackground: true` and the view
direction matching the reference, then run `compare_silhouette.py`:

- **IoU** — intersection over union of the two silhouettes. >0.98 good, 0.95–0.98 worth a
  look, <0.95 means something is structurally wrong, not a rounding difference.
- **Mean contour deviation** — average nearest-neighbour distance between outlines. Compare
  it against your trace tolerance; deviation much larger than tolerance is a real error.
- **Hausdorff distance** — the single worst divergence. This is the diagnostic one: it points
  at *where* the model departs from the reference.
- **Aspect ratio delta** — scale-free, so it survives any alignment mistake. A few percent
  here means a proportion error, which is usually a wrong dimension rather than a wrong shape.
- **`diff.png`** — green is model-only, red is reference-only, grey is agreement. Look at it.
  The numbers tell you something is wrong; the picture tells you what.

Shape-only mode (default) rescales before comparing, so it tests shape. Metric mode
(`--mm-per-px-model`, `--mm-per-px-ref`) tests actual dimensions — use it once the screenshot
scale can be pinned, since that is the mode that catches a bore 0.4 mm undersize.

## 8. Worked sequence

```bash
# 1. trace, with the caliper jaw (6.5 mm) spanning 41 px in the photo
python scripts/trace_image.py clip.jpg --cal-mm 6.5 --cal-px 41 --tol-mm 0.2 --out trace/

# 2. LOOK at trace/overlay.png before believing any number in spec.json

# 3. build in Fusion from the rounded numbers, parametrically (route a)

# 4. screenshot the model, same view as the photo, transparent background

# 5. check it
python scripts/compare_silhouette.py --model shot.png --ref clip.jpg --out cmp/
```

Then report the deltas to the user with the gate: what matched, what didn't, by how much,
and which parameter you would change to close the gap.
