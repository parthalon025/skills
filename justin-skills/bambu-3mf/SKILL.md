---
name: bambu-3mf
description: Build a Bambu Studio 3MF project from incoming design information — meshes (STL/OBJ/3MF/STEP) plus plates, filaments/AMS slots, colours, materials, process settings, per-object and per-part overrides, modifiers, negative parts, height ranges, bed type, print sequence and H2D nozzle mapping. Use whenever the user wants a 3MF, a print plate, a test plate, a multi-plate or multi-material/multi-colour project, filament or slot assignment, or "the Bambu file" for a part — even when they only say "make it printable", "set up the plate", or "slice-ready". Also use to validate an existing Bambu 3MF or to bake and slice-check one headlessly with the bambu-studio CLI.
---

# bambu-3mf (x1.0)

Turn incoming information into a Bambu Studio project: geometry, plates, filaments and every
setting. The skill writes the 3MF in the container. Bambu Studio on the user's PC then bakes the
full project settings and proves the result with a real slice.

## Hard rules (each one comes from a real failure or from the Bambu source)

1. **Never write `Metadata/project_settings.config` into a generated 3MF.** A file that has the
   `BambuStudio-` application tag plus a hand-made project config segfaulted Bambu Studio.
   Global settings travel as user presets. `finalize` bakes them through the CLI, and Bambu
   Studio writes the real project config itself (all keys, `different_settings_to_system`, per-plate arrays).
2. **Object, part and range settings are scalar keys only.** On the H2D, vector keys (speeds,
   accelerations, temperatures) are per-nozzle multi-value arrays. A malformed per-object value is a
   crash risk. Put them in `process_overrides` or filament `overrides`. The builder enforces this.
3. **Meshes must be closed, consistent, positive-volume solids.** The builder welds vertices and
   removes degenerate faces, then refuses anything still open unless `allow_open` is set.
4. **Never overwrite plates or files.** The output folder name carries the version. A rebuild needs
   a new version. Prefix `x` on unsettled designs (`x9.1`). Drop it for a SKU (`9.1`). Object
   and part names also get the version.
5. **Fail closed.** A check that did not run reports NOT RUN, never PASS. Report every warning.
6. **Visual inspection is a test.** View the previews before you present files. Defects found so
   far only by viewing: invisible object, wrong colour, overlap, object off the plate.

## Workflow (tracer bullet: thin slice first, then thicken)

1. **Collect the inputs.** Get them from the conversation, uploaded files, CAD output (Fusion /
   CadQuery) and memory: printer (default H2D 0.4), AMS slot map, materials and colours, plates,
   orientation, special settings. Search Notion for the program hub or material profiles when the
   user keeps them there. Ask only for what blocks the build; state each default you assume.
2. **Find preset names** if they are unknown:
   `python scripts/profiles.py find "PCTG @BBL H2D"`. Names must match the BBL index exactly.
3. **Write the spec.** See `references/spec_schema.md`; `assets/example_spec.json` is a full
   example. For a new design, start with one plate and one object.
4. **Build:** `python scripts/build_3mf.py spec.json --out /mnt/user-data/outputs`
   (`--offline` skips the key validation and the report says NOT RUN).
5. **Validate every 3MF:** `python scripts/validate_3mf.py <file>.3mf --manifest <dir>/manifest.json`.
   Any FAIL means you fix the spec or the geometry, bump the version and rebuild.
6. **Inspect** `previews/*_plate<N>.png` with the image viewer: iso view plus top view with the
   shared-nozzle zone (dashed line).
7. **Thicken:** add plates, parts, ranges and overrides, then rebuild and revalidate.
8. **Finalize on the PC.** Use Desktop Commander when it is connected; otherwise give the user
   the command. Put the bundle folder on the PC (the user downloads it, or you write it in chunks),
   then run:
   `powershell -ExecutionPolicy Bypass -File finalize_<ver>.ps1`
   (defaults: `C:\Program Files\Bambu Studio\bambu-studio.exe`, work folder `C:\Temp\bs\<tag>`).
   It writes `<tag>_baked.3mf` (the Bambu-authored project to open and print), the sliced
   `.gcode.3mf`, Bambu's own plate PNGs and `verify.json`. Read `verify.json` and the per-plate
   time, grams and warnings, then report them to the user.
9. **Present** the 3MF, the report and the previews. Give the result in short STE sentences:
   what was built, which checks passed, what is NOT RUN or unverified, the next action.

## Crash isolation (when Bambu Studio fails to open or slice)

Open the files in this order: `_first_object.3mf`, then `.3mf`, then `_geometry_only.3mf`.
- First object fails: the problem is the geometry or the object settings.
- Full fails, first object opens: the problem is the multi-object or multi-plate data.
- Only geometry-only opens: the problem is a setting. Bisect the settings in the report.

## Known unverified items (confirm on first real use, then update this list)

- The GUI and CLI load multi-plate `<plate>` blocks from a generated (non-saved) file.
- H2D `filament_maps`: 1 = left nozzle, 2 = right nozzle (the builder warns on every use).
- The CLI bake applies `--load-settings` to a Bambu-tagged file that has no project config.
- Windows PowerShell 5.1 JSON round-trip of the presets (tested on pwsh 7.4 only).

## Files

- `scripts/build_3mf.py`: spec → bundle (3MF ×3, presets, report, previews, manifest, finalize).
- `scripts/validate_3mf.py`: 12 checks, with lib3mf (3MF Consortium) for core-spec reading.
- `scripts/profiles.py`: BBL preset resolver and key catalog (661 keys + enum values) from BambuStudio source.
- `scripts/finalize.ps1`: PC bake, slice, render and readback.
- `references/format.md`: Bambu 3MF layout, key names and plate math, with sources. Read it before you edit the writer.
- `references/spec_schema.md`: spec fields, defaults and validation rules.
- `assets/key_catalog_*.json`: offline snapshot of the key catalog.

Dependencies: `pip install trimesh numpy matplotlib lib3mf --break-system-packages`
(add `cadquery` for STEP input). The build needs network access to raw.githubusercontent.com for
presets; when it is not available, use `--offline`.
