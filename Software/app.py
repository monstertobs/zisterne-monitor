#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║              ZISTERNE MONITOR                            ║
║  Raspberry Pi Zero 2W + JSN-SR04T Ultraschallsensor     ║
╠══════════════════════════════════════════════════════════╣
║  Version:  0.2.0                                         ║
║  Datum:    2026-03-21                                    ║
║  Autor:    Tobias Meier                                  ║
║  E-Mail:   admin@secutobs.com                            ║
╚══════════════════════════════════════════════════════════╝
"""

# ── Versionsinformation ──────────────────────────────────────
__version__     = "0.5.0"
__version_date__ = "2026-03-22"
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
    "trig_pin":      23,
    "echo_pin":      24,
    "warnung_leer":  20,
    "warnung_voll":  90,
    "kapazitaet_l":  5000,
    "dachflaeche_m2": 100,
    "standort_lat":  50.11,
    "standort_lon":   8.68,
    "abfluss_koeff":  0.8,
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
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(CFG["trig_pin"], GPIO.OUT)
    GPIO.setup(CFG["echo_pin"], GPIO.IN)
    GPIO_OK = True
except Exception:
    GPIO_OK = False
    print("⚠  GPIO nicht verfügbar")

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
    if not GPIO_OK: return None
    m=[]
    for _ in range(5):
        GPIO.output(CFG["trig_pin"],True); time.sleep(0.00001); GPIO.output(CFG["trig_pin"],False)
        s=time.time()
        while GPIO.input(CFG["echo_pin"])==0:
            if time.time()-s>1: return None
        t1=time.time()
        while GPIO.input(CFG["echo_pin"])==1:
            if time.time()-t1>1: return None
        m.append(((time.time()-t1)*34300)/2); time.sleep(0.1)
    return sorted(m)[2]

def fuellstand(a):
    n=CFG["tiefe_cm"]-CFG["min_cm"]; w=CFG["tiefe_cm"]-a
    return round(max(0.0,min(100.0,(w/n)*100)),1), round(max(0,w),1)

def messen():
    a=abstand_messen()
    if a is None: return
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
/* ── 3D Zisterne ─────────────────────────────────────── */
.mi{display:grid;grid-template-columns:1fr 1fr}
@media(max-width:680px){.mi{grid-template-columns:1fr}}

.wp{
  position:relative;
  background:radial-gradient(ellipse at 30% 20%, #0f2540 0%, #060e1c 60%, #030810 100%);
  min-height:360px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;
  border-radius:var(--rl) 0 0 var(--rl);
}
@media(max-width:680px){.wp{border-radius:var(--rl) var(--rl) 0 0;min-height:320px}}

/* Hintergrund-Licht */
.wp::before{
  content:'';position:absolute;
  width:200px;height:200px;border-radius:50%;
  background:radial-gradient(circle,rgba(14,165,233,.06),transparent 70%);
  top:20%;left:30%;pointer-events:none;
}

/* ── Beschriftung ── */
.wl{
  position:absolute;top:16px;left:0;right:50px;
  text-align:center;pointer-events:none;z-index:20;
}
.wpc{
  font-size:2.8rem;font-weight:700;color:#fff;
  letter-spacing:-2px;line-height:1;
  text-shadow:0 0 30px rgba(14,165,233,.4),0 2px 4px rgba(0,0,0,.5);
  font-variant-numeric:tabular-nums;
}
.wpcu{font-size:1.4rem;font-weight:300;opacity:.55}
.wlit{font-size:.95rem;font-weight:500;color:rgba(140,200,255,.65);
  margin-top:4px;font-variant-numeric:tabular-nums}
.wsl{font-family:'DM Mono',monospace;font-size:.58rem;
  color:rgba(100,170,255,.45);letter-spacing:2.5px;text-transform:uppercase;margin-top:2px}

/* ── Tank-Wrapper ── */
.tank3d{
  position:relative;
  width:170px;height:260px;
  margin-top:40px;
  filter:drop-shadow(0 20px 40px rgba(0,50,120,.5));
}

/* ── Zylinder Körper ── */
.cyl-body{
  position:absolute;
  left:0;right:0;top:0;bottom:0;
  border-radius:50% 50% 50% 50% / 10% 10% 10% 10%;
  overflow:hidden;
  /* Glas-Wand Effekt */
  background:
    /* linke Wand-Highlight */
    radial-gradient(ellipse 12% 60% at 6% 50%, rgba(180,220,255,.18) 0%, transparent 100%),
    /* rechte Wand-Highlight */
    radial-gradient(ellipse 8% 50% at 94% 40%, rgba(180,220,255,.1) 0%, transparent 100%),
    /* Glas-Körper */
    linear-gradient(90deg,
      rgba(20,60,120,.25) 0%,
      rgba(10,30,80,.08) 15%,
      rgba(5,15,50,.04) 50%,
      rgba(10,30,80,.08) 85%,
      rgba(20,60,120,.25) 100%);
  border: 1.5px solid rgba(100,180,255,.2);
  border-left: 2px solid rgba(140,200,255,.35);
  border-right: 2px solid rgba(140,200,255,.25);
  box-shadow:
    inset 0 0 30px rgba(0,0,0,.3),
    0 0 0 1px rgba(60,130,220,.1),
    0 4px 20px rgba(0,20,80,.4);
}

/* ── Ellipse oben (3D Deckel) ── */
.cyl-top{
  position:absolute;top:-12px;left:-1px;right:-1px;
  height:24px;border-radius:50%;z-index:15;
  background:linear-gradient(180deg,
    rgba(160,210,255,.3) 0%,
    rgba(80,160,255,.12) 50%,
    rgba(20,80,180,.08) 100%);
  border:1.5px solid rgba(120,190,255,.35);
  box-shadow:0 2px 8px rgba(0,0,0,.3),
    inset 0 1px 0 rgba(200,230,255,.2);
}
/* Inneres Highlight im Deckel */
.cyl-top::after{
  content:'';position:absolute;
  left:20%;right:40%;top:4px;height:4px;
  border-radius:50%;
  background:rgba(200,230,255,.25);
}

/* ── Ellipse unten ── */
.cyl-bot{
  position:absolute;bottom:-12px;left:-1px;right:-1px;
  height:24px;border-radius:50%;z-index:15;
  background:linear-gradient(180deg,
    rgba(5,20,60,.6) 0%,
    rgba(2,10,40,.8) 100%);
  border:1.5px solid rgba(40,80,160,.3);
  box-shadow:0 4px 12px rgba(0,0,0,.5);
}

/* ── Maßstab ── */
.cyl-scale{
  position:absolute;right:-44px;top:0;bottom:0;
  display:flex;flex-direction:column;justify-content:space-between;
  pointer-events:none;z-index:20;
}
.csm{
  display:flex;align-items:center;gap:4px;
  font-family:'DM Mono',monospace;font-size:.56rem;
  color:rgba(120,180,255,.3);
}
.csm::before{content:'';display:block;width:8px;height:1px;
  background:rgba(100,160,255,.2)}

/* ── Wasser-Füllung ── */
.cyl-water{
  position:absolute;left:0;right:0;bottom:0;
  transition:height 2s cubic-bezier(.34,1.05,.64,1);
  overflow:hidden;z-index:2;
}

/* Wasser-Oberfläche Ellipse */
.cyl-surface{
  position:absolute;top:-11px;left:-2px;right:-2px;
  height:22px;border-radius:50%;z-index:5;
  background:linear-gradient(180deg,
    rgba(100,210,255,.95) 0%,
    rgba(40,170,240,.8)  60%,
    rgba(14,140,220,.6) 100%);
  box-shadow:0 -2px 8px rgba(14,165,233,.25);
  animation:surf 3.5s ease-in-out infinite;
}
@keyframes surf{
  0%,100%{transform:scaleX(1) scaleY(1)}
  33%{transform:scaleX(1.008) scaleY(.94)}
  66%{transform:scaleX(.994) scaleY(1.06)}
}
/* Glanz auf Wasseroberfläche */
.cyl-surface::after{
  content:'';position:absolute;
  left:15%;right:35%;top:5px;height:3px;
  border-radius:50%;
  background:rgba(255,255,255,.35);
}

/* Wellen unter Oberfläche */
.cyl-wave,.cyl-wave2{
  position:absolute;top:8px;left:-70%;right:-70%;
  height:16px;border-radius:50%;z-index:4;
}
.cyl-wave{
  background:rgba(56,190,255,.2);
  animation:wv 5s ease-in-out infinite;
}
.cyl-wave2{
  background:rgba(100,210,255,.12);
  animation:wv 7s ease-in-out infinite reverse 1s;
}
@keyframes wv{
  0%,100%{transform:translateX(0) scaleY(1)}
  50%{transform:translateX(8px) scaleY(.6)}
}

/* Wasser-Körper */
.cyl-wb{
  position:absolute;top:9px;left:0;right:0;bottom:0;
  background:linear-gradient(180deg,
    rgba(20,160,240,.78) 0%,
    rgba(10,110,200,.88) 30%,
    rgba(5,75,165,.94)  65%,
    rgba(2,50,130,.98) 100%);
}

/* Glanz auf Wasser (Lichtstrahl) */
.cyl-wg{
  position:absolute;top:9px;left:8%;width:15%;bottom:0;
  background:linear-gradient(90deg,
    transparent 0%,
    rgba(255,255,255,.05) 30%,
    rgba(255,255,255,.07) 50%,
    rgba(255,255,255,.03) 70%,
    transparent 100%);
  border-radius:0 0 50% 0;
}

/* Kaustics (Lichtmuster im Wasser) */
.cyl-caustic{
  position:absolute;top:9px;left:0;right:0;bottom:0;
  background:
    radial-gradient(ellipse 20px 40px at 40% 30%, rgba(100,210,255,.04) 0%, transparent 100%),
    radial-gradient(ellipse 15px 30px at 70% 60%, rgba(100,210,255,.03) 0%, transparent 100%);
  animation:caus 8s ease-in-out infinite;
}
@keyframes caus{
  0%,100%{opacity:1;transform:translateY(0)}
  50%{opacity:.5;transform:translateY(-4px)}
}

/* Blasen */
.cyl-bu{position:absolute;inset:0;overflow:hidden;z-index:3}
.bub{
  position:absolute;bottom:-8px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,
    rgba(255,255,255,.4) 0%,
    rgba(180,230,255,.15) 40%,
    rgba(100,180,255,.05) 100%);
  border:1px solid rgba(255,255,255,.3);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.5),
    0 1px 3px rgba(0,0,0,.2);
  animation:bub3d var(--bd2,5s) ease-in infinite var(--dl,0s);
}
@keyframes bub3d{
  0%  {transform:translateY(0)    translateX(0)  scale(1);  opacity:.9}
  20% {transform:translateY(-20%) translateX(2px) scale(1.04)}
  40% {transform:translateY(-42%) translateX(-2px) scale(.97)}
  60% {transform:translateY(-62%) translateX(3px) scale(1.02);opacity:.5}
  80% {transform:translateY(-82%) translateX(-1px) scale(.95);opacity:.25}
  100%{transform:translateY(-105%) translateX(0) scale(.7); opacity:0}
}

/* Licht-Reflexionen am Glas */
.cyl-refl{
  position:absolute;top:5%;bottom:5%;left:7px;width:3px;
  background:linear-gradient(180deg,
    transparent 0%,
    rgba(200,230,255,.15) 20%,
    rgba(200,230,255,.2) 50%,
    rgba(200,230,255,.1) 80%,
    transparent 100%);
  border-radius:4px;z-index:6;pointer-events:none;
}
.cyl-refl2{
  position:absolute;top:15%;bottom:15%;right:9px;width:2px;
  background:linear-gradient(180deg,
    transparent,rgba(160,210,255,.08),transparent);
  border-radius:4px;z-index:6;pointer-events:none;
}

/* Status Badge */
.wst{
  position:absolute;bottom:16px;left:50%;transform:translateX(-50%);
  padding:5px 16px;border-radius:100px;font-size:.76rem;font-weight:600;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(255,255,255,.1);white-space:nowrap;
  transition:all .5s;z-index:20;
  text-shadow:0 1px 2px rgba(0,0,0,.3);
}
.wok{background:rgba(16,185,129,.22);color:#6ee7b7;border-color:rgba(16,185,129,.22)}
.wwa{background:rgba(245,158,11,.22);color:#fcd34d;border-color:rgba(245,158,11,.22)}
.wda{background:rgba(239,68,68,.22);color:#fca5a5;border-color:rgba(239,68,68,.22)}
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

      <!-- Beschriftung oben -->
      <div class="wl">
        <div class="wpc" id="wpc">–<span class="wpcu">%</span></div>
        <div class="wsl">Füllstand</div>
        <div class="wlit" id="wlit-panel">– L</div>
      </div>

      <!-- 3D Glas-Zylinder -->
      <div class="tank3d">

        <!-- Maßstab links -->
        <div class="cyl-scale">
          <div class="csm">100%</div>
          <div class="csm">75%</div>
          <div class="csm">50%</div>
          <div class="csm">25%</div>
          <div class="csm">0%</div>
        </div>

        <!-- Zylinder Körper (Glas-Rohr) -->
        <div class="cyl-body">
          <div class="cyl-refl"></div>
          <div class="cyl-refl2"></div>

          <!-- Wasser-Füllung -->
          <div class="cyl-water" id="wf" style="height:0%">
            <!-- Wellen auf Wasseroberfläche -->
            <div class="cyl-surface">
              <div class="cyl-wave"></div>
              <div class="cyl-wave2"></div>
            </div>
            <!-- Wasser-Körper -->
            <div class="cyl-wb"></div>
            <!-- Glanz -->
            <div class="cyl-wg"></div>
            <!-- Blasen -->
            <div class="cyl-bu" id="bu"></div>
          </div>
        </div>

        <!-- Deckel oben -->
        <div class="cyl-top"></div>
        <!-- Boden unten -->
        <div class="cyl-bot"></div>
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

  // Hintergrundfarbe je nach Füllstand
  const wp=document.getElementById('wp');
  if(wp){
    if(p<15) wp.style.background='linear-gradient(175deg,#1a0505,#2a0808)';
    else if(p<20) wp.style.background='linear-gradient(175deg,#1a1005,#2a1a08)';
    else if(p>90) wp.style.background='linear-gradient(175deg,#051a20,#082030)';
    else wp.style.background='linear-gradient(175deg,#0d1f33,#091524)';
  }

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
    const d=await fetch('/api/aktuell').then(r=>r.json());
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
<div class="sg"><div class="sgl">Hardware / GPIO</div><div class="sc">
  <div class="sr"><div class="si"><div class="sl">TRIG Pin</div><div class="sd">GPIO BCM</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="trig_pin">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.trig_pin }}" min="1" max="40"><span class="ul">GPIO</span></div>
      <button type="submit" class="btn bb" style="padding:9px 16px;font-size:.85rem">Speichern</button>
    </form></div>
  <div class="sr"><div class="si"><div class="sl">ECHO Pin</div><div class="sd">GPIO BCM</div></div>
    <form method="POST" action="/einstellungen/speichern" style="display:flex;align-items:center;gap:8px">
      <input type="hidden" name="feld" value="echo_pin">
      <div class="si2"><input type="number" name="wert" value="{{ cfg.echo_pin }}" min="1" max="40"><span class="ul">GPIO</span></div>
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
    num={'intervall_sek':(10,3600),'trig_pin':(1,40),'echo_pin':(1,40),'warnung_leer':(1,50),'warnung_voll':(50,99),'kapazitaet_l':(100,500000),'dachflaeche_m2':(10,10000),'standort_lat':(-90,90),'standort_lon':(-180,180)}
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
        if GPIO_OK: GPIO.cleanup()
        scheduler.shutdown()
