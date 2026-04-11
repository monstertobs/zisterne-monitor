#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║   ZISTERNE MONITOR – First Boot Setup v0.7.4                   ║
# ║   Tobias Meier · admin@secutobs.com                            ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# SD-Karte vorbereiten (Mac/PC vor dem ersten Start):
#   1. firstboot.sh  → /boot/firmware/firstboot.sh  kopieren
#   2. app.py        → /boot/firmware/app.py         kopieren
#   3. cmdline.txt öffnen (Texteditor!), ans Ende der EINEN Zeile anhängen:
#      systemd.run=/boot/firmware/firstboot.sh
#   4. SD-Karte auswerfen → Pi einschalten → fertig

# ══════════════════════════════════════════════════════════════════
#  KONFIGURATION – optional anpassen
# ══════════════════════════════════════════════════════════════════
ZISTERNE_NAME="Zisterne Garten"
ZISTERNE_TIEFE_CM=240
ZISTERNE_MIN_CM=25
MESS_INTERVALL=60
SERIAL_PORT="/dev/serial0"
HOTSPOT_SSID="Zisterne-Setup"
HOTSPOT_PASS="zisterne123"
# ══════════════════════════════════════════════════════════════════

# ── Boot-Verzeichnis erkennen (Bookworm=/boot/firmware, älter=/boot) ─
if [ -d /boot/firmware ]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
fi

DONE_FLAG="${BOOT_DIR}/zisterne_setup_done"
LOG="/var/log/zisterne_firstboot.log"
PROJECT_DIR="/home/pi/zisterne"

# ── Logging ───────────────────────────────────────────────────────
mkdir -p /var/log
exec > >(tee -a "$LOG") 2>&1

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ZISTERNE MONITOR – FIRST BOOT v0.7.4      ║"
echo "║   $(date '+%Y-%m-%d %H:%M:%S')              ║"
echo "╚══════════════════════════════════════════════╝"
echo "  Boot-Dir: $BOOT_DIR"
echo ""

# ── Bereits abgeschlossen? ────────────────────────────────────────
[ -f "$DONE_FLAG" ] && { echo "✓ Setup bereits erledigt – überspringe."; exit 0; }

# ── FIX 1: NetworkManager abwarten ───────────────────────────────
# systemd.run startet früh – wir müssen auf NM warten
echo "→ Warte auf NetworkManager..."
systemctl start NetworkManager 2>/dev/null || true
for i in $(seq 1 30); do
    if systemctl is-active --quiet NetworkManager; then
        echo "✓ NetworkManager bereit (${i}×2s)"
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "⚠ NetworkManager nach 60s nicht bereit – trotzdem weiter"
    fi
done
sleep 3

# ══════════════════════════════════════════════════════════════════
#  PORTAL.PY (wird jetzt VOR Phase 1 geschrieben – kein Set-E-Problem)
# ══════════════════════════════════════════════════════════════════
mkdir -p /tmp/portal
cat > /tmp/portal/portal.py << 'PYEOF'
#!/usr/bin/env python3
"""
Zisterne WLAN-Portal
Nur Python-Standardbibliothek - kein Flask, keine externen Pakete
FIX 5/10: Portal erklärt klar dass SSID manuell eingegeben werden muss
          (Pi Zero 2W hat nur 1 WLAN-Chip – kein Scan im AP-Modus)
"""
import os, subprocess, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

DONE_FILE   = "/tmp/wlan_verbunden"
FEHLER_FILE = "/tmp/wlan_fehler"

CSS = (
    "<style>"
    ":root{--bg:#f2f2f7;--card:#fff;--tx:#1c1c1e;--mu:#8e8e93;"
    "--bl:#007aff;--sep:rgba(60,60,67,.15);--rd:#ff3b30;--gn:#34c759;}"
    "@media(prefers-color-scheme:dark){:root{"
    "--bg:#000;--card:#1c1c1e;--tx:#fff;--mu:#636366;"
    "--sep:rgba(255,255,255,.1);}}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{background:var(--bg);color:var(--tx);"
    "font-family:-apple-system,'Helvetica Neue',sans-serif;"
    "min-height:100vh;display:flex;align-items:center;"
    "justify-content:center;padding:20px;-webkit-font-smoothing:antialiased}"
    ".card{background:var(--card);border-radius:22px;padding:36px 28px;"
    "width:100%;max-width:380px;box-shadow:0 8px 40px rgba(0,0,0,.1)}"
    ".icon{font-size:3rem;text-align:center;margin-bottom:8px}"
    "h1{font-size:1.5rem;font-weight:700;text-align:center;"
    "letter-spacing:-.5px;margin-bottom:6px}"
    ".sub{font-size:.88rem;color:var(--mu);text-align:center;"
    "margin-bottom:28px;line-height:1.5}"
    ".info{background:rgba(0,122,255,.08);border-radius:12px;"
    "padding:12px 14px;font-size:.8rem;color:var(--bl);"
    "margin-bottom:20px;line-height:1.5}"
    "label{display:block;font-size:.78rem;font-weight:600;color:var(--mu);"
    "margin-bottom:6px;text-transform:uppercase;letter-spacing:.3px}"
    ".field{margin-bottom:16px}"
    "input{width:100%;padding:14px 16px;border-radius:12px;"
    "border:1.5px solid var(--sep);background:var(--bg);color:var(--tx);"
    "font-size:1rem;outline:none;-webkit-appearance:none}"
    "input:focus{border-color:var(--bl)}"
    ".btn{width:100%;padding:16px;border-radius:14px;border:none;"
    "background:var(--bl);color:#fff;font-size:1rem;font-weight:600;"
    "cursor:pointer;margin-top:6px;-webkit-appearance:none}"
    ".err{background:rgba(255,59,48,.1);color:var(--rd);"
    "border-radius:10px;padding:12px 14px;font-size:.85rem;"
    "margin-bottom:16px;text-align:center}"
    ".hint{font-size:.75rem;color:var(--mu);text-align:center;"
    "margin-top:18px;line-height:1.5}"
    ".sw{display:none;text-align:center;padding:24px 0}"
    ".sp{width:36px;height:36px;border:3px solid var(--sep);"
    "border-top-color:var(--bl);border-radius:50%;"
    "animation:sp .8s linear infinite;margin:0 auto 14px}"
    "@keyframes sp{to{transform:rotate(360deg)}}"
    ".sw p{color:var(--mu);font-size:.9rem;line-height:1.6}"
    "</style>"
)

JS = (
    "<script>"
    "function showSpin(){"
    "document.getElementById('fm').style.display='none';"
    "document.getElementById('sw').style.display='block';}"
    "</script>"
)


def verbinde_wlan(ssid, passwort):
    try:
        # Bestehende Verbindung löschen
        subprocess.run(
            ["nmcli", "connection", "delete", ssid],
            capture_output=True, timeout=10
        )
        # Verbinden
        r = subprocess.run(
            ["nmcli", "dev", "wifi", "connect", ssid,
             "password", passwort, "ifname", "wlan0"],
            capture_output=True, text=True, timeout=40
        )
        if r.returncode == 0:
            # Hotspot beenden
            subprocess.run(
                ["nmcli", "connection", "down", "Zisterne-Hotspot"],
                capture_output=True, timeout=10
            )
            with open(DONE_FILE, "w") as f:
                f.write(ssid)
        else:
            fehler = r.stderr.strip() or r.stdout.strip() or "Verbindung fehlgeschlagen"
            with open(FEHLER_FILE, "w") as f:
                f.write(fehler)
    except subprocess.TimeoutExpired:
        with open(FEHLER_FILE, "w") as f:
            f.write("Timeout – Verbindung dauerte zu lange")
    except Exception as e:
        with open(FEHLER_FILE, "w") as f:
            f.write(str(e))


def html_form(fehler=""):
    err_html = f'<div class="err">&#9888; {fehler}</div>' if fehler else ""
    return (
        "<!DOCTYPE html><html lang='de'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Zisterne – WLAN einrichten</title>"
        + CSS
        + "</head><body><div class='card'>"
        "<div class='icon'>&#x1F4E1;</div>"
        "<h1>WLAN verbinden</h1>"
        "<p class='sub'>Zisterne Monitor mit deinem<br>Heimnetzwerk verbinden</p>"
        "<div class='info'>"
        "&#8505; Gib WLAN-Name und Passwort deines<br>"
        "Heimnetzes ein. Das Gerät verbindet sich<br>"
        "danach automatisch."
        "</div>"
        + err_html
        + "<div id='fm'>"
        "<form method='POST' action='/verbinden' onsubmit='showSpin()'>"
        "<div class='field'><label>WLAN Name (SSID)</label>"
        "<input type='text' name='ssid' id='ssid' "
        "placeholder='z.B. FritzBox 7590' required "
        "autocomplete='off' autocorrect='off' "
        "autocapitalize='none' spellcheck='false'></div>"
        "<div class='field'><label>WLAN Passwort</label>"
        "<input type='password' name='pw' "
        "placeholder='Passwort eingeben' required "
        "autocomplete='new-password'></div>"
        "<button type='submit' class='btn'>Verbinden &#x2192;</button>"
        "</form>"
        "<p class='hint'>Der Hotspot schaltet sich nach<br>"
        "erfolgreicher Verbindung automatisch ab.</p>"
        "</div>"
        "<div class='sw' id='sw'>"
        "<div class='sp'></div>"
        "<p>Verbinde...<br><small>Bitte ca. 30 Sekunden warten</small></p>"
        "</div>"
        + JS
        + "</div></body></html>"
    )


def html_ok(ssid):
    return (
        "<!DOCTYPE html><html lang='de'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Verbunden!</title>"
        + CSS
        + "</head><body><div class='card' style='text-align:center'>"
        "<div class='icon'>&#x2705;</div>"
        "<h1>Verbunden!</h1>"
        "<p class='sub'>Jetzt wieder mit deinem<br>"
        f"Heimnetz <strong style='color:var(--tx)'>{ssid}</strong> verbinden</p>"
        "<div style='background:rgba(0,0,0,.04);border-radius:14px;"
        "padding:18px;margin-top:20px;font-size:.85rem;"
        "color:var(--mu);line-height:2.0;text-align:left'>"
        "<div><strong style='color:var(--tx)'>1.</strong> "
        "iPhone &#x2192; Einstellungen &#x2192; WLAN</div>"
        f"<div><strong style='color:var(--tx)'>2.</strong> "
        f"Mit <strong>{ssid}</strong> verbinden</div>"
        "<div><strong style='color:var(--tx)'>3.</strong> "
        "Browser: <strong>http://zisterne.local</strong></div>"
        "<div><strong style='color:var(--tx)'>4.</strong> "
        "Ca. 3&ndash;5 Minuten warten</div>"
        "</div></div></body></html>"
    )


def html_fehler(fehler):
    return (
        "<!DOCTYPE html><html lang='de'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Fehler</title>"
        + CSS
        + "</head><body><div class='card' style='text-align:center'>"
        "<div class='icon'>&#x274C;</div>"
        "<h1>Verbindung fehlgeschlagen</h1>"
        f"<p class='sub' style='color:var(--rd)'>{fehler}</p>"
        "<div style='margin-top:20px'>"
        "<a href='/' style='display:inline-block;padding:14px 28px;"
        "background:var(--bl);color:#fff;border-radius:14px;"
        "text-decoration:none;font-weight:600'>Erneut versuchen</a>"
        "</div></div></body></html>"
    )


# Captive Portal Detection – alle Betriebssysteme
CAPTIVE_PATHS = {
    "/hotspot-detect.html", "/generate_204", "/connecttest.txt",
    "/redirect", "/success.txt", "/ncsi.txt", "/canonical.html",
    "/library/test/success.html",
}


class Portal(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # HTTP-Logs unterdrücken

    def _redirect_home(self):
        self.send_response(302)
        self.send_header("Location", "http://192.168.4.1/")
        self.end_headers()

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        # ── iOS / macOS Captive Portal Detection ──────────────────
        # iOS fragt: GET http://captive.apple.com/hotspot-detect.html
        # Wenn Antwort ein HTTP 302 Redirect ist → iOS zeigt Portal-Popup
        # Wenn Antwort HTTP 200 + "Success" ist → iOS denkt Internet vorhanden
        # Wir antworten mit 302 → Portal-Popup erscheint automatisch
        if path in ("/hotspot-detect.html",
                    "/library/test/success.html",
                    "/bag"):
            self.send_response(302)
            self.send_header("Location", "http://192.168.4.1/")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return

        # ── Android Captive Portal Detection ──────────────────────
        # Android fragt generate_204 – erwartet HTTP 204 bei Internet
        # Wir antworten mit 302 → Android zeigt Portal-Benachrichtigung
        if path in ("/generate_204", "/connecttest.txt"):
            self.send_response(302)
            self.send_header("Location", "http://192.168.4.1/")
            self.end_headers()
            return

        # ── Windows NCSI ───────────────────────────────────────────
        if path in ("/ncsi.txt", "/redirect", "/canonical.html"):
            self.send_response(302)
            self.send_header("Location", "http://192.168.4.1/")
            self.end_headers()
            return

        # Fehlerseite anzeigen falls Verbindung fehlschlug
        if os.path.exists(FEHLER_FILE):
            fehler = open(FEHLER_FILE).read().strip()
            os.remove(FEHLER_FILE)
            self._send_html(html_form(fehler=fehler))
            return
        self._send_html(html_form())

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/verbinden":
            self._redirect_home()
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        params = parse_qs(raw)
        ssid     = params.get("ssid", [""])[0].strip()
        passwort = params.get("pw",   [""])[0].strip()

        if not ssid or not passwort:
            self._send_html(html_form("Bitte WLAN-Name und Passwort eingeben."))
            return
        if len(passwort) < 8:
            self._send_html(html_form("Das WLAN-Passwort muss mind. 8 Zeichen haben."))
            return

        threading.Thread(
            target=verbinde_wlan, args=(ssid, passwort), daemon=True
        ).start()
        self._send_html(html_ok(ssid))


if __name__ == "__main__":
    try:
        server = HTTPServer(("0.0.0.0", 80), Portal)
        print("Portal aktiv: http://192.168.4.1")
        server.serve_forever()
    except OSError as e:
        print(f"Portal-Fehler: {e}")
        # Port 80 besetzt? Versuche 8080
        server = HTTPServer(("0.0.0.0", 8080), Portal)
        print("Portal aktiv: http://192.168.4.1:8080")
        server.serve_forever()
PYEOF

# ══════════════════════════════════════════════════════════════════
#  PHASE 1 – WLAN EINRICHTEN
# ══════════════════════════════════════════════════════════════════
echo "── Phase 1: WLAN prüfen ──"

wlan_ok() { ping -c1 -W5 8.8.8.8 >/dev/null 2>&1; }

if wlan_ok; then
    echo "✓ WLAN bereits verbunden – Portal übersprungen"
else
    echo "→ Kein Internet – starte Einrichtungs-Hotspot..."

    # FIX: wpa_supplicant stoppen (verursachte 802.1X Timeout-Fehler)
    systemctl stop wpa_supplicant 2>/dev/null || true
    systemctl disable wpa_supplicant 2>/dev/null || true
    sleep 3

    # Pi Zero 2 W: BCM43436 Treiber braucht manchmal etwas länger
    # Warten bis wlan0 wirklich verfügbar ist (max 30s)
    echo "→ Warte auf wlan0 Interface..."
    for i in $(seq 1 15); do
        if ip link show wlan0 >/dev/null 2>&1; then
            echo "✓ wlan0 bereit (${i}×2s)"
            break
        fi
        sleep 2
        if [ "$i" -eq 15 ]; then
            echo "⚠ wlan0 nach 30s nicht gefunden – trotzdem weiter"
        fi
    done

    # WLAN + Interface zurücksetzen
    nmcli radio wifi on 2>/dev/null || true
    ip link set wlan0 down 2>/dev/null || true
    sleep 2
    ip link set wlan0 up 2>/dev/null || true
    sleep 4

    # Alten Hotspot entfernen
    nmcli connection delete "Zisterne-Hotspot" 2>/dev/null || true

    # Hotspot erstellen mit wifi-sec.pmf 1 (verhindert 802.1X Fehler)
    nmcli connection add \
        type wifi \
        ifname wlan0 \
        con-name "Zisterne-Hotspot" \
        autoconnect no \
        ssid "$HOTSPOT_SSID" \
        mode ap \
        ipv4.method shared \
        ipv4.addresses "192.168.4.1/24" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$HOTSPOT_PASS" \
        wifi-sec.pmf 1 \
        802-11-wireless.band bg \
        802-11-wireless.channel 6 2>&1 || true

    # Hotspot starten - bis zu 5 Versuche mit Interface-Reset
    HOTSPOT_OK=0
    for try in 1 2 3 4 5; do
        echo "  Hotspot-Start Versuch $try/5..."
        if nmcli connection up "Zisterne-Hotspot" 2>&1; then
            HOTSPOT_OK=1
            break
        fi
        echo "  Versuch $try fehlgeschlagen – Interface reset..."
        ip link set wlan0 down 2>/dev/null || true
        sleep 3
        ip link set wlan0 up 2>/dev/null || true
        sleep 5
    done

    if [ "$HOTSPOT_OK" -eq 0 ]; then
        echo "✗ Hotspot nach 5 Versuchen fehlgeschlagen – Pi startet neu..."
        sleep 15
        reboot
        exit 1
    fi

    sleep 4
    echo "✓ Hotspot '$HOTSPOT_SSID' aktiv | Passwort: $HOTSPOT_PASS"

    # Portal starten
    python3 /tmp/portal/portal.py &
    PORTAL_PID=$!
    sleep 2

    # Prüfen ob Portal läuft
    if ! kill -0 "$PORTAL_PID" 2>/dev/null; then
        echo "⚠ Portal auf Port 80 fehlgeschlagen – versuche Port 8080"
        # Port 80 könnte besetzt sein – Portal startet automatisch auf 8080
    fi

    echo ""
    echo "  ┌──────────────────────────────────────────┐"
    echo "  │  WLAN-Name:  $HOTSPOT_SSID               │"
    echo "  │  Passwort:   $HOTSPOT_PASS               │"
    echo "  │  URL:        http://192.168.4.1           │"
    echo "  │  iPhone:     WLAN → Zisterne-Setup        │"
    echo "  └──────────────────────────────────────────┘"
    echo ""

    # ── Warten auf WLAN-Verbindung (max. 15 Minuten) ─────────────
    TIMEOUT=900
    ELAPSED=0
    while [ ! -f /tmp/wlan_verbunden ] && [ "$ELAPSED" -lt "$TIMEOUT" ]; do
        sleep 5
        ELAPSED=$((ELAPSED + 5))
        # Alle 60s Status ausgeben
        if [ $((ELAPSED % 60)) -eq 0 ]; then
            echo "  → Warte auf WLAN-Eingabe... (${ELAPSED}s / ${TIMEOUT}s)"
        fi
    done

    # Portal beenden
    kill "$PORTAL_PID" 2>/dev/null || true
    nmcli connection delete "Zisterne-Hotspot" 2>/dev/null || true

    if [ ! -f /tmp/wlan_verbunden ]; then
        echo "✗ Timeout – kein WLAN eingegeben"
        echo "  Pi startet neu → Hotspot erscheint wieder"
        sleep 5
        reboot
        exit 0
    fi

    SSID_VERBUNDEN=$(cat /tmp/wlan_verbunden)
    echo "✓ WLAN-Verbindung hergestellt: $SSID_VERBUNDEN"
    sleep 5
fi

# ── Internetverbindung sicherstellen ─────────────────────────────
echo "→ Warte auf Internetverbindung..."
INET_OK=0
for i in $(seq 1 30); do
    if wlan_ok; then
        echo "✓ Internet erreichbar (${i}×5s)"
        INET_OK=1
        break
    fi
    sleep 5
done

if [ "$INET_OK" -eq 0 ]; then
    echo "✗ Keine Internetverbindung nach 150s"
    echo "  Bitte WLAN-Verbindung prüfen – Pi startet neu"
    sleep 5
    reboot
    exit 0
fi

# ══════════════════════════════════════════════════════════════════
#  SWAP – Temporärer Swap für pip install (verhindert OOM-Crash)
# ══════════════════════════════════════════════════════════════════
SWAP_FILE="/swapfile_firstboot"
if [ ! -f "$SWAP_FILE" ]; then
    echo "→ Lege temporären Swap (512 MB) an..."
    fallocate -l 512M "$SWAP_FILE" 2>/dev/null || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=512 status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" -q
    swapon "$SWAP_FILE"
    echo "✓ Swap aktiv ($(swapon --show | grep "$SWAP_FILE" | awk '{print $3}'))"
else
    echo "✓ Swap bereits vorhanden"
fi

# ══════════════════════════════════════════════════════════════════
#  PHASE 2 – PAKETE INSTALLIEREN
# ══════════════════════════════════════════════════════════════════
echo ""
echo "── Phase 2: Pakete installieren ──"
export DEBIAN_FRONTEND=noninteractive
# FIX: Systemzeit synchronisieren BEVOR apt-get
# Ohne korrekte Zeit schlagen GPG-Signaturen fehl ("Not live until...")
echo "→ Zeitzone auf Europe/Berlin setzen..."
timedatectl set-timezone Europe/Berlin 2>/dev/null ||     ln -sf /usr/share/zoneinfo/Europe/Berlin /etc/localtime 2>/dev/null || true
echo "✓ Zeitzone: $(timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone)"

echo "→ Systemzeit synchronisieren (wichtig fuer GPG-Signaturen)..."
apt-get install -y -qq ntpdate 2>/dev/null || true
ntpdate -u pool.ntp.org 2>/dev/null || ntpdate -u time.google.com 2>/dev/null || true
timedatectl set-ntp true 2>/dev/null || true
# Warte bis NTP synchronisiert (max 60s)
for i in $(seq 1 30); do
    SYNC=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || echo "no")
    if [ "$SYNC" = "yes" ]; then
        echo "✓ NTP synchronisiert (${i}×2s)"
        break
    fi
    sleep 2
done
echo "✓ Systemzeit (Berlin): $(date)"


# ── FIX 9: Timeout für apt-get ───────────────────────────────────
echo "→ apt-get update..."
if ! apt-get update -qq -o Acquire::http::Timeout=60 2>&1; then
    echo "⚠ apt-get update fehlgeschlagen – nochmal versuchen..."
    sleep 10
    apt-get update -qq 2>&1 || true
fi

echo "→ Pakete installieren..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-dev \
    sqlite3 \
    curl \
    avahi-daemon \
    avahi-utils \
    libnss-mdns \
    2>&1

if [ $? -ne 0 ]; then
    echo "✗ Paket-Installation fehlgeschlagen"
    echo "  Bitte Internetverbindung prüfen"
    exit 1
fi

# ── FIX 7: avahi korrekt konfigurieren ───────────────────────────
# /etc/nsswitch.conf für mDNS anpassen (zisterne.local funktioniert)
if grep -q "^hosts:" /etc/nsswitch.conf; then
    if ! grep "mdns4_minimal" /etc/nsswitch.conf; then
        sed -i 's/^hosts:.*/hosts: files mdns4_minimal [NOTFOUND=return] dns/' \
            /etc/nsswitch.conf
    fi
fi

systemctl enable avahi-daemon 2>/dev/null || true
systemctl restart avahi-daemon 2>/dev/null || true
echo "✓ avahi-daemon gestartet (zisterne.local)"

# ── FIX 6: pip3 mit Fehlerprüfung ────────────────────────────────
echo "→ Python-Pakete installieren..."
pip3 install --break-system-packages --quiet \
    flask \
    apscheduler \
    pyserial \
    2>&1

if [ $? -ne 0 ]; then
    echo "✗ pip3 install fehlgeschlagen"
    echo "  Versuche ohne --quiet..."
    pip3 install --break-system-packages flask apscheduler pyserial 2>&1
    if [ $? -ne 0 ]; then
        echo "✗ Python-Pakete konnten nicht installiert werden"
        exit 1
    fi
fi

echo "✓ Alle Pakete installiert"

# ══════════════════════════════════════════════════════════════════
#  PHASE 3 – PROJEKTDATEIEN
# ══════════════════════════════════════════════════════════════════
echo ""
echo "── Phase 3: Projektdateien ──"
mkdir -p "$PROJECT_DIR"

# config.json
cat > "$PROJECT_DIR/config.json" << CFGEOF
{
  "name":           "$ZISTERNE_NAME",
  "tiefe_cm":       $ZISTERNE_TIEFE_CM,
  "min_cm":         $ZISTERNE_MIN_CM,
  "intervall_sek":  $MESS_INTERVALL,
  "serial_port":    "$SERIAL_PORT",
  "warnung_leer":   20,
  "warnung_voll":   90,
  "kapazitaet_l":   5000,
  "dachflaeche_m2": 100,
  "standort_lat":   50.11,
  "standort_lon":   8.68,
  "abfluss_koeff":  0.8
}
CFGEOF
echo "✓ config.json erstellt"

# app.py von Boot-Partition kopieren
if [ -f "$BOOT_DIR/app.py" ]; then
    cp "$BOOT_DIR/app.py" "$PROJECT_DIR/app.py"
    APP_VER=$(grep -m1 '__version__' "$PROJECT_DIR/app.py" \
              | grep -o '"[^"]*"' | tr -d '"' || echo "unbekannt")
    echo "✓ app.py kopiert (v${APP_VER})"
else
    echo "✗ FEHLER: $BOOT_DIR/app.py nicht gefunden!"
    echo "  Bitte app.py auf die Boot-Partition (bootfs/) kopieren"
    echo "  und den Pi erneut starten."
    exit 1
fi

# ── FIX 3: VERSION-Datei mit korrekter Version ───────────────────
cat > "$PROJECT_DIR/VERSION" << VEREOF
Zisterne Monitor
================
Version:  0.7.0
Datum:    2026-04-06
Autor:    Tobias Meier
E-Mail:   admin@secutobs.com
VEREOF

chmod +x "$PROJECT_DIR/app.py"
chown -R pi:pi "$PROJECT_DIR"
echo "✓ Projektdateien bereit in $PROJECT_DIR"

# ══════════════════════════════════════════════════════════════════
#  PHASE 4 – SYSTEMD SERVICE
# ══════════════════════════════════════════════════════════════════
echo ""
echo "── Phase 4: Autostart einrichten ──"

# ── FIX 7: After= avahi + network-online ─────────────────────────
cat > /etc/systemd/system/zisterne.service << 'SVCEOF'
[Unit]
Description=Zisterne Monitor
Documentation=https://github.com/secutobs/zisterne
After=network-online.target avahi-daemon.service
Wants=network-online.target avahi-daemon.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/zisterne
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/python3 /home/pi/zisterne/app.py
Restart=always
RestartSec=15
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=zisterne

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable zisterne.service
systemctl start zisterne.service
sleep 6

if systemctl is-active --quiet zisterne.service; then
    echo "✓ Zisterne Monitor läuft"
else
    echo "⚠ Dienst noch nicht aktiv – startet automatisch nach dem Neustart"
    journalctl -u zisterne -n 10 --no-pager 2>/dev/null || true
fi

# ══════════════════════════════════════════════════════════════════
#  PHASE 5 – ABSCHLUSS
# ══════════════════════════════════════════════════════════════════
echo ""
echo "── Phase 5: Abschluss ──"

# ── UART für SR04M-2 aktivieren ───────────────────────────────────
echo "→ UART für SR04M-2 Sensor aktivieren..."
if ! grep -q "^enable_uart=1" "${BOOT_DIR}/config.txt" 2>/dev/null; then
    echo "enable_uart=1" >> "${BOOT_DIR}/config.txt"
    echo "✓ enable_uart=1 gesetzt"
fi
if ! grep -q "^dtoverlay=disable-bt" "${BOOT_DIR}/config.txt" 2>/dev/null; then
    echo "dtoverlay=disable-bt" >> "${BOOT_DIR}/config.txt"
    echo "✓ dtoverlay=disable-bt gesetzt (PL011 UART freigegeben)"
fi

# Serial Console aus cmdline.txt entfernen (blockiert UART)
if [ -f "${BOOT_DIR}/cmdline.txt" ]; then
    sed -i 's/ console=serial[^ ]*//g' "${BOOT_DIR}/cmdline.txt" 2>/dev/null || true
    sed -i 's/console=serial[^ ]* //g' "${BOOT_DIR}/cmdline.txt" 2>/dev/null || true
    sed -i 's/ console=ttyAMA[^ ]*//g' "${BOOT_DIR}/cmdline.txt" 2>/dev/null || true
    sed -i 's/console=ttyAMA[^ ]* //g' "${BOOT_DIR}/cmdline.txt" 2>/dev/null || true
    echo "✓ Serial Console aus cmdline.txt entfernt"
fi

# Serial Getty Service deaktivieren
systemctl disable serial-getty@ttyAMA0.service 2>/dev/null || true
systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true
echo "✓ serial-getty@ttyAMA0 deaktiviert"

# systemd.run aus cmdline.txt entfernen (Einmalig-Ausführung sicherstellen)
if grep -q "systemd.run" "${BOOT_DIR}/cmdline.txt" 2>/dev/null; then
    sed -i 's| systemd\.run=[^ ]*||g' "${BOOT_DIR}/cmdline.txt"
    echo "✓ cmdline.txt bereinigt (Setup wird nicht nochmals ausgeführt)"
fi

# Temporäre Dateien entfernen
rm -rf /tmp/portal /tmp/wlan_verbunden /tmp/wlan_fehler 2>/dev/null || true

# Swap wieder entfernen
if [ -f "/swapfile_firstboot" ]; then
    swapoff /swapfile_firstboot 2>/dev/null || true
    rm -f /swapfile_firstboot
    echo "✓ Temporärer Swap entfernt"
fi

# Fertig-Flag setzen
touch "$DONE_FLAG"
echo "✓ Fertig-Flag gesetzt: $DONE_FLAG"

# Abschluss-Ausgabe
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
APP_VER=$(grep -m1 '__version__' "$PROJECT_DIR/app.py" \
          | grep -o '"[^"]*"' | tr -d '"' 2>/dev/null || echo "0.6.0")
echo "╔══════════════════════════════════════════════════╗"
echo "║     ✓  ZISTERNE MONITOR BEREIT  v${APP_VER}          ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Dashboard:  http://zisterne.local              ║"
if [ -n "$IP" ]; then
echo "║  IP-Adresse: http://$IP             ║"
fi
echo "╠══════════════════════════════════════════════════╣"
echo "║  Nächster Schritt: Kalibrierung im Browser!     ║"
echo "║  → Tab 'Kalibrierung' → Tiefe einstellen        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Abgeschlossen: $(date)"
echo "  Log: $LOG"
echo "  Autor: Tobias Meier · admin@secutobs.com"

# Neustart damit zisterne.service sauber startet
# (systemd.run= fährt Pi sonst herunter nach dem Script)
echo '→ Neustart in 5s damit Zisterne Monitor sauber startet...'
sleep 5
reboot
