#!/usr/bin/env python3
"""
compare_silhouette.py - turn "looks about right" into a number.

Compares the silhouette of a Fusion screenshot against the reference image (or against
a traced outline) and reports IoU, contour distance, Hausdorff distance and bbox deltas.
Run it after every build increment where the reference is a photo or drawing - it catches
the proportion errors that the eye forgives and the caliper does not.

Two modes:

  shape only (default)   --align bbox
      Scales the model silhouette onto the reference bbox first, so the answer is about
      SHAPE, not size. Use when the screenshot has no known scale.

  metric                 --mm-per-px-model F --mm-per-px-ref F
      No rescaling. Distances come out in mm and bbox deltas are real dimensional errors.
      Use when you can pin both scales - this is the one that finds a wrong dimension.

Usage:
  python compare_silhouette.py --model shot.png --ref part.png --out cmp/
  python compare_silhouette.py --model shot.png --ref part.png \
         --mm-per-px-model 0.21 --mm-per-px-ref 0.158 --out cmp/

Screenshot the model with transparentBackground:true and the view direction matching the
reference photo, or the comparison measures the camera angle instead of the part.
"""

import argparse, json, os, sys
import numpy as np
import cv2
from scipy.spatial import cKDTree


def silhouette(path, invert=False):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit("cannot read %s" % path)
    if img.ndim == 3 and img.shape[2] == 4 and img[:, :, 3].min() < 250:
        mask = (img[:, :, 3] > 127).astype(np.uint8) * 255
    else:
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if ((mask > 0).mean() > 0.5) != invert:
            mask = 255 - mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        raise SystemExit("no silhouette in %s (try --invert)" % path)
    big = max(cnts, key=cv2.contourArea)
    clean = np.zeros_like(mask)
    cv2.drawContours(clean, [big], -1, 255, -1)
    return clean, big.reshape(-1, 2).astype(np.float64)


def bbox(c):
    return c.min(axis=0), c.max(axis=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Fusion screenshot PNG")
    ap.add_argument("--ref", required=True, help="reference photo/drawing")
    ap.add_argument("--out", default="cmp_out")
    ap.add_argument("--align", choices=["bbox", "none"], default="bbox")
    ap.add_argument("--mm-per-px-model", type=float)
    ap.add_argument("--mm-per-px-ref", type=float)
    ap.add_argument("--invert-model", action="store_true")
    ap.add_argument("--invert-ref", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    m_mask, m_c = silhouette(a.model, a.invert_model)
    r_mask, r_c = silhouette(a.ref, a.invert_ref)

    metric = bool(a.mm_per_px_model and a.mm_per_px_ref)
    if metric:
        m_c = m_c * a.mm_per_px_model
        r_c = r_c * a.mm_per_px_ref
        unit = "mm"
    else:
        unit = "px(ref)"

    m_min, m_max = bbox(m_c)
    r_min, r_max = bbox(r_c)
    m_size, r_size = m_max - m_min, r_max - r_min

    if a.align == "bbox" and not metric:
        s = r_size / np.maximum(m_size, 1e-9)
        s = np.array([min(s), min(s)])          # uniform scale, keeps aspect honest
        m_c = (m_c - m_min) * s + r_min
        m_min, m_max = bbox(m_c)
        m_size = m_max - m_min

    # contour distance both ways
    t_r, t_m = cKDTree(r_c), cKDTree(m_c)
    d_mr, _ = t_r.query(m_c)
    d_rm, _ = t_m.query(r_c)
    hausdorff = float(max(d_mr.max(), d_rm.max()))
    mean_dev = float((d_mr.mean() + d_rm.mean()) / 2.0)

    # IoU on a common raster
    allpts = np.vstack([m_c, r_c])
    lo, hi = allpts.min(axis=0), allpts.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    S = 800.0 / span.max()
    W, H = int(span[0] * S) + 10, int(span[1] * S) + 10
    def raster(c):
        img = np.zeros((H, W), np.uint8)
        cv2.fillPoly(img, [((c - lo) * S + 5).astype(np.int32)], 255)
        return img > 0
    A, B = raster(m_c), raster(r_c)
    inter, union = (A & B).sum(), (A | B).sum()
    iou = float(inter) / float(max(union, 1))

    diff = np.zeros((H, W, 3), np.uint8)
    diff[B] = (60, 60, 200)        # reference only  - red
    diff[A] = (60, 200, 60)        # model only      - green
    diff[A & B] = (90, 90, 90)     # agreement       - grey
    cv2.imwrite(os.path.join(a.out, "diff.png"), diff)

    res = {
        "mode": "metric" if metric else ("shape-only (bbox aligned)" if a.align == "bbox" else "raw pixels"),
        "unit": unit,
        "iou": iou,
        "mean_contour_deviation": mean_dev,
        "hausdorff": hausdorff,
        "model_bbox": m_size.tolist(),
        "ref_bbox": r_size.tolist(),
        "bbox_delta": (m_size - r_size).tolist(),
        "aspect_model": float(m_size[0] / max(m_size[1], 1e-9)),
        "aspect_ref": float(r_size[0] / max(r_size[1], 1e-9)),
    }
    json.dump(res, open(os.path.join(a.out, "compare.json"), "w"), indent=2)

    print("mode        : %s" % res["mode"])
    print("IoU         : %.4f   (>0.98 good, 0.95-0.98 check, <0.95 wrong shape)" % iou)
    print("mean dev    : %.3f %s" % (mean_dev, unit))
    print("hausdorff   : %.3f %s   <- worst single divergence, look there first" % (hausdorff, unit))
    print("bbox model  : %.2f x %.2f %s" % (m_size[0], m_size[1], unit))
    print("bbox ref    : %.2f x %.2f %s" % (r_size[0], r_size[1], unit))
    print("bbox delta  : %+.2f x %+.2f %s" % (res["bbox_delta"][0], res["bbox_delta"][1], unit))
    print("aspect      : model %.4f vs ref %.4f (%+.2f%%)" %
          (res["aspect_model"], res["aspect_ref"],
           100.0 * (res["aspect_model"] / max(res["aspect_ref"], 1e-9) - 1.0)))
    print("wrote       : %s/diff.png  (green = model only, red = reference only)" % a.out)


if __name__ == "__main__":
    main()
