# Image → build spec

Reference images come in four flavours and each is read differently. Identify which you have before measuring anything.

| Input | What it gives you | What it never gives you |
|---|---|---|
| Engineering drawing / CAD screenshot with dimensions | exact numbers, tolerances, views | nothing — trust it, transcribe it |
| Caliper or ruler photo | one reliable dimension + the shape | anything off the measured axis |
| Plain photo of a part | proportions, feature topology | absolute scale, hidden features, depth |
| Napkin sketch / whiteboard | intent and topology | precision of any kind |

## 1. Read the image before measuring it

Describe what you see back to the user in structural terms, not adjectives: number of distinct features, which are through vs. blind, which faces are planar vs. curved, where the symmetry is. This surfaces misreadings while they are still cheap, and it tells the user what you can and cannot see from that angle.

Call out explicitly:

- **Occluded geometry** — "the back face isn't visible in either photo"
- **Perspective distortion** — a photo shot at an angle makes rectangles into trapezoids. Do not read proportions off a perspective shot as if it were orthographic; say so and ask for a straight-on shot if proportions matter.
- **Features you can see but not size** — fillets, chamfers, draft.

## 2. Establish scale

Nothing gets built until one real dimension is pinned. In order of preference:

1. **User-stated dimension** — ask for one: "what's the overall length?" One number plus proportions gets you everything else.
2. **Caliper or ruler in frame** — read the value; use it as the calibration length.
3. **Known object in frame** — a coin, a standard fastener, a printed grid, graph paper. State which you used and its assumed size.
4. **Standard feature** — a hole that is clearly meant for an M3 screw, a 1/4-20 thread, a standard bearing OD. State the inference.

Then scale everything else by ratio:

```
calibration: caliper jaw reads 6.5 mm, spans 41 px  →  0.1585 mm/px
overall length: 303 px  →  48.0 mm  (±1 mm, pixel-measurement error)
nose radius:     19 px  →   3.0 mm  (±0.5 mm)
```

Report derived dimensions **with their uncertainty** and round them to something manufacturable — 48 mm, not 48.03 mm. A photo does not justify two decimal places. Mark every derived number as derived in the spec so the user knows which ones to correct.

If there is no scale reference at all, that is a blocking unknown. Ask; do not pick a size.

## 3. Separate shape from size

Proportions survive perspective better than absolute sizes do. Extract the topology first — "closed outer profile with a rounded nose, one through bore near the nose, constant thickness, symmetric about the long axis" — and get that confirmed. The numbers can be corrected later with one parameter edit; a wrong topology means rebuilding the sketch.

## 4. Choose the datum from the image

Pick the origin and orientation that make the model editable, and say what you picked:

- Origin at the part's symmetry centre or at a natural datum feature (a mounting face, a bore axis), not at an arbitrary corner.
- Put the main profile on the plane matching the view you're tracing — a top-down photo maps to XY, a side profile to XZ or YZ.
- If the part is symmetric, sketch **half** and mirror. It halves the constraint work and makes symmetry a property of the model rather than a coincidence.

## 5. Write the spec

Turn the reading into the build spec block in SKILL.md §2. Every dimension carries its source:

```
PARAMETERS
  name        value     source
  body_len    48 mm     derived from caliper photo (±1 mm)
  bore_dia    6.5 mm    measured directly, caliper
  wall        2.0 mm    ASSUMED — printable minimum, not visible in photo
  nose_r      3.0 mm    derived (±0.5 mm)
```

`ASSUMED` is the important tag. Those are the lines the user will scan and correct.

## 6. Verify against the source image

When you screenshot the model, take the view that matches the reference photo's angle (`front`, `top`, `right`, or an iso) so the two can be compared directly. Then compare specifically:

- silhouette match — where does the outline diverge?
- feature placement — is the bore at the same fraction of the length?
- proportion check — length:width ratio in the model vs. in the image

Report the deltas in those terms. "Looks good" is not a verification; "silhouette matches except the tail is squarer than the photo's radius" is.

## 7. Screenshots of Fusion itself

If the user sends a screenshot of their own Fusion session rather than a part, they are usually pointing at a problem: a red timeline marker, a failed feature, an over-constrained sketch, a dialog they're stuck in. Read the UI, then confirm what you inferred with a read-only script (timeline health, sketch state) rather than acting on the picture alone — the screenshot may be stale.

## 8. Canvas tracing

If the image exists as a file **on the machine running Fusion**, attaching it as a canvas and tracing over it is more accurate than pixel arithmetic. See §9 of `api-recipes.md`. Calibrate the canvas against the known dimension first; an uncalibrated canvas produces a model that looks right and measures wrong.

Images that only exist in the chat cannot be attached — work from the measured spec.

## 9. 3D topology from 2D references: confirm before you build

A plan view fixes plan positions; it does **not** fix 3D topology. Several different topologies
match it:
- whether a lip bends up or down;
- whether a boss is hollow;
- whether a rib runs through;
- which way a fold or roll goes;
- whether a dip is a U or a Z.

Guessing costs one full build per wrong guess, and on organic parts that can run to a dozen
iterations on a single feature. The protocol that ends the loop:

1. **Say what the image can't tell you** before modeling: "from the top I can't see whether
   this rolls toward the blade or the band".
2. **Show your reading, don't describe it.** Draw your traced interpretation on the
   reference as numbered, colored paths ("1 → 2 → 3 → 4, is this the flow?"). Draw the implied side profile as a plain line plot. Ask "is this the flow?"
   One round of that replaces several build iterations. The user's corrections come back
   precise ("4 is the back side you can't see", "3 goes up, then back down").
3. **Ask for the cheapest disambiguating input:**
   - a side-profile sketch of the path;
   - colored strokes on the image (extract them by color mask and convert to mm; say they're
     guides, not exact);
   - any second view, even an AI render. Read it on both mirrored halves: they show the
     front and the back of the same feature.
4. **Treat every correction as a topology change first**, parameter change second, and
   re-confirm the diagram before the next build.
5. When intent is visual and iterative, move the loop into an interactive preview the user
   drives (`co-design-tools.md`).

For measurement from two views (camera solving, markers, triangulation, fitting), see
`photo-matching-and-markers.md`.
