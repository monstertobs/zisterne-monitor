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

**GPIO:** Beim Import-Fehler (Entwicklung auf Mac) setzt das Script `GPIO_OK = False` und Messungen geben `None` zurück – die App startet trotzdem vollständig für UI-Entwicklung.

## Versionierung

Bei jeder Änderung PATCH-Version hochzählen und Datum aktualisieren. Versionsstellen:
1. `app.py` – Docstring (Zeile ~7) und `__version__` / `__version_date__` (Zeile ~15–16)
2. `VERSION` – Changelog-Datei mit Beschreibung der Änderung
3. `README.md` – Badge-Zeile (`![Version](https://img.shields.io/badge/Version-X.Y.Z-blue)`)

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

- **Sensor:** JSN-SR04T Ultraschall (wasserdicht)
- **TRIG:** GPIO 23 (Pin 16), **ECHO:** GPIO 24 (Pin 18) – mit Spannungsteiler (1kΩ/2kΩ)
- Messung: 5 Messungen, Median (sortiert, Index 2)
- Füllstand-Formel: `(tiefe_cm - abstand_cm - min_cm) / (tiefe_cm - min_cm) * 100`

## Dashboard-Visualisierung

Die Zisterne wird als **Erdquerschnitt** dargestellt (Himmel → Gras → Erdreich). Die Positionierung der Rohre (Zulauf, Überlauf, Entnahme) erfolgt per JavaScript nach dem Rendern (`positionPipes()` in `HTML_INDEX`), da die Zisternengröße von CSS-Berechnungen abhängt. Das Wasserlevel wird über `#wf` (height-Prozent) und der Füllstandsbalken über `#fi-bar` gesteuert.
