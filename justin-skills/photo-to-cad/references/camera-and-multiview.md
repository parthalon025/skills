# Cameras, rectification and multi-view measurement

A 2-point px/mm scale (`calibrate.py`) assumes the photo is square to the reference and the
feature lies on it. Real photos break both assumptions. This file covers the next three
levels:
- rectify the reference plane (angled photos);
- solve the camera (matched renders, features off the plane);
- two views (heights).

It also covers markers and fitting parameters to measurements.

## Contents
1. Grade every image before measuring
2. Rectify the reference plane (angled shots)
3. Solve the camera from the reference
4. Features above the plane: one view with a known height
5. Two views: triangulate heights
6. Render from the photo's camera, then compare
7. Named markers: measure and discuss
8. Fitting the parameter block to measurements
9. Thresholds

## 1. Grade every image before measuring

| Image | Plane (x, y) | Heights (z) | Shape / topology |
|---|---|---|---|
| square-on, part flat on the mat | high (2-point scale is fine) | none | partial |
| angled, part on the mat, ≥ 4 grid points visible | high after rectification | from a second view or a known height | good |
| macro / part raised off the reference | only via a solved camera, at a known height | low | good |
| drawing / datasheet | exact where dimensioned | exact where dimensioned | exact |
| AI-generated or heavily edited image | low | low | topology and intent only |

Say which image owns which axis, and write it into the dimension table's source column.

## 2. Rectify the reference plane (angled shots)

With ≥ 4 points on the mat whose mm coordinates you know (use 6–12 grid corners spread
around the part, not four adjacent ones), a homography removes perspective exactly **for
features on the plane**:

```bash
python scripts/rectify_plane.py IMG.jpg --pts "u,v,x_mm,y_mm;..." --mmpx 0.1 --out rect/
python scripts/rectify_plane.py IMG.jpg --load rect/homography.json --measure "u1,v1;u2,v2"
```

Read the plane-fit residual. Above 0.5 mm means lens distortion, a warped mat or a
mis-clicked corner. The rectified image is a true top view in mm: trace outlines in it, and
measure the footprint, holes on the bottom face, and anything touching the mat.

Anything **above** the plane is still magnified by `D / (D − h)` (D = camera height,
h = feature height). A 10 mm tall top face shot from 300 mm reads 3.4% large.

## 3. Solve the camera from the reference

Mat grid corners are known 3D points on z = 0, so they solve the full camera:

```bash
python scripts/solve_camera.py --image IMG.jpg --points grid_points.csv --out cam.json
# grid_points.csv: id,x_mm,y_mm,z_mm,u_px,v_px   (z = 0 for mat points; 6-12 points, spread)
```

It scans focal length with PnP and reports reprojection per point. With a solved camera
you can do §4–6. Mixing in points of known height (a stack of coins, the top of a gauge
block) strengthens the solve.

## 4. Features above the plane: one view with a known height

If a feature's height is known (a caliper reading, or a flat top face measured from the
side), intersect its pixel ray with the plane `z = h`. That gives true plan coordinates for
a raised feature from a single photo, and it makes macro and close-up shots usable for
features at a known height instead of discarding them.

## 5. Two views: triangulate heights

Two photos, each with its own solved camera, give 3D points. A point clicked in view A is a
ray, and its projection into view B is a line (the epipolar line). Tick it with heights
(0, 5, 10… mm) and click the feature where it crosses. The triangulated point is the midpoint
of the closest points of the two rays. The gap between the rays is a quality check: re-click
above about 1 mm.

This is how to get heights, rises, dips and overhangs from photos. It works for any two
views of the part sitting still on the mat, even from a phone.

## 6. Render from the photo's camera, then compare

Comparing orthographic renders to perspective photos makes the camera look like a model
error. Once a photo's camera is solved, render the model from it:

```bash
python scripts/render_matched.py out/part.stl IMG.jpg cam.json out/matched.png [--mask part_mask.png]
```

The four panels are: photo, model from the same camera, 50/50 blend, and the model outline
on the photo. With a part mask of the photo it also reports silhouette IoU and which side
has extra material. Look at the blend; every misfit left there is the model's. Keep the
orthographic panels (`render_views.py`) for overall shape; use matched renders to *verify*.

## 7. Named markers: measure and discuss

Give the model named markers at the features that matter: corners, hole centers, tips,
section starts and ends, and extreme points. On symmetric parts, L# and mirrored R#. Project
them into each photo with its camera and draw them. A dot that misses its feature is a
measured, named error ("M4 sits 1.2 mm left of the hole center in IMG_02"), which is easier
for the user to confirm than a screenshot. Export a legend (id, description, xyz).

## 8. Fitting the parameter block to measurements

Once measurements outnumber the parameters, fit `P` to them instead of hand-tuning:
- Residuals in mm: pixel error × mm/px at that point's depth.
- Huber loss (δ ≈ 1–3 mm), so one bad click doesn't drag the fit.
- Regularize toward the current `P` so parameters no measurement touches don't drift.
- A bounded pattern search over a chosen parameter subset is robust and simple; a CadQuery
  rebuild per evaluation is fine for a few hundred evaluations.
- Validate the fitter first with a **synthetic recovery test**: generate measurements from a
  known different `P`, fit from the current one, and check that the shape comes back.
- Expect parameters to **trade off** (a width plus a chamfer, a radius versus a length).
  Report the shape error, and pin the ambiguous ones with a caliper reading.

## 9. Thresholds

| Measure | Accept | Investigate | Stop |
|---|---|---|---|
| Plane-fit residual (rectify) | ≤ 0.2 mm | 0.2–0.5 mm | > 0.5 mm |
| Camera solve reprojection (real photo) | ≤ 0.3% of width | 0.3–1% | > 1% |
| Triangulation ray gap | ≤ 1 mm | 1–3 mm | > 3 mm |
| Matched-render silhouette IoU | ≥ 0.97 | 0.93–0.97 | < 0.93 |
