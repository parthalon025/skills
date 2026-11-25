# Bambu Studio 3MF format: what the writer relies on (x1.0)

Sources: bambulab/BambuStudio master (Oct 2026) `src/libslic3r/Format/bbs_3mf.cpp`,
`src/slic3r/GUI/PartPlate.{hpp,cpp}`, `src/libslic3r/PrintConfig.cpp`, `src/libslic3r/Model.cpp`,
`src/BambuStudio.cpp` (CLI); field results from the user's prior sessions; the queso gist
"3MF File Format Research" (Jan 2026); printago.io slicer CLI notes.

## Package layout written

```
[Content_Types].xml          rels, model, png, config, xml
_rels/.rels                  3D/3dmodel.model + thumbnail Metadata/plate_1.png
3D/3dmodel.model             core 3MF; all meshes inline; one assembly object per printable object
Metadata/model_settings.config   objects, parts, extruders, settings, plates
Metadata/layer_config_ranges.xml height-range modifiers (only when used)
Metadata/plate_N.png         plate thumbnails
```
Not written: `project_settings.config`, `slice_info.config`, `plate_N.json`, `*_settings_N.config`.
Bambu Studio writes them when it bakes or saves.

## 3dmodel.model

- `<metadata name="Application">BambuStudio-02.08.02.61</metadata>`: `starts_with("BambuStudio-")`
  sets `m_is_bbl_3mf` (bbs_3mf.cpp). This version string opened in prior sessions.
- `<metadata name="BambuStudio:3mfVersion">1</metadata>`.
- Mesh objects: `type="model"` for normal parts, `type="other"` for negative, modifier and support
  volumes. The config `subtype` is what Bambu uses.
- Assembly object: `<components>` with one `<component objectid>` per part and no transform.
- Vertices are in **world coordinates** (plate offset included). Build items have no transform.
  This layout loaded and sliced in the clip and slip-float sessions.
- `printable="1"` on `<item>` is a Bambu extension. lib3mf warns 32935 about it; the warning is expected.

## model_settings.config

```xml
<object id="ASSEMBLY_ID">
  <metadata key="name" value="..."/>   <metadata key="extruder" value="N"/>   <metadata key="<process key>" value="..."/>
  <part id="COMPONENT_OBJECT_ID" subtype="normal_part|negative_part|modifier_part|support_enforcer|support_blocker">
    <metadata key="name" .../> <metadata key="extruder" .../> <metadata key="<process key>" .../>
  </part>
</object>
<plate>
  plater_id, plater_name, locked, bed_type, print_sequence, filament_map_mode, filament_maps, thumbnail_file
  <model_instance> object_id, instance_id, identify_id </model_instance>
</plate>
```
- The part `id` is the sub-object id: `_handle_start_config_volume` → `volumes.emplace_back(subobject_id, type)`.
- `extruder` = 1-based project filament index. The skill sets index = AMS slot (gaps get placeholders).
- `bed_type` values: Default Plate, Cool Plate, Engineering Plate, High Temp Plate, Textured PEI Plate, Supertack Plate.
- `print_sequence`: `by layer` | `by object`.
- `filament_map_mode`: Auto For Flush, Auto For Match, Manual, Nozzle Manual, Auto For Quality ("Auto" is ignored).
- `filament_maps`: space-separated ints, one per filament, values < 1 clamp to 1. 1 = left and
  2 = right is the extruder order of `extruder_printable_area` in the H2D machine preset (index 0
  covers x 0–325). This is UNVERIFIED in the GUI.
- `plater_name`, not `plate_name` (source typo, kept).

## layer_config_ranges.xml

```xml
<objects><object id="ASSEMBLY_ID"><range min_z=".." max_z=".."><option opt_key="k">v</option></range></object></objects>
```

## Plate grid (PartPlate)

`cols = compute_colum_count(n)`: `v = sqrt(n)`, `cols = round(v) + (v > round(v))`.
Plate i (0-based): `row = i / cols`, `col = i % cols`,
`origin = (col * W * 1.2, -row * D * 1.2)` with `LOGICAL_PART_PLATE_GAP = 1/5`. W and D come from the
bounding box of `printable_area` (H2D: 350 × 320). The gist measured ~303 mm on a 256 mm bed, which
does not match 307.2; the source formula is used.

## Config keys

- The key universe is `PrintConfigDef` (661 keys excluding CLI options). Scalar types are coFloat,
  coInt, coBool, coString, coEnum, coPercent, coFloatOrPercent and coPoint. All others are vectors.
- All values are strings in Bambu files.
- In process and filament presets, vector keys have one entry per extruder variant (H2D process: 7
  entries; H2D filament: 3 entries). The builder expands a scalar override to the preset length.
- `different_settings_to_system` must list every changed key, or Bambu silently drops the value
  (gist). The skill avoids the trap: Bambu computes the list when it bakes user presets.

## CLI (BambuStudio.cpp / CLIActionsConfigDef)

- `--load-settings "machine.json;process.json"` and `--load-filaments "f1;f2;..."`: each file is
  a full config. A user preset (`from: User`) names its system parent in `inherits`. Installed
  full system presets: `<install>/resources/profiles/BBL/{machine,process,filament}_full/<name>.json`.
- `--slice 0` slices all plates (`--slice i` slices plate i). `--export-3mf <name>` goes into `--outputdir`.
- `--export-png 0 --camera_view 0` gives native plate renders. `--allow-newer-file`, `--info` and
  `--export-settings <file>` are also available.
- `result.json` in the outputdir has `return_code`, `error_string`, and `sliced_plates[]` with
  `total_predication`, `main_predication`, `filaments[].total_used_g`, `warning_message` and
  `feature_type_times`.
- Windows launch (proven): `Start-Process -PassThru -NoNewWindow`, `WaitForExit`, then `Start-Sleep 2` before reading `result.json`.

## Validation references

- 3MF Core Spec 1.x (3MF Consortium); official `lib3mf` (pip) reads and validates the core model.
- Core rules that are checked: unique ids, resolvable references, index range, no degenerate
  triangles, closed manifold meshes, build items reference objects.
