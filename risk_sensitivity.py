#!/usr/bin/env python3
"""ЧУВСТВИТЕЛЬНОСТЬ РИСКА (R4/R5 совета): slippage на стопах и гэпы золота.

Выход: reports/RISK_SENSITIVITY_v1.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
from freeze_hash import freeze_hash  # noqa: E402

REP = ROOT / "reports"
BASE = REP / "trades_G_BASE47.csv"
D1 = ROOT / "data" / "gcf_d1.csv"
SLIP = [0.0, 0.1, 0.2, 0.3]
MULT = [0.5, 1.0, 1.5, 2.0, 3.0]


def main() -> int:
    df = pd.read_csv(BASE)
    md = ["# ЧУВСТВИТЕЛЬНОСТЬ РИСКА v1 — slippage и гэпы", "",
          f"freeze SHA-256: `{freeze_hash()}` · база: кандидат v2, N={len(df)}, PROXY-данные.", ""]

    # 1) slippage на стопах
    md += ["## 1. Slippage на стоп-выходах", "",
           "Допущение: slippage добавляется только к выходам по SL/SL_FIRST (гэпы и очереди в стоп).",
           "", "| Slippage, USD | Expectancy, R | Net R | PF | WR |", "|---|---|---|---|---|"]
    for s in SLIP:
        net = df["net_r"].copy()
        mask = df["reason"].isin(["SL", "SL_FIRST"])
        net[mask] -= s / df.loc[mask, "r_usd"]
        n = net.to_numpy(float)
        gw, gl = n[n > 0].sum(), -n[n < 0].sum()
        md.append(f"| {s:.1f} | {n.mean():+.4f} | {n.sum():+.1f} | {gw/gl if gl else float('inf'):.3f} | "
                  f"{(n > 0).mean()*100:.1f}% |")
    md += ["## 1b. Мультипликаторы полных издержек (spread+commission+slippage)", "",
           "| Множитель | Expectancy, R | Net R | PF |", "|---|---|---|---|"]
    base_cost = 0.52
    break_even = None
    for m in MULT:
        net_m = df["net_r"].to_numpy(float).copy()
        delta = (m - 1.0) * base_cost
        net_m -= delta / df["r_usd"].to_numpy(float)
        gw, gl = net_m[net_m > 0].sum(), -net_m[net_m < 0].sum()
        md.append(f"| {m:.1f}× | {net_m.mean():+.4f} | {net_m.sum():+.1f} | {gw/gl if gl else float('inf'):.3f} |")
        if break_even is None and net_m.mean() <= 0:
            break_even = m
    md += ["", f"Expectancy становится ≤ 0 при множителе издержек **{break_even if break_even else '> 3.0'}×** "
               f"(т.е. при round-trip ≥ {base_cost*(break_even or 3.0):.2f} USD).", ""]
    base_net = df["net_r"].to_numpy(float).copy()
    mask = df["reason"].isin(["SL", "SL_FIRST"])
    slipped = base_net.copy()
    slipped[mask] -= 0.3 / df.loc[mask, "r_usd"].to_numpy(float)
    md += ["", f"Вывод: slippage 0.3 USD на стопах снижает expectancy с {base_net.mean():+.4f}R до {slipped.mean():+.4f}R "
               f"(Net {base_net.sum():+.1f}R → {slipped.sum():+.1f}R); база устойчива, но запас по edge небольшой — "
               "см. always-valid p в журнале сделок.", ""]

    # 2) гэпы D1
    d1 = pd.read_csv(D1)
    d1 = d1.sort_values("time" if "time" in d1.columns else d1.columns[0])
    o = d1["open"].to_numpy(float)
    c = d1["close"].to_numpy(float)
    gap = o[1:] - c[:-1]
    atr = pd.Series(c).diff().abs().rolling(14).mean().to_numpy()[1:]
    rel = np.abs(gap) / np.where(atr > 0, atr, np.nan)
    md += ["## 2. Гэпы открытия D1 (GC=F, реальное золото)", "",
           f"- дней: {len(gap)} · средний |гэп| {np.nanmean(np.abs(gap)):.2f} USD · "
           f"медиана {np.nanmedian(np.abs(gap)):.2f} USD · максимум {np.nanmax(np.abs(gap)):.2f} USD",
           f"- в единицах ATR(14): медиана {np.nanmedian(rel):.3f} · "
           f"доля дней с |гэпом| > 0.5 ATR: {np.nanmean(rel > 0.5)*100:.1f}% · > 1 ATR: {np.nanmean(rel > 1)*100:.1f}%",
           f"- худший гэп: {gap[np.nanargmax(np.abs(gap))]:+.2f} USD", "",
           "Вывод: дневные гэпы золота в медиане малы относительно ATR, но хвосты существуют: "
           "стоп-выход после выходных может исполниться хуже уровня на величину до нескольких ATR. "
           "Рекомендация R5 учтена в стресс-сценарии журнала (10 стопов подряд).", ""]
    (REP / "RISK_SENSITIVITY_v1.md").write_text("\n".join(md), encoding="utf-8")
    print(f"→ {REP/'RISK_SENSITIVITY_v1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
