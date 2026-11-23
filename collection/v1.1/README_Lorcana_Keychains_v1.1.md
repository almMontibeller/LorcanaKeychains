# Lorcana binder keychains — v1.1

The designs and individual previews are now in `../../sets/<set>/v1.1/`.
This folder retains collection-wide documentation, reports, and historical source scripts.
The release notes below describe the original release.

14 English set labels, traced from official Disney/Ravensburger artwork. Personal binder identification. Earlier versions are retained separately.

## Changes from v1.0

- Added sets 1 and 2.
- Files now pass through Bambu Studio 02.08.02.61 native project export, then are reimported by its CLI.
- Embedded A1 0.4 mm printer, 0.20 mm process, PLA profiles, filament display colours and per-part extruder assignments.
- Set 3: replaced the old horizontal crop split with complete letter shapes and a continuous 0.65 mm blue border.
- Flattened gradient fragments into solid colour regions; simplified fine highlights and the Archazia frame.

## Opening and printing

1. Extract the outer ZIP fully into a folder. Do not extract the individual .3mf files: a .3mf is itself a ZIP-based project.
2. In Bambu Studio use File → Open Project and select one individual .3mf. Choose Open as project if asked. Importing geometry alone can discard the project colour assignments.
3. Filaments and part colours are already assigned. Confirm your connected AMS Lite slots match the project colours before printing; the project cannot know which spool is physically in each slot.
4. Baseline: Bambu Lab A1, 0.4 mm nozzle, PLA, textured PEI, 0.20 mm layers, Arachne walls, 3 walls, 5 top/bottom layers, 15% infill. Select your actual nozzle/plate if different.
5. Flat back down, artwork up, supports disabled. Inspect the sliced preview for any fine detail omitted by your nozzle. A 0.2 mm nozzle is optional for finer lettering; its profile must be selected separately.
6. Projects are unsliced and contain no print-ready G-code. They must be sliced before printing.

The loop has a 4.5 mm through-hole. Backing is 2 mm thick, with 0.4–1 mm relief. All colour meshes were checked as watertight and the assembled body as one connected solid. Each final project was imported by Bambu Studio; filament colours and per-part extruder IDs were verified after native export. Set 3 was additionally sliced successfully with three filament channels. None has been physically test-printed.

## Filament assignments

Colours are approximations for the Bambu filaments in your purchase inventory. Slots below are local to each project, in order.

| Set | Title | Dimensions (mm) | Slots 1–4 |
|---|---|---|---|
| 01 | The First Chapter | 91.74 × 24.6 × 2.8 | Purple → Ivory White |
| 02 | Rise of the Floodborn | 95.32 × 32.81 × 2.8 | Marine Blue → Ice Blue → Ivory White |
| 03 | Into the Inklands | 93.1 × 39.7 × 3.0 | Cocoa Brown → Ice Blue → Sunflower Yellow |
| 04 | Ursula’s Return | 86.47 × 41.0 × 2.8 | Purple → Sunflower Yellow → Ice Blue |
| 05 | Shimmering Skies | 94.94 × 38.17 × 3.0 | Purple → Red → Ivory White |
| 06 | Azurite Sea | 79.26 × 41.28 × 2.8 | Marine Blue → Ice Blue → Sunflower Yellow |
| 07 | Archazia’s Island | 80.53 × 40.81 × 3.0 | Dark Green → Caramel → Ivory White |
| 08 | Reign of Jafar | 71.9 × 41.54 × 2.8 | Charcoal → Pumpkin Orange → Sunflower Yellow → Red |
| 09 | Fabled | 94.69 × 33.38 × 3.0 | Marine Blue → Sunflower Yellow → Purple |
| 10 | Whispers in the Well | 55.78 × 39.38 × 2.8 | Charcoal → Ash Gray → Sunflower Yellow |
| 11 | Winterspell | 95.01 × 26.8 × 3.0 | Marine Blue → Ice Blue → Ivory White |
| 12 | Wilds Unknown | 82.58 × 40.91 × 3.0 | Cocoa Brown → Dark Green → Ivory White |
| 13 | Attack of the Vine! | 68.01 × 40.9 × 2.8 | Purple → Mistletoe Green → Sunflower Yellow |
| 14 | Hyperia City | 71.92 × 40.79 × 3.0 | Cocoa Brown → Caramel → Ivory White |

## Official artwork sources

Set 1: https://www.disneylorcana.com/en-US/product
Set 2: https://www.disneylorcana.com/en-US/product/rise-of-the-floodborn
Set 3: https://www.disneylorcana.com/en-US/product-s3
Set 4: https://www.disneylorcana.com/en-US/product/ursulas-return
Set 5: https://www.disneylorcana.com/en-US/product/shimmering-skies
Set 6: https://www.disneylorcana.com/en-US/product/azurite-sea
Set 7: https://www.disneylorcana.com/en-US/product/archazias-island
Set 8: https://www.disneylorcana.com/en-US/product/reign-of-jafar
Set 9: https://www.disneylorcana.com/en-US/product/fabled
Set 10: https://www.disneylorcana.com/en-US/product/whispers
Set 11: https://www.disneylorcana.com/en-US/product/winterspell
Set 12: https://www.disneylorcana.com/en-US/product/wilds-unknown
Set 13: https://www.disneylorcana.com/en-US/product/attack-of-the-vine
Set 14: https://www.disneylorcana.com/en-US/product/hyperia-city

Original artwork/trademarks © Disney/Ravensburger. Gradients, textures and fine decoration are intentionally simplified for FDM.
