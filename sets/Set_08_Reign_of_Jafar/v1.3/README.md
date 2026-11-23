# Reign of Jafar v1.3

Open [Set_08_Reign_of_Jafar_v1.3.3mf](Set_08_Reign_of_Jafar_v1.3.3mf) as a project in Bambu Studio.

The attachment hole matches Set 04: **5.5 mm bore**, **10.5 mm nominal outer diameter**, and **2.5 mm nominal rim**. The original 2 mm loop and backing thickness is retained. Only the hole is enlarged; all other backing contours, artwork, colours, placement and process settings are preserved.

Bambu Studio 02.08.02.61 imports and slices the project successfully, uses all intended filaments and reports no plate warnings. The rebuilt backing is a closed manifold solid without degenerate triangles. Source colour meshes are preserved exactly, including any pre-existing mesh details. Physical printing and ring fit have not been tested.

![Updated project](Set_08_Reign_of_Jafar_v1.3_preview.png)

Geometry: [Geometry_v1.3.json](Geometry_v1.3.json). Validation: [Validation_v1.3.json](Validation_v1.3.json).

Rebuild and validate all thirteen diameter revisions from the repository root with Python, NumPy and Pillow:

```sh
python3 tools/standardize_loop_diameters.py
```
