# Winterspell v1.7

Open the [Bambu Studio project](Set_11_Winterspell_v1.7.3mf) with the **A1 0.4 mm nozzle** at **100% scale**. It uses the 0.20 mm Arachne process and measures **94.94 × 27.23 × 3.00 mm**. The v1.6 lettering and backing meshes carry forward exactly, including the **6.5 mm bore**.

The logo’s blue wash is represented by three solid tones on the same face. Dark Blue anchors the lettering, Marine Blue sweeps through the field, and Ice Blue picks out the lower-left and upper-right edges. Sunflower Yellow gives the lettering a warm gold colour. The linked WebP was unavailable during the build, so the colour layout uses the archived Winterspell artwork as its reference. [Linked artwork](https://i0.wp.com/disneylorcana.com/wp-content/uploads/2026/08/dlc_s11_logo_en.webp?fit=648%2C300&ssl=1) · [Archived artwork](../../../collection/v1.0/Sources/lorcana-keychains/sources/11.png)

| AMS slot | Filament | Manufacturer code |
| --- | --- | --- |
| 1 | PLA Matte Dark Blue | 11602 |
| 2 | PLA Matte Marine Blue | 11600 |
| 3 | PLA Matte Ice Blue | 11601 |
| 4 | PLA Basic Sunflower Yellow | 10402 |

This version adds the Dark Blue spool to the Marine Blue, Ice Blue, and Sunflower Yellow colours used elsewhere in the collection. Preview colours use the manufacturer’s slicer swatches. [Bambu Studio filament colour catalogue](https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json)

[Before and after](Set_11_Winterspell_v1.7_comparison.png) · [Top view](Set_11_Winterspell_v1.7_preview.png) · [Isometric view](Set_11_Winterspell_v1.7_isometric.png)

![Bambu Studio toolpaths at 100% with the 0.4 mm nozzle](Set_11_Winterspell_v1.7_sliced_preview.png)

Bambu Studio 02.09.01.70 sliced the project without plate warnings and estimated **30 minutes**. All four filaments appear in the toolpaths. Both blue field layers retain the intended colour regions, and all eleven gold letters stay separate on every gold layer. Physical colour, print quality and chain fit remain unverified. [Geometry](Geometry_v1.7.json) · [Validation](Validation_v1.7.json) · [Raw slice](../../../validation/Set_11_Winterspell/v1.7/)

## Reproduce

From the project root, run the following with Python, NumPy, Pillow, Shapely, system Cairo/GLU and the local Bambu Studio Flatpak.

```sh
python3 tools/recolor_set11.py --output-dir /tmp/winterspell-v1.7-reproduction
```

[Editable band masks](../../../tools/set11_frost_bands.svg) · [Source snapshot](Source_snapshot.zip) · [Build inputs and hashes](Build_manifest.json)
