# Hyperia City v06

Open [Set_14_Hyperia_City_v06.3mf](Set_14_Hyperia_City_v06.3mf) as a project in Bambu Studio.

The loop and backing now share the same flat **2 mm height**. The ring is thinner in the XY plane: a **6.5 mm hole** inside the existing **10.5 mm nominal outer diameter** gives a **2 mm nominal radial rim**, reduced from 2.5 mm. The bore centre and every other backing contour are retained.

The colour meshes, artwork, placement and filament/process settings are exactly preserved. Bambu imports and slices successfully, uses all intended colours, and reports no plate warnings. The rebuilt backing is a closed manifold solid with no degenerate triangles. Actual toolpaths confirm that the loop reaches the same 2 mm layer as the backing.

![Actual sliced toolpaths](Set_14_Hyperia_City_v06_sliced_preview.png)

[Validation_v06.json](Validation_v06.json) records the checks. Physical printing and chain fit have not been tested. Reproduce the current collection from the project root with `python3 tools/full_height_narrow_rims.py`, using NumPy, Pillow and local Bambu Studio.
