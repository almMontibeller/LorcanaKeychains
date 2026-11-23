# Winterspell v1.9

Open the [Bambu Studio project](Set_11_Winterspell_v1.9.3mf) at **100% scale** with the **A1 0.4 mm nozzle** and the saved 0.20 mm Arachne process.

The Dark Blue backing and eyelet share a flat **2.0 mm height**. Removing the raised blue field brings the maximum thickness from **3.4 mm to 3.0 mm**. The gold lettering and seven Ice Blue snow patches sit 0.4 mm lower. The footprint is **94.94 × 27.23 mm** and the eyelet bore is **6.5 mm**.

[Isometric comparison](Set_11_Winterspell_v1.9_comparison.png) · [Top view](Set_11_Winterspell_v1.9_preview.png) · [Isometric view](Set_11_Winterspell_v1.9_isometric.png)

![Actual toolpaths at full size with the 0.4 mm nozzle](Set_11_Winterspell_v1.9_sliced_preview.png)

Bambu Studio sliced the project without plate warnings and estimated **23.5 minutes**. The toolpaths end the Dark Blue at 2.0 mm and preserve all eleven letters and seven snow patches. Physical printing and fit remain unverified. [Geometry](Geometry_v1.9.json) · [Validation](Validation_v1.9.json) · [Raw slice](../../../validation/Set_11_Winterspell/v1.9/)

## Reproduce

Run from the project root with Python, NumPy, Pillow, Shapely, system Cairo/GLU and Bambu Studio Flatpak.

```sh
python3 tools/flatten_set11.py --output-dir /tmp/winterspell-v1.9-reproduction
```

[Source snapshot](Source_snapshot.zip) · [Build inputs and hashes](Build_manifest.json)
