"""Единая точка анализа рынка: возвращает словарь (используется CLI live_analysis.py и дашбордом).

Данные: GC=F M15 (реальное золото, 60 дней) + GC=F H1 (730 дней) для MTF-контекста,
        TradingView WebSocket/scanner — спот-цена, спред, кросс-чек индикаторов, DXY.
Конфигурация: PARAMETER_FREEZE_v2 (LONG_ONLY B04→B01→B02, G_BASE47, event filter, costs REAL).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT.parent / "tradingview"))

import backtest as bt                                   # noqa: E402
import elliott as ew                                    # noqa: E402
import events as ev                                     # noqa: E402
import wyckoff as wk                                    # noqa: E402
from branches import BY_ID, GEOMETRIES                  # noqa: E402
from data import fetch_yahoo                            # noqa: E402

CAND = [BY_ID[b] for b in ["B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"]]
GEOM = GEOMETRIES["G_BASE47"]
SYM_TV = "OANDA:XAUUSD"
RT = 0.40 + 2 * 0.06


def tv_snapshot() -> dict:
    out: dict = {}
    try:
        from tv_client import TVSocket, scan
        with TVSocket() as s:
            q = s.quotes([SYM_TV, "TVC:DXY"])
        out["live"] = q.get(SYM_TV, {})
        out["dxy_live"] = q.get("TVC:DXY", {})
        out["spread"] = round(out["live"].get("ask", 0) - out["live"].get("bid", 0), 3) if out["live"].get("ask") else None
        out["tv"] = {tf: scan([SYM_TV], ["close", "EMA200", "RSI", "ATR", "Recommend.All"],
                              market="global", timeframe=tf).get(SYM_TV, {}) for tf in ["1D", "240", "60", "15"]}
        out["dxy"] = scan(["TVC:DXY"], ["close", "change", "EMA200", "RSI"], market="global").get("TVC:DXY", {})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def analyze(chart_bars: int = 420) -> dict:
    now = pd.Timestamp.utcnow()
    m15 = fetch_yahoo("GC=F", "15m", days=58)
    h1 = fetch_yahoo("GC=F", "1h", days=720)
    m15["time"] = pd.to_datetime(m15["time"], utc=True)
    h1["time"] = pd.to_datetime(h1["time"], utc=True)

    d = bt.prepare(m15, k=2.0)
    ctx = bt.build_context(m15, df_h1=h1, df_d1=h1)
    mask, events = ev.blocked_mask(d["t"])
    wy = wk.wyckoff_series(d["v"], d["h"], d["l"], d["c"], d["structs"], d["n"])
    i = len(m15) - 2                                  # последний ЗАКРЫТЫЙ бар

    res: dict = {"now_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "engine": "v2", "freeze": "PARAMETER_FREEZE_v2",
                 "spec": "MASTER_SPEC v1.8", "instrument": "XAUUSD (анализ на GC=F M15)",
                 "data": {"m15_bars": len(m15), "h1_bars": len(h1),
                          "m15_from": str(m15.time.iloc[0])[:16], "m15_to": str(m15.time.iloc[-1])[:16],
                          "last_bar_utc": str(pd.Timestamp(d["t"][i]))[:16],
                          "pivots_total": len(d["pivots"]),
                          "impulse_structures": sum(1 for s in d["structs"].values() if s.kind == "IMPULSE_W5")},
                 "tv": tv_snapshot()}

    # ── MTF контекст ──
    res["mtf"] = {}
    for tag, name in [("d1", "D1"), ("h4", "H4"), ("h1", "H1")]:
        cl, em, rs = float(ctx[f"{tag}_close"][i]), float(ctx[f"{tag}_ema200"][i]), float(ctx[f"{tag}_rsi"][i])
        res["mtf"][tag] = {"name": name, "close": cl, "ema200": em, "rsi": rs,
                           "above_ema": bool(cl > em), "dist_pct": round((cl / em - 1) * 100, 3)}
    res["m15"] = {"close": float(d["c"][i]), "atr": float(d["atr"][i]), "rsi": float(d["rsi"][i]),
                  "donchian_hi": float(d["dh"][i]), "donchian_lo": float(d["dl"][i])}

    # ── events ──
    near = events[(events.time >= pd.Timestamp(d["t"][i]).tz_convert("UTC") - pd.Timedelta(hours=12)) &
                  (events.time <= pd.Timestamp(d["t"][i]).tz_convert("UTC") + pd.Timedelta(hours=48))]
    res["events"] = {"in_window": bool(mask[i]),
                     "upcoming": [{"event": r.event, "time": r.time.strftime("%Y-%m-%d %H:%M UTC")}
                                  for _, r in near.iterrows()]}

    # ── структура ──
    active = None
    for bar in sorted(k for k in d["structs"] if k <= i):
        st = d["structs"][bar]
        active = None if st.dead(i, d["c"][i]) else st
    if active is None:
        res["structure"] = None
    else:
        p = active.piv
        res["structure"] = {
            "kind": active.kind, "direction": int(active.direction),
            "direction_name": "LONG (бычий)" if active.direction > 0 else "SHORT (медвежий)",
            "as_of_bar": int(active.as_of), "as_of_utc": str(pd.Timestamp(d["t"][active.as_of]))[:16],
            "age_bars": int(i - active.as_of), "max_age": ew.SETUP_MAX_AGE,
            "pivots": [{"kind": x.kind, "price": float(x.price), "time": str(pd.Timestamp(d["t"][x.idx]))[:16],
                        "idx": int(x.idx)} for x in p],
            "invalidation": float(active.invalidation),
            "fib_ok": bool(active.fib_ok)}
        if active.kind == "IMPULSE_W5":
            res["structure"].update({"w1": active.w1, "w2": active.w2, "w3": active.w3, "w4": active.w4,
                                     "ret2": active.ret2, "ret4": active.ret4, "ratio31": active.ratio31,
                                     "w3_class": active.w3_class, "w5_target": active.w5_target_fib,
                                     "wyckoff": bool(wy[i])})

    # ── gates по веткам ──
    skipped = {k: 0 for k in ["kind_mismatch", "w3_class", "regime", "h4", "confirm", "fib",
                              "trigger_absent", "sl_incompatible", "atr_nan", "in_position", "expired",
                              "mtf_nan", "event_blocked"]}
    gates, chosen = [], None
    if active is not None:
        for br in CAND:
            ok, extra = bt._eligible(active, br, i, ctx, d, skipped)
            gates.append({"branch": br.id, "spec": br.spec_ref, "eligible": bool(ok)})
            if ok and chosen is None:
                chosen, extra_info = br, extra
    res["gates"] = gates
    res["skipped"] = {k: v for k, v in skipped.items() if v}

    # ── решение ──
    dec: dict = {"decision": "WAIT", "state": "S91 WAIT_STRUCTURE", "reason": [], "signal": None}
    bull = res["mtf"]["d1"]["above_ema"]
    if active is None:
        dec["reason"].append("нет валидной causal Elliott структуры (G03) — ни один пивот-паттерн не подтверждён")
    elif active.kind != "IMPULSE_W5":
        dec["reason"].append(f"структура {active.kind} — не IMPULSE_W5; ABC/Failed Fifth не торгуются (§6/§10)")
        if not bull:
            dec["reason"].append("дополнительно G07 REGIME fail для LONG: D1 close ниже EMA200 (§7)")
    else:
        if not bull:
            dec["reason"].append("G07 REGIME fail: D1 close ниже EMA200 → production LONG запрещён (§7)")
        if chosen is None:
            if skipped.get("fib"):
                dec["reason"].append("G08 Fib ON не выполнен (ret2/ret4 вне замороженных диапазонов)")
            if skipped.get("confirm"):
                dec["reason"].append("G08 mandatory confirmation не выполнен (RSI H1)")
            if skipped.get("w3_class"):
                dec["reason"].append(f"G05 W3 class {active.w3_class} не входит в допустимые для активных веток")
            if not dec["reason"]:
                dec["reason"].append(f"G10 TRIGGER отсутствует: M15 close {res['m15']['close']:.2f}, "
                                     f"Donchian(8) {res['m15']['donchian_lo']:.2f} / {res['m15']['donchian_hi']:.2f}")
                dec["state"] = "S94 WAIT_TRIGGER"
        elif mask[i]:
            dec["reason"].append("G08a EVENT: бар сигнала в окне FOMC/NFP ±2h (§43)")
            dec["state"] = "S92 WAIT_CONFIRMATION"
        else:
            entry = float(d["o"][i + 1]) if i + 1 < len(m15) else float("nan")
            sl = entry - GEOM.long_sl_atr * res["m15"]["atr"]
            r_usd = abs(entry - sl)
            tp = entry + GEOM.tp_r * r_usd
            spread = res["tv"].get("spread") or 0.52
            dec.update({"decision": "LONG", "state": "S17 SIGNAL_ISSUED → S18 SIGNAL_FROZEN",
                        "reason": ["все mandatory gates G00–G15 = TRUE"],
                        "signal": {"branch": chosen.id, "direction": "LONG", "entry": entry, "sl": sl, "tp": tp,
                                   "r_usd": r_usd, "rr": f"1:{GEOM.tp_r}", "invalidation": active.invalidation,
                                   "cost_usd": RT + spread, "cost_r": round((RT + spread) / r_usd, 4),
                                   "timeframe": "M15", "max_hold": GEOM.max_hold_bars}})
    res["decision"] = dec

    # ── данные для графика ──
    a = max(0, i - chart_bars)
    piv_in = [p for p in d["pivots"] if a <= p.idx <= i and p.confirm_idx <= i]
    res["chart"] = {
        "bars": [{"t": str(pd.Timestamp(t))[:16], "o": float(o), "h": float(h), "l": float(l), "c": float(c)}
                 for t, o, h, l, c in zip(d["t"][a:i + 1], d["o"][a:i + 1], d["h"][a:i + 1],
                                          d["l"][a:i + 1], d["c"][a:i + 1])],
        "pivots": [{"x": int(p.idx - a), "kind": p.kind, "price": float(p.price),
                    "time": str(pd.Timestamp(d["t"][p.idx]))[:16]} for p in piv_in],
        "structure": ([{"x": int(x.idx - a), "kind": x.kind, "price": float(x.price)} for x in active.piv]
                      if active is not None else []),
        "invalidation": float(active.invalidation) if active is not None else None,
    }
    return res


if __name__ == "__main__":
    import json
    r = analyze()
    print(json.dumps({k: v for k, v in r.items() if k != "chart"}, ensure_ascii=False, indent=1, default=str))
