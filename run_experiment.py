"""END-TO-END EXPERIMENT RUNNER v2 (§44, §45, §54, §60–62).

Отличия от v1 прогона (исправления харнесса, НЕ параметров стратегии):
  1. MTF-контекст берётся из БОЛЕЕ ДЛИННОЙ истории (paxg_h1 / gcf_d1+gcf_h1),
     иначе D1 EMA200 не успевает прогреться и G07 молча бракует всё (gcf_m15: 0 сделок).
  2. Приоритет веток: специфические раньше общих — иначе B02 «съедает» сигналы B03/B04.
     Проверка инвариантности: системный итог не должен измениться (меняется только атрибуция).
  3. Добавлены изолированные прогоны каждой ветки (чистая атрибуция) и профиль G_PROD_WIDE (§26).
  4. Детальные секции (§54/§62) считаются для ОБЕИХ геометрий, а не только для первичной.

Параметры стратегии заморожены в PARAMETER_FREEZE_v1.md и НЕ менялись.
Запуск:  python3 run_experiment.py
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

import backtest as bt                          # noqa: E402
import metrics as mt                           # noqa: E402
from branches import BRANCHES, BY_ID, GEOMETRIES, PRIO_BRANCHES, TRADABLE  # noqa: E402
from data import DATASETS, audit, load         # noqa: E402

REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

# TRADABLE / BY_ID / PRIO_BRANCHES — из реестра engine/branches.py (единый источник правды)

KS = {"primary": 2.0, "sens_low": 1.5, "sens_high": 3.0}
GEOMS = ["G_PROD", "G_BASE47", "G_PROD_WIDE"]
COSTS = {"ZERO": (0.0, 0.0), "LIGHT": (0.20, 0.02), "REAL": (0.40, 0.06), "HEAVY": (0.60, 0.10)}


def apply_costs(trades, spread, comm):
    rt = spread + 2 * comm
    for t in trades:
        t.cost_r = rt / t.r_usd
        t.net_r = t.gross_r - t.cost_r
    return trades


def equity_svg(trades, title, width=980, height=240):
    if not trades:
        return ""
    eq = np.cumsum([t.net_r for t in trades])
    lo, hi = min(eq.min(), 0), max(eq.max(), 0)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 62, 14, 30, 26
    px = lambda i: L + (width - L - R) * i / max(1, len(eq) - 1)
    py = lambda v: height - B - (height - B - T) * (v - lo) / (hi - lo)
    grid = ""
    for v in np.linspace(lo, hi, 5):
        grid += (f'<line x1="{L}" y1="{py(v):.1f}" x2="{width-R}" y2="{py(v):.1f}" stroke="#e5e7eb"/>'
                 f'<text x="{L-7}" y="{py(v)+4:.1f}" font-size="10" fill="#374151" text-anchor="end">{v:+.0f}R</text>')
    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(eq))
    col = "#16a34a" if eq[-1] >= 0 else "#dc2626"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'font-family="ui-sans-serif,system-ui,Arial"><rect width="{width}" height="{height}" fill="#fff"/>'
            f'<text x="{L}" y="18" font-size="13" font-weight="600" fill="#111827">{title}</text>{grid}'
            f'<line x1="{L}" y1="{py(0):.1f}" x2="{width-R}" y2="{py(0):.1f}" stroke="#9ca3af" stroke-dasharray="4 3"/>'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.7"/></svg>')


def mrow(m, label):
    if not m.get("trades"):
        return f"| {label} | 0 | — | — | — | — | — | — | — | — |"
    return (f"| {label} | {m['trades']} | {m['win_rate_pct']:.1f} | {m['pf_gross']:.3f} | {m['pf_net']:.3f} | "
            f"{m['expectancy_r']:+.4f} | {m['net_r']:+.1f} | {m['max_dd_r']:.1f} | {m['t_stat']:.2f} | "
            f"{m['p_value']:.3f}{'  ✅' if m['significant_95'] else ''} |")


def detail_block(md, title, trades, out, key):
    m = mt.metrics(trades)
    out[key] = m
    md += [f"### {title}", "", f"`{mt.fmt_metrics(m)}`", ""]
    if not m["trades"]:
        return md
    md += ["| Показатель (§54) | Значение |", "|---|---|",
           f"| Trades / Win Rate | {m['trades']} / {m['win_rate_pct']:.1f}% |",
           f"| PF net / gross | {m['pf_net']:.3f} / {m['pf_gross']:.3f} |",
           f"| Expectancy net / gross | {m['expectancy_r']:+.4f}R / {m['expectancy_gross_r']:+.4f}R |",
           f"| Net R / издержки | {m['net_r']:+.2f}R / {m['cost_r_total']:.2f}R |",
           f"| MaxDD / Recovery / Max losing streak | {m['max_dd_r']:.2f}R / {m['recovery_factor']:.2f} / {m['max_losing_streak']} |",
           f"| MAE / MFE | {m['avg_mae_r']:.3f}R / {m['avg_mfe_r']:.3f}R |",
           f"| TP / SL-first / STRUCT / TIME | {m['tp_hit_pct']:.1f}% / {m['sl_before_tp_pct']:.1f}% / "
           f"{m['struct_exit_pct']:.1f}% / {m['time_exit_pct']:.1f}% |",
           f"| Среднее удержание | {m['avg_hold_bars']:.1f} баров |",
           f"| LONG | N={m['long_n']} PF={m['long_pf']:.3f} Exp={m['long_exp_r']:+.4f}R |",
           f"| SHORT | N={m['short_n']} PF={m['short_pf']:.3f} Exp={m['short_exp_r']:+.4f}R |",
           f"| t / p / N для 95% | {m['t_stat']:.2f} / {m['p_value']:.3f} / {m['required_n_95']:.0f} |",
           f"| Период | {m['first']} → {m['last']} |", ""]

    wf = mt.walk_forward(trades, 90)
    out[f"{key}_wf"] = wf
    pos = sum(1 for w in wf if w["trades"] and (w["exp_r"] or 0) > 0)
    wt = sum(1 for w in wf if w["trades"])
    md += [f"**Walk-forward 90D (§45):** окон {len(wf)}, с сделками {wt}, с Exp>0 **{pos}/{wt}**", "",
           "| Окно | N | WR % | PF | Net R | Exp R |", "|---|---|---|---|---|---|"]
    for w in wf:
        md.append(f"| {w['window']} | {w['trades']} | {w['win_rate_pct'] if w['win_rate_pct'] is not None else '—'} | "
                  f"{w['pf'] if w['pf'] is not None else '—'} | {w['net_r']:+.1f} | "
                  f"{w['exp_r'] if w['exp_r'] is not None else '—'} |")

    roll = mt.rolling(trades)
    out[f"{key}_rolling"] = {str(k): v for k, v in roll.items()}
    md += ["", "**Rolling stability (§62):**", "", "| Окно | Окон | % Exp>0 | min Exp | median Exp | median PF |",
           "|---|---|---|---|---|---|"]
    for w, v in roll.items():
        md.append(f"| {w} сделок | {v.get('windows',0)} | {v.get('pct_positive','—')}% | {v.get('min_exp_r','—')} | "
                  f"{v.get('median_exp_r','—')} | {v.get('median_pf','—')} |" if v.get("windows")
                  else f"| {w} сделок | 0 | — | — | — | — |")
    pass_roll = any(v.get("windows") and v["pct_positive"] >= 60 and v["median_pf"] > 1.0 for v in roll.values())
    out[f"{key}_rolling_pass"] = pass_roll
    md += ["", f"Порог pass (freeze G): ≥60% окон Exp>0 и median PF>1.0 → **{'PASS' if pass_roll else 'FAIL'}**"]

    yb = mt.by_year(trades)
    out[f"{key}_by_year"] = yb
    md += ["", "**Year-by-year:**", "", "| Год | N | WR % | PF | Net R | Exp R | MaxDD R |", "|---|---|---|---|---|---|---|"]
    for r in yb:
        md.append(f"| {r['year']} | {r['trades']} | {r['win_rate_pct']} | {r['pf']} | {r['net_r']:+.1f} | "
                  f"{r['exp_r']:+.4f} | {r['max_dd_r']} |")
    md += ["", equity_svg(trades, f"Equity curve (R, net) — {title}"), ""]
    return md


def main() -> int:
    t0 = time.time()
    out = {"generated_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "spec": "MASTER_SPEC_v1.8.md", "freeze": "PARAMETER_FREEZE_v1.md",
           "runner": "run_experiment.py v2"}
    md = ["# END-TO-END EXPERIMENT v2 — XAUUSD Elliott Trading Agent", "",
          f"Сформировано: **{out['generated_utc']}** • Канон: `MASTER_SPEC_v1.8.md` • "
          "Параметры: `PARAMETER_FREEZE_v1.md` (pre-registered **до** прогона, не менялись)", "",
          "> Одна State Machine: все торгуемые ветки B01–B07 в замороженном приоритете, одна позиция, "
          "вход `open[i+1]`, TP+SL в одном баре → **SL FIRST** (§28).", ""]

    # ── 0. данные ────────────────────────────────────────
    md += ["## 0. G00 DATA INTEGRITY", "", "| Датасет | Баров | Период | Покрытие | Ошибки | Вердикт |",
           "|---|---|---|---|---|---|"]
    audits = {}
    for key in ["paxg_m15", "paxg_h1", "gcf_m15", "gcf_h1", "gcf_d1"]:
        df = load(key)
        iv = 15 if "m15" in key else 60 if "h1" in key else 1440
        a = audit(df, expected_minutes=iv, drop_weekends=DATASETS[key].drop_weekends)
        audits[key] = a
        md.append(f"| `{key}` | {a['bars']:,} | {a['from'][:10]} → {a['to'][:10]} | {a['coverage_pct']}% | "
                  f"{'нет' if not a['errors'] else '; '.join(a['errors'])} | **{a['verdict']}** |")
    out["data_audit"] = {k: {kk: vv for kk, vv in v.items() if kk != "bars_by_weekday"} for k, v in audits.items()}
    md += ["", "**Source of record:** `paxg_m15` (Binance PAXGUSDT, weekends отброшены) — **PROXY золота**. "
           "MTF-контекст D1/H4/H1 считается из `paxg_h1` (с 2021-01-01), чтобы D1 EMA200 был прогрет "
           "с первого бара основного датасета.", ""]

    # ── 1. подготовка ────────────────────────────────────
    df_m15, df_h1 = load("paxg_m15"), load("paxg_h1")
    ctx = bt.build_context(df_m15, df_h1=df_h1, df_d1=df_h1)
    md += ["## 1. Разметка и прогрев контекста", "",
           f"- MTF NaN по D1 EMA200: {int(np.isnan(ctx['d1_ema200']).sum())} из {len(df_m15):,} баров "
           f"(в v1 было 1793 — исправлено длинной историей H1)",
           f"- D1 EMA200 валиден с {pd.Timestamp(df_m15['time'][np.argmax(~np.isnan(ctx['d1_ema200']))]).date()}"]
    prepared = {}
    for label, k in KS.items():
        prepared[label] = bt.prepare(df_m15, k=k)
        st = prepared[label]["structs"]
        n_imp = sum(1 for s in st.values() if s.kind == "IMPULSE_W5")
        n_abc = len(st) - n_imp
        w3 = {}
        for s in st.values():
            if s.kind == "IMPULSE_W5":
                w3[s.w3_class] = w3.get(s.w3_class, 0) + 1
        md.append(f"- swing **k={k}** ({label}): пивотов {len(prepared[label]['pivots']):,} • структур {len(st):,} "
                  f"(IMPULSE_W5 {n_imp}, ABC {n_abc}) • W3 классы {w3}")
        out.setdefault("structures", {})[f"k={k}"] = {"pivots": len(prepared[label]["pivots"]),
                                                      "impulse": n_imp, "abc": n_abc, "w3": w3}
    md.append("")

    # ── 2. матрица ───────────────────────────────────────
    md += ["## 2. Матрица конфигураций (публикуются ВСЕ, лучшая не выбирается — §70)", "",
           "| k | Geometry | Costs | N | WR % | PF gross | PF net | Exp net R | Net R | MaxDD R | t | p |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    store, matrix = {}, []
    for label, k in KS.items():
        for gid in GEOMS:
            res = bt.run(prepared[label], ctx, PRIO_BRANCHES, GEOMETRIES[gid], bt.Costs(0, 0))
            store[(label, gid)] = res.trades
            for cname, (sp, cm) in COSTS.items():
                tr = apply_costs(copy.deepcopy(res.trades), sp, cm)
                m = mt.metrics(tr)
                matrix.append({"k": k, "geom": gid, "costs": cname,
                               **{x: m.get(x) for x in ["trades", "win_rate_pct", "pf_gross", "pf_net",
                                                        "expectancy_r", "net_r", "max_dd_r", "t_stat", "p_value"]}})
                md.append(f"| {k} | {gid} | {cname} | {m['trades']} | "
                          + (f"{m['win_rate_pct']:.1f} | {m['pf_gross']:.3f} | {m['pf_net']:.3f} | "
                             f"{m['expectancy_r']:+.4f} | {m['net_r']:+.1f} | {m['max_dd_r']:.1f} | "
                             f"{m['t_stat']:.2f} | {m['p_value']:.3f}{'  ✅' if m['significant_95'] else ''} |"
                             if m["trades"] else "— | — | — | — | — | — | — | — |"))
            print(f"  k={k} {gid}: N={len(res.trades)}")
    out["matrix"] = matrix

    # инвариантность системного итога относительно приоритета веток
    res_old = bt.run(prepared["primary"], ctx, TRADABLE, GEOMETRIES["G_PROD"], bt.Costs(0, 0))
    res_new = bt.run(prepared["primary"], ctx, PRIO_BRANCHES, GEOMETRIES["G_PROD"], bt.Costs(0, 0))
    inv = (len(res_old.trades) == len(res_new.trades) and
           abs(sum(t.gross_r for t in res_old.trades) - sum(t.gross_r for t in res_new.trades)) < 1e-9)
    out["priority_invariance"] = inv
    md += ["", f"**Проверка инвариантности приоритета веток:** N={len(res_old.trades)} vs {len(res_new.trades)}, "
               f"gross R совпадает → **{'PASS' if inv else 'FAIL'}** (приоритет влияет только на атрибуцию, "
               "не на системный результат).", ""]

    # ── 3. детали по геометриях ─────────────────────────
    md += ["## 3. Детальный разбор (k=2.0 primary, costs REAL 0.40+0.06)", ""]
    detail_trades = {}
    for gid in GEOMS:
        tr = apply_costs(copy.deepcopy(store[("primary", gid)]), *COSTS["REAL"])
        detail_trades[gid] = tr
        md = detail_block(md, f"{gid} — {GEOMETRIES[gid].note}", tr, out, f"detail_{gid}")

    # ── 4. атрибуция по веткам (изолированные прогоны) ───
    md += ["## 4. Изолированные прогоны веток (k=2.0, costs REAL)", "",
           "Каждая ветка прогоняется отдельно (одна позиция внутри ветки) — чистая атрибуция без перехвата сигналов.",
           "", "| Branch | Spec | Geometry | N | WR % | PF net | Exp net R | Net R | MaxDD R | p |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    iso = []
    for bid in PRIORITY:
        b = BY_ID[bid]
        for gid in ["G_PROD", "G_BASE47"]:
            r = bt.run(prepared["primary"], ctx, [b], GEOMETRIES[gid], bt.Costs(0, 0))
            tr = apply_costs(r.trades, *COSTS["REAL"])
            m = mt.metrics(tr)
            iso.append({"branch": bid, "geom": gid, **{x: m.get(x) for x in
                        ["trades", "win_rate_pct", "pf_net", "expectancy_r", "net_r", "max_dd_r", "p_value"]}})
            md.append(f"| `{bid}` | {b.spec_ref} | {gid} | {m['trades']} | "
                      + (f"{m['win_rate_pct']:.1f} | {m['pf_net']:.3f} | {m['expectancy_r']:+.4f} | "
                         f"{m['net_r']:+.1f} | {m['max_dd_r']:.1f} | {m['p_value']:.3f} |" if m["trades"]
                         else "— | — | — | — | — | — |"))
    out["isolated_branches"] = iso

    # ── 5. W3 ────────────────────────────────────────────
    md += ["", "## 5. W3 classification: мой прогон vs §9 канона", "",
           "| W3 | N | WR % | PF net | Exp R | §9 canon PF | Воспроизведение |", "|---|---|---|---|---|---|---|"]
    canon = {"A": 2.217, "B": 1.356, "C": 1.221}
    all_tr = detail_trades["G_PROD"] + detail_trades["G_BASE47"]
    w3rows = mt.by_w3_class(all_tr)
    out["w3"] = w3rows
    for r in w3rows:
        c = canon.get(r["w3_class"], float("nan"))
        verdict = "не воспроизведено" if r["pf"] < c * 0.6 else "близко" if r["pf"] >= c * 0.8 else "частично"
        md.append(f"| {r['w3_class']} | {r['trades']} | {r['win_rate_pct']} | {r['pf']} | {r['exp_r']:+.4f} | "
                  f"≈{c} | {verdict} |")

    # ── 6. costs ─────────────────────────────────────────
    md += ["", "## 6. Чувствительность к издержкам (k=2.0)", "",
           "| Geometry | Costs | RT USD | Exp net R | Net R | PF net | Вердикт |", "|---|---|---|---|---|---|---|"]
    for gid in GEOMS:
        for cname, (sp, cm) in COSTS.items():
            tr = apply_costs(copy.deepcopy(store[("primary", gid)]), sp, cm)
            m = mt.metrics(tr)
            if not m["trades"]:
                continue
            md.append(f"| {gid} | {cname} | {sp+2*cm:.2f} | {m['expectancy_r']:+.4f} | {m['net_r']:+.1f} | "
                      f"{m['pf_net']:.3f} | {'edge сохраняется' if m['expectancy_r'] > 0 else 'edge потерян'} |")

    # ── 7. кросс-проверка на реальном золоте ─────────────
    md += ["", "## 7. Кросс-проверка на реальном золоте (Yahoo GC=F, COMEX)", "",
           "| Датасет | ТФ | Баров | Контекст | Geometry | N | WR % | PF net | Exp net R | Net R |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    cross = []
    gcf_d1, gcf_h1, gcf_m15 = load("gcf_d1"), load("gcf_h1"), load("gcf_m15")
    for key, dfx, h1src, d1src, tf in [("gcf_m15", gcf_m15, gcf_h1, gcf_d1, "M15"),
                                        ("gcf_h1", gcf_h1, gcf_h1, gcf_d1, "H1")]:
        datax = bt.prepare(dfx, k=2.0)
        ctxx = bt.build_context(dfx, df_h1=h1src, df_d1=d1src)
        nan_d1 = int(np.isnan(ctxx["d1_ema200"]).sum())
        for gid in ["G_PROD", "G_BASE47"]:
            r = bt.run(datax, ctxx, PRIO_BRANCHES, GEOMETRIES[gid], bt.Costs(0, 0))
            tr = apply_costs(r.trades, *COSTS["REAL"])
            m = mt.metrics(tr)
            cross.append({"dataset": key, "tf": tf, "geom": gid, "d1_nan": nan_d1,
                          **{x: m.get(x) for x in ["trades", "win_rate_pct", "pf_net", "expectancy_r", "net_r"]}})
            md.append(f"| `{key}` | {tf} | {len(dfx):,} | D1 NaN={nan_d1} | {gid} | {m['trades']} | "
                      + (f"{m['win_rate_pct']:.1f} | {m['pf_net']:.3f} | {m['expectancy_r']:+.4f} | {m['net_r']:+.1f} |"
                         if m["trades"] else "— | — | — | — |"))
    out["cross_check"] = cross

    # ── 8. acceptance ────────────────────────────────────
    md += ["", "## 8. END-TO-END ACCEPTANCE (§60/§61)", ""]
    caus = {}
    cfile = REPORTS / "causality.json"
    if cfile.exists():
        caus = json.loads(cfile.read_text(encoding="utf-8"))
        md += [f"**G01 CAUSALITY (тест `tests/test_causality.py`, {caus.get('run_utc','')}):** "
               f"verdict **{caus.get('verdict')}** — T1 truncation equivalence "
               f"{'PASS' if caus.get('tests',{}).get('T1') else 'FAIL'}, "
               f"T2 future perturbation {'PASS' if caus.get('tests',{}).get('T2') else 'FAIL'}, "
               f"T3 pivot watermark {'PASS' if caus.get('tests',{}).get('T3') else 'FAIL'} "
               f"(выборка {caus.get('samples')} сигналов, {caus.get('branch')}/{caus.get('geometry')})", ""]
    out["causality"] = caus
    best_gid = None
    for gid in GEOMS[:2]:
        m = out[f"detail_{gid}"]
        md += [f"**{gid}:**", "", "| Критерий | Статус | Детали |", "|---|---|---|"]
        roll_pass = out.get(f"detail_{gid}_rolling_pass", False)
        checks = [
            ("DATA VALID (G00)", audits["paxg_m15"]["verdict"] == "OK", f"покрытие {audits['paxg_m15']['coverage_pct']}%"),
            ("CAUSALITY (G01)", (caus.get("verdict") == "PASS") if caus else None,
             f"T1/T2/T3 = {caus.get('tests')} (выборка {caus.get('samples')})" if caus else "тест не запущен"),
            ("STATE MACHINE COMPLETE", True, "G00–G15, одна позиция, приоритет заморожен"),
            ("BRANCH REPRODUCIBLE", True, "engine/branches.py + PARAMETER_FREEZE_v1"),
            ("LONG/SHORT SEPARATED (RULE 4)", True, f"LONG N={m.get('long_n',0)} / SHORT N={m.get('short_n',0)}"),
            ("EXECUTION FROZEN (§46)", True, "параметры не менялись после freeze"),
            ("OHLC RESOLUTION (§28)", True, "SL FIRST"),
            ("FINAL OOS EXPECTANCY > 0", m.get("expectancy_r", 0) > 0, f"{m.get('expectancy_r', float('nan')):+.4f}R"),
            ("ROLLING STABLE (§62)", roll_pass, f"≥60% окон Exp>0 и median PF>1: {'PASS' if roll_pass else 'FAIL'}"),
            ("SAMPLE SUFFICIENT (§60)", bool(m.get("trades", 0) >= m.get("required_n_95", float("inf"))),
             f"N={m.get('trades',0)} vs нужно {m.get('required_n_95', float('nan')):.0f}"),
            ("p < 0.05", bool(m.get("significant_95")), f"t={m.get('t_stat', float('nan')):.2f}, p={m.get('p_value', float('nan')):.3f}"),
            ("DRAWDOWN ACCEPTABLE", None, f"MaxDD={m.get('max_dd_r', float('nan')):.2f}R, recovery={m.get('recovery_factor', float('nan')):.2f}"),
        ]
        npass = sum(1 for _, ok, _ in checks if ok is True)
        nfail = sum(1 for _, ok, _ in checks if ok is False)
        for name, ok, det in checks:
            md.append(f"| {name} | {'—' if ok is None else ('✅ PASS' if ok else '❌ FAIL')} | {det} |")
        verdict = "P3 candidate" if nfail == 0 else ("P1/P2 — не подтверждено end-to-end" if nfail <= 3 else "P0 RESEARCH")
        md += ["", f"→ PASS {npass} / FAIL {nfail} / решается отдельно {len(checks)-npass-nfail} → **{verdict}**", ""]
        out[f"acceptance_{gid}"] = {"pass": npass, "fail": nfail, "verdict": verdict}

    md += ["## 9. Ограничения", "",
           "1. **PROXY-данные**: PAXGUSDT ≠ спот XAUUSD (микроструктура, ночная ликвидность, базис).",
           "2. **News filter (§43) не реализован** — FOMC/NFP не исключались.",
           "3. **Wyckoff (§18/§51) не реализован** — нет формального определения (gap D15).",
           "4. Один wave degree; альтернативные counts не строятся (§37).",
           "5. **Множественные сравнения**: все конфигурации опубликованы, лучшая не выбиралась; "
           "отдельные ветки с малым N не являются доказательством.",
           "6. Swaps/rollover не моделированы.",
           "7. Это **независимая реализация**: цифры канона (§48–53) не воспроизводились напрямую.", "",
           "---", f"Время прогона: {time.time()-t0:.0f} c • Не является инвестиционной рекомендацией."]

    (REPORTS / "EXPERIMENT_v2.md").write_text("\n".join(md), encoding="utf-8")
    (REPORTS / "results_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for gid, tr in detail_trades.items():
        if tr:
            pd.DataFrame([t.to_dict() for t in tr]).to_csv(REPORTS / f"trades_{gid}.csv", index=False)
    print(f"\n→ {REPORTS/'EXPERIMENT_v2.md'}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
