// ╔══════════════════════════════════════════════════════════╗
// ║  Pi Zero 2 WH Gehäuse – DECKEL                          ║
// ║  Tobias Meier · admin@secutobs.com · v0.2.0             ║
// ╠══════════════════════════════════════════════════════════╣
// ║  DRUCKEN:                                               ║
// ║  1. F6 → rendern  2. File → Export → STL               ║
// ║  Material:  PLA  |  Schichthöhe: 0.2mm                 ║
// ║  Wandlinien: 4   |  Infill: 20%  |  Support: NEIN      ║
// ║  Ausrichtung: Deckelaußenseite nach UNTEN               ║
// ╚══════════════════════════════════════════════════════════╝

// ── Gleiche Maße wie Unterteil ───────────────────────────
PI_L   = 65.0;
PI_B   = 30.0;
SPIEL  =  0.5;
WAND   =  2.5;
BODEN  =  1.8;
H_INNEN = 14.0;
R_ECKE =  3.0;

IN_L = PI_L + SPIEL*2;
IN_B = PI_B + SPIEL*2;
AU_L = IN_L + WAND*2;
AU_B = IN_B + WAND*2;
AU_H = H_INNEN + BODEN;

// ── Deckel-spezifisch ────────────────────────────────────
DH       =  5.0;    // Deckelhöhe gesamt
RAND_T   =  3.5;    // Tiefe Innenrand (greift ins Unterteil)
RAND_W   =  1.8;    // Wandstärke Innenrand
RAND_SP  =  0.3;    // Spiel Innenrand (damit er reinpasst)

$fn = 40;

// ════════════════════════════════════════════════════════
//  DECKEL
// ════════════════════════════════════════════════════════
module gehaeuse_deckel() {
    difference() {
        union() {
            // ── Deckplatte ───────────────────────────────
            hull() {
                for(x = [R_ECKE, AU_L - R_ECKE])
                for(y = [R_ECKE, AU_B - R_ECKE])
                    translate([x, y, 0])
                        cylinder(r=R_ECKE, h=DH, $fn=32);
            }

            // ── Innenrand (greift in Unterteil) ──────────
            translate([WAND + RAND_SP, WAND + RAND_SP, -RAND_T])
            difference() {
                cube([IN_L - RAND_SP*2, IN_B - RAND_SP*2, RAND_T]);
                translate([RAND_W, RAND_W, -0.1])
                    cube([IN_L - RAND_SP*2 - RAND_W*2,
                          IN_B - RAND_SP*2 - RAND_W*2,
                          RAND_T + 0.2]);
            }
        }

        // ── Lüftungsschlitze (schmal = kein Durchhängen) ─
        // 3 Reihen × 4 Schlitze
        for(row = [0:2])
        for(col = [0:3])
            translate([AU_L*0.18 + col*14, AU_B*0.2 + row*8, -0.1])
                cube([3.0, AU_B*0.35, DH + 0.2]);

        // ── Clip-Aussparungen (passend zu Unterteil) ────
        for(x = [AU_L*0.28, AU_L*0.72]) {
            translate([x - 2.5, -0.1, -RAND_T])
                cube([5, WAND + 0.2, RAND_T + 0.5]);
            translate([x - 2.5, AU_B - WAND - 0.1, -RAND_T])
                cube([5, WAND + 0.2, RAND_T + 0.5]);
        }

        // ── Beschriftung (vertieft) ──────────────────────
        // "ZISTERNE" in der Mitte des Deckels
        translate([AU_L/2, AU_B/2, DH - 0.5])
        linear_extrude(height=0.6)
        text("ZISTERNE", size=5, font="Liberation Sans:style=Bold",
             halign="center", valign="center");
    }
}

gehaeuse_deckel();
