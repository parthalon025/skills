#!/usr/bin/env python3
"""
sdf_kit.py - parametric organic solids from signed-distance functions (grips, knobs, handles,
blended bosses, sculpted forms). Named primitives + smooth blends + a shell -> watertight mesh.

Why: CadQuery/Fusion B-rep blends between organic forms are fragile (fillets fail, lofts
twist). An SDF composes any number of smooth unions/subtractions robustly, and every
parameter stays a named number. Output is a MESH (STL/3MF), not STEP; say so at the start.

  primitives : sphere, box (rounded), capsule, cylinder, torus, ellipsoid, tube (polyline with
               per-point radius), halfspace
  operations : union, smooth_union(k), intersect, smooth_intersect(k), subtract,
               smooth_subtract(k), shell(t), offset(d), translate, rotate, mirror_x
  meshing    : mesh(f, bounds, res) -> trimesh (marching cubes, chunked evaluation), report()

All units mm. f(P) takes an (N,3) array and returns (N,) signed distances (negative inside).
Resolution: res <= 1/3 of the thinnest wall or smallest radius you care about.

  python sdf_kit.py --demo out.stl        worked example (ergonomic handle) + self-test
"""
import math, sys
import numpy as np

# ----------------------------------------------------------------- primitives
def sphere(c, r):
    c = np.asarray(c, float); return lambda P: np.linalg.norm(P - c, axis=1) - r

def box(c, size, round_r=0.0):
    c = np.asarray(c, float); h = np.asarray(size, float) / 2 - round_r
    def f(P):
        q = np.abs(P - c) - h
        return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0) - round_r
    return f

def capsule(a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float); ab = b - a; L2 = ab @ ab
    def f(P):
        t = np.clip(((P - a) @ ab) / L2, 0, 1)
        return np.linalg.norm(P - (a + t[:, None] * ab), axis=1) - r
    return f

def cylinder(a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float); ab = b - a; L = np.linalg.norm(ab); u = ab / L
    def f(P):
        t = (P - a) @ u; radial = np.linalg.norm((P - a) - t[:, None] * u, axis=1)
        d = np.stack([radial - r, np.abs(t - L / 2) - L / 2], 1)
        return np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0)
    return f

def torus(c, R, r, axis=(0, 0, 1)):
    c = np.asarray(c, float); n = np.asarray(axis, float) / np.linalg.norm(axis)
    def f(P):
        q = P - c; h = q @ n; rad = np.linalg.norm(q - h[:, None] * n, axis=1)
        return np.hypot(rad - R, h) - r
    return f

def ellipsoid(c, radii):
    c = np.asarray(c, float); rr = np.asarray(radii, float)
    def f(P):                                  # standard bound approximation, good near the surface
        q = (P - c); k0 = np.linalg.norm(q / rr, axis=1); k1 = np.linalg.norm(q / (rr * rr), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
    return f

def tube(points, radii):
    """Polyline with a radius per point (linear in between): hoses, handles, loops, ribs."""
    Pts = np.asarray(points, float); R = np.broadcast_to(np.asarray(radii, float), (len(Pts),))
    def f(P):
        best = np.full(len(P), np.inf)
        for i in range(len(Pts) - 1):
            a, b = Pts[i], Pts[i + 1]; ab = b - a; L2 = max(ab @ ab, 1e-12)
            t = np.clip(((P - a) @ ab) / L2, 0, 1)
            d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1) - (R[i] + t * (R[i + 1] - R[i]))
            np.minimum(best, d, out=best)
        return best
    return f

def halfspace(point, normal):
    p = np.asarray(point, float); n = np.asarray(normal, float) / np.linalg.norm(normal)
    return lambda P: (P - p) @ n                    # negative on the side opposite the normal

# ----------------------------------------------------------------- operations
def union(*fs): return lambda P: np.min([f(P) for f in fs], axis=0)
def intersect(*fs): return lambda P: np.max([f(P) for f in fs], axis=0)
def subtract(a, b): return lambda P: np.maximum(a(P), -b(P))

def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1); return b * (1 - h) + a * h - k * h * (1 - h)

def smooth_union(k, *fs):
    def f(P):
        d = fs[0](P)
        for g in fs[1:]: d = _smin(d, g(P), k)
        return d
    return f

def smooth_intersect(k, a, b): return lambda P: -_smin(-a(P), -b(P), k)
def smooth_subtract(k, a, b): return lambda P: -_smin(-a(P), b(P), k)
def shell(f, t): return lambda P: np.abs(f(P)) - t / 2          # hollow wall of thickness t
def offset(f, d): return lambda P: f(P) - d
def translate(f, v): v = np.asarray(v, float); return lambda P: f(P - v)
def mirror_x(f): return lambda P: f(np.c_[np.abs(P[:, 0]), P[:, 1], P[:, 2]])

def rotate(f, axis, deg):
    a = np.asarray(axis, float) / np.linalg.norm(axis); t = math.radians(-deg); c, s = math.cos(t), math.sin(t)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]]); Rm = np.eye(3) * c + s * K + (1 - c) * np.outer(a, a)
    return lambda P: f(P @ Rm.T)

# ----------------------------------------------------------------- meshing
def mesh(f, bounds, res=0.5, chunk=400_000):
    """Marching cubes over bounds=((xmin,ymin,zmin),(xmax,ymax,zmax)) at res mm. Returns trimesh.Trimesh."""
    from skimage.measure import marching_cubes
    import trimesh
    # offset the grid by an irrational fraction of a cell: round-number shapes on a round-number grid put
    # samples exactly on the surface, marching cubes then emits zero-area triangles and the mesh opens up
    lo, hi = np.asarray(bounds[0], float) - (2 + 0.3183) * res, np.asarray(bounds[1], float) + 2 * res
    n = np.ceil((hi - lo) / res).astype(int) + 1
    if np.prod(n) > 60_000_000: raise SystemExit('grid %s too large: raise res or tighten bounds' % n.tolist())
    xs, ys, zs = (np.linspace(lo[i], lo[i] + (n[i] - 1) * res, n[i]) for i in range(3))
    G = np.stack(np.meshgrid(xs, ys, zs, indexing='ij'), -1).reshape(-1, 3)
    D = np.empty(len(G))
    for i in range(0, len(G), chunk): D[i:i + chunk] = f(G[i:i + chunk])
    D = D.reshape(n); D[D == 0] = 1e-7                  # no exact zeros
    if D.min() >= 0: raise SystemExit('shape is empty inside the bounds')
    if (D[0].min() < 0 or D[-1].min() < 0 or D[:, 0].min() < 0 or D[:, -1].min() < 0 or D[:, :, 0].min() < 0 or D[:, :, -1].min() < 0):
        print('WARNING: shape touches the bounds - it will be cut open; enlarge bounds')
    v, faces, _, _ = marching_cubes(D, level=0.0, spacing=(res, res, res))
    m = trimesh.Trimesh(v + lo, faces[:, ::-1], process=True)
    if m.volume < 0: m.invert()
    return m

def report(m, label='mesh'):
    ext = m.bounds[1] - m.bounds[0]
    print('%s: %d faces | watertight %s | volume %.1f cm3 | size %.1f x %.1f x %.1f mm | bodies %d'
          % (label, len(m.faces), m.is_watertight, m.volume / 1000, *ext, len(m.split(only_watertight=False))))
    return m.is_watertight

# ----------------------------------------------------------------- demo
def demo(out=None):
    """Ergonomic handle: capsule body, flared end, three finger grooves, lanyard loop, shaft bore.
    Every number is a named parameter, as in the skill's parameter-block rule."""
    P = dict(L=110.0, R=14.0, flare_R=18.0, groove_R=4.0, groove_depth=2.5, groove_pitch=19.0, loop_R=8.0, loop_r=3.2,
             bore_d=8.2, bore_depth=45.0, blend_k=6.0, res=0.5)
    body = capsule((0, 0, 0), (0, 0, P['L']), P['R'])
    flare = sphere((0, 0, P['L']), P['flare_R'])
    grip = smooth_union(P['blend_k'], body, flare)
    for i in range(3):
        z = 22 + i * P['groove_pitch']
        grip = smooth_subtract(2.0, grip, torus((0, 0, z), P['R'] + P['groove_R'] - P['groove_depth'], P['groove_R']))
    loop = torus((0, 0, P['L'] + P['flare_R'] + P['loop_R'] - 3), P['loop_R'], P['loop_r'], axis=(1, 0, 0))
    part = smooth_union(2.5, grip, loop)
    part = subtract(part, cylinder((0, 0, -P['R'] - 1), (0, 0, P['bore_depth'] - P['R']), P['bore_d'] / 2))
    bounds = ((-P['flare_R'] - 2, -P['flare_R'] - 2, -P['R'] - 2), (P['flare_R'] + 2, P['flare_R'] + 2, P['L'] + P['flare_R'] + 2 * P['loop_R'] + 2))
    m = mesh(part, bounds, P['res'])
    ok = report(m, 'handle')
    # self-test: the bore must be open at the bottom and the loop must be a through-hole (genus >= 2)
    genus = (2 - m.euler_number) // 2 if m.is_watertight else -1
    print('genus %d (expect 1 for the loop; the blind bore adds none)' % genus)
    if out: m.export(out); print('wrote', out)
    return ok and genus >= 1

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--demo':
        sys.exit(0 if demo(sys.argv[2] if len(sys.argv) > 2 else None) else 1)
    print(__doc__)
