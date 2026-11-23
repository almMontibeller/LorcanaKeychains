# Into the Inkdark v1.0

The [saved 3MF](Set_15_Into_the_Inkdark_v1.0.3mf) uses the user's updated navy (`#042F56`), silver (`#C8C8C8`), and light blue (`#A3D8E1`) palette in slots 1–3, with the Classic wall generator. The previews, validation report, and reproduction command below document the original export and its Arachne slice. The updated palette appears in the [v2.0 comparison](../v2.0/Set_15_Into_the_Inkdark_v2.0_comparison.png).

The keychain measures **75.457 × 30.935 × 2.8 mm**. The backing and eyelet are 2 mm thick. The eyelet has a 6.5 mm through-bore, 10.5 mm nominal outer diameter, and 2 mm nominal rim. The relief follows the angular letter shapes and clear counters in the supplied WebP, using solid colours in place of the artwork’s crystal texture. The continuous backing follows the logo silhouette and supports all 14 raised letters.

- [Top preview](Set_15_Into_the_Inkdark_v1.0_preview.png) and [isometric preview](Set_15_Into_the_Inkdark_v1.0_isometric.png) from the saved 3MF.
- [Matched-scale source overlay](Set_15_Into_the_Inkdark_v1.0_source_overlay.png), [editable SVG](Sources/set15_artwork.svg), and [original WebP](../originals/en_jbs83nhsz6.webp). The orange and pink lines mark the exported backing and letter outlines. This is the first saved version.
- [Actual toolpath preview](Set_15_Into_the_Inkdark_v1.0_sliced_preview.png), [validation report](Validation_v1.0.json), and [slice evidence](Slice/).

The mesh audit found three closed manifold solids, a minimum 0.46 mm space between letters, and a minimum 1.207 mm backing margin. Bambu Studio 2.9.1.70 sliced the project without plate warnings using the A1, 0.4 mm nozzle, 0.20 mm layers, and Arachne. Every letter and the O, D, and A openings survive across all four relief layers. The bore remains open across all ten backing layers. The minimum measured letter core coverage was 99.725% with a 0.075 mm bead-edge tolerance. The toolpath preview shows small fill gaps at some acute corners. Physical print and chain fit remain unverified.

From the collection root, use Python with NumPy, Pillow, and Shapely, system Cairo and GLU, and the local Bambu Studio Flatpak.

```sh
python3 tools/rebuild_set15.py --output-dir /tmp/lorcana-set15-v1.0-reproduction
```

The [source snapshot](Source_snapshot.zip) contains the SVG and Python scripts. The [build manifest](Build_manifest.json) includes their hashes and identifies the saved Hyperia City v1.5 project used for the printer profile.
