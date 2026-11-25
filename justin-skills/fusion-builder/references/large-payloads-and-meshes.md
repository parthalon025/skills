# Large payloads, fitted curves and mesh bodies

Anything generated outside Fusion — a traced point cloud, a procedural or scanned mesh, a
3D path, hundreds of fit points — has to cross the MCP script boundary. That boundary has limits the
API documentation doesn't mention, and crossing it wrong fails silently more often than loudly.

## Contents
1. The script payload limit
2. Chunked transfer with verification
3. Quantize before you compress
4. Fitted 3D splines: the silent point-count ceiling
5. Mesh bodies through a base feature
6. Replacing a mesh without leaving the old one behind
7. Clip meshes outside Fusion, not by clamping vertices
8. Checklist

## 1. The script payload limit

A `fusion_mcp_execute` script much above **~6.5 KB** is unreliable. Keep every script under
~6 KB including the embedded data. Code plus a 5.7 KB base64 block is the practical maximum.

## 2. Chunked transfer with verification

Never retype a data block from memory into a later script. Transcription errors are the most
common failure in this path, and they produce plausible-looking garbage rather than an error.
The protocol that works:

1. In the sandbox: serialize → `zlib.compress(level=9)` → base64 → split into ≤ 5.7 KB parts.
   Compute the MD5 of every part and of the whole string.
2. Print one part, then send it **immediately** in the next tool call, wrapped in a
   receiver script that recomputes the MD5 and refuses to write on mismatch.
   Each part is stored in `tempfile.gettempdir()` (append by part index).
3. The last script reassembles, checks the total MD5, decompresses, and builds.
4. Print sizes and hashes on every step, so a mismatch names the part to resend.

`scripts/payload_chunker.py` does all of this. It emits the receiver scripts ready to paste,
so the agent only copies generated text and never retypes data.

```bash
python scripts/payload_chunker.py pack frames.npy --quant 100 --out chunks/
#  -> chunks/part_00.py ... part_NN.py (receivers), chunks/manifest.json (md5s)
```

## 3. Quantize before you compress

Geometry rarely needs float64. Store mm × 100 as `int16` (±327 mm range at 0.01 mm), unit
vectors × 10000 as `int16`. Example: frames for a strip (position, normal, width vector, width = 10 numbers per station)
came to ~11 KB for 500 stations after zlib, which is two chunks. Raw float JSON of the same
data was ~120 KB.

Send the **generator state**, not the mesh, whenever the receiving script can rebuild the
mesh from it cheaply: stations + frames rebuild the whole thick ribbon in a few lines of
Python inside Fusion.

## 4. Fitted 3D splines: the silent point-count ceiling

`sketchFittedSplines.add()` with more than **~120–130** fit points in one script can fail
without an exception, leaving no curve. Keep 3D spline fits at **≤ 120 points**, chosen by
curvature rather than uniformly:

```python
w = np.cumsum(seg_len / 9.0 + turn_angle / 0.6)            # arc length + turning, weighted
idx = np.unique(np.r_[0, np.searchsorted(w, np.arange(0, w[-1], 1.0)), len(pts) - 1])
```

Then **prove** the subsample. Fit a `scipy.interpolate.CubicSpline` through the chosen
points (chord-length parameter), sample it densely, and take the max distance back to the
full curve with a KD-tree. Report `maxdev`. Accept ≤ 0.1 mm for a design-intent sketch.
Also set `spline.isFixed = True` for reference geometry, and print `fitPoints.count`, the
length and the Z range from Fusion, to compare against the sandbox numbers.

## 5. Mesh bodies through a base feature

Personal use allows mesh bodies inside a base feature (parametric designs need the base
feature wrapper):

```python
bf = comp.features.baseFeatures.add(); bf.name = 'BASE_part_mesh_v3'
bf.startEdit()
comp.meshBodies.addByTriangleMeshData(V_cm, F_idx, [], [])   # coords in CM, flat lists
bf.finishEdit()
mb = comp.meshBodies.item(comp.meshBodies.count - 1); mb.name = 'Mesh_Part'
```

- Coordinates are **cm** (internal units), same as everything else in the API.
- Normals can be passed empty; Fusion computes them.
- Verify with `mb.mesh.triangleCount` and the bounding box against the sandbox mesh. They
  must match to rounding. A bbox mismatch means a units or axis error, not a modeling
  error.

## 6. Replacing a mesh without leaving the old one behind

Base-feature names are not reliable handles across sessions. A rename can silently fail,
and `baseFeatures.itemByName()` then returns `None`. The result is two meshes stacked in one
component, and the old one keeps its name. Always:

1. List `comp.features.baseFeatures` and `comp.meshBodies` (name + triangle count) **before**
   replacing.
2. Delete the old mesh **inside** the edit of the base feature that owns it:
   `bf.startEdit(); old_mesh.deleteMe(); bf.finishEdit()`. A mesh body can't be deleted from
   outside its base feature.
3. List again afterwards and assert exactly one mesh, with the new triangle count.

## 7. Clip meshes outside Fusion, not by clamping vertices

To trim a mesh at a plane (a part that dips into its base), don't clamp vertex Z inside
the receiver. Clamping folds triangles over each other, and Fusion shows them as
pink/inverted slivers. Do the trim in the sandbox with a real boolean
(`manifold3d`: `mesh ^ halfspace_box`) and send the clipped, watertight result. Check
`trimesh.is_watertight` before sending.

## 8. Checklist

- [ ] script ≤ 6 KB, data ≤ 5.7 KB per part
- [ ] every part MD5-checked on arrival; total MD5 checked before use
- [ ] int16 quantization; generator state sent instead of mesh where possible
- [ ] 3D spline ≤ 120 fit points, curvature-weighted, maxdev reported
- [ ] mesh inside a named base feature; count and bbox match the sandbox
- [ ] old mesh deleted inside its base-feature edit; one mesh left, asserted
- [ ] clipping done by boolean in the sandbox, watertight before transfer
