#!/usr/bin/env python3
"""
mesh_to_fusion.py - put any mesh (STL/OBJ/PLY/3MF) into Fusion as a named mesh body, safely.

Pipeline:
  1. load (mm), optionally scale, reduce to a Fusion-sized REFERENCE mesh (--target-faces,
     default 8000). Quadric decimation first; if it stalls (long thin triangles, typical of
     generated/boolean meshes) fall back to vertex clustering. For generated parts it is
     better to regenerate at a coarser resolution than to decimate - do that when you can.
     The full-resolution mesh stays the PRINT file; the Fusion mesh is for placement, mating
     and visual checks.
  2. quantize vertices to int16 (auto scale so the part fits), faces uint16/uint32,
     zlib + base64, split into <= 5.7 KB parts with MD5 per part and total.
  3. write chunks/part_NN.py (receivers, send one per fusion_mcp_execute call, in order)
     and chunks/build_mesh.py (<= 6 KB) which reassembles, verifies, then:
        - finds or creates the named component,
        - removes any previous mesh with the same name (inside its base feature's edit) and
          its base feature,
        - creates base feature BASE_<name>, adds the mesh (cm), names it,
        - prints triangle count and bbox (mm) against the expected values and asserts one
          mesh of that name remains.
  4. --verify decodes the packed data locally with the same code the build script uses.

Usage:
  python mesh_to_fusion.py part.stl --name Mesh_Grip --component Comp_Grip --out chunks/ [--target-faces 8000]
  python mesh_to_fusion.py part.stl --name Mesh_Grip --out chunks/ --verify
"""
import argparse, base64, hashlib, json, math, os, struct, zlib
import numpy as np

CHUNK = 5700
DECODE_SRC = r'''
import os, tempfile, hashlib, base64, zlib, struct
def decode_mesh(name, nparts, total_md5, meta):
    s = ''.join(open(os.path.join(tempfile.gettempdir(), '%s.part%02d' % (name, i))).read() for i in range(nparts))
    assert hashlib.md5(s.encode()).hexdigest() == total_md5, 'total MD5 mismatch - resend parts'
    raw = zlib.decompress(base64.b64decode(s))
    nv, nf, q, o = meta['nv'], meta['nf'], meta['quant'], meta['origin']
    vq = struct.unpack('<%dh' % (nv * 3), raw[:nv * 6])
    fmt = '<%dH' % (nf * 3) if meta['fbytes'] == 2 else '<%dI' % (nf * 3)
    F = list(struct.unpack(fmt, raw[nv * 6:]))
    V = [(vq[i] / q + o[i % 3]) / 10.0 for i in range(nv * 3)]      # mm -> cm (Fusion internal)
    return V, F
'''
BUILD_SRC = r'''
import adsk.core, adsk.fusion
NAME, COMP, NPARTS, MD5 = {name!r}, {comp!r}, {nparts}, {md5!r}
META = {meta!r}
{decode}
def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    V, F = decode_mesh(NAME, NPARTS, MD5, META)
    comps = [c for c in design.allComponents if c.name == COMP]
    if comps: comp = comps[0]
    else:
        occ = design.rootComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create()); comp = occ.component; comp.name = COMP
    before = [(m.name, m.mesh.triangleCount) for m in comp.meshBodies]
    bfs = sorted(comp.features.baseFeatures, key=lambda b: b.name != 'BASE_' + NAME)   # the matching base feature first
    for bf in bfs:
        olds = [m for m in comp.meshBodies if m.name == NAME]
        if not olds: break
        bf.startEdit()
        for m in olds:
            if m.isValid:
                m.deleteMe()
        bf.finishEdit()
        if bf.name == 'BASE_' + NAME: bf.deleteMe()
    bf = comp.features.baseFeatures.add(); bf.name = 'BASE_' + NAME
    bf.startEdit(); comp.meshBodies.addByTriangleMeshData(V, F, [], []); bf.finishEdit()
    mb = comp.meshBodies.item(comp.meshBodies.count - 1); mb.name = NAME
    bb = mb.boundingBox; lo = [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10]; hi = [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]
    same = [m for m in comp.meshBodies if m.name == NAME]
    dev = max(abs(a - b) for a, b in zip(lo + hi, META['bbox_lo'] + META['bbox_hi']))
    print('%s in %s: %d tris (expect %d) | bbox dev %.3f mm | meshes named %s: %d | before %s' % (NAME, COMP, mb.mesh.triangleCount, META['nf'], dev, NAME, len(same), before))
    assert len(same) == 1, 'more than one mesh named ' + NAME
'''
RECEIVER = '''import os, tempfile, hashlib
D = \'\'\'{data}\'\'\'
def run(_context: str):
    s = D.replace(chr(10), '')
    h = hashlib.md5(s.encode()).hexdigest()
    if h != '{md5}':
        print('MD5 MISMATCH {name} part {i}/{n}', h, len(s)); return
    with open(os.path.join(tempfile.gettempdir(), '{name}.part{i:02d}'), 'w') as f: f.write(s)
    print('OK {name} part {i}/{n}', len(s))
'''


def reduce_mesh(m, target):
    import trimesh
    if len(m.faces) <= target: return m, 'none'
    try:
        d = m.simplify_quadric_decimation(face_count=target)
        if len(d.faces) <= 1.5 * target: return d, 'quadric'
    except Exception:
        pass
    ext = float(np.max(m.extents)); lo, hi = ext / 2000, ext / 10; best = None
    for _ in range(30):                                  # vertex clustering: bisect the cell size
        c = math.sqrt(lo * hi); key = np.floor((m.vertices - m.bounds[0]) / c).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True); inv = inv.ravel()
        nv = inv.max() + 1; V = np.zeros((nv, 3)); np.add.at(V, inv, m.vertices); V /= np.bincount(inv, minlength=nv)[:, None]
        F = inv[m.faces]; F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
        keep = np.unique(np.sort(F, axis=1), axis=0, return_index=True)[1]; F = F[np.sort(keep)]      # drop duplicate faces
        if len(F) > target: lo = c
        else: hi = c; best = trimesh.Trimesh(V, F, process=True)
        if hi / lo < 1.02: break
    return (best if best is not None else m), 'vertex clustering'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mesh'); ap.add_argument('--name', required=True); ap.add_argument('--component')
    ap.add_argument('--target-faces', type=int, default=8000); ap.add_argument('--scale', type=float, default=1.0, help='multiply input to get mm')
    ap.add_argument('--out', default='chunks'); ap.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    import trimesh
    m = trimesh.load(a.mesh, force='mesh', process=True)
    if a.scale != 1.0: m.apply_scale(a.scale)
    n0 = len(m.faces); r, how = reduce_mesh(m, a.target_faces)
    V = np.asarray(r.vertices, float); F = np.asarray(r.faces, np.int64)
    origin = V.min(0) + (V.max(0) - V.min(0)) / 2
    q = min(100.0, math.floor(32000.0 / max(np.abs(V - origin).max(), 1e-9)))
    vq = np.round((V - origin) * q).astype('<i2')
    fb = 2 if len(V) < 65536 else 4
    raw = vq.tobytes() + F.astype('<u2' if fb == 2 else '<u4').tobytes()
    b64 = base64.b64encode(zlib.compress(raw, 9)).decode(); parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    total = hashlib.md5(b64.encode()).hexdigest()
    Vd = vq.astype(float) / q + origin
    meta = dict(nv=len(V), nf=len(F), quant=q, origin=[round(float(x), 6) for x in origin], fbytes=fb,
                bbox_lo=[round(float(x), 3) for x in Vd.min(0)], bbox_hi=[round(float(x), 3) for x in Vd.max(0)])
    os.makedirs(a.out, exist_ok=True)
    for i, p in enumerate(parts):
        open(os.path.join(a.out, 'part_%02d.py' % i), 'w').write(RECEIVER.format(data='\n'.join(p[k:k + 100] for k in range(0, len(p), 100)),
                                                                                 md5=hashlib.md5(p.encode()).hexdigest(), name=a.name, i=i, n=len(parts)))
    build = BUILD_SRC.format(name=a.name, comp=a.component or 'Comp_' + a.name.replace('Mesh_', ''), nparts=len(parts), md5=total, meta=meta, decode=DECODE_SRC)
    open(os.path.join(a.out, 'build_mesh.py'), 'w').write(build)
    json.dump(dict(meta, parts=len(parts), total_md5=total, source=a.mesh, source_faces=n0, reduction=how), open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1)
    print('%s: %d -> %d faces (%s), quant %.0f/mm (%.3f mm), %d bytes b64 in %d part(s); build_mesh.py %d bytes'
          % (a.name, n0, len(F), how, q, 1 / q, len(b64), len(parts), len(build.encode())))
    if len(parts) > 15: print('NOTE: %d parts is a lot of tool calls - lower --target-faces, or send generator state instead of a mesh' % len(parts))
    if len(build.encode()) > 6000: print('WARNING: build_mesh.py exceeds 6 KB')
    if a.verify:
        import runpy, glob, tempfile
        for f in sorted(glob.glob(os.path.join(a.out, 'part_*.py'))): runpy.run_path(f)['run']('')
        ns = {}; exec(DECODE_SRC, ns); Vc, Fc = ns['decode_mesh'](a.name, len(parts), total, meta)
        Vm = np.array(Vc).reshape(-1, 3) * 10.0; Fm = np.array(Fc).reshape(-1, 3)
        print('verify: decoded %d verts %d faces | max vertex error %.4f mm | faces identical %s'
              % (len(Vm), len(Fm), np.abs(Vm - V).max(), bool((Fm == F).all())))


if __name__ == '__main__':
    main()
