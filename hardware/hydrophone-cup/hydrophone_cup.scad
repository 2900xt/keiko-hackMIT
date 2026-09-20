// Hydrophone potting cup: lost mold for 3x 20 mm piezo discs in epoxy/hot glue.
$fn = 128;
id   = 50;    // inner diameter: fits 3 discs (20 mm) in a triangle
wall = 1.2;   // 2-3 perimeters
h    = 35;    // height
floor_t = 1.2;
od = id + 2*wall;

difference() {
    union() {
        cylinder(d = od, h = h);                       // body
        // three rim tabs to tie the cable / hang the cup while curing
        for (a = [0, 120, 240]) rotate([0,0,a])
            translate([od/2 - 1, 0, h - 6]) cube([5, 8, 6], center = false);
    }
    translate([0,0,floor_t]) cylinder(d = id, h = h);   // cavity
    // zip-tie / string holes through the rim tabs
    for (a = [0, 120, 240]) rotate([0,0,a])
        translate([od/2 + 2, 4, h - 3]) rotate([90,0,0]) cylinder(d = 3.2, h = 20, center = true);
    // cable notch in rim so the tether can lie sideways while pouring
    translate([-2, -od/2 - 1, h - 8]) cube([4, wall + 2, 10]);
}
// floor standoffs: keep discs 2 mm off the floor so resin flows under them
for (a = [30, 150, 270]) rotate([0,0,a])
    translate([14, 0, floor_t - 0.01]) cylinder(d = 3, h = 2);
// pour line mark: small inner ridge 25 mm up (fill to here, then top off)
translate([0,0,25]) difference() { cylinder(d = id + 0.02, h = 0.6); translate([0,0,-1]) cylinder(d = id - 1.2, h = 3); }
