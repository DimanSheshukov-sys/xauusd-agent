"""DASHBOARD — self-contained HTML (инлайн CSS/SVG, без внешних зависимостей).

Живая часть: TradingView WebSocket/scanner (спот XAUUSD, спред, MTF-индикаторы, DXY)
             + GC=F M15/H1 для структуры и решения по §72.
Статика: отчёты reports/*.json, trades_v2_candidate.csv, data/forward/collection_log.jsonl.

Виджет TradingView подключается скриптом — в sandbox-превью он не загрузится
(нет сети), в обычном браузере работает.

Запуск:  python3 dashboard.py   →  dashboard/index.html
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))

from analyze import analyze                              # noqa: E402

import os                                                 # noqa: E402

OUT = ROOT / "dashboard"
OUT.mkdir(exist_ok=True)
REP = ROOT / "reports"
FWD = Path(os.environ.get("XAU_FWD_DIR", str(ROOT / "data" / "forward")))

LIVE_JS = """
<script>
(function(){
  if(location.protocol === "file:") return;
  var C = {WAIT:"#f0b429", LONG:"#22c55e", SHORT:"#ef4444"};
  function set(id, v){ var e = document.getElementById(id); if(e && v !== undefined && v !== null) e.textContent = v; }
  function tick(){
    fetch("/api/live", {cache:"no-store"}).then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.ok) return;
      set("live-price", d.price); set("live-price-hint", d.bidask);
      set("live-chg", d.chg);     set("live-chg-hint", d.chg_usd);
      set("live-spread", d.spread); set("live-spread-hint", d.spread_hint);
      set("live-time", d.now_utc);
      set("live-decision", d.decision); set("live-state", d.state);
      var de = document.getElementById("live-decision"); if(de && C[d.decision]) de.style.color = C[d.decision];
      var rs = document.getElementById("live-reasons");
      if(rs && d.reasons) rs.innerHTML = d.reasons.map(function(x){ return "<li>" + x + "</li>"; }).join("");
      var bd = document.getElementById("live-badge"); if(bd) bd.textContent = "live · обновление каждые 20 c";
    }).catch(function(){
      var b=document.getElementById("staticBanner");
      if(b){ b.style.display="block"; }
    });
  }
  setInterval(tick, 20000); setTimeout(tick, 800);
})();
</script>
"""

GOLD, GREEN, RED, MUTED = "#f0b429", "#22c55e", "#ef4444", "#8b98b0"
BG, CARD, LINE = "#0b1220", "#131d33", "#22304d"


def jload(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ───────────────────────── SVG ─────────────────────────
def svg_candles(chart: dict, w=1000, h=340) -> str:
    bars = chart["bars"]
    if not bars:
        return ""
    lo = min(b["l"] for b in bars)
    hi = max(b["h"] for b in bars)
    inv = chart.get("invalidation")
    if inv:
        lo, hi = min(lo, inv), max(hi, inv)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 8, 62, 12, 26
    n = len(bars)
    px = lambda k: L + (w - L - R) * k / max(1, n - 1)
    py = lambda v: h - B - (h - B - T) * (v - lo) / (hi - lo)
    bw = max(0.8, (w - L - R) / n * 0.66)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">']
    for gv in np.linspace(lo, hi, 6):
        out.append(f'<line x1="{L}" y1="{py(gv):.1f}" x2="{w-R}" y2="{py(gv):.1f}" stroke="{LINE}" stroke-width="0.6"/>')
        out.append(f'<text x="{w-R+6}" y="{py(gv)+4:.1f}" font-size="10" fill="{MUTED}">{gv:.0f}</text>')
    for k, b in enumerate(bars):
        x = px(k)
        col = GREEN if b["c"] >= b["o"] else RED
        out.append(f'<line x1="{x:.1f}" y1="{py(b["h"]):.1f}" x2="{x:.1f}" y2="{py(b["l"]):.1f}" stroke="{col}" stroke-width="0.7"/>')
        yo, yc = py(b["o"]), py(b["c"])
        out.append(f'<rect x="{x-bw/2:.1f}" y="{min(yo,yc):.1f}" width="{bw:.1f}" height="{max(0.7,abs(yc-yo)):.1f}" fill="{col}" opacity="0.9"/>')
    # все подтверждённые пивоты
    for p in chart["pivots"]:
        x, y = px(p["x"]), py(p["price"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{MUTED}" opacity="0.75"/>')
    # пивоты активной структуры + подписи волн
    st = chart.get("structure") or []
    if st:
        pts = " ".join(f"{px(p['x']):.1f},{py(p['price']):.1f}" for p in st)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{GOLD}" stroke-width="1.8" opacity="0.95"/>')
        labels = ["W1", "W2", "W3", "W4", "W5?"] if len(st) >= 5 else ["A", "B", "C"]
        for k, p in enumerate(st):
            x, y = px(p["x"]), py(p["price"])
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{GOLD}"/>')
            if k < len(labels) - 1:
                mx = (x + px(st[k + 1]["x"])) / 2
                my = (y + py(st[k + 1]["price"])) / 2 - 6
                out.append(f'<text x="{mx:.1f}" y="{my:.1f}" font-size="11" font-weight="700" fill="{GOLD}" text-anchor="middle">{labels[k]}</text>')
    if inv:
        out.append(f'<line x1="{L}" y1="{py(inv):.1f}" x2="{w-R}" y2="{py(inv):.1f}" stroke="#60a5fa" stroke-width="1" stroke-dasharray="5 4"/>')
        out.append(f'<text x="{L+4}" y="{py(inv)-5:.1f}" font-size="10" fill="#60a5fa">structural invalidation {inv:.2f}</text>')
    # подписи времени
    for k in range(0, n, max(1, n // 6)):
        out.append(f'<text x="{px(k):.1f}" y="{h-8}" font-size="9.5" fill="{MUTED}" text-anchor="middle">{bars[k]["t"][5:16]}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_line(vals: list[float], w=1000, h=200, color=GOLD, fill=True, zero=False, label="") -> str:
    if not vals:
        return ""
    arr = np.array(vals, dtype=float)
    lo, hi = min(arr.min(), 0) if zero else arr.min(), max(arr.max(), 0) if zero else arr.max()
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 8, 52, 10, 20
    px = lambda k: L + (w - L - R) * k / max(1, len(arr) - 1)
    py = lambda v: h - B - (h - B - T) * (v - lo) / (hi - lo)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">']
    for gv in np.linspace(lo, hi, 4):
        out.append(f'<line x1="{L}" y1="{py(gv):.1f}" x2="{w-R}" y2="{py(gv):.1f}" stroke="{LINE}" stroke-width="0.6"/>')
        out.append(f'<text x="{w-R+6}" y="{py(gv)+4:.1f}" font-size="10" fill="{MUTED}">{gv:+.0f}</text>')
    if zero:
        out.append(f'<line x1="{L}" y1="{py(0):.1f}" x2="{w-R}" y2="{py(0):.1f}" stroke="{MUTED}" stroke-dasharray="4 3" stroke-width="0.8"/>')
    pts = " ".join(f"{px(k):.1f},{py(v):.1f}" for k, v in enumerate(arr))
    if fill:
        base = py(0) if zero else h - B
        out.append(f'<polygon points="{px(0):.1f},{base:.1f} {pts} {px(len(arr)-1):.1f},{base:.1f}" fill="{color}" opacity="0.13"/>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7"/>')
    if label:
        out.append(f'<text x="{L+4}" y="{T+8}" font-size="11" fill="{MUTED}">{label}</text>')
    out.append("</svg>")
    return "".join(out)


# ───────────────────────── HTML-кусочки ─────────────────────────
def card(title: str, body: str, sub: str = "", span: int = 1, accent: str = "") -> str:
    st = f' style="grid-column:span {span}"' if span > 1 else ""
    return (f'<section class="card"{st}><div class="ct"><h2>{title}</h2>'
            + (f'<span class="sub">{sub}</span>' if sub else "") + f'</div>'
            + (f'<div class="accent" style="background:{accent}"></div>' if accent else "")
            + f'<div class="cb">{body}</div></section>')


def kpi(label: str, value: str, tone: str = "", hint: str = "", kid: str = "") -> str:
    idattr = f' id="{kid}"' if kid else ""
    hid = f' id="{kid}-hint"' if kid else ""
    return (f'<div class="kpi"><span>{label}</span><b class="{tone}"{idattr}>{value}</b>'
            + (f'<i{hid}>{hint}</i>' if hint else "") + '</div>')


def tbl(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def fnum(v, spec=".3f", dash="—"):
    """None-safe форматирование."""
    if v is None or (isinstance(v, float) and v != v):
        return dash
    return format(v, spec)


def tone(v, invert=False):
    if v is None:
        return ""
    return ("neg" if v > 0 else "pos") if invert else ("pos" if v > 0 else "neg")


def build() -> str:
    A = analyze()
    v3 = jload(REP / "results_v3.json", {}) or {}
    wf = jload(REP / "walkforward_v2.json", {}) or {}
    v2 = jload(REP / "results_v2.json", {}) or {}
    caus = jload(REP / "causality.json", {}) or {}
    cand = v3.get("candidate", {})
    trades = pd.read_csv(REP / "trades_v2_candidate.csv") if (REP / "trades_v2_candidate.csv").exists() else pd.DataFrame()
    fwlog = []
    if (FWD / "collection_log.jsonl").exists():
        fwlog = [json.loads(x) for x in (FWD / "collection_log.jsonl").read_text(encoding="utf-8").strip().split("\n") if x]
    fw = fwlog[-1] if fwlog else {}
    fsig = pd.read_csv(FWD / "forward_signals.csv") if (FWD / "forward_signals.csv").exists() else pd.DataFrame()

    tv = A.get("tv", {})
    live = tv.get("live", {})
    price = live.get("lp")
    chp = live.get("chp")
    spread = tv.get("spread")
    dxy = tv.get("dxy", {})
    dec = A["decision"]
    st = A["structure"]
    mtf = A["mtf"]
    m15 = A["m15"]

    dcolor = {"LONG": GREEN, "SHORT": RED, "WAIT": GOLD}.get(dec["decision"], MUTED)
    H = []
    H.append(f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAUUSD Elliott Trading Agent — Dashboard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%276%27 fill=%27%230b1220%27/%3E%3Crect x=%2714.5%27 y=%276%27 width=%273%27 height=%2720%27 fill=%27%23f0b429%27/%3E%3Crect x=%2710%27 y=%2711%27 width=%2712%27 height=%2710%27 fill=%27%23f0b429%27/%3E%3C/svg%3E">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:#e6edf7;font-family:ui-sans-serif,system-ui,'Segoe UI',Roboto,Arial;
 font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1440px;margin:0 auto;padding:22px 20px 60px}}
header.top{{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;justify-content:space-between;
 border-bottom:1px solid {LINE};padding-bottom:16px;margin-bottom:18px}}
h1{{font-size:23px;margin:0;letter-spacing:.2px}}
h1 span{{color:{GOLD}}}
.badges{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}
.badge{{background:#1b2740;border:1px solid {LINE};border-radius:999px;padding:3px 10px;font-size:11.5px;color:#c7d3e6}}
.badge.gold{{border-color:#5c4a17;color:{GOLD};background:#241d0c}}
.badge.green{{border-color:#1d4a33;color:#5ee39a;background:#0d2318}}
.ts{{color:{MUTED};font-size:12px;text-align:right}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.card{{background:{CARD};border:1px solid {LINE};border-radius:14px;padding:14px 16px 16px;position:relative;overflow:hidden}}
.card .ct{{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px}}
.card h2{{font-size:13px;margin:0;text-transform:uppercase;letter-spacing:.09em;color:#a9b7cf;font-weight:600}}
.card .sub{{font-size:11.5px;color:{MUTED}}}
.accent{{position:absolute;left:0;top:0;bottom:0;width:3px}}
.cb{{font-size:13px}}
.kpis{{display:flex;flex-wrap:wrap;gap:10px}}
.kpi{{flex:1 1 120px;background:#0f1830;border:1px solid {LINE};border-radius:10px;padding:9px 11px}}
.kpi span{{display:block;font-size:10.5px;color:{MUTED};text-transform:uppercase;letter-spacing:.06em}}
.kpi b{{display:block;font-size:19px;margin-top:3px;font-weight:650}}
.kpi i{{display:block;font-size:11px;color:{MUTED};font-style:normal;margin-top:2px}}
.pos{{color:#5ee39a}}.neg{{color:#ff7b7b}}.gold{{color:{GOLD}}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{padding:6px 8px;border-bottom:1px solid #1b2740;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
th{{color:#93a3bd;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em}}
tbody tr:hover{{background:#16213a}}
.big{{font-size:34px;font-weight:750;letter-spacing:.5px}}
.state{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:#9fd0ff}}
ul.reasons{{margin:8px 0 0;padding-left:18px;color:#c7d3e6}}
ul.reasons li{{margin:3px 0}}
.pill{{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;border:1px solid {LINE}}}
.pill.ok{{color:#5ee39a;border-color:#1d4a33;background:#0d2318}}
.pill.no{{color:#ff9b9b;border-color:#4a1d1d;background:#231010}}
.pill.warn{{color:{GOLD};border-color:#5c4a17;background:#241d0c}}
.note{{font-size:11.5px;color:{MUTED};margin-top:8px}}
.flow{{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}}
.flow div{{font-size:10.5px;padding:3px 7px;border-radius:6px;background:#0f1830;border:1px solid {LINE};color:#a9b7cf}}
.flow div.on{{border-color:#1d4a33;color:#5ee39a}}
.flow div.off{{border-color:#4a1d1d;color:#ff9b9b;text-decoration:line-through}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:1100px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.two{{grid-template-columns:1fr}}}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
footer{{margin-top:22px;padding-top:14px;border-top:1px solid {LINE};color:{MUTED};font-size:11.5px}}
code{{background:#0f1830;border:1px solid {LINE};padding:1px 5px;border-radius:5px;font-size:11.5px}}
.tvbox{{background:#0f1830;border:1px solid {LINE};border-radius:10px;height:420px;overflow:hidden}}
</style></head><body><div class="wrap">""")

    # ── header ──
    H.append(f"""<header class="top"><div>
<h1>XAUUSD <span>ELLIOTT</span> TRADING AGENT</h1>
<div class="badges">
<span class="badge gold">spec v1.8</span><span class="badge gold">freeze v2</span>
<span class="badge">engine v2</span><span class="badge green">status P2 (PROXY)</span>
<span class="badge">G01 causality {'PASS' if caus.get('verdict')=='PASS' else '—'}</span>
<span class="badge">structure-first</span>
</div></div>
<div class="ts"><span class="badge" id="live-badge">статичный снимок</span><br>
снимок: <span id="live-time">{A['now_utc']}</span><br>данные: GC=F M15 {A['data']['m15_bars']:,} баров · TV spot live<br>
источник: TradingView + Yahoo Finance</div></header>""")

    # ── live row ──
    live_kpis = "".join([
        kpi("XAUUSD спот (TV)", f"{price:,.2f}" if price else "—", "gold",
            f"bid {live.get('bid','—')} / ask {live.get('ask','—')}", kid="live-price"),
        kpi("Изм. за день", f"{chp:+.2f}%" if chp is not None else "—", tone(chp),
            f"{live.get('ch', 0):+,.2f} USD", kid="live-chg"),
        kpi("Спред", f"{spread:.2f} USD" if spread else "—", "",
            f"{(spread/(m15['atr']*2.5)*100 if spread else 0):.1f}% от R (2.5 ATR)", kid="live-spread"),
        kpi("M15 close (GC=F) · ATR(14)", f"{m15['close']:,.2f}", "",
            f"ATR {m15['atr']:.2f} USD · RSI {m15['rsi']:.1f} · базис спот−фьюч "
            f"{(price - m15['close']):+.1f} USD" if price else f"ATR {m15['atr']:.2f} USD"),
        kpi("DXY", f"{dxy.get('close','—')}", tone(-(dxy.get('change') or 0)),
            f"{(dxy.get('change') or 0):+.2f}% · EMA200 {dxy.get('EMA200', float('nan')):.2f}"),
        kpi("Баров в forward-окне", f"{fw.get('forward_bars', 0):,}", "",
            f"статус: {fw.get('status','—')}"),
    ])
    H.append('<div id="staticBanner" style="display:none;background:#14243d;border:1px solid #2b4a6b;'
             'color:#9fd0ff;border-radius:10px;padding:9px 13px;font-size:12.5px;margin-bottom:12px">'
             'Это <b>статичный снимок</b>: страница открыта без сервера данных. '
             'Реальное время, прогнозы с TP/SL и сопровождение сделок — на странице '
             '<a href="live.html" style="color:#f0b429"><b>LIVE →</b></a></div>')
    H.append('<div class="grid" style="margin-bottom:14px">' + card("Рынок сейчас", '<div class="kpis">' + live_kpis + '</div>', "live", 4, GOLD) + '</div>')

    # ── decision ──
    sig = dec.get("signal")
    if sig:
        body = (f'<div class="big" id="live-decision" style="color:{dcolor}">{dec["decision"]}</div>'
                f'<div class="state" id="live-state">{dec["state"]}</div>'
                + tbl(["Параметр", "Значение"], [
                    ["Branch", f'<code>{sig["branch"]}</code>'], ["Entry (next M15 open)", f'{sig["entry"]:,.2f}'],
                    ["SL", f'{sig["sl"]:,.2f} ({GEOM_A := 2.5} ATR)'], ["TP", f'{sig["tp"]:,.2f} ({sig["rr"]})'],
                    ["R", f'{sig["r_usd"]:.2f} USD'], ["Structural invalidation", f'{sig["invalidation"]:,.2f}'],
                    ["Cost / R", f'{sig["cost_usd"]:.2f} USD = {sig["cost_r"]:.3f}R'],
                    ["Max hold", f'{sig["max_hold"]} баров M15']])
                + '<div class="note">Сигнал заморожен в момент выдачи (S18, RULE 13) — переписыванию не подлежит.</div>')
    else:
        body = (f'<div class="big" id="live-decision" style="color:{dcolor}">{dec["decision"]}</div>'
                f'<div class="state" id="live-state">{dec["state"]}</div>'
                '<ul class="reasons" id="live-reasons">' + "".join(f"<li>{r}</li>" for r in dec["reason"]) + "</ul>"
                + '<div class="note">Resume condition: валидный IMPULSE_W5 + D1 close &gt; EMA200 + M15 Donchian(8) trigger.</div>')
    H.append('<div class="grid">' + card("Решение по §72", body, f'бар {A["data"]["last_bar_utc"]} UTC', 2, dcolor))

    # gates flow
    gate_names = ["G00 DATA", "G01 CAUSAL", "G02 MTF", "G03 ELLIOTT", "G04 TYPE", "G05 W3", "G06 BRANCH",
                  "G07 REGIME", "G08 CONFIRM", "G08a EVENT", "G10 TRIGGER", "G11 INVALID", "G12 EXEC",
                  "G13 TARGET", "G14 R:R", "G14a COST/R", "G15 DECISION"]
    bull = mtf["d1"]["above_ema"]
    off = set()
    if st is None:
        off |= {"G03 ELLIOTT", "G04 TYPE", "G05 W3", "G06 BRANCH", "G07 REGIME", "G08 CONFIRM", "G10 TRIGGER",
                "G11 INVALID", "G12 EXEC", "G13 TARGET", "G14 R:R", "G14a COST/R", "G15 DECISION"}
    elif st["kind"] != "IMPULSE_W5":
        off |= {"G04 TYPE", "G06 BRANCH", "G10 TRIGGER", "G12 EXEC", "G15 DECISION"}
    if not bull:
        off.add("G07 REGIME")
    if A["events"]["in_window"]:
        off.add("G08a EVENT")
    flow = "".join(f'<div class="{"off" if g in off else "on"}">{g}</div>' for g in gate_names)
    H.append(card("Gate pipeline (§10)", f'<div class="flow">{flow}</div>'
                  + tbl(["Branch (v2)", "Spec", "Eligible"], [[f'<code>{g["branch"]}</code>', g["spec"],
                        '<span class="pill ok">TRUE</span>' if g["eligible"] else '<span class="pill no">FALSE</span>']
                        for g in A["gates"]] or [["—", "нет активной структуры", "—"]]), "проход по G00→G15", 2))
    H.append("</div>")

    # ── MTF + структура ──
    mtf_rows = []
    for tag in ["d1", "h4", "h1"]:
        m = mtf[tag]
        tvc = tv.get("tv", {}).get({"d1": "1D", "h4": "240", "h1": "60"}[tag], {})
        mtf_rows.append([m["name"], f'{m["close"]:,.2f}', f'{m["ema200"]:,.2f}',
                         f'<span class="pill {"ok" if m["above_ema"] else "no"}">{"выше" if m["above_ema"] else "ниже"}</span>',
                         f'{m["dist_pct"]:+.2f}%', f'{m["rsi"]:.1f}',
                         f'{tvc.get("EMA200", float("nan")):,.2f}' if tvc else "—"])
    mtf_body = tbl(["ТФ", "Close", "EMA200", "Regime", "Δ", "RSI(14)", "EMA200 (TV-кроссчек)"], mtf_rows)
    mtf_body += (f'<div class="note">Regime filter §7: для production LONG требуется D1 close &gt; D1 EMA200. '
                 f'Сейчас — {"PASS" if bull else "FAIL"}. TV-кроссчек по споту (не по фьючерсу).</div>')

    if st:
        piv_rows = [[f'{k+1}', p["kind"], f'{p["price"]:,.2f}', p["time"]] for k, p in enumerate(st["pivots"])]
        sbody = (f'<div class="kpis">'
                 + kpi("Тип", st["kind"], "gold" if st["kind"] == "IMPULSE_W5" else "",
                       f'{st["direction_name"]}')
                 + kpi("Возраст", f'{st["age_bars"]} баров', "", f'лимит {st["max_age"]}')
                 + kpi("Invalidation", f'{st["invalidation"]:,.2f}', "", "structural, §11")
                 + (kpi("W3 class", st.get("w3_class", "—"), "gold", f'W3/W1 = {st.get("ratio31", float("nan")):.3f}')
                    if st["kind"] == "IMPULSE_W5" else kpi("Fib ON", "yes" if st["fib_ok"] else "no"))
                 + (kpi("Wyckoff (context)", "TRUE" if st.get("wyckoff") else "FALSE", "", "§18: gate запрещён")
                    if st["kind"] == "IMPULSE_W5" else "")
                 + "</div>"
                 + tbl(["#", "Тип", "Цена", "Время (UTC)"], piv_rows))
        if st["kind"] == "IMPULSE_W5":
            sbody += tbl(["Волна", "Размер (USD)", "Retracement"], [
                ["W1", f'{st["w1"]:.2f}', "—"], ["W2", f'{st["w2"]:.2f}', f'{st["ret2"]:.3f}'],
                ["W3", f'{st["w3"]:.2f}', f'W3/W1 = {st["ratio31"]:.3f} → class {st["w3_class"]}'],
                ["W4", f'{st["w4"]:.2f}', f'{st["ret4"]:.3f}'],
                ["W5 fib-цель (диагностика)", f'{st["w5_target"]:,.2f}', "TP не является (§13)"]])
    else:
        sbody = '<div class="note">Активной структуры нет: последний подтверждённый паттерн мёртв (пробой invalidation или возраст &gt; 200 баров).</div>'
    H.append('<div class="grid" style="margin-top:14px">'
             + card("MTF контекст (G02)", mtf_body, "только закрытые бары", 2)
             + card("Elliott structure (G03–G05)", sbody, f'as of {st["as_of_utc"]}' if st else "нет структуры", 2)
             + "</div>")

    # ── график ──
    H.append('<div class="grid" style="margin-top:14px">'
             + card("M15: пивоты и волны (causal, только подтверждённые)", svg_candles(A["chart"]),
                    f'последние {len(A["chart"]["bars"])} баров · k=2.0 × ATR(14)', 4, GOLD) + "</div>")

    # ── events ──
    up = A["events"]["upcoming"]
    ev_body = (f'<div class="kpis">' + kpi("Сейчас в окне ±2h", "ДА" if A["events"]["in_window"] else "НЕТ",
                                           "neg" if A["events"]["in_window"] else "pos", "§43: вход запрещён") + "</div>"
               + (tbl(["Событие", "Время (UTC)"], [[e["event"], e["time"]] for e in up]) if up
                  else '<div class="note">Ближайших FOMC/NFP в окне 48h нет.</div>')
               + '<div class="note">Покрыто: FOMC decision + NFP. CPI не покрыт (нет исторического календаря).</div>')
    H.append('<div class="grid" style="margin-top:14px">' + card("Event risk (§43)", ev_body, "FOMC + NFP", 2))

    # ── производительность ──
    if cand:
        perf = "".join([
            kpi("Trades", f'{cand["trades"]}', "", "research sample 2022–2026"),
            kpi("Win rate", f'{cand["win_rate_pct"]:.1f}%', "", f'LONG {cand["long_n"]} / SHORT {cand["short_n"]}'),
            kpi("PF net", f'{cand["pf_net"]:.3f}', "pos" if cand["pf_net"] > 1 else "neg", f'gross {cand["pf_gross"]:.3f}'),
            kpi("Expectancy", f'{cand["expectancy_r"]:+.4f}R', tone(cand["expectancy_r"]), f'gross {cand["expectancy_gross_r"]:+.4f}R'),
            kpi("Net R", f'{cand["net_r"]:+.1f}R', tone(cand["net_r"]), f'издержки {cand["cost_r_total"]:.1f}R'),
            kpi("MaxDD", f'{cand["max_dd_r"]:.1f}R', "neg", f'recovery {cand["recovery_factor"]:.2f}'),
            kpi("p-value", f'{cand["p_value"]:.3f}', "pos" if cand.get("significant_95") else "neg", f't = {cand["t_stat"]:.2f}'),
            kpi("N для 95%", f'{cand["required_n_95"]:.0f}', "pos" if cand["trades"] >= cand["required_n_95"] else "neg",
                "SAMPLE SUFFICIENT" if cand["trades"] >= cand["required_n_95"] else "недостаточно"),
        ])
        eq = np.cumsum(trades["net_r"].to_numpy()) if len(trades) else np.array([])
        peak = np.maximum.accumulate(np.concatenate([[0], eq]))[:-1] if len(eq) else np.array([])
        dd = (eq - peak) if len(eq) else np.array([])
        charts = (svg_line(list(eq), color=GREEN, zero=True, label="equity, R (net)")
                  + svg_line(list(dd), color=RED, zero=True, label="drawdown, R"))
        H.append(card("Кандидат v2 · LONG_ONLY + G_BASE47 + event filter + costs 0.52 USD",
                      f'<div class="kpis">{perf}</div><div style="margin-top:10px">{charts}</div>',
                      "in-sample (selection bias объявлен) — подтверждение только forward OOS", 2, GREEN))
    H.append("</div>")

    # ── таблицы: годы, WF, геометрии, ветки ──
    yb = wf.get("by_year") or v3.get("candidate_by_year") or []
    if not yb and len(trades):
        t2 = trades.copy()
        t2["year"] = pd.to_datetime(t2.entry_time).dt.year
        yb = []
        for y, g in t2.groupby("year"):
            net = g.net_r.to_numpy()
            yb.append({"year": int(y), "trades": len(g), "win_rate_pct": round((net > 0).mean() * 100, 1),
                       "pf": round(float(net[net > 0].sum() / max(1e-9, -net[net < 0].sum())), 3),
                       "net_r": round(float(net.sum()), 1), "exp_r": round(float(net.mean()), 4)})
    year_body = tbl(["Год", "N", "WR %", "PF", "Net R", "Exp R"],
                    [[r["year"], r["trades"], r["win_rate_pct"], r["pf"], f'{r["net_r"]:+.1f}', f'{r["exp_r"]:+.4f}']
                     for r in yb]) if yb else '<div class="note">нет данных</div>'

    roll = wf.get("rolling", {})
    roll_body = tbl(["Окно", "Окон", "% Exp>0", "median Exp", "median PF"],
                    [[f"{k} сделок", v.get("windows", 0), f'{v.get("pct_positive","—")}%',
                      v.get("median_exp_r", "—"), v.get("median_pf", "—")] for k, v in roll.items()]
                    ) if roll else '<div class="note">нет данных</div>'
    roll_pass = any(v.get("windows") and v.get("pct_positive", 0) >= 60 and v.get("median_pf", 0) > 1.0
                    for v in roll.values())
    roll_body += f'<div class="note">Порог §62: ≥60% окон Exp&gt;0 и median PF&gt;1.0 → <b class="{"pos" if roll_pass else "neg"}">{"PASS" if roll_pass else "FAIL"}</b></div>'

    folds = wf.get("folds", [])
    fold_body = tbl(["Train → Test", "Выбрано", "Test N", "Test Exp", "Test Net R"],
                    [[f'{f["train"][:10]} → {f["test"][:10]}', f'<code>{f["selected"]}</code>', f["n_test"],
                      f'{f["exp_test"]:+.3f}' if f["exp_test"] is not None else "—", f'{f["net_test"]:+.1f}']
                     for f in folds]) if folds else ""
    fold_note = (f'<div class="note">Сделки были в {sum(1 for f in folds if f["n_test"])} из {len(folds)} фолдов; '
                 f'остальные — S27 NEEDS_MORE_DATA. OOS-выборка смещена к периоду высокой активности.</div>') if folds else ""

    H.append(f'<div class="grid" style="margin-top:14px">'
             + card("Year-by-year (§54)", year_body, "кандидат v2", 2)
             + card("Walk-forward OOS (§45)", roll_body + fold_note, f'{wf.get("oos",{}).get("trades","—")} OOS-сделок', 2)
             + "</div>")
    if fold_body:
        H.append(f'<div class="grid" style="margin-top:14px">' + card("Walk-forward по фолдам", fold_body,
                 "train 365d → test 90d, отбор внутри train", 4) + "</div>")

    # геометрии
    matrix = [r for r in (v2.get("matrix") or []) if r.get("k") == 2.0]
    if matrix:
        rows = [[str(r["geom"]), str(r["costs"]), str(r.get("trades", 0)), fnum(r.get("win_rate_pct"), ".1f"),
                 fnum(r.get("pf_net")), fnum(r.get("expectancy_r"), "+.4f"), fnum(r.get("net_r"), "+.1f"),
                 fnum(r.get("p_value"))] for r in matrix]
        H.append(f'<div class="grid" style="margin-top:14px">' + card(
            "Матрица конфигураций (§47 vs §25/§82 × издержки)",
            tbl(["Geometry", "Costs", "N", "WR %", "PF net", "Exp net R", "Net R", "p"], rows),
            "k=2.0 · PAXG PROXY · публикуется полностью, лучшая не выбирается (§70)", 4) + "</div>")

    # ветки
    iso = v2.get("isolated_branches") or []
    if iso:
        rows = [[f'<code>{r["branch"]}</code>', str(r["geom"]), str(r.get("trades", 0)),
                 fnum(r.get("win_rate_pct"), ".1f"), fnum(r.get("pf_net")),
                 fnum(r.get("expectancy_r"), "+.4f"), fnum(r.get("net_r"), "+.1f")] for r in iso]
        H.append(f'<div class="grid" style="margin-top:14px">' + card("Изолированные прогоны веток (реестр G06)",
                 tbl(["Branch", "Geometry", "N", "WR %", "PF net", "Exp net R", "Net R"], rows),
                 "каждая ветка отдельно · SHORT-ветки в v2 DISABLED", 4) + "</div>")

    # ── прокси, причинность, forward ──
    prox = v3.get("proxy", {})
    pm, ph, so = prox.get("m15", {}), prox.get("h1", {}), prox.get("signal_overlap", {})
    prox_body = tbl(["Показатель", "M15", "H1"], [
        ["Баров в перекрытии", f'{pm.get("bars","—"):,}', f'{ph.get("bars","—"):,}'],
        ["Корреляция доходностей", f'{pm.get("corr_returns","—")}', f'{ph.get("corr_returns","—")}'],
        ["Уровень базиса (медиана)", f'{pm.get("basis_median_usd","—")} USD', f'{ph.get("basis_median_usd","—")} USD'],
        ["Шум базиса (важно)", f'{pm.get("basis_noise_mean_usd","—")} USD = {pm.get("basis_noise_in_atr","—")} × ATR',
         f'{ph.get("basis_abs_mean_usd","—")} USD'],
    ]) + (f'<div class="note">Совпадение сигналов на общем окне: <b class="neg">{so.get("matched_within_1h",0)} из '
          f'{so.get("proxy",0)}</b> (на реальном золоте {so.get("real",0)}). Вывод: PAXG — directional/robustness стенд, '
          f'не замена споту для structural-валидации → <b>P3 заблокирован</b> до спот-данных.</div>')

    ca = caus.get("tests", {})
    caus_body = (tbl(["Тест", "Что проверяет", "Результат"], [
        ["T1 truncation", "сигнал на префиксе данных идентичен полному прогону",
         f'<span class="pill {"ok" if ca.get("T1") else "no"}">{"PASS" if ca.get("T1") else "FAIL"}</span>'],
        ["T2 perturbation", "500 баров абсурдного будущего не меняют решение",
         f'<span class="pill {"ok" if ca.get("T2") else "no"}">{"PASS" if ca.get("T2") else "FAIL"}</span>'],
        ["T3 watermark", "пивот не используется раньше confirm_idx",
         f'<span class="pill {"ok" if ca.get("T3") else "no"}">{"PASS" if ca.get("T3") else "FAIL"}</span>'],
    ]) + f'<div class="note">Выборка {caus.get("samples","—")} сигналов · {caus.get("branch","—")} / {caus.get("geometry","—")} · '
          f'{caus.get("run_utc","—")} · вердикт <b class="pos">{caus.get("verdict","—")}</b></div>')

    acc_n = fw.get("forward_metrics", {}).get("trades", len(fsig))
    fm = fw.get("forward_metrics", {}) or {}
    warns = fw.get("integrity_warnings", []) or []
    fw_body = (f'<div class="kpis">'
               + kpi("Статус", fw.get("status", "—"), "gold", f'запуск {fw.get("run_utc","—")} · всего {len(fwlog)}')
               + kpi("M15 в хранилище", f'{fw.get("m15_rows",0):,}', "", f'последний бар {str(fw.get("m15_to",""))[:16]}')
               + kpi("Forward-баров", f'{fw.get("forward_bars",0):,}', "", "после 2026-09-15 20:00 UTC")
               + kpi("Замороженных сигналов", f'{len(fsig)}', "pos" if len(fsig) else "gold",
                     f'новых за запуск: {fw.get("signals_new", 0)}')
               + kpi("Сделок к ACCEPT", f'{acc_n}/74', "pos" if acc_n >= 74 else "gold", "freeze v2 §4")
               + kpi("RULE 13 (целостность)", "OK" if not warns else f'{len(warns)} ⚠', "pos" if not warns else "neg",
                     "замороженные поля не менялись" if not warns else "есть расхождения!")
               + (kpi("Forward Exp", f'{fm["expectancy_r"]:+.4f}R', tone(fm.get("expectancy_r")), f'PF {fm.get("pf_net", float("nan")):.3f}')
                  if fm.get("trades") else "")
               + (kpi("Forward Net R", f'{fm["net_r"]:+.2f}R', tone(fm.get("net_r")), f'MaxDD {fm.get("max_dd_r", float("nan")):.2f}R')
                  if fm.get("trades") else "")
               + "</div>"
               + f'<div style="margin-top:10px;background:#0f1830;border:1px solid {LINE};border-radius:8px;height:10px;overflow:hidden">'
               + f'<div style="width:{min(100, acc_n/74*100):.0f}%;height:100%;background:{GOLD}"></div></div>'
               + '<div class="note">Прогресс к ACCEPT: '
               f'{acc_n}/74 сделок ({acc_n/74*100:.0f}%). Критерии: Exp &gt; 0, p &lt; 0.10, MaxDD ≤ 15R, '
               'rolling ≥ 60% окон Exp&gt;0. Изменения правил запрещены до набора выборки (§64).</div>'
               + '<div class="note">Запуск: <code>python3 forward_collector.py</code> — раз в сутки достаточно.</div>')
    # ── журнал forward-сигналов и динамика ──
    fwd_extra = []
    if len(fsig):
        net = fsig["net_r"].to_numpy(float) if "net_r" in fsig else np.array([])
        closed = net[~np.isnan(net)] if len(net) else np.array([])
        eq = np.cumsum(closed) if len(closed) else np.array([])
        if len(eq):
            fwd_extra.append(svg_line(list(eq), color=GOLD, zero=True, label="forward OOS equity, R (net)"))
        rows = []
        for _, r in fsig.tail(15).iloc[::-1].iterrows():
            rows.append([str(r.get("entry_time", ""))[:16],
                         '<span class="pill ok">LONG</span>' if r.get("direction", 1) > 0 else '<span class="pill no">SHORT</span>',
                         f'<code>{r.get("branch","")}</code>', f'{r.get("entry", float("nan")):,.2f}',
                         f'{r.get("sl", float("nan")):,.2f}', f'{r.get("tp", float("nan")):,.2f}',
                         f'{r.get("r_usd", float("nan")):.2f}', str(r.get("w3_class", "—")),
                         str(r.get("reason", "")) or "—",
                         f'{r.get("net_r", float("nan")):+.2f}R' if pd.notna(r.get("net_r")) else "открыта"])
        fwd_extra.append(tbl(["Entry (UTC)", "Dir", "Branch", "Entry", "SL", "TP", "R USD", "W3", "Исход", "Net R"], rows))
        fwd_extra.append('<div class="note">Журнал append-only: entry/SL/TP/R/invalidation заморожены в момент выдачи '
                         '(S18, RULE 13) и не перезаписываются; обновляются только поля исхода.</div>')
    else:
        fwd_extra.append('<div class="note">Сигналов пока нет — идёт накопление данных forward-окна '
                         '(нужно ≥200 M15-баров ≈ 2 торговых дня для первого прогона).</div>')

    if len(fwlog) > 1:
        dyn = []
        for r in fwlog[-12:]:
            m = r.get("forward_metrics", {}) or {}
            dyn.append([str(r.get("run_utc", ""))[:19], f'{r.get("m15_rows",0):,}', f'{r.get("forward_bars",0):,}',
                        str(r.get("signals_total", 0)), str(m.get("trades", 0) or 0),
                        fnum(m.get("expectancy_r"), "+.4f"), fnum(m.get("net_r"), "+.2f"),
                        str(r.get("status", "—"))])
        fwd_extra.append('<div style="margin-top:12px">' + tbl(
            ["Запуск (UTC)", "M15 всего", "Forward-баров", "Сигналов", "Сделок", "Exp R", "Net R", "Статус"], dyn)
            + '<div class="note">История запусков `forward_collector.py` — видно, как накапливается выборка forward OOS.</div></div>')

    H.append(f'<div class="grid" style="margin-top:14px">'
             + card("Валидация PROXY (PAXG vs GC=F)", prox_body, "почему P3 заблокирован", 2)
             + card("G01 Causality (§70)", caus_body, "доказательство отсутствия look-ahead", 2)
             + card("Forward OOS tracker", fw_body, "единственный путь к P3/P4 · автообновление при каждом запуске коллектора", 4, GOLD)
             + card("Forward OOS: замороженные сигналы и динамика", "".join(fwd_extra),
                    "append-only журнал (RULE 13) + история запусков", 4)
             + "</div>")

    # ── TV widget ──
    H.append(f'<div class="grid" style="margin-top:14px">' + card("Живой график TradingView",
             '<div class="tvbox" id="tv"></div>'
             '<div class="note">Виджет загружается с s3.tradingview.com — в sandbox-превью сети нет, '
             'поэтому блок пустой. Откройте файл в обычном браузере.</div>'
             '<script>try{var s=document.createElement("script");'
             's.src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";s.async=true;'
             's.innerHTML=JSON.stringify({autosize:true,symbol:"OANDA:XAUUSD",interval:"15",timezone:"Etc/UTC",'
             'theme:"dark",style:"1",locale:"ru",hide_top_toolbar:false,allow_symbol_change:false,'
             'studies:["STD;EMA","STD;RSI","STD;ATR"],"support_host":"https://www.tradingview.com"});'
             'document.getElementById("tv").appendChild(s);}catch(e){}</script>',
             "OANDA:XAUUSD · M15 · EMA/RSI/ATR", 4) + "</div>")

    H.append(LIVE_JS)
    H.append(f"""<footer>
Файлы: <code>MASTER_SPEC_v1.8.md</code> (канон) · <code>PARAMETER_FREEZE_v2.md</code> (замороженные правила) ·
<code>engine/</code> (9 модулей) · <code>reports/EXPERIMENT_v2.md, EXPERIMENT_v3.md, WALKFORWARD_v2.md</code> ·
<code>trades_v2_candidate.csv</code> · <code>журнал.md</code> (лог диалога).<br>
Ограничения: PROXY-данные (PAXG) для research sample; правила v2 сформированы по итогам этого периода → selection bias объявлен;
news filter без CPI; Wyckoff — контекст; один wave degree; swaps не моделированы.<br>
Сформировано {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())} · <b>Не является инвестиционной рекомендацией.</b>
</footer></div></body></html>""")
    return "".join(H)


if __name__ == "__main__":
    t0 = time.time()
    html = build()
    p = OUT / "index.html"
    p.write_text(html, encoding="utf-8")
    print(f"→ {p}  ({p.stat().st_size/1024:.0f} KB, {time.time()-t0:.1f}s)")
