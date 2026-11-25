# Fits and nominals

Two jobs: turning a measured number into the number the part was actually made to, and turning
a mating requirement into a parameter. Both happen at G1, before anything is modelled.

## 1. Snap measurements to nominals

A trace or a caliper gives 6.37 mm. No one machined 6.37 mm. Reconcile every measured value
against the series it probably came from, and carry **both** numbers into the spec:

```
bore_dia   6.35 mm   measured 6.37, snapped to 1/4in (delta 0.02)
```

If the delta is larger than the measurement's own uncertainty, don't snap — say so and ask.
A 0.4 mm gap to the nearest nominal is a real dimension, not noise.

### Where the numbers come from

| Clue in the part | Series to check |
|---|---|
| a round bore | drill sizes, then fractional inch, then metric whole mm |
| a bore with a shoulder or a press mark | bearing OD/ID, bushing sizes |
| a clearance hole | fastener clearance for M3/M4/M5/M6 or #6/#8/#10/1/4-20 |
| a threaded hole | tap drill for the thread, not the thread major diameter |
| sheet or plate thickness | stock gauge, or 1/16in / 1/8in / 3/16in / 1/4in, or 1/2/3/4/5/6 mm |
| tube or rod | standard OD with a wall from the stock table |
| a hex feature | across-flats for a standard nut or driver |
| a slot | the width of the fastener that runs in it, plus clearance |

### Common snaps worth recognising on sight

| Measured (mm) | Almost certainly |
|---|---|
| 3.15–3.25 | 1/8in (3.175) |
| 4.7–4.85 | 3/16in (4.763) |
| 6.3–6.4 | 1/4in (6.35) |
| 9.4–9.6 | 3/8in (9.525) |
| 12.6–12.8 | 1/2in (12.7) |
| 25.2–25.6 | 1in (25.4) |
| 3.3 | M3 clearance (close fit) |
| 4.5 | M4 clearance (close fit) |
| 5.5 | M5 clearance (close fit) |
| 6.6 | M6 clearance (close fit) |
| 2.5 | M3 tap drill |
| 3.3 | M4 tap drill (same number as the M3 clearance hole — read the context) |
| 4.2 | M5 tap drill |
| 5.0 | M6 tap drill |
| 22 / 8 / 7 | 608 bearing OD / ID / width — the skate bearing in everything |
| 19 / 6 / 6 | 626 bearing |

An imperial part measured in mm gives itself away: several dimensions land within 0.05 mm of a
multiple of 0.3969 mm (1/64in). When two or three do, model the whole part in inch-derived
nominals rather than snapping each dimension independently.

## 2. Clearance as a parameter, not a number

Every mating dimension is derived from one clearance parameter per interface class. One test
fit then retunes every feature at once, which is the entire point.

```
clr_slip     0.20 mm   hand-assembled sliding fit
clr_close    0.10 mm   located, assembled with light force
clr_press   -0.05 mm   interference; press or heat-set
print_clear  0.25 mm   FFF process allowance, tuned by one test print
```

Then:

```
shaft_bore  = shaft_dia + clr_slip + print_clear
pin_pocket  = pin_dia   + clr_press
lid_id      = box_od    + 2 * clr_close
```

Starting values for hand-built and printed assemblies, before any test fit:

| Interface | Diametral allowance |
|---|---|
| free-running, printed | 0.4–0.6 mm |
| sliding by hand, printed | 0.2–0.3 mm |
| located, light push, printed | 0.1–0.15 mm |
| press / heat-set insert, printed | −0.05 to −0.15 mm (pocket smaller than the part) |
| machined slip fit | 0.05–0.1 mm |
| machined press fit | −0.01 to −0.03 mm |

These are starting points, not specifications. State them as assumptions in the spec so the
user can correct them from their own printer or their own stock, and expect the first test fit
to move them.

## 3. Which dimension to hold

When a measured part and a mating requirement disagree, the mating requirement wins and the
measurement becomes the sanity check. Model the **functional** dimension as the driving
parameter and derive the cosmetic ones from it:

- A bracket that bolts to a 40 mm hole pattern is driven by `hole_pitch = 40 mm`. Its outer
  length is `hole_pitch + 2 * edge_dist`, not a measured 52.3 mm.
- A cap that fits a 22 mm bearing is driven by the bearing OD. Its wall is derived; its overall
  diameter is a consequence.

A part whose driving parameters are all silhouette measurements looks right and fits nothing.
Interfaces drive; silhouettes follow.

## 4. Printed-hole allowance

Printed bores come out undersize: elephant foot at the first layers, plus the inward pull of
the perimeter on a curve. Budget 0.1–0.3 mm on diameter for a 0.4 nozzle, more as the hole gets
smaller relative to the nozzle. Holes under about 2 mm are more reliable drilled after printing
than printed to size. Vertical bores (axis along Z) are round; bores printed on their side come
out egg-shaped at the top and need either a teardrop profile or a reamer.

Full print-side treatment: `references/domains/additive.md`.
