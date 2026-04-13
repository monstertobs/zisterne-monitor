# 🏺 Zisterne Monitor

**Intelligente Zisternen-Wasserstandsüberwachung mit Raspberry Pi Zero 2W**

Ein vollständiges DIY-Projekt zur Überwachung des Füllstands einer Regenwasserzisterne – mit automatischer Installation, elegantem Web-Dashboard, 3D-gedrucktem Gehäuse und Wettervorhersage für den erwarteten Regenwasserzulauf.

![Version](https://img.shields.io/badge/Version-0.5.0-blue)
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
- 🏺 **3D Glas-Zylinder** – animierte Wasserdarstellung mit Blasen und Wellen
- 💧 **Liter-Anzeige** – aktueller Inhalt, Kapazität, Zu-/Abfluss
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
- 📏 **Präzise Messung** – JSN-SR04T Ultraschallsensor (wasserdicht)

---

## 🛒 Einkaufsliste

| Bauteil | Beschreibung | Preis ca. |
|---|---|---|
| Raspberry Pi Zero 2 WH | Mit vorgelötetem GPIO-Header | ~18 € |
| JSN-SR04T | Wasserdichter Ultraschallsensor | ~5 € |
| MicroSD 32GB | SanDisk Extreme A1 | ~9 € |
| Micro-USB Netzteil 5V/2A | Für den Pi | ~8 € |
| 1 kΩ Widerstand | Für Spannungsteiler ECHO-Pin | < 1 € |
| 2 kΩ Widerstand | Für Spannungsteiler ECHO-Pin | < 1 € |
| KNX/EIB Kabel 2x2x0,8mm | Für Sensor-Verbindung (bis 5m) | ~8 € |
| **Gesamt** | | **~50 €** |

---

## 🔌 Verkabelung

```
HC-SR04 / JSN-SR04T        Spannungsteiler        Pi Zero 2 WH
──────────────────         ───────────────        ────────────
VCC   ──────────────────────────────────────────── Pin 2  (5V)
GND   ──────────────────────────────────────────── Pin 6  (GND)
TRIG  ──────────────────────────────────────────── Pin 16 (GPIO 23)
ECHO  ── 1kΩ ── Punkt A ── 2kΩ ── GND (Pin 9)
                    │
                    └───────────────────────────── Pin 18 (GPIO 24)
```

> ⚠️ **Wichtig:** Der ECHO-Pin liefert 5V – der Pi verträgt nur 3,3V!  
> Der Spannungsteiler ist **Pflicht** und schützt den GPIO-Pin vor Schäden.

---

## 🚀 Installation

### Schritt 1 – SD-Karte vorbereiten

1. **Raspberry Pi Imager** herunterladen: [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Flashen mit:
   - **Gerät:** Raspberry Pi Zero 2W
   - **OS:** Raspberry Pi OS Lite (64-bit)
   - **Einstellungen:** Hostname `zisterne`, SSH aktivieren, Benutzer `pi`
3. Nach dem Flashen die SD-Karte **neu einstecken** → `bootfs` erscheint
4. Folgende Dateien in das **Root-Verzeichnis** von `bootfs` kopieren:
   - `Software/firstboot.sh`
   - `Software/app.py`
5. `bootfs/cmdline.txt` mit **TextEdit** öffnen (Format → Als reinen Text!)  
   Ans Ende der **einzigen Zeile** anhängen *(Leerzeichen davor!)*:
   ```
   systemd.run=/boot/firmware/firstboot.sh
   ```

### Schritt 2 – Ersten Start abwarten

1. SD-Karte in den Pi einlegen, Strom anschließen
2. Nach ~30s erscheint der Hotspot **`Zisterne-Setup`** (Passwort: `zisterne123`)
3. Mit dem iPhone verbinden → Portal öffnet sich automatisch
4. WLAN-Name + Passwort eingeben → Pi verbindet sich
5. Nach ~5 Minuten ist alles fertig

### Schritt 3 – Dashboard aufrufen

```
http://zisterne.local
```
oder direkt über die IP-Adresse aus dem Router.

---

## ⚙️ Konfiguration

Nach der Installation im Browser unter **Einstellungen** konfigurieren:

| Einstellung | Beschreibung | Standard |
|---|---|---|
| Name | Anzeigename | Zisterne Garten |
| Kapazität | Maximaler Inhalt in Litern | 5.000 L |
| Tiefe | Zisternentiefe in cm | 240 cm |
| Messintervall | Sekunden zwischen Messungen | 60 s |
| Dachfläche | Fläche für Regenvorhersage | 100 m² |
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
- Schichthöhe: 0.2 mm
- Wandlinien: 4
- Infill: 20-40%
- Material: PLA (Gehäuse) oder PETG (Sensorhalterung, feuchtigkeitsbeständig)

---

## 🌐 API-Endpunkte

Das Dashboard läuft als Flask-Server und stellt folgende API bereit:

| Endpoint | Beschreibung |
|---|---|
| `GET /api/aktuell` | Aktuelle Messung |
| `GET /api/range?h=24` | Verlauf (h=Stunden, d=Tage, m=Monate) |
| `GET /api/liter` | Aktuelle Liter + Zu-/Abfluss |
| `GET /api/prognose` | Verbrauchsprognose |
| `GET /api/regen` | Erkannte Regenereignisse |
| `GET /api/woche` | Wochenverbrauch |
| `GET /api/wetter` | 7-Tage Regenvorhersage (Open-Meteo) |
| `GET /api/wifi` | WLAN-Status + Signalstärke |
| `GET /api/version` | Versionsinformation |

---

## 🏗️ Technischer Stack

```
Raspberry Pi Zero 2W
├── Raspberry Pi OS Lite 64-bit (Bookworm)
├── Python 3
│   ├── Flask          – Web-Dashboard
│   ├── APScheduler    – Automatische Messungen
│   ├── RPi.GPIO       – GPIO-Sensor-Steuerung
│   └── SQLite         – Messdaten-Datenbank
├── NetworkManager     – WLAN-Verwaltung
└── avahi-daemon       – zisterne.local mDNS
```

**Frontend:** Reines HTML/CSS/JavaScript – keine Frameworks, keine npm, läuft im Browser.

**Wetterdaten:** [Open-Meteo](https://open-meteo.com/) – kostenlos, kein API-Key, DSGVO-konform.

---

## 📁 Repository-Struktur

```
zisterne-monitor/
├── Software/
│   ├── app.py              # Flask-Webserver + Dashboard
│   └── firstboot.sh        # Automatisches Erststart-Skript
├── 3D_Druck/
│   └── SCAD/               # OpenSCAD Quelldateien
├── docs/                   # Dokumentation
├── VERSION                 # Changelog
├── .gitignore
└── README.md
```

---

## 🔄 Updates einspielen

```bash
# Vom Mac auf den Pi kopieren
scp Software/app.py pi@zisterne.local:/home/pi/zisterne/app.py

# Dienst neu starten
ssh pi@zisterne.local "sudo systemctl restart zisterne"
```

---

## 📊 Versions-Historie

Siehe [VERSION](VERSION) für den vollständigen Changelog.

| Version | Highlights |
|---|---|
| v0.5.0 | Regenvorhersage, 3D Glas-Tank, WLAN-Verwaltung |
| v0.4.x | Captive Portal WLAN, WLAN-Signalstärke |
| v0.3.x | Verbrauchsprognose, Regenerkennung, Wochenverbrauch |
| v0.2.0 | Liter-Anzeige, Kapazitäts-Einstellung |
| v0.1.x | Bugfixes, Hotspot-Fixes, Zeitzone, Erststart |
| v0.1.0 | Initiale Version |

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
🌐 [github.com/secutobs](https://github.com/secutobs)

## ☕ Support If you find this project useful and want to say thanks, feel free to send a small donation in Bitcoin: **BTC:** 1ADFsY95oPRvVQ36yWcud8zM4qzZZDqf6F No pressure – a GitHub ⭐ star is also very much appreciated!
---

*Entwickelt mit ❤️ für alle die ihre Zisterne im Blick behalten wollen.*
