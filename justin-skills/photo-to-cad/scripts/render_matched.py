#!/usr/bin/env python3
"""
render_matched.py - render an STL from a photo's solved camera and overlay it on the photo.

Orthographic render panels (render_views.py) are good for shape, but a photo is a
perspective projection from wherever the phone was. Comparing the two mixes camera error
into model error. This renders the model from the SAME camera as the photo (solve it with
solve_camera.py), then composites:

  panel 1  photo
  panel 2  model from the photo's camera (shaded)
  panel 3  50/50 blend              <- where disagreements jump out
  panel 4  model silhouette outline drawn on the photo
  (+ IoU vs a part mask of the photo, if --mask is given)

Usage:
  python render_matched.py part.stl photo.jpg cam.json out.png [--mask part_mask.png] [--scale 0.5]
cam.json: {pos, target, up, fov (vertical deg), w, h}  - from solve_camera.py
Model units must match the camera's (mm). Pure numpy + PIL; no GPU, no mesh library.
"""
import argparse, json, math, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def load_stl(path):
    with open(path, 'rb') as f:
        head = f.read(80); n = struct.unpack('<I', f.read(4))[0]; data = f.read()
    if len(data) >= n * 50 and not head.lstrip().lower().startswith(b'solid') or len(data) == n * 50:
        rec = np.frombuffer(data[:n * 50], dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]))
        return rec['v'].astype(float)
    txt = open(path).read().split(); tri, cur = [], []
    for i, t in enumerate(txt):
        if t == 'vertex':
            cur.append([float(txt[i + 1]), float(txt[i + 2]), float(txt[i + 3])])
            if len(cur) == 3: tri.append(cur); cur = []
    return np.array(tri, float)


def camera(c, scale):
    W, H = int(c['w'] * scale), int(c['h'] * scale)
    f = (H / 2) / math.tan(math.radians(c['fov']) / 2)
    pos, tgt, up = map(np.array, (c['pos'], c['target'], c['up']))
    z = tgt - pos; z /= np.linalg.norm(z); x = np.cross(z, up); x /= np.linalg.norm(x); y = np.cross(z, x)
    return pos, np.vstack([x, y, z]), f, W, H


def render(tris, c, scale):
    pos, R, f, W, H = camera(c, scale)
    q = (tris - pos) @ R.T                                   # camera coords (x right, y down, z forward)
    keep = (q[:, :, 2] > 1e-3).all(1); q = q[keep]; t = tris[keep]
    uv = np.stack([W / 2 + f * q[:, :, 0] / q[:, :, 2], H / 2 + f * q[:, :, 1] / q[:, :, 2]], -1)
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    view = pos - t.mean(1); view /= np.linalg.norm(view, axis=1, keepdims=True)
    light = np.abs((nrm * view).sum(1))                       # two-sided headlight shading
    order = np.argsort(-q[:, :, 2].mean(1))                   # painter's algorithm: far first
    img = Image.new('RGB', (W, H), (38, 40, 44)); msk = Image.new('L', (W, H), 0)
    d, dm = ImageDraw.Draw(img), ImageDraw.Draw(msk)
    for i in order:
        p = [tuple(v) for v in uv[i]]; g = int(60 + 170 * light[i])
        col = (g, g, int(g * 1.03)); d.polygon(p, fill=col, outline=col); dm.polygon(p, fill=255, outline=255)
    return img, msk


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stl'); ap.add_argument('photo'); ap.add_argument('cam'); ap.add_argument('out')
    ap.add_argument('--mask'); ap.add_argument('--scale', type=float, default=0.5); ap.add_argument('--max-tris', type=int, default=150000)
    a = ap.parse_args()
    tris = load_stl(a.stl)
    if len(tris) > a.max_tris: tris = tris[:: int(math.ceil(len(tris) / a.max_tris))]
    c = json.load(open(a.cam))
    ren, msk = render(tris, c, a.scale)
    ph = Image.open(a.photo).convert('RGB').resize(ren.size)
    blend = Image.blend(ph, ren, 0.5)
    msk = msk.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))          # close raster cracks
    edge = msk.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
    outl = ph.copy(); outl.paste((255, 211, 77), mask=edge)
    W, H = ren.size; sheet = Image.new('RGB', (W * 2 + 10, H * 2 + 10), (25, 25, 25))
    for k, im in enumerate([ph, ren, blend, outl]): sheet.paste(im, ((k % 2) * (W + 10), (k // 2) * (H + 10)))
    for k, lab in enumerate(['photo', 'model, same camera', '50/50 blend', 'model outline on photo']):
        ImageDraw.Draw(sheet).text(((k % 2) * (W + 10) + 8, (k // 2) * (H + 10) + 6), lab, fill=(255, 255, 0))
    sheet.save(a.out)
    msg = 'rendered %d triangles at %dx%d -> %s' % (len(tris), W, H, a.out)
    if a.mask:
        pm = np.asarray(Image.open(a.mask).convert('L').resize(ren.size)) > 127; mm = np.asarray(msk) > 127
        inter, uni = (pm & mm).sum(), (pm | mm).sum()
        msg += ' | silhouette IoU %.3f (model-only %.1f%%, photo-only %.1f%%)' % (inter / max(uni, 1), 100 * (mm & ~pm).sum() / max(uni, 1), 100 * (pm & ~mm).sum() / max(uni, 1))
    print(msg)


if __name__ == '__main__':
    main()
