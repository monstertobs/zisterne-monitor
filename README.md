# 🏺 Zisterne Monitor

**Intelligente Zisternen-Wasserstandsüberwachung mit Raspberry Pi Zero 2W**

Ein vollständiges DIY-Projekt zur Überwachung des Füllstands einer Regenwasserzisterne – mit automatischer Installation, elegantem Web-Dashboard, 3D-gedrucktem Gehäuse und Wettervorhersage für den erwarteten Regenwasserzulauf.

![Version](https://img.shields.io/badge/Version-0.7.9-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20Zero%202W-red)
![License](https://img.shields.io/badge/License-MIT-green)
![Language](https://img.shields.io/badge/Python-3.x-yellow)

---

## 💡 Die Idee

Ich habe eine Regenwasserzisterne im Garten, die Wasser vom Hausdach sammelt. Das Wasser wird zum Gießen und für andere Zwecke genutzt. Das Problem: Man weiß nie genau wie voll die Zisterne ist – ohne hineinzuschauen.

Die Idee war ein **vollautomatisches, selbst gehostetes Überwachungssystem** das:
- Den Wasserstand präzise misst
- Ein elegantes Dashboard im Browser zeigt
- Auf dem eigenen Heimnetzwerk läuft (keine Cloud, keine Abos)
- Komplett selbst nachgebaut werden kann

---

## ✨ Features

### Dashboard
- 🏺 **3D Erdquerschnitt** – animierte Zisterne mit Wasserstand, Blasen und Wellen
- 💧 **Liter-Anzeige** – aktueller Inhalt, Kapazität, Zu-/Abfluss seit letzter Messung
- 🔮 **Verbrauchsprognose** – wie viele Tage reicht der Vorrat noch?
- 🌧️ **Regenvorhersage** – 7-Tage-Vorhersage mit erwartetem Zulauf in Litern
- 📅 **Wochenverbrauch** – Durchschnitt pro Wochentag
- 🌧️ **Regenereignis-Erkennung** – automatische Erkennung von Regenfällen

### Installation & Betrieb
- ⚡ **Vollautomatische Installation** – SD-Karte vorbereiten, Pi einschalten, fertig
- 📡 **Captive Portal** – WLAN-Einrichtung per Smartphone wie im Hotel
- 🌐 **zisterne.local** – erreichbar über einfache URL im Heimnetz
- 📶 **WLAN-Verwaltung** – weitere Netzwerke direkt in den Einstellungen hinzufügen

### Hardware
- 🖨️ **3D-Druck Gehäuse** – für Pi Zero 2WH, druckfertige SCAD-Dateien
- 🔧 **Sensor-Halterung** – für DN25-Rohr oder Wandmontage mit Langlöchern
- 📏 **UART-Sensor** – SR04M-2 Ultraschallsensor (wasserdicht, robuste UART-Kommunikation)

---

## 🛒 Einkaufsliste

| Bauteil | Beschreibung | Preis ca. |
|---|---|---|
| Raspberry Pi Zero 2 WH | Mit vorgelötetem GPIO-Header | ~18 € |
| SR04M-2 | Wasserdichter Ultraschallsensor mit UART | ~8 € |
| MicroSD 32GB | SanDisk Extreme A1 | ~9 € |
| Micro-USB Netzteil 5V/2A | Für den Pi | ~8 € |
| 1 kΩ Widerstand | Spannungsteiler Sensor-TX → Pi-RX | < 1 € |
| 2 kΩ Widerstand | Spannungsteiler Sensor-TX → Pi-RX | < 1 € |
| JY(ST)Y 2×2×0,8 mm | KNX/EIB Kabel für Sensor (bis 10 m) | ~10 € |
| **Gesamt** | | **~55 €** |

---

## 🔌 Verkabelung

Der SR04M-2 kommuniziert über **UART** (seriell) – kein GPIO-Triggern nötig, der Sensor sendet automatisch alle ~100 ms einen Abstandswert.

```
SR04M-2 Sensor              Spannungsteiler        Pi Zero 2 WH
──────────────              ───────────────        ────────────
VCC  ──────────────────────────────────────────── Pin 2  (5V)
GND  ──────────────────────────────────────────── Pin 6  (GND)
TX   ──── 1 kΩ ──── Punkt A ──── 2 kΩ ──── GND (Pin 9)
                        │
                        └──────────────────────── Pin 10 (GPIO 15 / RXD)
RX   ── (nicht angeschlossen – Auto-Output-Modus)
```

> ⚠️ **Wichtig:** Der Sensor-TX liefert 5 V – der Pi verträgt nur 3,3 V!
> Der Spannungsteiler (1 kΩ / 2 kΩ) ist **Pflicht** und schützt den UART-Eingang.

**Kabelempfehlung:** JY(ST)Y 2×2×0,8 mm (KNX/EIB-Kabel) – bis 10 m problemlos nutzbar.

---

## 🚀 Installation (vollständig headless)

### Schritt 1 – SD-Karte vorbereiten

1. **Raspberry Pi Imager** herunterladen: [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Flashen mit:
   - **Gerät:** Raspberry Pi Zero 2W
   - **OS:** Raspberry Pi OS Lite (64-bit, Bookworm)
   - **Einstellungen (Zahnrad ⚙️):** Hostname `zisterne`, SSH aktivieren, Benutzer `pi`, Passwort setzen
3. Nach dem Flashen SD-Karte **neu einstecken** → `bootfs` erscheint im Finder/Explorer
4. Folgende Dateien in das **Root-Verzeichnis** von `bootfs` kopieren:
   - `Software/firstboot.sh`
   - `Software/app.py`
5. `bootfs/cmdline.txt` mit einem **Texteditor** öffnen (auf dem Mac: TextEdit → Format → Als reinen Text!)
   Ans Ende der **einzigen Zeile** anhängen *(mit Leerzeichen davor!)*:
   ```
    systemd.run=/boot/firmware/firstboot.sh
   ```
   > ⚠️ Keine neue Zeile anfangen – alles muss in **einer einzigen Zeile** bleiben!

### Schritt 2 – Pi starten und WLAN einrichten

1. SD-Karte in den Pi einlegen, Strom anschließen
2. Nach ~30 Sekunden erscheint der Hotspot **`Zisterne-Setup`** (Passwort: `zisterne123`)
3. Mit dem Smartphone verbinden → das Portal öffnet sich automatisch
4. WLAN-Name und Passwort des Heimnetzes eingeben → Pi verbindet sich
5. Nach ~5 Minuten ist alles fertig

### Schritt 3 – Dashboard aufrufen

```
http://zisterne.local
```
oder direkt über die IP-Adresse aus dem Router.

> **Tipp:** Beim ersten Start gleich die **Kalibrierung** aufrufen (Tab oben) und die tatsächliche Zisternentiefe einstellen.

---

## ⚙️ Konfiguration

Nach der Installation im Browser unter **Einstellungen** konfigurieren:

| Einstellung | Beschreibung | Standard |
|---|---|---|
| Name | Anzeigename im Dashboard | Zisterne Garten |
| Kapazität | Maximaler Inhalt in Litern | 5.000 L |
| Tiefe | Zisternentiefe in cm | 240 cm |
| Min-Abstand | Toter Bereich über dem Boden | 25 cm |
| Messintervall | Sekunden zwischen Messungen | 60 s |
| Dachfläche | Fläche für Regenvorhersage | 100 m² |
| Abflusskoeffizient | Anteil Regenwasser der ankommt | 0,8 |
| Standort GPS | Für Wettervorhersage | 50.11°N, 8.68°O |

---

## 🖨️ 3D-Druck

Alle SCAD-Dateien sind in `3D_Druck/SCAD/` zu finden und direkt in **OpenSCAD** renderbar:

| Datei | Beschreibung |
|---|---|
| `1_Gehaeuse_Unterteil.scad` | Pi Zero 2WH Gehäuse Unterteil |
| `2_Gehaeuse_Deckel.scad` | Gehäuse Deckel |
| `3_Sensor_Rohrhalterung_DN25.scad` | Halterung für DN25-Rohr |
| `4_Sensor_Wandhalterung.scad` | Halterung für Betonwand (Langlöcher) |

**Druckeinstellungen:**
- Schichthöhe: 0,2 mm
- Wandlinien: 4
- Infill: 20–40 %
- Material: PLA (Gehäuse) oder PETG (Sensorhalterung, feuchtigkeitsbeständig)

---

## 🌐 API-Endpunkte

Das Dashboard läuft als Flask-Server und stellt folgende API bereit:

| Endpoint | Beschreibung |
|---|---|
| `GET /api/aktuell` | Aktuelle Messung (Abstand, Füllstand, Uhrzeit) |
| `GET /api/range?h=24` | Verlauf (h=Stunden, d=Tage, m=Monate) |
| `GET /api/liter` | Aktueller Inhalt in Litern + Zu-/Abfluss |
| `GET /api/liter/verlauf` | Stündliche Liter-Werte heute |
| `GET /api/prognose` | Verbrauchsprognose in Tagen |
| `GET /api/regen` | Erkannte Regenereignisse |
| `GET /api/woche` | Ø Verbrauch pro Wochentag |
| `GET /api/wetter` | 7-Tage Regenvorhersage (Open-Meteo) |
| `GET /api/wifi` | WLAN-Status + Signalstärke |
| `GET /api/version` | Versionsinformation |

---

## 🏗️ Technischer Stack

```
Raspberry Pi Zero 2W
├── Raspberry Pi OS Lite 64-bit (Bookworm)
├── Python 3
│   ├── Flask          – Web-Dashboard (Port 80)
│   ├── APScheduler    – Automatische Messungen (alle 60 s)
│   ├── pyserial       – UART-Kommunikation mit SR04M-2
│   └── SQLite         – Messdaten-Datenbank (daten.db)
├── NetworkManager     – WLAN-Verwaltung + Captive Portal
└── avahi-daemon       – zisterne.local mDNS
```

**Frontend:** Reines HTML/CSS/JavaScript – keine Frameworks, keine npm, läuft direkt im Browser.

**Wetterdaten:** [Open-Meteo](https://open-meteo.com/) – kostenlos, kein API-Key, DSGVO-konform.

---

## 📁 Repository-Struktur

```
zisterne-monitor/
├── Software/
│   ├── app.py              # Flask-Webserver + Dashboard (alle Templates inline)
│   └── firstboot.sh        # Automatisches Erststart-Skript (headless Setup)
├── 3D_Druck/
│   └── SCAD/               # OpenSCAD Quelldateien für Gehäuse + Halterungen
├── docs/                   # Dokumentation
├── VERSION                 # Changelog
├── .gitignore
└── README.md
```

---

## 🔄 Updates einspielen

```bash
# Vom Mac auf den Pi kopieren (Pi muss im Heimnetz sein):
scp Software/app.py pi@zisterne.local:/home/pi/zisterne/app.py

# Dienst neu starten:
ssh pi@zisterne.local "sudo systemctl restart zisterne.service"
```

---

## 📊 Versions-Historie

Siehe [VERSION](VERSION) für den vollständigen Changelog.

| Version | Highlights |
|---|---|
| v0.7.0 | UART Auto-Output-Modus, robuste Port-Verwaltung, vollständige Doku-Überarbeitung |
| v0.6.x | SR04M-2 UART Sensor, pyserial statt RPi.GPIO, Captive Portal Fixes |
| v0.5.0 | Regenvorhersage, 3D Erdquerschnitt-Visualisierung, WLAN-Verwaltung |
| v0.3.x | Verbrauchsprognose, Regenerkennung, Wochenverbrauch |
| v0.2.0 | Liter-Anzeige, Kapazitäts-Einstellung |
| v0.1.0 | Initiale Version: Dashboard, Dark Mode, SQLite |

---

## 🤝 Beitragen

Pull Requests sind willkommen! Bei größeren Änderungen bitte zuerst ein Issue öffnen.

1. Fork erstellen
2. Feature-Branch: `git checkout -b feature/mein-feature`
3. Änderungen committen: `git commit -m 'Add: mein Feature'`
4. Push: `git push origin feature/mein-feature`
5. Pull Request erstellen

---

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

## 👤 Autor

**Tobias Meier**
📧 admin(at)secutobs.com
🌐 [github.com/monstertobs](https://github.com/monstertobs)

## ☕ Support

If you find this project useful and want to say thanks, feel free to send a small donation in Bitcoin:
**BTC:** 1ADFsY95oPRvVQ36yWcud8zM4qzZZDqf6F
No pressure – a GitHub ⭐ star is also very much appreciated!

---

*Entwickelt mit ❤️ für alle, die ihre Zisterne im Blick behalten wollen.*
