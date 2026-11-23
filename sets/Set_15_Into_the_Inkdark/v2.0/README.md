# Into the Inkdark v2.0

Open the [3MF](Set_15_Into_the_Inkdark_v2.0.3mf) as a Bambu Studio project. It uses the saved v1.0 filament assignments in slots 1–3. These are navy (`#042F56`) for the backing, silver (`#C8C8C8`) for **INTO THE**, and light blue (`#A3D8E1`) for **INKDARK**.

The eyelet has a **4 mm neck** measured from its nominal outer tangent to the left edge of the logo body. The neck is 4.5 mm wide and 2 mm thick, with rounded shoulders. The bore stays at 6.5 mm. The eyelet moves 4.708 mm left and the finished keychain measures **80.165 × 30.935 × 2.8 mm**. The original lettering meshes and plate placement carry forward.

- [Top preview](Set_15_Into_the_Inkdark_v2.0_preview.png) and [isometric preview](Set_15_Into_the_Inkdark_v2.0_isometric.png) from the saved 3MF.
- [Matched-scale comparison](Set_15_Into_the_Inkdark_v2.0_comparison.png) with the [user-edited v1.0 3MF](../v1.0/Set_15_Into_the_Inkdark_v1.0.3mf), which is also the build baseline.
- [Actual toolpath preview](Set_15_Into_the_Inkdark_v2.0_sliced_preview.png), [validation report](Validation_v2.0.json), and [slice evidence](Slice/).

Bambu Studio 2.9.1.70 sliced with the saved A1, 0.4 mm nozzle, 0.20 mm layer, and Classic settings without plate warnings. Both neck walls and the open bore are present across all ten backing layers. Each of the four relief layers retains all 14 letters and all three letter openings. The toolpath preview shows small fill gaps at some acute corners. Physical print and chain fit remain unverified.

The [source snapshot](Source_snapshot.zip) includes the exact edited baseline, the editable artwork, and the build scripts. The [build manifest](Build_manifest.json) records their hashes. Extract the snapshot into a fresh directory and run the following command from that directory with Python, NumPy, Pillow, Shapely, Cairo, GLU, and Bambu Studio available.

```sh
python3 tools/rebuild_set15_v2.py --output-dir /tmp/lorcana-inkdark-v2-reproduction
```
