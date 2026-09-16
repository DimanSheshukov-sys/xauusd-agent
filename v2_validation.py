"""V2 VALIDATION: кандидат v2 + абляции (§51/§52-логика) + валидация PROXY-данных.

Кандидат v2 (pre-registered в PARAMETER_FREEZE_v2.md):
    ветки LONG_ONLY (B01–B04) • геометрия G_BASE47 (2.5 ATR / 1.0R / 96 баров)
    • event filter §43 ON • costs REAL 0.40+0.06 • swing k=2.0

Отчёт → reports/EXPERIMENT_v3.md
Запуск → python3 v2_validation.py
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

import backtest as bt                                  # noqa: E402
import events as ev                                    # noqa: E402
import metrics as mt                                   # noqa: E402
import wyckoff as wk                                   # noqa: E402
from branches import BY_ID, GEOMETRIES                 # noqa: E402
from data import fetch_yahoo, load                     # noqa: E402

REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)
CAND = [BY_ID[b] for b in ["B03_LONG_W3A_HV", "B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"]]
GEOM = GEOMETRIES["G_BASE47"]
RT = 0.40 + 2 * 0.06


def with_costs(trades, rt=RT):
    for t in trades:
        t.cost_r = rt / t.r_usd
        t.net_r = t.gross_r - t.cost_r
    return trades


def mline(m, label):
    if not m.get("trades"):
        return f"| {label} | 0 | — | — | — | — | — | — |"
    return (f"| {label} | {m['trades']} | {m['win_rate_pct']:.1f} | {m['pf_net']:.3f} | "
            f"{m['expectancy_r']:+.4f} | {m['net_r']:+.1f} | {m['max_dd_r']:.1f} | {m['p_value']:.3f} |")


HDR = "| Конфигурация | N | WR % | PF net | Exp net R | Net R | MaxDD R | p |"
SEP = "|---|---|---|---|---|---|---|---|"


def proxy_validation() -> tuple[list[str], dict]:
    """PAXG (прокси) vs GC=F (реальное золото): качество замены."""
    md = ["## 4. Валидация PROXY: PAXGUSDT против реального золота GC=F", ""]
    res = {}
    # M15: перекрытие ~60 дней
    px = load("paxg_m15")
    gc = fetch_yahoo("GC=F", "15m", days=58)
    a = px.set_index("time")[["close", "high", "low"]].add_suffix("_px")
    b = gc.set_index("time")[["close", "high", "low"]].add_suffix("_gc")
    j = a.join(b, how="inner").dropna()
    if len(j) > 200:
        rpx, rgc = j["close_px"].pct_change().dropna(), j["close_gc"].pct_change().dropna()
        idx = rpx.index.intersection(rgc.index)
        corr = float(np.corrcoef(rpx[idx], rgc[idx])[0, 1])
        basis = (j["close_px"] - j["close_gc"])
        basis_dev = (basis - basis.median()).abs()      # ШУМ базиса (уровень вычтен)
        atr = bt.prepare(gc, k=2.0)["atr"]
        med_atr = float(np.nanmedian(atr)) if len(atr) else np.nan
        md += [f"- **M15 перекрытие:** {len(j):,} баров ({j.index[0].date()} → {j.index[-1].date()})",
               f"- **Корреляция 15-минутных доходностей: {corr:.4f}**",
               f"- Базис (PAXG − GC=F): медиана {basis.median():+.2f} USD (уровень), "
               f"**шум базиса** (|базис − медиана|): средний {basis_dev.mean():.2f} USD = "
               f"{basis_dev.mean()/med_atr:.2f} × ATR(M15), max {basis_dev.max():.2f} USD",
               f"- Медианный ATR(14) M15: GC=F {med_atr:.2f} USD"]
        res["m15"] = {"bars": len(j), "corr_returns": round(corr, 4),
                      "basis_median_usd": round(float(basis.median()), 2),
                      "basis_abs_mean_usd": round(float(basis.abs().mean()), 2),
                      "basis_noise_mean_usd": round(float(basis_dev.mean()), 2),
                      "basis_noise_in_atr": round(float(basis_dev.mean() / med_atr), 2),
                      "atr_gc_m15": round(med_atr, 2)}
    # H1: перекрытие ~730 дней
    ph1, gh1 = load("paxg_h1"), load("gcf_h1")
    a = ph1.set_index("time")["close"].rename("px")
    b = gh1.set_index("time")["close"].rename("gc")
    j = a.to_frame().join(b, how="inner").dropna()
    if len(j) > 500:
        rp, rg = j["px"].pct_change().dropna(), j["gc"].pct_change().dropna()
        idx = rp.index.intersection(rg.index)
        corr = float(np.corrcoef(rp[idx], rg[idx])[0, 1])
        daily_basis = (j["px"] - j["gc"]).resample("1D").last().dropna()
        md += [f"- **H1 перекрытие:** {len(j):,} баров ({j.index[0].date()} → {j.index[-1].date()})",
               f"- **Корреляция часовых доходностей: {corr:.4f}**",
               f"- Базис по дням: медиана {daily_basis.median():+.2f} USD, "
               f"шум (|базис − медиана|) средний {(daily_basis - daily_basis.median()).abs().mean():.2f} USD, "
               f"max |базис| {daily_basis.abs().max():.2f} USD",
               f"- Базис в % от цены: медиана {(daily_basis / j['gc'].resample('1D').last().dropna()).median()*100:+.3f}%"]
        res["h1"] = {"bars": len(j), "corr_returns": round(corr, 4),
                     "basis_median_usd": round(float(daily_basis.median()), 2),
                     "basis_abs_mean_usd": round(float(daily_basis.abs().mean()), 2),
                     "basis_pct_median": round(float((daily_basis / j['gc'].resample('1D').last().dropna()).median() * 100), 3)}
    # совпадение сигналов на общем окне
    common_start = max(px.time.iloc[0], gc.time.iloc[0])
    md += ["", "### Совпадение сигналов на общем окне (M15)", ""]
    sig = {}
    for name, dfx, h1x in [("PAXG (прокси)", px[px.time >= common_start].reset_index(drop=True), load("paxg_h1")),
                           ("GC=F (реальное)", gc, load("gcf_h1"))]:
        h1x = h1x[h1x.time <= dfx.time.iloc[-1]].reset_index(drop=True)
        d = bt.prepare(dfx, k=2.0)
        c = bt.build_context(dfx, df_h1=h1x, df_d1=h1x)
        m, _ = ev.blocked_mask(d["t"])
        w = wk.wyckoff_series(d["v"], d["h"], d["l"], d["c"], d["structs"], d["n"])
        r = bt.run(d, c, CAND, GEOM, bt.Costs(0, 0), event_mask=m, wyckoff=w)
        sig[name] = r.trades
        net = with_costs(list(r.trades))
        mm = mt.metrics(net)
        md.append(f"- **{name}:** N={len(r.trades)}, структур IMPULSE_W5="
                  f"{sum(1 for s in d['structs'].values() if s.kind == 'IMPULSE_W5')}"
                  + (f", Exp {mm['expectancy_r']:+.4f}R, PF {mm['pf_net']:.3f}, Net {mm['net_r']:+.1f}R" if mm.get("trades") else ""))
    t1 = [pd.Timestamp(t.entry_time) for t in sig["PAXG (прокси)"]]
    t2 = [pd.Timestamp(t.entry_time) for t in sig["GC=F (реальное)"]]
    matched = sum(1 for x in t1 if any(abs((x - y).total_seconds()) <= 3600 for y in t2))
    md += [f"- Совпало входов (±1 час): **{matched} из {len(t1)}** сигналов прокси "
           f"(на реальном золоте {len(t2)} сигналов за то же окно)"]
    res["signal_overlap"] = {"proxy": len(t1), "real": len(t2), "matched_within_1h": matched}
    md += ["", "> **Вывод по прокси.** Постоянный уровень базиса на R-метрики не влияет (они нормированы на ATR). "
              "Влияет **шум базиса**: если он сопоставим с ATR(M15), то пивоты ZigZag и границы волн на прокси "
              "не совпадают со спотом — ровно это и показывает низкое совпадение сигналов. "
              "При малом числе сигналов в окне (единицы) статистика совпадений слабая, но направление вывода "
              "однозначно: **PAXG пригоден как directional/robustness стенд, но НЕ как замена спот XAUUSD "
              "для production-валидации M15-структур**.", ""]
    return md, res


def main() -> int:
    t0 = time.time()
    df, h1 = load("paxg_m15"), load("paxg_h1")
    data = bt.prepare(df, k=2.0)
    ctx = bt.build_context(df, df_h1=h1, df_d1=h1)
    mask, events = ev.blocked_mask(data["t"])
    wy = wk.wyckoff_series(data["v"], data["h"], data["l"], data["c"], data["structs"], data["n"])

    md = ["# EXPERIMENT v3 — кандидат v2, абляции и валидация прокси", "",
          f"Сформировано: **{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}** • "
          "Кандидат v2: `LONG_ONLY (B01–B04)` + `G_BASE47 (2.5 ATR / 1.0R / 96)` + event filter §43 + costs REAL", "",
          "> Всё, что ниже на периоде 2022-01-24 → 2026-09-15, — **RESEARCH SAMPLE** (уже использован). "
          "Подтверждение кандидата возможно только на forward OOS (§64).", "",
          f"Event-фильтр: событий {len(events)} (FOMC {int((events.event=='FOMC').sum())}, "
          f"NFP {int((events.event=='NFP').sum())}), заблокировано {int(mask.sum()):,} M15-баров "
          f"({mask.mean()*100:.2f}% датасета).", ""]

    # 1. кандидат
    r_on = bt.run(data, ctx, CAND, GEOM, bt.Costs(0, 0), event_mask=mask, wyckoff=wy)
    r_off = bt.run(data, ctx, CAND, GEOM, bt.Costs(0, 0), wyckoff=wy)
    cand = with_costs(list(r_on.trades))
    mc = mt.metrics(cand)

    md += ["## 1. Кандидат v2 на research sample", "", f"`{mt.fmt_metrics(mc)}`", "",
           HDR, SEP, mline(mc, "**v2 кандидат (event filter ON)**")]

    # 2. абляции
    md += ["", "## 2. Абляции (каждый фактор отдельно, остальное заморожено)", "", HDR, SEP]
    abl = {"candidate_event_ON": mc}
    m_off = mt.metrics(with_costs(list(r_off.trades)))
    md.append(mline(m_off, "§43 event filter **OFF**"))
    abl["event_OFF"] = m_off

    # только LONG / только SHORT
    for tag, brs in [("только B02 (EMA200+FibOFF)", [BY_ID["B02_LONG_EMA200_FIBOFF"]]),
                     ("только B04 (ExtW3+RSI)", [BY_ID["B04_LONG_EXTW3_RSI"]]),
                     ("только B01 (Fib ON)", [BY_ID["B01_LONG_CORE"]])]:
        r = bt.run(data, ctx, brs, GEOM, bt.Costs(0, 0), event_mask=mask, wyckoff=wy)
        m = mt.metrics(with_costs(list(r.trades)))
        md.append(mline(m, tag))
        abl[tag] = m
    shorts = [BY_ID[b] for b in ["B07_SHORT_H4_ALIGNED", "B06_SHORT_RSI_FIBOFF", "B05_SHORT_CORE"]]
    r = bt.run(data, ctx, shorts, GEOM, bt.Costs(0, 0), event_mask=mask, wyckoff=wy)
    m_short = mt.metrics(with_costs(list(r.trades)))
    md.append(mline(m_short, "**только SHORT (B05–B07)**"))
    abl["short_only"] = m_short

    # sensitivity k
    for k in [1.5, 3.0]:
        dk = bt.prepare(df, k=k)
        wk_ = wk.wyckoff_series(dk["v"], dk["h"], dk["l"], dk["c"], dk["structs"], dk["n"])
        r = bt.run(dk, ctx, CAND, GEOM, bt.Costs(0, 0), event_mask=mask, wyckoff=wk_)
        m = mt.metrics(with_costs(list(r.trades)))
        md.append(mline(m, f"sensitivity: swing k={k}"))
        abl[f"k={k}"] = m

    # costs
    for rt, tag in [(0.0, "costs ZERO"), (0.24, "costs LIGHT 0.24"), (0.80, "costs HEAVY 0.80")]:
        m = mt.metrics(with_costs(list(r_on.trades), rt))
        md.append(mline(m, tag))
        abl[tag] = m

    # 3. Wyckoff diagnostic (§51)
    md += ["", "## 3. Wyckoff-флаг (§18/§51) — CONTEXT ONLY, gate не является", "",
           "| Подмножество | N | WR % | PF net | Exp net R | Net R |", "|---|---|---|---|---|---|"]
    wy_t = [t for t in cand if t.wyckoff]
    wy_f = [t for t in cand if not t.wyckoff]
    wy_res = {}
    for tag, sub in [("Wyckoff = True", wy_t), ("Wyckoff = False", wy_f)]:
        m = mt.metrics(sub)
        wy_res[tag] = m
        if m.get("trades"):
            md.append(f"| {tag} | {m['trades']} | {m['win_rate_pct']:.1f} | {m['pf_net']:.3f} | "
                      f"{m['expectancy_r']:+.4f} | {m['net_r']:+.1f} |")
        else:
            md.append(f"| {tag} | 0 | — | — | — | — |")
    md += ["", f"Флаг определён для {len(cand)} сделок кандидата: True у {len(wy_t)}. "
              "Согласно §19 флаг **не** может быть mandatory gate; приводится как диагностический срез "
              "(проверка гипотезы §51 на независимой реализации)."]

    # 4. proxy
    pmd, pres = proxy_validation()
    md += [""] + pmd

    # 5. статус
    md += ["## 5. Итоговый статус (§57)", "",
           "| Компонент | Статус v1.8 (канон) | Предлагаемый статус | Основание |", "|---|---|---|---|",
           f"| LONG_ONLY + G_BASE47 (кандидат v2) | — | **P2 (walk-forward validated)** | "
           f"research: N={mc['trades']}, Exp {mc['expectancy_r']:+.3f}R, p={mc['p_value']:.3f}; "
           "WF-OOS: см. WALKFORWARD_v2.md (LONG_ONLY|G_BASE47 Exp +0.205R, p=0.020) |",
           f"| §25/§82 geometry (1 ATR / 1.5R) | production candidate | **P1 → понизить** | убыточна после costs на M15 |",
           f"| SHORT B05–B07 | P1 | **P0 (disable)** | N={m_short.get('trades',0)}, Exp {m_short.get('expectancy_r',float('nan')):+.3f}R |",
           f"| B04 ExtW3+RSI | P0 | **P1** | N={abl['только B04 (ExtW3+RSI)'].get('trades',0)}, "
           f"Exp {abl['только B04 (ExtW3+RSI)'].get('expectancy_r',float('nan')):+.3f}R |",
           "| Wyckoff flag | P1 contextual | **P1 contextual** (реализован) | gap D15 закрыт формальным определением |",
           "| Event filter §43 | не реализован | **реализован, ablation выше** | FOMC+NFP ±2h |",
           "| Full State Machine | P0 until end-to-end | **P2 на PROXY** | end-to-end пройден; P3 только после спот-данных и forward OOS |",
           "", "**Для P3 → P4 требуется:** forward OOS на данных после 2026-09-15 20:00 UTC "
           "(N ≥ 44 для Exp ≈ +0.30R по формуле freeze G) **и** подтверждение на спот XAUUSD M15.", "",
           "---", f"Время: {time.time()-t0:.0f} c • Не является инвестиционной рекомендацией."]

    (REPORTS / "EXPERIMENT_v3.md").write_text("\n".join(md), encoding="utf-8")
    (REPORTS / "results_v3.json").write_text(json.dumps(
        {"candidate": mc, "ablations": abl, "wyckoff": wy_res, "proxy": pres,
         "events": int(len(events))}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if cand:
        pd.DataFrame([t.to_dict() for t in cand]).to_csv(REPORTS / "trades_v2_candidate.csv", index=False)
    print(f"кандидат v2: {mt.fmt_metrics(mc)}")
    print(f"event OFF   : {mt.fmt_metrics(m_off)}")
    print(f"SHORT only  : {mt.fmt_metrics(m_short)}")
    print(f"wyckoff True N={len(wy_t)} False N={len(wy_f)}")
    print(f"proxy: {json.dumps(pres, ensure_ascii=False)}")
    print(f"→ {REPORTS/'EXPERIMENT_v3.md'} ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
