#!/usr/bin/env python3
"""
ribbon_kit.py - building blocks for procedural strips, straps, ribbons, hoses and other
rule-driven organic parts that Fusion's API can't sweep or sculpt. See references/domains/procedural-organic.md.

  clamped_spline(ctrl, d0, d1, n)      chord-length cubic through control points, end tangents
  rmf_frames(pts, n0)                  rotation-minimizing frames -> t, n, w
  level_width(t, w)                    lock the width vector horizontal (no twist in plan)
  profile(segments, n)                 side profile from (radius, turn_rad) / (None, length) segments
  strip_grid(c, w, W, K)               ruled strip grid rows x K
  oblique_fold(c_end, t_end, w_end, W, crease_deg, run_in, profile_segments, K, n)
                                        exact developable fold/roll along a diagonal crease
  thick_shell(G, T)                    closed mesh around a mid-surface grid (+ edge/core face split)
  mirror_join(L)                       mirror a left-half grid about x=0 and join at the seam
  clip_below(V, F, z)                  manifold boolean trim at a plane (no vertex clamping)
  self_gap_surface(G, T)               clash test on the unrolled surface (None = clean)

Run `python ribbon_kit.py --demo out.stl` for a worked example (band -> oblique fold under ->
arch), which also self-tests watertightness and self-clearance.
"""
import math, sys
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree


def smoothstep(f):
    f = np.clip(f, 0, 1); return f * f * (3 - 2 * f)


def clamped_spline(ctrl, d0, d1, n):
    P = np.asarray(ctrl, float); t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    d0 = np.asarray(d0, float) / np.linalg.norm(d0); d1 = np.asarray(d1, float) / np.linalg.norm(d1)
    cs = CubicSpline(t, P, bc_type=((1, d0), (1, d1)))
    return cs(np.linspace(0, t[-1], n))


def rmf_frames(pts, n0=(0, 0, 1)):
    t = np.gradient(pts, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
    N = np.zeros_like(pts); N[0] = n0
    for i in range(1, len(pts)):
        v = N[i - 1] - np.dot(N[i - 1], t[i]) * t[i]; nv = np.linalg.norm(v)
        N[i] = v / nv if nv > 1e-9 else N[i - 1]
    w = np.cross(N, t)
    return t, N, w


def level_width(t, w):
    wh = np.c_[t[:, 1], -t[:, 0], np.zeros(len(t))]; wh /= np.linalg.norm(wh, axis=1)[:, None]
    wh *= np.sign((wh * w).sum(1))[:, None]
    n = np.cross(t, wh); n /= np.linalg.norm(n, axis=1)[:, None]
    return wh, n


def profile(segments, n=4000):
    """segments: list of (radius, turn_rad) or (None, length). Returns eta, qn, qu (arc-length side profile)."""
    lens = [abs(r * a) if r else a for r, a in segments]; total = sum(lens)
    eg = np.linspace(0, total, n); kap = np.zeros(n); e0 = 0.0
    for (r, a), L in zip(segments, lens):
        if r: kap[(eg >= e0) & (eg < e0 + L)] = np.sign(a) / r
        e0 += L
    th = np.r_[0, np.cumsum(kap[1:] * np.diff(eg))]
    qn = np.r_[0, np.cumsum(np.cos(th[1:]) * np.diff(eg))]; qu = np.r_[0, np.cumsum(np.sin(th[1:]) * np.diff(eg))]
    return eg, qn, qu


def strip_grid(c, w, W, K):
    s = np.linspace(-0.5, 0.5, K); W = np.broadcast_to(np.asarray(W, float), (len(c),))
    return c[:, None, :] + w[:, None, :] * (W[:, None] * s[None, :])[..., None]


def oblique_fold(c_end, t_end, w_end, W, crease_deg, run_in, segments, K=15, n=400):
    """Continue a flat strip (ending at c_end, travelling t_end, width vector w_end) through a side profile
    applied perpendicular to a crease at crease_deg (plan angle). Exact developable map. The strip ends at
    constant arc length so the last row is a straight cross-line once every fibre has left the profile."""
    t = np.array([t_end[0], t_end[1], 0.0]); t /= np.linalg.norm(t)
    a = math.radians(crease_deg); e = np.array([math.cos(a), math.sin(a), 0.0])
    if np.dot(e, t) < 0: e = -e
    sa = float(np.dot(t, e)); alpha = math.asin(np.clip(sa, -0.95, 0.95)); ca = math.cos(alpha)
    nvec = (t - sa * e) / ca; up = np.array([0, 0, 1.0])
    wmap = ca * e - math.sin(alpha) * nvec; sgn = 1.0 if np.dot(wmap, w_end) > 0 else -1.0
    O = np.asarray(c_end, float) + run_in * t
    eg, qn, qu = profile(segments + [(None, abs(W) + 5)])
    need = sum(abs(r * a_) if r else a_ for r, a_ in segments)
    sig_end = (need + abs(W) / 2 * math.sin(alpha)) / ca
    s = np.linspace(-0.5, 0.5, K) * W * sgn; sig = np.linspace(-run_in, sig_end, n)[1:]
    S, Sg = np.meshgrid(s, sig)
    xi = Sg * math.sin(alpha) + S * ca; eta = Sg * ca - S * math.sin(alpha)
    q1 = np.where(eta < 0, eta, np.interp(eta, eg, qn)); q2 = np.where(eta < 0, 0.0, np.interp(eta, eg, qu))
    return O[None, None, :] + xi[..., None] * e + q1[..., None] * nvec + q2[..., None] * up


def thick_shell(G, T):
    """Closed mesh around mid-surface grid G (rows x K x 3). Returns V, F, edge_face_mask (edge strips, walls, caps)."""
    du = np.gradient(G, axis=0); dv = np.gradient(G, axis=1)
    N = np.cross(du, dv); N /= np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-12)
    r, k = G.shape[:2]; V = np.vstack([(G + N * T / 2).reshape(-1, 3), (G - N * T / 2).reshape(-1, 3)]); off = r * k
    idx = lambda i, j: i * k + j; F, E = [], []
    for i in range(r - 1):
        for j in range(k - 1):
            a, b, c, d = idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1); edge = j in (0, k - 2)
            F += [[a, b, c], [a, c, d], [off + a, off + c, off + b], [off + a, off + d, off + c]]; E += [edge] * 4
    for i in range(r - 1):
        a, b = idx(i, 0), idx(i + 1, 0); F += [[a, off + a, off + b], [a, off + b, b]]
        a, b = idx(i, k - 1), idx(i + 1, k - 1); F += [[a, b, off + b], [a, off + b, off + a]]; E += [True] * 4
    for i, flip in ((0, True), (r - 1, False)):
        for j in range(k - 1):
            a, b = idx(i, j), idx(i, j + 1); f1, f2 = [a, off + b, b], [a, off + a, off + b]
            if flip: f1, f2 = f1[::-1], f2[::-1]
            F += [f1, f2]; E += [True] * 2
    return V, np.array(F), np.array(E)


def mirror_join(L):
    R = L[::-1] * [-1, 1, 1]; R = R[:, ::-1]
    if np.linalg.norm(R[-1, 0] - L[0, 0]) > np.linalg.norm(R[-1, 0] - L[0, -1]): R = R[:, ::-1]
    return np.concatenate([R, L[1:]], axis=0)


def clip_below(V, F, z):
    import trimesh, manifold3d as mf
    m = trimesh.Trimesh(V, F, process=True)
    if m.volume < 0: m.invert()
    M = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))
    if M.status() != mf.Error.NoError: raise RuntimeError('not manifold: %s' % M.status())
    M = M ^ mf.Manifold.cube([2000, 2000, 1000]).translate([-1000, -1000, z])
    o = M.to_mesh(); return trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts), process=True)


def self_gap_surface(G, T, factor=3.0):
    """Pairs closer than T in 3D but > factor*T apart on the unrolled surface. None = clean,
    else (min_dist, point_a, point_b, pair_count)."""
    C = G[:, G.shape[1] // 2]; sig = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    K = G.shape[1]; wdt = np.linalg.norm(G[:, -1] - G[:, 0], axis=1)
    s = (np.arange(K) / (K - 1) - 0.5)[None, :] * wdt[:, None]
    U = np.stack([np.repeat(sig[:, None], K, 1), s], -1).reshape(-1, 2); P = G.reshape(-1, 3)
    pairs = cKDTree(P).query_pairs(r=T, output_type='ndarray')
    if len(pairs) == 0: return None
    bad = np.linalg.norm(U[pairs[:, 0]] - U[pairs[:, 1]], axis=1) > factor * T
    if not bad.any(): return None
    d = np.linalg.norm(P[pairs[bad, 0]] - P[pairs[bad, 1]], axis=1); k = d.argmin()
    return float(d[k]), P[pairs[bad][k, 0]].round(1), P[pairs[bad][k, 1]].round(1), int(bad.sum())


def demo(out_path=None):
    """Left half: band rising from the seam, oblique fold UNDER at 45 deg, then an arch toward the centre."""
    base, T, W, K = 6.0, 1.6, 26.0, 15
    c = clamped_spline([(0, 40, 14), (-25, 55, 14), (-40, 90, 14), (-41, 130, 16)], (-1, 0, 0), (0, 1, 0), 400)
    t, n, w = rmf_frames(c); w, n = level_width(t, w)
    band = strip_grid(c, w, W, K)
    fold = oblique_fold(c[-1], c[-1] - c[-2], w[-1], W, 45.0, 6.0, [(1.8, -math.pi), (None, 3.0)], K)
    if np.linalg.norm(fold[0, 0] - band[-1, 0]) > np.linalg.norm(fold[0, -1] - band[-1, 0]): fold = fold[:, ::-1]
    L = np.concatenate([band, fold], axis=0)
    G = mirror_join(L)
    V, F, E = thick_shell(G, T)
    m = clip_below(V, F, base)
    clash = self_gap_surface(L, T)
    print('grid', G.shape, '| faces', len(m.faces), '| watertight', m.is_watertight, '| z [%.1f, %.1f]' % tuple(m.bounds[:, 2]),
          '| edge faces %d of %d' % (int(E.sum()), len(E)), '| self-clash', 'none' if clash is None else clash)
    if out_path: m.export(out_path); print('wrote', out_path)
    return m.is_watertight and clash is None


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--demo':
        ok = demo(sys.argv[2] if len(sys.argv) > 2 else None); sys.exit(0 if ok else 1)
    print(__doc__)
