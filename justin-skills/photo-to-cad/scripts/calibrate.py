#!/usr/bin/env python3
"""Pixel-to-mm calibration for measuring a part against a scale reference.

Only useful when the uploaded images are actually on disk (check /mnt/user-data/uploads).
If they aren't, measure visually and say so -- don't pretend to have run this.

Two modes:

  Establish scale from two reference ticks a known distance apart, then convert
  measured pixel distances:

    python calibrate.py --ref 1410 620 950 620 --ref-mm 20 \\
        --measure 1050 540 1640 915

  Auto-estimate grid pitch from a horizontal or vertical strip of the image
  (works on a printed grid with strong lines):

    python calibrate.py --image mat.jpeg --grid-strip 600 900 --axis x --pitch-mm 10

Reported scale is only as good as the baseline: span ten grid squares, not one.
Anything measured on a part elevated off the reference plane (macro shots) is invalid
regardless of what this prints.
"""
import argparse
import math


def dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def auto_pitch(image, lo, hi, axis):
    """Estimate grid pitch in px via autocorrelation of a bright-line profile."""
    import numpy as np
    from PIL import Image

    im = np.asarray(Image.open(image).convert("L"), dtype=float)
    strip = im[lo:hi, :] if axis == "x" else im[:, lo:hi]
    prof = strip.mean(axis=0 if axis == "x" else 1)
    prof = prof - prof.mean()
    ac = np.correlate(prof, prof, mode="full")[len(prof) - 1:]
    ac[:5] = 0
    lag = int(np.argmax(ac[: len(ac) // 2]))
    return lag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"),
                    help="two reference points with a known separation")
    ap.add_argument("--ref-mm", type=float, help="true distance between --ref points, mm")
    ap.add_argument("--measure", nargs=4, type=float, action="append",
                    metavar=("X1", "Y1", "X2", "Y2"),
                    help="a distance to convert; repeatable")
    ap.add_argument("--image")
    ap.add_argument("--grid-strip", nargs=2, type=int, metavar=("LO", "HI"))
    ap.add_argument("--axis", choices=["x", "y"], default="x")
    ap.add_argument("--pitch-mm", type=float, default=10.0,
                    help="true grid pitch, mm (10 for a 1 cm mat)")
    args = ap.parse_args()

    px_per_mm = None

    if args.ref and args.ref_mm:
        d = dist(*args.ref)
        px_per_mm = d / args.ref_mm
        print("reference: %.1f px over %.2f mm  ->  %.4f px/mm"
              % (d, args.ref_mm, px_per_mm))

    if args.image and args.grid_strip:
        lag = auto_pitch(args.image, args.grid_strip[0], args.grid_strip[1], args.axis)
        print("grid pitch: %d px  ->  %.4f px/mm" % (lag, lag / args.pitch_mm))
        if px_per_mm is None:
            px_per_mm = lag / args.pitch_mm

    if px_per_mm is None:
        ap.error("give --ref/--ref-mm or --image/--grid-strip")

    for m in args.measure or []:
        d = dist(*m)
        print("  %.1f px  =  %.2f mm" % (d, d / px_per_mm))


if __name__ == "__main__":
    main()
