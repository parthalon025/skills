# Editing an existing timeline, and building variants

The core workflow builds a part forward from an empty document. This file covers the harder
case: a timeline that already exists and has to be *changed* — a wall thickness, a feature
angle, a family of variants cut from one master — and the failure modes that only appear
there. Every item below was paid for in a real session.

Read this when the task is "change the existing model", "make a set of sizes", "turn off that
feature", "engrave a label on each", or when you are about to edit a feature that other
features consume.

**Table of contents**

1. The two rules that prevent most of the damage
2. Suppression cascades
3. Editing extents and participants — body identity
4. Verifying an edit: the body inventory
5. `computeAll()` is part of the test, not a formality
6. Text engraving that survives a rebuild
7. Shared parameters have more consumers than you think
8. Variants from one master
9. Measuring the model instead of trusting parameters
10. Long builds: the staged library
11. Version recovery and archiving

---

## 1. The two rules that prevent most of the damage

**Add features; don't edit the ones other features depend on.** An edit to an existing
join/cut/extent reaches forward through everything downstream. A new feature appended at the
right timeline position achieves the same geometry and touches nothing.

**A script's own success report is not evidence.** Features report healthy at creation and
fail on the next full recompute; bodies vanish while every feature still reads "healthy". The
check that matters is: recompute, then count bodies by name, volume and lump count (§4, §5).

---

## 2. Suppression cascades

`timelineObject.isSuppressed = True` does not disable one feature. Fusion suppresses
everything downstream that depends on it, silently — copies, combines, labels, layout moves,
the lot. Setting `isSuppressed = False` on a dependent re-enables its upstream chain too, so
an "undo" of the suppression can quietly switch a feature you meant to keep off back on.

A health check that only looks at `healthState` will not see any of this: suppressed features
are not unhealthy, they are absent. That is how a 16-body set disappears from a design that
reports zero errors.

So: **never suppress a feature to remove its effect.** Instead

| Want | Do |
|---|---|
| a cut to stop cutting | change its operation to `NewBodyFeatureOperation`, then `removeFeatures.add(body)` |
| a feature's geometry gone | delete the feature (`entity.deleteMe()`), in reverse timeline order if several |
| a dimension not to apply | edit the driving sketch or parameter, not the feature |
| to test "what if this weren't here" | roll the marker back, inspect, roll to end — no state change |

If you do suppress, count suppressed features in every health check and treat a nonzero count
as a failure unless you put it there on purpose:

```python
supp = [tl.item(i).name for i in range(tl.count) if tl.item(i).isSuppressed]
bad  = [(i, tl.item(i).name) for i in range(tl.count)
        if not tl.item(i).isSuppressed and tl.item(i).healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState]
```

---

## 3. Editing extents and participants — body identity

Editing the extent of an existing **join** or **cut** extrude (`setOneSideExtent`,
`setTwoSidesExtent`) can clear its `participantBodies`. The feature then creates *new* bodies
instead of modifying the target. Downstream combines re-target whichever body now sits in that
slot, and the body *name* you rely on can end up on a 10 mm³ fragment while the real part
carries an auto name like `Body36`.

Symptoms, in the order you notice them: volumes that make no sense, stray `Body##` bodies, a
combine feature whose target is not the body you named, `Clip_v6` suddenly 21 mm³.

Rules:

- Editing a feature requires `feature.timelineObject.rollTo(True)` first; reading
  `participantBodies` does too. Roll to end in a `finally` block.
- After any extent edit, **re-set `participantBodies` in the same rolled state**, then verify
  the body inventory (§4).
- Prefer not to edit at all: append a new join/cut feature that makes the same change.
- A combine whose `targetBody` has drifted is repaired by assigning `targetBody` again while
  rolled back — but if two edits have already stacked, reverting to the last saved version
  (§11) is cheaper than untangling.

Scripts are transactional, so a script that raises leaves none of this behind. That is the
argument for doing an edit and its verification **in one script**: if the verification throws,
the edit is gone too.

---

## 4. Verifying an edit: the body inventory

After every edit to an existing timeline, print and compare:

```python
def inventory(root, expect_names):
    rows = [(b.name, round(b.volume * 1000, 1), b.lumps.count, b.isSolid) for b in root.bRepBodies]
    stray = [n for n, *_ in rows if n.startswith(('Body', 'tmp', 'Component'))]
    missing = [n for n in expect_names if root.bRepBodies.itemByName(n) is None]
    return rows, stray, missing
```

Fail the stage on: a missing expected body, a stray auto-named body, a body whose volume moved
by more than the edit should explain, `lumps.count > 1` on a part that must print as one
piece, or `isSolid == False`.

This is the check that catches what feature health misses.

---

## 5. `computeAll()` is part of the test, not a formality

Feature health immediately after creation reflects the incremental compute. A full
`design.computeAll()` (then `timeline.moveToEnd()`) re-evaluates references and is where
stale-reference failures surface. Run it at the end of every stage, before reporting.

Cheap pattern for a stage:

```python
d.computeAll(); d.timeline.moveToEnd()
# then: unhealthy list + suppressed list + body inventory
```

If a feature is healthy before `computeAll()` and unhealthy after, the reference is the
problem — not the geometry. §6 is the most common instance.

---

## 6. Text engraving that survives a rebuild

`SketchText` as an extrude profile is fragile: on a full recompute the most recent
text-profile cut in the timeline loses its reference ("Cannot complete extrusion — 1 Reference
Failures"), even though it cut correctly when created. Re-creating it just moves the failure to
whichever text cut is now last.

**Explode the text to curves before cutting.** The curves have no text reference to lose:

```python
ti = sk.sketchTexts.createInput3("'%s'" % text, adsk.core.ValueInput.createByReal(height_cm))
ti.setAsMultiLine(p_lo, p_hi, adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                  adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0)
ti.fontName = 'Arial'; ti.textStyle = adsk.fusion.TextStyles.TextStyleBold
txt = sk.sketchTexts.add(ti)
if plane_normal_faces_away:      # check before exploding
    txt.isHorizontalFlip = True
txt.explode()
```

`createInput2` is retired; `createInput3` takes a `ValueInput` height and a quoted string.

Exploded text profiles include the **counters** — the enclosed holes in P, A, 0, 9, b. Cutting
all profiles fills them in and the letters read wrong. Keep only profiles whose outer loop is
not an inner loop of another profile:

```python
def letter_profiles(sk):
    profs = [sk.profiles.item(i) for i in range(sk.profiles.count)]
    key = lambda loop: frozenset(round(c.sketchEntity.boundingBox.minPoint.x, 6) * 1e3
                                 + round(c.sketchEntity.boundingBox.minPoint.y, 6) for c in loop.profileCurves)
    inner = {key(lp) for p in profs for lp in p.profileLoops if not lp.isOuter}
    keep = adsk.core.ObjectCollection.create()
    for p in profs:
        if key([lp for lp in p.profileLoops if lp.isOuter][0]) not in inner:
            keep.add(p)
    return keep
```

Sanity-check the count: "PETG" is 4 regions, "TPU" 3, "0.9 lb W" 6. A count one higher than
expected usually means a counter slipped through; one lower means touching glyphs merged
(bold "LA" does this) — harmless.

Other engraving gotchas:

- **Engrave after layout, not before.** Cutting identical text into bodies that still sit
  coincident at the origin makes participant resolution ambiguous and the cut fails on
  recompute. Move the variants apart first, then engrave each on its own offset plane.
- **Curved walls:** a flat label plane tangent at one point loses depth along the wall. Probe
  the surface-to-plane distance across the label's span and keep the text where the deviation
  is a fraction of the cut depth; or split long text into shorter runs.
- **Glyphs at a face edge** may drop out of the cut entirely. Verify by probing the engraved
  band, not by trusting the removed volume.
- Verify a cut by **volume removed** and by a screenshot; a cut can "succeed" and remove 0.05 mm³.

---

## 7. Shared parameters have more consumers than you think

A parameter named for one feature is often consumed by another. Raising `bump_r` from 1.2 to
1.6 mm to make the interlock bump gentler also grew a detent bump that shared the parameter —
pushing it 0.13 mm through the outer wall, where it showed as a bulge that erased a chamfer.

Before changing any parameter, list its consumers — sketch dimensions, feature extents, other
expressions — and say which ones you intended:

```python
for s in root.sketches:
    for dm in s.sketchDimensions:
        if 'bump_r' in (dm.parameter.expression or ''):
            print(s.name, dm.parameter.name, dm.parameter.expression)
```

Then give each physical feature its own parameter (`side_bump_r`, `interlock_bump_r`) so the
next change can't reach sideways. After a size change, re-probe the affected wall (§9) rather
than assuming it still fits.

---

## 8. Variants from one master

To build a family (sizes, materials, ratings) from one master body:

1. Roll to the timeline position where the master is complete but before the variant-specific
   feature, then `copyToComponent(root)` and rename the copy. Roll to end in `finally`.
2. Give each variant its own user parameter (`il8_PETG_0` …) and drive its variant feature
   from that parameter.
3. Apply variant geometry (a different wall, a different bump) as **added** features on the
   copy, not as edits to the master.
4. Lay the variants out (move features) **before** engraving or splitting them.
5. Assign materials/appearances last.

A thickness variant is a sketch job, not an edit of the master parameter: build a strip
between two offsets of the same source curve and cut or join it on that copy only.

Overlapping bodies at the origin are the root of several failures here — coincident bodies
confuse participant selection and make screenshots unreadable. Move first.

---

## 9. Measuring the model instead of trusting parameters

Parameters describe intent; the solid is the fact. `pointContainment` plus a bisection gives
0.001 mm-level measurement of any surface, with no dependence on face indices:

```python
inside = lambda x, y, z: body.pointContainment(adsk.core.Point3D.create(x/10, y/10, z/10)) == 0

def surface_between(a, b, axis_pt):        # a inside, b outside, along one axis
    for _ in range(30):
        m = (a + b) / 2
        a, b = (m, b) if inside(*axis_pt(m)) else (a, m)
    return a
```

Use it to check the things a parameter can't promise: an actual interlock overlap, a wall
span, whether a bump protrudes through a face, the slope of a ramp (two probes and an
arctangent), the gap between two features.

This is how a 0.012 mm systematic offset between a model reference height and the real tooth
tip was found — every variant parameter was then corrected by that amount, which is the
difference between a design that hits its target force and one that misses by 1.5%.

---

## 10. Long builds: the staged library

For a build that spans many MCP calls, don't paste the same helper code into every script.
Write a library file once to a known path (via the file tools, or from inside a Fusion script)
and `exec` it in each stage:

```python
LIB = os.path.join(os.path.expanduser('~'), 'Documents', '<part>', '<part>_lib.py')

def run(_context: str):
    g = {'__name__': 'lib'}
    exec(open(LIB, encoding='utf-8').read(), g)
    d = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    g['check'](d, 'stage 3')
```

Keep the stage functions (`check`, `engrave`, `move_body`, `material`) in the library and the
per-stage orchestration in the script you send. Patch the library from a script when a lesson
lands mid-build. This is also the build script (`build_<part>.py`) — keep them the same file
where you can, so what is proven is what is archived.

---

## 11. Version recovery and archiving

- `dataFile.promote()` on an old version makes a copy of it the latest version. Nothing is
  deleted; the intermediate versions stay in the history. This is the safe "revert to v6".
- `app.documents.open(dataFileVersion, True)` opens a specific version.
- **Unsaved work is one tab-close from gone.** Opening the latest version of a lineage while a
  modified older-version tab is open can leave that tab closed. Before promoting, reverting, or
  opening another version, export any unsaved design as an archive:

```python
em = design.exportManager
em.execute(em.createFusionArchiveExportOptions(path_f3d, design.rootComponent))
```

- The archive plus the build script is the real backup: one restores the document, the other
  regenerates it from source.
- Saving is still a G7 action — `promote()` and archive export are not saves of the user's
  open document, but say plainly what each one does before running it.
