#!/usr/bin/env python3
"""
rectify_plane.py - turn an angled photo of a part on a flat scale reference (cutting mat,
graph paper, ruler sheet) into a true top-down image in mm, and measure in it.

Two-point px/mm (calibrate.py) is only right for a photo taken square to the mat. Any tilt
makes the scale vary across the frame. With >= 4 points on the reference plane whose mm
coordinates you know (grid intersections), a homography removes the perspective exactly
FOR FEATURES ON THAT PLANE.

  python rectify_plane.py IMG.jpg --pts "u1,v1,x1,y1;u2,v2,x2,y2;..." --mmpx 0.1 --out rect/
      -> rect/rectified.png (x right, y up, origin at the mm origin you chose)
         rect/homography.json  (H image->mm, residual per point in mm)
  python rectify_plane.py IMG.jpg --load rect/homography.json --measure "u1,v1;u2,v2"
      -> distance in mm between two image points (both must lie on the plane)

Pick points spread over the whole mat area around the part: 6-12 grid corners, not four
adjacent ones. The residual report tells you whether the plane fit holds (lens distortion
and a warped mat show up here). Anything ABOVE the plane (the part's top surface, a raised
feature) is still wrong in the rectified image, by a factor of (camera height)/(camera
height - feature height). For heights, solve the camera (solve_camera.py) and use two views
(references/camera-and-multiview.md).
"""
import argparse, json, os
import numpy as np
import cv2


def parse_pts(s):
    rows = [list(map(float, p.split(','))) for p in s.strip().strip(';').split(';')]
    return np.array(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image'); ap.add_argument('--pts', help='"u,v,x_mm,y_mm;..." (>= 4 plane points)')
    ap.add_argument('--load', help='homography.json from a previous run'); ap.add_argument('--measure', help='"u1,v1;u2,v2"')
    ap.add_argument('--mmpx', type=float, default=0.1, help='output resolution, mm per pixel'); ap.add_argument('--out', default='rect')
    a = ap.parse_args()
    img = cv2.imread(a.image)
    if img is None: raise SystemExit('cannot read ' + a.image)
    if a.load:
        H = np.array(json.load(open(a.load))['H'])
    else:
        P = parse_pts(a.pts)
        if len(P) < 4: raise SystemExit('need >= 4 plane points')
        H, _ = cv2.findHomography(P[:, :2], P[:, 2:4], 0)
        pr = cv2.perspectiveTransform(P[:, None, :2], H)[:, 0]
        res = np.linalg.norm(pr - P[:, 2:4], axis=1)
        os.makedirs(a.out, exist_ok=True)
        print('plane fit: mean residual %.3f mm, max %.3f mm over %d points' % (res.mean(), res.max(), len(P)))
        if res.max() > 0.5: print('WARNING: residual > 0.5 mm - lens distortion, a warped mat, or a mis-clicked point')
        # rectified image covering the mm extent of the image corners
        h, w = img.shape[:2]
        corners = cv2.perspectiveTransform(np.array([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]], float), H)[:, 0]
        lo, hi = corners.min(0), corners.max(0)
        span = (hi - lo) / a.mmpx
        if span.max() > 8000:        # guard against near-horizon extents
            lo, hi = P[:, 2:4].min(0) - 40, P[:, 2:4].max(0) + 40; span = (hi - lo) / a.mmpx
        S = np.array([[1 / a.mmpx, 0, -lo[0] / a.mmpx], [0, -1 / a.mmpx, hi[1] / a.mmpx], [0, 0, 1]])   # mm -> px, y up
        out = cv2.warpPerspective(img, S @ H, (int(span[0]), int(span[1])))
        cv2.imwrite(os.path.join(a.out, 'rectified.png'), out)
        json.dump(dict(H=H.tolist(), mm_to_px=S.tolist(), mmpx=a.mmpx, origin_mm=[float(lo[0]), float(hi[1])],
                       residual_mm=res.round(3).tolist(), mean_residual_mm=float(res.mean())),
                  open(os.path.join(a.out, 'homography.json'), 'w'), indent=1)
        print('rectified image %dx%d px at %.3f mm/px -> %s' % (out.shape[1], out.shape[0], a.mmpx, os.path.join(a.out, 'rectified.png')))
    if a.measure:
        M = np.array([list(map(float, p.split(','))) for p in a.measure.split(';')])
        mm = cv2.perspectiveTransform(M[:, None, :], H)[:, 0]
        print('points (mm):', mm.round(2).tolist(), '| distance %.2f mm' % np.linalg.norm(mm[1] - mm[0]))


if __name__ == '__main__':
    main()
