#!/usr/bin/env python3
"""
solve_camera.py - recover the camera of a reference image from landmarks with known 3D
model positions, so the model can be rendered (and markers projected) from exactly that view.

Scans focal length, runs cv2.solvePnP at each, keeps the lowest mean reprojection error.
Writes a renderer-neutral camera {pos, target, up, fov(deg, vertical), w, h, f, mean_err_px}.
Optionally projects extra 3D markers onto the image (mocap-style overlay).

Usage:
  python solve_camera.py --image ref.jpg --points landmarks.csv --out cam.json \
         [--overlay overlay.png] [--markers markers.csv]
  landmarks.csv : id,x_mm,y_mm,z_mm,u_px,v_px         (>= 5 points, spread out)
  markers.csv   : id,x_mm,y_mm,z_mm                    (projected and drawn, optional)

Read the per-point errors: one landmark far above the rest is a misplaced click or a part
whose height in the reference differs from the model. Thresholds are in
references/photo-matching-and-markers.md section 10.

Three.js: camera.position.set(...pos); camera.up.set(...up); camera.fov = fov; lookAt(target).
Fusion:   viewport.camera eye=pos target=target upVector=up, perspectiveAngle=radians(fov).
"""
import argparse, csv, json, math
import numpy as np
import cv2


def read_csv(path):
    with open(path) as f:
        return [r for r in csv.DictReader(f)]


def solve(P3, P2, W, H, fmin, fmax, steps=160):
    best = None
    for f in np.linspace(fmin, fmax, steps):
        K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
        ok, rv, tv = cv2.solvePnP(P3, P2, K, None, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            continue
        pr, _ = cv2.projectPoints(P3, rv, tv, K, None)
        err = np.linalg.norm(pr[:, 0] - P2, axis=1)
        if best is None or err.mean() < best[0]:
            best = (err.mean(), f, rv, tv, err)
    if best is None:
        raise SystemExit('solvePnP failed at every focal length; check the point pairs')
    return best


def camera_json(f, rv, tv, W, H, err):
    R, _ = cv2.Rodrigues(rv)
    C = (-R.T @ tv).ravel(); fwd = R.T @ np.array([0, 0, 1.0]); up = R.T @ np.array([0, -1.0, 0])
    return dict(pos=C.tolist(), target=(C + 200 * fwd).tolist(), up=up.tolist(),
                fov=math.degrees(2 * math.atan(H / 2 / f)), w=W, h=H, f=float(f), mean_err_px=float(err.mean()))


def project(cam, pts):
    pos, tgt, up = map(np.array, (cam['pos'], cam['target'], cam['up']))
    z = tgt - pos; z /= np.linalg.norm(z); x = np.cross(z, up); x /= np.linalg.norm(x); y = np.cross(z, x)
    R = np.vstack([x, y, z]); out = []
    for p in pts:
        q = R @ (np.asarray(p, float) - pos)
        out.append((cam['w'] / 2 + cam['f'] * q[0] / q[2], cam['h'] / 2 + cam['f'] * q[1] / q[2]) if q[2] > 0 else None)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', required=True); ap.add_argument('--points', required=True); ap.add_argument('--out', default='cam.json')
    ap.add_argument('--fmin', type=float); ap.add_argument('--fmax', type=float)
    ap.add_argument('--overlay'); ap.add_argument('--markers')
    a = ap.parse_args()
    img = cv2.imread(a.image); H, W = img.shape[:2]
    rows = read_csv(a.points)
    P3 = np.array([[float(r['x_mm']), float(r['y_mm']), float(r['z_mm'])] for r in rows])
    P2 = np.array([[float(r['u_px']), float(r['v_px'])] for r in rows])
    e, f, rv, tv, err = solve(P3, P2, W, H, a.fmin or 0.4 * W, a.fmax or 4.0 * W)
    cam = camera_json(f, rv, tv, W, H, err)
    json.dump(cam, open(a.out, 'w'), indent=1)
    print('focal %.0f px (vertical FOV %.2f deg), mean reprojection %.1f px = %.2f%% of width' % (f, cam['fov'], e, 100 * e / W))
    for r, ee in zip(rows, err):
        print('  %-6s %6.1f px' % (r['id'], ee))
    print('camera at', np.round(cam['pos'], 1).tolist())
    if a.overlay:
        out = img.copy()
        pr = project(cam, P3)
        for r, uv, obs in zip(rows, pr, P2):
            cv2.circle(out, (int(obs[0]), int(obs[1])), 7, (0, 255, 0), 2)
            if uv: cv2.circle(out, (int(uv[0]), int(uv[1])), 5, (255, 216, 77), -1); cv2.line(out, (int(obs[0]), int(obs[1])), (int(uv[0]), int(uv[1])), (0, 0, 255), 2)
            cv2.putText(out, r['id'], (int(obs[0]) + 9, int(obs[1]) - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if a.markers:
            mk = read_csv(a.markers)
            for r, uv in zip(mk, project(cam, [[float(r['x_mm']), float(r['y_mm']), float(r['z_mm'])] for r in mk])):
                if uv:
                    cv2.circle(out, (int(uv[0]), int(uv[1])), 6, (77, 211, 255), -1); cv2.circle(out, (int(uv[0]), int(uv[1])), 6, (20, 20, 20), 2)
                    cv2.putText(out, r['id'], (int(uv[0]) + 8, int(uv[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.imwrite(a.overlay, out)
        print('overlay ->', a.overlay, '(green = clicked, dot = reprojected, red = error)')


if __name__ == '__main__':
    main()
