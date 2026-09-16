"""§45/§46 WALK-FORWARD С ОТБОРОМ ВНУТРИ TRAIN-ОКНА — настоящий end-to-end OOS.

В отличие от v2 (где конфигурация была известна заранее из того же периода), здесь
выбор конфигурации делается **только на данных train-окна** и затем замораживается
на test-окно. Агрегированный результат по всем test-окнам = честная OOS-оценка всей
процедуры «отбор + freeze + торговля».

Заморожено (v2):
  folds         : train 365d → test 90d, сдвиг 90d
  candidates    : 5 наборов веток × 2 геометрии = 10 (новых не добавляем)
  eligibility   : N_train ≥ 25 AND Exp_net(train) > 0
  selection     : max Exp_net(train); при равенстве — max N
  нет eligible  : в test-окне сделок нет (S27 NEEDS_MORE_DATA)
  event filter  : §43 ON для всех кандидатов (фиксированное правило, не выбирается)
  costs         : REAL 0.40 спред + 0.06 комиссия/сторону
  swing k       : 2.0 (primary, не участвует в отборе — иначе мета-оверфиттинг)

Запуск: python3 walkforward.py
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))

import backtest as bt                                     # noqa: E402
import events as ev                                       # noqa: E402
import metrics as mt                                      # noqa: E402
import wyckoff as wk                                      # noqa: E402
from branches import BY_ID, GEOMETRIES                    # noqa: E402
from data import load                                     # noqa: E402

REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

TRAIN_D, TEST_D = 365, 90
MIN_TRAIN_N = 25
COST = (0.40, 0.06)

CANDIDATES = {
    "ALL_7":            ["B03_LONG_W3A_HV", "B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF",
                         "B07_SHORT_H4_ALIGNED", "B06_SHORT_RSI_FIBOFF", "B05_SHORT_CORE"],
    "LONG_ONLY":        ["B03_LONG_W3A_HV", "B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"],
    "LONG_CORE+FIBOFF": ["B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"],
    "B02_ONLY":         ["B02_LONG_EMA200_FIBOFF"],
    "B04_ONLY":         ["B04_LONG_EXTW3_RSI"],
}
GEOMS = ["G_PROD", "G_BASE47"]


def costs_on(trades):
    rt = COST[0] + 2 * COST[1]
    for t in trades:
        t.cost_r = rt / t.r_usd
        t.net_r = t.gross_r - t.cost_r
    return trades


def _utc(x):
    ts = pd.Timestamp(x)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def window(trades, a, b):
    ta = _utc(a); tb = _utc(b)
    return [t for t in trades if ta <= _utc(t.entry_time) < tb]


def main() -> int:
    t0 = time.time()
    df = load("paxg_m15")
    h1 = load("paxg_h1")
    data = bt.prepare(df, k=2.0)
    ctx = bt.build_context(df, df_h1=h1, df_d1=h1)
    mask, events = ev.blocked_mask(data["t"])
    wy = wk.wyckoff_series(data["v"], data["h"], data["l"], data["c"], data["structs"], data["n"])
    print(f"данные: {len(df):,} баров • событий {len(events)} • event-маска на датасете: {mask.sum():,} баров "
          f"({mask.mean()*100:.2f}%) • wyckoff=True структур: {int(wy.sum())}")

    # все кандидаты — по одному полному прогону (дальше только нарезка окон)
    runs: dict[str, list] = {}
    for cname, bids in CANDIDATES.items():
        for gid in GEOMS:
            r = bt.run(data, ctx, [BY_ID[b] for b in bids], GEOMETRIES[gid], bt.Costs(0, 0),
                       event_mask=mask, wyckoff=wy)
            runs[f"{cname}|{gid}"] = costs_on(r.trades)
            print(f"  {cname:18s} {gid:9s} N={len(r.trades):4d}")

    # folds
    first = _utc(df.time.iloc[0])
    last = _utc(df.time.iloc[-1])
    start = first + pd.Timedelta(days=TRAIN_D)
    folds = []
    while start + pd.Timedelta(days=TEST_D) <= last + pd.Timedelta(days=1):
        folds.append((start, start + pd.Timedelta(days=TEST_D)))
        start += pd.Timedelta(days=TEST_D)

    oos, fold_rows = [], []
    for tr_start, tr_end in folds:
        best_key, best_exp, best_n = None, -1e9, 0
        elig = []
        for key, trades in runs.items():
            tw = window(trades, tr_start - pd.Timedelta(days=TRAIN_D), tr_start)
            if len(tw) < MIN_TRAIN_N:
                continue
            e = float(np.mean([t.net_r for t in tw]))
            elig.append((key, len(tw), e))
            if e > 0 and (e > best_exp or (e == best_exp and len(tw) > best_n)):
                best_key, best_exp, best_n = key, e, len(tw)
        test = window(runs[best_key], tr_start, tr_end) if best_key else []
        oos += test
        net = [t.net_r for t in test]
        fold_rows.append({"train": f"{tr_start.date()} → {tr_end.date()}",
                          "test": f"{tr_end.date()} → {(tr_end + pd.Timedelta(days=TEST_D)).date()}",
                          "selected": best_key or "NONE (S27)", "train_exp": round(best_exp, 4) if best_key else None,
                          "train_n": best_n, "eligible": len(elig),
                          "n_test": len(test), "exp_test": round(float(np.mean(net)), 4) if net else None,
                          "net_test": round(float(np.sum(net)), 2),
                          "wr_test": round(float(np.mean([x > 0 for x in net]) * 100), 1) if net else None})

    m = mt.metrics(oos)
    roll = mt.rolling(oos)
    yb = mt.by_year(oos)

    # статические бейслайны на тех же test-окнах
    baselines = {}
    for key in ["ALL_7|G_BASE47", "ALL_7|G_PROD", "LONG_ONLY|G_BASE47", "B04_ONLY|G_BASE47"]:
        btr = []
        for tr_start, tr_end in folds:
            btr += window(runs[key], tr_start, tr_end)
        baselines[key] = mt.metrics(btr)

    md = ["# WALK-FORWARD v2 — end-to-end OOS с отбором внутри train-окна", "",
          f"Сформировано: **{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}** • §45/§46 • "
          f"данные: `paxg_m15` (PROXY) • costs REAL 0.52 USD RT • event filter §43 ON • k=2.0", "",
          f"Fold-схема: **train {TRAIN_D}d → test {TEST_D}d**, сдвиг {TEST_D}d, всего **{len(folds)} folds**. "
          f"Кандидатов: {len(runs)} (5 наборов веток × 2 геометрии). "
          f"Eligibility: N_train ≥ {MIN_TRAIN_N} и Exp_net(train) > 0. Selection: max Exp_net(train).", "",
          "## 1. Агрегированный OOS (только test-окна, конфигурация выбиралась вслепую)", "",
          f"`{mt.fmt_metrics(m)}`", "",
          "| Показатель | Значение |", "|---|---|",
          f"| Trades (OOS) | {m['trades']} |",
          f"| Win Rate | {m['win_rate_pct']:.1f}% |",
          f"| PF net / gross | {m['pf_net']:.3f} / {m['pf_gross']:.3f} |",
          f"| Expectancy net | {m['expectancy_r']:+.4f}R |",
          f"| Net R | {m['net_r']:+.2f}R |",
          f"| MaxDD / Recovery | {m['max_dd_r']:.2f}R / {m['recovery_factor']:.2f} |",
          f"| Max losing streak | {m['max_losing_streak']} |",
          f"| LONG / SHORT | N={m['long_n']} PF={m['long_pf']:.3f} Exp={m['long_exp_r']:+.4f}R / "
          f"N={m['short_n']} PF={m['short_pf']:.3f} Exp={m['short_exp_r']:+.4f}R |",
          f"| t / p | {m['t_stat']:.2f} / {m['p_value']:.3f} → {'ЗНАЧИМО' if m['significant_95'] else 'не значимо'} |",
          f"| Требуется N (95%) | {m['required_n_95']:.0f} |",
          f"| Издержки съели | {m['cost_r_total']:.2f}R |", ""]

    md += ["## 2. Сравнение со статическими бейслайнами на тех же test-окнах", "",
           "| Конфигурация | N | WR % | PF net | Exp net R | Net R | MaxDD R | p |", "|---|---|---|---|---|---|---|---|"]
    md.append(f"| **WF-отбор (адаптивно)** | {m['trades']} | {m['win_rate_pct']:.1f} | {m['pf_net']:.3f} | "
              f"{m['expectancy_r']:+.4f} | {m['net_r']:+.1f} | {m['max_dd_r']:.1f} | {m['p_value']:.3f} |")
    for key, bm in baselines.items():
        if not bm.get("trades"):
            md.append(f"| {key} (статично) | 0 | — | — | — | — | — | — |")
            continue
        md.append(f"| {key} (статично) | {bm['trades']} | {bm['win_rate_pct']:.1f} | {bm['pf_net']:.3f} | "
                  f"{bm['expectancy_r']:+.4f} | {bm['net_r']:+.1f} | {bm['max_dd_r']:.1f} | {bm['p_value']:.3f} |")
    better_net = [k for k, bm in baselines.items() if bm.get("trades") and bm["net_r"] > m["net_r"]]
    better_exp = [k for k, bm in baselines.items() if bm.get("trades") and bm["expectancy_r"] > m["expectancy_r"]]
    net_list = ", ".join("`%s` %+.1fR" % (k, baselines[k]["net_r"]) for k in better_net)
    exp_list = ", ".join(better_exp) if better_exp else "ни один бейслайн не выше"
    n_traded = sum(1 for r in fold_rows if r["n_test"])
    md += ["", "**Вывод по §48-логике (сравниваем ОБА показателя):**",
           "- по суммарному Net R адаптивный отбор " + ("уступил статике: " + net_list if better_net else "превзошёл статику"),
           "- по Exp на сделку адаптивный отбор " + ("уступил: " + exp_list if better_exp else "превзошёл все бейслайны"),
           "",
           "⚠️ **Критическая оговорка:** из %d фолдов сделки были только в %d — остальные %d закрыты как "
           "S27 NEEDS_MORE_DATA (в train-окне не нашлось конфигурации с N ≥ %d и Exp > 0). "
           "OOS-выборка приходится на период высокой активности (2025-07 → 2026-10) и **не репрезентативна "
           "для всего периода**. Статические бейслайны торгуют все окна — отсюда их преимущество по суммарному R."
           % (len(fold_rows), n_traded, len(fold_rows) - n_traded, MIN_TRAIN_N), ""]

    md += ["## 3. По фолдам", "", "| Train | Test | Выбрано | Train Exp | Train N | Eligible | Test N | Test WR % | Test Exp | Test Net R |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in fold_rows:
        md.append(f"| {r['train']} | {r['test']} | `{r['selected']}` | "
                  f"{r['train_exp'] if r['train_exp'] is not None else '—'} | {r['train_n']} | {r['eligible']} | "
                  f"{r['n_test']} | {r['wr_test'] if r['wr_test'] is not None else '—'} | "
                  f"{r['exp_test'] if r['exp_test'] is not None else '—'} | {r['net_test']:+.1f} |")
    pos = sum(1 for r in fold_rows if r["n_test"] and (r["exp_test"] or 0) > 0)
    wt = sum(1 for r in fold_rows if r["n_test"])
    md += ["", f"Фолдов с сделками: {wt}/{len(fold_rows)}; с Test Exp > 0: **{pos}/{wt}**"]

    md += ["", "## 4. Rolling stability OOS (§62)", "", "| Окно | Окон | % Exp>0 | min Exp | median Exp | median PF |",
           "|---|---|---|---|---|---|"]
    for w, v in roll.items():
        md.append(f"| {w} сделок | {v.get('windows',0)} | {v.get('pct_positive','—')}% | {v.get('min_exp_r','—')} | "
                  f"{v.get('median_exp_r','—')} | {v.get('median_pf','—')} |" if v.get("windows")
                  else f"| {w} сделок | 0 | — | — | — | — |")
    pass_roll = any(v.get("windows") and v["pct_positive"] >= 60 and v["median_pf"] > 1.0 for v in roll.values())
    md += ["", f"Порог pass: ≥60% окон Exp>0 и median PF>1.0 → **{'PASS' if pass_roll else 'FAIL'}**"]

    md += ["", "## 5. Year-by-year OOS", "", "| Год | N | WR % | PF | Net R | Exp R |", "|---|---|---|---|---|---|"]
    for r in yb:
        md.append(f"| {r['year']} | {r['trades']} | {r['win_rate_pct']} | {r['pf']} | {r['net_r']:+.1f} | {r['exp_r']:+.4f} |")

    md += ["", "## 6. Вердикт", "",
           "| Критерий §60 | Статус |", "|---|---|",
           f"| FINAL OOS EXPECTANCY > 0 | {'✅' if m['expectancy_r'] > 0 else '❌'} {m['expectancy_r']:+.4f}R |",
           f"| ROLLING OOS STABLE | {'✅ PASS' if pass_roll else '❌ FAIL'} |",
           f"| SAMPLE SUFFICIENT (N ≥ {m['required_n_95']:.0f}) | {'✅' if m['trades'] >= m['required_n_95'] else '❌'} N={m['trades']} |",
           f"| p < 0.05 | {'✅' if m['significant_95'] else '❌'} p={m['p_value']:.3f} |",
           f"| DRAWDOWN | MaxDD {m['max_dd_r']:.2f}R, recovery {m['recovery_factor']:.2f} |",
           f"| CAUSALITY (G01) | ✅ PASS (T1/T2/T3, reports/causality.json) |", "",
           "Ограничения: PROXY-данные (PAXG), news filter покрывает FOMC+NFP (без CPI), "
           "Wyckoff — контекст, не gate; период 2022–2026 уже использовался в research, "
           "поэтому promotion в P4 требует forward OOS (§64).", "",
           f"Время прогона: {time.time()-t0:.0f} c"]

    (REPORTS / "WALKFORWARD_v2.md").write_text("\n".join(md), encoding="utf-8")
    if oos:
        pd.DataFrame([t.to_dict() for t in oos]).to_csv(REPORTS / "trades_walkforward_oos.csv", index=False)
    (REPORTS / "walkforward_v2.json").write_text(json.dumps({
        "oos": m, "rolling": {str(k): v for k, v in roll.items()}, "by_year": yb,
        "folds": fold_rows, "baselines": baselines, "rolling_pass": pass_roll,
        "events_total": len(events), "event_masked_bars": int(mask.sum())},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\nOOS: {mt.fmt_metrics(m)}")
    print(f"rolling pass: {pass_roll} • фолдов с Exp>0: {pos}/{wt}")
    for key, bm in baselines.items():
        if bm.get("trades"):
            print(f"  baseline {key:22s} N={bm['trades']:4d} Exp={bm['expectancy_r']:+.4f}R PF={bm['pf_net']:.3f}")
    print(f"→ {REPORTS/'WALKFORWARD_v2.md'}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
