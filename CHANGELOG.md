# Project changelog

Collection-wide changes and selected set revisions. The linked version notes include previews and slicer evidence where available. For downloads and printing instructions, see the [project README](README.md).

## Version renumbering

- Revisions now use whole-number names padded to two digits. The former `v1.0` is `v01`, `v1.1` is `v02`, and `v1.10` is `v11`. Into the Inkdark’s second saved design is `v02`. The saved Ursula’s Return model previously marked `v1.4.1_printed` is `v05_printed`, matching its folder.
- The migration renamed saved files and updated current links, build scripts, and indexes. The model files, historical preview images, logs, and archived source contents retain their original bytes. Old paths and hash records can be read in the [pre-migration checkout](https://github.com/almMontibeller/LorcanaKeychains/tree/fd8d8fd483aa5cd494f45dba7a5dfcd872066260). Use that commit in a disposable checkout for exact source snapshots that rely on the original paths.

## Collection-wide changes

- The [full-height narrow-rim baseline](collection/full_height_narrow_rims/README.md) brought the loops on Sets 01–14 level with the 2 mm backing, with a 6.5 mm hole, a nominal 10.5 mm outer diameter, and a 2 mm radial rim. Set 05 retained its continuous underline and reinforced stars.
- Sets 07, 09, and 10 gained v08 Bambu Studio projects using the same A1, 0.4 mm nozzle, and 0.20 mm Arachne profile as the Set 01–06 projects listed at the time. The profile update kept the saved v07 meshes, placement, and filament slot assignments. Each v08 has a fresh slice and toolpath report. Sets 07 and 09 also retain the approved v07 projects with Classic settings. [Set 07 v08](sets/Set_07_Archazias_Island/v08/README.md) · [Set 09 v08](sets/Set_09_Fabled/v08/README.md) · [Set 10 v08](sets/Set_10_Whispers_in_the_Well/v08/README.md)
- Saved versions moved into their set folders. The [file location map](collection/File_locations.json) connects recorded paths to the reorganized files and includes their pre-move hashes.

The shared baseline was built with `python3 tools/full_height_narrow_rims.py` and requires NumPy, Pillow, system Cairo and GLU libraries, and a local Bambu Studio installation. Run historical builds in a disposable checkout. The [baseline generator](tools/full_height_narrow_rims.py) writes to fixed model, report, and README paths.

## Set 06 · Azurite Sea

- **v08** gives the blue wave bodies a fuller shape. It keeps the restored letter counters, separated letters, and clean wave crests from v07, along with the shared loop dimensions. The version notes record the rebuild and validation commands used after the collection build. [v08 notes](sets/Set_06_Azurite_Sea/v08_printed/README.md)

## Set 07 · Archazia’s Island

- **v07** restores the feathered light green frame with caramel trim, a shaped owl face with engraved brow and beak, ivory eyes, and smooth source-traced lettering. It uses four colours and keeps the shared backing and loop dimensions. The version notes record the build and validation commands. [v07 notes](sets/Set_07_Archazias_Island/v07_approved/README.md)

## Set 08 · Reign of Jafar

- **v11** closes the red-letter gaps found by the slicer audit with a 0.33 mm local red-fill width. It keeps the v10 artwork and A1 / 0.4 mm process. [v11 notes](sets/Set_08_Reign_of_Jafar/v11/README.md)
- **v10** gives the red eyes fuller rounded tips, strengthens the red letter fills, and extends five engraved cobra-hood bands to the inner rim. It keeps the plain orange cobra face, continuous orange rim, original four filament slots, and shared loop dimensions. Maximum height is 3 mm, with a 1.6 mm backing floor beneath the engravings. Bambu Studio sliced without plate warnings. The strict audit (`python3 tools/validate_set08_v10.py`) reports two small residual gaps and exits with an assertion. [v10 notes](sets/Set_08_Reign_of_Jafar/v10/README.md)

The historical v10 build ran these scripts after the shared collection build in the following order.

`tools/rebuild_set08.py` → `tools/rebuild_set08_v08.py` → `tools/rebuild_set08_v09.py` → `tools/rebuild_set08_v10.py`

## Set 09 · Fabled

- **v07** rebuilds the lettering with smooth curves, continuous gold outlines, and complete book ornaments. A solid Marine Blue background supports the entire design. It keeps the three filament slots, 2 mm backing and loop, 6.5 mm hole, and 3 mm maximum height. It has a standalone build and validation procedure. [v07 notes](sets/Set_09_Fabled/v07_approved/README.md) · [Set changelog](sets/Set_09_Fabled/CHANGELOG.md)

## Set 10 · Whispers in the Well

- **v10** trims the charcoal backing below WELL. [v10 notes](sets/Set_10_Whispers_in_the_Well/v10_approved/README.md)
- **v09** removes the grey underline below WELL and carries forward the v08 Arachne profile. [v09 notes](sets/Set_10_Whispers_in_the_Well/v09/README.md)
- **v07** adds a continuous Charcoal field beneath all three lines of lettering, smooth source-traced curves, a complete gold upper wisp, and a continuous grey underline. It keeps the original three filament slots, 2 mm backing and loop, 6.5 mm hole, and 2.8 mm overall height. It has a standalone build and validation procedure. [v07 notes](sets/Set_10_Whispers_in_the_Well/v07/README.md) · [v06 to v07 comparison](sets/Set_10_Whispers_in_the_Well/v07/Set_10_Whispers_in_the_Well_v07_comparison.png) · [Set changelog](sets/Set_10_Whispers_in_the_Well/CHANGELOG.md)

## Set 11 · Winterspell

- **v11** adds six Ice Blue patches to the flat-backed design. All thirteen patches survive a full-size 0.4 mm slice. [v11 notes](sets/Set_11_Winterspell/v11_approved/README.md) · [Set changelog](sets/Set_11_Winterspell/CHANGELOG.md)
- **v10** places the gold lettering and Ice Blue snow patches directly on the 2 mm Dark Blue backing, for an overall thickness of 3 mm. [v10 notes](sets/Set_11_Winterspell/v10/README.md)
- **v09** uses one Dark Blue background, gold lettering, and seven Ice Blue patches. The three-filament project slices at full size with the 0.4 mm nozzle. [v09 notes](sets/Set_11_Winterspell/v09/README.md)
- **v08** pairs gold-toned Sunflower Yellow lettering with three blue tones and keeps the v07 letter shapes. The four-filament project slices at full size with the 0.4 mm nozzle. [v08 notes](sets/Set_11_Winterspell/v08/README.md)
- **v07** redraws all eleven letters on a solid backing and continuous Ice Blue field. The stock A1 0.4 mm slice retains every letter at full size. The version notes compare the toolpaths with a 0.2 mm nozzle and with a 110% XY scale-up. [v07 notes](sets/Set_11_Winterspell/v07/README.md)

## Set 14 · Hyperia City

- **v09** adds tapered Ice Blue side accents on Ivory White letters over Cocoa Brown padding. The full-size A1 0.4 mm slice retains all 18 blue accents, the letter openings, and the 6.5 mm attachment bore. [v09 notes](sets/Set_14_Hyperia_City/v09/README.md) · [Set changelog](sets/Set_14_Hyperia_City/CHANGELOG.md)
