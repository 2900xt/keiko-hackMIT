# Buoy v2 (Charles Ear)

Parametric OpenSCAD buoy for one ESP32-S3 DevKitC + USB power bank, with a piezo hydrophone on a tether below.
Designed for two Bambu/Prusa-class PLA printers, one plate each. Reviewed adversarially by OpenAI Codex
(round-1 reports in `codex_*.md`, round 2 in `codex_round2.md`).

## Parts

| File | Print orientation | Size | PLA | Est. time (0.28 mm, Bambu class) |
|---|---|---|---|---|
| `hull.stl` | as exported, floor on bed | 130 mm OD x 100 mm | ~160 g | 3.5–4.5 h (plate A) |
| `lid.stl` | as exported, top face on bed | 139 mm OD x 19 mm | ~88 g | ~2 h (plate B) |
| `head.stl` | as exported, floor on bed | 44 mm OD x 72 mm | ~50 g | ~1.2 h (plate B) |

Regenerate: `openscad --backend=manifold -o hull.stl -D 'part="hull"' buoy_v2.scad` (parts: hull, lid, head, plate_b, all).

## Slicer settings

- PLA, 0.4 nozzle, 0.28 mm layers. **Walls: 5 lines** (2.0 mm hull wall is solid perimeters, no infill in the shell). Floor 6 layers.
- No supports anywhere. Brim on the hull (the two lugs are the widest point).
- Hull is 130 mm across plus 22 mm of lugs; needs a 160 mm bed (fine on 220/250/256 mm beds).
- Lid prints upside down. The internal thread groove is left-handed in the file so it becomes right-handed once flipped onto the hull.

## Assembly

1. **Gasket:** lay a 2 mm rubber cord or two stacked rubber bands in the groove on the neck rim. Screw the lid on 2 turns. Wrap the lid/hull seam with waterproof duct tape before launch (the thread is not a seal; the gasket + tape are).
2. **Power bank** (5,000 mAh, ~95 x 62 x 15 mm, ~115 g; edit the payload block if yours differs) lies flat on the floor between the two rails. **ESP32** stands vertical in the side pocket, antenna end UP, rubber band to the rail. Its antenna sits ~23 mm above the design waterline.
3. **Cable gland:** the hydrophone cable passes through the 3.5 mm hole in the lid. Slide marine adhesive heat shrink over the cable, push it down over the 8 mm boss on the inside of the lid, shrink. Do this with the cable UNTERMINATED, then connect inside. Leave a 120 mm service loop inside.
4. **Bridle:** one line through each bottom lug, equal lengths, joined to a single ring 100–150 mm below the hull. Hang the hydrophone head from that ring. Moor to the same ring, never to the hull top.
5. **Head:** tape 1" fender washers into a stack, drop into the floor pocket. Sealed piezo (balloon/oil or coating, ~24 mm) sits on the three posts under the three tabs. Cable up through the apex hole; zip tie across the two parallel slots for strain relief. Drop line through the eye plate.

## Design numbers (from the file's echo; edit the payload block to match your parts)

Total afloat ~545 g with a 115 g 5,000 mAh bank and 100 g effective tether load. Draft 41 mm, freeboard 45 mm to the neck shoulder and 59 mm to the rim, GM +7 mm before the bridle's pendulum effect (the tether load hanging from a ring 100-150 mm below the hull adds most of the real righting moment). ESP32 antenna top ~31 mm above the waterline.

## Known limits

- Freeboard to the neck is 45 mm, just under the 50 mm the reviewers wanted. Tape the seam. Raising `hull_h` to 110 adds ~8% hull mass if you want more margin.
- Static GM is small (+7 mm). Keep the bridle ring 100-150 mm below the hull with the head hanging from it; that pendulum is what keeps it upright in a wake.
- Printed PLA threads with a rubber-band gasket are splash-tight, not dive-tight. Dunk-test the empty sealed hull for 30 min before loading electronics.
- USB-C from the bank to the ESP32 needs a short right-angle or thin flexible cable; test-fit before printing the second hull.
