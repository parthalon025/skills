#!/usr/bin/env python3
"""Render orthographic views of an STL for visual comparison against photos.

Usage:
    python render_views.py part.stl views.png
    python render_views.py part.stl views.png --labels "bend plane (cf. IMG_4198)" \
        "face on (cf. IMG_4199)" "end on (cf. IMG_4201)" "iso"

Four panels by default: two orthogonal in-plane views, one end-on, one iso. Label each
with the photo it should be compared against so the comparison is direct.

Needs numpy + matplotlib only (no mesh library) -- binary STL is parsed inline.
"""
import argparse
import struct

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

VIEWS = [(0, 0), (0, 90), (90, -90), (24, 35)]
DEFAULT_LABELS = ["front (X axis)", "side (Y axis)", "end on (Z axis)", "iso"]


def load_stl(path):
    with open(path, "rb") as f:
        header = f.read(80)
        if header.lstrip()[:5] == b"solid" and b"facet" in f.read(512):
            return load_ascii_stl(path)
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
        tris = np.empty((n, 3, 3), dtype=np.float32)
        for i in range(n):
            d = struct.unpack("<12fH", f.read(50))
            tris[i] = np.array(d[3:12]).reshape(3, 3)
    return tris


def load_ascii_stl(path):
    verts = []
    with open(path) as f:
        for line in f:
            if line.strip().startswith("vertex"):
                verts.append([float(v) for v in line.split()[1:4]])
    return np.array(verts, dtype=np.float32).reshape(-1, 3, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("out")
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--color", default="#d9a520")
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args()

    tris = load_stl(args.stl)
    pts = tris.reshape(-1, 3)
    centre = pts.mean(axis=0)
    span = np.abs(pts - centre).max() * 1.05
    labels = (args.labels or [])[:4] + DEFAULT_LABELS[len(args.labels or []):]

    bb = pts.max(axis=0) - pts.min(axis=0)
    print("bbox mm  X %.2f  Y %.2f  Z %.2f   (%d triangles)"
          % (bb[0], bb[1], bb[2], len(tris)))

    fig = plt.figure(figsize=(13, 11))
    for k, ((elev, azim), label) in enumerate(zip(VIEWS, labels), 1):
        ax = fig.add_subplot(2, 2, k, projection="3d")
        ax.add_collection3d(Poly3DCollection(
            tris, facecolor=args.color, edgecolor="#8a6a10", linewidths=0.12))
        ax.set_xlim(centre[0] - span, centre[0] + span)
        ax.set_ylim(centre[1] - span, centre[1] + span)
        ax.set_zlim(centre[2] - span, centre[2] + span)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        try:
            ax.set_proj_type("ortho")
        except Exception:
            pass
        ax.set_title(label, fontsize=11)
        ax.set_xlabel("X mm")
        ax.set_ylabel("Y mm")
        ax.set_zlabel("Z mm")
    plt.tight_layout()
    plt.savefig(args.out, dpi=args.dpi)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
