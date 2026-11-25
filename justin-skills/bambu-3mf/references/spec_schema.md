# Job spec (x1.0)

JSON. Mesh paths are relative to the spec file. Units are mm. Unknown keys and bad values stop the build.

```jsonc
{
  "name": "Clip_H2D_WhiteGlow",          // required; becomes <name>_<version>
  "version": "x9.1",                     // required; x = unsettled design, no x = SKU
  "printer": {                           // optional; defaults shown
    "machine": "Bambu Lab H2D 0.4 nozzle",
    "process": "0.20mm Standard @BBL H2D",
    "profiles_ref": "master"             // BambuStudio git ref for presets and key catalog
  },
  "filaments": [                         // required; slot = project filament index = AMS slot
    {"slot": 3, "preset": "Generic PCTG @BBL H2D", "color": "#FFFFFF", "label": "White PCTG",
     "overrides": {"nozzle_temperature": 250}}   // filament keys; scalar expands to every variant
  ],
  "process_overrides": {"layer_height": 0.3, "outer_wall_speed": 120},  // any process key
  "plates": [{
    "name": "Test",                      // plater_name
    "bed_type": "Textured PEI Plate",    // Default|Cool|Engineering|High Temp|Textured PEI|Supertack Plate
    "print_sequence": "by layer",        // or "by object"
    "filament_map_mode": "Auto For Flush",   // optional
    "nozzle_map": {"3": "left", "8": "right"}, // optional (H2D); sets Manual + filament_maps
    "locked": false,
    "objects": [{
      "name": "Clip_i0.20",
      "mesh": "clip.stl",                // or "parts", or both (mesh = first normal part)
      "parts": [{"name": "glow", "mesh": "glow.stl", "filament": 8,
                 "type": "normal_part",  // negative_part|modifier_part|support_enforcer|support_blocker
                 "settings": {"wall_loops": 3}, "allow_open": false}],
      "filament": 3,                     // object default; parts inherit it
      "rotate": [0, 0, 0],               // degrees, applied X then Y then Z
      "scale": 1.0,
      "position": [175, 160],            // plate-local bbox centre; omit = auto-arrange
      "copies": 1,                       // separate objects, suffixed _c1.._cN
      "settings": {"sparse_infill_density": "20%"},          // scalar process keys only
      "height_ranges": [{"min_z": 0, "max_z": 1.2, "settings": {"sparse_infill_density": "100%"}}]
    }]
  }],
  "options": {"spacing": 6, "edge_margin": 5}   // auto-arrange gap and margin (mm)
}
```

## Placement

- Each object drops to Z = 0. Only normal parts count; negative and modifier volumes may extend below the bed.
- Auto-arrange packs shelves in the zone that every nozzle reaches (H2D: X 25–325), then centres the group.
- A given `position` may use the full bed. Outside the shared zone the builder warns; outside the bed it stops.
- Overlapping bounding boxes give a warning, not an error, because interlocking parts can be intentional.

## Validation

| Rule | Scope |
|---|---|
| key exists in PrintConfigDef | all settings |
| enum value is legal | all settings |
| scalar types only; no per-nozzle keys | object, part, range |
| vector length = preset length | process / filament overrides |
| filament refers to a defined slot | object, part, nozzle_map |
| closed solid mesh | every part unless allow_open |
| fits bed and height | every object |
| output folder does not exist | build |
