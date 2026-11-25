#!/usr/bin/env python3
"""
payload_chunker.py - move large data into Fusion through the MCP script limit, verified.

Fusion MCP scripts above ~6.5 KB are unreliable, and retyping data blocks between tool calls
is the most common silent corruption. This packs an array (or JSON / bytes) into compressed,
quantized, MD5-checked parts and WRITES the receiver scripts for you: the agent pastes
generated text and never retypes data.

  pack    data -> chunks/part_00.py .. part_NN.py  (send each as a fusion_mcp_execute script)
          + chunks/manifest.json + chunks/loader_snippet.py (paste into the consuming script)
  unpack  local round-trip check of a packed set (same code path the loader uses)

Usage:
  python payload_chunker.py pack frames.npy --quant 100 --name scroll_frames --out chunks/
  python payload_chunker.py pack spine.json --quant 100 --name spine --out chunks/
  python payload_chunker.py unpack chunks/ --check frames.npy

Quantization: values * quant, rounded, stored as int16 (range +-32767/quant). mm*100 gives
+-327 mm at 0.01 mm. Pass --quant 10000 for unit vectors. Mixed columns: pass --col-quant
"100,100,100,10000,10000,10000" for a 2-D array.
"""
import argparse, base64, hashlib, json, os, sys, zlib
import numpy as np

CHUNK = 5700
RECEIVER = '''import os, tempfile, hashlib
D = \'\'\'{data}\'\'\'
def run(_context: str):
    s = D.replace(chr(10), '')
    h = hashlib.md5(s.encode()).hexdigest()
    if h != '{md5}':
        print('MD5 MISMATCH {name} part {i}/{n}', h, len(s)); return
    fn = os.path.join(tempfile.gettempdir(), '{name}.part{i:02d}')
    with open(fn, 'w') as f: f.write(s)
    print('OK {name} part {i}/{n}', len(s))
'''
LOADER = '''# --- paste into the consuming Fusion script -------------------------------------------
import os, tempfile, hashlib, base64, zlib, struct
def load_{name}():
    """{name}: {shape} int16, quant {quant_desc}. Returns a list of rows (floats)."""
    parts = [open(os.path.join(tempfile.gettempdir(), '{name}.part%02d' % i)).read() for i in range({n})]
    s = ''.join(parts)
    assert hashlib.md5(s.encode()).hexdigest() == '{total_md5}', 'total MD5 mismatch - resend parts'
    raw = zlib.decompress(base64.b64decode(s))
    v = struct.unpack('<%dh' % (len(raw) // 2), raw)
    q = {quants}; cols = {cols}
    return [[v[r * cols + c] / q[c] for c in range(cols)] for r in range(len(v) // cols)]
'''


def load_any(path):
    if path.endswith('.npy'):
        return np.load(path)
    if path.endswith('.json'):
        return np.array(json.load(open(path)), dtype=float)
    raise SystemExit('pack expects .npy or .json (numeric array)')


def pack(args):
    a = np.atleast_2d(load_any(args.data).astype(float))
    if a.shape[0] == 1 and a.ndim == 2 and args.data.endswith('.json') and a.shape[1] > 16:
        a = a.T
    rows, cols = a.shape
    q = [float(x) for x in args.col_quant.split(',')] if args.col_quant else [args.quant] * cols
    if len(q) != cols:
        raise SystemExit('--col-quant needs %d values' % cols)
    qa = np.round(a * np.array(q)[None, :])
    if np.abs(qa).max() > 32767:
        raise SystemExit('overflow: max |value*quant| = %.0f > 32767; lower --quant' % np.abs(qa).max())
    b64 = base64.b64encode(zlib.compress(qa.astype('<i2').tobytes(), 9)).decode()
    parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    os.makedirs(args.out, exist_ok=True)
    total = hashlib.md5(b64.encode()).hexdigest()
    man = dict(name=args.name, rows=rows, cols=cols, quant=q, parts=len(parts), total_md5=total,
               part_md5=[hashlib.md5(p.encode()).hexdigest() for p in parts], b64_len=len(b64))
    for i, p in enumerate(parts):
        wrapped = '\n'.join(p[k:k + 100] for k in range(0, len(p), 100))
        code = RECEIVER.format(data=wrapped, md5=man['part_md5'][i], name=args.name, i=i, n=len(parts))
        open(os.path.join(args.out, 'part_%02d.py' % i), 'w').write(code)
        if len(code.encode()) > 6400:
            print('WARNING part %d script is %d bytes (> 6.4 KB)' % (i, len(code.encode())))
    open(os.path.join(args.out, 'manifest.json'), 'w').write(json.dumps(man, indent=1))
    open(os.path.join(args.out, 'loader_snippet.py'), 'w').write(LOADER.format(
        name=args.name, shape='%dx%d' % (rows, cols), quant_desc=q if len(set(q)) > 1 else q[0], n=len(parts),
        total_md5=total, quants=q, cols=cols))
    print('packed %s: %dx%d -> %d bytes b64 in %d part(s); total md5 %s' % (args.name, rows, cols, len(b64), len(parts), total))
    print('send part_00.py .. part_%02d.py in order, one per fusion_mcp_execute call; then use loader_snippet.py' % (len(parts) - 1))


def unpack(args):
    man = json.load(open(os.path.join(args.dir, 'manifest.json')))
    s = ''
    for i in range(man['parts']):
        code = open(os.path.join(args.dir, 'part_%02d.py' % i)).read()
        d = code.split("'''")[1].replace('\n', '')
        assert hashlib.md5(d.encode()).hexdigest() == man['part_md5'][i], 'part %d md5' % i
        s += d
    assert hashlib.md5(s.encode()).hexdigest() == man['total_md5']
    v = np.frombuffer(zlib.decompress(base64.b64decode(s)), dtype='<i2').astype(float).reshape(man['rows'], man['cols'])
    v /= np.array(man['quant'])[None, :]
    print('unpacked %s %s' % (man['name'], v.shape))
    if args.check:
        ref = np.atleast_2d(load_any(args.check).astype(float))
        if ref.shape != v.shape and ref.T.shape == v.shape:
            ref = ref.T
        print('max abs error vs %s: %.6f' % (args.check, np.abs(ref - v).max()))
    return v


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('pack'); p.add_argument('data'); p.add_argument('--name', required=True)
    p.add_argument('--quant', type=float, default=100.0); p.add_argument('--col-quant'); p.add_argument('--out', default='chunks')
    u = sp.add_parser('unpack'); u.add_argument('dir'); u.add_argument('--check')
    a = ap.parse_args()
    pack(a) if a.cmd == 'pack' else unpack(a)
