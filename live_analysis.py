"""LIVE ANALYSIS — §72 AGENT DECISION TEMPLATE по текущему рынку.

Данные:
  • структура/триггер : Yahoo GC=F M15 (60 дней, реальное золото COMEX)
  • MTF-контекст      : Yahoo GC=F H1 (730 дней) → D1/H4/H1 EMA200, RSI
  • live-цена и спред : TradingView WebSocket OANDA:XAUUSD (спот)
  • кросс-чек индик.  : TradingView scanner (D1/H4/H1/M15)

Спот XAUUSD и фьючерс GC=F отличаются на базис (единицы USD) — помечено в выводе.
Решение формируется СТРОГО по frozen-параметрам PARAMETER_FREEZE_v1.md.

Запуск:  python3 live_analysis.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT.parent / "tradingview"))

import backtest as bt                                     # noqa: E402
import elliott as ew                                      # noqa: E402
from branches import BRANCHES, BY_ID, GEOMETRIES                  # noqa: E402
import events as evmod                                            # noqa: E402
from data import fetch_yahoo                              # noqa: E402

# PARAMETER_FREEZE_v2: торгуются только LONG-ветки, приоритет B04 → B01 → B02;
# SHORT (B05–B07) = DISABLED, B03 (W3 CLASS A) = CONTEXT_ONLY.
PRIO = [BY_ID[b] for b in ["B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"]]
DISABLED = {"B05_SHORT_CORE": "P0 DISABLED (v2)", "B06_SHORT_RSI_FIBOFF": "P0 DISABLED (v2)",
            "B07_SHORT_H4_ALIGNED": "P0 DISABLED (v2)", "B03_LONG_W3A_HV": "CONTEXT_ONLY (v2)"}
SYM_TV = "OANDA:XAUUSD"


def tv_snapshot() -> dict:
    """Live-цена/спред + индикаторы TV по таймфреймам."""
    out = {}
    try:
        from tv_client import TVSocket, scan
        with TVSocket() as s:
            q = s.quotes([SYM_TV, "TVC:DXY"]).get(SYM_TV, {})
            out["live"] = q
            out["spread_usd"] = round(q.get("ask", 0) - q.get("bid", 0), 3) if q.get("ask") else None
        out["tv"] = {}
        for tf in ["1D", "240", "60", "15"]:
            out["tv"][tf] = scan([SYM_TV], ["close", "EMA200", "RSI", "ATR", "Recommend.All"],
                                 market="global", timeframe=tf).get(SYM_TV, {})
        out["dxy"] = scan(["TVC:DXY"], ["close", "change", "EMA200", "RSI"], market="global").get("TVC:DXY", {})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== XAUUSD ELLIOTT AGENT — LIVE ANALYSIS ===\n{now} • spec v1.8 • freeze v1 • engine v2\n")

    # ── G00 DATA ─────────────────────────────────────────
    m15 = fetch_yahoo("GC=F", "15m", days=58)
    h1 = fetch_yahoo("GC=F", "1h", days=720)
    tv = tv_snapshot()
    spot = tv.get("live", {}).get("lp")
    data_ok = len(m15) > 500 and len(h1) > 5000
    print("── G00 DATA INTEGRITY")
    print(f"   M15 GC=F : {len(m15):,} баров  {m15.time.iloc[0]} → {m15.time.iloc[-1]}")
    print(f"   H1  GC=F : {len(h1):,} баров  {h1.time.iloc[0]} → {h1.time.iloc[-1]}")
    print(f"   TV spot  : {SYM_TV} = {spot}  bid/ask {tv.get('live',{}).get('bid')}/{tv.get('live',{}).get('ask')}"
          f"  → спред {tv.get('spread_usd')} USD")
    if spot and len(m15):
        print(f"   базис (спот − фьючерс): {spot - m15.close.iloc[-1]:+.2f} USD")
    state = "S01 DATA_VALIDATED" if data_ok else "S90 WAIT_DATA"
    print(f"   → {state}\n")
    if not data_ok:
        print("DECISION = WAIT (S90 WAIT_DATA): недостаточно данных"); return 1

    # ── структура и контекст ─────────────────────────────
    d = bt.prepare(m15, k=2.0)
    ctx = bt.build_context(m15, df_h1=h1, df_d1=h1)
    i = len(m15) - 2                      # последний ЗАКРЫТЫЙ бар (последний может быть неполным)
    ts = str(pd.Timestamp(d["t"][i]))
    c, atr_i = d["c"][i], d["atr"][i]

    print("── G02 MTF CONTEXT (только закрытые бары)")
    for tag, name in [("d1", "D1"), ("h4", "H4"), ("h1", "H1")]:
        cl, em, rs = ctx[f"{tag}_close"][i], ctx[f"{tag}_ema200"][i], ctx[f"{tag}_rsi"][i]
        rel = "выше" if cl > em else "ниже"
        print(f"   {name}: close {cl:.2f}  EMA200 {em:.2f}  → цена {rel} EMA200  RSI(14) {rs:.1f}")
    tvd1 = tv.get("tv", {}).get("1D", {})
    if tvd1:
        print(f"   кросс-чек TV: D1 close {tvd1.get('close')} EMA200 {tvd1.get('EMA200'):.2f} "
              f"RSI {tvd1.get('RSI'):.1f} ATR {tvd1.get('ATR'):.2f} Rec {tvd1.get('Recommend.All'):+.2f}")
    print(f"   M15 bar {ts}: close {c:.2f}  ATR(14) {atr_i:.2f}\n")

    # активная структура
    structs = d["structs"]
    active = None
    for bar in sorted(k for k in structs if k <= i):
        st = structs[bar]
        if st.dead(i, c):
            active = None
        else:
            active = st
    print("── G03/G04/G05 ELLIOTT STRUCTURE")
    if active is None:
        print("   структура не определена / мертва → S91 WAIT_STRUCTURE")
        print("\nDECISION = WAIT\nSTATE = S91 WAIT_STRUCTURE\nREASON = нет валидной causal Elliott структуры")
        return 0
    p = active.piv
    print(f"   kind={active.kind}  direction={'LONG (бычий)' if active.direction > 0 else 'SHORT (медвежий)'}")
    print(f"   as_of bar #{active.as_of} ({str(pd.Timestamp(d['t'][active.as_of]))[:16]}), возраст {i - active.as_of} баров "
          f"(лимит {ew.SETUP_MAX_AGE})")
    print("   пивоты: " + " → ".join(f"{x.kind}@{str(pd.Timestamp(d['t'][x.idx]))[5:16]}={x.price:.2f}" for x in p))
    if active.kind == "IMPULSE_W5":
        print(f"   W1={active.w1:.2f}  W2={active.w2:.2f} (ret {active.ret2:.3f})  "
              f"W3={active.w3:.2f}  W4={active.w4:.2f} (ret {active.ret4:.3f})")
        print(f"   W3/W1 = {active.ratio31:.3f} → CLASS {active.w3_class}   Fib ON = {active.fib_ok}")
        print(f"   structural invalidation = {active.invalidation:.2f}")
        print(f"   fib-цель W5 (диагностика) = {active.w5_target_fib:.2f}")

    # ── gates по веткам ──────────────────────────────────
    # §43 event filter: проверяем текущий бар
    ev_mask, ev_list = evmod.blocked_mask(d["t"])
    in_event = bool(ev_mask[i])
    ev_now = ev_list[(ev_list.time >= pd.Timestamp(d["t"][i]).tz_convert("UTC") - pd.Timedelta(hours=6)) &
                     (ev_list.time <= pd.Timestamp(d["t"][i]).tz_convert("UTC") + pd.Timedelta(hours=6))]
    print("\n── G08a EVENT FILTER (§43)")
    print(f"   событий в календаре: {len(ev_list)} (FOMC/NFP) • текущий бар в окне ±2h: {in_event}")
    if len(ev_now):
        print("   ближайшее событие: " + ", ".join(f"{r.event} @ {r.time:%Y-%m-%d %H:%M UTC}" for _, r in ev_now.iterrows()))

    print("\n── G06–G15 GATES ПО ВЕТКАМ (приоритет v2: B04 → B01 → B02)")
    skipped = {k: 0 for k in ["kind_mismatch", "w3_class", "regime", "h4", "confirm", "fib",
                              "trigger_absent", "sl_incompatible", "atr_nan", "in_position", "expired", "mtf_nan"]}
    chosen = None
    for br in PRIO:
        ok, extra = bt._eligible(active, br, i, ctx, d, skipped)
        mark = "✅ ELIGIBLE" if ok else "—"
        print(f"   {br.id:24s} {br.spec_ref:22s} {mark}")
        if ok and chosen is None:
            chosen, extra_info = br, extra
    if in_event and chosen is not None:
        print(f"\nDECISION = WAIT\nSTATE = S92 WAIT_CONFIRMATION")
        print("REASON = §43 event risk: бар сигнала в окне FOMC/NFP ±2h, вход запрещён (G08a)")
        print("Resume condition = окончание event-окна при сохранении структуры и триггера")
        print(f"MODEL VERSION = spec v1.8 / freeze v2 / engine v2 / {now}")
        return 0
    if chosen is None:
        why = []
        bull = ctx["d1_close"][i] > ctx["d1_ema200"][i]
        if active.kind != "IMPULSE_W5":
            why.append(f"структура {active.kind} — не IMPULSE_W5 (торгуемых веток нет, §6/§10)")
        if skipped["regime"]:
            why.append(f"G07 REGIME fail: D1 close {'>' if bull else '<'} EMA200, а для production LONG нужно > (§7)")
        if skipped["w3_class"]:
            why.append(f"G05 W3 class {active.w3_class} не входит в допустимые для prioritized веток")
        if skipped["fib"]:
            why.append("G08 Fib ON не выполнен (ret2/ret4 вне замороженных диапазонов)")
        if skipped["confirm"]:
            why.append("G08 mandatory confirmation (RSI H1) не выполнен")
        if skipped["h4"]:
            why.append("G07 H4 alignment не выполнен")
        if not why:
            why.append(f"G10 TRIGGER отсутствует: M15 close {c:.2f}, Donchian(8) up {d['dh'][i]:.2f} / down {d['dl'][i]:.2f}")
        print("\n" + "\n".join(f"   • {w}" for w in why))
        trig_state = "S94 WAIT_TRIGGER" if not skipped["trigger_absent"] and not any(
            skipped[x] for x in ["regime", "fib", "confirm", "h4", "w3_class"]) else "S92 WAIT_CONFIRMATION"
        if active.kind != "IMPULSE_W5":
            trig_state = "S91 WAIT_STRUCTURE"
        for bid, why_dis in DISABLED.items():
            b = BY_ID[bid]
            if b.direction == active.direction or True:
                pass
        print(f"\nDECISION = WAIT\nSTATE = {trig_state}")
        print("REASON = " + "; ".join(why))
        print(f"\nResume condition: {'валидный M15 trigger (close за Donchian-8)' if trig_state=='S94 WAIT_TRIGGER' else 'выполнение недостающего mandatory condition'}")
        print(f"MODEL VERSION = spec v1.8 / freeze v2 / engine v2 / {now}")
        return 0

    # ── executable setup ─────────────────────────────────
    geom = GEOMETRIES["G_BASE47"]      # единственная геометрия, прошедшая acceptance 11/11 в EXPERIMENT_v2
    entry = d["o"][i + 1] if i + 1 < len(m15) else np.nan
    sl_mult = geom.long_sl_atr if chosen.direction > 0 else geom.short_sl_atr
    sl = entry - sl_mult * atr_i if chosen.direction > 0 else entry + sl_mult * atr_i
    r_usd = abs(entry - sl)
    tp = entry + geom.tp_r * r_usd if chosen.direction > 0 else entry - geom.tp_r * r_usd
    compatible = (sl >= active.invalidation) if chosen.direction > 0 else (sl <= active.invalidation)
    print(f"\n── G12–G15 EXECUTION (branch {chosen.id}, geometry {geom.id})")
    print(f"   entry (next M15 open) = {entry:.2f}")
    print(f"   SL = {sl:.2f} ({sl_mult} ATR = {sl_mult*atr_i:.2f} USD)")
    print(f"   TP = {tp:.2f} ({geom.tp_r}R)")
    print(f"   R = {r_usd:.2f} USD   R:R = 1:{geom.tp_r}")
    print(f"   structural invalidation = {active.invalidation:.2f}  → SL совместим: {compatible}")
    print(f"   стоимость round-trip ≈ {tv.get('spread_usd') or 0.52:.2f} USD = {(tv.get('spread_usd') or 0.52)/r_usd:.3f}R")
    if not compatible:
        print("\nDECISION = WAIT\nSTATE = S95 WAIT_RISK\nREASON = SL несовместим со structural invalidation (§26)")
        return 0
    print(f"\nDECISION = {'LONG' if chosen.direction > 0 else 'SHORT'}")
    print("STATE = S17 SIGNAL_ISSUED → S18 SIGNAL_FROZEN (сигнал не переписывается, RULE 13)")
    print(f"MODEL VERSION = spec v1.8 / freeze v2 / engine v2 / {now}")
    print("\n⚠️ Это исследовательский сигнал по замороженным правилам, НЕ инвестиционная рекомендация.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
