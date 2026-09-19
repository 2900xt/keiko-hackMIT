# Buoy hull 3D prints

Hull from the [T3chFlicks Smart Buoy](https://github.com/sk-t3ch/smart-buoy) (`src/buoy/3d/`), re-oriented for printing.

| File | Orientation | Footprint | Height |
|---|---|---|---|
| `top_zup_100pct.stl` | flat cut face on bed, dome up | 188 mm | 114 mm |
| `bottom_zup_100pct.stl` | rounded apex on bed, open end up | 188 mm | 155 mm |
| `top_zup_70pct.stl` / `bottom_zup_70pct.stl` | same | 132 mm | 80 / 109 mm |
| `top.stl` / `bottom.stl` | originals (Y-up) | | |

## Print settings (PLA, 0.4 nozzle)

- 0.28 mm layers, 3 walls, 10% gyroid infill (mesh already has ~4 mm solid walls)
- Top: tree supports, 45° threshold (only inside the dome crown)
- Bottom: tree supports + brim (apex needs support for its bottom ~25 mm)
- Not watertight and doesn't need to be; it's a prop. Original used PETG, 0.3 mm, 4 perimeters, 15%, ~24 h per half on an Ender.

## Time estimates, Bambu/Prusa class

| Scale | Per half | Filament per half |
|---|---|---|
| 100% | 5–7 h | ~250–300 g |
| 70% | 2–2.5 h | ~100 g |

Too big for desktop SLA (188 mm exceeds Form 3/4 beds). Halves mate via a 160 mm lip on the bottom; no snap fit, tape or glue the seam.
