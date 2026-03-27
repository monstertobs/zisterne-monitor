// ╔══════════════════════════════════════════════════════════╗
// ║  Pi Zero 2 WH Gehäuse – UNTERTEIL                       ║
// ║  Tobias Meier · admin@secutobs.com · v0.2.0             ║
// ╠══════════════════════════════════════════════════════════╣
// ║  DRUCKEN:                                               ║
// ║  1. F6 → rendern  2. File → Export → STL               ║
// ║  Material:  PLA  |  Schichthöhe: 0.2mm                 ║
// ║  Wandlinien: 4   |  Infill: 20%  |  Support: NEIN      ║
// ╚══════════════════════════════════════════════════════════╝

// ── Platinen-Maße Pi Zero 2W ─────────────────────────────
PI_L   = 65.0;   // Platinenlänge
PI_B   = 30.0;   // Platinenbreite
SPIEL  =  0.5;   // Spiel ringsrum

// ── Gehäuse-Parameter ───────────────────────────────────
WAND   =  2.5;   // Wandstärke
BODEN  =  1.8;   // Bodenstärke
H_INNEN = 14.0;  // Innenhöhe (Platine ~5mm + Bauteile + Luft)
R_ECKE =  3.0;   // Eckenradius

// ── Berechnete Maße ──────────────────────────────────────
IN_L = PI_L + SPIEL*2;    // Innenmaß Länge
IN_B = PI_B + SPIEL*2;    // Innenmaß Breite
AU_L = IN_L + WAND*2;     // Außenmaß Länge  = ~73mm
AU_B = IN_B + WAND*2;     // Außenmaß Breite = ~37mm
AU_H = H_INNEN + BODEN;   // Außenhöhe gesamt

// ── Pi Zero Lochpositionen (von Platinen-Ursprung) ───────
// Löcher: 3.5mm Ø, Raster 58 x 23mm (Mitte-zu-Mitte)
L_X1 = WAND + SPIEL + 3.5;
L_X2 = WAND + SPIEL + 3.5 + 58.0;
L_Y1 = WAND + SPIEL + 3.5;
L_Y2 = WAND + SPIEL + 3.5 + 23.0;

// ── Port-Positionen (von Platinen-Kante gemessen) ────────
// Rechte Seite: PWR (Micro-USB) und OTG (Micro-USB)
// Pi Zero: PWR bei X≈54mm, OTG bei X≈41mm (von links)
PWR_X  = WAND + SPIEL + 54.5;   // Mitte PWR-USB
OTG_X  = WAND + SPIEL + 41.5;   // Mitte OTG-USB
USB_B  =  9.0;   // Breite Micro-USB Ausschnitt
USB_H  =  4.0;   // Höhe  Micro-USB Ausschnitt
USB_Z  =  BODEN; // USB liegt direkt auf Boden-Level

// Linke Seite: Mini-HDMI bei X≈12mm
HDMI_X = WAND + SPIEL + 12.0;
HDMI_B = 12.0;
HDMI_H =  4.5;

// Vorne (kurze Seite, wo SD-Karte): SD bei Y≈1mm
SD_X   = WAND + SPIEL + 1.0;
SD_B   = 13.0;
SD_H   =  2.2;

// ── Lüftungsschlitze Boden ───────────────────────────────
// Schmal und kurz → kein Durchhängen
SLOT_B = 2.5;    // Breite Schlitz (schmal!)
SLOT_H = IN_B * 0.6;  // Länge
SLOT_Z = BODEN;

$fn = 40;

// ════════════════════════════════════════════════════════
//  UNTERTEIL
// ════════════════════════════════════════════════════════
module gehaeuse_unterteil() {
    difference() {
        // ── Grundkörper mit abgerundeten Ecken ──────────
        hull() {
            for(x = [R_ECKE, AU_L - R_ECKE])
            for(y = [R_ECKE, AU_B - R_ECKE])
                translate([x, y, 0])
                    cylinder(r=R_ECKE, h=AU_H, $fn=32);
        }

        // ── Innenraum ───────────────────────────────────
        translate([WAND, WAND, BODEN])
            cube([IN_L, IN_B, H_INNEN + 0.1]);

        // ── Port-Ausschnitte ────────────────────────────

        // PWR Micro-USB (rechte kurze Seite)
        translate([PWR_X - USB_B/2, AU_B - WAND - 0.1, USB_Z])
            cube([USB_B, WAND + 0.2, USB_H]);

        // OTG Micro-USB (rechte kurze Seite)
        translate([OTG_X - USB_B/2, AU_B - WAND - 0.1, USB_Z])
            cube([USB_B, WAND + 0.2, USB_H]);

        // Mini-HDMI (linke kurze Seite)
        translate([HDMI_X - HDMI_B/2, -0.1, USB_Z])
            cube([HDMI_B, WAND + 0.2, HDMI_H]);

        // SD-Karte (lange Seite vorne, links)
        translate([-0.1, SD_X, BODEN - 0.1])
            cube([WAND + 0.2, SD_B, SD_H]);

        // ── Schraublöcher in Ecken (M2.5) ───────────────
        // Option: Gehäuse kann mit Schrauben geschlossen werden
        for(x = [L_X1, L_X2])
        for(y = [L_Y1, L_Y2])
            translate([x, y, -0.1])
                cylinder(r=1.4, h=BODEN + 0.2, $fn=16);

        // ── Lüftungsschlitze Boden (schmal, kein Support) ─
        for(i = [0:5])
            translate([WAND + 4 + i * 9, (AU_B - SLOT_H)/2, -0.1])
                cube([SLOT_B, SLOT_H, BODEN + 0.2]);
    }

    // ── Montagepfosten innen ─────────────────────────────
    // Platine liegt auf diesen Pfosten auf (Höhe = 2mm)
    for(x = [L_X1, L_X2])
    for(y = [L_Y1, L_Y2]) {
        translate([x, y, BODEN])
            cylinder(r=2.8, h=2.0, $fn=20);
        // Sackloch für M2 Schraube (optional)
        translate([x, y, BODEN - 0.1])
            cylinder(r=1.0, h=2.2, $fn=16);
    }

    // ── Clip-Nasen für Deckel (je 2× links/rechts) ───────
    for(x = [AU_L*0.28, AU_L*0.72]) {
        translate([x - 2, -0.1, AU_H - 4])
            cube([4, 1.6, 4]);
        translate([x - 2, AU_B - 1.5, AU_H - 4])
            cube([4, 1.6, 4]);
    }
}

gehaeuse_unterteil();

// ════════════════════════════════════════════════════════
//  PORT-REFERENZ
// ════════════════════════════════════════════════════════
// Ausrichtung auf dem Druckbett: Boden nach unten
// Die Öffnungen sind:
//   Kurze Seite hinten (Y=AU_B): PWR + OTG Micro-USB
//   Kurze Seite vorne (Y=0):     Mini-HDMI
//   Lange Seite links (X=0):     SD-Karten-Schlitz
