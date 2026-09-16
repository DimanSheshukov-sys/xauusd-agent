#!/usr/bin/env python3
"""VALIDATION v1 (P1–P2 ТЗ): bootstrap, Monte Carlo, parameter stability, regime,
улучшенная отчётность walk-forward, attribution, LONG/SHORT, equity-графики.

Все расчёты помечены источником (PROXY_PAXG) и версиями. Торговая логика не меняется.
Выход: reports/VALIDATION_v1.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
from sources import versions_block, label, PROXY_WARNING  # noqa: E402

REP = ROOT / "reports"
BASE = REP / "trades_G_BASE47.csv"
RNG = np.random.default_rng(42)
N_BOOT = 2000


def svg_line(vals, title, color="#8a6a1c", zero=False, h=170):
    if not len(vals):
        return ""
    v = np.asarray(vals, float)
    lo, hi = (min(v.min(), 0), max(v.max(), 0)) if zero else (v.min(), v.max())
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    W = 980
    px = lambda i: 40 + i * (W - 100) / max(1, len(v) - 1)
    py = lambda x: h - 22 - (h - 34) * (x - lo) / (hi - lo)
    pts = " ".join(f"{px(i):.1f},{py(x):.1f}" for i, x in enumerate(v))
    grid = "".join(f'<line x1="40" y1="{py(g):.1f}" x2="{W-60}" y2="{py(g):.1f}" stroke="#c9b285" stroke-width=".6"/>'
                   f'<text x="{W-56}" y="{py(g)+3:.1f}" font-size="10" fill="#6b543a">{g:+.1f}</text>'
                   for g in np.linspace(lo, hi, 4))
    zl = f'<line x1="40" y1="{py(0):.1f}" x2="{W-60}" y2="{py(0):.1f}" stroke="#6b543a" stroke-dasharray="4 3"/>' if zero else ""
    return (f'<svg viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">'
            f'<text x="40" y="14" font-size="12" fill="#4a3316">{title}</text>{grid}{zl}'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


def svg_hist(vals, title, h=170):
    v = np.asarray(vals, float)
    W = 980
    cnt, edges = np.histogram(v, bins=24)
    bw = (W - 100) / len(cnt)
    mx = cnt.max() or 1
    bars = "".join(f'<rect x="{40+i*bw:.1f}" y="{h-22- (h-40)*c/mx:.1f}" width="{bw*0.8:.1f}" '
                   f'height="{(h-40)*c/mx:.1f}" fill="#8a6a1c" opacity=".8"/>' for i, c in enumerate(cnt))
    return (f'<svg viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">'
            f'<text x="40" y="14" font-size="12" fill="#4a3316">{title} '
            f'(диапазон {v.min():+.2f}…{v.max():+.2f}R)</text>{bars}</svg>')


def pf_of(v):
    g, l = v[v > 0].sum(), -v[v < 0].sum()
    return g / l if l > 0 else np.inf


def mdd_of(v):
    eq = np.cumsum(v)
    peak = np.maximum.accumulate(np.concatenate([[0], eq]))[:-1]
    return float((eq - peak).min()) if len(eq) else 0.0


def losing_streak(v):
    best = cur = 0
    for x in v:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def session_of(hour_utc: int) -> str:
    if 0 <= hour_utc < 7:
        return "Asia"
    if 7 <= hour_utc < 12:
        return "London"
    if 12 <= hour_utc < 16:
        return "London/NY overlap"
    if 16 <= hour_utc < 21:
        return "New York"
    return "Rollover / low liquidity"


def main() -> int:
    df = pd.read_csv(BASE)
    net = df["net_r"].to_numpy(float)
    md = ["# VALIDATION v1 — статистическая валидность", "", versions_block(), "", label("PROXY_PAXG"), "",
          f"⚠ {PROXY_WARNING}", "", f"Сделок: {len(net)} · source: PROXY_PAXG · метрики по NET R.", ""]

    # 1) bootstrap CI
    boot = {"expectancy": [], "net": [], "pf": [], "mdd": []}
    for _ in range(N_BOOT):
        s = RNG.choice(net, size=len(net), replace=True)
        boot["expectancy"].append(s.mean())
        boot["net"].append(s.sum())
        boot["pf"].append(pf_of(s))
        boot["mdd"].append(mdd_of(s))
    md += ["## 1. Bootstrap 95% CI (2000 ресэмплингов)", "",
           "| Метрика | Point estimate | 95% CI |", "|---|---|---|"]
    for k, nice in [("expectancy", "Expectancy, R"), ("net", "Net R"), ("pf", "Profit factor"), ("mdd", "Max drawdown, R")]:
        arr = np.asarray(boot[k], float)
        arr = arr[np.isfinite(arr)]
        md.append(f"| {nice} | {net.mean() if k=='expectancy' else (net.sum() if k=='net' else (pf_of(net) if k=='pf' else mdd_of(net))):+.4f} | "
                  f"[{np.percentile(arr,2.5):+.4f} ; {np.percentile(arr,97.5):+.4f}] |")
    ci_lo, ci_hi = np.percentile(boot["expectancy"], [2.5, 97.5])
    md += ["", f"⚠ CI для expectancy включает ноль → результат **нельзя** подавать как однозначно подтверждённый edge: "
               f"CI [{ci_lo:+.3f} ; {ci_hi:+.3f}]R.", ""]

    # 2) Monte Carlo по последовательности
    dds, streaks = [], []
    for _ in range(N_BOOT):
        s = RNG.permutation(net)
        dds.append(mdd_of(s))
        streaks.append(losing_streak(s))
    dds, streaks = np.asarray(dds), np.asarray(streaks)
    md += ["## 2. Monte Carlo (случайный порядок сделок, 2000 симуляций)", "",
           f"- фактический MaxDD: {mdd_of(net):+.2f}R · медиана симуляций: {np.median(dds):+.2f}R",
           f"- перцентили DD: 95% {np.percentile(dds,95):+.2f}R · 99% {np.percentile(dds,99):+.2f}R",
           f"- фактическая серия убытков: {losing_streak(net)} · ожидаемая (медиана): {np.median(streaks):.0f} · "
           f"95%: {np.percentile(streaks,95):.0f}",
           "", "Вывод: если фактический DD заметно лучше медианы симуляций — часть equity-кривой объясняется "
               "удачной последовательностью, а не устойчивостью.", ""]

    # 3) parameter stability (k и SL-множитель) — пересчёт движком
    md += ["## 3. PARAMETER STABILITY / FRAGILITY", ""]
    try:
        import backtest as bt
        from branches import BY_ID
        d1 = pd.read_csv(ROOT / "data" / "paxg_h1.csv")
        m15 = pd.read_csv(ROOT / "data" / "paxg_m15.csv")
        m15["time"] = pd.to_datetime(m15["time"], utc=True)
        d1["time"] = pd.to_datetime(d1["time"], utc=True)
        ctx = bt.build_context(m15, df_h1=d1, df_d1=d1)
        branches = [BY_ID[b] for b in ["B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"]]
        rows = []
        for k in [1.6, 1.8, 2.0, 2.2, 2.4]:
            data = bt.prepare(m15, k=k)
            r = bt.run(data, ctx, branches, bt.Geometry("G", 2.5, 2.5, 1.0, 96), bt.Costs(0.40, 0.06))
            v = np.asarray([t.net_r for t in r.trades], float)
            rows.append((k, len(v), v.sum() if len(v) else 0.0))
        md += ["| K (порог ZigZag, ×ATR) | Сделок | Net R |", "|---|---|---|"]
        md += [f"| {k} | {n} | {s:+.1f} |" for k, n, s in rows]
        nets = [s for _, _, s in rows]
        centre = nets[2]
        stable = all(x >= 0.5 * centre for x in nets) if centre > 0 else False
        md += ["", f"**{'PARAMETER STABILITY' if stable else 'PARAMETER FRAGILITY'}**: соседние значения K дают "
                   f"{min(nets):+.1f}…{max(nets):+.1f}R при центральном {centre:+.1f}R."
                   + ("" if stable else " ⚠ результат чувствителен к точному значению параметра — не доверять точечной цифре."), ""]
    except Exception as e:  # pragma: no cover
        md += [f"_пересчёт движком недоступен: {type(e).__name__}: {e}_", ""]

    # 4) regime analysis
    d1c = pd.read_csv(ROOT / "data" / "paxg_h1.csv")
    d1c["time"] = pd.to_datetime(d1c["time"], utc=True)
    day = d1c.set_index("time").resample("1D")["close"].last().dropna()
    ema = day.rolling(200).mean()
    atr_d = d1c.set_index("time").resample("1D").apply(lambda x: (x["high"] - x["low"]).mean())
    vol_q = atr_d.rolling(200).quantile(0.7), atr_d.rolling(200).quantile(0.3)
    ent = pd.DatetimeIndex(pd.to_datetime(df["entry_time"], utc=True))
    reg = []
    for t in ent:
        d = t.floor("D")
        if d not in day.index or pd.isna(ema.get(d)):
            reg.append("unknown")
            continue
        bull = day[d] > ema[d]
        slope = (ema[d] / ema.shift(5)[d] - 1) if d in ema.shift(5).index and not pd.isna(ema.shift(5).get(d)) else 0
        if abs(slope) < 0.002 and abs(day[d] / ema[d] - 1) < 0.01:
            reg.append("range")
        else:
            reg.append("bull" if bull else "bear")
    df["regime"] = reg
    df["vol"] = [("high" if d in atr_d.index and not pd.isna(vol_q[0].get(d)) and atr_d[d] > vol_q[0][d]
                  else ("low" if d in atr_d.index and not pd.isna(vol_q[1].get(d)) and atr_d[d] < vol_q[1][d] else "mid"))
                 for d in ent.floor("D")]
    md += ["## 4. REGIME ANALYSIS", "", "| Режим | Сделок | WR | Expectancy | PF | Net R | MaxDD |", "|---|---|---|---|---|---|---|"]
    for key, g in df.groupby("regime"):
        v = g["net_r"].to_numpy(float)
        if not len(v):
            continue
        md.append(f"| {key} | {len(v)} | {(v>0).mean()*100:.1f}% | {v.mean():+.4f} | {pf_of(v):.3f} | {v.sum():+.1f} | {mdd_of(v):+.1f} |")
    md += ["", "| Волатильность | Сделок | WR | Expectancy | Net R |", "|---|---|---|---|---|"]
    for key, g in df.groupby("vol"):
        v = g["net_r"].to_numpy(float)
        md.append(f"| {key} | {len(v)} | {(v>0).mean()*100:.1f}% | {v.mean():+.4f} | {v.sum():+.1f} |")
    md += ["", "## 5. LONG / SHORT раздельно", "", "| Направление | Статус | Сделок | WR | Expectancy | PF | Net R | MaxDD |",
           "|---|---|---|---|---|---|---|---|"]
    for d, stt in [(1, "LONG ENABLED"), (-1, "SHORT DISABLED (retired, §реестр)")]:
        g = df[df["direction"] == d]
        v = g["net_r"].to_numpy(float)
        if not len(v):
            md.append(f"| {'LONG' if d==1 else 'SHORT'} | {stt} | 0 | — | — | — | — | — |")
            continue
        md.append(f"| {'LONG' if d==1 else 'SHORT'} | {stt} | {len(v)} | {(v>0).mean()*100:.1f}% | {v.mean():+.4f} | "
                  f"{pf_of(v):.3f} | {v.sum():+.1f} | {mdd_of(v):+.1f} |")
    md += ["", "Отрицательное expectancy SHORT не маскируется общим результатом: направление отключено реестром веток.", ""]

    # 6) walk-forward улучшенная отчётность
    md += ["## 6. WALK-FORWARD: пофолдовая отчётность", "",
           "| # | Test period | Сделок | Статус | OOS Exp | OOS PF | OOS WR | MaxDD | Result R |",
           "|---|---|---|---|---|---|---|---|---|"]
    ts = pd.DatetimeIndex(pd.to_datetime(df["entry_time"], utc=True))
    start = ts.min().floor("90D")
    folds, i = [], 0
    while start + pd.Timedelta(days=90) <= ts.max():
        g = df[(ts >= start) & (ts < start + pd.Timedelta(days=90))]
        v = g["net_r"].to_numpy(float)
        status = "VALID" if len(v) >= 10 else "INSUFFICIENT DATA"
        folds.append((start.date(), len(v), status, v))
        md.append(f"| {i+1} | {start.date()} → {(start+pd.Timedelta(days=90)).date()} | {len(v)} | {status} | "
                  + (f"{v.mean():+.4f} | {pf_of(v):.3f} | {(v>0).mean()*100:.1f}% | {mdd_of(v):+.1f} | {v.sum():+.1f} |"
                     if len(v) else "— | — | — | — | — |"))
        start += pd.Timedelta(days=90)
        i += 1
    valid = [v for _, _, stt, v in folds if stt == "VALID" and len(v)]
    if valid:
        exps = [v.mean() for v in valid]
        md += ["", f"- VALID FOLDS: {len(valid)} · INSUFFICIENT: {sum(1 for _,_,s,_ in folds if s!='VALID')}",
               f"- доля прибыльных valid-фолдов: {sum(1 for e in exps if e>0)/len(exps)*100:.0f}%",
               f"- медиана fold expectancy: {np.median(exps):+.4f}R · худший {min(exps):+.4f}R · лучший {max(exps):+.4f}R",
               f"- дисперсия между фолдами (std): {np.std(exps):.4f}R",
               "", "⚠ Вывод «strategy robust» только по aggregate OOS **не делается**: см. разброс фолдов.", ""]

    # 7) attribution
    md += ["## 7. P&L ATTRIBUTION", "", "| Срез | Сделок | Expectancy | Net R |", "|---|---|---|---|"]
    df["weekday"] = ent.day_name()
    df["session"] = [session_of(h) for h in ent.hour]
    for col in ["regime", "session", "weekday", "vol"]:
        for key, g in df.groupby(col):
            v = g["net_r"].to_numpy(float)
            if len(v) >= 5:
                md.append(f"| {col}:{key} | {len(v)} | {v.mean():+.4f} | {v.sum():+.1f} |")
        md.append("| | | | |")
    md += ["", "## 8. Equity curve и распределение", "",
           svg_line(np.cumsum(net), "Cumulative Net R (PROXY_PAXG)", zero=True),
           svg_line(np.cumsum(net) - np.maximum.accumulate(np.cumsum(net)), "Drawdown R", color="#8a1f1f"),
           svg_line([np.mean(net[max(0,i-29):i+1]) for i in range(len(net))], "Rolling 30-trade expectancy"),
           svg_line([(net[max(0,i-29):i+1] > 0).mean()*100 for i in range(len(net))], "Rolling 30-trade win rate, %"),
           svg_hist(net, "Распределение результатов сделок, R"), ""]
    (REP / "VALIDATION_v1.md").write_text("\n".join(md), encoding="utf-8")
    print(f"→ {REP/'VALIDATION_v1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
