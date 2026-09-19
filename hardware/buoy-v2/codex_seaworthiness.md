1. **Blocker — the upright configuration has negative metacentric stability and will not self-right.**  
   Lines 156–163 estimate \(m=529\) g and draft \(T=67.3\) mm. For a 100 mm circular waterplane:

   \[
   A=\pi(50)^2=7{,}854\ {\rm mm^2}
   \]
   \[
   I=\frac{\pi r^4}{4}=4.91\times10^6\ {\rm mm^4}
   \]
   \[
   KB=T/2=33.7\ {\rm mm},\quad BM=I/\nabla=4.91e6/(529000)=9.3\ {\rm mm}
   \]

   So \(KM=43.0\) mm above the hull bottom. The code places the 230 g bank vertically from \(z=3\) to 103 mm (lines 152, 8), so its CG alone is at 53 mm. A reasonable mass moment from the code’s own parts is: hull ≈172 g at 66 mm, lid ≈55 g at ~130 mm, bank 230 g at 53 mm, ESP 12 g at 38 mm, and 60 g miscellaneous at ~65 mm. That gives:

   \[
   KG \approx 66.5\ {\rm mm};\quad GM=KM-KG\approx -23.5\ {\rm mm}
   \]

   It is statically unstable: a small heel will tend to increase, not recover. The vertical bank is the dominant practical issue, but the tall PLA shell/lid also raise CG.

   **Fix:** do not launch this form factor upright without real low ballast or a much wider waterplane. For merely neutral stability, add about **170 g of effective submerged hanging ballast** acting at \(z\approx5\) mm; that yields draft ≈89 mm and \(GM\approx0\). For a still-modest \(GM\approx10\) mm, use about **250–260 g effective ballast at the keel**, but then draft is ≈100 mm and functional freeboard is only ≈16 mm. The better fix is increase `hull_od` from `100` to at least **140–150 mm**, keep ballast low, and keep the battery as low as packaging permits. A 100 mm × 132 mm upright cylinder is a poor river buoy hull.

2. **Blocker — the claimed 49 mm freeboard omits the tethered hydrophone’s effective weight.**  
   `payload_g` is only `230 + 12 + 60` (line 160). It does not include the printed `head_body()`, its washers/nuts, or the 1–2 m wet cable. The suspended assembly pulls downward by its **submerged effective weight**, not its dry mass, and must be included in the buoy displacement calculation.

   Each additional 100 g effective downward load adds:

   \[
   100/7.854=12.7\ {\rm mm}
   \]

   of draft. Therefore:

   | Effective suspended load | Draft | Freeboard to 116 mm shoulder |
   |---:|---:|---:|
   | 0 g (code estimate) | 67 mm | 49 mm |
   | 100 g | 80 mm | 36 mm |
   | 200 g | 93 mm | 23 mm |
   | 250 g | 99 mm | 17 mm |

   The very ballast needed to make this hull righting-stable nearly eliminates its wave margin. The 16 mm threaded neck is geometrically still above that shoulder, but it is not a safe, dry freeboard reserve once wakes wet the threads and cable entry.

   **Fix:** weigh the complete dry buoy and weigh the fully submerged hydrophone/washer/cable assembly in water; use the latter as added load. Change line 160 to include a measured `tether_effective_g`. Do not accept less than roughly **50 mm freeboard to the lowest credible ingress path** after that load is included; with this diameter, that means materially reducing mass or increasing `hull_od`.

3. **Major — the two “bottom” tether lugs do not by themselves guarantee a stabilizing bridle; their geometry needs to carry the hanging load centrally.**  
   `eye_lug(0, 0)` and `eye_lug(0, 180)` (line 74) put the hole centers approximately 51 mm from the centerline and around \(z=3\) mm. This can be excellent *if* the bridle legs are equal and join at a central point below the buoy: the combined vertical tether force then acts near the bottom center and supplies the low “ballast” moment assumed above.

   But a single cable tied through one lug, unequal bridle legs, or a snagged cable makes the force off-axis. A 100 g downward tether load acting 51 mm off-center produces:

   \[
   0.981\ {\rm N}\times0.051\ {\rm m}=0.050\ {\rm N\,m}
   \]

   — far more than this unballasted hull’s nonexistent restoring moment. It will heel hard toward the loaded lug.

   **Fix:** use a fixed, equal-length two-leg bridle to a single ring **at least 100–150 mm below the hull**, then attach the hydrophone line at that ring. Add a centered underside attachment point if printing can be changed. Do not tie the hydrophone cable/line directly to either edge lug.

4. **Major — the top “mooring” eye is a capsize lever under horizontal line load.**  
   The top lug is generated at `eye_lug(hull_h - neck_h - lug_t - 4, 90)` (line 75), i.e. its hole is about \(z=109\) mm, while the nominal waterline is \(z=67\) mm. A mooring pull therefore acts about 42 mm above the waterline. At only 10 m/s wind, the exposed nominal 100 mm × 49 mm projected area gives approximately:

   \[
   F_{\rm wind}\approx \tfrac12(1.2)(1.1)(0.100)(0.049)(10^2)
   \approx0.32\ {\rm N}
   \]

   A comparable mooring-line force at the top lug applies about:

   \[
   0.32 \times 0.042 = 0.013\ {\rm N\,m}
   \]

   overturning moment. With the current negative \(GM\), essentially any sustained sideways line load makes this worse. Even with only 10 mm positive GM, that force corresponds to roughly 15° heel before accounting for gusts/wakes.

   **Fix:** eliminate the top mooring lug for anchoring. Attach any anchor/mooring line to the same **low central bridle ring** as the hydrophone, or move the towing/mooring point to approximately the loaded waterline, `z ≈ 60–70 mm`, with a sealed attachment. The existing top lug is suitable only as a carry/recovery feature, not a mooring point.

5. **Major — wake and splash tolerance is inadequate once the real hanging load/ballast is added.**  
   At the stated no-tether-load condition, 49 mm to the neck shoulder is already little margin for a 100 mm-diameter object in boat wake. At 100–200 g effective tether load it becomes 36–23 mm. A short wake can readily wash over the lid, wet the external thread, and immerse the cable penetration. Repeated splash is more concerning than a single static submersion because it creates pumping through imperfect threads/gaskets.

   The cable hole is `gland_hole = 6` mm (line 29; cut at line 109). The design comment calls for hot glue / heat shrink on the boss (line 111), but hot glue is explicitly unavailable. A plain 6 mm hole around a cable is not splashproof.

   **Fix:** use the available **marine adhesive heat-shrink** as the actual cable gland: shrink it onto the cable, pass it through a tighter hole sized to the recovered sleeve OD, and tape/strain-relieve it to the boss. Add a drip loop below the lid. For tomorrow, wrap the fully tightened lid/thread circumference with waterproof duct tape as a secondary splash barrier. This is not a substitute for restoring freeboard.

6. **Major — wind drift is unavoidable without an anchor; an anchor on the top lug is worse than drift.**  
   The same projected wind calculation gives about 0.08 N at 5 m/s and 0.32 N at 10 m/s. With no anchor, the buoy will drift downriver/downwind; the 1–2 m submerged hydrophone and line add current drag, so it will not remain near the intended listening location. With an anchor on the current top lug, the line’s high attachment converts that lateral load into heel/capsize moment.

   **Fix:** either operate it as a closely attended drifting device with recovery planned, or use a low bridle attachment and enough line/weight to hold station. Do not rely on Wi‑Fi range as recovery control. A short tether to a shore-side fixed point should also attach through the low bridle, not the top eye.

7. **Minor — the code’s “freeboard” naming understates the distinction between hull shoulder and sealed top.**  
   Line 163 prints draft “of `hull_h - neck_h` mm sidewall,” i.e. 116 mm, yielding the quoted 49 mm. But the hull remains 100 mm OD through the 16 mm neck (lines 69–72), so the geometric distance from nominal waterline to rim is \(132-67=65\) mm. The 49 mm figure is appropriately conservative only if the start of the threaded neck is treated as the practical splash/ingress threshold. That should be explicit, because buoyancy calculations otherwise look more favorable than the actual splash-safe design.

   **Fix:** report both values: `freeboard_to_neck_mm = hull_h-neck_h-draft_mm` and `freeboard_to_rim_mm = hull_h-draft_mm`, and calculate both using the measured effective hydrophone load.