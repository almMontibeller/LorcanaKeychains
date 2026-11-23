# Attack of the Vine v07

Open the [3MF project](Set_13_Attack_of_the_Vine_v07.3mf) in Bambu Studio. Assign purple to filament slot 1 and lime green to slot 2. The lime in the preview is `#B4D83D`.

The redrawn artwork follows the original letter shapes, three counters, curled vine, and exclamation mark. All raised artwork uses solid lime. A smooth purple outline supports the entire title. The keychain measures 67.897 × 40.877 × 2.8 mm, with a 2 mm backing and eyelet height and the original 6.5 mm bore in its original position.

- [Top view](Set_13_Attack_of_the_Vine_v07_preview.png) and [isometric view](Set_13_Attack_of_the_Vine_v07_isometric.png) from the saved model
- [Matched-scale comparison](Set_13_Attack_of_the_Vine_v07_comparison.png) with [v06](../v06/Set_13_Attack_of_the_Vine_v06.3mf), the model used as the build baseline
- [Source overlay](Set_13_Attack_of_the_Vine_v07_source_overlay.png) and [editable artwork](Sources/set13_clean_artwork.svg)
- [Actual sliced toolpaths](Set_13_Attack_of_the_Vine_v07_sliced_preview.png) and [validation report](Validation_v07.json)

Bambu Studio sliced the two-filament project without plate warnings using the A1, 0.4 mm nozzle, 0.20 mm layers, and Arachne. The lime part uses 0.34 mm wall and solid-fill line widths to improve coverage in the small lettering. All 15 letters, the vine curl, and both parts of the exclamation mark are present across all four raised layers. The letter counters and eyelet bore stay open. The minimum measured glyph core coverage is 99.77% with a 0.075 mm bead-edge tolerance. Small gaps near some sharp tips are visible in the toolpath preview. Physical print and chain fit remain unverified.

Build and validate from the repository root with Python, NumPy, Pillow, Shapely, Cairo, GLU, and local Bambu Studio.

```sh
python3 tools/rebuild_set13.py --output-dir /tmp/lorcana-set13-v07-reproduction
python3 tools/validate_set13.py --project /tmp/lorcana-set13-v07-reproduction/Set_13_Attack_of_the_Vine_v07.3mf
```

The [build manifest](Build_manifest.json) identifies the original artwork, template, and input hashes. The [source snapshot](Source_snapshot.zip) includes the saved SVG and scripts. [Slicer log and G-code](../../../validation/Set_13_Attack_of_the_Vine/v07/) are in the validation folder.
