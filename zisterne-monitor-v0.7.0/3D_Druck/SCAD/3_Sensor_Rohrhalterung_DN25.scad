// ╔══════════════════════════════════════════════════════════╗
// ║  JSN-SR04T Sensorhalterung                              ║
// ║  Vertikales Rohr DN25 · Sensor zeigt nach unten        ║
// ║  Tobias Meier · admin@secutobs.com · v0.2.0            ║
// ╠══════════════════════════════════════════════════════════╣
// ║  DRUCKEN:                                              ║
// ║  1. F6 → rendern  2. File → Export → STL              ║
// ║  Material:  PETG oder PLA                              ║
// ║  Schichthöhe: 0.2mm | Wandlinien: 4 | Infill: 40%    ║
// ║  Support: JA – von Bett                                ║
// ║  Ausrichtung: Klammer steht senkrecht auf dem Bett     ║
// ╚══════════════════════════════════════════════════════════╝

// ── Rohr-Durchmesser anpassen ────────────────────────────
ROHR_D = 32;   // DN25 = 32mm Außendurchmesser
               // DN20 = 25mm | DN32 = 40mm | DN40 = 50mm

// ── Sensor JSN-SR04T ─────────────────────────────────────
SENS_D  = 22.0;   // Sensorkopf Außendurchmesser
SENS_SP =  0.4;   // Pressfit-Spiel
SENS_T  = 13.0;   // Einbautiefe

// ── Kabelbinder ──────────────────────────────────────────
KB_B    =  5.0;   // Breite Kabelbinder-Schlitz
KB_ABST = 22.0;   // Abstand der zwei Schlitze
WAND_C  =  3.5;   // Wandstärke Klammer

// ── Berechnung ───────────────────────────────────────────
ROHR_R  = ROHR_D / 2;
CLIP_RA = ROHR_R + WAND_C;           // Klammer Außenradius
CLIP_H  = KB_ABST + KB_B*2 + 10;    // Klammerhöhe gesamt
SENS_R  = SENS_D/2 + SENS_SP;        // Sensoraufnahme Innenradius
AUFN_RA = SENS_R + 3.5;              // Sensoraufnahme Außenradius

// Arm-Geometrie
ARM_B   = 16;    // Arm-Querschnitt Breite
ARM_H   = 14;    // Arm-Querschnitt Höhe
// Arm startet mittig an der Klammer
ARM_Z   = (CLIP_H - ARM_H) / 2;
// Sensor hängt unter dem Arm
SENS_Z  = ARM_Z - SENS_T - 10;
// X-Abstand Rohrmitte → Sensormitte
OFFS_X  = CLIP_RA + ARM_B + AUFN_RA + 2;

$fn = 48;

// ════════════════════════════════════════════════════════
//  ALLES IN EINEM union() – verhindert lose Teile!
// ════════════════════════════════════════════════════════
difference() {
    union() {

        // ── 1. ROHRKLAMMER ───────────────────────────────
        // C-förmiger Ring um das Rohr
        difference() {
            cylinder(h=CLIP_H, r=CLIP_RA);
            // Rohrbohrung
            translate([0,0,-0.1])
                cylinder(h=CLIP_H+0.2, r=ROHR_R);
            // C-Öffnung nach hinten (neg. Y)
            OE = ROHR_R * 0.7;
            translate([-OE/2, -CLIP_RA-0.1, -0.1])
                cube([OE, CLIP_RA+0.2, CLIP_H+0.2]);
        }

        // ── 2. HORIZONTALER ARM ──────────────────────────
        // Verbindet Klammer mit Sensoraufnahme
        // Direkt mit hull() an Klammer angebunden → KEINE losen Teile
        hull() {
            // An der Klammer-Außenwand
            translate([CLIP_RA-1, -ARM_B/2, ARM_Z])
                cube([1, ARM_B, ARM_H]);
            // An der Sensorseite
            translate([OFFS_X-AUFN_RA-ARM_B, -ARM_B/2, ARM_Z])
                cube([ARM_B, ARM_B, ARM_H]);
        }

        // ── 3. VERTIKALER STEG ───────────────────────────
        // Führt Sensoraufnahme nach unten
        // hull() verbindet Arm und Sensoraufnahme → EIN Teil
        hull() {
            // Oben: Ende des Horizontalarms
            translate([OFFS_X-AUFN_RA-ARM_B, -ARM_B/2, ARM_Z])
                cube([ARM_B, ARM_B, ARM_H]);
            // Unten: über der Sensoraufnahme
            translate([OFFS_X-AUFN_RA-4, -ARM_B/2, SENS_Z+SENS_T-2])
                cube([4, ARM_B, 2]);
        }

        // ── 4. SENSORAUFNAHME ────────────────────────────
        // Zylindrische Aufnahme für Sensor (Pressfit von unten)
        // Mit hull() an Steg angebunden → EIN Teil
        hull() {
            // Verbindung zum Steg
            translate([OFFS_X-AUFN_RA-4, -ARM_B/2, SENS_Z+SENS_T-2])
                cube([4, ARM_B, 2]);
            // Aufnahmezylinder oben
            translate([OFFS_X, 0, SENS_Z+SENS_T])
                cylinder(h=0.5, r=AUFN_RA);
        }
        // Eigentlicher Aufnahmezylinder
        translate([OFFS_X, 0, SENS_Z])
            cylinder(h=SENS_T, r=AUFN_RA);

        // ── 5. VERSTEIFUNGSRIPPE ─────────────────────────
        // Dreieck-Rippe unter dem Arm für Stabilität
        hull() {
            translate([CLIP_RA-0.5, -2, ARM_Z])
                cube([1, 4, 3]);
            translate([OFFS_X-AUFN_RA-ARM_B-1, -2, ARM_Z+ARM_H*0.6])
                cube([1, 4, 3]);
        }

    } // end union()

    // ── BOHRUNGEN (außerhalb union, schneidet alles) ─────

    // Sensor-Bohrung von unten (Pressfit)
    translate([OFFS_X, 0, SENS_Z-0.1])
        cylinder(h=SENS_T-3+0.1, r=SENS_R);

    // Einführphase unten (erleichtert Einsetzen)
    translate([OFFS_X, 0, SENS_Z-1.5])
        cylinder(h=1.6, r1=SENS_R+2.0, r2=SENS_R);

    // Kabel-Nut seitlich (Kabel nach oben führen)
    translate([OFFS_X-3, -AUFN_RA-0.1, SENS_Z+SENS_T*0.3])
        cube([6, AUFN_RA+0.2, SENS_T*0.8]);

    // Kabelbinder-Schlitz 1 (unterer)
    translate([0, 0, 5])
        kb_schlitz_bohrung(CLIP_RA, KB_B);

    // Kabelbinder-Schlitz 2 (oberer)
    translate([0, 0, 5+KB_ABST])
        kb_schlitz_bohrung(CLIP_RA, KB_B);

} // end difference()


// ── Kabelbinder-Schlitz als Modul ────────────────────────
module kb_schlitz_bohrung(r, breite) {
    difference() {
        cylinder(h=breite, r=r+0.1);
        translate([0, 0, -0.1])
            cylinder(h=breite+0.2, r=r-WAND_C+0.2);
        // C-Öffnung nach hinten freilassen
        OE = ROHR_R * 0.7 + 1;
        translate([-OE/2, -r-0.2, -0.2])
            cube([OE, r+0.4, breite+0.4]);
    }
}
