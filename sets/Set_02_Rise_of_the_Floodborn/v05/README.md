# Rise of the Floodborn v05

Open [Set_02_Rise_of_the_Floodborn_v05.3mf](Set_02_Rise_of_the_Floodborn_v05.3mf) as a project in Bambu Studio.

The attachment loop is **1.6 mm thick** and joins the original **2 mm backing** with a flat vertical step. The step is positioned before the artwork so it remains fully supported. The 5.5 mm bore, nominal 10.5 mm outer diameter, backing footprint, colours, placement and print profiles are retained.

Bambu Studio imports and slices successfully, uses every intended filament and reports no plate warnings. Mesh checks confirm a closed manifold backing with no degenerate triangles. Actual G-code confirms the loop ends at Z=1.6 mm. Physical printing and chain fit have not been tested.

![Actual sliced toolpaths](Set_02_Rise_of_the_Floodborn_v05_sliced_preview.png)

[Validation_v05.json](Validation_v05.json) contains the geometry, toolpath checks and slicer results. Reproduce from the repository root with `python3 tools/refine_loops_and_underline.py`, using NumPy, Pillow and local Bambu Studio.
