// scrollgen.js — JS port of scroll_gen / scroll_gen2 / scroll_gen3 (v29c). Units mm, Z up, plaque top = base_t.
(function (root) {
  const SEL = [[-9.055, 40.06], [-17.5, 44.175], [-23.615, 49.005], [-30.35, 56.31], [-35.325, 64.4], [-38.535, 73.215], [-40.225, 82.405]];
  const DEFAULTS = {
    base_t: 6.0, W: 26.0, W_up: 28.0, T: 1.6, bank_deg: 10.0, z_bot: 8.2, z_hump: 0.8, z_top: 10.0,
    fold_y: 98, fold_ang: 0.0, dip_w: 16.0, dip_shape: 2.5, dip_bottom: 0.8, rise_y0: 110.0, rise_y1: 138.0, up_x: -41.0, app_y: 146.0, crest_h: 8.0, crest_pos: 0.45,
    flare_y0: 112.0, flare_end_gap: 22.0, flare_mm: 4.0, rise_mm: 2.0,
    L_app: 8.0, crease_ang: 45.0, r_fold: 1.8, exit_len: 3.0, fold_dir: -1,
    c_top_arm: 0.5, c_rb: 3.0, c_rise: 5.0, c_R: 5.5, c_turn_deg: 200.0, c_back_len: 9.0, c_lean_deg: 12.0, c_width: 24.0,
    K: 15, n: 1400, n_curl: 420, n_c: 260
  };
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = a => Math.hypot(a[0], a[1], a[2]);
  const unit = a => { const n = norm(a); return n > 1e-12 ? mul(a, 1 / n) : a.slice(); };
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const smoothstep = f => { f = clamp(f, 0, 1); return f * f * (3 - 2 * f); };
  const linspace = (a, b, n) => { const o = new Array(n); for (let i = 0; i < n; i++) o[i] = n === 1 ? a : a + (b - a) * i / (n - 1); return o; };
  function interp(x, xs, ys) {                       // numpy.interp for monotone xs
    if (x <= xs[0]) return ys[0];
    const n = xs.length; if (x >= xs[n - 1]) return ys[n - 1];
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
    const t = (x - xs[lo]) / (xs[hi] - xs[lo]); return ys[lo] + t * (ys[hi] - ys[lo]);
  }
  // cubic spline through points (chord-length knots), clamped first-derivative ends (null => natural), like scipy CubicSpline
  function spline(ctrl, d0, d1, nOut) {
    const n = ctrl.length, t = [0];
    for (let i = 1; i < n; i++) t.push(t[i - 1] + norm(sub(ctrl[i], ctrl[i - 1])));
    const h = []; for (let i = 0; i < n - 1; i++) h.push(t[i + 1] - t[i]);
    const e0 = d0 ? unit(d0) : null, e1 = d1 ? unit(d1) : null;
    const Ms = [];
    for (let dim = 0; dim < 3; dim++) {
      const y = ctrl.map(p => p[dim]);
      const a = new Array(n).fill(0), b = new Array(n).fill(0), c = new Array(n).fill(0), r = new Array(n).fill(0);
      if (e0) { b[0] = 2 * h[0]; c[0] = h[0]; r[0] = 6 * ((y[1] - y[0]) / h[0] - e0[dim]); } else { b[0] = 1; }
      for (let i = 1; i < n - 1; i++) { a[i] = h[i - 1]; b[i] = 2 * (h[i - 1] + h[i]); c[i] = h[i]; r[i] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1]); }
      if (e1) { a[n - 1] = h[n - 2]; b[n - 1] = 2 * h[n - 2]; r[n - 1] = 6 * (e1[dim] - (y[n - 1] - y[n - 2]) / h[n - 2]); } else { b[n - 1] = 1; }
      for (let i = 1; i < n; i++) { const m = a[i] / b[i - 1]; b[i] -= m * c[i - 1]; r[i] -= m * r[i - 1]; }
      const M = new Array(n); M[n - 1] = r[n - 1] / b[n - 1];
      for (let i = n - 2; i >= 0; i--) M[i] = (r[i] - c[i] * M[i + 1]) / b[i];
      Ms.push(M);
    }
    const out = [], ts = linspace(0, t[n - 1], nOut);
    let seg = 0;
    for (const tt of ts) {
      while (seg < n - 2 && tt > t[seg + 1]) seg++;
      const hh = h[seg], A = t[seg + 1] - tt, B = tt - t[seg];
      const p = [0, 0, 0];
      for (let dim = 0; dim < 3; dim++) {
        const M = Ms[dim], yi = ctrl[seg][dim], yj = ctrl[seg + 1][dim];
        p[dim] = M[seg] * A * A * A / (6 * hh) + M[seg + 1] * B * B * B / (6 * hh) + (yi / hh - M[seg] * hh / 6) * A + (yj / hh - M[seg + 1] * hh / 6) * B;
      }
      out.push(p);
    }
    return out;
  }
  function gradient(P) {                             // numpy.gradient along axis 0
    const n = P.length, g = new Array(n);
    g[0] = sub(P[1], P[0]); g[n - 1] = sub(P[n - 1], P[n - 2]);
    for (let i = 1; i < n - 1; i++) g[i] = mul(sub(P[i + 1], P[i - 1]), 0.5);
    return g;
  }
  function leftHalf(p) {
    const b = p.base_t, zb = b + p.z_bot, Z = [0, 0, 1];
    const hump = y => p.z_hump * Math.sin(Math.PI * clamp((y - 45) / 45, 0, 1));
    const ctrl = [[0, 38.8, zb]].concat(SEL.map(([x, y]) => [x, y, zb + hump(y)]), [[-41, 92, zb], [-41, p.fold_y, zb]]);
    const fa = p.fold_ang * Math.PI / 180, tF = [-Math.sin(fa), Math.cos(fa), 0];
    const U = spline(ctrl, [-1, 0, 0], tF, Math.floor(p.n / 2));
    const F = U[U.length - 1];
    // dip under the fletching: a smooth U sag from the U band down near the plaque and up into the upper band
    const zE = b + p.z_top, zBot = b + p.T / 2 + p.dip_bottom, Wd = p.dip_w, pw = p.dip_shape;
    const zu = u => u <= 0.5 ? zBot + (F[2] - zBot) * Math.pow(1 - u / 0.5, pw) : zBot + (zE - zBot) * Math.pow((u - 0.5) / 0.5, pw);
    const dctrl = [F].concat([0.12, 0.25, 0.38, 0.5, 0.62, 0.75, 0.88].map(u => add(add(F, mul(tF, u * Wd)), [0, 0, zu(u) - F[2]])), [add(add(F, mul(tF, Wd)), [0, 0, zE - F[2]])]);
    const seg = spline(dctrl, tF, tF, Math.max(40, Math.round(Wd * 6))).slice(1);
    const E3 = seg[seg.length - 1];
    const zt = b + p.z_top;
    const zr = y => E3[2] + (zt - E3[2]) * smoothstep((y - p.rise_y0) / (p.rise_y1 - p.rise_y0));
    // upper band: climbs from the dip to a crest, then slopes back down into the top bend
    const yA = E3[1] + 6 * tF[1], yEnd = Math.max(p.app_y, yA + 20), cp = clamp(p.crest_pos, 0.1, 0.9);
    const bump = y => { const s = clamp((y - yA) / (yEnd - yA), 0, 1); return p.crest_h * (s < cp ? smoothstep(s / cp) : 1 - smoothstep((s - cp) / (1 - cp))); };
    const ctrl3 = [E3, add(E3, mul(tF, 6))].concat(linspace(0.12, 0.9, 7).map(f => { const y = yA + f * (yEnd - yA); return [p.up_x - 1.0 * f, y, zr(y) + bump(y)]; }), [[p.up_x - 1, yEnd, zt]]);
    const up = spline(ctrl3, tF, [0, 1, 0], Math.floor(p.n / 3)).slice(1);
    const pts = U.concat(seg, up);
    return { pts, iU: U.length, iF: U.length + seg.length };
  }
  function frames(pts, iU, iF, p) {
    const t = gradient(pts).map(unit), n = pts.length;
    const N = new Array(n); N[0] = [0, 0, 1];
    for (let i = 1; i < n; i++) { const v = sub(N[i - 1], mul(t[i], dot(N[i - 1], t[i]))); const nv = norm(v); N[i] = nv > 1e-9 ? mul(v, 1 / nv) : N[i - 1]; }
    const nn = new Array(n), w = new Array(n), Wv = new Array(n);
    for (let i = 0; i < n; i++) {
      const B = cross(t[i], N[i]), y = pts[i][1];
      const bank = i < iU ? p.bank_deg * Math.PI / 180 * smoothstep((y - 38) / 20) * (1 - smoothstep((y - 80) / 12)) : 0;
      nn[i] = add(mul(N[i], Math.cos(bank)), mul(B, Math.sin(bank)));
      w[i] = cross(nn[i], t[i]);
      if (i >= iF) {                                   // upper band: keep the width level (no twist over the crest)
        let wh = unit([t[i][1], -t[i][0], 0]); if (dot(wh, w[i]) < 0) wh = mul(wh, -1);
        w[i] = wh; nn[i] = unit(cross(t[i], wh));
      }
      Wv[i] = i >= iF ? p.W + (p.W_up - p.W) * smoothstep((y - p.rise_y0) / 20) : p.W;
    }
    return { n: nn, w, Wv };
  }
  function bandGrid(p) {
    const { pts, iU, iF } = leftHalf(p), { w, Wv } = frames(pts, iU, iF, p);
    const s = linspace(-0.5, 0.5, p.K);
    const X = pts.map((c, i) => s.map(sj => add(c, mul(w[i], Wv[i] * sj))));
    return { X, pts, w, Wv, iU, iF };
  }
  function foldGrid(cEnd, tEnd, wEnd, W, p) {
    let t = [tEnd[0], tEnd[1], 0]; t = unit(t);
    const a = p.crease_ang * Math.PI / 180; let e = [Math.cos(a), Math.sin(a), 0];
    if (dot(e, t) < 0) e = mul(e, -1);
    const sa = dot(t, e), alpha = Math.asin(clamp(sa, -0.95, 0.95)), ca = Math.cos(alpha), sal = Math.sin(alpha);
    const nvec = mul(sub(t, mul(e, sa)), 1 / ca), up = [0, 0, 1];
    const wmap = sub(mul(e, ca), mul(nvec, sal)), sgn = dot(wmap, wEnd) > 0 ? 1 : -1;
    const O = add(cEnd, mul(t, p.L_app));
    const r = p.r_fold, e1 = Math.PI * r, etaNeed = e1 + p.exit_len;
    const sigEnd = (etaNeed + Math.abs(W) / 2 * sal) / ca;
    const ne = 4000, eg = linspace(0, etaNeed + Math.abs(W) + 5, ne), qn = [0], qu = [0];
    let th = 0;
    const fdir = p.fold_dir === undefined ? -1 : Math.sign(p.fold_dir) || -1;
    for (let i = 1; i < ne; i++) { const de = eg[i] - eg[i - 1]; th += (eg[i] < e1 ? fdir / r : 0) * de; qn.push(qn[i - 1] + Math.cos(th) * de); qu.push(qu[i - 1] + Math.sin(th) * de); }
    const s = linspace(-0.5, 0.5, p.K).map(v => v * W * sgn);
    const sig = linspace(-p.L_app, sigEnd, p.n_curl).slice(1);
    return sig.map(sg => s.map(ss => {
      const xi = sg * sal + ss * ca, eta = sg * ca - ss * sal;
      const q1 = eta < 0 ? eta : interp(eta, eg, qn), q2 = eta < 0 ? 0 : interp(eta, eg, qu);
      return add(add(add(O, mul(e, xi)), mul(nvec, q1)), mul(up, q2));
    }));
  }
  function cProfile(p, n) {
    // top U bend: lead-in toward the blade -> bend up -> rising leg -> arch over the top (U turn) -> falling leg down the far side
    const segs = [[null, p.c_top_arm], [p.c_rb, Math.PI / 2], [null, p.c_rise], [p.c_R, -p.c_turn_deg * Math.PI / 180], [null, p.c_back_len]];
    const lens = segs.map(([r, a]) => r ? Math.abs(r * a) : a), total = lens.reduce((x, y) => x + y, 0);
    const eg = linspace(0, total, n), kap = new Array(n).fill(0);
    let e0 = 0;
    segs.forEach(([r, a], k) => { const L = lens[k]; if (r) for (let i = 0; i < n; i++) if (eg[i] >= e0 && eg[i] < e0 + L) kap[i] = Math.sign(a) / r; e0 += L; });
    const qn = [0], qu = [0]; let th = 0;
    for (let i = 1; i < n; i++) { const de = eg[i] - eg[i - 1]; th += kap[i] * de; qn.push(qn[i - 1] + Math.cos(th) * de); qu.push(qu[i - 1] + Math.sin(th) * de); }
    return { eg, qn, qu };
  }
  function leftGrid(p) {
    let { X, iU, iF: iDip } = bandGrid(p);
    const K = p.K, s = linspace(-0.5, 0.5, K);
    let c = X.map(r => r.reduce((acc, v) => add(acc, v), [0, 0, 0]).map(v => v / K));
    let wv = X.map(r => sub(r[K - 1], r[0]));
    let w = wv.map(unit);
    const y = c.map(v => v[1]), nr = X.length, yEnd = y[nr - 1];
    let iF = y.findIndex(v => v > p.flare_y0); if (iF < 0) iF = nr;
    const f = y.map((yy, i) => i < iF ? 0 : smoothstep((yy - p.flare_y0) / (yEnd - p.flare_end_gap - p.flare_y0)));
    X = X.map((row, i) => row.map((P, j) => add(add(P, mul(w[i], p.flare_mm * f[i] * (s[j] + 0.5))), [0, 0, p.rise_mm * f[i]])));
    c = X.map(r => r.reduce((acc, v) => add(acc, v), [0, 0, 0]).map(v => v / K));
    wv = X.map(r => sub(r[K - 1], r[0])); const Wv = wv.map(norm); w = wv.map(unit);
    let F = foldGrid(c[nr - 1], sub(c[nr - 1], c[nr - 2]), w[nr - 1], Wv[nr - 1], p);
    if (norm(sub(F[0][0], X[nr - 1][0])) > norm(sub(F[0][K - 1], X[nr - 1][0]))) F = F.map(r => r.slice().reverse());
    const end = F[F.length - 1];
    const C0 = end.reduce((acc, v) => add(acc, v), [0, 0, 0]).map(v => v / K);
    let wc = sub(end[K - 1], end[0]); wc[2] = 0; const W0 = norm(wc); wc = mul(wc, 1 / W0);
    let d = cross(wc, [0, 0, 1]);
    const pre = F[F.length - 5].reduce((acc, v) => add(acc, v), [0, 0, 0]).map(v => v / K);
    if (dot(d, sub(C0, pre)) < 0) d = mul(d, -1);
    const { eg, qn, qu } = cProfile(p, p.n_c), lean = p.c_lean_deg * Math.PI / 180;
    const Uv = add(mul([0, 0, 1], Math.cos(lean)), mul(wc, Math.sin(lean)));
    const s0 = end.map(P => dot(sub(P, C0), wc)), egEnd = eg[eg.length - 1];
    const Cg = [];
    for (let k = 1; k < eg.length; k++) {
      const taper = 1 + (p.c_width / W0 - 1) * smoothstep(eg[k] / (0.35 * egEnd));
      const cen = add(add(C0, mul(d, qn[k])), mul(Uv, qu[k]));
      Cg.push(s0.map(sj => add(cen, mul(wc, sj * taper))));
    }
    return { L: X.concat(F, Cg), nBand: nr, nFold: F.length, iU, iF: iDip, info: { d, C0, W0 } };
  }
  function ribbonGrid(p) {
    const { L, nBand, nFold, info } = leftGrid(p), K = p.K;
    let R = L.slice().reverse().map(row => row.map(P => [-P[0], P[1], P[2]]).reverse());
    const last = R[R.length - 1];
    if (norm(sub(last[0], L[0][0])) > norm(sub(last[0], L[0][K - 1]))) R = R.map(r => r.slice().reverse());
    return { G: R.concat(L.slice(1)), half: R.length, nBand, nFold, info };
  }
  function thickMesh(G, T) {                          // closed shell around the mid-surface grid
    const r = G.length, k = G[0].length, V = new Float32Array(r * k * 2 * 3);
    const g = (i, j) => G[clamp(i, 0, r - 1)][clamp(j, 0, k - 1)];
    for (let i = 0; i < r; i++) for (let j = 0; j < k; j++) {
      const du = i === 0 ? sub(g(1, j), g(0, j)) : i === r - 1 ? sub(g(r - 1, j), g(r - 2, j)) : mul(sub(g(i + 1, j), g(i - 1, j)), 0.5);
      const dv = j === 0 ? sub(g(i, 1), g(i, 0)) : j === k - 1 ? sub(g(i, k - 1), g(i, k - 2)) : mul(sub(g(i, j + 1), g(i, j - 1)), 0.5);
      const N = unit(cross(du, dv)), P = G[i][j], o = (i * k + j) * 3, o2 = o + r * k * 3;
      V[o] = P[0] + N[0] * T / 2; V[o + 1] = P[1] + N[1] * T / 2; V[o + 2] = P[2] + N[2] * T / 2;
      V[o2] = P[0] - N[0] * T / 2; V[o2 + 1] = P[1] - N[1] * T / 2; V[o2 + 2] = P[2] - N[2] * T / 2;
    }
    const off = r * k, id = (i, j) => i * k + j, core = [], edge = [];
    for (let i = 0; i < r - 1; i++) for (let j = 0; j < k - 1; j++) {
      const a = id(i, j), b = id(i + 1, j), c = id(i + 1, j + 1), d = id(i, j + 1);
      (j === 0 || j === k - 2 ? edge : core).push(a, b, c, a, c, d, off + a, off + c, off + b, off + a, off + d, off + c);
    }
    for (let i = 0; i < r - 1; i++) {
      let a = id(i, 0), b = id(i + 1, 0); edge.push(a, off + a, off + b, a, off + b, b);
      a = id(i, k - 1); b = id(i + 1, k - 1); edge.push(a, b, off + b, a, off + b, off + a);
    }
    for (const [i, flip] of [[0, true], [r - 1, false]]) for (let j = 0; j < k - 1; j++) {
      const a = id(i, j), b = id(i, j + 1);
      if (flip) edge.push(b, off + b, a, off + b, off + a, a); else edge.push(a, off + b, b, a, off + a, off + b);
    }
    const idx = core.concat(edge);
    return { V, idx, core, edge, rows: r, cols: k };
  }
  function features(p) {
    // named model points + edge polylines (left half) used by the marker board and the fitter
    const { L, nBand, nFold, iU, iF } = leftGrid(p), K = L[0].length, mid = K >> 1;
    const inner = row => (row[0][0] > row[K - 1][0] ? row[0] : row[K - 1]), outer = row => (row[0][0] > row[K - 1][0] ? row[K - 1] : row[0]);
    const argBy = (a, b, f) => { let k = a, v = -Infinity; for (let i = a; i < b; i++) { const q = f(L[i]); if (q > v) { v = q; k = i; } } return k; };
    const iDipBot = argBy(iU, iF, r => -r[mid][2]), iCrest = argBy(iF, nBand, r => r[mid][2]), iEnd = L.length - 1, iFoldEnd = nBand + nFold - 1;
    const iArchTop = argBy(iFoldEnd, L.length, r => r[mid][2]), iUmid = Math.round(iU * 0.55), iUpMid = Math.round((iF + nBand) / 2);
    let crest = L[iF][0], archIn = L[iFoldEnd][0];
    for (let i = iF; i < nBand; i++) for (const q of L[i]) if (q[2] > crest[2]) crest = q;
    for (let i = iFoldEnd; i < L.length; i++) for (const q of L[i]) if (q[0] > archIn[0]) archIn = q;
    const pts = {
      L1: L[0][mid], L2: outer(L[iUmid]), L3: inner(L[iUmid]), L4: L[iU][mid], L5: L[iDipBot][mid], L6: L[iF][mid],
      L7: outer(L[iCrest]), L8: inner(L[iCrest]), L9: outer(L[nBand - 1]), L10: inner(L[nBand - 1]), L11: L[iFoldEnd][mid], L12: L[iArchTop][mid], L13: L[iEnd][mid],
      IE1: inner(L[iF]), IE2: inner(L[iUpMid]), IE3: inner(L[nBand - 1]), OE1: outer(L[iUpMid]), OE2: outer(L[nBand - 1]), CR: crest,
      AT: L[iArchTop][mid], AI: archIn, FE: L[iEnd][mid], DE: inner(L[iU]), DB: L[iDipBot][mid], DX: L[iF][mid],
      UO: outer(L[iUmid]), UI: inner(L[iUmid]), UB: outer(L[0]) };
    const rows = (a, b, f) => { const o = []; for (let i = a; i < b; i++) o.push(f(L[i])); return o; };
    const edges = {
      u_outer: [rows(0, iU, outer)], u_inner: [rows(0, iU, inner)],
      up_outer: [rows(iF, nBand, outer)], up_inner: [rows(iF, nBand, inner)],
      arch: [rows(iFoldEnd, L.length, r => r[0]), rows(iFoldEnd, L.length, r => r[K - 1])] };
    return { pts, edges };
  }
  const DESC = { 1: 'U bottom centre', 2: 'U band outer edge', 3: 'U band inner edge', 4: 'dip entry', 5: 'dip bottom', 6: 'dip exit', 7: 'crest outer edge', 8: 'crest inner edge',
    9: 'band end outer edge', 10: 'band end inner edge', 11: 'fold-under exit', 12: 'arch top', 13: 'free end' };
  function markers(p) {
    const { pts } = features(p), out = [];
    for (let n = 1; n <= 13; n++) { const P = pts['L' + n]; out.push({ id: 'L' + n, pos: P.slice(), desc: DESC[n] }); if (n !== 1) out.push({ id: 'R' + n, pos: [-P[0], P[1], P[2]], desc: DESC[n] }); }
    return out;
  }
  const api = { DEFAULTS, ribbonGrid, thickMesh, leftGrid, bandGrid, spline, markers, features };
  if (typeof module !== 'undefined') module.exports = api; else root.ScrollGen = api;
})(this);
