# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architektur

Die gesamte Anwendung besteht aus **einer einzigen Datei**: `Software/app.py`.

Alle HTML-Templates, CSS und JavaScript sind als Python-Strings inline definiert:
- `STYLES` – vollständiges CSS (inkl. Dark Mode, Zisterne-Querschnitt-Visualisierung)
- `WATER_JS` – Blasen-Animation im Wasserkörper
- `CHART_JS_INIT` – Chart.js Grundkonfiguration (Dark/Light Mode)
- `HTML_INDEX` – Dashboard (zusammengesetzt aus den obigen Strings + TABS)
- `HTML_KAL` – Kalibrierungsseite
- `HTML_EIN` – Einstellungsseite

Templates werden via `render_template_string()` gerendert. Es gibt keine separaten Template-Dateien.

**Daten-Stack auf dem Pi:**
- `daten.db` – SQLite, Tabelle `messungen (id, zeitpunkt, abstand, fuellstand, wasser_cm)`
- `config.json` – persistente Konfiguration, liegt neben `app.py` in `/home/pi/zisterne/`

**UART/Serial:** Beim Import-Fehler von `serial` (Entwicklung auf Mac) setzt das Script `_serial = None` und `SERIAL_OK = False` – Messungen geben `None` zurück, die App startet trotzdem vollständig für UI-Entwicklung.

## Versionierung

Bei jeder Änderung PATCH-Version hochzählen und Datum aktualisieren. Versionsstellen:
1. `app.py` – Docstring (Zeile ~7) und `__version__` / `__version_date__` (Zeile ~15–16)
2. `VERSION` – Changelog-Datei mit Beschreibung der Änderung
3. `README.md` – Badge-Zeile (`![Version](https://img.shields.io/badge/Version-X.Y.Z-blue)`)
4. `Software/firstboot.sh` – Header-Kommentar (Zeile 3 und 43)

## Deployment auf den Pi

Git ist auf dem Pi **nicht installiert**. Updates werden per `scp` übertragen:

```bash
# Aus dem Repo-Root:
scp Software/app.py pi@192.168.178.101:/home/pi/zisterne/app.py
ssh pi@192.168.178.101 "sudo systemctl restart zisterne.service"
```

Der Pi ist auch über `pi@zisterne.local` erreichbar. Die App läuft auf Port 80 (systemd-Service `zisterne.service`).

## API-Endpunkte

| Endpoint | Parameter | Beschreibung |
|---|---|---|
| `GET /api/aktuell` | – | Letzte Messung |
| `GET /api/range` | `h=`, `d=`, `m=` | Historische Daten (gruppiert) |
| `GET /api/liter` | – | Aktueller Inhalt + Zu-/Abfluss |
| `GET /api/liter/verlauf` | – | Stündliche Liter heute |
| `GET /api/prognose` | – | Verbrauchsprognose in Tagen |
| `GET /api/regen` | – | Erkannte Regenereignisse |
| `GET /api/woche` | – | Ø Verbrauch pro Wochentag |
| `GET /api/wetter` | – | 7-Tage Vorhersage via Open-Meteo |
| `GET /api/wifi` | – | WLAN-Status |

## Hardware-Konfiguration

- **Sensor:** SR04M-2 Ultraschall (wasserdicht, UART-Interface)
- **UART:** `/dev/serial0` (GPIO 15 / Pin 10 = RXD), 9600 Baud, Auto-Output-Modus
- **Spannungsteiler:** Sensor-TX (5V) → 1kΩ → Pi-RX, 2kΩ nach GND (Pflicht!)
- Messung: 0,6s Rolling-Window, `_parse_uart_frame()` mit Checksum (FF H L SUM), Median
- Füllstand-Formel: `(tiefe_cm - abstand_cm - min_cm) / (tiefe_cm - min_cm) * 100`
- Port-Management: `_open_serial()` / `_close_serial()` / `_reopen_serial()` – automatischer Reopen bei Fehler

## Dashboard-Visualisierung

Die Zisterne wird als **Erdquerschnitt** dargestellt (Himmel → Gras → Erdreich). Die Positionierung der Rohre (Zulauf, Überlauf, Entnahme) erfolgt per JavaScript nach dem Rendern (`positionPipes()` in `HTML_INDEX`), da die Zisternengröße von CSS-Berechnungen abhängt. Das Wasserlevel wird über `#wf` (height-Prozent) und der Füllstandsbalken über `#fi-bar` gesteuert.
