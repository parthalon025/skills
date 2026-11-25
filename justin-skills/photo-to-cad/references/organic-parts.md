# Organic parts that a loft can't express

`cadquery-patterns.md` covers sweeps and lofts, which handle taper, bow and varying
sections. Some photographed parts go further: straps and bands that fold over themselves,
ribbons that curl, hoses that loop, springs, and flexible parts in a relaxed state. Their
surfaces overlap or fold, and a loft through stations either fails or quietly
self-intersects.

## Choose the route

| What the photos show | Route | Tool |
|---|---|---|
| constant or tapering section along a path | sweep / loft | `cadquery-patterns.md` |
| strap, band, ribbon or hose that folds, curls or overlaps | strip generator | `scripts/ribbon_kit.py` |
| blobby, sculpted or blended solid: grip, knob, handle, figure, organic boss | implicit / signed-distance solid | `scripts/sdf_kit.py` |

## Strips

Build them procedurally with `scripts/ribbon_kit.py`:
- a centerline from clamped splines;
- rotation-minimizing frames with explicit twist;
- the exact developable oblique-fold map for creases at any angle;
- side profiles from a curvature schedule (a bend radius and a turn per segment);
- a grid-based thick shell;
- a mirror join and a manifold trim;
- a self-intersection test on the unrolled surface.

`python scripts/ribbon_kit.py --demo out.stl` shows the whole chain.

## Blended solids (SDF)

`scripts/sdf_kit.py` composes named primitives (sphere, rounded box, capsule, cylinder,
torus, ellipsoid, tube with a radius profile) with smooth unions and subtractions, a shell
for uniform walls, and marching cubes to a watertight mesh. Keep the photo-measured numbers
in the parameter block exactly as for CadQuery. Model holes that take hardware as exact
subtractions with a clearance parameter. Self-test watertight, a single body and the
expected genus (the number of through-holes). `python scripts/sdf_kit.py --demo out.stl`
shows a handle end to end.

## Into Fusion

`scripts/mesh_to_fusion.py part.stl --name Mesh_Part --out chunks/` reduces the mesh to a
reference size, writes MD5-verified chunk scripts and a build script that safely replaces
the named mesh body in a base feature, and checks triangle count and bbox. `--verify`
round-trips it locally. Print from the full-resolution STL.

## Consequences to state up front

- The output is a **mesh** (STL/3MF), not a STEP B-rep. Say so when you choose the route.
  If the user needs a STEP, offer a simplified lofted approximation alongside it and label
  it as one.
- The parameter block is still the source: fold angle, bend radii, lengths, width, twist.
  Name them for what the user sees.
- In Fusion, the part arrives as a mesh body inside a base feature, with a spine sketch for
  design intent. Rigid features that mate with it stay sketch-first.

## Topology first

Photos underdetermine folds more than anything else: which way it folds, over or under, U or
Z, where the free end tucks. Before generating, show your reading as a numbered traced path
on the photo plus a side-profile plot, and get it confirmed. A clean mesh with the wrong
topology passes every metric (`operating-principles.md` §3–4).
