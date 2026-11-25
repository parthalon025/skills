---
name: architecture-maps
description: Build, review, or update a solution architecture package — a set of coordinated architecture maps (system context, logical capability, technology, network/deployment, identity/security, data flow, sequence, operations, resilience) delivered as an editable multi-page draw.io file plus a self-contained HTML package with architecture decision records (ADRs), a Well-Architected review, and a risk/assumption register. Works for Azure, AWS, Google Cloud, Microsoft 365/Power Platform, on-prem, SaaS and hybrid designs. Use this whenever someone wants to diagram, map, document, draw or explain how a system is built or how its parts connect, asks for an architecture diagram, solution design, reference architecture, network/deployment diagram, data-flow or sequence diagram, trust-boundary or security architecture, or wants an existing architecture diagram reviewed, critiqued, checked against best practice or updated to a new version — even if they never say "architecture map".
---

# Architecture maps

Turn a system description (or an existing diagram) into an architecture package that answers a stakeholder question. One JSON spec drives every output, so diagrams, tables and title blocks always agree.

Deliverables (same folder, same version in every name):
- `<workload>_architecture_<version>.drawio` — one page per view, official vendor icons, editable in diagrams.net / draw.io desktop / VS Code.
- `<workload>_architecture_<version>.html` — the package: question, views, data-flow register, ADRs, Well-Architected review, register, validation, change log.
- `..._previews/*.png` — your visual test images. `..._spec.json` — the source for the next version.

The method lives in `references/method.md` (read it the first time you use this skill in a session — at least sections 2 and 3). Spec format: `references/spec.md`. Framework pillars: `references/frameworks.md`. Worked example: `assets/example_spec.json`.

## Pick the mode

- **Build** – a new design or a design that exists only in someone's head or in prose.
- **Review** – they give a diagram, image, document or description and want it checked.
- **Update** – a package from this skill (or any `.drawio`) needs to change.

## Step 1 – Frame the architecture question (all modes)

A map starts from a question, not from icons. Write this sentence first:

> For **[audience]**, this map explains **[system or decision]** so they can determine **[question]**, within **[scope and constraints]**.

Pull every input you can from the request: business outcome, actors, scope in/out, constraints, quality targets (availability, RTO/RPO, latency, scale), decisions needing approval, unknowns, target platform.

**Gaps: ask first, then build.** If an input that would change the design is missing — audience or question, platform, scope, a hard constraint (data residency, no public endpoints), quality targets, which end-to-end scenario matters — ask the user **one short batch** of questions (use a multiple-choice question tool if you have one; offer sensible defaults as options). Do not ask about things that do not change the drawing.
If nobody can answer (unattended run, or the user says "just go"), continue: record each gap in the register as an *Open question* or *Assumption*, write `TBD` in the field, and mark any assumed component `assumption: true` so it draws dashed with "(assumed)". Never present a guess as a fact — reviewers approve what they see.

## Step 2 – Choose the views that answer the question

A complete architecture is several focused maps, not one big one. Make only the views the question needs; make all ten only when asked for the full package.

| The audience needs to decide… | Views |
|---|---|
| Business value / funding | executive_outcome, system_context |
| What we are building, at a glance | system_context, logical_capability |
| Which products and why | logical_capability, technology (+ ADRs) |
| Security / identity sign-off | system_context, identity_security, network_deployment, one sequence for the main auth path |
| Network / landing-zone fit | network_deployment, identity_security |
| Data protection, privacy, AI grounding | data_flow (+ data_flows register), identity_security |
| How one scenario works | sequence (one per critical scenario) |
| Run / support readiness | operations, resilience |

Always include system_context unless the user asks for a single specific view. ADRs, register and validation go in every package; the Well-Architected review goes in every Build package (match the platform — `references/frameworks.md`).

## Step 3 – Write the spec, thin slice first

Work tracer-bullet style: write `meta`, `inputs` and **one** view (usually system_context), then `check` and `build` into a scratch folder and look at it. Only then add the remaining views. This catches layout and naming problems while they are cheap.

```bash
S=<this skill dir>/scripts/archmap.py
python3 $S check work/spec.json
python3 $S build work/spec.json --out work/scratch-1     # scratch builds: new folder each time
python3 $S icons aws:                                    # find icon keys
```

Rules the checker enforces (and why):
- Every edge is one-way, labelled, typed; add the protocol when it is not obvious — readers must see who starts each interaction.
- Boxes only for real boundaries (tenant, subscription/account/project, region, zone, VNet/VPC, subnet, trust, application, environment, external) — a decorative box gets read as a security boundary.
- Every technology-view node carries `requirement` (requirement ID or ADR) — no service is chosen for familiarity.
- A PaaS service reached through a private endpoint is drawn **outside** the subnet; the endpoint sits inside.
- The identity/security view has at least one labelled trust boundary.
- Icons come only from the verified catalog. A product with no icon gets a plain labelled box — never another product's icon.
- Assumed components appear in the register.
- Metadata (owner, reviewers, version, status, date, environment) is complete — it is printed on every page.

Use functional names in executive and capability views ("Knowledge retrieval", "Policy enforcement"), product names from the technology view onward. Keep each view to about 15 nodes; split rather than crowd.

## Step 4 – Inspect the pictures (this is a test, not a formality)

After every build, open each PNG in `_previews/` and look. A passing `check` does not mean the map reads well. Look for:
- labels sitting on nodes or on other labels; edges crossing through unrelated boxes;
- a boundary that wrongly swallows a node (e.g. an external SaaS drawn inside your tenant);
- a reader unable to answer the view's question from the picture alone.

Fix the spec (move `col`/`row`, add an empty column between sibling boundaries, shorten labels, split the view) and rebuild into a new scratch folder. Repeat until each picture is clean. Two or three rounds is normal.

## Step 5 – Decisions, review, register, validation

- **ADRs** – one per major choice (compute model, connectivity, identity, integration, data store, AI model hosting …). Fill every field; `TBD` plus a register item when unknown.
- **Well-Architected review** – framework matched to the platform; 3–6 sharp questions per pillar; status `met` only with evidence in the design.
- **Register** – risks, assumptions, dependencies, constraints, open questions, decisions required, PoCs, security/compliance reviews; each with impact, owner, date, validation method, status.
- **Validation** – answer the 14 method questions (`references/method.md` §7) honestly; "partial" and "no" are useful answers.
- **Data flows** – when a data_flow view exists, every flow gets all ten fields.

## Step 6 – Final build and hand-off

Build into the delivery folder only after the scratch previews are clean. `build` refuses to overwrite a version; if you spot a problem before you hand anything over, fix the spec and rebuild with `--replace-draft` (works only while `status` is Draft) — do not bump the version for a fix nobody has seen, and never leave stale files in the delivery folder. Hand over the `.drawio` and `.html` (and the spec JSON if they will iterate). In the reply: one line on what the package answers, the views included, and the top open questions from the register. Keep explanations short and plain.

## Review mode

1. Keep the original untouched.
2. Get the design into view:
   - `.drawio` → `python3 $S import file.drawio --out work/imported.json`, read it (stats show unlabelled, two-way, undirected and dangling edges).
   - image or PDF → look at it carefully; list every node, boundary and arrow you can see.
   - prose/doc → extract components and flows.
3. Assess against: the architecture question (is there one?), the view's "Show" list (`method.md` §2), the conventions (§3), the 14 validation questions (§7), and the platform framework. Accuracy matters most: wrong placement (PaaS inside a subnet, public endpoint drawn as private), missing trust boundaries, two-way arrows, unlabelled flows, decorative boxes, wrong or borrowed icons, assumptions shown as facts, missing metadata.
4. Write findings into a spec's `review` block: `id`, `severity` (high = misleads a decision or hides a security/reliability issue; medium = forces the reader to guess; low = consistency/polish), `rule` (method section), `location`, `finding`, `fix`. Rank high first.
5. Rebuild the reviewed design as corrected views (version `0.1` of the corrected package unless told otherwise) so the reader sees the fix, not only a list. If you could not confirm something from the source, register it as an open question — do not "fix" it with a guess.
6. Deliver the HTML (findings first) and the corrected `.drawio`.

## Update mode

1. Load the previous `..._spec.json` (or `import` the `.drawio` and rebuild a spec).
2. Make the change. Bump `meta.version`: minor for a change while in Draft/Proposed/Under review (0.1 → 0.2); 1.0 at Approved; later changes 1.1, 2.0 for a redesign. Add a `changelog` entry, update `date`, and set `status`.
3. If the change alters a boundary, data flow, integration, topology or availability target, re-check the matching views, ADRs and register items — an update that changes one view often invalidates another.
4. Build into the same folder. Old version files stay; new files appear beside them.

## Output conventions

- File and title names carry the version; the drawio page names carry the view number and title.
- Styling (colors, line types, boundary styles, legend, title block) comes from `archmap.py` only — do not hand-edit styles, so the whole set stays consistent.
- If the user names another diagram format (Visio, Mermaid, PowerPoint), still build the spec and the draw.io file (draw.io exports to `.vsdx`, PNG, SVG, PDF) and say how to export.
