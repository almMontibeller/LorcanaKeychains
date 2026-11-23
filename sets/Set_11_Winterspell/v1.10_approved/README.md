# Winterspell v1.10

Open the [Bambu Studio project](Set_11_Winterspell_v1.10.3mf) at **100% scale** with the **A1 0.4 mm nozzle** and the saved 0.20 mm Arachne process.

Six additional Ice Blue patches follow the frost on both lower W tips, the N curl, both E feet and the shorter L’s crown. Together with the seven v1.9 patches they cover roughly 11% of the letter faces. The project uses three colours and a flat 2 mm Dark Blue backing. Total thickness is 3 mm and the loop bore is 6.5 mm. The online WebP was unavailable during the build, so the archived logo supplied the tracing reference. [Archived logo](../../../collection/v1.0/Sources/lorcana-keychains/sources/11.png)

[Before and after](Set_11_Winterspell_v1.10_comparison.png) · [Top view](Set_11_Winterspell_v1.10_preview.png) · [Isometric view](Set_11_Winterspell_v1.10_isometric.png)

![Actual toolpaths with the 0.4 mm nozzle](Set_11_Winterspell_v1.10_sliced_preview.png)

Bambu Studio verified all eleven letters and thirteen distinct patches at full size without plate warnings. Estimated print time is 23.6 minutes. Physical printing remains unverified. [Geometry](Geometry_v1.10.json) · [Validation](Validation_v1.10.json) · [Raw slice](../../../validation/Set_11_Winterspell/v1.10/)

## Reproduce

Run from the project root with Python, NumPy, Pillow, Shapely, system Cairo/GLU and Bambu Studio Flatpak.

```sh
python3 tools/expand_set11_snow.py --output-dir /tmp/winterspell-v1.10-reproduction
```

[Editable masks](../../../tools/set11_extra_snow_caps.svg) · [Source snapshot](Source_snapshot.zip) · [Build inputs and hashes](Build_manifest.json)
