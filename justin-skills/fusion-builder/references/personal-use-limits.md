# Fusion for personal use — what you actually have

Everything this skill does is scoped to the free personal-use entitlement. Don't propose a
workflow that needs a paid tier; the user will hit a wall three steps in.

**Check first, don't assume.** `fusion_mcp_read{queryType:"licensing"}` returns
`summary.isHobbyist` / `isStudent` / `isCommercial`, plus `services`, `activeExtensions`,
`purchasableExtensions`. Run it at G0 and gate on the live answer — the entitlement table
below is what Autodesk published as of September 2026 and it moves.

Never steer the user toward buying anything. If they hit a limit, name the limit, give the
workaround inside the free tier, and stop there.

## Available (build freely)

| Area | Notes |
|---|---|
| Design workspace | full parametric solid modeling: sketches, constraints, parameters, all the features in `api-recipes.md` |
| Assemblies | components, occurrences, joints, as-built joints, rigid groups, contact sets |
| Surface + Form | patch/loft/stitch/thicken surfacing and T-Spline sculpting |
| Sheet metal | flanges, bends, flat patterns |
| FFF additive manufacturing | Manufacture workspace additive setup, STL/3MF/OBJ export, slicer handoff |
| CAM: 2 and 3-axis milling, adaptive clearing, turning, waterjet/laser/plasma | hobby CNC covered |
| 2D drawings | single sheet per drawing |
| Scripts and Add-Ins (the API this skill drives) | unrestricted |
| Cloud storage, projects, version history, commenting/markup, public shared views | single user |

## Not available (don't propose it)

| Blocked | Free-tier workaround |
|---|---|
| Simulation / stress analysis of any kind | hand calculations, or empirical test prints |
| Generative design, and all paid extensions | manual design studies; parameters make sweeping cheap |
| 3+2, 4-axis, 5-axis milling; mill-turning; probing; automatic tool change; rapid feed | 3-axis only |
| Exploded views and animations; GD&T; batch drawing print | single sheet, manual annotation |
| Multi-user collaboration, shared-view collaboration, user/admin management | public shared view link |
| Unlimited active documents | **10 active editable documents** — see the archive workflow in `domains/data-management.md` |
| Cloud rendering | local render only |
| Electronics beyond 2 schematic sheets / 4 signal layers | — |
| Configurations (`design.createConfiguredDesign()` is refused) | one integer switch parameter plus guarded expressions: `variant = 1`, `is_a = max(0; 2 - variant)`, `is_c = max(0; variant - 2)`, and every variant dimension driven through those flags (`split_z = -(t/2) * is_a`). Document the meaning of each value in the parameter comment. |

## Import/export

Personal use restricts interchange formats. Reliable: **F3D / F3Z, STL, OBJ, 3MF, SKP**.
Restricted or unavailable on the personal tier: **STEP, IGES, SAT, DXF** — reports of exactly
which are blocked differ by version and have changed more than once.

So: before telling a user "export a STEP for the machine shop", try the export and read the
error, or ask them to confirm what their File → Export dialog offers. For a 3D-print
workflow this rarely bites — STL and 3MF are both available and 3MF is the better choice.

## Commercial-use boundary

Personal use is for non-commercial work under $1,000 USD annual revenue from making
activities, and not for work in primary employment. If a user describes a part they intend to
sell, or work for an employer, say plainly once that personal use doesn't cover it, then help
with the modeling regardless — licensing is their call to make, not a gate on being useful.
