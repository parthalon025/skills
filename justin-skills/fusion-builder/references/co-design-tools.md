# Interactive co-design tools

When the user's intent is visual (a shape, a flow, a feel), text is a lossy channel.
Descriptions like "not a literal U", "it curls from the top down" or "the back slopes" can
take several turns each to decode. A small interactive page the user drives changes the loop
from "describe → agent guesses → user corrects" to "user shapes → agent builds". Publish
these as artifacts. They're quick to build and usually pay back within one iteration.

**When to build one:** two rounds of text corrections on the same feature, or a part whose
parameters the user would rather see than read. See `agent-operating-principles.md` §4.

## Contents
1. Live parametric preview
2. Freeform mode (inextensible sheet or strip)
3. Marker board (two-camera measurement)
4. Hand-off between tools and back to the build
5. Testing the tools headlessly
6. Pitfalls

## 1. Live parametric preview

- The preview runs a **port of the build generator** (or of the parameter math for a
  sketch-based part), parity-tested against the build side to 0.0000 mm. Without parity,
  what the user tunes is not what gets built.
- Sliders are grouped **the way the user thinks about the part**: along its path, by feature,
  or by function. Label them in the user's words, not variable names ("Crest height", "Wall",
  "Snap-fit overlap"), with units, and ranges equal to the declared parameter bounds.
- Context geometry sits at true positions: mating parts, the build plate, the enclosure it
  lives in. Place them at **derived** positions so clearance changes are visible.
- A live readout of consequences: minimum gaps, derived heights, minimum feature at the final
  scale, overhang share, a self-intersection flag, rebuild time. Only real violations turn
  red. When the user declares a constraint irrelevant, show it as information, not a warning.
- A **reference underlay** registered in world coordinates, toggleable, with a near-orthographic
  plan view for registration (`photo-matching-and-markers.md` §2).
- **User-stated rules become automatic, resolved parameters** ("keep X level with the peak",
  "lift Y instead of letting it hit Z"). The export writes resolved values.
- Preset views, including one per solved reference camera, plus orbit, pan and zoom.
- A camera hook (`window.__compare.set({pos, target, up, fov})`) and a UI-hide call, so a test
  harness can render from any solved camera.

## 2. Freeform mode (inextensible sheet or strip)

For intent no parameter captures, `assets/cloth.js` is an XPBD solver for a strip or sheet
that holds its length and width:
- stiff distance constraints along, across and on both diagonals;
- soft skip-one bending constraints with adjustable stiffness;
- a **per-particle floor** (`min(z0, floor + T/2)`) so the initial state is at rest;
- self-collision through a numeric spatial hash, ignoring pairs in contact at the start;
- drag with pin on release, double-click to unpin;
- for symmetric parts, half simulated and mirrored, with the seam pinned.

Start it from the current parametric shape. At rest it should drift under 0.2 mm with about
0.01% strain; check that in Node before shipping. Export a compact code
(`CLOTH1|rows|cols|T|base64(int16 × 100)`), about 10 KB. It decodes in Python to 0.005 mm,
and that grid becomes the generator's input or a fitting target. For display, upsample across
the width (Catmull-Rom) so edge bands render at true scale.

## 3. Marker board (two-camera measurement)

`assets/marker_board_template.html` has:
- two reference images with solved cameras;
- labelled markers;
- height-ticked guide lines from a point in one image into the other;
- triangulation, and obscured points placed by height;
- edge traces;
- **Fit to my markers**, which tunes the generator port;
- camera refinement from user-placed landmarks;
- parameter copy and paste, "remove my markers / remove all", and localStorage persistence.

The math and thresholds are in `photo-matching-and-markers.md`. Setup is in
`assets/README.md`.

## 4. Hand-off between tools and back to the build

- Every tool exports what the next imports: preview parameters → board → fitted parameters
  → preview (Apply) → user → agent build. Exports are **resolved** (rules applied), so the
  build never re-derives.
- The hand-off format is plain JSON (parameters) or a tagged compact code (shapes), pasted
  into chat. Keep codes under about 15 KB.
- localStorage (try/catch, empty-safe) keeps edits across reloads. It's per-viewer only.
- A clipboard copy needs a select-and-Ctrl+C fallback.

## 5. Testing the tools headlessly

The tools are part of the deliverable, so test them like it:
- `node --check` every inline script extracted from the built page.
- Unit-test the pure JS (generator, solver, camera math) in Node against the Python outputs.
- Playwright + Chromium with `--use-gl=swiftshader --enable-webgl --ignore-gpu-blocklist`
  renders WebGL headlessly. Script the user's flow (switch mode, drag, add, obscure, fit,
  reload) and read state back through a debug hook on `window`. Screenshot every view you
  claim works, and look at it.
- For fitters, run a synthetic recovery test (`photo-matching-and-markers.md` §9).
- SwiftShader is 3–5× slower than a GPU; don't tune performance against it.

## 6. Pitfalls

- An edit applied to only one runtime. Run the parity test after every generator change.
- `const` / `let` temporal dead zone: handlers can fire before later declarations. Declare
  state above the functions that draw.
- Exporting raw sliders instead of resolved values after rules.
- Large inline images: downscale references (about 900 px, JPEG q72) and keep the pixel
  mapping back to original coordinates.
- Warnings the user has said don't matter. Remove them rather than asking the user to ignore
  them.
