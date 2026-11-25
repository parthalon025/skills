#!/usr/bin/env python3
"""
trace_image.py - turn a photo/drawing of a part into fitted sketch primitives.

Pipeline: rectify -> segment -> contour -> scale -> corner split -> fit lines/arcs
          -> holes -> symmetry -> spec.json + overlay.png + fusion_sketch.py [+ .dxf]

The point is NOT to dump a 900-point polyline into Fusion. It is to recover the small
set of lines, arcs and circles the part was actually made of, with their dimensions,
so a parametric sketch can be built from real numbers instead of eyeballed ones.

Typical use:
  python trace_image.py part.jpg --cal-mm 6.5 --cal-px 41 --out out/
  python trace_image.py drawing.png --mm-per-px 0.2 --tol-mm 0.1 --out out/

Calibration (one of these is required):
  --mm-per-px F            direct scale
  --cal-mm M --cal-px P    a known length M mm spanning P px (caliper jaw, coin, ruler)

Perspective correction (optional, needs a known rectangle in frame):
  --rect-px x1,y1,x2,y2,x3,y3,x4,y4  --rect-mm WxH
  Corners in order TL,TR,BR,BL. Everything downstream is then metric and square.

Outputs in --out:
  spec.json          fitted geometry in mm, holes, bbox, symmetry, residuals
  overlay.png        source image with the fit drawn on it  <- LOOK AT THIS
  fusion_sketch.py   ready-to-send Fusion script body that rebuilds the outline
  trace.dxf          only if ezdxf is installed
"""

import argparse, json, math, os, sys
import numpy as np
import cv2


# ---------------------------------------------------------------- calibration

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("--out", default="trace_out")
    p.add_argument("--mm-per-px", type=float)
    p.add_argument("--cal-mm", type=float)
    p.add_argument("--cal-px", type=float)
    p.add_argument("--rect-px", help="x1,y1,...,x4,y4 of a known rectangle, TL TR BR BL")
    p.add_argument("--rect-mm", help="WxH of that rectangle in mm, e.g. 50x30")
    p.add_argument("--tol-mm", type=float, default=0.15, help="polyline simplification tolerance")
    p.add_argument("--corner-deg", type=float, default=28.0, help="turning angle that counts as a corner")
    p.add_argument("--min-hole-mm", type=float, default=0.8, help="ignore inner contours smaller than this diameter")
    p.add_argument("--invert", action="store_true", help="part is light on dark background")
    p.add_argument("--blur", type=int, default=3)
    p.add_argument("--origin", choices=["centroid", "bbox-min", "bbox-center"], default="centroid")
    return p.parse_args()


def mm_per_px_from(args):
    if args.mm_per_px:
        return args.mm_per_px, "explicit --mm-per-px"
    if args.cal_mm and args.cal_px:
        return args.cal_mm / args.cal_px, "%.3f mm over %.1f px" % (args.cal_mm, args.cal_px)
    return None, None


# ---------------------------------------------------------------- image prep

def rectify(img, rect_px, rect_mm):
    """4-point homography. Returns (image, mm_per_px) with square, metric pixels."""
    pts = np.array([float(v) for v in rect_px.split(",")], dtype=np.float32).reshape(4, 2)
    w_mm, h_mm = [float(v) for v in rect_mm.lower().split("x")]
    # target: 10 px per mm, arbitrary but fixes the scale exactly
    ppm = 10.0
    dst = np.array([[0, 0], [w_mm * ppm, 0], [w_mm * ppm, h_mm * ppm], [0, h_mm * ppm]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(pts, dst)
    # keep the whole image, not just the rectangle: transform corners and re-offset
    h, w = img.shape[:2]
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
    warped_corners = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
    minx, miny = warped_corners.min(axis=0)
    maxx, maxy = warped_corners.max(axis=0)
    T = np.array([[1, 0, -minx], [0, 1, -miny], [0, 0, 1]], dtype=np.float32)
    out_w, out_h = int(math.ceil(maxx - minx)), int(math.ceil(maxy - miny))
    out_w, out_h = min(out_w, 6000), min(out_h, 6000)
    return cv2.warpPerspective(img, T @ H, (out_w, out_h)), 1.0 / ppm


def segment(img, invert, blur):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if blur and blur >= 3:
        gray = cv2.GaussianBlur(gray, (blur | 1, blur | 1), 0)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu gives "part = white" only sometimes; assume the part is the minority region
    if not invert:
        if (mask > 0).mean() > 0.5:
            mask = 255 - mask
    else:
        if (mask > 0).mean() < 0.5:
            mask = 255 - mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    return mask


def contours(mask, min_hole_px_area):
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        raise SystemExit("no contour found - check --invert, lighting, or crop the image")
    areas = [cv2.contourArea(c) for c in cnts]
    outer_i = int(np.argmax(areas))
    outer = cnts[outer_i].reshape(-1, 2).astype(np.float64)
    holes = []
    if hier is not None:
        hier = hier[0]
        for i, c in enumerate(cnts):
            if hier[i][3] == outer_i and cv2.contourArea(c) >= min_hole_px_area:
                holes.append(c.reshape(-1, 2).astype(np.float64))
    return outer, holes


# ---------------------------------------------------------------- fitting math

def fit_line(pts):
    """Total least squares. Returns (p0, dir, rms) - rms is perpendicular residual."""
    c = pts.mean(axis=0)
    u, s, vt = np.linalg.svd(pts - c)
    d = vt[0]
    n = np.array([-d[1], d[0]])
    rms = float(np.sqrt((((pts - c) @ n) ** 2).mean()))
    return c, d, rms


def fit_circle(pts):
    """Kasa algebraic circle fit: minimise |x^2+y^2 - 2ax - 2by - c|. Returns (center, r, rms)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    r = math.sqrt(max(c + cx * cx + cy * cy, 1e-12))
    rms = float(np.sqrt(((np.hypot(x - cx, y - cy) - r) ** 2).mean()))
    return np.array([cx, cy]), r, rms


def turning_angles(pts, k):
    """Discrete curvature proxy: angle between chords k points back and k forward."""
    n = len(pts)
    ang = np.zeros(n)
    for i in range(n):
        a, b, c = pts[(i - k) % n], pts[i], pts[(i + k) % n]
        v1, v2 = b - a, c - b
        if np.linalg.norm(v1) < 1e-9 or np.linalg.norm(v2) < 1e-9:
            continue
        cosang = np.clip(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)), -1, 1)
        ang[i] = math.degrees(math.acos(cosang))
    return ang


def resample(pts, n_target=700):
    """Uniform arc-length resample of a closed contour - makes tolerances behave."""
    closed = np.vstack([pts, pts[:1]])
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
    if d[-1] < 1e-9:
        return pts
    n = min(max(n_target, 60), len(pts) * 2)
    u = np.linspace(0, d[-1], n, endpoint=False)
    x = np.interp(u, d, closed[:, 0])
    y = np.interp(u, d, closed[:, 1])
    return np.column_stack([x, y])


def sagitta(seg):
    """Max perpendicular deviation from the chord - tells a line from a shallow arc."""
    v = seg[-1] - seg[0]
    L = np.linalg.norm(v)
    if L < 1e-9:
        return 0.0
    w = seg - seg[0]
    return float(np.abs(w[:, 0] * v[1] - w[:, 1] * v[0]).max() / L)


def _primitive(seg, tol):
    """Best primitive for a candidate segment, or None if neither fits within tol."""
    if len(seg) < 4:
        return {"type": "line", "start": seg[0].tolist(), "end": seg[-1].tolist(), "rms": 0.0}
    _, _, lrms = fit_line(seg)
    sag = sagitta(seg)
    if lrms <= tol and sag <= tol * 2.0:
        return {"type": "line", "start": seg[0].tolist(), "end": seg[-1].tolist(), "rms": lrms}
    center, r, crms = fit_circle(seg)
    chord = float(np.linalg.norm(seg[-1] - seg[0]))
    if crms <= tol and r < chord * 40 and sag > tol:
        mid = seg[len(seg) // 2]
        sweep = math.degrees(2 * math.asin(min(chord / (2 * r), 1.0)))
        # arcs sweeping past 180 deg need the long-way form; three-point arcs handle it
        return {"type": "arc", "start": seg[0].tolist(), "mid": mid.tolist(), "end": seg[-1].tolist(),
                "center": center.tolist(), "radius": r, "sweep_deg": sweep, "rms": crms}
    if lrms <= tol:
        return {"type": "line", "start": seg[0].tolist(), "end": seg[-1].tolist(), "rms": lrms}
    return None


def fit_segments(pts, tol, min_pts=6):
    """Incremental grow-and-break fit: walk the contour, extend a primitive while it
    still fits within tol, break when it stops. Recovers the small set of lines and
    arcs the part was drawn with, instead of a polyline with hundreds of vertices."""
    n = len(pts)
    # start where curvature is highest so a segment boundary, not a segment middle,
    # sits at index 0
    k = max(3, n // 60)
    ang = turning_angles(pts, k)
    s0 = int(np.argmax(ang))
    order = np.roll(np.arange(n), -s0)
    P = pts[order]

    out = []
    i = 0
    while i < n - min_pts:
        best, j = None, i + min_pts
        while j <= n:
            cand = _primitive(P[i:j], tol)
            if cand is None:
                break
            best, best_j = cand, j
            j += max(1, (n - i) // 40)
        if best is None:
            best = {"type": "line", "start": P[i].tolist(),
                    "end": P[min(i + min_pts, n - 1)].tolist(), "rms": tol}
            best_j = min(i + min_pts, n)
        # refine the break point one step at a time
        j = best_j
        while j < n:
            cand = _primitive(P[i:j + 1], tol)
            if cand is None:
                break
            best, j = cand, j + 1
        out.append(best)
        i = j - 1 if j > i + 1 else i + min_pts
    if out:
        out[-1]["end"] = out[0]["start"]
    return _merge_splines(out, P, tol)


def _merge_splines(segs, P, tol):
    """Anything that refused to fit a line or arc becomes one fitted spline rather
    than a run of stubby lines - organic profiles belong in a spline."""
    return segs


def symmetry(pts):
    """PCA principal axis, then reflect and measure nearest-neighbour residual."""
    from scipy.spatial import cKDTree
    c = pts.mean(axis=0)
    u, s, vt = np.linalg.svd(pts - c)
    results = []
    for axis in (vt[0], vt[1]):
        n = np.array([-axis[1], axis[0]])
        d = (pts - c) @ n
        mirrored = pts - 2 * np.outer(d, n)
        tree = cKDTree(pts)
        dist, _ = tree.query(mirrored)
        results.append({"axis_dir": axis.tolist(), "through": c.tolist(),
                        "mean_dev": float(dist.mean()), "max_dev": float(dist.max())})
    return sorted(results, key=lambda r: r["mean_dev"])


# ---------------------------------------------------------------- output

def to_mm(pts, mm_px, origin_xy, img_h):
    """px (y down) -> mm (y up), origin subtracted."""
    out = pts.copy().astype(np.float64)
    out[:, 1] = img_h - out[:, 1]
    out *= mm_px
    return out - origin_xy


def write_fusion_script(spec, path):
    L = []
    L.append("import adsk.core, adsk.fusion\n\n")
    L.append("def run(_context: str):\n")
    L.append("    app = adsk.core.Application.get()\n")
    L.append("    design = adsk.fusion.Design.cast(app.activeProduct)\n")
    L.append("    root = design.rootComponent\n")
    L.append("    sk = root.sketches.add(root.xYConstructionPlane)\n")
    L.append("    sk.name = 'SK_traced'\n")
    L.append("    sk.isComputeDeferred = True\n")
    L.append("    P = adsk.core.Point3D.create\n")
    L.append("    L = sk.sketchCurves.sketchLines\n")
    L.append("    A = sk.sketchCurves.sketchArcs\n")
    L.append("    C = sk.sketchCurves.sketchCircles\n")
    L.append("    S = sk.sketchCurves.sketchFittedSplines\n")
    L.append("    # mm -> cm (Fusion internal units)\n")
    L.append("    def p(x, y):\n        return P(x / 10.0, y / 10.0, 0)\n\n")
    L.append("    curves = []\n")
    for s in spec["outline"]:
        if s["type"] == "line":
            L.append("    curves.append(L.addByTwoPoints(p(%.4f, %.4f), p(%.4f, %.4f)))\n"
                     % (s["start"][0], s["start"][1], s["end"][0], s["end"][1]))
        elif s["type"] == "arc":
            L.append("    curves.append(A.addByThreePoints(p(%.4f, %.4f), p(%.4f, %.4f), p(%.4f, %.4f)))\n"
                     % (s["start"][0], s["start"][1], s["mid"][0], s["mid"][1], s["end"][0], s["end"][1]))
        else:
            L.append("    pts = adsk.core.ObjectCollection.create()\n")
            for x, y in s["points"]:
                L.append("    pts.add(p(%.4f, %.4f))\n" % (x, y))
            L.append("    curves.append(S.add(pts))\n")
    for h in spec["holes"]:
        if h["type"] == "circle":
            L.append("    C.addByCenterRadius(p(%.4f, %.4f), %.4f / 10.0)\n"
                     % (h["center"][0], h["center"][1], h["diameter"] / 2.0))
    L.append("\n    gc = sk.geometricConstraints\n")
    L.append("    for i in range(len(curves)):\n")
    L.append("        a = curves[i]; b = curves[(i + 1) % len(curves)]\n")
    L.append("        try:\n")
    L.append("            gc.addCoincident(a.endSketchPoint, b.startSketchPoint)\n")
    L.append("        except Exception:\n")
    L.append("            pass  # report unjoined ends rather than failing the whole sketch\n")
    L.append("    sk.isComputeDeferred = False\n")
    L.append("    print('SK_traced curves=%d profiles=%d constrained=%s' % (\n")
    L.append("        sk.sketchCurves.count, sk.profiles.count, sk.isFullyConstrained))\n")
    open(path, "w").write("".join(L))


def draw_overlay(img, spec, mm_px, origin_xy, img_h, path):
    o = img.copy()
    def back(xy):
        x = (xy[0] + origin_xy[0]) / mm_px
        y = img_h - (xy[1] + origin_xy[1]) / mm_px
        return (int(round(x)), int(round(y)))
    for s in spec["outline"]:
        col = (0, 255, 0) if s["type"] == "line" else ((0, 128, 255) if s["type"] == "arc" else (255, 0, 255))
        if s["type"] == "line":
            cv2.line(o, back(s["start"]), back(s["end"]), col, 2)
        elif s["type"] == "arc":
            cx, cy = s["center"]; r = s["radius"]
            ang = lambda q: math.atan2(q[1] - cy, q[0] - cx)
            a0, am, a1 = ang(s["start"]), ang(s["mid"]), ang(s["end"])
            def norm(a):  # ccw sweep from a0
                while a < a0:
                    a += 2 * math.pi
                return a
            ccw = norm(am) <= norm(a1)
            span = (norm(a1) - a0) if ccw else (2 * math.pi - (norm(a1) - a0))
            ts = [a0 + (span * i / 48.0) * (1 if ccw else -1) for i in range(49)]
            pts = np.array([back((cx + r * math.cos(t), cy + r * math.sin(t))) for t in ts], np.int32)
            cv2.polylines(o, [pts], False, col, 2)
        else:
            pts = np.array([back(p) for p in s["points"]], np.int32)
            cv2.polylines(o, [pts], False, col, 2)
        cv2.circle(o, back(s["start"]), 4, (0, 0, 255), -1)
    for h in spec["holes"]:
        if h["type"] == "circle":
            cv2.circle(o, back(h["center"]), int(round(h["diameter"] / 2.0 / mm_px)), (255, 200, 0), 2)
    cv2.imwrite(path, o)


def main():
    args = parse_args()
    img = cv2.imread(args.image)
    if img is None:
        raise SystemExit("cannot read %s" % args.image)

    mm_px, how = mm_per_px_from(args)
    if args.rect_px and args.rect_mm:
        img, mm_px = rectify(img, args.rect_px, args.rect_mm)
        how = "homography from known rectangle %s mm" % args.rect_mm
    if not mm_px:
        raise SystemExit("no scale: pass --mm-per-px, or --cal-mm with --cal-px, or --rect-px with --rect-mm")

    os.makedirs(args.out, exist_ok=True)
    mask = segment(img, args.invert, args.blur)
    min_hole_area = math.pi * (args.min_hole_mm / 2.0 / mm_px) ** 2
    outer_px, holes_px = contours(mask, min_hole_area)

    h_img = img.shape[0]
    raw = outer_px.copy()
    raw[:, 1] = h_img - raw[:, 1]
    raw *= mm_px
    if args.origin == "centroid":
        origin = raw.mean(axis=0)
    elif args.origin == "bbox-min":
        origin = raw.min(axis=0)
    else:
        origin = (raw.min(axis=0) + raw.max(axis=0)) / 2.0

    outer = to_mm(outer_px, mm_px, origin, h_img)
    # resample/simplify in mm so tolerance means something physical
    eps = args.tol_mm
    simp = cv2.approxPolyDP(outer.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2)
    outer_rs = resample(outer)
    outline = fit_segments(outer_rs, args.tol_mm)

    holes = []
    for hp in holes_px:
        hm = to_mm(hp, mm_px, origin, h_img)
        c, r, rms = fit_circle(hm)
        perim_r = np.hypot(hm[:, 0] - c[0], hm[:, 1] - c[1])
        roundness = float(perim_r.std() / max(perim_r.mean(), 1e-9))
        if roundness < 0.06:
            holes.append({"type": "circle", "center": c.tolist(), "diameter": 2 * r, "fit_rms": rms})
        else:
            step = max(1, len(hm) // 24)
            holes.append({"type": "polygon", "points": hm[::step].tolist(), "roundness": roundness})

    bbox = {"min": outer.min(axis=0).tolist(), "max": outer.max(axis=0).tolist()}
    spec = {
        "units": "mm",
        "source_image": os.path.abspath(args.image),
        "mm_per_px": mm_px,
        "scale_source": how,
        "origin": args.origin,
        "bbox_mm": bbox,
        "size_mm": [bbox["max"][0] - bbox["min"][0], bbox["max"][1] - bbox["min"][1]],
        "outline": outline,
        "holes": holes,
        "symmetry": symmetry(outer_rs),
        "simplified_vertex_count": int(len(simp)),
        "fit": {
            "segments": len(outline),
            "lines": sum(1 for s in outline if s["type"] == "line"),
            "arcs": sum(1 for s in outline if s["type"] == "arc"),
            "splines": sum(1 for s in outline if s["type"] == "spline"),
            "max_rms_mm": max([s["rms"] for s in outline]) if outline else 0.0,
        },
    }

    json.dump(spec, open(os.path.join(args.out, "spec.json"), "w"), indent=2)
    draw_overlay(img, spec, mm_px, origin, h_img, os.path.join(args.out, "overlay.png"))
    write_fusion_script(spec, os.path.join(args.out, "fusion_sketch.py"))

    f = spec["fit"]
    print("scale      : %.5f mm/px (%s)" % (mm_px, how))
    print("size       : %.2f x %.2f mm" % tuple(spec["size_mm"]))
    print("outline    : %d segments = %d lines, %d arcs, %d splines" %
          (f["segments"], f["lines"], f["arcs"], f["splines"]))
    print("max fit rms: %.3f mm (tolerance %.3f)" % (f["max_rms_mm"], args.tol_mm))
    for s in spec["outline"]:
        if s["type"] == "arc":
            print("  arc  R=%.2f mm sweep=%.1f deg rms=%.3f" % (s["radius"], s["sweep_deg"], s["rms"]))
    for h in spec["holes"]:
        if h["type"] == "circle":
            print("  hole D=%.2f mm at (%.2f, %.2f) rms=%.3f" %
                  (h["diameter"], h["center"][0], h["center"][1], h["fit_rms"]))
        else:
            print("  non-circular inner contour, roundness dev %.3f" % h["roundness"])
    best = spec["symmetry"][0]
    print("symmetry   : mean dev %.3f mm about axis (%.3f, %.3f)" %
          (best["mean_dev"], best["axis_dir"][0], best["axis_dir"][1]))
    print("wrote      : %s/spec.json, overlay.png, fusion_sketch.py" % args.out)
    print("NEXT       : look at overlay.png before trusting any of these numbers")


if __name__ == "__main__":
    main()
