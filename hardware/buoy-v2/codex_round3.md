## (a) Thread sweep

Not correct as stated.

- The axial base is 2.6 mm: profile endpoints are at ±1.3 mm ([line 66](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:66), [line 69](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:69)).
- The exposed outer radius is 65 → 66.2 mm, so the intended exposed radial height is 1.2 mm ([lines 64–69](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:64)).
- But the actual closed polygon root is at `r - 0.3 = 64.7`, making each flank span 1.5 mm radially over 1.2 mm axially. That is a 51.3° flank, not 45°. The 0.3 mm embedding may be intentional for unioning to the shell, but then it must not be counted as part of the 45° tooth profile.

Pitch is 5 mm and 2.2 turns gives 11 mm helical rise ([lines 28–31](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:28)); the 2.6 mm axial tooth width leaves 2.4 mm between same-phase turns. The 106 hull segments (`ceil(2.2×48)`) overlap at their common slice, so the union should be closed/watertight and does not self-intersect from turn-to-turn ([lines 74–80](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:74)).

However, the ramp does **not** shrink the tooth to zero. At `hscale=0`, its radial span remains 64.7–65.0 mm because only `hh` scales; the root offset `-0.3` remains ([lines 64–69](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:64)). It remains manifold, but has a finite radial stub at each end.

## (b) Lid groove and handedness

The hand is now right. Flipping around X negates both helix angle and axial direction, so `hand=1` in the unflipped lid becomes the same physical hand as the hull after the assembly transform ([lines 121–128](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:121), [line 188](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:188)).

At the seated height:

- Hull thread envelope: nominal centerline z = 87.5–98.5; including the 1.3 mm axial half-base, z = **86.2–99.8 mm** ([lines 59, 66–69, 98](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:59)).
- Lid-cut envelope after flip: z = **84.45–100.95 mm**, using lid top 3.2, offset 0.8, 2.6 turns, and expanded profile half-base 1.75 mm ([lines 35, 66–69, 126–128, 188](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:35)).
- Radially, hull is 64.7–66.2 mm; the groove cut is 64.25–66.65 mm. It contains the tooth with 0.45 mm clearance.

This is conditional on the lid being rotated to its thread engagement phase. At the preview’s arbitrary zero rotation, the tracks are phase-shifted by 122.4°. A rotation of 122.4° aligns them; actual screw engagement should establish that orientation.

## (c) Lead-in

The ramp itself is not a lead-in because it leaves the finite 0.3 mm root stub noted above. The hull rim chamfer does intersect the high end of the thread: it runs z = 99–100 mm while the tooth reaches z = 99.8 mm ([line 109](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:109)). The lid-mouth chamfer is also at the engagement end after flipping ([line 130](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:130)). But neither fixes the finite ramp stub at the other end.

## (d) Bank / rails

The bank is flat: 100 × 65 × 25 mm at z = 2.4–27.4 mm ([lines 15, 190](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:15)).

Rails occupy y = −35.9…−33.5 and +33.5…+35.9 mm, leaving a 67 mm inside gap ([lines 94, 112–113](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:94)). The 65 mm bank has 1.0 mm side clearance to each rail.

At bank corners, radius is `sqrt(50² + 32.5²) = 59.63 mm`; inner bore radius is 63 mm. Corner-to-wall clearance is **3.37 mm**.

## (e) ESP board / ribs / draft

Board envelope is x = ±13, y = 26.7–46.7, z = 2.4–72.4 mm ([lines 16, 115, 191](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:16)). Its outer upper corners are at radius `sqrt(13² + 46.7²) = 48.48 mm`, leaving **14.52 mm** to the 63 mm bore.

Ribs are x = ±13.8…16.2, so they clear the board sides by **0.8 mm** ([line 116](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:116)). Their outer corner is radius 57.05 mm, leaving **5.95 mm** to the bore.

The board nevertheless intersects the bank: the board occupies y = 26.7–46.7 while the bank occupies y = −32.5…32.5, creating a **5.8 mm y-overlap** across x = ±13 and z = 2.4–27.4.

Recomputed draft is **49.65 mm**; antenna top at z = 72.4 is **22.75 mm above water**.

## (f) Head

The post tops are z = 16; an 8 mm pack rests from z = 16 to 24 ([lines 46, 149–151](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:46)). Tab underside is z = 24.6, thus 0.6 mm vertically clear. But the tabs’ nearest radial edge is 16.9 mm, versus the pack radius 12 mm: a **4.9 mm radial gap**. They do not retain the pack ([line 169](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:169)).

Cable bore radius is 1.75 mm. Zip slots are x = −3.5…3.5 and y = ±4.25…7.75:

- Cable-to-slot edge clearance: **2.5 mm**.
- Slot-to-slot edge clearance: **8.5 mm**.
- Eye plate reaches x = −6 mm; nearest slot edge is x = −3.5, giving **2.5 mm** clearance. Cable-bore-to-plate clearance is **4.25 mm**.

Those are cut after the eye-plate union ([lines 154, 171–181](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:154)), so Boolean order is safe.

The six radial side slots end at z = 33.15 mm; the inner cone begins at z = 35.15 mm, leaving **2.0 mm** of roof clearance ([lines 152, 160–161](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:152)).

The two nominal zip slots are blind pockets, not through-slots. Their floor is z = 52.99 mm. The cone’s inside surface beneath them is z ≈ 50.5 mm at the nearest point and lower elsewhere, leaving 2.5–6.7 mm of material. A zip tie cannot pass through them.

## (g) Stability

The flat-bank CG term is correctly `bank_t/2`, placing its CG at z = 14.9 mm ([line 202](file:///Users/mallhw/.claude/jobs/c05f918e/tmp/HackMIT/hardware/buoy-v2/buoy_v2.scad:202)).

Using the file’s mass model:

| Quantity | Result |
|---|---:|
| hull mass | 172.92 g |
| lid mass | 84.10 g |
| total mass | 659.02 g |
| draft | 49.65 mm |
| KB | 24.83 mm |
| BM | 21.27 mm |
| KM | 46.10 mm |
| KG | 35.53 mm |
| GM | **10.57 mm** |

## New defects

1. **Blocker — ESP and bank occupy the same volume.**  
   Move the ESP outward until its inner y edge exceeds 32.5 mm, or relocate/rotate it. Preserve wall clearance after moving it.

2. **Major — “retaining” tabs do not reach the 24 mm pack.**  
   Move their inner edge inward to approximately r ≤ 11.5 mm, or replace them with tabs attached to the post/ring geometry above the pack perimeter.

3. **Major — zip slots are blind and cannot accept a zip tie.**  
   Extend the cuts down through the roof into the head interior, with a defined roof/slot reinforcement strategy.

4. **Major — thread flanks are not 45° in the generated solid.**  
   Keep the 0.3 mm shell-overlap as a separate root/union feature, or make the profile’s radial and axial flank runs both 1.2 mm.

5. **Minor — height ramp never reaches zero tooth height.**  
   Scale/root-collapse the entire profile, or explicitly taper both root and crest to a common radius at each end.