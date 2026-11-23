# LorcanaKeychains

3D-printable Disney Lorcana set logos for binder keychains. The collection covers Sets 01–15 and includes multicolour Bambu Studio projects, saved design revisions, previews, and slicer reports.

[Project changelog](CHANGELOG.md)

## Find a print

| Set | Bambu Studio projects |
| --- | --- |
| [01 · The First Chapter](sets/Set_01_The_First_Chapter/) | [v06](sets/Set_01_The_First_Chapter/v06/Set_01_The_First_Chapter_v06.3mf) |
| [02 · Rise of the Floodborn](sets/Set_02_Rise_of_the_Floodborn/) | [v06](sets/Set_02_Rise_of_the_Floodborn/v06/Set_02_Rise_of_the_Floodborn_v06.3mf) |
| [03 · Into the Inklands](sets/Set_03_Into_the_Inklands/) | [v06](sets/Set_03_Into_the_Inklands/v06/Set_03_Into_the_Inklands_v06.3mf) |
| [04 · Ursula’s Return](sets/Set_04_Ursulas_Return/) | [v07](sets/Set_04_Ursulas_Return/v07/Set_04_Ursulas_Return_v07.3mf) |
| [05 · Shimmering Skies](sets/Set_05_Shimmering_Skies/) | [v08_printed](sets/Set_05_Shimmering_Skies/v08_printed/Set_05_Shimmering_Skies_v08_printed.3mf) |
| [06 · Azurite Sea](sets/Set_06_Azurite_Sea/) | [v08_printed](sets/Set_06_Azurite_Sea/v08_printed/Set_06_Azurite_Sea_v08_printed.3mf) |
| [07 · Archazia’s Island](sets/Set_07_Archazias_Island/) | [v07 approved](sets/Set_07_Archazias_Island/v07_approved/Set_07_Archazias_Island_v07.3mf) · [v08 Arachne](sets/Set_07_Archazias_Island/v08/Set_07_Archazias_Island_v08.3mf) |
| [08 · Reign of Jafar](sets/Set_08_Reign_of_Jafar/) | [v11](sets/Set_08_Reign_of_Jafar/v11/Set_08_Reign_of_Jafar_v11.3mf) |
| [09 · Fabled](sets/Set_09_Fabled/) | [v07 approved](sets/Set_09_Fabled/v07_approved/Set_09_Fabled_v07.3mf) · [v08 Arachne](sets/Set_09_Fabled/v08/Set_09_Fabled_v08.3mf) |
| [10 · Whispers in the Well](sets/Set_10_Whispers_in_the_Well/) | [v10](sets/Set_10_Whispers_in_the_Well/v10_approved/Set_10_Whispers_in_the_Well_v10.3mf) |
| [11 · Winterspell](sets/Set_11_Winterspell/) | [v11](sets/Set_11_Winterspell/v11_approved/Set_11_Winterspell_v11.3mf) |
| [12 · Wilds Unknown](sets/Set_12_Wilds_Unknown/) | [v08 green inlays](sets/Set_12_Wilds_Unknown/v08_approved/Set_12_Wilds_Unknown_v08.3mf) · [v07 plain ivory](sets/Set_12_Wilds_Unknown/v07/Set_12_Wilds_Unknown_v07.3mf) |
| [13 · Attack of the Vine](sets/Set_13_Attack_of_the_Vine/) | [v07 solid lime](sets/Set_13_Attack_of_the_Vine/v07_approved/Set_13_Attack_of_the_Vine_v07.3mf) |
| [14 · Hyperia City](sets/Set_14_Hyperia_City/) | [v09](sets/Set_14_Hyperia_City/v09/Set_14_Hyperia_City_v09.3mf) |
| [15 · Into the Inkdark](sets/Set_15_Into_the_Inkdark/) | [v02 with 4 mm neck](sets/Set_15_Into_the_Inkdark/v02/Set_15_Into_the_Inkdark_v02.3mf) |

## Print a keychain

1. Download a `.3mf` from the table and open it **as a project** in Bambu Studio to load the saved filament assignments and print settings.
2. Check the version’s notes for its printer and nozzle profile, previews, and any recorded print feedback. The saved profiles vary by version.
3. Slice the project in Bambu Studio and review the toolpath preview for the lettering and attachment hole.

The shared geometry baseline for Sets 01–14 uses a 2 mm backing and loop, a 6.5 mm hole, a nominal 10.5 mm outer loop diameter, and a 2 mm radial rim. See the [collection dimensions and validation](collection/full_height_narrow_rims/README.md) and the individual version notes for later revisions.

## Version numbers

Revisions use whole numbers with a leading zero for single digits. Folders sort in order as `v08`, `v09`, `v10`, `v11`. Sets 01 and 02 begin at `v02` because that is their first saved release. Status suffixes such as `_printed` and `_approved` are part of the saved paths.

Captured archives, source snapshots, slicer logs, and labels inside saved files retain the names recorded at the time. The [changelog](CHANGELOG.md#version-renumbering) explains the migration and how to reproduce from the original paths.

## Repository layout

- [Sets](sets/) contains the print projects, saved revisions, version notes, previews, and supplied originals where available. Older revisions may also include STL files.
- [Collection](collection/) contains release notes, manifests, preview sheets, and source snapshots. The [file location map](collection/File_locations.json) records the current paths for files named in historical reports.
- [Validation](validation/) contains slicer logs, reports, and G-code evidence from earlier builds.
- [Archives](archives/) contains ZIP packages, including the shared-loop collection.
- [Tools](tools/) contains repair, rebuild, and validation scripts. See the individual version notes for reproduction instructions and the [artwork tracing guide](AGENTS.md) for new designs.
