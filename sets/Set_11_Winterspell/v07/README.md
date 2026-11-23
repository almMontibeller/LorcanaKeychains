# Winterspell v07

Open the [Bambu Studio project](Set_11_Winterspell_v07.3mf) at **100% scale with the A1 0.4 mm nozzle**. The project retains the original 0.20 mm Arachne process and the Marine Blue, Ice Blue and Ivory White filament assignments.

The retrace follows the full letter shapes in the original Winterspell artwork. It restores the W and final L scrolls, rounds the serif tips and gives all eleven letters individual outlines. The lettering sits on a continuous Ice Blue field over solid Marine Blue. The overall size is **94.94 × 27.23 × 3.00 mm**. The loop has a **6.5 mm bore**, **10.5 mm nominal outside diameter**, and **2 mm height**.

[Before and after](Set_11_Winterspell_v07_comparison.png) · [Source overlay](Set_11_Winterspell_v07_source_overlay.png) · [Top view](Set_11_Winterspell_v07_preview.png) · [Isometric view](Set_11_Winterspell_v07_isometric.png)

![Bambu Studio toolpaths at full size with the 0.4 mm nozzle](Set_11_Winterspell_v07_sliced_preview.png)

## Nozzle and scale

Bambu Studio 02.09.01.70 kept every letter separate and connected on every ivory layer in all three slices. The narrowest gap in the model is **0.55 mm between N and T**. The stock slice also produced a continuous backing and ice-blue field.

| A1 slice | Overall width | Loop bore | Estimated time |
| --- | ---: | ---: | ---: |
| 0.4 mm nozzle at 100% XY | 94.94 mm | 6.50 mm | 24 min |
| 0.4 mm nozzle at 110% XY | 104.43 mm | 7.15 mm | 26 min |
| 0.2 mm nozzle at 100% XY | 94.94 mm | 6.50 mm | 76 min |

The 110% test gave the narrowest gap about 0.05 mm more clearance and produced comparable top-layer lettering coverage. The 0.2 mm profile followed some tapered tips more closely, with a small overall coverage gain. The full-size 0.4 mm slice retains the lettering and the collection’s bore size. Results are from slicing and toolpath measurements. A physical print and chain fit remain unverified.

[Geometry](Geometry_v07.json) · [Per-layer validation](Validation_v07.json) · [Raw slicer output](../../../validation/Set_11_Winterspell/v07/)

## Reproduce

Run these commands from the project root with Python, NumPy, Pillow, Shapely, system Cairo/GLU and the local Bambu Studio Flatpak.

```sh
python3 tools/rebuild_set11.py --output-dir /tmp/winterspell-v07-reproduction
python3 tools/validate_set11.py --project /tmp/winterspell-v07-reproduction/Set_11_Winterspell_v07.3mf
```

[Editable trace](../../../tools/set11_clean_artwork.svg) · [Original PNG](../../../collection/v01/Sources/lorcana-keychains/sources/11.png) · [Source snapshot](Source_snapshot.zip) · [Build hashes](Build_manifest.json)
