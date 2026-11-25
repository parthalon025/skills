# Procedural and organic parts

Some geometry is described better by a rule than by a sketch:
- a strap or ribbon that folds and curls;
- a hose or cable run with bend-radius limits;
- a coil or spring;
- a lattice;
- a fairing that follows a path;
- a relief whose layers stack over each other.

Sketch → extrude/sweep can't carry folds and self-overlap, and the API can't drive T-Spline
sculpting (see `surface-form.md`). The route that works is a **procedural generator**
outside Fusion. It owns the organic shape as named parameters and produces a watertight
mesh. Fusion keeps everything rigid parametric and carries the organic part as a mesh body
plus a design-intent sketch (a spine, path or outline).

This is the one sanctioned exception to "sketches first". Declare it at G1 ("hybrid design
intent"), and name what stays parametric in Fusion and what lives in the generator.

Use it only when a sweep, loft or pipe genuinely can't express the shape. A path that never
overlaps itself, with a constant section, is still a sweep from a sketch.

## Contents
1. Architecture
2. Strips: centerline + frames
3. Real folds: the developable oblique-fold map
4. Profiles by curvature schedule
5. Thick shell from a surface grid
6. Symmetry, seams and trimming
7. Self-intersection: test on the unrolled surface
8. Layer heights from clearance, not guesses
9. Validation and gates
10. Topology first

## 1. Architecture

```
params ──► generator (python, one source of truth)
              ├─ path / centerline segments (splines, profile curves)
              ├─ frames (tangent, normal, width vector, width)
              ├─ surface grid (rows along, K columns across)
              └─ thick mesh ─► boolean trim ─► watertight mesh
                       │
         ┌─────────────┼──────────────────┐
     Fusion mesh   intent sketch      JS port (preview / fitting, optional)
     (base feat.)  (≤120 pts)         parity-tested to 1e-5 mm
```

- One generator module, and parameters as a flat dict with declared bounds. The dict *is*
  the part definition: version it and record the resolved dict in the build script.
- Name parameters for what a person would call them ("arch radius", "fold angle", "sag
  depth"), not `r2` or `k3`. The user will steer by those names.
- Any second runtime (a browser preview or a fitter) is a **port**. Parity-test it: same
  params in both, max point deviation of the grids, require 0.0000 mm, rerun after every
  generator edit. A half-applied edit is the most common silent divergence.

`scripts/ribbon_kit.py` holds the reusable pieces below.

## 2. Strips: centerline + frames

A strip is a centerline `c(s)`, an orthonormal frame per station (`t` tangent, `n` surface
normal, `w = n × t` width direction) and a width `W(s)`. The surface is
`c(s) + u·W(s)·w(s)` for `u ∈ [−½, ½]`. A hose or cable is the same model with a circular
section instead of a line.

- **Frames:** use a rotation-minimizing frame (project the previous normal onto the plane
  normal to `t`, then renormalize). Frenet frames flip at inflections.
- **Twist and bank** are explicit rotations of `n` about `t`, eased (smoothstep), never a
  by-product of frame drift.
- **Lock the width level** where the design wants no twist (`w = unit(t_y, −t_x, 0)`). A path
  that climbs, falls and moves sideways at once accumulates plan twist under an RMF, and on
  a wide strip the outer edge folds back over itself.
- **Flare / taper** by moving one edge only (`X += w · flare · (u + ½)`), so the other edge
  keeps its line.
- Build paths from **clamped cubic splines** with explicit end tangents. Keep the control
  points monotonic along the direction of travel, and derive waypoints from upstream
  endpoints rather than fixing them. A fixed waypoint that a longer upstream segment has
  already passed makes the path double back, which is invisible in plan.

## 3. Real folds: the developable oblique-fold map

A rigid hairpin bent in a tilted plane is not a fold; it self-intersects once it's skewed more
than about 12°. For a crease at any angle, use the exact developable map. Parametrize the
strip flat as `(σ along, s across)`, rotate by the crease angle `α` into
`(ξ along the crease, η perpendicular)`, and roll only `η` through a side profile:

```
ξ =  σ·sinα + s·cosα         η = σ·cosα − s·sinα
X(σ,s) = O + ξ·e + qn(η)·n̂ + qu(η)·ẑ      (η<0 → flat: qn=η, qu=0)
```

- A 180° roll of radius `r` in the profile is a folded crease along `e`. After it the strip
  travels in the mirrored direction; a 45° crease turns the strip 90°.
- Over versus under is the sign of the profile's curvature.
- End the strip at constant `σ`, sized so every fibre has cleared the roll:
  `σ_end = (η_needed + W/2·sinα)/cosα`. The last row is then flat and straight, and a second
  stage can continue from it.
- Match column orientation to the incoming grid (nearest-corner test) before concatenating.

The same map gives sheet-like parts made from flat stock (a folded tab, a wrapped label)
their true developable shape.

## 4. Profiles by curvature schedule

Describe any side profile (a U sag, a C, an arch, a hook, a Z) as segments of
`(radius, turn)` or `(straight, length)`, and integrate heading along arc length:

```
θ(η) = ∫ κ dη,   qn = ∫ cos θ,   qu = ∫ sin θ
segments = [(None, lead), (r1, +90°), (None, rise), (R, −turn), (None, fall)]   # an arch
```

Every parameter is then something the user can name. A soft sag (a general U, not a
literal one) comes from spline-fitting samples of a shape function, e.g.
`z(u) = z_bot + (z_edge − z_bot)·|1 − 2u|^p`, with horizontal end tangents. `p` goes from V
to flat-bottomed.

## 5. Thick shell from a surface grid

Build the mid-surface as a `rows × K` grid (K = 13–21). Offset ±T/2 along per-vertex
normals (`cross(∂row, ∂col)`, central differences), and emit top and bottom quads, side walls
and end caps with consistent winding. A grid is required once the strip wraps obliquely,
because a straight cross-line cuts through the wrap. Check watertight; flip if the volume is
negative. Keep the **edge-strip faces separate from the core**, which gives a free second
body or material group for a contrasting edge band, a separate print color, or an inlay.

## 6. Symmetry, seams and trimming

For symmetric parts, generate half, then mirror, reverse the rows, re-order the columns so
the seam rows coincide, and drop the duplicate row. The seam needs a tangent perpendicular
to the mirror plane. Trim against other bodies (a base plate, a wall) with a manifold
boolean in the sandbox, never by clamping vertices (`large-payloads-and-meshes.md` §7).

## 7. Self-intersection: test on the unrolled surface

Nearest-neighbour tests on the grid give false positives at folds and seams. A pair of points
is a clash when it is **closer than T in 3D but farther than 3T apart on the unrolled
surface**, with σ = arc length along the center fibre and s = column offset × row width. Run
it per region. Report the count and the closest pair's location, and show it live in any
preview. It turns "passes through itself" from a print-time surprise into a readout.

## 8. Layer heights from clearance, not guesses

When parts stack (a relief under an overlay under a cap, or a cable under a bracket), derive
each layer's height from the geometry beneath it:

```
layer_z = max over lower-part vertices inside the upper part's footprint (point-in-polygon)
          of  z_top + half_thickness(upper) + clearance
```

Recompute on every change to the lower part and feed the result into Fusion parameters.
Small edits below move everything above by surprising amounts; the readout makes that
visible.

## 9. Validation and gates

Per generator change, report:
- watertight
- the unrolled clash count
- min / max extents of each named section
- the IoU of the relevant projection against the reference mask, with pixels hidden by
  other parts in the reference masked out ("visible IoU")
- parity deviation, if a port exists

Accept a generator gate on those plus a camera-matched visual
(`photo-matching-and-markers.md`), not on numbers alone.

## 10. Topology first

A 2D reference doesn't fix 3D topology: which way something rolls, over or under, U or Z,
standing or lying. A generator can be geometrically clean and topologically wrong, and every
metric above will still pass. Confirm topology as a diagram (numbered traced path plus side
profile) before writing generator code. See `image-to-spec.md` §9 and
`agent-operating-principles.md` §3–4.

*Worked example:* on a heraldic scroll, a dozen clean generator versions were each rejected
on topology. What converged was the user's side sketch, one numbered-trace confirmation
round, and a second view read on both mirrored halves.
