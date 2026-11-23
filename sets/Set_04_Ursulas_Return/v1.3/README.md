# Set 04 — Ursula’s Return v1.3

Current tools generate and validate 3MF projects only. The STL files and STL
verification results below are retained from the original release.

Open `Set_04_Ursulas_Return_v1.3.3mf` as a **project** in Bambu Studio,
match the three project colours to your AMS spools, then slice.

The gold and blue letters were traced as clean vector outlines from the local
source artwork. This removes the notches, missing strokes and stray blue
fragments created by extracting colours from shadows and decoration. The purple
backing has a smoother outline and its accidental tiny hole has been filled.
The lettering is a simplified interpretation of the source art.

The attachment loop has both requested reductions:

| Feature | Previous | v1.3 |
| --- | --- | --- |
| Hole diameter | 4.5 mm | 5.5 mm |
| Rim width around the hole | About 3 mm | About 2.5 mm |
| Loop vertical thickness | 2 mm | 1.6 mm |

The thinner loop blends into the full 2 mm backing over a 2.5 mm transition,
before the lettering. Overall dimensions remain **86.465 × 41 × 2.8 mm**.
The native project retains the previous A1, 0.4 mm nozzle, 0.20 mm process and
purple / sunflower yellow / ice blue filament profiles.

`Set_04_Ursulas_Return_v1.3_preview.png` shows the model geometry.
`Set_04_Ursulas_Return_v1.3_sliced_preview.png` composites the actual Bambu
toolpaths at the finished loop, backing and letter heights; it is a top view
rendered from G-code, not a screenshot of Bambu Studio or a prediction of finish.

Bambu Studio 02.08.02.61 imports the project as manifold and slices it
successfully using all three colours, with no plate warnings. All three fallback
STLs also import as manifold. Independent checks found no degenerate triangles,
overlapping gold/blue footprints or unsupported letter footprints. The letter
and backing meshes have positive volume. The loop dimensions were checked in
the exported native geometry. The command-line engine reports missing `/app`
resources because its Flatpak executable is relocated; it uses the embedded
project settings successfully. A graphical opening test and physical print have
not been performed. Ring fit still needs to be checked on a print.

Detailed evidence is in `Geometry_v1.3.json`, `Validation_v1.3.json` and
`../../../validation/Set_04_Ursulas_Return/v1.3/`. The source outlines are in
`../../../tools/set04_clean_letters.svg`; rebuild with `python3 ../../../tools/rebuild_set04.py --version v1.3`
and validate with `../../../tools/validate_set04.py --version v1.3` using Python with Pillow installed.
The original project and printed Set 03 are unchanged.

If an STL import is needed, select all three files in the `STL_fallback`
subfolder together, import them as **one object with multiple parts**, and
assign colours by filename. Preserve their relative positions and heights.

Original artwork and trademarks belong to Disney/Ravensburger.
