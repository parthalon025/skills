# Assemblies

Components, occurrences, joints, rigid groups, contact sets. All available on personal use.

Verify any signature you're unsure of before sending:
`fusion_mcp_read{queryType:"apiDocumentation", filter:"adsk.fusion.Joints"}`. The joint API
has more type-specific inputs than any other area and guessing costs an undo.

## The mental model that prevents most pain

- **Component** = the definition (geometry, sketches, its own origin).
- **Occurrence** = a placement of that component in a parent. Same component, three places on
  the assembly, three occurrences.
- Geometry belongs to the component; position belongs to the occurrence.
- **Joints** relate occurrences by their *geometry*, and are the assembly's real structure.
  Moving parts by transform instead of jointing produces an assembly that looks right and
  falls apart the moment anything changes.

Bodies in the root component are the classic beginner's mess. Multi-part designs get real
components from the start.

## Creating components and occurrences

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    m = adsk.core.Matrix3D.create()
    occ = root.occurrences.addNewComponent(m)      # identity = at the parent origin
    comp = occ.component
    comp.name = "Arm"
    occ.component.description = "swing arm"

    # a second placement of the SAME component
    m2 = adsk.core.Matrix3D.create()
    m2.translation = adsk.core.Vector3D.create(5.0, 0, 0)   # cm
    occ2 = root.occurrences.addExistingComponent(comp, m2)

    print("components=%d occurrences=%d" % (design.allComponents.count, root.occurrences.count))
```

Sketch and feature inside a component by using `comp.sketches` / `comp.features`, not
`root.*`. Getting this wrong is why geometry ends up in the root and won't move with its
part.

**Ground the base component**: `occ.isGrounded = True`. An assembly with nothing grounded
drifts under joint solving and every motion looks wrong.

## Joints

Two halves: the **geometry** on each side, and the **motion type**.

```python
def planar_geo(occ_face):
    return adsk.fusion.JointGeometry.createByPlanarFace(
        occ_face, None, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)

def circular_geo(occ_edge):
    return adsk.fusion.JointGeometry.createByCurve(
        occ_edge, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)

ji = root.joints.createInput(geo_one, geo_two)
ji.setAsRigidJointMotion()
# or:
# ji.setAsRevoluteJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)
# ji.setAsSliderJointMotion(adsk.fusion.JointDirections.XAxisJointDirection)
# ji.setAsCylindricalJointMotion(...)  setAsPinSlotJointMotion(...)  setAsPlanarJointMotion(...)  setAsBallJointMotion()
jt = root.joints.add(ji)
jt.name = "J_arm_pivot"
```

Key points:

- Joint geometry comes from **occurrence-proxy** faces/edges, not the component's own
  entities. Get them via `occ.bRepBodies.item(i).faces.item(j)` on the occurrence, or use
  `entity.createForAssemblyContext(occ)`. Using the raw component entity in a multi-occurrence
  assembly joints the wrong copy — and it will look correct until the second occurrence moves.
- Select those faces/edges **by geometry**, never by index (`api-recipes.md` §6). Indices
  churn on rebuild, and a joint pointing at the wrong face is worse than a failed one.
- `JointKeyPointTypes`: Center, Start, End, Middle. Center on a circular edge gives the axis —
  that's the usual pick for a pivot.
- Offset and angle: `jt.offset = adsk.core.ValueInput.createByString("2 mm")`,
  `jt.angle = ...`, `jt.isFlipped = True`. Parameterize the offset like any other dimension.
- Limits: `jt.jointMotion` cast to the specific motion type exposes `rotationLimits` /
  `slideLimits` with `isMaximumValueEnabled`, `maximumValue`, and so on.

**Joint origins** (`comp.jointOrigins`) give a stable named attachment point that survives
geometry edits. For anything that will be revised — which is everything — creating a joint
origin and jointing to that beats jointing to a face.

**As-built joints** (`root.asBuiltJoints`) hold parts where they already are, no geometric
alignment. Right for things modeled in place; wrong when you want the joint to define position.

**Rigid groups** (`root.rigidGroups.add(occurrenceCollection, True)`) lock a set of
occurrences together without a joint each — fasteners, subassemblies that never move.

## Contact sets

Contact sets make parts collide during motion instead of passing through each other.
Enable contact only between the specific pairs you care about; global contact on a large
assembly is slow enough to make the model unusable.

The contact-set API surface is thinner than the rest of assemblies and has moved between
releases — look it up (`apiDocumentation`, search `Contact`) before scripting, and be ready to
tell the user to set it up in the UI, which is two clicks. Not everything is worth automating.

## Inspecting an assembly (read-only)

```python
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    def walk(occ, depth=0):
        print("%s%s  grounded=%s bodies=%d" % ("  " * depth, occ.name,
              occ.isGrounded, occ.bRepBodies.count))
        for child in occ.childOccurrences:
            walk(child, depth + 1)

    for occ in root.occurrences:
        walk(occ)
    print("root loose bodies: %d  <- should usually be 0" % root.bRepBodies.count)
    for j in root.joints:
        print("joint %s type=%s suppressed=%s" % (j.name, type(j.jointMotion).__name__, j.isSuppressed))
    for rg in root.rigidGroups:
        print("rigid group %s occurrences=%d" % (rg.name, rg.occurrences.count))
```

Run this before touching an existing assembly. "Root loose bodies > 0" and "nothing grounded"
are the two findings that change the whole plan, and both are worth raising at G0.

## Gates for assembly work

Assembly work adds one gate of its own: **joint scheme approval**. Before creating any joint,
present the intended scheme — which component is grounded, each joint as
`A ↔ B, type, axis, what it allows` — and wait. Rebuilding a joint tree is much more painful
than rebuilding a solid feature, because every downstream joint references it.

Then one gate per joint or per tight group, as with features. Verify motion by driving the
joint and screenshotting at two or three positions, not just at rest — a joint that looks
right at rest can be pinned or inverted at 40°.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| whole assembly moves when one part should | nothing grounded | `occ.isGrounded = True` on the base |
| joint moves the wrong part | first geometry argument is the one that moves | swap the arguments |
| parts pass through each other | no contact set | enable contact for that pair only |
| joint fails after a parameter change | joint geometry pointed at a face that vanished | joint to a joint origin instead |
| second copy of a part misbehaves | joint used component entities, not occurrence proxies | `createForAssemblyContext(occ)` |
| "the assembly is over-constrained" | duplicate joints between the same pair | one joint per relationship; use rigid groups for the rest |
