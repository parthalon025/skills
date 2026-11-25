---
name: "fusion-builder"
description: Build and modify Fusion 360 models from reference images, photos, napkin sketches, engineering drawings, screenshots, or plain-language descriptions, by driving the Autodesk Fusion MCP (fusion_mcp_execute / fusion_mcp_read / fusion_mcp_update). Use this whenever the user wants geometry created or changed in Fusion — "model this part", "build this from the photo", "trace this drawing", "add a fillet/hole/rib/pocket", "make the wall thickness a parameter", "change the bore diameter", "measure/inspect my model", "fix this broken feature", "is this printable", "is this model actually parametric" — or uploads a picture of a part they want as a 3D model. Also for organic/procedural parts (straps, ribbons, hoses, reliefs), 3D photo matching (cameras, markers, fitting), and previews the user shapes. Trigger even when Fusion is not named explicitly, as long as the goal is parametric CAD geometry, and trigger before writing any Fusion API script by hand.
compatibility: Requires the Autodesk Fusion MCP connector with Fusion running and a document open. Scoped to the free personal-use entitlement.
---

# Fusion Builder

Turn an image or a description into a parametric Fusion model, one verified increment at a time.

Everything happens through three tools:

| Tool | Use |
|---|---|
| `fusion_mcp_read` | `licensing`, `activeCommand`, `document`, `screenshot`, `apiDocumentation` |
| `fusion_mcp_execute` `featureType:"script"` | all geometry creation and inspection (Python, inside Fusion) |
| `fusion_mcp_update` | `undo` / `redo` for recovery |

The model is not the only deliverable: maintain `build_<part>.py` as you go (see "The build script").

Plus two local scripts (run with bash/python, not inside Fusion) for the image path:

| Script | Use |
|---|---|
| `scripts/trace_image.py` | photo/drawing + a scale reference → fitted lines, arcs, circles in mm |
| `scripts/compare_silhouette.py` | Fusion screenshot vs reference image → IoU, deviation, bbox delta |
| `scripts/solve_camera.py` | reference image + landmarks with known model 3D positions → camera (PnP), reprojection error, marker overlay |
| `scripts/payload_chunker.py` | large arrays/meshes → ≤ 5.7 KB MD5-verified receiver scripts + loader (the MCP script limit is ~6.5 KB) |
| `scripts/ribbon_kit.py` | procedural strips: frames, exact oblique folds, profiles, thick shell, mirror, manifold clip, clash test |

Print-prep, assembly, surfacing and data-management work each have a domain reference — see the routing table below.

There is no direct "make extrude" tool. Every operation is a Python script. Read `references/api-recipes.md` before writing the first script of a session — the units and selection rules there are the two things that break models most often.

## Non-negotiables

1. **Sketches first, always.** Every solid feature is built from a named, dimensioned sketch. Never generate a solid from raw `BRepBody` construction or a temporary profile. If the user asks for a box, that is still a sketch + extrude. This is what makes the model editable afterwards, which is the entire reason to use Fusion instead of a mesh.

   **One sanctioned exception: hybrid design intent.** A rule-driven organic part the API can't sweep or sculpt (a strip that folds and overlaps itself, a hose with bend limits, a stacked relief) is owned by a **procedural generator** outside Fusion. The generator's parameter dict is the editable definition, and the part arrives as a mesh body inside a named base feature, plus a design-intent spine sketch (≤ 120 fit points). Everything rigid around it stays sketch-first and parametric. Declare the split at G1. `references/domains/procedural-organic.md`.
2. **Parameters before geometry.** Create user parameters for every dimension that has meaning (bore diameter, wall thickness, overall length). Drive sketch dimensions with parameter expressions, not literals. A model whose numbers can't be changed later is a failed deliverable.
3. **Finish the 2D before any 3D.** Every sketch that can be built on datum geometry — outline, bores, slots, ribs, profiles for later features — is created, dimensioned, constrained and visually checked *before* the first solid feature. Sketches are the part's definition; solids are a consequence. Building a solid off sketch one and then discovering sketch three needs a different datum means unwinding the timeline, and a half-defined sketch layer hides exactly the errors that are cheapest to fix in 2D.

   The narrow exception, which is declared up front and never discovered later: a sketch that genuinely requires resultant geometry — the interior face of a shell, a plane tangent to a revolve, a seed placed on a face a feature creates. Those are listed in the sketch plan as `DEFERRED (after <feature>)` with the dependency named, and each gets its own screenshot-and-check when it is finally created. If you find yourself wanting to defer a sketch that could have gone on a datum plane, that is a sign the datum scheme is wrong, not that the rule is.
4. **Sketch on datums, not on faces.** Attach sketches to origin planes and named construction planes. A sketch attached to a model face inherits every topological change upstream of it, which is the exact fragility the whole selection discipline in `api-recipes.md` §6 exists to work around. Offset a construction plane from the origin instead; it costs one feature and survives rebuilds.
5. **One named component per part.** Open a named component at the start of the build and model inside it (`comp.sketches`, `comp.features`). Root stays empty. This is free at feature zero and expensive to retrofit once the timeline has depth, and it is what makes the part reusable in an assembly or splittable for printing later. See `references/domains/assemblies.md`.
6. **Tag what you will need again.** The moment a feature creates a face or edge set you will select later — mount face, bore wall, the edges that get filleted — tag it with an attribute (`api-recipes.md` §6). Geometric heuristics like "highest-area +Z face" are correct when you write them and drift the first time the timeline rebuilds. Tags don't.
7. **Tracer bullet, inside each stage.** Within the sketch stage, build and check one sketch at a time. Within the solid stage, one feature or tight group per script, each verified. Never emit a 300-line script that builds the whole part in one shot; when it fails you learn nothing about where.
8. **Visual inspection is a test, and a test needs a threshold.** After every increment, take a screenshot and actually look at it against the reference image or the stated intent. Report what matches and what doesn't, then apply the accept/investigate/stop bands in "Acceptance criteria" below. A script returning "success" proves nothing about geometry, and a number reported with no criterion is telemetry, not a test.
9. **The build script is the deliverable, not just the document.** Every script that is accepted at a gate gets appended to a local `build_<part>.py`. The Fusion document is one corrupted timeline away from gone and cannot be diffed; the build script rebuilds the whole part into an empty document, is the regression test for every later change, and is the only record of *how* the part was made. Maintain it as you go — reconstructing it at the end from chat history does not work.
10. **Never save unless told.** `document{operation:"save"}` only on an explicit instruction from the user.
11. **Stop at every gate.** Each stage below ends with an approval gate, and the gate set is sized to the part (see "Approval gates"). Present the result, state what you intend to do next, and wait. Do not chain two gated stages in one turn, even when the next step seems obvious — the user is modelling with you, not receiving a finished part.
12. **Stay inside the free tier.** This skill targets Fusion for personal use. Check the live entitlement at G0 and never propose a workflow that needs a paid tier or an extension — see `references/personal-use-limits.md`. When a limit bites, name it, give the free-tier workaround, and stop; don't steer toward buying anything.
13. **Ask when uncertain, before building.** A guessed dimension becomes a wrong solid that then has to be unwound. See "Handling uncertainty" below.
14. **Never suppress a feature to remove its effect.** The API suppresses everything downstream that depends on it, silently, and a health check reading `healthState` sees nothing wrong — suppressed features aren't unhealthy, they're absent. That is how a whole set of bodies disappears from a design reporting zero errors. Delete the feature, change its operation, or edit the sketch that drives it. If anything is suppressed, count it and say so. `references/editing-and-variants.md` §2.
15. **A stage isn't verified until it survives `computeAll()` and a body inventory.** Feature health at creation reflects an incremental compute; stale references surface only on a full rebuild, and the worst failures (a body gone, a name landing on a fragment) never show as feature errors at all. Every stage ends with `design.computeAll()`, then the unhealthy list, the suppressed list, and bodies by name/volume/lump count against what you expect. §4-5 of the same file.

## Operating principles

Read `references/agent-operating-principles.md` once per session. It is the handoff on how to
run the engagement, as opposed to how to drive Fusion. The rules that matter most:

- **Done = accepted + works in the world + rebuilds from source + stays editable.** All four.
- **Resolve uncertainty in layers: topology → proportion → dimension → tolerance.** Metrics
  validate the last three only; topology needs a confirmed diagram.
- **Two corrections on the same feature: stop building it and change the channel.** Go from
  words to a drawn interpretation, then a user sketch, a second view, an interactive preview,
  and freeform or marker input. Don't make a third guess in the same channel.
- **Explore cheap, commit expensive.** Iterate in the sandbox or preview; push only accepted
  states to Fusion, gated.
- **One source of truth, flowing one way**, with parity tests between any two
  implementations of the same math.
- **Glossary and decision log in the user's words**, with corrections quoted verbatim.
  Reconcile conflicting corrections out loud.
- **Every claim carries evidence** in the same message. Rule out the measurement (camera,
  perspective, stale screenshot) before blaming the model.
- **Manufacturing constraints are captured at G1**, not at export.
- **`session_state.md` is updated at every gate**, so any session or agent can resume from
  it. Add every new surprise to the references before the session ends.

## Approval gates

| Gate | Ends with | Waits for |
|---|---|---|
| G0 Preflight | state of the document, blockers | go-ahead if anything is off (dialog open, direct design, wrong doc, existing geometry that will be affected) |
| G1 Spec | the build spec + assumptions + open questions | "yes" / corrections to the spec |
| G2 Parameters | parameter table as created | confirmation the values are right |
| G3 Sketches complete | every sketch built, constrained, one screenshot of the whole 2D set | confirmation the 2D definition is right — nothing 3D happens before this |
| G4 Tracer bullet | first solid, screenshots, delta report | confirmation before adding detail features |
| G5 Each detail feature | screenshot + delta report per feature or tight group | confirmation before the next |
| G6 Verify | measurements, timeline health, parameter sweep, final views | acceptance, or a punch list |
| G7 Save / export | nothing written until asked | explicit instruction |

**G1, G4 and G7 are never skipped.** G1 is where the numbers everything inherits get agreed, G4 is the cheapest catch in the sequence (detail features on a wrong base is the expensive failure), G7 is the user's file.

**Size the gate set to the part.** Eight gates on a four-feature bracket trains the user to say "just build it" on turn one, which costs more than it saves.

| Part | Gates |
|---|---|
| Simple: dimensions supplied by the user, no image reference, ≤ 3 features | G1, G4, G6, G7 |
| Normal | all eight, G0+G2 cleared in one turn when the document is empty and nothing is ambiguous |
| Complex: image-derived, > 8 features, assembly, surfacing, or an edit to someone else's model | all eight, and G5 per feature rather than per group |

Say which set you're using and why, at G1. When in doubt use the full set; the user can compress it, and they will.

If the user says "just build it" or "stop asking": drop G2, G3 and G5, keep G1, G4, G6 and G7, and tell them which ones you dropped so they can put one back. Do not drop G4 — a wrong base found at the end costs the whole build.

## Handling uncertainty

Uncertainty gets **asked about**, never papered over. Three kinds, three treatments:

- **Blocking and unknowable** — a dimension with no scale reference, a hidden internal feature, which of two readings of a drawing is intended. Ask. Do not build a placeholder.
- **Inferable with risk** — a wall thickness that is probably 2 mm, a fillet that looks like R1. State the assumption in the spec with its basis, build on it, and flag it in the delta report. The user corrects a stated assumption cheaply; they cannot correct one you never mentioned.
- **Cosmetic / reversible** — text position of a dimension, which of two equivalent constraint schemes. Decide and move on.

Batch questions into one round at the gate rather than dribbling them out one per turn. Number them, propose a default for each so a one-word answer works:

```
Before I sketch:
1. Overall length — photo has no scale. 48 mm? (assumed from the 1/4" hole)
2. Is the back face flat, or dished like the brass original? (assuming flat)
3. Bore through-all, or blind at 6 mm deep? (assuming through-all)
```

When an image is ambiguous, say what you see and what you can't see rather than asking an open question: "I can't tell from this angle whether the rib runs the full length — can you shoot it from the side, or tell me?"

## Workflow

### 1. Preflight

Two calls. First `fusion_mcp_read{queryType:"licensing"}` — `summary.isHobbyist` tells you which capability set is real, and `activeExtensions` tells you what else is on. Gate everything downstream on that answer rather than on the published table, which moves.

Then one read-only script to learn the state you're walking into:

```json
{"featureType":"script","object":{"readOnly":true,"script":"<preflight, see api-recipes.md>"}}
```

Capture: document name, design type (parametric vs direct), default length unit, root component name, existing bodies/sketches, existing user parameters, timeline count and health.

If `fusion_mcp_read{queryType:"activeCommand"}` shows a dialog open, modifying scripts will fail — say so and ask the user to close it. Read-only scripts still work.

If the design type is DirectDesignType, warn the user: no timeline, no parametric history. Offer to continue anyway or switch.

If the document already contains bodies, say what is there and confirm whether you are adding to it, editing it, or should be in a new document. On personal use, creating a new document counts against the 10-document cap — check where they stand before proposing one (`references/domains/data-management.md`).

**G0** — report the state in three or four lines. Proceed straight to intake only if nothing is off; otherwise stop and ask.

### 2. Intake → build spec

If the user supplied images, read `references/image-to-spec.md` (how to read the image) and `references/image-to-sketch-math.md` (how to measure it).

For anything dimensional, **measure, don't eyeball**: run `scripts/trace_image.py` with a scale reference to recover fitted primitives in mm, then look at `overlay.png` before trusting a single number it printed. The default is to use those numbers to hand-build a parametric sketch — a traced sketch is unconstrained and uneditable, which defeats the purpose. Trace to geometry only for organic profiles.

If there is no scale reference in the image, that is a blocking unknown: ask for one dimension. Do not pick a size.

**Topology before geometry.** A 2D reference does not fix 3D topology: which way a curl rolls, whether a fold goes over or under, whether a dip is a U or a Z. Before modeling anything whose 3D form the image leaves open, show your reading as a numbered, colored trace on the reference plus a side-profile plot, and get it confirmed. Guessing costs one full build per wrong guess. `references/image-to-spec.md` §9.

**Two or more views, or a shape the user wants to steer visually:** solve each reference's camera and measure in 3D with markers (`references/photo-matching-and-markers.md`). Consider an interactive preview the user drives (`references/co-design-tools.md`). Grade reference trust up front: a straight-on render owns plan, a real oblique photo owns heights, an AI render is low-trust for both.

**Snap measurements to nominals before they become parameters.** A trace that returns 6.37 mm is a 6.35 mm (1/4") bore that was measured through a pixel grid. Reconcile every measured value against stock, drill, fastener and bearing series, and carry both numbers into the spec with the delta. Measurement noise driven straight into parameters produces a part that looks right and won't mate with real hardware. Tables and clearance classes: `references/fits-and-nominals.md`.

Produce a **build spec** and show it before touching the model:

```
UNITS: mm
COMPONENT: Comp_clip           (root stays empty)
DATUM: origin at <feature>, X = <direction>, part symmetric about <plane>
DRIVING PARAMETERS          (independent; the sweep range is the declared valid range)
  name         value    min    max   basis
  bore_dia     6.35 mm  6.2    6.6   measured 6.37, snapped to 1/4"
  wall         2.0 mm   1.6    4.0   assumed, printable minimum
  body_len     48 mm    40     60    from caliper photo
DERIVED PARAMETERS          (expressions only — a repeated literal is a defect)
  boss_od      bore_dia + 2*wall
  edge_r       min(1.5 mm; wall/2 - 0.1 mm)      guard: can't exceed the wall
  bore_print   bore_dia + print_clear
SKETCH PLAN
  SK_profile   (XY datum)   outer silhouette, closed, fully constrained
  SK_bore      (XY datum)   bore circle, concentric to nose arc
  SK_rib       DEFERRED (after SH_cavity — sits on the shelled interior face)
FEATURE PLAN
  1 EX_body    extrude SK_profile, symmetric, body_len
  2 CU_bore    cut SK_bore through all
  3 FI_edges   fillet, edge_r        tag: edge set "outer_fillet"
ACCEPTANCE
  bbox 48.0 x 20.0 x 6.0 mm ±1%,  volume ≈ 3.1 cm³,  IoU ≥ 0.98 vs photo
UNKNOWNS
  - overall length: no scale reference in photo — need one measurement
```

Three things in that spec are load-bearing and get skipped if you don't force them: the **min/max on each driving parameter** (that range is what G6 sweeps, so a parameter with no range is a parameter nobody proved), the **guard expressions** on derived values (`min()` / `max()` keep a later edit from driving a fillet through its own wall), and the **ACCEPTANCE line** (the numbers G4 and G6 are judged against, written down before the geometry exists so they can't be rationalised afterwards).

Ask only about unknowns that change geometry and cannot be inferred. State assumptions explicitly rather than asking about everything; the user can correct a stated assumption in one word. **G1** — post the spec, the assumptions with their basis, and the numbered questions. Wait. This gate is never skipped: everything downstream inherits these numbers.

### 3. Parameters, then the component

One script that creates every user parameter from the spec and opens the named component. Use `ValueInput.createByString("25 mm")` so units are explicit. Print the resulting parameter table so the values are verified, not assumed.

- **Driving parameters carry literals. Derived parameters carry expressions, never a repeated number.** If `boss_od` is typed as `10.35 mm` instead of `bore_dia + 2*wall`, the model is a dumb solid wearing parameter names and the G6 sweep will prove it.
- **Guard the expressions that can fail geometry.** Fusion expressions support `min()` and `max()`: `edge_r = min(1.5 mm; wall/2 - 0.1 mm)`, `rib_t = max(rib_nom; 2 * nozzle)`. The fillet-larger-than-its-wall and shell-thicker-than-its-radius failures in `troubleshooting.md` are the two most common in the whole workflow, and a guard expression prevents both permanently instead of catching them once.
- If a parameter already exists, update its expression rather than creating a duplicate name.
- Then `root.occurrences.addNewComponent(...)`, name it, and model everything downstream into that component (`api-recipes.md` §3).

**G2** — show the parameter table as Fusion resolved it (expression and evaluated value, so a unit mistake is visible), and the component name. Confirm before sketching.

### 4. Sketches — all of them

List every sketch the part needs before writing any of them, then build them one script at a time. The stage ends when the 2D definition is complete, not when the first profile is extrudable. Sketches marked `DEFERRED` in the spec are the only ones allowed to be missing at G3, and each must name the feature it waits on. For each sketch:

- Attach it to an origin plane or a named construction plane, not a model face (non-negotiable 4). `comp.sketches.add(comp.xYConstructionPlane)`.
- Name it (`SK_profile`, not `Sketch1`).
- Build geometry with `sketchCurves`, then apply geometric constraints, then dimensions.
- Drive each dimension with a parameter: `dim.parameter.expression = "bore_dia/2"`.
- **The API adds no automatic constraints.** `addTwoPointRectangle` in the UI comes with horizontal, vertical and coincident constraints; through the API it is four bare lines that will skew into a parallelogram. Add them yourself.
- Anchor to the origin by projecting the construction axes and constraining symmetry to them — see the centering idiom in `api-recipes.md` §4.
- Add constraints **one at a time and check `isFullyConstrained` after each**, stopping the moment it flips True. The next constraint after that throws `VCS_SKETCH_OVER_CONSTRAINTS` and, because scripts are transactional, takes the whole script down with it.
- Print `sketch.profiles.count` and, when it matters, the area/bounding box of each profile. Zero profiles means the loop isn't closed — fix it before extruding.

Then screenshot (`direction` matching the sketch plane) and look at it. A sketch that looks wrong will not extrude into something right.

**G3** — when every sketch is done, show one screenshot of the complete 2D set plus a per-sketch line: profiles, constraint count, `isFullyConstrained`, and the plane it sits on. Any sketch still unconstrained gets named, with what is free and whether it matters. List the deferred sketches and what they're waiting on. Wait. This is the last cheap moment in the build.

### 5. Solid, incrementally

Only after G3. One feature or one small group per script. After each:

- Print the feature name, resulting body count, and body volume. Volume is a strong check: a cut or fillet whose volume delta matches the hand calculation is almost certainly right.
- Tag the faces and edge sets this feature created that any later feature will select (non-negotiable 6). Do it in the same script; there is no second chance that doesn't involve guessing.
- Screenshot `iso-top-right` plus whichever ortho view shows the feature you just made.
- When the reference is an image, run `scripts/compare_silhouette.py` on the screenshot and report IoU, aspect delta and the Hausdorff worst-case. "Looks right" is not a measurement.
- Compare against the reference image or spec, out loud, in specifics: "bore is centered on the nose arc, matches; the taper is shorter than the photo — the photo's taper runs about 60% of the length, mine runs 40%."
- Then apply the acceptance criteria below and state the verdict. Not the numbers alone: the verdict.

#### Acceptance criteria

Every increment resolves to accept, investigate or stop. Compare against the ACCEPTANCE line written into the spec at G1, not against what the geometry happens to be.

| Measure | Accept | Investigate | Stop |
|---|---|---|---|
| IoU vs reference silhouette | ≥ 0.98 | 0.95–0.98 | < 0.95 |
| Bounding box vs expected | ≤ 1% on every axis | 1–3% | > 3% |
| Volume vs hand calculation | ≤ 2% | 2–10% | > 10% |
| Timeline health | 0 unhealthy | any warning | any error |
| Sweep across declared parameter range | 0 unhealthy at every step | — | any step unhealthy |

**Investigate** means name the region that disagrees and say what you think causes it, in the same turn. **Stop** means do not add the next feature; re-spec with the user. A silhouette at IoU 0.93 with three more features stacked on it is three features that all have to come out.

For 3D comparisons against photos (camera solve residuals, marker-fit RMS, triangulation gap), use the bands in `photo-matching-and-markers.md` §10. Register against plan references with an **orthographic** view: a perspective "top" of tall relief reads about 8% oversized and looks like a modeling error.

Hausdorff worst-case is a locator, not a gate: a high IoU with a large Hausdorff means one small region is badly wrong, which is exactly the thing the eye misses in an iso view.

**G4** — the first solid is the tracer bullet. Stop there. Detail features are worthless on a wrong base, and unwinding them costs more than the pause.

**G5** — one gate per detail feature, or per tight group (all fillets on one edge set, say). Each ends with the screenshot and the delta report, then waits.

### 6. Verify

When the build is complete, run one read-only verification script and report:

- timeline health (any errored/warning features)
- bounding box vs. expected overall dimensions
- volume and, if a material is set, mass
- body count (should usually be 1 for a printed part), and that the geometry is inside the named component with root empty
- a body inventory: every expected body present by name, its volume, `lumps.count` and `isSolid`, plus any stray auto-named (`Body12`) or leftover temporary bodies. A stray body or a missing name is a failed build even when every feature reads healthy
- parameter table, flagging any derived parameter whose expression is a bare literal
- robustness audit: how many sketches are attached to model faces rather than datum planes, and which features select geometry by index rather than by tag or geometry. Both are latent failures, not current ones; name them so the user knows what will break on the next edit.

**Then sweep the parameters.** Driving one parameter to one other value proves almost nothing. Run the sweep script (`api-recipes.md` §10): for each driving parameter, set it to its declared `min`, recompute, record timeline health and the key measurements; repeat at `max`; restore the nominal. Report a table of parameter, bound, health, and what moved.

This is the check that earns the word parametric. It catches the two failures that otherwise surface in the user's hands a week later: a fillet or shell that computes at nominal and dies at the wall's lower bound, and a feature that doesn't track its datum at all (bore stays put while the plate grows). A parameter with no declared range is a parameter nobody proved, which is why the range is captured at G1.

The sweep is one script and it modifies the design, so it is not `readOnly`. Because scripts are transactional, a sweep that throws leaves nothing behind. A sweep that completes must restore every nominal itself — verify by printing the parameter table again at the end.

Then a final screenshot set: `iso-top-right`, `front`, `top`, and a final append to `build_<part>.py`.

**G6** — present measurements against the spec's ACCEPTANCE line, the sweep table, and the verdict per the acceptance criteria. Ask for acceptance or a punch list.

**G7** — no save, no export, no overwrite of the user's file without an explicit instruction naming it.

### 7. Recover

**Scripts are transactional.** An exception discards everything that script did, including the operations that already printed success. So a failed script usually leaves nothing to clean up — and `undo` after one will eat the *previous* good feature instead. That is how a build loses its plate and its parameters in two clicks.

When a script throws:

1. Read the actual exception text — never swallow it with try/except.
2. **Inspect before undoing.** Run a read-only state check (timeline count, bodies, sketches). Undo only if that check shows real partial geometry, which is rare.
3. If the error is an API misuse, look it up: `fusion_mcp_read{queryType:"apiDocumentation", searchPattern:"...", filter:"adsk.fusion.<Class>"}`. Do this instead of guessing a second time — the second guess is usually wrong in the same way.
4. `references/troubleshooting.md` covers the recurring failure modes.

Never leave the timeline in a broken state at the end of a turn. Either fix it or undo it and say so.

When a timeline is tangled past cheap repair — two stacked edits that moved body identity, a
cascade of suppressions — reverting is the fast path: `dataFile.promote()` makes a copy of an
earlier version the latest one without deleting anything in between. Before promoting or
opening another version, export any unsaved design as a `.f3d` archive; opening the latest
version of a lineage can leave a modified older-version tab closed, and unsaved work does not
survive that. `references/editing-and-variants.md` §11.

## The build script

Maintain `build_<part>.py` in the working directory alongside the session. After every gate the user accepts, append the script that cleared it.

```python
# build_clip.py — regenerates Comp_clip from an empty parametric document.
# Accepted increments only. Each block is the script that cleared its gate.
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    # --- G2 parameters + component -------------------------------------
    ...
    # --- G3 SK_profile --------------------------------------------------
    ...
    # --- G4 EX_body -----------------------------------------------------
    ...
```

Rules:

- Append at the gate, not at the end of the session. A build script reconstructed from chat history is a guess.
- Only accepted increments go in. A script that was rejected and reworked contributes its final form or nothing.
- Keep the gate labels as comments. They are the map from the timeline back to the conversation.
- It must run start-to-finish in an **empty** document. That is the test: run it, then run the verify script, and the measurements must match the accepted ones.

**Generated parts:** the build script also records the generator version (or hash) and the exact resolved parameter JSON, and the mesh transfer goes through the payload loader. Rebuilding a hybrid part means rerunning the generator from that JSON, then sending the chunks. The JSON is the source, not the mesh.

What this buys, in order of how often it matters: a corrupted or lost document costs a rerun instead of a session; a change request months later starts from source instead of archaeology; a parameter change that breaks something can be bisected; and the part becomes diffable, which nothing else here makes it.

Offer the rerun explicitly when the timeline gets into a state that is cheaper to rebuild than to repair. Three dead features and a rolled-back marker is usually that state.

## Domain routing

The core workflow above covers parametric solid modeling. When the task reaches past that,
read the matching file — one file, when the request touches it, not upfront:

| Request touches | Read |
|---|---|
| multiple parts, joints, motion, "assembly", "does it fit together" | `references/domains/assemblies.md` |
| organic shapes, sculpting, "Form", lofted/patched/stitched surfaces, fairings | `references/domains/surface-form.md` |
| 3D printing, "will this print", supports, orientation, STL/3MF, slicer, Manufacture | `references/domains/additive.md` |
| projects, versions, "which version", saving, archiving, the 10-document cap, sharing | `references/domains/data-management.md` |
| mating parts, clearances, fits, "will this fit the bearing/bolt", snapping a measurement to a standard size | `references/fits-and-nominals.md` |
| whether something is available at all on the free tier | `references/personal-use-limits.md` |
| editing an existing timeline, variants/families, engraved text, reverting a version | `references/editing-and-variants.md` |
| folding/curling strips, straps, ribbons, hoses, springs, lattices, layered reliefs — anything rule-driven the API can't sweep | `references/domains/procedural-organic.md` |
| sending big data into Fusion: point clouds, meshes, > 100-point splines, anything > 6 KB | `references/large-payloads-and-meshes.md` |
| matching photos in 3D: solving a reference camera, markers, two-view triangulation, fitting parameters to references, AI-generated references | `references/photo-matching-and-markers.md` |
| letting the user shape it: live preview, sliders, cloth/freeform mode, a marker board, headless testing of those tools | `references/co-design-tools.md` |
| repeated corrections, stalled iterations, long or multi-session builds, handing a build to another agent | `references/agent-operating-principles.md` |

Outside those areas plus the core — simulation, generative design, multi-axis CAM,
drawings beyond a single sheet — say plainly that it's out of scope or outside the free
entitlement, then offer what the free tier *can* do toward the same goal. A hand calculation
and a test print beat a simulation the user can't run.

## Editing an existing model

Read `references/editing-and-variants.md` before the first edit. Editing a timeline that
already exists has its own failure set — suppression cascades, extent edits that silently clear
`participantBodies` and scramble which body owns which name, text cuts that fail only on the
next rebuild, shared parameters with a second consumer you didn't know about. The short version
is one rule: **append features rather than editing the ones other features consume**, and
verify with a body inventory rather than a success message.

The same rules apply, plus:

- Inspect before changing. Dump the timeline, sketches, parameters, and named features first.
- Prefer changing a **parameter** over adding geometry. If the user wants a thicker wall and `wall` exists, set its expression — one line, no new features.
- If the model has no parameters and the user wants a dimensional change, offer to parameterize the driving dimensions as part of the edit.
- Reference faces and edges by geometry (normal, centroid, area, distance) or by attribute tag, never by raw index. Indices shift when the timeline rebuilds. See the selection section of `references/api-recipes.md`.
- Building a family of variants (sizes, materials, ratings) from one master: copy the master body at the right timeline position, drive each copy from its own parameter, add variant geometry as new features, lay the copies out *before* engraving or splitting them, and assign materials last. Coincident bodies at the origin break participant selection. `references/editing-and-variants.md` §8.
- Measure the result with `pointContainment` bisection rather than trusting the parameter you typed — it reads any surface to 0.001 mm with no dependence on face indices, and it is what catches a systematic offset between your model reference and the real geometry. §9.
- An existing model has no build script and you can't write one retroactively. Start one at the first change you make, with a comment saying where it picks up, and run the G6 sweep before handing back — an edit to a model you didn't build is exactly where an untested parameter range bites.

## Print prep (when the target is a 3D print)

Read `references/domains/additive.md`. Short version: ask nozzle, material and build
orientation before analyzing anything; run the overhang and wall checks as a read-only script;
express print clearance as a parameter (`bore_dia = bore_nominal + print_clear`) so one test
print tunes the whole model. Export is a G7 action.

## Script contract

Every script you send:

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    # ... work ...
    print("EX_body ok | bodies=%d volume=%.2f cm^3" % (root.bRepBodies.count, body.volume))
```

- Entry point is exactly `def run(_context: str)`.
- No try/except around the work. A raised exception is the diagnostic; catching it destroys the only signal you get.
- `readOnly: true` for anything that inspects and changes nothing — it's the only kind of script that runs while a dialog is open, and it's enforced, so don't claim it falsely.
- Always `print()` a compact result line. Silent success is indistinguishable from doing nothing.
- Keep each script under **~6 KB**. Larger payloads go through `scripts/payload_chunker.py` (≤ 5.7 KB parts, MD5 per part, generated receivers). Never retype a data block from an earlier message. `references/large-payloads-and-meshes.md`.

## References

- `references/api-recipes.md` — units, parameters, components, sketches + constraints, features, stable selection, export, preflight/verify/sweep script bodies, build-script template. Read before the first script.
- `references/fits-and-nominals.md` — snapping measurements to standard sizes, clearance classes for mating parts, printed-hole allowances.
- `references/image-to-spec.md` — reading photos, caliper shots, drawings, Fusion screenshots; what each can and cannot tell you.
- `references/image-to-sketch-math.md` — the measurement pipeline: scale calibration, perspective rectification, segmentation, line/arc fitting, symmetry detection, verification metrics, and how to use the two scripts.
- `references/editing-and-variants.md` — editing an existing timeline safely: suppression cascades, participant/body identity, variant families, text engraving that survives a rebuild, measuring with `pointContainment`, staged libraries, version recovery.
- `references/troubleshooting.md` — errors, causes, fixes.
- `references/personal-use-limits.md` — what the free entitlement includes, what it doesn't, and the workarounds.
- `references/domains/` — assemblies, surface-form, additive, data-management, procedural-organic. Read on demand per the routing table above.
- `references/large-payloads-and-meshes.md` — the script size limit, chunked transfer with MD5, quantization, the fitted-spline point ceiling, mesh bodies in base features, replacing and clipping meshes.
- `references/photo-matching-and-markers.md` — reference trust levels, the perspective trap, PnP camera solving, rendering from a solved camera, markers, triangulation, edge traces, fitting and its validation, 3D acceptance bands.
- `references/co-design-tools.md` — interactive preview (parity-tested generator port), freeform mode, marker board, hand-off codes, headless Playwright/SwiftShader testing.
- `references/agent-operating-principles.md` — the principal-level handoff: definition of done, route choice, uncertainty layers, the loop breaker, source-of-truth flow, decision log, evidence, proxy metrics, reference hygiene, continuity, measuring the agent.
- `evals/evals.json` — starter eval set spanning the skill; add a case for every new failure mode.
- `assets/` — `cloth.js`, `marker_board_template.html`, `example_generator_port.js` (see `assets/README.md`).
