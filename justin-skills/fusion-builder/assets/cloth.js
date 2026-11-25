// cloth.js — inextensible ribbon (XPBD): fixed length & width, adjustable bending, plaque + self collision.
(function (root) {
  function makeCloth(grid, opts) {
    // grid: rows x cols x [x,y,z] (left half, row 0 = bottom centre seam, stays pinned on x = 0)
    const R = grid.length, C = grid[0].length, N = R * C;
    const x = new Float64Array(N * 3), prev = new Float64Array(N * 3), v = new Float64Array(N * 3), w = new Float64Array(N).fill(1);
    grid.forEach((row, i) => row.forEach((P, j) => { const k = (i * C + j) * 3; x[k] = P[0]; x[k + 1] = P[1]; x[k + 2] = P[2]; }));
    const id = (i, j) => i * C + j;
    const cons = [];                                   // [a, b, rest, kind] kind 0 stretch/shear, 1 bend
    const dist = (a, b) => Math.hypot(x[3 * a] - x[3 * b], x[3 * a + 1] - x[3 * b + 1], x[3 * a + 2] - x[3 * b + 2]);
    const add = (a, b, kind) => cons.push([a, b, dist(a, b), kind]);
    for (let i = 0; i < R; i++) for (let j = 0; j < C; j++) {
      if (i + 1 < R) add(id(i, j), id(i + 1, j), 0);
      if (j + 1 < C) add(id(i, j), id(i, j + 1), 0);
      if (i + 1 < R && j + 1 < C) { add(id(i, j), id(i + 1, j + 1), 0); add(id(i + 1, j), id(i, j + 1), 0); }
      if (i + 2 < R) add(id(i, j), id(i + 2, j), 1);
      if (j + 2 < C) add(id(i, j), id(i, j + 2), 1);
      if (i + 2 < R && j + 2 < C) { add(id(i, j), id(i + 2, j + 2), 1); add(id(i + 2, j), id(i, j + 2), 1); }
    }
    for (let j = 0; j < C; j++) w[id(0, j)] = 0;          // seam pinned
    const floorZ = new Float64Array(N); for (let n = 0; n < N; n++) floorZ[n] = Math.min(x[3 * n + 2], opts.floor + opts.thick / 2);
    const pins = new Map();                                // particle -> [x,y,z]
    const S = {
      R, C, x, cons, pins, grabbed: -1, grabTarget: null,
      bend: opts.bend ?? 0.15, gravity: opts.gravity ?? 0, floor: opts.floor, thick: opts.thick, damping: 0.985, paused: false,
      restLen: 0, restWid: 0,
    };
    // reference length (centre column) and mean width
    const mid = C >> 1;
    for (let i = 0; i + 1 < R; i++) S.restLen += dist(id(i, mid), id(i + 1, mid));
    for (let i = 0; i < R; i++) S.restWid += dist(id(i, 0), id(i, C - 1)) / R;
    // spatial hash for self collision
    const cell = opts.thick * 1.2, neighborhood = 2;
    const hashKey = (a, b, c) => ((a * 73856093) ^ (b * 19349663) ^ (c * 83492791)) | 0;
    const cellOf = new Int32Array(N * 3);
    const ignore = new Set();
    function selfCollide(record) {
      const T = S.thick, H = new Map();
      for (let n = 0; n < N; n++) {
        const a = Math.floor(x[3 * n] / cell), b = Math.floor(x[3 * n + 1] / cell), c = Math.floor(x[3 * n + 2] / cell);
        cellOf[3 * n] = a; cellOf[3 * n + 1] = b; cellOf[3 * n + 2] = c;
        const key = hashKey(a, b, c); let arr = H.get(key); if (!arr) H.set(key, arr = []); arr.push(n);
      }
      for (let n = 0; n < N; n++) {
        if (w[n] === 0 && !record) continue;
        const cx = cellOf[3 * n], cy = cellOf[3 * n + 1], cz = cellOf[3 * n + 2], ri = (n / C) | 0, rj = n % C;
        for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
          const arr = H.get(hashKey(cx + dx, cy + dy, cz + dz)); if (!arr) continue;
          for (let q = 0; q < arr.length; q++) {
            const m = arr[q]; if (m <= n) continue;
            const mi = (m / C) | 0, mj = m % C;
            if (Math.abs(mi - ri) <= neighborhood + 2 && Math.abs(mj - rj) <= neighborhood) continue;
            const ddx = x[3 * m] - x[3 * n], ddy = x[3 * m + 1] - x[3 * n + 1], ddz = x[3 * m + 2] - x[3 * n + 2];
            const d2 = ddx * ddx + ddy * ddy + ddz * ddz; if (d2 >= T * T || d2 < 1e-18) continue;
            if (record) { ignore.add(n * N + m); continue; }
            if (ignore.has(n * N + m)) continue;
            const d = Math.sqrt(d2), wsum = w[n] + w[m]; if (wsum === 0) continue;
            const corr = (T - d) / d / wsum;
            x[3 * n] -= ddx * corr * w[n]; x[3 * n + 1] -= ddy * corr * w[n]; x[3 * n + 2] -= ddz * corr * w[n];
            x[3 * m] += ddx * corr * w[m]; x[3 * m + 1] += ddy * corr * w[m]; x[3 * m + 2] += ddz * corr * w[m];
          }
        }
      }
    }
    selfCollide(true);
    S.initialContacts = ignore.size;
    S.step = function (dt, substeps) {
      if (S.paused) return;
      const h = dt / substeps, zmin = S.floor + S.thick / 2;
      const alphaStretch = 0, alphaBend = S.bend > 0 ? 1e-3 / (S.bend * S.bend) / (h * h) : Infinity;
      for (let s = 0; s < substeps; s++) {
        for (let n = 0; n < N; n++) {
          prev[3 * n] = x[3 * n]; prev[3 * n + 1] = x[3 * n + 1]; prev[3 * n + 2] = x[3 * n + 2];
          if (w[n] === 0) continue;
          v[3 * n + 2] -= S.gravity * h;
          x[3 * n] += v[3 * n] * h; x[3 * n + 1] += v[3 * n + 1] * h; x[3 * n + 2] += v[3 * n + 2] * h;
        }
        for (const [p, t] of pins) { x[3 * p] = t[0]; x[3 * p + 1] = t[1]; x[3 * p + 2] = t[2]; }
        if (S.grabbed >= 0 && S.grabTarget) { const g = S.grabbed; x[3 * g] = S.grabTarget[0]; x[3 * g + 1] = S.grabTarget[1]; x[3 * g + 2] = S.grabTarget[2]; }
        const wl = n => (pins.has(n) || n === S.grabbed) ? 0 : w[n];
        for (let it = 0; it < (S.gravity > 0 ? 3 : 2); it++) for (const c of cons) {
          const [a, b, rest, kind] = c, wa = wl(a), wb = wl(b), wsum = wa + wb;
          if (wsum === 0) continue;
          const alpha = kind === 0 ? alphaStretch : alphaBend; if (alpha === Infinity) continue;
          const dx = x[3 * a] - x[3 * b], dy = x[3 * a + 1] - x[3 * b + 1], dz = x[3 * a + 2] - x[3 * b + 2];
          const d = Math.hypot(dx, dy, dz); if (d < 1e-9) continue;
          const lam = -(d - rest) / (wsum + alpha), k = lam / d;
          x[3 * a] += dx * k * wa; x[3 * a + 1] += dy * k * wa; x[3 * a + 2] += dz * k * wa;
          x[3 * b] -= dx * k * wb; x[3 * b + 1] -= dy * k * wb; x[3 * b + 2] -= dz * k * wb;
        }
        for (let n = 0; n < N; n++) if (x[3 * n + 2] < floorZ[n]) { x[3 * n + 2] = floorZ[n]; x[3 * n] = 0.6 * x[3 * n] + 0.4 * prev[3 * n]; x[3 * n + 1] = 0.6 * x[3 * n + 1] + 0.4 * prev[3 * n + 1]; }
        if (s % 3 === 0) selfCollide();
        for (let j = 0; j < C; j++) { const n = id(0, j); x[3 * n] = 0; }
        for (let n = 0; n < N; n++) for (let q = 0; q < 3; q++) v[3 * n + q] = (x[3 * n + q] - prev[3 * n + q]) / h * S.damping;
      }
    };
    S.grid = function () { const G = []; for (let i = 0; i < R; i++) { const row = []; for (let j = 0; j < C; j++) { const k = 3 * id(i, j); row.push([x[k], x[k + 1], x[k + 2]]); } G.push(row); } return G; };
    S.stats = function () {
      let L = 0, Wd = 0, maxStrain = 0;
      for (let i = 0; i + 1 < R; i++) L += dist(id(i, mid), id(i + 1, mid));
      for (let i = 0; i < R; i++) Wd += dist(id(i, 0), id(i, C - 1)) / R;
      for (const [a, b, rest, kind] of cons) if (kind === 0) maxStrain = Math.max(maxStrain, Math.abs(dist(a, b) - rest) / rest);
      return { length: L, width: Wd, lenErr: (L - S.restLen) / S.restLen, widErr: (Wd - S.restWid) / S.restWid, maxStrain };
    };
    S.nearestScreen = null;
    S.encode = function () {                               // CLOTH1|rows|cols|T|base64(int16 x100)
      const a = new Int16Array(N * 3); for (let k = 0; k < N * 3; k++) a[k] = Math.round(x[k] * 100);
      const u8 = new Uint8Array(a.buffer); let s = ''; for (let k = 0; k < u8.length; k++) s += String.fromCharCode(u8[k]);
      const b64 = (typeof btoa !== 'undefined') ? btoa(s) : Buffer.from(u8).toString('base64');
      return 'CLOTH1|' + R + '|' + C + '|' + S.thick + '|' + b64;
    };
    return S;
  }
  // resample a parametric left-half grid (rows x K) to ~ds spacing along the centre column and every 'cstep' column
  function resampleGrid(L, ds, cstep) {
    const K = L[0].length, mid = K >> 1, arc = [0];
    for (let i = 1; i < L.length; i++) { const a = L[i][mid], b = L[i - 1][mid]; arc.push(arc[i - 1] + Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])); }
    const total = arc[arc.length - 1], n = Math.max(2, Math.round(total / ds) + 1), cols = [];
    for (let j = 0; j < K; j += cstep) cols.push(j); if (cols[cols.length - 1] !== K - 1) cols.push(K - 1);
    const out = []; let seg = 0;
    for (let q = 0; q < n; q++) {
      const s = total * q / (n - 1);
      while (seg < arc.length - 2 && arc[seg + 1] < s) seg++;
      const t = (s - arc[seg]) / Math.max(1e-9, arc[seg + 1] - arc[seg]);
      out.push(cols.map(j => { const A = L[seg][j], B = L[seg + 1][j]; return [A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1]), A[2] + t * (B[2] - A[2])]; }));
    }
    return out;
  }
  const api = { makeCloth, resampleGrid };
  if (typeof module !== 'undefined') module.exports = api; else root.Cloth = api;
})(this);
