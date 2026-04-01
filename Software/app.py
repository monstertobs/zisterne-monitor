#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║              ZISTERNE MONITOR                            ║
║  Raspberry Pi Zero 2W + SR04M-2 UART Ultraschallsensor  ║
╠══════════════════════════════════════════════════════════╣
║  Version:  0.6.0                                         ║
║  Datum:    2026-04-01                                    ║
║  Autor:    Tobias Meier                                  ║
║  E-Mail:   admin@secutobs.com                            ║
╚══════════════════════════════════════════════════════════╝
"""

# ── Versionsinformation ──────────────────────────────────────
__version__     = "0.6.0"
__version_date__ = "2026-04-01"
__author__      = "Tobias Meier"
__email__       = "admin@secutobs.com"
__project__     = "Zisterne Monitor"
# ─────────────────────────────────────────────────────────────

import time, sqlite3, os, json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PFAD  = os.path.join(BASE_DIR, "daten.db")
CFG_PFAD = os.path.join(BASE_DIR, "config.json")

DEFAULT_CFG = {
    "name":          "Zisterne Garten",
    "tiefe_cm":      240,
    "min_cm":        25,
    "intervall_sek": 60,
    "serial_port":   "/dev/serial0",
    "warnung_leer":  20,
    "warnung_voll":  90,
    "kapazitaet_l":  5000,
    "dachflaeche_m2": 100,
    "standort_lat":  50.11,
    "standort_lon":   8.68,
    "abfluss_koeff":  0.8,
    "plausibilitaets_schwelle_cm": 10,
}

def cfg_laden():
    if os.path.exists(CFG_PFAD):
        with open(CFG_PFAD) as f:
            return {**DEFAULT_CFG, **json.load(f)}
    return DEFAULT_CFG.copy()

def cfg_speichern(c):
    with open(CFG_PFAD,'w') as f:
        json.dump(c, f, indent=2, ensure_ascii=False)

CFG = cfg_laden()
cfg_speichern(CFG)

try:
    import serial as _serial
    _ser = _serial.Serial(CFG["serial_port"], 9600, timeout=1)
    SERIAL_OK = True
except Exception:
    _ser = None
    SERIAL_OK = False
    print("⚠  Serieller Port nicht verfügbar")

app = Flask(__name__)
scheduler = BackgroundScheduler()

def db_init():
    with sqlite3.connect(DB_PFAD) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zeitpunkt TEXT NOT NULL,
            abstand REAL, fuellstand REAL, wasser_cm REAL)""")
        c.commit()

def db_speichern(a, f, w):
    with sqlite3.connect(DB_PFAD) as c:
        c.execute("INSERT INTO messungen (zeitpunkt,abstand,fuellstand,wasser_cm) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec='seconds'), a, f, w))
        c.commit()

def db_letzte():
    with sqlite3.connect(DB_PFAD) as c:
        r = c.execute("SELECT zeitpunkt,abstand,fuellstand,wasser_cm FROM messungen ORDER BY id DESC LIMIT 1").fetchone()
    return {"zeitpunkt":r[0],"abstand":r[1],"fuellstand":r[2],"wasser_cm":r[3]} if r else {}

def db_range(stunden=None, tage=None, monate=None):
    if monate:
        seit  = (datetime.now()-timedelta(days=monate*30)).isoformat()
        group = "strftime('%Y-%m',zeitpunkt)"
    elif tage:
        seit  = (datetime.now()-timedelta(days=tage)).isoformat()
        group = "DATE(zeitpunkt)"
    elif stunden:
        seit  = (datetime.now()-timedelta(hours=stunden)).isoformat()
        group = "strftime('%Y-%m-%dT%H:%M',zeitpunkt)" if stunden<=2 else "strftime('%Y-%m-%dT%H',zeitpunkt)"
    else:
        seit  = (datetime.now()-timedelta(hours=24)).isoformat()
        group = "strftime('%Y-%m-%dT%H',zeitpunkt)"
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute(f"""
            SELECT {group} as t,
                   ROUND(AVG(fuellstand),1), ROUND(MIN(fuellstand),1),
                   ROUND(MAX(fuellstand),1), ROUND(AVG(wasser_cm),1)
            FROM messungen WHERE zeitpunkt>?
            GROUP BY t ORDER BY t ASC
        """, (seit,)).fetchall()
    return [{"t":r[0],"avg":r[1],"min":r[2],"max":r[3],"w":r[4]} for r in rows]

def db_roh(n=10):
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute("SELECT zeitpunkt,abstand,fuellstand,wasser_cm FROM messungen ORDER BY id DESC LIMIT ?",(n,)).fetchall()
    return [{"t":r[0],"a":r[1],"f":r[2],"w":r[3]} for r in rows]

def abstand_messen():
    if not SERIAL_OK or _ser is None: return None
    m=[]
    for _ in range(5):
        try:
            _ser.write(b'\x01')
            data = _ser.read(4)
            if len(data)==4 and data[0]==0xFF:
                chk = (data[0]+data[1]+data[2]) & 0xFF
                if chk==data[3]:
                    dist_mm = (data[1]<<8)|data[2]
                    m.append(dist_mm/10.0)
        except Exception:
            pass
        time.sleep(0.1)
    if len(m)<3: return None
    return sorted(m)[len(m)//2]

def fuellstand(a):
    n=CFG["tiefe_cm"]-CFG["min_cm"]; w=CFG["tiefe_cm"]-a
    return round(max(0.0,min(100.0,(w/n)*100)),1), round(max(0,w),1)

def plausibilitaet_pruefen(neuer_abstand):
    """Prüft ob eine neue Messung plausibel ist (kein Ausreißer).
    Vergleicht den neuen Wert mit dem Median der letzten 5 gespeicherten Messungen.
    Gibt False zurück wenn die Abweichung den konfigurierten Schwellwert überschreitet."""
    schwelle = CFG.get("plausibilitaets_schwelle_cm", 10)
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute("SELECT abstand FROM messungen ORDER BY id DESC LIMIT 5").fetchall()
    if len(rows) < 3:
        return True  # Zu wenig Referenzwerte → akzeptieren
    letzte_werte = [r[0] for r in rows]
    median = sorted(letzte_werte)[len(letzte_werte) // 2]
    abweichung = abs(neuer_abstand - median)
    if abweichung > schwelle:
        print(f"[PLAUSIBILITÄT] Ausreißer verworfen: {neuer_abstand:.1f}cm "
              f"(Median: {median:.1f}cm, Abweichung: {abweichung:.1f}cm > {schwelle}cm)")
        return False
    return True

def messen():
    a=abstand_messen()
    if a is None: return
    if not plausibilitaet_pruefen(a): return
    f,w=fuellstand(a); db_speichern(round(a,1),f,w)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {f}% | {w}cm | {a:.1f}cm")

STYLES = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#f0f4f8;--sf:#fff;--sf2:#f7fafc;--bd:rgba(0,0,0,0.07);--tx:#0d1b2a;--tx2:#4a5568;--mu:#94a3b8;--bl:#0ea5e9;--bdk:#0369a1;--bls:rgba(14,165,233,.10);--tl:#06b6d4;--gn:#10b981;--gns:rgba(16,185,129,.10);--am:#f59e0b;--ams:rgba(245,158,11,.10);--rd:#ef4444;--rds:rgba(239,68,68,.10);--sh1:0 1px 3px rgba(0,0,0,.06);--sh2:0 4px 16px rgba(0,0,0,.08);--sh3:0 12px 40px rgba(0,0,0,.10);--rm:18px;--rl:24px;}
@media(prefers-color-scheme:dark){:root{--bg:#070d14;--sf:#0f1923;--sf2:#162030;--bd:rgba(255,255,255,.06);--tx:#e8f0f8;--tx2:#8ba3bc;--mu:#3d5270;--bls:rgba(14,165,233,.15);--gns:rgba(16,185,129,.12);--ams:rgba(245,158,11,.12);--rds:rgba(239,68,68,.12);--sh1:0 1px 3px rgba(0,0,0,.3);--sh2:0 4px 16px rgba(0,0,0,.35);--sh3:0 12px 40px rgba(0,0,0,.5);}}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'DM Sans',-apple-system,sans-serif;font-size:15px;line-height:1.5;min-height:100vh;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px}
.hdr{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:36px}
.hdr h1{font-size:clamp(1.6rem,4vw,2.2rem);font-weight:600;letter-spacing:-.6px}
.hdr p{font-size:.85rem;color:var(--mu);margin-top:3px;font-family:'DM Mono',monospace}
.live{display:flex;align-items:center;gap:7px;padding:7px 14px;background:var(--gns);border:1px solid rgba(16,185,129,.2);border-radius:100px;font-size:.78rem;font-weight:500;color:var(--gn)}
.ldot{width:6px;height:6px;background:var(--gn);border-radius:50%;animation:lpulse 2s ease-in-out infinite}
@keyframes lpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.tabs{display:flex;gap:4px;background:var(--sf);border:1px solid var(--bd);padding:4px;border-radius:var(--rm);width:fit-content;box-shadow:var(--sh1);margin-bottom:28px}
.tab{padding:8px 18px;border-radius:calc(var(--rm) - 4px);font-size:.875rem;font-weight:500;color:var(--tx2);cursor:pointer;border:none;background:transparent;font-family:'DM Sans',sans-serif;transition:all .2s;text-decoration:none}
.tab.a{background:var(--bl);color:#fff;font-weight:600}
.tab:hover:not(.a){background:var(--sf2);color:var(--tx)}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:var(--rl);box-shadow:var(--sh3);margin-bottom:20px;animation:fu .4s ease both;overflow:hidden}
.cc{background:var(--sf);border:1px solid var(--bd);border-radius:var(--rl);box-shadow:var(--sh2);padding:24px;margin-bottom:20px;animation:fu .5s .1s ease both}
.ch{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px;gap:12px;flex-wrap:wrap}
.ct{font-size:1rem;font-weight:600;letter-spacing:-.2px}
.cs{font-size:.8rem;color:var(--mu);margin-top:2px}
.cw{position:relative;height:200px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
@media(max-width:680px){.g2{grid-template-columns:1fr}}
.tp{display:flex;gap:3px;background:var(--sf2);border:1px solid var(--bd);padding:3px;border-radius:12px}
.tpb{padding:5px 12px;border-radius:8px;font-size:.78rem;font-weight:500;color:var(--tx2);cursor:pointer;border:none;background:transparent;font-family:'DM Sans',sans-serif;transition:all .18s;white-space:nowrap}
.tpb.a{background:var(--bl);color:#fff;font-weight:600;box-shadow:0 2px 8px rgba(14,165,233,.3)}
.tpb:hover:not(.a){background:var(--sf);color:var(--tx)}
.sg{margin-bottom:8px}
.sgl{font-size:.75rem;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding:0 4px}
.sc{background:var(--sf);border:1px solid var(--bd);border-radius:var(--rl);box-shadow:var(--sh1);overflow:hidden;margin-bottom:16px}
.sr{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-bottom:1px solid var(--bd);gap:16px}
.sr:last-child{border-bottom:none}
.si{flex:1}.sl{font-size:.95rem;font-weight:500}.sd{font-size:.78rem;color:var(--mu);margin-top:3px;line-height:1.4}
.si2{display:flex;align-items:center;gap:8px;flex-shrink:0}
input[type=number],input[type=text]{width:110px;padding:9px 12px;border-radius:10px;border:1.5px solid var(--bd);background:var(--bg);color:var(--tx);font-size:.95rem;font-family:inherit;outline:none;transition:border-color .2s;text-align:right;-webkit-appearance:none}
input[type=text]{width:200px;text-align:left}
input:focus{border-color:var(--bl)}
.ul{font-size:.85rem;color:var(--mu);min-width:28px}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:10px 18px;border-radius:12px;border:none;font-size:.9rem;font-weight:600;font-family:inherit;cursor:pointer;transition:opacity .2s}
.btn:active{opacity:.75}
.bb{background:var(--bl);color:#fff}
.br{background:var(--rds);color:var(--rd)}
.bg{background:var(--gns);color:var(--gn)}
.al{padding:14px 18px;border-radius:14px;font-size:.875rem;margin-bottom:16px;font-weight:500;animation:fu .3s ease}
.alo{background:var(--gns);color:var(--gn)}
.ale{background:var(--rds);color:var(--rd)}
.cb{background:var(--bls);border-radius:16px;padding:20px 22px;margin-bottom:16px;border:1px solid rgba(14,165,233,.15)}
.cb h3{font-size:1rem;font-weight:600;margin-bottom:6px;color:var(--bl)}
.cb p{font-size:.85rem;color:var(--mu);line-height:1.5}
.clive{display:flex;align-items:flex-start;gap:24px;margin-top:14px;flex-wrap:wrap}
.clv{font-size:1.8rem;font-weight:700;letter-spacing:-1px;font-variant-numeric:tabular-nums}
.cll{font-size:.75rem;color:var(--mu);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;color:var(--mu);font-weight:500;font-size:.75rem;text-transform:uppercase;letter-spacing:.4px;padding:0 0 12px}
td{padding:11px 0;border-bottom:1px solid var(--bd);font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
td:not(:first-child){text-align:right;font-weight:500}
footer{margin-top:40px;text-align:center;font-size:.75rem;color:var(--mu);font-family:'DM Mono',monospace;border-top:1px solid var(--bd);padding-top:20px}
@keyframes fu{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
/* ── Querschnitt Zisterne ─────────────────────────────── */
.mi{display:grid;grid-template-columns:1fr 1fr}
@media(max-width:680px){.mi{grid-template-columns:1fr}}
.wp{
  position:relative;min-height:420px;overflow:hidden;
  background:linear-gradient(180deg,#c9e8f5 0%,#b8ddf0 18%,#5a9e3f 18%,#4a8a30 23%,#7a5330 23%,#6b4525 42%,#5c3a1c 70%,#4a2e12 100%);
  border-radius:var(--rl) 0 0 var(--rl);
}
@media(max-width:680px){.wp{border-radius:var(--rl) var(--rl) 0 0;min-height:360px}}
.wp::before{
  content:'';position:absolute;top:18%;left:0;right:0;height:5%;
  background:radial-gradient(ellipse 3px 6px at 8% 50%,#3d7a25 0%,transparent 100%),radial-gradient(ellipse 2px 5px at 15% 30%,#4a8a30 0%,transparent 100%),radial-gradient(ellipse 3px 7px at 22% 60%,#3d7a25 0%,transparent 100%),radial-gradient(ellipse 2px 5px at 30% 40%,#4d8f33 0%,transparent 100%),radial-gradient(ellipse 3px 6px at 38% 55%,#3d7a25 0%,transparent 100%),radial-gradient(ellipse 2px 4px at 50% 30%,#4a8a30 0%,transparent 100%),radial-gradient(ellipse 3px 7px at 62% 60%,#3d7a25 0%,transparent 100%),radial-gradient(ellipse 2px 5px at 72% 35%,#4a8a30 0%,transparent 100%),radial-gradient(ellipse 3px 6px at 82% 55%,#3d7a25 0%,transparent 100%),radial-gradient(ellipse 2px 4px at 92% 40%,#4d8f33 0%,transparent 100%);
  pointer-events:none;z-index:2;
}
.wp::after{
  content:'';position:absolute;top:23%;left:0;right:0;bottom:0;
  background:radial-gradient(ellipse 4px 3px at 7% 20%,rgba(90,50,20,.4) 0%,transparent 100%),radial-gradient(ellipse 3px 4px at 18% 45%,rgba(80,40,15,.3) 0%,transparent 100%),radial-gradient(ellipse 5px 3px at 28% 65%,rgba(70,35,12,.35) 0%,transparent 100%),radial-gradient(ellipse 3px 5px at 83% 30%,rgba(90,50,20,.4) 0%,transparent 100%),radial-gradient(ellipse 4px 3px at 90% 55%,rgba(80,40,15,.3) 0%,transparent 100%),radial-gradient(ellipse 3px 4px at 76% 70%,rgba(70,35,12,.35) 0%,transparent 100%);
  pointer-events:none;z-index:2;
}
.fill-indicator{
  position:absolute;top:7px;left:50%;transform:translateX(-50%);
  background:rgba(255,255,255,.92);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  border-radius:12px;padding:7px 16px 8px;min-width:210px;text-align:center;
  box-shadow:0 2px 12px rgba(0,0,0,.12);z-index:30;white-space:nowrap;
}
.fi-title{font-size:.7rem;color:#666;margin-bottom:5px;letter-spacing:.2px}
.fi-title strong{color:#0d1b2a}
.fi-bar{height:7px;background:#e0e0e0;border-radius:4px;overflow:hidden}
.fi-bar-inner{height:100%;background:linear-gradient(90deg,#0ea5e9,#38bdf8);border-radius:4px;transition:width 1s}
.pipe-v-left{
  position:absolute;width:10px;
  background:linear-gradient(90deg,#8a9ab0,#b8c8dc,#8a9ab0);
  border-radius:2px;box-shadow:1px 0 3px rgba(0,0,0,.2);z-index:5;
}
.pipe-v-left::after{
  content:'';position:absolute;bottom:0;left:50%;transform:translateX(-50%);
  width:3px;height:8px;background:linear-gradient(180deg,transparent,rgba(100,200,255,.8));
  border-radius:0 0 50% 50%;animation:drip 2s ease-in-out infinite;
}
@keyframes drip{0%,100%{opacity:0;transform:translateX(-50%) scaleY(0)}60%{opacity:1;transform:translateX(-50%) scaleY(1)}}
.pipe-h-left{
  position:absolute;height:10px;
  background:linear-gradient(180deg,#8a9ab0,#b8c8dc,#8a9ab0);
  border-radius:2px 0 0 2px;box-shadow:0 1px 3px rgba(0,0,0,.2);z-index:5;
}
.cist-wrap{position:absolute;left:12%;right:12%;top:21%;bottom:3%;z-index:4;}
.cist-wall{
  position:absolute;inset:0;
  border-radius:50% 50% 50% 50%/20% 20% 20% 20%;
  background:radial-gradient(ellipse at 35% 30%,#c0c8d0,#8a9299 50%,#6e7880 100%);
  border:2px solid #9aabb8;
  box-shadow:inset 0 4px 15px rgba(0,0,0,.25),inset 0 -4px 10px rgba(0,0,0,.15),0 6px 24px rgba(0,0,0,.45);
}
.cist-inner{
  position:absolute;inset:14px;
  border-radius:50% 50% 50% 50%/20% 20% 20% 20%;
  background:#071525;overflow:hidden;
  box-shadow:inset 0 2px 10px rgba(0,0,0,.5);
}
.cyl-water{
  position:absolute;bottom:0;left:0;right:0;
  background:linear-gradient(180deg,rgba(20,150,230,.9) 0%,rgba(10,100,190,.95) 35%,rgba(5,70,155,.98) 70%,rgba(2,50,130,1) 100%);
  transition:height 2s cubic-bezier(.34,1.05,.64,1);overflow:hidden;
}
.cyl-surface{
  position:absolute;top:-10px;left:-3%;right:-3%;height:20px;border-radius:50%;
  background:linear-gradient(180deg,rgba(120,215,255,.95) 0%,rgba(40,170,240,.75) 60%,transparent 100%);
  box-shadow:0 -2px 6px rgba(14,165,233,.2);animation:surf 3.5s ease-in-out infinite;
}
@keyframes surf{0%,100%{transform:scaleX(1) scaleY(1)}40%{transform:scaleX(1.01) scaleY(.85)}70%{transform:scaleX(.99) scaleY(1.1)}}
.cyl-surface::after{content:'';position:absolute;left:18%;right:38%;top:6px;height:3px;border-radius:50%;background:rgba(255,255,255,.4)}
.cyl-wg{
  position:absolute;top:0;left:12%;width:14%;bottom:0;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.04) 40%,rgba(255,255,255,.06) 50%,rgba(255,255,255,.03) 60%,transparent);
  pointer-events:none;
}
.cyl-bu{position:absolute;inset:0;overflow:hidden;z-index:3}
.bub{
  position:absolute;bottom:-8px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.4) 0%,rgba(180,230,255,.15) 40%,rgba(100,180,255,.05) 100%);
  border:1px solid rgba(255,255,255,.3);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 1px 3px rgba(0,0,0,.2);
  animation:bub3d var(--bd2,5s) ease-in infinite var(--dl,0s);
}
@keyframes bub3d{
  0%{transform:translateY(0) translateX(0) scale(1);opacity:.9}
  20%{transform:translateY(-20%) translateX(2px) scale(1.04)}
  40%{transform:translateY(-42%) translateX(-2px) scale(.97)}
  60%{transform:translateY(-62%) translateX(3px) scale(1.02);opacity:.5}
  80%{transform:translateY(-82%) translateX(-1px) scale(.95);opacity:.25}
  100%{transform:translateY(-105%) translateX(0) scale(.7);opacity:0}
}
.cist-scale{
  position:absolute;right:10px;top:0;bottom:0;
  display:flex;flex-direction:column;justify-content:space-between;
  padding:10% 0;pointer-events:none;z-index:15;
}
.csm{display:flex;align-items:center;gap:3px;font-family:'DM Mono',monospace;font-size:.52rem;color:rgba(160,210,255,.35);line-height:1;}
.csm::after{content:'';display:block;width:7px;height:1px;background:rgba(160,210,255,.2)}
.cist-label{
  position:absolute;top:12%;left:0;right:0;text-align:center;
  font-size:.65rem;font-weight:700;letter-spacing:3px;
  color:rgba(255,255,255,.3);text-transform:uppercase;pointer-events:none;z-index:15;
}
.ladder{position:absolute;width:12px;z-index:12;}
.ladder::before,.ladder::after{content:'';position:absolute;top:0;bottom:0;width:2px;background:rgba(160,200,255,.15);border-radius:1px;}
.ladder::before{left:0}.ladder::after{right:0}
.cist-manhole{
  position:absolute;left:50%;transform:translateX(-50%);
  width:58px;height:18px;
  background:linear-gradient(180deg,#bcc8d4,#8fa0ae);
  border-radius:6px 6px 3px 3px;border:1.5px solid #7a8fa0;
  box-shadow:0 3px 8px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.15);z-index:8;
}
.cist-manhole::before{content:'';position:absolute;left:6px;right:6px;top:4px;height:2px;background:rgba(0,0,0,.15);border-radius:2px;}
.cist-manhole::after{content:'';position:absolute;left:6px;right:6px;bottom:4px;height:2px;background:rgba(0,0,0,.15);border-radius:2px;}
.pipe-overflow,.pipe-extraction{
  position:absolute;right:0;height:10px;
  background:linear-gradient(180deg,#8a9ab0,#b8c8dc,#8a9ab0);
  border-radius:0 2px 2px 0;box-shadow:0 1px 3px rgba(0,0,0,.25);z-index:7;
}
.pump{
  position:absolute;z-index:8;width:52px;height:22px;border-radius:11px;
  background:linear-gradient(135deg,#6a7a8a,#4a5a6a);border:2px solid #8a9aaa;
  box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;
  font-size:.55rem;color:rgba(255,255,255,.7);font-weight:700;font-family:'DM Mono',monospace;
}
.pipe-label{
  position:absolute;background:rgba(255,255,255,.92);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);
  color:#1a2a3a;font-size:.7rem;font-weight:600;padding:4px 10px 4px 8px;border-radius:20px;
  white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.14);z-index:25;display:flex;align-items:center;gap:5px;
}
.pipe-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.wl{position:absolute;left:0;right:0;text-align:center;z-index:20;pointer-events:none;}
.wpc{
  font-size:2.6rem;font-weight:700;color:#fff;letter-spacing:-2px;line-height:1;
  text-shadow:0 0 20px rgba(14,165,233,.5),0 2px 6px rgba(0,0,0,.6);font-variant-numeric:tabular-nums;
}
.wpcu{font-size:1.2rem;font-weight:300;opacity:.7}
.wlit{font-size:.88rem;font-weight:500;color:rgba(150,215,255,.75);margin-top:3px;font-variant-numeric:tabular-nums;}
.wst{
  position:absolute;bottom:8px;left:50%;transform:translateX(-50%);
  padding:5px 16px;border-radius:100px;font-size:.76rem;font-weight:600;
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  white-space:nowrap;transition:all .5s;z-index:25;text-shadow:0 1px 2px rgba(0,0,0,.2);
}
.wok{background:rgba(16,185,129,.8);color:#fff;box-shadow:0 2px 8px rgba(16,185,129,.3)}
.wwa{background:rgba(245,158,11,.8);color:#fff;box-shadow:0 2px 8px rgba(245,158,11,.3)}
.wda{background:rgba(239,68,68,.8);color:#fff;box-shadow:0 2px 8px rgba(239,68,68,.3)}
.kp{padding:28px;display:flex;flex-direction:column;justify-content:center}
.kr{display:flex;align-items:center;justify-content:space-between;padding:15px 0;border-bottom:1px solid var(--bd)}
.kr:last-child{border-bottom:none}
.kl{font-size:.875rem;color:var(--tx2)}
.kv{font-size:1.35rem;font-weight:600;letter-spacing:-.5px;font-variant-numeric:tabular-nums}
.ku{font-size:.8rem;font-weight:400;color:var(--mu);margin-left:2px}
</style>"""

TABS = lambda a: f'''<div class="tabs">
  <a class="tab {'a' if a=='d' else ''}" href="/">Dashboard</a>
  <a class="tab {'a' if a=='k' else ''}" href="/kalibrierung">Kalibrierung</a>
  <a class="tab {'a' if a=='e' else ''}" href="/einstellungen">Einstellungen</a>
</div>'''

WATER_JS = """
(function(){
  const b=document.getElementById('bu');
  // Drei Blasen-Typen für realistische Optik
  const typen=[
    [2, 4,  7, 2.5, 5,  0,  8],
    [4, 7,  5, 5,   9,  0, 11],
    [8,12,  3, 8,  14,  0, 15],
  ];
  typen.forEach(([mn,mx,cnt,dmin,dmax,dlmin,dlmax])=>{
    for(let i=0;i<cnt;i++){
      const el=document.createElement('div');
      el.className='bub';
      const s=(mn+Math.random()*(mx-mn)).toFixed(1);
      const dur=(dmin+Math.random()*(dmax-dmin)).toFixed(1);
      const del=(dlmin+Math.random()*(dlmax-dlmin)).toFixed(1);
      const left=(8+Math.random()*80).toFixed(1);
      el.style.cssText=`width:${s}px;height:${s}px;left:${left}%;--bd2:${dur}s;--dl:${del}s`;
      b.appendChild(el);
    }
  });
})();"""

CHART_JS_INIT = """
const dk=window.matchMedia('(prefers-color-scheme:dark)').matches;
Chart.defaults.color=dk?'#3d5270':'#94a3b8';
Chart.defaults.borderColor=dk?'rgba(255,255,255,.04)':'rgba(0,0,0,.05)';
Chart.defaults.font.family="'DM Sans',sans-serif";Chart.defaults.font.size=11;
const gc2=dk?'rgba(255,255,255,.04)':'rgba(0,0,0,.04)';
const tb=dk?'#162030':'#fff'; const tt=dk?'#e8f0f8':'#0d1b2a';
const bo={responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
  plugins:{legend:{display:false},tooltip:{backgroundColor:tb,borderColor:dk?'rgba(255,255,255,.08)':'rgba(0,0,0,.07)',borderWidth:1,titleColor:tt,bodyColor:dk?'#8ba3bc':'#4a5568',padding:12,cornerRadius:10,callbacks:{label:c=>` ${c.parsed.y} %`}}},
  scales:{x:{grid:{color:gc2},ticks:{maxTicksLimit:7},border:{display:false}},y:{grid:{color:gc2},min:0,max:100,ticks:{callback:v=>v+'%',stepSize:25},border:{display:false}}},
  animation:{duration:700}};
function mkG(ctx,c1,c2){const g=ctx.createLinearGradient(0,0,0,200);g.addColorStop(0,c1);g.addColorStop(1,c2);return g;}"""

HTML_INDEX = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ cfg.name }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
""" + STYLES + """
</head>
<body><div class="wrap">
<div class="hdr">
  <div><h1>{{ cfg.name }}</h1><p id="zeit">Lade…</p></div>
  <div class="live"><span class="ldot"></span> Live</div>
</div>
""" + TABS('d') + """
<div class="card">
  <div class="mi">
    <div class="wp" id="wp">

      <!-- Fill-Indicator oben -->
      <div class="fill-indicator">
        <div class="fi-title">Zisternen-Füllstand &nbsp;<strong id="fi-pct">–%</strong></div>
        <div class="fi-bar"><div class="fi-bar-inner" id="fi-bar" style="width:0%"></div></div>
      </div>

      <!-- Zulauf-Label -->
      <div class="pipe-label" id="lbl-inlet" style="top:3%;left:2%">
        <span class="pipe-dot" style="background:#0ea5e9"></span>Zulauf von Dach
      </div>

      <!-- Zulauf-Rohr (vertikal vom Dach, horizontal in Zisterne) -->
      <div class="pipe-v-left" id="pipe-v"></div>
      <div class="pipe-h-left" id="pipe-h"></div>

      <!-- Zisterne Querschnitt -->
      <div class="cist-wrap">
        <div class="cist-wall">
          <div class="cist-inner" id="cist-inner">
            <div class="cist-label">Zisterne</div>
            <div class="cist-scale">
              <div class="csm">100%</div>
              <div class="csm">80%</div>
              <div class="csm">60%</div>
              <div class="csm">40%</div>
              <div class="csm">20%</div>
              <div class="csm">0%</div>
            </div>
            <div class="ladder" id="ladder"></div>
            <!-- Wasser-Füllung -->
            <div class="cyl-water" id="wf" style="height:0%">
              <div class="cyl-surface"></div>
              <div class="cyl-wg"></div>
              <div class="cyl-bu" id="bu"></div>
            </div>
            <!-- Prozentanzeige -->
            <div class="wl" id="wl">
              <div class="wpc" id="wpc">–<span class="wpcu">%</span></div>
              <div class="wlit" id="wlit-panel">– L</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Einstiegsschacht -->
      <div class="cist-manhole" id="cist-manhole"></div>

      <!-- Überlauf -->
      <div class="pipe-overflow" id="pipe-overflow"></div>
      <div class="pipe-label" id="lbl-overflow" style="right:2%">
        <span class="pipe-dot" style="background:#f59e0b"></span>Überlauf
      </div>

      <!-- Entnahme / Pumpe -->
      <div class="pipe-extraction" id="pipe-extraction"></div>
      <div class="pump" id="pump">Pumpe</div>
      <div class="pipe-label" id="lbl-extraction" style="right:2%">
        <span class="pipe-dot" style="background:#10b981"></span>Entnahme
      </div>

      <!-- Status Badge -->
      <div class="wst wok" id="wst">✓ Normal</div>
    </div>
    <div class="kp">
      <div class="kr"><span class="kl">Inhalt</span><span class="kv" id="kv-liter" style="color:var(--bl);font-size:1.6rem">–<span class="ku">L</span></span></div>
      <div class="kr"><span class="kl">Kapazität</span><span class="kv" style="font-size:1rem">{{ cfg.kapazitaet_l }}<span class="ku">L max</span></span></div>
      <div class="kr"><span class="kl" id="kl-delta">Δ letzte Messung</span><span class="kv" id="kv-delta" style="font-size:1.1rem">–<span class="ku">L</span></span></div>
      <div class="kr"><span class="kl">Wasserstand</span><span class="kv" id="kvc">–<span class="ku">cm</span></span></div>
      <div class="kr"><span class="kl">Letzte Messung</span><span class="kv" style="font-size:.9rem;letter-spacing:-.3px" id="kvz">–</span></div>
      <div class="kr"><span class="kl">Status</span><span class="kv" style="font-size:.9rem" id="kvs"><span style="padding:4px 12px;background:var(--gns);color:var(--gn);border-radius:100px;font-weight:500">–</span></span></div>
    </div>
  </div>
</div>

<div class="cc">
  <div class="ch"><div><div class="ct">24 Stunden</div><div class="cs">Stündlicher Füllstand</div></div></div>
  <div class="cw"><canvas id="c24"></canvas></div>
</div>

<div class="g2">
  <!-- Prognose Card -->
  <div class="cc" style="padding:22px">
    <div class="ct" style="margin-bottom:16px">🔮 Prognose</div>
    <div style="text-align:center;padding:8px 0">
      <div id="prog-tage" style="font-size:3rem;font-weight:700;letter-spacing:-2px;color:var(--bl);font-variant-numeric:tabular-nums">–</div>
      <div style="font-size:.85rem;color:var(--mu);margin-top:4px">Tage Vorrat</div>
    </div>
    <div style="border-top:1px solid var(--bd);margin-top:14px;padding-top:12px">
      <div style="display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:6px">
        <span style="color:var(--mu)">Ø Verbrauch/Tag</span>
        <span id="prog-verbr" style="font-weight:600">– L</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.82rem">
        <span style="color:var(--mu)">Datenbasis</span>
        <span id="prog-basis" style="font-weight:600">– Tage</span>
      </div>
    </div>
  </div>

  <!-- Regen Card -->
  <div class="cc" style="padding:22px">
    <div class="ct" style="margin-bottom:14px">🌧️ Letzter Zufluss</div>
    <div id="regen-liste" style="font-size:.85rem">
      <div style="color:var(--mu);text-align:center;padding:16px 0">Keine Daten</div>
    </div>
  </div>
</div>

<!-- Wochenverbrauch -->
<div class="cc">
  <div class="ch">
    <div><div class="ct">📅 Wochenverbrauch</div><div class="cs">Durchschnitt pro Wochentag (letzte 4 Wochen)</div></div>
  </div>
  <div class="cw"><canvas id="cwoche"></canvas></div>
</div>

<!-- Regenvorhersage -->
<div class="cc" id="cc-wetter">
  <div class="ch">
    <div>
      <div class="ct">🌧️ Regenvorhersage & Zulauf</div>
      <div class="cs" id="wetter-sub">7 Tage · Dachfläche {{ cfg.dachflaeche_m2 }} m²</div>
    </div>
    <div id="wetter-total" style="text-align:right">
      <div style="font-size:1.3rem;font-weight:700;color:var(--bl);letter-spacing:-.5px" id="wetter-total-l">–</div>
      <div style="font-size:.75rem;color:var(--mu)">erwartet gesamt</div>
    </div>
  </div>
  <!-- 7-Tage Tabelle -->
  <div id="wetter-tage" style="display:flex;flex-direction:column;gap:0">
    <div style="color:var(--mu);font-size:.85rem;padding:12px 0;text-align:center">Lade Wetterdaten...</div>
  </div>
  <div style="margin-top:14px;padding:12px 14px;background:var(--sf2);border-radius:12px;
       font-size:.75rem;color:var(--mu);line-height:1.6">
    <strong style="color:var(--tx2)">Formel:</strong>
    Niederschlag × {{ cfg.dachflaeche_m2 }} m² × {{ cfg.abfluss_koeff }} (Abfluss) = Liter
    · Quelle: Open-Meteo
  </div>
</div>

<div class="cc">
  <div class="ch">
    <div><div class="ct">Inhalt heute</div><div class="cs">Liter pro Stunde</div></div>
  </div>
  <div class="cw"><canvas id="cliter"></canvas></div>
</div>

<div class="cc">
  <div class="ch">
    <div><div class="ct" id="rt">Verlauf</div><div class="cs" id="rs">Zeitraum wählen</div></div>
    <div class="tp">
      <button class="tpb" onclick="setR('1h',this)">1 Std</button>
      <button class="tpb a" onclick="setR('24h',this)">24 Std</button>
      <button class="tpb" onclick="setR('7d',this)">7 Tage</button>
      <button class="tpb" onclick="setR('30d',this)">Monat</button>
      <button class="tpb" onclick="setR('1y',this)">Jahr</button>
    </div>
  </div>
  <div class="cw"><canvas id="cr"></canvas></div>
</div>

<footer>
  {{ cfg.name }} · Raspberry Pi Zero 2W · Alle {{ cfg.intervall_sek }} s<br>
  <span style="opacity:.6">v{{ version }} · {{ version_date }} · {{ author }} · <a href="mailto:{{ email }}" style="color:inherit">{{ email }}</a></span>
</footer>
</div>
<script>""" + WATER_JS + CHART_JS_INIT + """
const x24=document.getElementById('c24').getContext('2d');
const g24=mkG(x24,'rgba(14,165,233,.2)','rgba(14,165,233,0)');
const c24=new Chart(x24,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#0ea5e9',backgroundColor:g24,borderWidth:2.5,fill:true,tension:.45,pointRadius:0,pointHoverRadius:5,pointHoverBackgroundColor:'#0ea5e9',pointHoverBorderColor:'#fff',pointHoverBorderWidth:2}]},options:{...bo}});
// Liter-Chart
const xliter=document.getElementById('cliter').getContext('2d');
const gliter=mkG(xliter,'rgba(16,185,129,.25)','rgba(16,185,129,0)');
const cliter=new Chart(xliter,{type:'bar',data:{labels:[],datasets:[{data:[],backgroundColor:function(ctx){const v=ctx.dataset.data[ctx.dataIndex]||0;const max=Math.max(...ctx.dataset.data.filter(x=>x!=null),1);return v/max>0.7?'rgba(14,165,233,.8)':'rgba(16,185,129,.7)';},borderColor:'rgba(16,185,129,1)',borderWidth:1.5,borderRadius:6}]},options:{...bo,scales:{...bo.scales,y:{...bo.scales.y,min:0,max:undefined,ticks:{callback:v=>v+' L',stepSize:undefined}}},plugins:{...bo.plugins,tooltip:{...bo.plugins.tooltip,callbacks:{label:c=>` ${c.parsed.y} L`}}}}});

const xr=document.getElementById('cr').getContext('2d');
const gr=mkG(xr,'rgba(6,182,212,.2)','rgba(6,182,212,0)');
const cr=new Chart(xr,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#06b6d4',backgroundColor:gr,borderWidth:2.5,fill:true,tension:.45,pointRadius:0,pointHoverRadius:5,pointHoverBackgroundColor:'#06b6d4',pointHoverBorderColor:'#fff',pointHoverBorderWidth:2}]},options:{...bo}});
const WL={{ cfg.warnung_leer }},WV={{ cfg.warnung_voll }};
function upW(p, liter){
  // Liter-Anzeige aktualisieren (immer wenn Liter übergeben)
  const wlp=document.getElementById('wlit-panel');
  if(wlp && liter!=null) wlp.textContent=Math.round(liter).toLocaleString('de-DE')+' L';

  // Wenn kein Prozentwert → nur Liter updaten, sonst alles
  if(p==null || isNaN(p)) return;

  // 3D Zylinder Wasserhöhe
  const wf=document.getElementById('wf');
  if(wf) wf.style.height=p+'%';

  // Prozentzahl
  document.getElementById('wpc').innerHTML=
    Math.round(p)+'<span class="wpcu">%</span>';

  // Fill-Indicator Bar + Prozenttext
  const fb=document.getElementById('fi-bar');if(fb)fb.style.width=p+'%';
  const fp=document.getElementById('fi-pct');if(fp)fp.textContent=Math.round(p)+'%';

  // Status-Badge
  const ws=document.getElementById('wst');
  const ks=document.getElementById('kvs');
  let st,sc,kb,kc;
  if(p>WV){st='▲ Fast voll';sc='wst wok';kb='var(--bls)';kc='var(--bl)';}
  else if(p<15){st='⚠ Kritisch';sc='wst wda';kb='var(--rds)';kc='var(--rd)';}
  else if(p<WL){st='⚠ Fast leer';sc='wst wwa';kb='var(--ams)';kc='var(--am)';}
  else{st='✓ Normal';sc='wst wok';kb='var(--gns)';kc='var(--gn)';}
  if(ws){ws.textContent=st;ws.className=sc;}
  if(ks) ks.innerHTML=`<span style="padding:4px 12px;background:${kb};color:${kc};border-radius:100px;font-weight:500">${st}</span>`;
}
const RC={'1h':{t:'Letzte Stunde',s:'Minutenwerte',p:'?h=1'},'24h':{t:'24 Stunden',s:'Stündlich',p:'?h=24'},'7d':{t:'7 Tage',s:'6h-Intervall',p:'?d=7'},'30d':{t:'Letzter Monat',s:'Tageswerte',p:'?d=30'},'1y':{t:'Letztes Jahr',s:'Monatlich',p:'?m=12'}};
async function setR(r,btn){
  document.querySelectorAll('.tpb').forEach(b=>b.classList.remove('a'));
  if(btn)btn.classList.add('a');
  const c=RC[r]; document.getElementById('rt').textContent=c.t; document.getElementById('rs').textContent=c.s;
  try{const d=await fetch('/api/range'+c.p).then(r=>r.json());
    if(d.length){cr.data.labels=d.map(x=>x.t.slice(0,16).replace('T',' '));cr.data.datasets[0].data=d.map(x=>x.avg);cr.update('none');}
  }catch(e){}
}
async function load(){
  try{
    const a=await fetch('/api/aktuell').then(r=>r.json());
    if(a&&a.fuellstand!=null){
      upW(parseFloat(a.fuellstand), null);
      const kvc=document.getElementById('kvc');
      if(kvc) kvc.innerHTML=`${a.wasser_cm}<span class="ku">cm</span>`;
      const kvd=document.getElementById('kvd');
      if(kvd) kvd.innerHTML=`${a.abstand}<span class="ku">cm</span>`;
      const dt=new Date(a.zeitpunkt);
      const kvz=document.getElementById('kvz');
      if(kvz) kvz.textContent=dt.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'})+' Uhr';
      const zeitEl=document.getElementById('zeit');
      if(zeitEl) zeitEl.textContent='Zuletzt: '+dt.toLocaleString('de-DE');
    }
    const h=await fetch('/api/range?h=24').then(r=>r.json());
    if(h.length){c24.data.labels=h.map(x=>x.t.slice(11,16));c24.data.datasets[0].data=h.map(x=>x.avg);c24.update('none');}
    // Liter API
    const lit=await fetch('/api/liter').then(r=>r.json());
    if(lit){
      document.getElementById('kv-liter').innerHTML=`${lit.liter}<span class="ku">L</span>`;
      upW(null, lit.liter);  // Liter-Anzeige im Tank aktualisieren
      const deltaEl=document.getElementById('kv-delta');
      const labelEl=document.getElementById('kl-delta');
      if(lit.richtung==='zufluss'){
        deltaEl.innerHTML=`<span style="color:var(--bl)">▲ +${lit.delta_l}</span><span class="ku">L</span>`;
        labelEl.textContent='Zugeflossen';
      } else if(lit.richtung==='abfluss'){
        deltaEl.innerHTML=`<span style="color:var(--orange)">▼ -${lit.delta_l}</span><span class="ku">L</span>`;
        labelEl.textContent='Abgeflossen';
      } else {
        deltaEl.innerHTML=`<span style="color:var(--mu)">= ${lit.delta_l}</span><span class="ku">L</span>`;
        labelEl.textContent='Δ letzte Messung';
      }
    }
    // Liter-Verlauf Graph
    const lv=await fetch('/api/liter/verlauf').then(r=>r.json());
    if(lv.length){cliter.data.labels=lv.map(x=>x.h);cliter.data.datasets[0].data=lv.map(x=>x.liter);cliter.update('none');}
  }catch(e){console.error(e);}
}
// Wochenverbrauch-Chart
const xwoche=document.getElementById('cwoche').getContext('2d');
const cwoche=new Chart(xwoche,{type:'bar',
  data:{labels:['Mo','Di','Mi','Do','Fr','Sa','So'],
    datasets:[{data:[0,0,0,0,0,0,0],
      backgroundColor:['rgba(14,165,233,.75)','rgba(14,165,233,.75)','rgba(14,165,233,.75)','rgba(14,165,233,.75)','rgba(16,185,129,.75)','rgba(16,185,129,.75)','rgba(245,158,11,.75)'],
      borderRadius:6,borderSkipped:false,borderWidth:0}]},
  options:{...bo,scales:{...bo.scales,y:{...bo.scales.y,min:0,max:undefined,ticks:{callback:v=>v+' L'}}},
    plugins:{...bo.plugins,tooltip:{...bo.plugins.tooltip,callbacks:{label:c=>` ${c.parsed.y} L`}}}}});

async function loadExtra(){
  try{
    const pr=await fetch('/api/prognose').then(r=>r.json());
    if(pr){
      const t=document.getElementById('prog-tage');
      if(pr.prognose_tage!==null&&pr.prognose_tage!==undefined){
        t.textContent=pr.prognose_tage;
        t.style.color=pr.prognose_tage<7?'var(--rd)':pr.prognose_tage<14?'var(--am)':'var(--bl)';
      }else{t.textContent='–';}
      document.getElementById('prog-verbr').textContent=pr.verbrauch_l_tag+' L';
      document.getElementById('prog-basis').textContent=pr.datenbasis_tage+' Tage';
    }
    const re=await fetch('/api/regen').then(r=>r.json());
    const rl=document.getElementById('regen-liste');
    if(re&&re.length>0){
      rl.innerHTML=re.slice(0,4).map(ev=>{
        const d=new Date(ev.zeitpunkt);
        const ds=d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'});
        const ts=d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
        return '<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--bd);font-size:.82rem"><span style="color:var(--mu)">'+ds+' '+ts+'</span><span style="font-weight:600;color:var(--bl)">+'+ev.zufluss_l+' L</span></div>';
      }).join('');
    }else{
      rl.innerHTML='<div style="color:var(--mu);text-align:center;padding:16px 0;font-size:.85rem">Noch kein Zufluss erkannt</div>';
    }
    const wo=await fetch('/api/woche').then(r=>r.json());
    if(wo&&wo.length>0){cwoche.data.datasets[0].data=wo.map(x=>x.verbrauch_l);cwoche.update('none');}
    // Wettervorhersage
    const wt=await fetch('/api/wetter').then(r=>r.json());
    if(wt&&wt.ok&&wt.tage.length>0){
      document.getElementById('wetter-total-l').textContent=
        wt.total_liter.toLocaleString('de-DE')+' L';
      const tageEl=document.getElementById('wetter-tage');
      const tage_de=['So','Mo','Di','Mi','Do','Fr','Sa'];
      tageEl.innerHTML=wt.tage.map((t,i)=>{
        const d=new Date(t.datum);
        const wt_name=i===0?'Heute':i===1?'Morgen':tage_de[d.getDay()]+'. '+d.getDate()+'.';
        const probColor=t.prob>60?'var(--bl)':t.prob>30?'var(--am)':'var(--mu)';
        const barW=Math.min(100,t.mm*8);  // Max bei ~12mm
        return `<div style="display:flex;align-items:center;gap:10px;padding:10px 0;
                     border-bottom:1px solid var(--bd);font-size:.85rem">
          <span style="font-size:1.3rem;width:28px;text-align:center">${t.icon}</span>
          <span style="width:52px;font-weight:${i<2?'600':'400'};color:var(--tx)">${wt_name}</span>
          <div style="flex:1;display:flex;align-items:center;gap:6px">
            <div style="flex:1;height:6px;background:var(--bd);border-radius:3px;overflow:hidden">
              <div style="height:100%;width:${barW}%;background:var(--bl);border-radius:3px;
                          transition:width .6s;opacity:${0.4+t.prob/160}"></div>
            </div>
            <span style="font-family:'DM Mono',monospace;font-size:.75rem;color:${probColor};
                         min-width:32px;text-align:right">${t.prob}%</span>
          </div>
          <span style="font-family:'DM Mono',monospace;font-size:.8rem;color:var(--mu);
                       min-width:38px;text-align:right">${t.mm} mm</span>
          <span style="font-weight:600;color:${t.liter>0?'var(--bl)':'var(--mu)'};
                       min-width:58px;text-align:right;font-size:.82rem">
            ${t.liter>0?'+'+t.liter.toLocaleString('de-DE')+' L':'–'}
          </span>
        </div>`;
      }).join('');
    } else if(wt&&!wt.ok){
      const el=document.getElementById('wetter-tage');
      if(el) el.innerHTML='<div style="color:var(--mu);font-size:.85rem;padding:12px 0;text-align:center">Keine Internetverbindung für Wetterdaten</div>';
    }
  }catch(e){console.error(e);}
}

load();loadExtra();
setInterval(load,{{ cfg.intervall_sek }}000);
setInterval(loadExtra,300000);
setTimeout(()=>setR('24h',document.querySelector('.tpb.a')),400);
// Rohre + Leiter positionieren nach Render
function positionPipes(){
  const wp=document.getElementById('wp');
  const ci=document.getElementById('cist-inner');
  if(!wp||!ci)return;
  const wpr=wp.getBoundingClientRect();
  const cir=ci.getBoundingClientRect();
  const relT=cir.top-wpr.top,relL=cir.left-wpr.left;
  const relR=wpr.right-cir.right;
  const ciH=cir.height,ciW=cir.width;
  // Zulauf vertikal
  const pv=document.getElementById('pipe-v');
  const inletY=relT+ciH*0.38;
  if(pv){pv.style.left=(relL-8)+'px';pv.style.top='0';pv.style.height=inletY+'px';}
  // Zulauf horizontal
  const ph=document.getElementById('pipe-h');
  if(ph){ph.style.top=(inletY-5)+'px';ph.style.left='0';ph.style.width=(relL+2)+'px';}
  // Überlauf
  const ovY=relT+ciH*0.13;
  const pov=document.getElementById('pipe-overflow');
  if(pov){pov.style.top=(ovY-5)+'px';pov.style.width=(relR+6)+'px';}
  const lov=document.getElementById('lbl-overflow');
  if(lov){lov.style.top=(ovY-14)+'px';lov.style.bottom='auto';}
  // Entnahme
  const exY=relT+ciH*0.84;
  const pex=document.getElementById('pipe-extraction');
  if(pex){pex.style.top=(exY-5)+'px';pex.style.width=(relR+6)+'px';}
  const pmp=document.getElementById('pump');
  if(pmp){pmp.style.left=(relL+ciW*0.45)+'px';pmp.style.top=(relT+ciH*0.78)+'px';}
  const lex=document.getElementById('lbl-extraction');
  if(lex){lex.style.top=(exY-14)+'px';lex.style.bottom='auto';}
  // Schacht-Deckel
  const mh=document.getElementById('cist-manhole');
  if(mh){mh.style.top=(relT-14)+'px';}
  // Prozentanzeige (über der Wasserlinie)
  const wf=document.getElementById('wf');
  const wll=document.getElementById('wl');
  if(wf&&wll){
    const h=parseFloat(wf.style.height)||0;
    const waterTop=relT+ciH*(1-h/100);
    wll.style.top=(waterTop+ciH*h/100*0.3)+'px';
    wll.style.bottom='auto';
  }
  // Leiter-Sprossen
  const ldr=document.getElementById('ladder');
  if(ldr&&!ldr.dataset.init){
    ldr.dataset.init='1';
    ldr.style.left=(relL+ciW*0.72)+'px';
    ldr.style.top=(relT+ciH*0.06)+'px';
    ldr.style.height=(ciH*0.86)+'px';
    ldr.style.position='absolute';
    const rungs=Math.floor(ciH*0.86/22);
    for(let i=0;i<rungs;i++){
      const r=document.createElement('div');
      r.style.cssText='position:absolute;left:0;right:0;top:'+Math.round(i/rungs*100)+'%;height:1px;background:rgba(160,200,255,.12)';
      ldr.appendChild(r);
    }
  }
}
window.addEventListener('load',positionPipes);
window.addEventListener('resize',positionPipes);
</script></body></html>"""

HTML_KAL = """<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalibrierung – {{ cfg.name }}</title>""" + STYLES + """</head>
<body><div class="wrap">
<div class="hdr"><div><h1>{{ cfg.name }}</h1><p>Kalibrierung</p></div></div>
""" + TABS('k') + """
{% if meldung %}<div class="al alo">✓ {{ meldung }}</div>{% endif %}
{% if fehler  %}<div class="al ale">⚠ {{ fehler }}</div>{% endif %}
<div class="cb">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div>
      <h3>📡 Live-Sensorwerte</h3>
      <p id="live-status-txt" style="color:var(--mu)">Gestoppt – Button drücken zum Starten</p>
    </div>
    <button id="live-toggle-btn" onclick="toggleLive()"
      style="display:flex;align-items:center;gap:8px;padding:10px 20px;
             border-radius:100px;border:none;font-size:.9rem;font-weight:600;
             background:var(--gns);color:var(--gn);cursor:pointer;
             border:1.5px solid rgba(16,185,129,.3);font-family:inherit;
             transition:all .2s;white-space:nowrap">
      <span id="live-dot" style="width:8px;height:8px;border-radius:50%;background:var(--gn);display:inline-block"></span>
      <span id="live-btn-txt">Live starten</span>
    </button>
  </div>
  <div class="clive" style="margin-top:16px">
    <div><div class="clv" id="la">–<span style="font-size:1rem;color:var(--mu)"> cm</span></div><div class="cll">Abstand</div></div>
    <div><div class="clv" id="lf">–<span style="font-size:1rem;color:var(--mu)"> %</span></div><div class="cll">Füllstand</div></div>
    <div><div class="clv" id="lw">–<span style="font-size:1rem;color:var(--mu)"> cm</span></div><div class="cll">Wasser</div></div>
  </div>
</div>
<div class="sg"><div class="sgl">Schritt 1 – Zisternentiefe</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Aktuell</div><div class="sd">Tiefe: <strong>{{ cfg.tiefe_cm }} cm</strong></div></div></div>
  <div class="sr" style="background:var(--bls)">
    <div class="si"><div class="sl">Automatisch übernehmen</div><div class="sd">Zisterne leeren → Button drücken</div></div>
    <form method="POST" action="/kalibrierung/setze_leer"><button type="submit" class="btn bb">Jetzt übernehmen</button></form>
  </div>
  <div class="sr"><div class="si"><div class="sl">Manuell eingeben</div></div>
    <form method="POST" action="/kalibrierung/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="tiefe_cm">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.tiefe_cm }}" min="10" max="1000"><span class="ul">cm</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form>
  </div>
</div></div>
<div class="sg"><div class="sgl">Schritt 2 – Blindbereich</div><div class="sc"><div class="sr">
  <div class="si"><div class="sl">Mindestabstand Sensor → Wasser</div><div class="sd">Standard 25 cm</div></div>
  <form method="POST" action="/kalibrierung/speichern" style="display:flex;align-items:center;gap:8px">
    <input type="hidden" name="feld" value="min_cm">
    <div class="si2"><input type="number" name="wert" value="{{ cfg.min_cm }}" min="5" max="100"><span class="ul">cm</span></div>
    <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
  </form>
</div></div></div>
<div class="sg"><div class="sgl">Schritt 3 – Testmessung</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Sofortige Messung</div></div>
    <form method="POST" action="/kalibrierung/testmessung"><button type="submit" class="btn bg">Jetzt messen</button></form>
  </div>
  {% if letzter %}
  <div class="sr">
    <div class="si"><div class="sl">Letztes Ergebnis</div><div class="sd" style="font-family:'DM Mono',monospace">{{ letzter.zeitpunkt[:16].replace('T',' ') }}</div></div>
    <div style="text-align:right"><div style="font-size:1.3rem;font-weight:600;font-variant-numeric:tabular-nums">{{ letzter.fuellstand }}<span style="font-size:.85rem;color:var(--mu)"> %</span></div><div style="font-size:.8rem;color:var(--mu)">{{ letzter.wasser_cm }} cm</div></div>
  </div>{% endif %}
</div></div>
<div class="sg"><div class="sgl">Letzte 10 Messungen</div>
<div class="cc" style="padding:0 24px"><table>
  <thead><tr><th>Zeitpunkt</th><th>Abstand</th><th>Wasser</th><th>Füllstand</th></tr></thead>
  <tbody>{% for r in roh %}
  <tr><td style="color:var(--mu);font-size:.8rem;font-family:'DM Mono',monospace">{{ r.t[:16].replace('T',' ') }}</td><td>{{ r.a }} cm</td><td>{{ r.w }} cm</td><td><strong>{{ r.f }} %</strong></td></tr>
  {% endfor %}{% if not roh %}<tr><td colspan="4" style="color:var(--mu);text-align:center;padding:20px">Noch keine Messungen</td></tr>{% endif %}
  </tbody></table></div></div>
<footer>{{ cfg.name }} · v{{ version }} · {{ author }} · <a href="mailto:{{ email }}" style="color:inherit">{{ email }}</a></footer></div>
<script>
let liveAktiv = false;
let liveTimer = null;
let liveMsgTimer = null;

async function liveMessen(){
  try{
    const d=await fetch('/api/sensor').then(r=>r.json());
    if(d&&d.abstand){
      document.getElementById('la').innerHTML=`${d.abstand}<span style="font-size:1rem;color:var(--mu)"> cm</span>`;
      document.getElementById('lf').innerHTML=`${d.fuellstand}<span style="font-size:1rem;color:var(--mu)"> %</span>`;
      document.getElementById('lw').innerHTML=`${d.wasser_cm}<span style="font-size:1rem;color:var(--mu)"> cm</span>`;
      // Countdown-Text aktualisieren
      let sek = 5;
      clearInterval(liveMsgTimer);
      document.getElementById('live-status-txt').textContent = 'Nächste Messung in 5s...';
      liveMsgTimer = setInterval(()=>{
        sek--;
        if(sek > 0){
          document.getElementById('live-status-txt').textContent = `Nächste Messung in ${sek}s...`;
        } else {
          clearInterval(liveMsgTimer);
        }
      }, 1000);
    }
  }catch(e){}
}

function toggleLive(){
  const btn = document.getElementById('live-toggle-btn');
  const txt = document.getElementById('live-btn-txt');
  const dot = document.getElementById('live-dot');
  const statusTxt = document.getElementById('live-status-txt');

  if(!liveAktiv){
    // Einschalten
    liveAktiv = true;
    txt.textContent = 'Live stoppen';
    btn.style.background = 'var(--rds)';
    btn.style.color = 'var(--rd)';
    btn.style.borderColor = 'rgba(239,68,68,.3)';
    dot.style.background = 'var(--rd)';
    dot.style.animation = 'lpulse 1s ease-in-out infinite';
    statusTxt.textContent = 'Live-Modus aktiv – misst alle 5 Sekunden';
    statusTxt.style.color = 'var(--gn)';
    liveMessen(); // Sofort erste Messung
    liveTimer = setInterval(liveMessen, 5000);
  } else {
    // Ausschalten
    liveAktiv = false;
    clearInterval(liveTimer);
    clearInterval(liveMsgTimer);
    liveTimer = null;
    txt.textContent = 'Live starten';
    btn.style.background = 'var(--gns)';
    btn.style.color = 'var(--gn)';
    btn.style.borderColor = 'rgba(16,185,129,.3)';
    dot.style.background = 'var(--gn)';
    dot.style.animation = 'none';
    statusTxt.textContent = 'Gestoppt – Button drücken zum Starten';
    statusTxt.style.color = 'var(--mu)';
  }
}
</script></body></html>"""

HTML_EIN = """<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Einstellungen – {{ cfg.name }}</title>""" + STYLES + """</head>
<body><div class="wrap">
<div class="hdr"><div><h1>{{ cfg.name }}</h1><p>Einstellungen</p></div></div>
""" + TABS('e') + """
{% if meldung %}<div class="al alo">✓ {{ meldung }}</div>{% endif %}
{% if fehler  %}<div class="al ale">⚠ {{ fehler }}</div>{% endif %}
<div class="sg"><div class="sgl">Allgemein</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Name</div><div class="sd">Anzeigename im Dashboard</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="name"><input type="text" name="wert" value="{{ cfg.name }}" maxlength="40">
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">Kapazität Zisterne</div><div class="sd">Maximaler Inhalt in Litern – für Liter-Berechnung</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="kapazitaet_l">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.kapazitaet_l }}" min="100" max="500000" step="100"><span class="ul">L</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">Messintervall</div><div class="sd">Sekunden (10–3600)</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="intervall_sek">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.intervall_sek }}" min="10" max="3600" step="10"><span class="ul">sek</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
</div></div>
<div class="sg"><div class="sgl">Hardware / Sensor</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Serieller Port</div><div class="sd">SR04M-2 UART</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="serial_port">
      <div class="si2"><input type="text" name="wert" value="{{ cfg.serial_port }}" style="width:160px"></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
</div></div>
<div class="sg"><div class="sgl">Warnschwellen</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Fast leer</div><div class="sd">Orange unter diesem Wert</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="warnung_leer">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.warnung_leer }}" min="1" max="50"><span class="ul">%</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">Fast voll</div><div class="sd">„Fast voll" Hinweis darüber</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="warnung_voll">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.warnung_voll }}" min="50" max="99"><span class="ul">%</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
</div></div>
<div class="sg"><div class="sgl">WLAN</div><div class="sc">

  <!-- Aktuelle Verbindung -->
  <div class="sr">
    <div class="si">
      <div class="sl">Aktuelle Verbindung</div>
      <div class="sd" id="wifi-status-txt">Lade...</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <div id="wifi-balken" style="display:flex;align-items:flex-end;gap:3px;height:18px">
        <div id="wb1" style="width:4px;background:var(--bd);border-radius:2px;height:30%;transition:background .3s"></div>
        <div id="wb2" style="width:4px;background:var(--bd);border-radius:2px;height:55%;transition:background .3s"></div>
        <div id="wb3" style="width:4px;background:var(--bd);border-radius:2px;height:78%;transition:background .3s"></div>
        <div id="wb4" style="width:4px;background:var(--bd);border-radius:2px;height:100%;transition:background .3s"></div>
      </div>
      <span id="wifi-signal-pct" style="font-family:'DM Mono',monospace;font-size:.85rem;color:var(--mu)">–</span>
    </div>
  </div>

  <!-- WLAN hinzufügen -->
  <div class="sr" style="flex-direction:column;align-items:stretch;gap:14px">
    <div class="si">
      <div class="sl">WLAN hinzufügen / wechseln</div>
      <div class="sd">Netzwerk auswählen oder manuell eingeben – z.B. beim Freund</div>
    </div>
    <!-- Portal-Button -->
    <button onclick="portalStarten()" id="portal-btn"
      style="width:100%;padding:13px 16px;border-radius:12px;border:none;
             background:var(--bl);color:#fff;font-size:.95rem;font-weight:600;
             cursor:pointer;font-family:inherit;transition:all .2s;
             display:flex;align-items:center;justify-content:center;gap:8px">
      📡 Neues WLAN einrichten
    </button>

    <!-- Portal Anleitung (erscheint nach Start) -->
    <div id="portal-box" style="display:none;background:var(--bls);border:1.5px solid rgba(14,165,233,.2);
         border-radius:14px;padding:16px 18px;font-size:.85rem;line-height:2">
      <div style="font-weight:600;color:var(--bl);margin-bottom:8px">📱 Jetzt auf dem iPhone:</div>
      <div>1. Einstellungen → WLAN</div>
      <div>2. Netzwerk: <strong id="portal-ssid">Zisterne-Setup</strong></div>
      <div>3. Passwort: <strong id="portal-pw">zisterne123</strong></div>
      <div>4. Browser öffnet sich automatisch</div>
      <div style="margin-top:10px;font-size:.82rem">
        Falls nicht automatisch: &nbsp;
        <a id="portal-link" href="http://192.168.4.1:8080"
           style="color:var(--bl);font-weight:600;text-decoration:none">
          http://192.168.4.1:8080 →
        </a>
      </div>
      <button onclick="portalStoppen()"
        style="margin-top:12px;width:100%;padding:9px;border-radius:10px;
               border:1.5px solid var(--bd);background:transparent;color:var(--tx2);
               font-size:.82rem;cursor:pointer;font-family:inherit">
        Abbrechen
      </button>
    </div>

    <div id="wifi-meldung" style="display:none;padding:10px 14px;border-radius:10px;font-size:.85rem;text-align:center"></div>
  </div>

</div></div>

<script>
// ── WLAN-Status ───────────────────────────────────────────
async function loadWifi(){
  try{
    const w=await fetch('/api/wifi').then(r=>r.json());
    const ac=w.verbunden?(w.balken>=3?'var(--gn)':w.balken>=2?'var(--am)':'var(--rd)'):'var(--mu)';
    for(let i=1;i<=4;i++){
      const el=document.getElementById('wb'+i);
      if(el) el.style.background=i<=w.balken?ac:'var(--bd)';
    }
    const stxt=document.getElementById('wifi-status-txt');
    const spct=document.getElementById('wifi-signal-pct');
    if(stxt) stxt.innerHTML=w.verbunden
      ?`<strong>${w.ssid}</strong> &nbsp;·&nbsp; ${w.qualitaet}`
      :'<span style="color:var(--rd)">Nicht verbunden</span>';
    if(spct) spct.textContent=w.verbunden?w.signal+'%':'–';
  }catch(e){}
}

// ── Captive Portal starten ────────────────────────────────
let _portalPoll=null;
async function portalStarten(){
  const btn=document.getElementById('portal-btn');
  const meld=document.getElementById('wifi-meldung');
  const box=document.getElementById('portal-box');
  btn.disabled=true;btn.textContent='Starte Hotspot...';
  meld.style.display='none';
  try{
    const r=await fetch('/api/wifi/portal/start',{method:'POST'}).then(r=>r.json());
    if(r.ok){
      box.style.display='block';
      document.getElementById('portal-ssid').textContent=r.ssid;
      document.getElementById('portal-pw').textContent=r.passwort;
      const urlEl=document.getElementById('portal-url');
      if(urlEl) urlEl.textContent=r.url;
      // Link direkt anklickbar machen
      const link=document.getElementById('portal-link');
      if(link){link.href=r.url;link.textContent=r.url;}
      btn.textContent='Hotspot aktiv';
      // Polling: sobald Portal fertig ist, Box ausblenden
      _portalPoll=setInterval(async()=>{
        try{
          const s=await fetch('/api/wifi/portal/status').then(r=>r.json());
          if(!s.aktiv){
            clearInterval(_portalPoll);
            box.style.display='none';
            btn.disabled=false;btn.textContent='Neues WLAN einrichten';
            meld.style.display='block';
            meld.style.background='var(--gns)';meld.style.color='var(--gn)';
            meld.textContent='✓ Neues WLAN verbunden!';
            setTimeout(loadWifi,2000);
          }
        }catch(e){}
      },3000);
    }else{
      btn.disabled=false;btn.textContent='Neues WLAN einrichten';
      meld.style.display='block';meld.style.background='var(--rds)';meld.style.color='var(--rd)';
      meld.textContent='Fehler: '+(r.fehler||'Hotspot konnte nicht gestartet werden');
    }
  }catch(e){
    btn.disabled=false;btn.textContent='Neues WLAN einrichten';
  }
}
async function portalStoppen(){
  if(_portalPoll) clearInterval(_portalPoll);
  await fetch('/api/wifi/portal/stop',{method:'POST'});
  document.getElementById('portal-box').style.display='none';
  document.getElementById('portal-btn').disabled=false;
  document.getElementById('portal-btn').textContent='Neues WLAN einrichten';
}
loadWifi();
setInterval(loadWifi,30000);
// Beim Laden prüfen ob Portal schon aktiv
(async()=>{
  try{
    const s=await fetch('/api/wifi/portal/status').then(r=>r.json());
    if(s.aktiv){
      const box=document.getElementById('portal-box');
      const btn=document.getElementById('portal-btn');
      if(box) box.style.display='block';
      if(btn){btn.textContent='Hotspot aktiv';btn.disabled=true;}
      // Polling starten
      _portalPoll=setInterval(async()=>{
        try{
          const s2=await fetch('/api/wifi/portal/status').then(r=>r.json());
          if(!s2.aktiv){
            clearInterval(_portalPoll);
            if(box) box.style.display='none';
            if(btn){btn.disabled=false;btn.textContent='Neues WLAN einrichten';}
            const meld=document.getElementById('wifi-meldung');
            if(meld){meld.style.display='block';
              meld.style.background='var(--gns)';meld.style.color='var(--gn)';
              meld.textContent='✓ Neues WLAN verbunden!';}
            setTimeout(loadWifi,2000);
          }
        }catch(e){}
      },3000);
    }
  }catch(e){}
})();
</script>

<div class="sg"><div class="sgl">Regenvorhersage</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Dachfläche</div><div class="sd">Wirksame Fläche fürs Regenwasser (Draufsicht)</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="dachflaeche_m2">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.dachflaeche_m2 }}" min="10" max="10000" step="5"><span class="ul">m²</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">Abflusskoeffizient</div><div class="sd">Wirkungsgrad (Ziegel=0.8, Flachdach=0.9, begrünt=0.3)</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="abfluss_koeff">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.abfluss_koeff }}" min="0.1" max="1.0" step="0.05"><span class="ul"></span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">Standort GPS</div><div class="sd">Breitengrad, Längengrad (für Wettervorhersage)</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <input type="hidden" name="feld" value="standort_lat">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.standort_lat }}" min="-90" max="90" step="0.01" placeholder="Lat"><span class="ul">°N</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Lat</button>
    </form>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px;margin-top:6px;flex-wrap:wrap">
      <input type="hidden" name="feld" value="standort_lon">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.standort_lon }}" min="-180" max="180" step="0.01" placeholder="Lon"><span class="ul">°O</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Lon</button>
    </form>
  </div>
</div></div>

<div class="sg"><div class="sgl">System</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">Testmessung</div></div>
    <form method="POST" action="/einstellungen/messen"><button type="submit" class="btn bg">Jetzt messen</button></form></div>
  <div class="sr"><div class="si"><div class="sl">Zurücksetzen</div><div class="sd">Alle Einstellungen auf Standard</div></div>
    <form method="POST" action="/einstellungen/reset" onsubmit="return confirm('Wirklich zurücksetzen?')">
      <button type="submit" class="btn br">Zurücksetzen</button></form></div>
</div></div>
<div class="sg"><div class="sgl">Über diese App</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">{{ project }}</div><div class="sd">Zisterne Wasserstandsüberwachung</div></div>
    <span style="padding:4px 12px;background:var(--bls);color:var(--bl);border-radius:100px;font-size:.8rem;font-weight:600;font-family:'DM Mono',monospace">v{{ version }}</span>
  </div>
  <div class="sr"><div class="si"><div class="sl">Version</div><div class="sd">Veröffentlicht am {{ version_date }}</div></div>
    <span style="font-family:'DM Mono',monospace;font-size:.85rem;color:var(--mu)">{{ version }}</span>
  </div>
  <div class="sr"><div class="si"><div class="sl">Autor</div><div class="sd"><a href="mailto:{{ email }}" style="color:var(--bl)">{{ email }}</a></div></div>
    <span style="font-size:.9rem;font-weight:500">{{ author }}</span>
  </div>
  <div class="sr"><div class="si"><div class="sl">Plattform</div><div class="sd">JSN-SR04T Ultraschallsensor</div></div>
    <span style="font-size:.85rem;color:var(--mu)">Raspberry Pi Zero 2W</span>
  </div>
</div></div>
<footer>{{ cfg.name }} · v{{ version }} · {{ author }} · <a href="mailto:{{ email }}" style="color:inherit">{{ email }}</a></footer></div></body></html>"""

def liter_aktuell():
    """Aktuellen Inhalt und Zu/Abfluss seit letzter Messung berechnen"""
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute(
            "SELECT zeitpunkt, fuellstand FROM messungen ORDER BY id DESC LIMIT 2"
        ).fetchall()
    if not rows:
        return {"liter": 0, "max_liter": CFG["kapazitaet_l"], "delta_l": 0, "richtung": "gleich"}
    kap = CFG["kapazitaet_l"]
    liter_aktuell = round(rows[0][1] / 100 * kap, 1)
    delta = 0.0
    richtung = "gleich"
    if len(rows) == 2:
        liter_vorher = rows[1][1] / 100 * kap
        delta = round(liter_aktuell - liter_vorher, 1)
        if delta > 0.5:
            richtung = "zufluss"
        elif delta < -0.5:
            richtung = "abfluss"
    return {
        "liter":      liter_aktuell,
        "max_liter":  kap,
        "delta_l":    abs(delta),
        "richtung":   richtung,
    }

def liter_heute():
    """Heutigen Gesamt-Zu- und Abfluss in Litern berechnen"""
    heute = datetime.now().strftime('%Y-%m-%d')
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute(
            "SELECT fuellstand FROM messungen WHERE DATE(zeitpunkt)=? ORDER BY id ASC",
            (heute,)
        ).fetchall()
    if len(rows) < 2:
        return {"zufluss_l": 0.0, "abfluss_l": 0.0}
    kap = CFG["kapazitaet_l"]
    zufluss = abfluss = 0.0
    for i in range(1, len(rows)):
        delta = (rows[i][0] - rows[i-1][0]) / 100 * kap
        if delta > 0.5:
            zufluss += delta
        elif delta < -0.5:
            abfluss += abs(delta)
    return {"zufluss_l": round(zufluss, 1), "abfluss_l": round(abfluss, 1)}

def liter_verlauf_heute():
    """Stündlicher Liter-Verlauf für heute"""
    heute = datetime.now().strftime('%Y-%m-%d')
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute("""
            SELECT strftime('%H', zeitpunkt) as h,
                   ROUND(AVG(fuellstand) / 100 * ?, 1) as liter
            FROM messungen WHERE DATE(zeitpunkt)=?
            GROUP BY h ORDER BY h ASC
        """, (CFG["kapazitaet_l"], heute)).fetchall()
    return [{"h": r[0] + ":00", "liter": r[1]} for r in rows]


def verbrauch_prognose():
    """Durchschnittlicher Tagesverbrauch + Prognose wie viele Tage Wasser reicht"""
    kap = CFG["kapazitaet_l"]
    with sqlite3.connect(DB_PFAD) as c:
        # Tagesverbrauch der letzten 7 Tage (nur Abfluss, kein Zufluss)
        rows = c.execute("""
            SELECT DATE(zeitpunkt) as tag,
                   MAX(fuellstand) as max_f,
                   MIN(fuellstand) as min_f
            FROM messungen
            WHERE zeitpunkt > datetime('now', '-7 days')
            GROUP BY tag ORDER BY tag ASC
        """).fetchall()
    # Täglichen Nettoverbrauch berechnen (nur negative Deltas = Entnahme)
    verbr_tage = []
    for r in rows:
        delta_pct = r[1] - r[2]  # max - min des Tages
        if delta_pct > 1:  # mind. 1% Unterschied
            verbr_tage.append(delta_pct / 100 * kap)
    if not verbr_tage:
        return {"verbrauch_l_tag": 0, "prognose_tage": None, "datenbasis_tage": 0}
    avg_verbr = sum(verbr_tage) / len(verbr_tage)
    # Aktueller Inhalt
    letzter = db_letzte()
    liter_aktuell_val = letzter.get("fuellstand", 0) / 100 * kap if letzter else 0
    prognose = round(liter_aktuell_val / avg_verbr) if avg_verbr > 0 else None
    return {
        "verbrauch_l_tag": round(avg_verbr, 1),
        "prognose_tage":   prognose,
        "datenbasis_tage": len(verbr_tage),
    }


def regenereignisse():
    """Erkennt Regenereignisse (Füllstand steigt schnell an) der letzten 30 Tage"""
    kap = CFG["kapazitaet_l"]
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute("""
            SELECT zeitpunkt, fuellstand FROM messungen
            WHERE zeitpunkt > datetime('now', '-30 days')
            ORDER BY zeitpunkt ASC
        """).fetchall()
    ereignisse = []
    i = 0
    while i < len(rows) - 1:
        delta = rows[i+1][1] - rows[i][1]
        # Zufluss-Ereignis: >3% Anstieg = Regen oder Befüllung
        if delta >= 3.0:
            # Wie weit geht der Anstieg?
            start_f = rows[i][1]
            start_t = rows[i][0]
            j = i + 1
            while j < len(rows) - 1 and rows[j+1][1] > rows[j][1]:
                j += 1
            end_f = rows[j][1]
            zufluss_l = round((end_f - start_f) / 100 * kap, 0)
            ereignisse.append({
                "zeitpunkt": start_t,
                "zufluss_l": int(zufluss_l),
                "anstieg_pct": round(end_f - start_f, 1),
            })
            i = j + 1
        else:
            i += 1
    # Letztes Ereignis zuerst
    ereignisse.reverse()
    return ereignisse[:10]  # Max 10 letzte Ereignisse


def wochenverbrauch():
    """Verbrauch pro Wochentag der letzten 4 Wochen (Durchschnitt)"""
    kap = CFG["kapazitaet_l"]
    with sqlite3.connect(DB_PFAD) as c:
        rows = c.execute("""
            SELECT DATE(zeitpunkt) as tag,
                   strftime('%w', zeitpunkt) as wochentag,
                   MAX(fuellstand) - MIN(fuellstand) as delta_pct
            FROM messungen
            WHERE zeitpunkt > datetime('now', '-28 days')
            GROUP BY tag ORDER BY tag ASC
        """).fetchall()
    # Pro Wochentag sammeln (0=So, 1=Mo, ..., 6=Sa)
    tage_de = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"]
    verbrauch = {i: [] for i in range(7)}
    for r in rows:
        wt = int(r[1])
        delta = r[2] if r[2] and r[2] > 0 else 0
        verbrauch[wt].append(delta / 100 * kap)
    result = []
    # Mo-So Reihenfolge (1-6, dann 0)
    for wt in [1, 2, 3, 4, 5, 6, 0]:
        werte = verbrauch[wt]
        avg = round(sum(werte) / len(werte), 1) if werte else 0
        result.append({"tag": tage_de[wt], "verbrauch_l": avg})
    return result

@app.route('/api/liter')
def api_liter():
    d = liter_aktuell()
    d.update(liter_heute())
    return jsonify(d)

@app.route('/api/liter/verlauf')
def api_liter_verlauf():
    return jsonify(liter_verlauf_heute())

@app.route('/api/wetter')
def api_wetter():
    return jsonify(wetter_vorhersage())

@app.route('/api/prognose')
def api_prognose():
    return jsonify(verbrauch_prognose())

@app.route('/api/regen')
def api_regen():
    return jsonify(regenereignisse())

@app.route('/api/woche')
def api_woche():
    return jsonify(wochenverbrauch())


import subprocess as _sp

def wifi_info():
    """Aktuelle WLAN-Verbindung und Signalstärke via nmcli"""
    try:
        # Aktive Verbindung
        r = _sp.run(
            ['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL,SECURITY', 'dev', 'wifi'],
            capture_output=True, text=True, timeout=8
        )
        for line in r.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3 and parts[0] == 'yes':
                signal = int(parts[2]) if parts[2].isdigit() else 0
                return {
                    'verbunden': True,
                    'ssid':      parts[1] if len(parts) > 1 else '?',
                    'signal':    signal,
                    'sicherheit':parts[3] if len(parts) > 3 else '',
                    'qualitaet': 'Sehr gut' if signal>=75 else 'Gut' if signal>=50 else 'Mittel' if signal>=25 else 'Schwach',
                    'balken':    4 if signal>=75 else 3 if signal>=50 else 2 if signal>=25 else 1,
                }
    except Exception as e:
        pass
    return {'verbunden': False, 'ssid': '', 'signal': 0, 'qualitaet': 'Getrennt', 'balken': 0}

def wifi_scan():
    """Verfügbare WLAN-Netzwerke scannen"""
    try:
        _sp.run(['nmcli', 'dev', 'wifi', 'rescan'], capture_output=True, timeout=5)
        r = _sp.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE', 'dev', 'wifi', 'list'],
            capture_output=True, text=True, timeout=10
        )
        seen, nets = set(), []
        for line in r.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 2:
                ssid = parts[0].strip()
                if ssid and ssid not in seen and ssid != '--':
                    seen.add(ssid)
                    signal = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 0
                    nets.append({
                        'ssid':    ssid,
                        'signal':  signal,
                        'sicher':  parts[2] if len(parts)>2 else '',
                        'aktiv':   parts[3].strip() == '*' if len(parts)>3 else False,
                    })
        return sorted(nets, key=lambda x: -x['signal'])[:12]
    except Exception:
        return []

import urllib.request as _urq
import json as _json_mod

_wetter_cache = {"data": None, "ts": 0}

def wetter_vorhersage():
    """7-Tage Regenvorhersage via Open-Meteo (kostenlos, kein API-Key)"""
    import time as _t
    # Cache: 1 Stunde
    if _wetter_cache["data"] and (_t.time() - _wetter_cache["ts"]) < 3600:
        return _wetter_cache["data"]
    try:
        lat = CFG.get("standort_lat", 50.11)
        lon = CFG.get("standort_lon", 8.68)
        dach = CFG.get("dachflaeche_m2", 100)
        koeff = CFG.get("abfluss_koeff", 0.8)
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=precipitation_sum,precipitation_probability_max,weathercode"
            f"&timezone=Europe%2FBerlin&forecast_days=7"
        )
        with _urq.urlopen(url, timeout=8) as r:
            d = _json_mod.loads(r.read())
        daily = d.get("daily", {})
        tage = []
        total_mm = 0
        for i, datum in enumerate(daily.get("time", [])):
            mm   = daily["precipitation_sum"][i] or 0
            prob = daily["precipitation_probability_max"][i] or 0
            wc   = daily.get("weathercode", [0]*7)[i] or 0
            liter = round(mm * dach * koeff, 1)
            total_mm += mm
            # Wettercode -> Icon
            if   wc == 0:             icon = "☀️"
            elif wc in range(1,4):    icon = "🌤️"
            elif wc in range(45,68):  icon = "🌧️"
            elif wc in range(71,78):  icon = "🌨️"
            elif wc in range(80,83):  icon = "🌦️"
            elif wc in range(95,100): icon = "⛈️"
            else:                     icon = "🌥️"
            tage.append({
                "datum":    datum,
                "mm":       round(mm, 1),
                "prob":     prob,
                "liter":    liter,
                "icon":     icon,
                "wc":       wc,
            })
        total_liter = round(total_mm * dach * koeff, 0)
        result = {
            "tage":         tage,
            "total_mm":     round(total_mm, 1),
            "total_liter":  int(total_liter),
            "dachflaeche":  dach,
            "koeff":        koeff,
            "ok":           True,
        }
        _wetter_cache["data"] = result
        _wetter_cache["ts"]   = _t.time()
        return result
    except Exception as e:
        return {"ok": False, "fehler": str(e), "tage": []}


# Captive Portal Detection – iOS/Android leiten auf Portal um wenn aktiv
CAPTIVE_PATHS_APP = [
    '/hotspot-detect.html', '/generate_204', '/ncsi.txt',
    '/connecttest.txt', '/canonical.html', '/redirect',
    '/library/test/success.html',
]

@app.before_request
def captive_portal_check():
    global _portal_aktiv
    if _portal_aktiv and request.path in CAPTIVE_PATHS_APP:
        from flask import redirect as _redir
        return _redir('http://192.168.4.1:8080/', 302)

@app.route('/')
def index():
    return render_template_string(HTML_INDEX, cfg=CFG,
        version=__version__, version_date=__version_date__,
        author=__author__, email=__email__)

@app.route('/api/aktuell')
def api_aktuell(): return jsonify(db_letzte())

@app.route('/api/sensor')
def api_sensor():
    """Direkte Sensor-Messung ohne DB-Speicherung (für Live-Kalibrierung)."""
    a = abstand_messen()
    if a is None:
        return jsonify({"fehler": "Sensor nicht erreichbar"})
    f, w = fuellstand(round(a, 1))
    return jsonify({"abstand": round(a, 1), "fuellstand": f, "wasser_cm": w})

@app.route('/api/range')
def api_range():
    return jsonify(db_range(
        stunden=request.args.get('h',type=int),
        tage=request.args.get('d',type=int),
        monate=request.args.get('m',type=int)
    ))

@app.route('/kalibrierung')
def kalibrierung():
    return render_template_string(HTML_KAL, cfg=CFG,
        meldung=request.args.get('ok'), fehler=request.args.get('err'),
        roh=db_roh(10), letzter=db_letzte() or None,
        version=__version__, version_date=__version_date__,
        author=__author__, email=__email__)

@app.route('/kalibrierung/speichern', methods=['POST'])
def kal_speichern():
    feld=request.form.get('feld'); wert=request.form.get('wert','').strip()
    erlaubt={'tiefe_cm':(10,1000),'min_cm':(5,100)}
    if feld not in erlaubt: return redirect('/kalibrierung?err=Ungültiges+Feld')
    try:
        v=float(wert); lo,hi=erlaubt[feld]
        if not(lo<=v<=hi): return redirect(f'/kalibrierung?err=Wert+zwischen+{lo}+und+{hi}')
        CFG[feld]=round(v,1); cfg_speichern(CFG); return redirect('/kalibrierung?ok=Gespeichert')
    except: return redirect('/kalibrierung?err=Ungültige+Zahl')

@app.route('/kalibrierung/setze_leer', methods=['POST'])
def kal_setze_leer():
    a=abstand_messen()
    if a is None: return redirect('/kalibrierung?err=Sensor+nicht+erreichbar')
    CFG['tiefe_cm']=round(a,1); cfg_speichern(CFG)
    return redirect(f'/kalibrierung?ok=Tiefe+auf+{round(a,1)}+cm+gesetzt')

@app.route('/kalibrierung/testmessung', methods=['POST'])
def kal_test():
    messen(); return redirect('/kalibrierung?ok=Testmessung+durchgeführt')

@app.route('/api/wifi')
def api_wifi():
    return jsonify(wifi_info())

@app.route('/api/wifi/scan')
def api_wifi_scan():
    return jsonify(wifi_scan())

@app.route('/api/wifi/connect', methods=['POST'])
def api_wifi_connect():
    data = request.get_json() or {}
    ssid = data.get('ssid','').strip()
    pw   = data.get('passwort','').strip()
    if not ssid:
        return jsonify({'ok': False, 'fehler': 'SSID fehlt'})
    try:
        _sp.run(['nmcli', 'connection', 'delete', ssid],
                capture_output=True, timeout=8)
        r = _sp.run(
            ['nmcli', 'dev', 'wifi', 'connect', ssid,
             'password', pw, 'ifname', 'wlan0'],
            capture_output=True, text=True, timeout=35
        )
        if r.returncode == 0:
            return jsonify({'ok': True, 'ssid': ssid})
        else:
            fehler = r.stderr.strip() or r.stdout.strip() or 'Verbindung fehlgeschlagen'
            return jsonify({'ok': False, 'fehler': fehler})
    except Exception as e:
        return jsonify({'ok': False, 'fehler': str(e)})

@app.route('/api/wifi/delete', methods=['POST'])
def api_wifi_delete():
    data = request.get_json() or {}
    ssid = data.get('ssid','').strip()
    if not ssid:
        return jsonify({'ok': False})
    try:
        _sp.run(['nmcli', 'connection', 'delete', ssid],
                capture_output=True, timeout=8)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'fehler': str(e)})

# Captive Portal fuer WLAN-Einrichtung (wie beim Erststart)
import threading as _th
_portal_aktiv = False

@app.route('/api/wifi/portal/start', methods=['POST'])
def api_wifi_portal_start():
    global _portal_aktiv
    if _portal_aktiv:
        return jsonify({'ok': False, 'fehler': 'Portal laeuft bereits'})
    def _start():
        global _portal_aktiv
        _portal_aktiv = True
        try:
            _sp.run(['nmcli','connection','delete','Zisterne-Hotspot'],
                    capture_output=True, timeout=8)
            _sp.run([
                'nmcli','connection','add',
                'type','wifi','ifname','wlan0',
                'con-name','Zisterne-Hotspot','autoconnect','no',
                'ssid','Zisterne-Setup','mode','ap',
                'ipv4.method','shared','ipv4.addresses','192.168.4.1/24',
                'wifi-sec.key-mgmt','wpa-psk','wifi-sec.psk','zisterne123',
                'wifi-sec.pmf','1',
                '802-11-wireless.band','bg','802-11-wireless.channel','6'
            ], capture_output=True, timeout=15)
            _sp.run(['nmcli','connection','up','Zisterne-Hotspot'],
                    capture_output=True, timeout=15)
        except Exception:
            pass
    _th.Thread(target=_start, daemon=True).start()
    return jsonify({'ok': True, 'ssid': 'Zisterne-Setup',
                    'passwort': 'zisterne123', 'url': 'http://192.168.4.1:8080'})

@app.route('/api/wifi/portal/stop', methods=['POST'])
def api_wifi_portal_stop():
    global _portal_aktiv
    _portal_aktiv = False
    try:
        _sp.run(['nmcli','connection','delete','Zisterne-Hotspot'],
                capture_output=True, timeout=8)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'fehler': str(e)})

@app.route('/api/wifi/portal/status')
def api_wifi_portal_status():
    return jsonify({'aktiv': _portal_aktiv, 'wifi': wifi_info()})

def _portal_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse
    CSS = ("<style>*{box-sizing:border-box;margin:0;padding:0}"
        "body{background:#f0f4f8;font-family:-apple-system,sans-serif;"
        "min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}"
        ".card{background:#fff;border-radius:22px;padding:36px 28px;width:100%;max-width:380px;"
        "box-shadow:0 8px 40px rgba(0,0,0,.1)}"
        "@media(prefers-color-scheme:dark){body{background:#000}.card{background:#1c1c1e;color:#fff}}"
        ".icon{font-size:3rem;text-align:center;margin-bottom:8px}"
        "h1{font-size:1.5rem;font-weight:700;text-align:center;margin-bottom:6px}"
        ".sub{font-size:.88rem;color:#8e8e93;text-align:center;margin-bottom:24px}"
        "label{display:block;font-size:.78rem;font-weight:600;color:#8e8e93;"
        "margin-bottom:6px;text-transform:uppercase;letter-spacing:.3px}"
        ".field{margin-bottom:14px}"
        "input{width:100%;padding:14px;border-radius:12px;"
        "border:1.5px solid rgba(60,60,67,.15);font-size:1rem;outline:none}"
        "input:focus{border-color:#007aff}"
        ".btn{width:100%;padding:16px;border-radius:14px;border:none;"
        "background:#007aff;color:#fff;font-size:1rem;font-weight:600;cursor:pointer;margin-top:6px}"
        ".ok{background:rgba(52,199,89,.1);color:#248a3d;border-radius:12px;"
        "padding:14px;text-align:center;margin-top:14px;font-weight:500;line-height:2}"
        "</style>")
    CPATHS = {"/hotspot-detect.html","/generate_204","/ncsi.txt",
              "/connecttest.txt","/canonical.html","/redirect"}
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def _redir(self):
            self.send_response(302)
            self.send_header("Location","http://192.168.4.1:8080/")
            self.end_headers()
        def _html(self,body,code=200):
            b=body.encode()
            self.send_response(code)
            self.send_header("Content-Type","text/html;charset=utf-8")
            self.send_header("Content-Length",str(len(b)))
            self.send_header("Cache-Control","no-cache")
            self.end_headers()
            self.wfile.write(b)
        def do_GET(self):
            if urlparse(self.path).path in CPATHS:
                self._redir(); return
            self._html(
                "<!DOCTYPE html><html lang='de'><head>"
                "<meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>WLAN einrichten</title>"
                +CSS+
                "</head><body><div class='card'>"
                "<div class='icon'>&#x1F4E1;</div>"
                "<h1>WLAN verbinden</h1>"
                "<p class='sub'>Zisterne Monitor - Neues Netzwerk</p>"
                "<form method='POST' action='/verbinden'>"
                "<div class='field'><label>WLAN Name</label>"
                "<input name='ssid' placeholder='z.B. FritzBox 7590' required "
                "autocomplete='off' autocorrect='off' autocapitalize='none'></div>"
                "<div class='field'><label>Passwort</label>"
                "<input type='password' name='pw' placeholder='Passwort' required></div>"
                "<button class='btn' type='submit'>Verbinden &#x2192;</button>"
                "</form></div></body></html>"
            )
        def do_POST(self):
            if urlparse(self.path).path != '/verbinden':
                self._redir(); return
            ln = int(self.headers.get("Content-Length",0))
            raw = self.rfile.read(ln).decode("utf-8","replace")
            params = parse_qs(raw)
            ssid = params.get("ssid",[""])[0].strip()
            pw   = params.get("pw",[""])[0].strip()
            if not ssid or len(pw) < 8:
                self._html("<!DOCTYPE html><html><body><p>Fehler - bitte zurueck</p></body></html>")
                return
            def _conn():
                global _portal_aktiv
                try:
                    _sp.run(['nmcli','connection','delete',ssid],
                            capture_output=True,timeout=8)
                    r=_sp.run(['nmcli','dev','wifi','connect',ssid,
                               'password',pw,'ifname','wlan0'],
                              capture_output=True,text=True,timeout=35)
                    if r.returncode==0:
                        _sp.run(['nmcli','connection','delete','Zisterne-Hotspot'],
                                capture_output=True,timeout=8)
                        _portal_aktiv = False
                except Exception:
                    pass
            _th.Thread(target=_conn,daemon=True).start()
            self._html(
                "<!DOCTYPE html><html lang='de'><head>"
                "<meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>Verbunden!</title>"
                +CSS+
                "</head><body><div class='card'>"
                "<div class='icon'>&#x2705;</div>"
                "<h1>Verbunden!</h1>"
                "<p class='sub'>Verbinde mit <strong>"+ssid+"</strong>...</p>"
                "<div class='ok'>"
                "1. iPhone &#x2192; Einstellungen &#x2192; WLAN<br>"
                "2. Mit <strong>"+ssid+"</strong> verbinden<br>"
                "3. Browser: <strong>http://zisterne.local</strong><br>"
                "4. Ca. 30 Sekunden warten"
                "</div></div></body></html>"
            )
    try:
        HTTPServer(("0.0.0.0",8080),H).serve_forever()
    except Exception:
        pass

_th.Thread(target=_portal_server, daemon=True).start()

@app.route('/einstellungen')
def einstellungen():
    return render_template_string(HTML_EIN, cfg=CFG,
        meldung=request.args.get('ok'), fehler=request.args.get('err'),
        version=__version__, version_date=__version_date__,
        author=__author__, email=__email__, project=__project__)

@app.route('/einstellungen/speichern', methods=['POST'])
def ein_speichern():
    feld=request.form.get('feld'); wert=request.form.get('wert','').strip()
    num={'intervall_sek':(10,3600),'warnung_leer':(1,50),'warnung_voll':(50,99),'kapazitaet_l':(100,500000),'dachflaeche_m2':(10,10000),'standort_lat':(-90,90),'standort_lon':(-180,180)}
    if feld=='serial_port':
        if not wert: return redirect('/einstellungen?err=Port+darf+nicht+leer+sein')
        CFG['serial_port']=wert[:40]; cfg_speichern(CFG); return redirect('/einstellungen?ok=Gespeichert')
    if feld in ('abfluss_koeff',):
        try:
            v=float(wert)
            if 0.05<=v<=1.0:
                CFG[feld]=v; cfg_speichern(CFG)
            return redirect('/einstellungen?ok=Gespeichert')
        except: return redirect('/einstellungen?err=Ungültiger+Wert')
    if feld=='name':
        if not wert: return redirect('/einstellungen?err=Name+darf+nicht+leer+sein')
        CFG['name']=wert[:40]; cfg_speichern(CFG); return redirect('/einstellungen?ok=Gespeichert')
    if feld in num:
        try:
            v=float(wert); lo,hi=num[feld]
            if not(lo<=v<=hi): return redirect(f'/einstellungen?err=Wert+zwischen+{lo}+und+{hi}')
            CFG[feld]=int(v); cfg_speichern(CFG); return redirect('/einstellungen?ok=Gespeichert')
        except: return redirect('/einstellungen?err=Ungültige+Zahl')
    return redirect('/einstellungen?err=Unbekanntes+Feld')

@app.route('/einstellungen/messen', methods=['POST'])
def ein_messen():
    messen(); return redirect('/einstellungen?ok=Messung+durchgeführt')

@app.route('/einstellungen/reset', methods=['POST'])
def ein_reset():
    global CFG; CFG=DEFAULT_CFG.copy(); cfg_speichern(CFG)
    return redirect('/einstellungen?ok=Zurückgesetzt')

@app.route('/api/version')
def api_version():
    return jsonify({
        "version":      __version__,
        "date":         __version_date__,
        "author":       __author__,
        "email":        __email__,
        "project":      __project__,
        "platform":     "Raspberry Pi Zero 2W + JSN-SR04T"
    })

if __name__ == '__main__':
    db_init(); messen()
    scheduler.add_job(messen,'interval',seconds=CFG['intervall_sek'])
    scheduler.start()
    print(f"""
╔══════════════════════════════════════════╗
║  {__project__:<40}║
╠══════════════════════════════════════════╣
║  Version : {__version__:<30}║
║  Datum   : {__version_date__:<30}║
║  Autor   : {__author__:<30}║
║  URL     : http://zisterne.local{' '*9}║
╚══════════════════════════════════════════╝
    """)
    try:
        app.run(host='0.0.0.0',port=80,use_reloader=False)
    finally:
        if _ser: _ser.close()
        scheduler.shutdown()
