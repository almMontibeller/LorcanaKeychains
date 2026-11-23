# Wilds Unknown v1.6

Open [Wilds Unknown v1.6](Set_12_Wilds_Unknown_v1.6.3mf) as a project in Bambu Studio to load the three filament assignments and the A1 0.4 mm nozzle, 0.20 mm layer, Arachne process.

The lettering and foliage were redrawn from the archived title artwork. The 12 ivory letters have smooth edges, and the counters in D and O show the brown underneath. Dark green is confined to the six foliage elements. Filling 24 small openings gives the title a continuous 2 mm cocoa-brown backing with a single 6.5 mm eyelet bore.

The new footprint is **82.91 × 40.47 × 3.00 mm**. The exact bore coordinates, 10.5 mm nominal eyelet size, relief heights, assembly placement and embedded filament and process settings carry forward from [v1.5](../v1.5/Set_12_Wilds_Unknown_v1.5.3mf).

[Top view](Set_12_Wilds_Unknown_v1.6_preview.png) · [Isometric view](Set_12_Wilds_Unknown_v1.6_isometric.png) · [Comparison with v1.5](Set_12_Wilds_Unknown_v1.6_comparison.png)

![Bambu Studio toolpath preview of Wilds Unknown v1.6](Set_12_Wilds_Unknown_v1.6_sliced_preview.png)

Bambu Studio 2.9.1 sliced all three colours with no plate warnings. The geometry and toolpath audits confirmed a continuous brown floor around the open eyelet, six separate green foliage shapes and twelve separate ivory letters on their respective layers. Physical printing and chain fit remain unverified. [Validation report](Validation_v1.6.json) · [Slice result](../../../validation/Set_12_Wilds_Unknown/v1.6/result.json) · [CLI log](../../../validation/Set_12_Wilds_Unknown/v1.6/slice.log)

## Reproduction

The [editable vector artwork](Sources/set12_clean_artwork.svg) uses the coordinate system of the [archived PNG](../../../collection/v1.0/Sources/lorcana-keychains/sources/12.png). The [build manifest](Build_manifest.json) records the input and model hashes. From the project root, using Python with NumPy, Pillow and Shapely, system Cairo and GLU, and the local Bambu Studio installation:

```sh
python3 tools/rebuild_set12.py --output-dir /tmp/lorcana-set12-v1.6-reproduction
python3 tools/validate_set12.py --project /tmp/lorcana-set12-v1.6-reproduction/Set_12_Wilds_Unknown_v1.6.3mf
```
