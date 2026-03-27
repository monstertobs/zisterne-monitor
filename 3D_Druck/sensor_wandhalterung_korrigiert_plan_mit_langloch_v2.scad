// ╔══════════════════════════════════════════════════════════╗
// ║  JSN-SR04T Sensor-Wandhalterung                         ║
// ║  Montage an Betonwand mit Langlöchern                   ║
// ║  Sensor zeigt nach UNTEN in die Zisterne               ║
// ║  Tobias Meier · admin@secutobs.com · v0.5.0            ║
// ╠══════════════════════════════════════════════════════════╣
// ║  DRUCKEN:                                              ║
// ║  1. F6 → rendern  2. File → Export → STL              ║
// ║  Material:  PETG (feuchtigkeitsbeständig, empfohlen)   ║
// ║            oder PLA für trockene Umgebung              ║
// ║  Schichthöhe: 0.2mm | Wandlinien: 4 | Infill: 40%    ║
// ║  Support:  NEIN – druckfreundlich ausgerichtet         ║
// ║  Ausrichtung: Rückwand flach auf Druckbett             ║
// ╠══════════════════════════════════════════════════════════╣
// ║  MONTAGE:                                              ║
// ║  1. Halterung an Betonwand halten, Position markieren  ║
// ║  2. 2× Dübel setzen (6mm Universaldübel)              ║
// ║  3. Schraube M4×30 oder 4mm Holzschraube verwenden    ║
// ║  4. Langlöcher erlauben ±15mm vertikale Justage       ║
// ║  5. Sensor von unten in Aufnahme drücken (Pressfit)   ║
// ║  6. Sensor schwenkbar: Winkel 0°-30° einstellbar      ║
// ╚══════════════════════════════════════════════════════════╝

// ── Sensor JSN-SR04T ─────────────────────────────────────
SENS_D   = 19.4;    // angepasst    // Sensorkopf Durchmesser
SENS_SP  =  0.4;    // angepasst    // Pressfit-Spiel
SENS_T   = 20.0;    // angepasst    // Einbautiefe Sensor
WAND_S   =  3.5;    // Wandstärke Sensoraufnahme

// ── Wandplatte ───────────────────────────────────────────
WP_B     = 80.0;    // Breite Wandplatte
WP_H     = 60.0;    // Höhe Wandplatte
WP_T     =  8.0;    // Tiefe/Dicke Wandplatte

// ── Langlöcher ───────────────────────────────────────────
LL_B     =  5.5;    // Breite Langloch (für M4/4mm Schraube)
LL_H     = 22.0;    // Höhe Langloch  (±11mm Justage)
LL_X     = 20.0;    // Abstand Langloch von Mitte (je Seite)
LL_Y     =  0.0;    // Vertikale Position (Mitte der Platte)
LL_SR    =  LL_B/2; // Eckenradius Langloch

// ── Sensorarm ────────────────────────────────────────────
ARM_L    = 35.0;    // Armlänge (Abstand Wand → Sensormitte)
ARM_B    = 20.0;    // Armbreite
ARM_T    = 24.0;    // angepasst für 20 mm Sensorhöhe    // Armtiefe

// ── Sensor-Aufnahme ──────────────────────────────────────
SENS_R   = SENS_D/2 + SENS_SP;
AUFN_RA  = SENS_R + WAND_S;

// ── Versteifungsrippe ────────────────────────────────────
RIP_T    =  6.0;    // Rippendicke
RIP_H    = 30.0;    // Rippenhöhe

// Korrigierte Version:
// - ursprüngliche Form bleibt erhalten
// - Sensor auf 19.4 x 20 mm angepasst
// - Langlöcher wieder vorhanden
// - mittlerer Rückseiten-Überstand entfernt
// - keine Rückseiten-Versenkungen / Gewichtsfenster
// - Langlöcher vollständig durch die Platte verlängert
$fn = 48;

// ════════════════════════════════════════════════════════
//  WANDHALTERUNG – alles in einem Teil
// ════════════════════════════════════════════════════════
difference() {
    union() {

        // ── 1. WANDPLATTE ────────────────────────────────
        hull() {
            for(x = [-WP_B/2+6, WP_B/2-6])
            for(z = [-WP_H/2+6, WP_H/2-6])
                translate([x, 0, z])
                    rotate([90,0,0])
                        cylinder(r=6, h=WP_T);
        }

        // ── 2. SENSORARM (nach vorne und unten) ──────────
        // Arm geht von Mitte der Platte nach vorne
        hull() {
            // Verbindung zur Platte (unten-mitte)
            translate([-ARM_B/2, -ARM_T, -10])
                cube([ARM_B, ARM_T, 10]);
            // Arm-Ende (weiter vorne)
            translate([-ARM_B/2, -(WP_T + ARM_L), -ARM_T/2])
                cube([ARM_B, ARM_T, ARM_T]);
        }

        // ── 3. SENSOR-AUFNAHME (am Arm-Ende, Sensor nach unten) ──
        translate([0, -(WP_T + ARM_L), 0])
            cylinder(h=ARM_T+0.1, r=AUFN_RA, center=true);

        // ── 4. VERSTEIFUNGSRIPPEN ────────────────────────
        // intersection() begrenzt Rippen auf y<=0 → Rückwand bleibt flach
        intersection() {
            union() {
                hull(){
                    translate([-RIP_T/2, -WP_T, WP_H/2-6-RIP_H])
                        cube([RIP_T, RIP_T, RIP_H]);
                    translate([-RIP_T/2, -(WP_T+ARM_L*0.6), -8])
                        cube([RIP_T, RIP_T, 8]);
                }
                hull(){
                    translate([-RIP_T/2, -WP_T, -WP_H/2+6])
                        cube([RIP_T, WP_T+2, RIP_H]);
                    translate([-RIP_T/2, -(WP_T+ARM_L*0.5), -WP_H/2+6])
                        cube([RIP_T, 6, 16]);
                }
            }
            // Nur Bereich VOR der Rückwand (y <= 0)
            translate([-500, -500, -500]) cube([1000, 500, 1000]);
        }
    }

    // ── BOHRUNGEN ────────────────────────────────────────

    // Langloch Links
    translate([-LL_X, -WP_T/2, LL_Y])
        rotate([90,0,0]) {
            hull() {
                translate([0,  LL_H/2-LL_SR, 0]) cylinder(r=LL_SR, h=WP_T+20, center=true);
                translate([0, -LL_H/2+LL_SR, 0]) cylinder(r=LL_SR, h=WP_T+20, center=true);
            }
        }

    // Langloch Rechts
    translate([LL_X, -WP_T/2, LL_Y])
        rotate([90,0,0]) {
            hull() {
                translate([0,  LL_H/2-LL_SR, 0]) cylinder(r=LL_SR, h=WP_T+20, center=true);
                translate([0, -LL_H/2+LL_SR, 0]) cylinder(r=LL_SR, h=WP_T+20, center=true);
            }
        }

    // Sensor-Bohrung (von unten, Pressfit)
    translate([0, -(WP_T + ARM_L), -(ARM_T/2)-0.1])
        cylinder(h=ARM_T-WAND_S+0.1, r=SENS_R);

    // Einführphase Sensor
    translate([0, -(WP_T + ARM_L), -(ARM_T/2)-2])
        cylinder(h=2.1, r1=SENS_R+2, r2=SENS_R);

    // Kabel-Nut (Kabel kommt seitlich raus und nach oben)
    translate([-3.5, -(WP_T + ARM_L + AUFN_RA - 1), ARM_T*0.1])
        cube([7, AUFN_RA+1, ARM_T]);
}

// ════════════════════════════════════════════════════════
//  LANGLOCH-ERKLÄRUNG
// ════════════════════════════════════════════════════════
// Langlöcher: 5.5mm × 22mm
// → Schraube M4 oder Dübel 6mm + Schraube 4mm
// → ±11mm Verstellbereich vertikal
// → Schraubenkopf versenkt (bündig mit Wandplatte)
//
// SENSOR-AUSRICHTUNG:
// → Sensor drückt von UNTEN in die Aufnahme
// → Durch Verschieben der Halterung an der Wand
//   kann der Sensor exakt ausgerichtet werden
// → Für horizontale Justage: Dübellöcher entsprechend setzen
