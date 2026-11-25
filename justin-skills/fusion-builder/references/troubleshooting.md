# Troubleshooting

## Scripts are transactional — read this before reaching for undo

A script that raises discards **everything it did**, including operations that already
printed success. Confirmed live: a script that added two constraints and then threw left the
sketch with its original two.

Consequences:

- A failed script usually leaves nothing to clean up. Inspect with a read-only state check
  before doing anything else.
- `fusion_mcp_update{featureType:"undo"}` after a failed script undoes the **previous**
  successful feature instead. Two reflexive undos can take a build back to an empty document,
  parameters included.
- Batching related operations in one script is therefore safer than splitting them: partial
  states don't survive. Batch what belongs together; still keep one feature-group per script
  so you know where a failure happened.

## Script won't run at all

| Symptom | Cause | Fix |
|---|---|---|
| "cannot run while a command dialog is open" | user is mid-Sketch/Extrude in the UI | ask them to close it; use `readOnly: true` to inspect meanwhile |
| "Cannot modify the design from a read-only context" | `readOnly: true` on a script that creates something | drop the flag; it's enforced, not advisory |
| `RuntimeError: 2 : InternalValidationError` | almost always a null object you didn't check — wrong plane, empty profile, missing body | print the object before using it |
| no output at all | script never printed | always print a result line |
| `Failed to match against any enum values` on featureType | `readOnly` is a field inside `object`, not a featureType | `{"featureType":"script","object":{"readOnly":true,...}}` |
| `AttributeError` on an API member | member renamed or namespaced differently | `fusion_mcp_read{queryType:"apiDocumentation", filter:"adsk.fusion.<Class>"}` — look, don't guess twice |

## Wrong geometry

| Symptom | Cause | Fix |
|---|---|---|
| part is 10× too big | `createByReal` with a mm number — internal units are cm | `createByString("25 mm")` |
| angles absurd | radians internally | `createByString("30 deg")` |
| `profiles.count == 0` | sketch loop isn't closed | print curve endpoints; add the missing coincident constraint |
| extrude grabbed the wrong region | profile picked by index | pick by area or centroid: `max(sk.profiles, key=lambda p: p.areaProperties().area)` |
| feature lands on the wrong face after an edit | face picked by index | select by normal/area/attribute (`api-recipes.md` §6) |
| sketch drifts when a parameter changes | sketch not anchored to the origin | project the construction axes and add symmetry (`api-recipes.md` §4) |
| rectangle skews into a parallelogram | API adds no auto h/v constraints | add one horizontal and one vertical yourself |
| `VCS_SKETCH_OVER_CONSTRAINTS` on a valid dimension | `isComputeDeferred = True` while dimensioning | turn deferral off before adding dimensions |
| `VCS_SKETCH_SOLVING_FAILED` on the last symmetry of a set | constraints form a loop | n features need n−1 symmetry constraints, chained |
| holes don't move when the plate resizes | positions placed numerically, not dimensioned to a datum | dimension centers to the origin with parameter expressions |
| mirror produced two bodies | operation was NewBody | join, or mirror the feature rather than the body |
| feature computes at nominal, errors when a parameter moves | no guard on the dependent value | `edge_r = min(edge_r_nom; wall/2 - 0.1 mm)` — `api-recipes.md` §3 |
| sweep shows bbox unchanged when a length parameter moves | that dimension drives nothing | find the sketch dimension still holding a literal and bind it to the parameter |
| `min()` / `max()` expression rejected | argument separator is `;` in Fusion, not `,` | `min(1.5 mm; wall/2)` |
| geometry ended up in root instead of the component | used `root.sketches` / `root.features` | build through `comp.*` — `api-recipes.md` §3 |
| downstream sketch moved after an upstream edit | sketch attached to a model face | reattach to an offset construction plane |
| bodies vanished but every feature reads healthy | a feature was suppressed; Fusion suppressed its dependents too | never suppress to disable — delete, or switch the operation; count suppressed features in every check (`editing-and-variants.md` §2) |
| body name ended up on a tiny fragment; stray `Body36` appeared | an extent edit on a join/cut cleared `participantBodies`, so it made new bodies and a later combine re-targeted the wrong one | re-set `participantBodies` in the same rolled state, or append a new feature instead of editing; verify with a body inventory (§3-4) |
| text cut healthy when created, "Cannot complete extrusion — 1 Reference Failures" after a rebuild | `SketchText` profile reference doesn't survive `computeAll()` for the most recent text cut | `txt.explode()` to curves, cut the letter profiles, drop the counters (§6) |
| engraved letters have their holes filled (P, A, 0 solid) | exploded text cut all profiles, including counters | keep only profiles whose outer loop isn't another profile's inner loop (§6) |
| identical labels on several copies fail on recompute | bodies still coincident at the origin — participant resolution is ambiguous | lay the copies out first, engrave second (§8) |
| a feature grew through a wall after a parameter change | the parameter had a second consumer | list consumers before changing; split into per-feature parameters; re-probe the wall (§7) |
| engraving looks shallow or a glyph is missing on a curved wall | flat label plane deviates from the surface across the text span | probe surface-to-plane distance across the span; shorten the text or move it to the flat region (§6) |

## Recompute is where references break

`healthState` right after a script reflects an incremental compute. Run
`design.computeAll()` then `timeline.moveToEnd()` and re-read health before reporting a stage
done — text cuts, participant references and stale face selections fail there and nowhere
earlier. Pair it with a body inventory (names, volumes, lumps); the failures that matter most
are invisible to feature health.

## Timeline problems

- **Red/errored feature after an edit**: a parameter change made a fillet larger than its edge or a cut miss the body. Read the failing feature's `errorOrWarningMessage` in the verify script — it names the cause. Usually the fix is a parameter bound (`edge_r < wall/2`), not a geometry change.
- **Warning, not error**: geometry computed but something degenerated. Don't ignore it; it becomes an error on the next edit.
- **Timeline rolled back**: features after the marker aren't computed. `design.timeline.moveToEnd()` before inspecting body counts, or the report is wrong.

## Fillets and shells failing

The most common failure in the whole workflow. Fillet radius must be smaller than the
adjacent face's narrowest dimension; shell thickness smaller than the smallest local radius.
When a fillet fails:

1. Try a smaller radius to confirm it's a size problem rather than a bad edge selection.
2. Fillet **before** the shell, not after, when both are needed.
3. Split a multi-edge fillet into separate features; one bad edge fails the whole set.

## Recovery discipline

**Inspect first. Undo second, and only if the inspection found something.** The order matters
more than either step: because scripts are transactional (top of this file), the usual state
after a failure is that nothing was committed, and an undo there eats the *previous* good
feature instead.

1. Run a read-only state check: timeline count, bodies, sketches, unhealthy features.
2. If it shows no partial geometry — the common case — fix the script and resend. Do not undo.
3. If it shows real partial geometry, `fusion_mcp_update{featureType:"undo"}`, then re-inspect
   to confirm what came off before retrying. Retrying on top of half-built geometry is how a
   timeline ends up with six dead features named EX_body2 through EX_body7.

Check `canUndo` in the response — "Nothing to undo" means the failure happened before
anything was committed, which is the good case.

When the timeline is in a state that costs more to repair than to rebuild — three dead features
and a rolled-back marker is usually that point — offer the rerun instead: empty document,
`build_<part>.py`, verify. That is what the build script is for.

## Image-pipeline problems

| Symptom | Cause | Fix |
|---|---|---|
| `no contour found` | part not separable from background | `--invert`, crop, or reshoot on a plain sheet |
| outline cuts corners | glare or shadow eating the edge | diffuse lighting; check `overlay.png` |
| dozens of tiny arcs | tolerance too tight for the image quality | raise `--tol-mm` |
| a real feature vanished | tolerance too loose | lower `--tol-mm`, or model that feature from a stated dimension instead |
| everything the right shape but the wrong size | calibration length misread | recheck `--cal-px` against the actual pixel span |
| shape subtly skewed, opposite edges not parallel | perspective | rectify with `--rect-px/--rect-mm` or get a straight-on photo |
| IoU high but bbox delta large | comparing in shape-only mode | rerun with `--mm-per-px-model/--mm-per-px-ref` |

## Procedural parts, big payloads, meshes and camera matching

| Symptom | Cause | Fix |
|---|---|---|
| script "succeeds" but data is corrupt, or fails only when long | payload over ~6.5 KB, or a data block retyped by hand | `scripts/payload_chunker.py`: ≤ 5.7 KB parts, MD5 per part and total (`large-payloads-and-meshes.md`) |
| fitted 3D spline missing, no exception | more than ~120–130 fit points in one call | curvature-weighted subsample to ≤ 120; report maxdev (§4 there) |
| move / align in a nested component does nothing or moves the wrong thing | native entities used outside their occurrence | `body.createForAssemblyContext(occ)`, `axis.createForAssemblyContext(occ)`, not only for joints |
| rotation goes the wrong way | `ConstructionAxis` from `setByTwoPlanes` can point −Z | check `axis.geometry.direction.z`; negate the angle |
| `createConfiguredDesign` refused | Personal tier | integer switch parameter + `max(0; …)` flags (`personal-use-limits.md`) |
| two meshes after "replacing" one; old name kept | base-feature rename failed silently; `itemByName` returned None | list meshes and base features; delete the old mesh inside its base feature's edit; assert one remains |
| pink / inverted slivers on an imported mesh | vertices clamped to a plane in the receiver | clip with a manifold boolean in the sandbox; send watertight |
| a generated strip passes through itself only where a fold is skewed | rigid hairpin bent in a tilted plane is not developable | exact oblique-fold map (`domains/procedural-organic.md` §3) |
| flared strip edge folds back over a crest | frame twist in plan (RMF over climb + sideways shift) | lock the width level there (§2 there) |
| a generated path doubles back right after a longer upstream segment | fixed spline waypoint now behind the segment end | derive waypoints from the upstream end, keep them monotonic |
| model looks about 8% too big against a plan photo | perspective camera over tall geometry | orthographic, or 3° FOV from far away (`photo-matching-and-markers.md` §2) |
| browser preview and built part disagree | edit applied to only one of the Python and JS generators | parity test after every generator edit; require 0.0000 mm |
| clash test flags folds and seams that are fine | nearest-neighbour test in grid index space | unrolled-surface clash test (closer than T in 3D, farther than 3T across the ribbon) |
| camera solve error about 1% no matter what | reference is AI-generated, not a consistent projection | down-weight it (about 0.4); trust it for heights and topology, not plan |
