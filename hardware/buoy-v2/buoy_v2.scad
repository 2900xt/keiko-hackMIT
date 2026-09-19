// Charles Ear buoy v2.3 — parametric hull for one ESP32-S3 DevKitC + USB power bank,
// hydrophone on a tether below. Two Bambu/Prusa-class PLA printers, each plate ~4 h.
//
// v2.1 after Codex adversarial review: squat 130 mm hull (positive GM), power bank lies flat on
// the floor, ESP32 stands in the side crescent with its antenna above the waterline, 45° thread
// with opposite hand in the lid, gasket groove in a thickened neck land, lugs moved outboard,
// top mooring lug deleted (mooring goes to the low bridle ring), lid panel is an engraved outline
// (no 60 mm bridge), head has a 45° cone roof, connected posts, retaining tabs, parallel zip slots,
// and an eye plate that prints from the roof.
//
// part = "hull" | "lid" | "head" | "plate_b" (lid + head) | "all" (assembly preview)
part = "all";

/* ---------------- payload (measure yours) ---------------- */
bank_l = 95;   bank_w = 62;  bank_t = 15;  bank_g = 115;   // 5,000 mAh USB power bank (measure yours), lies FLAT on the floor
esp_l  = 70;   esp_w  = 26;  esp_h  = 20;  esp_g  = 12;    // ESP32-S3 DevKitC with headers, stands vertical, antenna UP
tether_eff_g = 100;      // effective (submerged) weight of head + washers + wet cable hanging from the bridle
misc_g = 60;             // cables, gasket, tape

/* ---------------- hull -------------------- */
hull_od   = 130;
wall      = 2.0;         // print as 5 lines x 0.42 mm, no infill in the shell
floor_t   = 2.4;
hull_h    = 100;         // total height incl. neck
neck_h    = 14;
land_t    = 2.4;         // extra wall thickness inside the neck so the gasket groove has material
clr       = 0.45;        // radial clearance hull thread <-> lid thread
pitch     = 5;
thread_h  = 1.2;         // radial height of the trapezoid thread
thread_b  = 2.6;         // axial base width of the thread
turns     = 2.2;
groove_w  = 2.0;  groove_d = 0.9;   // gasket groove on the neck rim; 2 mm rubber cord or two rubber bands

/* ---------------- lid --------------------- */
lid_top_t  = 3.2;
skirt_wall = 2.4;
panel_x = 50; panel_y = 50; panel_line = 1.6; panel_depth = 0.6;   // engraved outline only, prints on the bed
gland_hole = 3.5;                            // = cable_d + 0.5 (cable_d below); marine heat shrink over the boss seals it
gland_boss = 8; gland_boss_h = 10;           // INTERNAL boss (lid prints top-down)

/* ---------------- lugs -------------------- */
lug_t = 6;  lug_hole = 8;  lug_r = 9;        // two bottom lugs, opposite, for a two-leg bridle to a ring 100-150 mm below

/* ---------------- hydrophone head --------- */
head_od = 44; head_h = 56; head_wall = 2.4; head_floor = 3;
piezo_pack_d = 24;  piezo_pack_t = 8;        // SEALED disc assembly (balloon / coating), not the bare 20 mm disc
sinker_d = 25.5; sinker_h = 8;               // 1" fender washers, taped into a stack; +0.5 mm clearance
slot_w = 6; n_slots = 6;
cable_d = 3.0;   // hydrophone cable OD; head hole is cable_d + 0.5

$fn = 120;
eps = 0.01;

hull_r  = hull_od/2;
neck_r  = hull_r;
lid_bore_r = neck_r + clr;
lid_od  = 2*(neck_r + thread_h + clr + skirt_wall);
lid_skirt_h = neck_h + 2;
thread_z0 = hull_h - neck_h + 1.5;           // where the hull thread starts

// ---------- helpers ----------
module thread_slice(r, h_rad, base, extra, hscale) {
    // r-z profile: 0.3 mm root embed (inside the wall, never exposed) + 45° trapezoid tooth.
    // extruded a hair tangentially; hull-chained along the helix by helix_thread()
    hh = h_rad*hscale;
    rotate([90,0,0]) linear_extrude(0.02, center = true)
        polygon([[r - 0.3 - extra, -(base/2 + extra)],
                 [r + extra,       -(base/2 + extra)],
                 [r + hh + extra,  -(base/2 - hh) - extra],
                 [r + hh + extra,   (base/2 - hh) + extra],
                 [r + extra,        (base/2 + extra)],
                 [r - 0.3 - extra,  (base/2 + extra)]]);
}
module helix_thread(r, h_rad, base, pitch, turns, hand = 1, extra = 0, ramp = 0.35) {
    // true helical sweep: profile lives in the r-z plane, so `base` is the AXIAL width.
    // hand=+1 right-hand. ramp: fraction of a turn over which the tooth height grows from 0 at each end.
    n = ceil(turns*48);
    for (i = [0:n-1]) {
        t0 = i/n*turns; t1 = (i+1)/n*turns;
        hull() {
            rotate([0,0,hand*360*t0]) translate([0,0,pitch*t0]) thread_slice(r, h_rad, base, extra, min(1, t0/ramp, (turns - t0)/ramp));
            rotate([0,0,hand*360*t1]) translate([0,0,pitch*t1]) thread_slice(r, h_rad, base, extra, min(1, t1/ramp, (turns - t1)/ramp));
        }
    }
}
module eye_lug(z0, rot) {
    // vertical-axis loop outboard of the hull wall, bottom face at z0 (prints flat on the bed)
    rotate([0,0,rot]) translate([hull_r + 2, 0, z0])
        difference() {
            hull() { cylinder(r = lug_r, h = lug_t); translate([-lug_r - 4, -lug_r, 0]) cube([4, 2*lug_r, lug_t]); }
            translate([lug_r*0.35, 0, -eps]) cylinder(d = lug_hole, h = lug_t + 2*eps);
        }
}

// ---------- hull ----------
module hull_body() {
    slot = bank_w + 2;
    difference() {
        union() {
            cylinder(r = hull_r, h = hull_h);
            translate([0,0,thread_z0]) helix_thread(neck_r, thread_h, thread_b, pitch, turns, 1);
            eye_lug(0, 0); eye_lug(0, 180);
        }
        // cavity, stepped: thinner wall below, thicker land in the neck
        translate([0,0,floor_t]) cylinder(r = hull_r - wall, h = hull_h - neck_h - floor_t - 2 + eps);
        translate([0,0,hull_h - neck_h - 2]) cylinder(r = hull_r - wall - land_t, h = neck_h + 3);
        // gasket groove centred in the land
        gr = hull_r - (wall + land_t)/2;
        translate([0,0,hull_h - groove_d])
            difference() { cylinder(r = gr + groove_w/2, h = groove_d + eps); translate([0,0,-eps]) cylinder(r = gr - groove_w/2, h = groove_d + 3*eps); }
        // thread lead-in chamfer at the rim (outer edge)
        translate([0,0,hull_h - 1]) difference() { cylinder(r = hull_r + thread_h + 1, h = 1 + eps); cylinder(r1 = hull_r - 0.6, r2 = hull_r + 0.6, h = 1 + eps); }
    }
    // power-bank locating rails (low; bank lies FLAT, 65 mm side between the rails, 25 mm tall)
    rail_h = 8;
    for (s = [-1, 1]) translate([-bank_l/2 + 10, s*(slot/2 + 1.2) - 1.2, floor_t - eps]) cube([bank_l - 20, 2.4, rail_h]);
    // ESP32 pocket in the side crescent: two short ribs; board stands vertical, antenna up, leans on the wall
    esp_y = slot/2 + 1.2 + 12;
    for (s = [-1, 1]) translate([s > 0 ? esp_w/2 + 0.8 : -esp_w/2 - 0.8 - 2.4, esp_y - 8, floor_t - eps]) cube([2.4, 16, 12]);
}

// ---------- lid ----------
module lid_body() {
    // printed top-down: flat top on the bed, skirt up. Flipping is a rotation, so the groove keeps the
    // hull's handedness (hand = 1). The groove is the hull tooth grown by clr on every side.
    gland_r = panel_x/2 + 10;
    difference() {
        cylinder(r = lid_od/2, h = lid_skirt_h + lid_top_t);
        translate([0,0,lid_top_t]) {
            cylinder(r = lid_bore_r, h = lid_skirt_h + eps);
            translate([0,0,0.8]) helix_thread(neck_r, thread_h, thread_b, pitch, turns + 0.4, 1, clr, 0.001);
            // lead-in at the skirt mouth
            translate([0,0,lid_skirt_h - 1]) cylinder(r1 = lid_bore_r, r2 = lid_bore_r + thread_h + 0.5, h = 1 + eps);
        }
        // engraved panel outline (shallow groove, bridges nothing)
        translate([0,0,-eps]) linear_extrude(panel_depth + eps) difference() {
            square([panel_x, panel_y], center = true);
            square([panel_x - 2*panel_line, panel_y - 2*panel_line], center = true);
        }
        // cable hole, outside the outline
        translate([gland_r, 0, -eps]) cylinder(d = gland_hole, h = 50);
    }
    // internal gland boss
    translate([gland_r, 0, lid_top_t - eps]) difference() { cylinder(d = gland_boss, h = gland_boss_h); translate([0,0,-eps]) cylinder(d = gland_hole, h = gland_boss_h + 2*eps); }
    // grip ribs
    for (a = [0:20:359]) rotate([0,0,a]) translate([lid_od/2 - 0.6, -1.5, 0]) cube([1.8, 3, lid_skirt_h + lid_top_t]);
}

// ---------- hydrophone head ----------
module head_body() {
    r = head_od/2; ri = r - head_wall;
    post_r = piezo_pack_d/2 + 1;               // 13 mm: posts overlap the sinker ring (ID 25.5 -> ring r 12.75..14.35)
    post_top = head_floor + sinker_h + 5;      // sealed disc rests on the posts here (z = 16)
    tab_z = post_top + piezo_pack_t + 0.6;     // tab underside 0.6 mm above the disc pack
    cone_h = ri - (cable_d + 0.5)/2;           // 45° cone roof
    roof_z = head_h - head_floor;
    difference() {
        union() {
            difference() {
                cylinder(r = r, h = head_h);
                translate([0,0,head_floor]) cylinder(r = ri, h = roof_z - cone_h - head_floor + eps);
                translate([0,0,roof_z - cone_h]) cylinder(r1 = ri, r2 = (cable_d + 0.5)/2, h = cone_h);
                for (i = [0:n_slots-1]) rotate([0,0,i*360/n_slots + 30])
                    translate([0, -slot_w/2, post_top]) cube([r + 1, slot_w, roof_z - cone_h - post_top - 2]);
            }
            // sinker pocket ring
            translate([0,0,head_floor - eps]) difference() { cylinder(d = sinker_d + 2*1.6, h = sinker_h); translate([0,0,-eps]) cylinder(d = sinker_d, h = sinker_h + 2*eps); }
            // posts tied to the ring by radial ribs; retaining tabs with 45° undersides
            for (a = [0, 120, 240]) rotate([0,0,a]) {
                // post: seat for the pack at post_top, then continues up past the pack as a retaining post
                translate([post_r, 0, head_floor + sinker_h - 2]) cylinder(d = 4.5, h = tab_z + 2 - (head_floor + sinker_h - 2), $fn = 24);
                translate([sinker_d/2 - 0.5, -1.2, head_floor + sinker_h - 2]) cube([post_r - sinker_d/2 + 2.5, 2.4, 2]);
                // pack seat: a 1.5 mm inward step at post_top so the pack rests on the posts, not between them
                translate([post_r - 3.5, -2.25, post_top - 3]) cube([3.5, 4.5, 3]);
                // hook: 45° underside wedge pointing inward, inner edge at r = piezo_pack_d/2 - 1.5 (1.5 mm overlap)
                hull() {
                    translate([post_r - 2.25, -2.25, tab_z]) cube([2.25, 4.5, 2]);
                    translate([piezo_pack_d/2 - 1.5, -2.25, tab_z + (post_r - 2.25 - (piezo_pack_d/2 - 1.5))]) cube([0.5, 4.5, 2]);
                }
            }
            // drop-line eye plate on the roof, clear of the cable hole and zip slots
            translate([-14, 0, head_h - eps]) rotate([90,0,0]) linear_extrude(4, center = true) difference() {
                hull() { square([16, 1], center = true); translate([0, 8]) circle(r = 8); }
                hull() { translate([0, 7]) circle(d = 6); translate([0, 10]) circle(d = 3); }
            }
        }
        // cable hole through the apex and top plate
        translate([0,0,roof_z - 1]) cylinder(d = cable_d + 0.5, h = 20);
        // two PARALLEL zip-tie slots on the y axis; the tie runs along x over the cable
        for (s = [-1, 1]) translate([-3.5, s*6 - 1.75, head_h - 13]) cube([7, 3.5, 14]);   // through the roof into the cavity
    }
}

// ---------- assembly & buoyancy ----------
module assembly() {
    slot = bank_w + 2;
    color("lightblue") hull_body();
    color("orange") translate([0,0,hull_h + lid_top_t]) rotate([180,0,0]) lid_body();
    color("gray") translate([hull_r + 40, 0, -60]) head_body();
    color("green", 0.5) translate([-bank_l/2, -bank_w/2, floor_t]) cube([bank_l, bank_w, bank_t]);   // flat: 25 mm tall
    color("red", 0.5) translate([-esp_w/2, slot/2 + 1.2 + 12 - esp_h/2, floor_t]) cube([esp_w, esp_h, esp_l]);
}

// mass & stability estimate (fresh water). Shell mass from areas; features +10 %.
pla_rho = 1.24;
A_wp = PI*hull_r*hull_r;
hull_g = ((PI*hull_r*hull_r*floor_t) + 2*PI*hull_r*wall*(hull_h - floor_t) + 2*PI*(hull_r - wall)*land_t*(neck_h + 2)) / 1000 * pla_rho * 1.10;
lid_g  = (PI*pow(lid_od/2,2)*lid_top_t + 2*PI*(lid_od/2)*skirt_wall*lid_skirt_h) / 1000 * pla_rho * 1.05;
total_g = hull_g + lid_g + bank_g + esp_g + misc_g + tether_eff_g;
draft = total_g / (A_wp/1000);
KB = draft/2;  BM = hull_r*hull_r/(4*draft);  KM = KB + BM;
KG = (hull_g*hull_h/2 + lid_g*(hull_h + 1) + bank_g*(floor_t + bank_t/2) + esp_g*(floor_t + esp_l/2) + misc_g*40 + tether_eff_g*0) / total_g;
echo(str("hull ~", round(hull_g), " g, lid ~", round(lid_g), " g, total ~", round(total_g), " g, draft ", round(draft), " mm, freeboard to neck ", round(hull_h - neck_h - draft), " mm, to rim ", round(hull_h - draft), " mm, GM ", round(KM - KG), " mm (KM ", round(KM), ", KG ", round(KG), "); ESP antenna top ", round(floor_t + esp_l - draft), " mm above waterline"));

esp_y0 = (bank_w + 2)/2 + 1.2 + 12 - esp_h/2;
echo(str("bank y +-", bank_w/2, " | ESP y ", esp_y0, "..", esp_y0 + esp_h, " (gap to bank ", esp_y0 - bank_w/2, " mm) | ESP outer corner r ", round(sqrt(pow(esp_w/2,2) + pow(esp_y0 + esp_h,2))*10)/10, " vs bore ", hull_r - wall));
if (part == "hull") hull_body();
else if (part == "lid") lid_body();
else if (part == "head") head_body();
else if (part == "plate_b") { lid_body(); translate([lid_od/2 + head_od/2 + 15, 0, 0]) head_body(); }
else assembly();
