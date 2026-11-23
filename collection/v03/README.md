# Lorcana keychains v03

Current tools generate and validate 3MF projects only. The STL files and STL
verification results below are retained from the original release.

Local compatibility repair of the supplied **v02** collection, 16 October 2026.
All fourteen native 3MF projects retain the v02 geometry resources byte for byte,
including dimensions, artwork, loop holes, part placement and filament colours.
The supplied v02 model contents are unchanged; each set now has its own folder under `../../sets/`.

## Open a model

In Bambu Studio, choose **File → Open Project** and open the 3MF in `../../sets/<set>/v03/`.
Set 03 retains its `Set_03_Into_the_Inklands_v03_printed.3mf` filename. If prompted, choose to open it as a project.
The A1 0.4 mm, PLA, 0.20 mm settings and the named colour parts are included.
Match the project colours to the spools installed in your AMS Lite, then slice.

If project loading still fails, select **all** STL files from that set's
`v03/STL_fallback` subfolder together and accept importing them as **one object with
multiple parts**. Assign each part to its colour using its filename. Those files
share assembled coordinates; preserve their relative positions and heights.
STL files do not contain filament profiles or colour assignments.

## Repairs

- Added the missing 512 px and 128 px preview images referenced by every project,
  with top views rendered directly from the actual meshes.
- Completed filament/extruder, nozzle, volume and colour metadata for every
  project slot; the original files had single-entry defaults for these lists.
  The A1 uses extruder 1, nozzle index 0 and standard nozzle volume for all colours.
- Corrected the purge-vector length to two entries per filament; retained each
  project's existing colour-specific purge matrix.
- Moved Set 08's purge tower from Y=220 to Y=180 mm. The original position caused
  Bambu's slicer to reject toolpaths outside the build plate with error -104.
- Supplied separate STL colour parts as an alternate import route. Only the
  Set 14 Caramel **STL fallback** has a microscopic geometry adjustment: two
  coincident contour vertices were separated by 0.001 mm to prevent an edge from
  becoming nonmanifold when STL vertices are welded. Its native 3MF is untouched.

The mapping conventions follow Bambu Studio's
[preset handling](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/libslic3r/PresetBundle.cpp).
These metadata inconsistencies are repaired, but the reported graphical opening
failure could not be reproduced without a desktop display or its exact error.

## Verification

- All 14 projects imported and sliced successfully in the installed Bambu Studio
  02.08.02.61 command-line engine.
- Every intended filament channel was used in each slice; none was silently lost.
- All 42 fallback STL parts imported as manifold.
- ZIP integrity, internal relationship targets and unchanged 3MF geometry
  resources were checked.
- No graphical-interface opening test or physical print was performed. The
  relocated command-line executable emitted resource lookup warnings; it used
  the embedded project settings and completed the slice checks successfully.

`Repair_details.json` records source/output hashes and every setting change.
`Validation_v03.json` records actual import/slice results and used filament IDs.
Detailed CLI logs are in `../../validation/<set>/v03/`.

To reproduce locally, use `../../tools/repair_v02.py` and
`../../tools/validate_bambu.py`; they read each set's `v02/` folder and write to its `v03/` folder. The shared
conversation link exposed only its title to the available web tools, so this
repair used the v02 README, source scripts and model contents as its requirements.

The projects remain unsliced. No printer was contacted.
Original artwork and trademarks belong to Disney/Ravensburger.
