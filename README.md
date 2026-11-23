# Lorcana binder keychains

Browse designs in [sets](sets/). Each set contains its available versions,
with the 3MF project, previews, and reports kept together.
New builds generate 3MF projects only. Existing STL fallbacks are historical files.
Version numbers and existing `_printed` filenames are preserved.

| Set | Bambu Studio projects |
| --- | --- |
| [Set 01 The First Chapter](sets/Set_01_The_First_Chapter/) | [Set_01_The_First_Chapter_v1.5.3mf](sets/Set_01_The_First_Chapter/v1.5/Set_01_The_First_Chapter_v1.5.3mf) |
| [Set 02 Rise of the Floodborn](sets/Set_02_Rise_of_the_Floodborn/) | [Set_02_Rise_of_the_Floodborn_v1.5.3mf](sets/Set_02_Rise_of_the_Floodborn/v1.5/Set_02_Rise_of_the_Floodborn_v1.5.3mf) |
| [Set 03 Into the Inklands](sets/Set_03_Into_the_Inklands/) | [Set_03_Into_the_Inklands_v1.5.3mf](sets/Set_03_Into_the_Inklands/v1.5/Set_03_Into_the_Inklands_v1.5.3mf) |
| [Set 04 Ursulas Return](sets/Set_04_Ursulas_Return/) | [Set_04_Ursulas_Return_v1.6.3mf](sets/Set_04_Ursulas_Return/v1.6/Set_04_Ursulas_Return_v1.6.3mf) |
| [Set 05 Shimmering Skies](sets/Set_05_Shimmering_Skies/) | [Set_05_Shimmering_Skies_v1.7_printed.3mf](sets/Set_05_Shimmering_Skies/v1.7_printed/Set_05_Shimmering_Skies_v1.7_printed.3mf) |
| [Set 06 Azurite Sea](sets/Set_06_Azurite_Sea/) | [Set_06_Azurite_Sea_v1.7_printed.3mf](sets/Set_06_Azurite_Sea/v1.7_printed/Set_06_Azurite_Sea_v1.7_printed.3mf) |
| [Set 07 Archazias Island](sets/Set_07_Archazias_Island/) | [v1.6 approved](sets/Set_07_Archazias_Island/v1.6_approved/Set_07_Archazias_Island_v1.6.3mf) · [v1.7 Arachne](sets/Set_07_Archazias_Island/v1.7/Set_07_Archazias_Island_v1.7.3mf) |
| [Set 08 Reign of Jafar](sets/Set_08_Reign_of_Jafar/) | [Set_08_Reign_of_Jafar_v1.10.3mf](sets/Set_08_Reign_of_Jafar/v1.10/Set_08_Reign_of_Jafar_v1.10.3mf) |
| [Set 09 Fabled](sets/Set_09_Fabled/) | [v1.6 approved](sets/Set_09_Fabled/v1.6_approved/Set_09_Fabled_v1.6.3mf) · [v1.7 Arachne](sets/Set_09_Fabled/v1.7/Set_09_Fabled_v1.7.3mf) |
| [Set 10 Whispers in the Well](sets/Set_10_Whispers_in_the_Well/) | [v1.9](sets/Set_10_Whispers_in_the_Well/v1.9/Set_10_Whispers_in_the_Well_v1.9.3mf) |
| [Set 11 Winterspell](sets/Set_11_Winterspell/) | [Set_11_Winterspell_v1.10.3mf](sets/Set_11_Winterspell/v1.10/Set_11_Winterspell_v1.10.3mf) |
| [Set 12 Wilds Unknown](sets/Set_12_Wilds_Unknown/) | [v1.7 green inlays](sets/Set_12_Wilds_Unknown/v1.7/Set_12_Wilds_Unknown_v1.7.3mf) · [v1.6 plain ivory](sets/Set_12_Wilds_Unknown/v1.6/Set_12_Wilds_Unknown_v1.6.3mf) |
| [Set 13 Attack of the Vine](sets/Set_13_Attack_of_the_Vine/) | [v1.6 solid lime](sets/Set_13_Attack_of_the_Vine/v1.6/Set_13_Attack_of_the_Vine_v1.6.3mf) |
| [Set 14 Hyperia City](sets/Set_14_Hyperia_City/) | [Set_14_Hyperia_City_v1.8.3mf](sets/Set_14_Hyperia_City/v1.8/Set_14_Hyperia_City_v1.8.3mf) |
| [Set 15 Into the Inkdark](sets/Set_15_Into_the_Inkdark/) | [v2.0 with 4 mm neck](sets/Set_15_Into_the_Inkdark/v2.0/Set_15_Into_the_Inkdark_v2.0.3mf) |

The latest projects have **2 mm loops and nominal backing height**, **6.5 mm holes**, **10.5 mm nominal outer diameters**, and **2 mm radial rims**. See [shared dimensions and collection validation](collection/full_height_narrow_rims/README.md); Set 08's background engravings are described below.

For example, `sets/Set_04_Ursulas_Return/` contains `v1.0/` through `v1.6/`.
Open the 3MF as a project in Bambu Studio to retain colour assignments and settings.

Follow the [first-pass tracing instructions](AGENTS.md) when preparing new artwork.

For Sets 07, 09, and 10, the v1.7 print projects use the same A1 / 0.4 mm / 0.20 mm Arachne process as the latest Set 01–06 files. These revisions restore the original build profiles while preserving the saved v1.6 mesh, placement, and filament slot assignments. Each v1.7 folder includes a fresh slice and toolpath report. Sets 07 and 09 also have their approved v1.6 projects with the saved Classic settings.

- `collection/`: collection-wide release notes, manifests, reports, preview sheets, and historical source snapshots.
- `validation/<set>/<version>/`: existing slicer logs and G-code evidence.
- `archives/`: historical ZIP packages and the current shared-loop project bundle.
- `tools/`: current repair, rebuild, and validation scripts using the set-based paths.
- A set’s `originals/` folder holds supplied originals and original source material when available.

Reproduce the shared geometry baseline from the project root:

```sh
python3 tools/full_height_narrow_rims.py
```

Requires NumPy, Pillow, the system Cairo/GLU libraries and local Bambu Studio. Older repair and rebuild scripts in `tools/` reproduce historical revisions. Set 05 retains its continuous underline and reinforced stars.

Set 06's latest [v1.7 artwork refinement](sets/Set_06_Azurite_Sea/v1.7_printed/README.md) retains the restored letter counters, separated letters and clean wave crests from v1.6, with fuller blue wave bodies. It retains the shared loop dimensions. Reproduce this revision after the collection build:

```sh
python3 tools/rebuild_set06.py
python3 tools/validate_set06.py
```

Set 07's [v1.6 artwork rebuild](sets/Set_07_Archazias_Island/v1.6_approved/README.md) restores the feathered light green frame with caramel trim, a shaped owl face with engraved brow/beak and ivory eyes, and smooth source-traced lettering. It uses four colours and preserves the shared backing and loop dimensions. Reproduce after the collection build:

```sh
python3 tools/rebuild_set07.py
python3 tools/validate_set07.py
```

Set 08’s [v1.10 print project](sets/Set_08_Reign_of_Jafar/v1.10/README.md) closes the red-letter gaps in the slicer audit through a 0.33 mm local red-fill width. The A1 / 0.4 mm process and v1.9 artwork carry over.

Set 08's [v1.9 print refinement](sets/Set_08_Reign_of_Jafar/v1.9/README.md) gives the red eyes fuller rounded tips, strengthens the red letter fills, and extends the five engraved cobra-hood bands to the inner rim. It retains the plain orange cobra face, continuous orange rim and original four filament slots. The maximum height is now 3 mm; the shared loop dimensions and 1.6 mm backing floor beneath the engravings are retained. Bambu Studio slices successfully with no plate warnings; the strict toolpath audit still reports two small residual gaps, documented in the revision notes. Reproduce after the collection build:

```sh
python3 tools/rebuild_set08.py
python3 tools/rebuild_set08_v1_7.py
python3 tools/rebuild_set08_v1_8.py
python3 tools/rebuild_set08_v1_9.py
```

`python3 tools/validate_set08_v1_9.py` runs the strict audit and currently exits with the documented residual-gap assertion. The supplied v1.9 project is preserved as reviewed.

Set 09's [v1.6 artwork and background rebuild](sets/Set_09_Fabled/v1.6_approved/README.md) replaces the rough tracing with smooth lettering, continuous gold outlines and complete book ornaments. A solid Marine Blue background connects and supports the entire design. It retains the three original filament slots, 2 mm backing/loop, 6.5 mm hole and 3 mm maximum height. Build and validate this revision separately from the historical collection scripts:

```sh
python3 tools/rebuild_set09.py --output-dir /tmp/lorcana-set09-v1.6-reproduction
python3 tools/validate_set09.py --project /tmp/lorcana-set09-v1.6-reproduction/Set_09_Fabled_v1.6.3mf
```

Historical manifests, reports, and logs retain their original recorded filenames
and paths. [File_locations.json](collection/File_locations.json) maps the previous
file locations to the current layout and records their hashes before reorganization.

Set 10’s [v1.9 project](sets/Set_10_Whispers_in_the_Well/v1.9/README.md) trims the charcoal backing below WELL. Set 10’s [v1.8 project](sets/Set_10_Whispers_in_the_Well/v1.8/README.md) removes the grey underline below WELL and carries forward the v1.7 Arachne profile.

Set 10's [v1.6 background and contour rebuild](sets/Set_10_Whispers_in_the_Well/v1.6/README.md) adds a continuous Charcoal field beneath all three lines of lettering, with smooth source-traced curves, a complete gold upper wisp and a continuous grey underline. It retains the original three filament slots, 2 mm backing/loop, 6.5 mm hole and 2.8 mm overall height. [Compare v1.5 and v1.6](sets/Set_10_Whispers_in_the_Well/v1.6/Set_10_Whispers_in_the_Well_v1.6_comparison.png). Build and validate separately from the historical collection scripts:

```sh
python3 tools/rebuild_set10.py --output-dir /tmp/lorcana-set10-v1.6-reproduction
python3 tools/validate_set10.py --project /tmp/lorcana-set10-v1.6-reproduction/Set_10_Whispers_in_the_Well_v1.6.3mf
```

Set 11’s [v1.6 retrace](sets/Set_11_Winterspell/v1.6/README.md) redraws all eleven letters on a solid backing and continuous Ice Blue field. The stock A1 0.4 mm slice retains every letter at full size. The version notes compare the toolpaths with a 0.2 mm nozzle and a 110% XY scale-up.

Set 11’s [v1.7 colour revision](sets/Set_11_Winterspell/v1.7/README.md) pairs gold-toned Sunflower Yellow lettering with three blue tones and keeps the v1.6 letter shapes. It slices at 100% with the 0.4 mm nozzle and uses four filament slots.

Set 11’s [v1.8 snow-cap revision](sets/Set_11_Winterspell/v1.8/README.md) uses a single Dark Blue background, gold lettering and seven Ice Blue patches. The three-filament project slices at full size with the 0.4 mm nozzle.

Set 11’s [v1.9 flat backing](sets/Set_11_Winterspell/v1.9/README.md) places the gold lettering and Ice Blue snow patches directly over the 2 mm Dark Blue backing. Overall thickness is 3 mm.

Set 11’s [v1.10 snow-patch revision](sets/Set_11_Winterspell/v1.10/README.md) adds six Ice Blue patches to the flat-backed design. The 0.4 mm slice retains all thirteen patches at full size.

Set 14’s [v1.8 project](sets/Set_14_Hyperia_City/v1.8/README.md) adds tapered Ice Blue side accents on Ivory White letters over Cocoa Brown padding. The full-size A1 0.4 mm slice retains all 18 blue accents, the letter openings, and the 6.5 mm attachment bore.
