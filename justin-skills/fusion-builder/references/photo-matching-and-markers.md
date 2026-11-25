# Photo matching, markers and fitting a model to references

`compare_silhouette.py` answers "is the outline right" for one straight-on view. This file
covers the 3D version: solve the camera of each reference image, render the model from that
exact camera, and use labelled markers to measure and fit in 3D. It works with any mix of
views: a trusted straight-on view plus a low-trust oblique one is the common case, including
AI-generated references.

## Contents
1. Trust levels of references
2. The perspective trap in "top" comparisons
3. Solving a reference camera (PnP + focal scan)
4. Rendering the model from a solved camera
5. Markers ("mocap"): naming, projecting, discussing
6. Two-view triangulation, guide lines and obscured points
7. Edge traces
8. Fitting generator parameters to markers and traces
9. Validating the fitter: synthetic recovery
10. Acceptance thresholds

## 1. Trust levels of references

| Reference | Plan (x, y) | Heights (z) | Topology |
|---|---|---|---|
| straight-on drawing, render or scan | high | none | partial |
| real oblique photo of the object | medium | medium | high |
| AI-generated image | low | low | medium; geometry isn't self-consistent |

Weight residuals by trust (photo 1.0, AI render about 0.4 by default, user-adjustable). Say
at G1 which reference owns which axis. An AI render's camera fits to about 1% at best
because the image isn't a projection of a single consistent object. Don't chase residuals
below that.

## 2. The perspective trap in "top" comparisons

A perspective "top" view from about 360 mm magnifies features 26 mm tall by about 8%
against the base plane. That looks like a modeling error when it's the camera. For any
registration against a plan reference, use orthographic, or a 3° FOV from about 4 m (under
1% parallax). In Fusion, set `camera.cameraType = OrthographicCameraType` before the
screenshot. In web previews, give the top view a tiny FOV and restore the normal lens when
the user orbits away.

## 3. Solving a reference camera (PnP + focal scan)

Use landmarks with known 3D positions in the model: rigid, unambiguous features are best
(corners, hole centers, tips, the ends of straight edges). Five to eight points, spread across
the image and not all coplanar.

```bash
python scripts/solve_camera.py --image ref.jpg --points landmarks.csv --out cam.json
# landmarks.csv: id,x_mm,y_mm,z_mm,u_px,v_px
```

The script scans focal length and runs `cv2.solvePnP` at each value. It keeps the lowest
mean reprojection error and reports it per point, and writes
`{pos, target, up, fov, w, h}` for any renderer. Read the per-point errors, since one bad
landmark shows up as a single large residual. Model heights are assumptions too: if one
landmark is the outlier, that feature may simply sit at a different height in the reference.

## 4. Rendering the model from a solved camera

Three.js: `camera.position = pos; camera.up = up; camera.fov = fov; lookAt(target)` at the
reference's aspect ratio. Headless Chromium can screenshot it (see `co-design-tools.md`).
Fusion: set `viewport.camera` `eye` / `target` / `upVector`, `isFitView = False`,
perspective with `perspectiveAngle` = fov in radians, then screenshot at the reference
aspect ratio.

Compose three panels: reference / model from the same camera / 50% blend. The blend is where
mismatches become obvious.

## 5. Markers ("mocap"): naming, projecting, discussing

Give the model a named marker set computed from the model itself: section starts and ends,
high and low points, tips, and the inner and outer edge at each. Use L# for the left side and
mirrored R# on symmetric parts, plus rigid landmarks in a second color. Project the model markers
into every reference with its solved camera and draw them on the image. A dot that misses
its feature is a measured error with a name ("L7 lands 4 mm outboard of the silver edge"),
which is far easier to discuss than a screenshot. Export a legend CSV (id, description,
xyz).

## 6. Two-view triangulation, guide lines and obscured points

With both cameras solved, a point placed in one image is a ray. Its projection into the
other image is a segment (the epipolar line). Tick it with heights above the plaque
(0, 5, 10… mm above the base) so the user places the second point knowing the height it implies.

- Placed in both views: triangulate as the midpoint of the closest points of the two rays.
  Report the ray gap as a placement-quality check.
- Obscured in one view: intersect the visible ray with a user-set height plane. Draw it
  hollow and dashed in the hidden view.
- Only markers the user **touched** are targets. Untouched model markers are neutral;
  otherwise they pin the model where it already is.
- Keep a feature guide: a named list of the features that constrain the most parameters,
  each with a one-click "place". Pick the few features that pin the most parameters: edges
  at three stations, extreme points, tips, the start and end of each bend.

## 7. Edge traces

A traced polyline along a visible edge constrains more than a dozen dots. Residual: for each
trace point, the distance to the nearest segment of the projected model edge of that type,
on either side for symmetry. Take the mean per trace so long traces don't dominate, times a
weight.

## 8. Fitting generator parameters to markers and traces

- Residuals in **mm-equivalent**: pixel error × mm/px at that point's depth (photo:
  constant; perspective view: depth / f).
- Huber loss (δ ≈ 3 mm) so one misplaced marker doesn't drag everything.
- Symmetry: guide features match whichever side (L or mirrored R) fits better.
- Regularize toward the starting parameters (Σ((Δp / range)²) × about 4), so parameters no
  marker constrains don't drift.
- Evaluate at reduced resolution (fewer rows and columns). Aim for ≤ 20 ms per model
  evaluation.
- Optimizer: bounded pattern search (coordinate steps at 15% of the range, halved on
  stall), in user-selectable groups, with a budget of about 900 evaluations, stop and undo.
  It's robust to the non-smoothness that spline re-sampling introduces, where gradient
  methods stall.
- Report the RMS before and after, what changed, and the residual per marker.
- **Parameters trade off** (a width plus a flare; a radius versus two lengths). Expect the shape
  to be recovered, not the literal values. Pin a sub-shape with more markers or a trace if
  its proportions matter.

## 9. Validating the fitter: synthetic recovery

Before trusting a fitter on real clicks, generate targets from a known different parameter
set, place them as touched markers, fit from the default, and compare. Expect the shape back to
well under 1 mm, well-constrained parameters back nearly exact, and trading parameters back
as an equivalent shape. (Worked example: RMS 2.55 → 0.47 mm; one height exact, one width
24.85 against 25.) Run it again after any change to the loss.

## 10. Acceptance thresholds

| Measure | Accept | Investigate | Stop |
|---|---|---|---|
| Camera solve, rigid landmarks, trusted image | ≤ 0.3% of image width | 0.3–1% | > 1% |
| Camera solve, AI-generated image | ≤ 1.5% | 1.5–3% | > 3% |
| Marker fit RMS (mm-equivalent, trusted view) | ≤ 0.5 mm | 0.5–1.5 mm | > 1.5 mm |
| Triangulation ray gap | ≤ 1 mm | 1–3 mm | > 3 mm (re-place) |
