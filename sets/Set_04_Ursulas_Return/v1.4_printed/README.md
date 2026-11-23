# Set 04 — Ursula’s Return v1.4

Current tools generate and validate 3MF projects only. The STL files and STL
verification results below are retained from the original release.

Open `Set_04_Ursulas_Return_v1.4.1_printed.3mf` as a **project** in Bambu Studio,
match the three colours to your AMS spools, and slice.

This revision changes the two marked areas:

- The gold R’s left leg is widened from about 1.6 mm to 2.7 mm.
- The gold A’s upper left stroke is redrawn to blend into the flourish,
  removing its taper to a hairline beside the inner opening. That part of the
  stroke now measures at least 1.3 mm at the sampled cross sections.

The purple backing, attachment loop and blue RETURN meshes are exactly the same
as v1.3. Every other letter outline is unchanged. The loop retains its 5.5 mm
hole, approximately 2.5 mm rim, and 1.6 mm vertical thickness, blending into the
2 mm backing. Overall dimensions remain 86.465 × 41 × 2.8 mm. A1 / 0.4 mm /
0.20 mm project settings and colour assignments are retained.

`Set_04_Ursulas_Return_v1.4_sliced_preview.png` shows a top view rendered from
the actual Bambu toolpaths at the completed loop, backing and lettering layers.
`Set_04_Ursulas_Return_v1.4_preview.png` shows the mesh geometry.

The project slices successfully in Bambu Studio 02.08.02.61, uses all three
filaments and has no plate warnings. All three colour meshes and fallback STLs
import as manifold. Footprint checks found no unsupported lettering or gold/blue
overlap. The mesh check found no degenerate triangles. Physical printing and
ring fit have not been tested. The relocated CLI reports missing `/app` preset
resources and successfully uses the embedded project settings.

Evidence is in `Validation_v1.4.json`, `Geometry_v1.4.json` and
`../../../validation/Set_04_Ursulas_Return/v1.4/`. Rebuild with
`python3 ../../../tools/rebuild_set04.py --version v1.4` and validate with
`../../../tools/validate_set04.py --version v1.4` using Python with Pillow installed.
The editable artwork is `../../../tools/set04_clean_letters_v1_4.svg`.

For fallback STL import, select the three files together and import as one
object with multiple parts. Preserve their relative positions and heights,
then assign colours by filename.

Original artwork and trademarks belong to Disney/Ravensburger.
