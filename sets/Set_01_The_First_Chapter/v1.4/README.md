# The First Chapter v1.4

Open [Set_01_The_First_Chapter_v1.4.3mf](Set_01_The_First_Chapter_v1.4.3mf) as a project in Bambu Studio.

The attachment loop is **1.6 mm thick** and joins the original **2 mm backing** with a flat vertical step. The step is positioned before the artwork so it remains fully supported. The 5.5 mm bore, nominal 10.5 mm outer diameter, backing footprint, colours, placement and print profiles are retained.

Bambu Studio imports and slices successfully, uses every intended filament and reports no plate warnings. Mesh checks confirm a closed manifold backing with no degenerate triangles. Actual G-code confirms the loop ends at Z=1.6 mm. Physical printing and chain fit have not been tested.

![Actual sliced toolpaths](Set_01_The_First_Chapter_v1.4_sliced_preview.png)

[Validation_v1.4.json](Validation_v1.4.json) contains the geometry, toolpath checks and slicer results. Reproduce from the repository root with `python3 tools/refine_loops_and_underline.py`, using NumPy, Pillow and local Bambu Studio.
