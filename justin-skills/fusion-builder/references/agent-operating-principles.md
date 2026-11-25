# Agent operating principles

Handoff notes for whoever runs or redesigns this skill. The rest of the skill says *how* to
drive Fusion; this file says how to run the engagement so the result is the part the user
meant, built right, and rebuildable. It applies to every kind of part: prismatic, printed,
organic, an edit, an assembly.

## Contents
1. What "done" means
2. Choose the modelling route deliberately
3. Resolve uncertainty in layers
4. The loop breaker: change the channel, not the guess
5. Explore cheap, commit expensive
6. One source of truth, flowing one way
7. Speak the user's language, and keep a decision log
8. Honor what the user says doesn't matter
9. Show consequences, not just geometry
10. Every claim carries evidence
11. Proxy metrics can pass while intent fails
12. Reference hygiene
13. Manufacturing is the north star from G1
14. Continuity across long sessions
15. Turn discipline and reporting
16. The skill is a living document
17. Measuring the agent

## 1. What "done" means

Done has four parts, and all four are required:
1. **The user accepted it** at G6 against the ACCEPTANCE line written at G1.
2. **It works in the world:** it prints, fits its mating parts, and meets the minimum
   features at the final scale.
3. **It rebuilds from source:** `build_<part>.py`, plus the parameter JSON and generator
   version for hybrid parts, reproduce it in an empty document.
4. **It stays editable:** the parameters the user will want to change are exposed, named,
   bounded and swept.

A beautiful model that fails any of the four is not done.

## 2. Choose the modelling route deliberately

Decide at G1, and say why:

| Route | When | Editable through |
|---|---|---|
| Parametric, sketch-first | prismatic parts, anything with holes, fits, fasteners | Fusion parameters |
| Edit an existing timeline | the user owns a model | parameters first, appended features second |
| Hybrid (generator + mesh) | folds, self-overlap, organic flow the API can't sweep | generator parameter dict |
| Surface/Form in the UI | sculpted consumer shapes | the user, by hand; the API only inspects |

Mixed parts are normal: rigid parts parametric, one organic part generated. Declare the
split, and put the boundary where the two meet (pins, pads, clearance parameters).

## 3. Resolve uncertainty in layers

Four layers, resolved **in this order**, each with its own evidence:

| Layer | Question | Evidence that settles it | Metric can validate? |
|---|---|---|---|
| Topology | what connects to what, which way it bends or folds, what's hollow | confirmed diagram, user sketch, second view | **no** |
| Proportion | relative sizes and positions | plan reference, silhouette, markers | yes (IoU, marker RMS) |
| Dimension | absolute sizes | scale reference, calipers, nominals | yes (bbox, volume) |
| Tolerance | fits and clearances | mating hardware, printer tests | yes (test prints) |

Most wasted iterations come from fixing proportion or dimension while topology is still
wrong. When a correction arrives, classify it by layer first. A topology correction means
re-confirming the diagram, not tweaking parameters.

## 4. The loop breaker: change the channel, not the guess

Count corrections per feature. **Two corrections on the same feature means stop building
it.** Another guess in the same channel is usually wrong in the same way. Escalate the
channel instead:

1. words → 2. your reading drawn on the reference (numbered traced path, side profile) →
3. the user's own sketch or colored strokes on the image → 4. a second view, read on both
sides if the part is symmetric → 5. an interactive preview the user drives → 6. freeform
manipulation (cloth mode) or markers the user places.

Each step costs more to set up and much less per iteration. Moving up a step early is almost
always cheaper than a third wrong build.

## 5. Explore cheap, commit expensive

Fusion operations are slow, transactional and gated; sandbox geometry is instant. Iterate
shape in the sandbox or preview: generator runs, renders, overlays, fits. Push to Fusion only
what the user has accepted there, then gate it as usual. The gates exist to protect the
timeline, not to slow exploration down. Don't gate every sandbox experiment, and don't
explore inside Fusion.

## 6. One source of truth, flowing one way

Write down which artifact owns each truth, and never let two own the same one:

```
references ─► spec (G1) ─► parameters / generator dict ─► build_<part>.py ─► Fusion document
                                  ▲                                         (derived; never edited
          previews / fitters ─────┘  (ports; parity-tested)                  as the source)
```

- Anything the user tunes in a tool comes back as **resolved values** into the one source.
- Two implementations of the same math need a parity test, run after every change.
- The Fusion document is a build product. When it and the build script disagree, the script
  is right, or it must be updated at a gate.

## 7. Speak the user's language, and keep a decision log

- Keep a **glossary** mapping the user's words to model entities ("top bend" → the crease
  feature; "the lip" → `lip_h`). Name parameters, sliders, markers and sketches in the user's
  words.
- Keep a **decision log** in the session state file: each decision, who made it, and the
  user's words **verbatim**. Paraphrase drifts.
- When a new correction conflicts with an earlier one ("fold under" earlier, "the curl goes
  up" now), don't silently override. Say both, propose how they reconcile, and confirm.
  Usually both are true of different parts of the feature.

## 8. Honor what the user says doesn't matter

"Height is not a factor", "don't worry about cost", "tolerances later": turn each into a rule
in the tools and the spec. Stop warning about it, stop optimizing for it, and don't bring it
back later as a constraint. Record it in the decision log so a later session doesn't
re-litigate it.

## 9. Show consequences, not just geometry

The user decides better from consequences than from shapes:
- minimum gaps to mating parts;
- derived heights of stacked parts;
- the minimum feature at the final print scale;
- overhang share;
- a self-intersection flag;
- print time and filament, when known.

Put them in the readout next to the shape, and color only real violations.

## 10. Every claim carries evidence

"Done", "fixed", "matches" and "clears" each need an artifact in the same message: a
screenshot looked at, or a number against a threshold. Beyond Fusion screenshots, the
evidence toolkit includes:
- build-script reruns in an empty document;
- parameter sweeps;
- parity tests between runtimes;
- synthetic recovery tests for any fitter;
- headless renders of any tool you ship;
- round-trip checks for any data transfer (MD5 and decode error).

If you can't produce the evidence, say what is unverified.

## 11. Proxy metrics can pass while intent fails

IoU, marker RMS, volume and bbox validate proportion and dimension only. A model can score
0.88 IoU with the topology backwards. Pair every metric with the confirmed diagram of the
layer it can't see. Also rule out the **measurement** before blaming the model. Perspective
magnification, a mis-solved camera and a stale screenshot have each looked like modelling
errors.

## 12. Reference hygiene

- Grade each reference for what it can tell you (`photo-matching-and-markers.md` §1). Say
  at G1 which reference owns plan, height and topology.
- AI-generated images are for topology and intent, not measurement. Down-weight them and
  expect about 1% camera residual at best.
- Mirrored halves of a symmetric reference are two views of the same feature, front and back.
- The user's annotations are guides, not coordinates. Extract them, then confirm the reading.

## 13. Manufacturing is the north star from G1

Capture at spec time, not at export:
- process, nozzle and material;
- final scale;
- build volume;
- minimum features (at least 3 nozzle widths at final scale);
- overhang policy;
- part splits and joining (pins, clearances as parameters);
- color or material strategy (separate parts or inlays beat per-layer color swaps);
- orientation.

Geometry that's right but unprintable goes back to G1.

## 14. Continuity across long sessions

Chat context gets compacted; files don't. Keep `session_state.md` beside the build script,
updated at every gate:
- current version and files;
- parameter JSON path;
- gate status;
- open decisions and the punch list;
- glossary and decision log;
- API lessons learned this session;
- the next action.

Name versioned artifacts (`gen_v18.py`, `params_v18.json`) and keep old ones; rollback is
then free. A new session, or a new agent, should be able to resume from that file alone.

## 15. Turn discipline and reporting

- One gated increment per turn. Long multi-tool turns are for sandbox exploration only.
- Lead with what changed and the evidence, then **one** decision with a proposed default.
  Don't end on an open question without a default.
- Match the user's register. For a terse, technical user: numbers, names, no preamble.
- When you're about to build something expensive on an interpretation, show the
  interpretation first.

## 16. The skill is a living document

Every surprise in a session is a missing line in a reference:
- an API limit (`troubleshooting.md`);
- a platform limit (`personal-use-limits.md`);
- a workflow failure (this file);
- a new tool (`scripts/`, `assets/`).

Add it at the end of the session, generalized. The crest build contributed the payload,
spline and mesh limits, the procedural route, camera matching and markers, and most of this
file.

## 17. Measuring the agent

Track per build:
- corrections per feature;
- iterations to an accepted G4;
- rework after G4;
- claims made with evidence versus without;
- parity, sweep and rebuild pass rate;
- time to first accepted solid.

Rising corrections per feature is the earliest sign the channel is wrong (§4). The starter
eval set is in `evals/evals.json`. Add a case whenever a new failure mode is found, so the
next skill change is tested against it.
