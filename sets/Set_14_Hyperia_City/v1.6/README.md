# Hyperia City v1.6

Open the [Bambu Studio project](Set_14_Hyperia_City_v1.6.3mf) as a project to load the A1 and filament settings.

All 11 letters were redrawn from the [saved Hyperia City artwork](../../../collection/v1.0/Sources/lorcana-keychains/sources/14.png). The solid Ivory White faces retain the curled H, angled bars, and openings in P, R, and A. The Ice Blue outline is 0.58 mm around the outside and 0.45 mm inside the three openings, where Caramel shows through. The Caramel relief and Cocoa Brown backing follow the lettering with smooth edges.

The keychain measures **71.90 × 40.56 × 3.00 mm**. The backing and eyelet are 2 mm high, with a 6.5 mm bore and nominal 10.5 mm outer diameter. Slots 1–4 are Cocoa Brown, Caramel, Ivory White, and Ice Blue.

![Model preview](Set_14_Hyperia_City_v1.6_preview.png)

- [Isometric view](Set_14_Hyperia_City_v1.6_isometric.png)
- [Matched-scale comparison with v1.5](Set_14_Hyperia_City_v1.6_comparison.png)
- [Exported letter contours over the original artwork](Set_14_Hyperia_City_v1.6_source_overlay.png)
- [Actual sliced toolpaths](Set_14_Hyperia_City_v1.6_sliced_preview.png)
- [Editable SVG letter paths](Sources/set14_clean_artwork.svg)

Bambu Studio sliced the full-size model with the A1 0.4 mm nozzle, 0.20 mm layers, and Arachne, with zero plate warnings. Both ivory layers contain 11 separate letters. The audit confirmed the blue bands and the three counter openings, and the bore stays clear on every backing layer. Physical print and ring fit are untested. [Validation report](Validation_v1.6.json) · [Slicer result](../../../validation/Set_14_Hyperia_City/v1.6/result.json)

## Reproduce

Build from the [v1.5 Bambu Studio project](../v1.5/Set_14_Hyperia_City_v1.5.3mf) and the editable SVG. Run from the project root with NumPy, Pillow, Shapely 2.1 or newer, Cairo, GLU, and local Bambu Studio.

```sh
python3 tools/rebuild_set14.py --output-dir /tmp/lorcana-set14-reproduction
python3 tools/validate_set14.py --project /tmp/lorcana-set14-reproduction/Set_14_Hyperia_City_v1.6.3mf
```

[Source snapshot](Source_snapshot.zip) · [Build manifest](Build_manifest.json)
