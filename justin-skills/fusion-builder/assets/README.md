# Assets

Working templates, extracted from a real build (a layered relief plaque with a folding
ribbon). They're general in mechanism but carry an example configuration: adapt them, don't
paste them blind. Guidance is in `references/co-design-tools.md`.

| File | What it is | Adapt |
|---|---|---|
| `cloth.js` | XPBD inextensible strip or sheet: fixed length and width, adjustable bending, per-particle floor, self-collision ignoring initial contacts, pins, compact export (`CLOTH1|rows|cols|T|b64`). Plain JS; runs in Node for tests. | Nothing for a strip. For a sheet, feed a rows × cols grid from your part. |
| `marker_board_template.html` | Two-camera marker board: solved cameras, draggable markers, height-ticked guide lines, triangulation, obscured-by-height, edge traces, fit-to-markers (pattern search, Huber, symmetry, regularization), camera refinement, parameter copy/paste, localStorage. | Fill `/*__CAMS__*/` (from `scripts/solve_camera.py`, rescaled to the embedded image size), `/*__MARKERS__*/` ([{id, desc, pos}]), `/*__GEM__*/` and `/*__PHOTO__*/` (base64 JPEGs of the two views), `/*__SCROLLGEN__*/` (your generator port exposing `DEFAULTS`, `leftGrid(p)`, `features(p)`). Edit everything in the PROJECT CONFIG block: the base plane, `TO_ORIG` pixel mapping, `EDGE_TYPES`, `PARAMS` (bounds and groups), `GUIDE` features and `RIGID` landmark ids. |
| `example_generator_port.js` | A complete generator port, used as the structural example: band path, U sag, flare and crest, exact oblique fold, arch profile, thick shell with core/edge split, named features and markers. It is parity-tested against its Python twin to 0.00000 mm. | Copy the structure (`DEFAULTS`, `leftGrid`, `ribbonGrid`, `thickMesh`, `features`, `markers`), not the shape. |
