1. **Lid thread wrong-handed after flip — NOT FIXED.** Hull uses `hand=1` at [line 86](./buoy_v2.scad:86); lid uses `hand=-1` at [line 116](./buoy_v2.scad:116). A 180° rotation about X is a proper rotation, not a mirror: it reverses both axial direction and angular coordinate, preserving screw handedness. The lid’s resulting global helix is still opposite the hull’s, so the threads do not mate.

2. **Gasket groove through the 2.4 mm neck wall — FIXED.** The neck cavity is radius `65 - 2 - 2.4 = 60.6 mm` ([line 91](./buoy_v2.scad:91)). The groove runs from radius `61.8` to `63.8 mm` ([lines 93–95](./buoy_v2.scad:93)), leaving 1.2 mm both inside and outside. It is at z=99.1–100 mm, inside the land.

3. **Piezo posts and head eye were floating islands — FIXED geometrically.** Posts overlap the sinker ring: post centers are r=13 mm, with radius 2.25 mm, while the ring is r=12.75–14.35 mm ([lines 137, 156, 159](./buoy_v2.scad:137)). They also have radial ribs ([line 160](./buoy_v2.scad:160)). The eye plate overlaps the roof by 0.5 mm at z≈55.5–56 mm ([lines 165–168](./buoy_v2.scad:165)). It introduces a new blocking interference below.

4. **60 mm lid-panel bridge — FIXED.** This is a 1.6 mm-wide, 0.6 mm-deep engraved ring, not a recessed panel ([lines 37, 120–124](./buoy_v2.scad:37)).

5. **Upper mooring lug unprintable / capsize lever — FIXED.** Only the two bottom `eye_lug(0, …)` calls remain ([line 87](./buoy_v2.scad:87)); no upper lug is present.

6. **Bottom-lug holes cut into cavity — FIXED.** Lug centers are at ±67 mm ([line 73](./buoy_v2.scad:73)), while the hull outer radius is 65 mm. Hole centers are ±70.15 mm and their inner edges are ±66.15 mm ([line 76](./buoy_v2.scad:76)), at least 1.15 mm outside the hull shell.

7. **Negative GM with vertical power bank — NOT FIXED.** The preview places the bank as `cube([bank_l, bank_t, bank_w])` ([line 177](./buoy_v2.scad:177)): 100 × 25 mm footprint and **65 mm vertical height**. It is on its side, not flat. The stability formula nevertheless assigns its CG using `bank_t/2 = 12.5 mm` ([line 189](./buoy_v2.scad:189)), rather than the modeled `bank_w/2 = 32.5 mm`.

8. **ESP32 antenna too close to waterline — FIXED, under the stated mass model.** ESP top is z=72.4 mm ([line 178](./buoy_v2.scad:178)). Calculated draft is 49.65 mm, so the quoted antenna clearance is 22.75 mm.

9. **Bank slot zero clearance — FIXED.** `slot=27 mm` ([line 82](./buoy_v2.scad:82)); rail inner faces are y=±13.5 mm ([line 101](./buoy_v2.scad:101)). A 25 mm bank spans y=±12.5 mm: 1.0 mm clearance per side.

10. **6 mm cable hole unsealable — FIXED geometrically, with a parameter mismatch.** The hole is 3.5 mm and has an 8 mm × 10 mm internal boss ([lines 38–39, 126, 129](./buoy_v2.scad:38)). But `cable_d` is also 3.5 mm ([line 49](./buoy_v2.scad:49)), so the comment “cable OD + 0.5” is false for the modeled cable.

11. **Cage slots clipped post tips — FIXED.** Posts end at z=16 mm ([lines 138, 159](./buoy_v2.scad:138)); slots begin at z=16 mm and are 30° off the posts ([lines 147–149](./buoy_v2.scad:147)). At r=13 mm their nearest lateral distance is 6.5 mm, exceeding the 3 mm slot half-width.

12. **Zip-tie slots crossed — FIXED.** The two slots are parallel, x=−7.75…−4.25 and +4.25…+7.75 mm ([line 153](./buoy_v2.scad:153)). The eye plate now blocks the left one.

New findings:

1. **BLOCKER — the head eye plate blocks the cable bore and left zip slot.** The cable bore is cut from the main head body before the eye plate is added ([lines 142–154](./buoy_v2.scad:142), [165–168](./buoy_v2.scad:165)). The plate occupies x=−16…0, y=−2…2, z≈55.5…72 mm; the cable bore occupies x/y within r=1.75 at z=52…62 mm. Thus the plate closes roughly the negative-X half of the cable passage. It also fills the left zip slot at x=−7.75…−4.25, z=55.5…57 mm. Cut the cable bore and both zip slots after unioning the eye plate, or move the eye plate clear of both features.

2. **BLOCKER — the printed “trapezoid thread” has effectively no axial tooth width.** `helix_thread()` extrudes a radial/tangential polygon while twisting it ([lines 62–70](./buoy_v2.scad:62)). Its stated `base=2.6 mm` is tangential, not axial. At r≈65 mm and 5 mm pitch, that corresponds to an axial width of only `2.6 × 5 / (2π × 65) = 0.032 mm`, not 2.6 mm. This produces knife-thin helical sheets spaced 5 mm apart, not a 45° trapezoidal screw thread. Use a true axial thread profile / a proven thread library, then generate its mating subtraction from the same profile.

3. **MAJOR — claimed 0.45 mm clearance is radially adequate, but the thread remains non-mating.** Hull crest is r=66.2 mm ([lines 28–31, 86](./buoy_v2.scad:28)); lid groove reaches r=66.65 mm (`65 + 1.2 + 0.45`, [line 116](./buoy_v2.scad:116)), giving 0.45 mm radial clearance. Axially, hull spans z=87.5–98.5 mm ([lines 59, 86](./buoy_v2.scad:59)); flipped lid cut spans z=86.0–98.5 mm, so it covers the hull length. Neither fact repairs the handedness failure. Set the lid to `hand=1` if retaining the current flipped assembly convention, after replacing the thread construction.

4. **MAJOR — both “lead-in chamfers” miss the mating thread start.** Hull thread is z=87.5–98.5 mm; its chamfer is z=99–100 mm ([lines 86, 97](./buoy_v2.scad:86)), 0.5 mm above the thread end. The flipped lid mouth chamfer is global z≈84–85 mm ([lines 114–118](./buoy_v2.scad:114)), 2.5–3.5 mm below the hull thread start. Neither provides an entry ramp into the first engaged thread. Put a lead-in on the hull’s upper thread end and/or the lid’s actual entering groove end, based on a corrected mating thread.

5. **MAJOR — ESP pocket ribs intentionally intersect the modeled board.** The ESP is x=−13…13 mm ([line 178](./buoy_v2.scad:178)); ribs occupy x=13.3…15.7 and −15.7…−13.3 mm ([line 104](./buoy_v2.scad:104)). Each rib cuts 0.3 mm into the board envelope through z=2.4–14.4 mm. Move rib inner faces to ±(13 + clearance), e.g. ±13.8 mm for 0.8 mm clearance, and preserve their gap from the positive bank rail (currently only 2.8 mm).

6. **MAJOR — head retaining tabs do not retain the stated 8 mm piezo pack.** The sinker pocket is z=3–11 mm ([line 156](./buoy_v2.scad:156)); an 8 mm pack placed on it occupies z=11–19 mm. Tab underside begins at z=24.6 mm ([lines 138–139, 162](./buoy_v2.scad:162)), leaving a 5.6 mm gap. Lower the tab underside to approximately z=19–19.5 mm, allowing only intended insertion clearance.

7. **MAJOR — reported stability is materially overstated.** From the code: hull mass ≈172.9 g, lid ≈84.1 g, total ≈659.0 g; draft ≈49.65 mm; KM≈46.10 mm; reported KG≈35.53 mm and GM≈10.57 mm ([lines 182–190](./buoy_v2.scad:182)). With the bank in its actual modeled orientation, bank CG is 34.9 rather than 14.9 mm. Corrected KG is ≈42.51 mm and GM≈3.59 mm. That is positive only marginally, before uncertainty in shell mass, lugs, rails, retained water, and actual tether force. Either model the bank flat as `[bank_l, bank_w, bank_t]` and redesign the layout, or use `bank_w/2` in KG and state the reduced GM.

8. **MINOR — the neck land and gasket placement themselves are coherent.** The main cavity ends at z≈84.01 mm, the land cavity starts at z=84 mm, and the thread starts at 87.5 mm ([lines 59, 90–91](./buoy_v2.scad:59)). The 4.4 mm land supports the thread; the gasket is above the thread end with 1.2 mm remaining wall. No overlap defect found there.