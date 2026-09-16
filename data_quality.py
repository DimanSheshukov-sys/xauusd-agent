#!/usr/bin/env python3
"""DATA QUALITY (P0 ТЗ): аудит каждого источника + сравнение PAXG / GC=F / REAL.

Выход: reports/DATA_QUALITY_v1.md (публикуется как DATA_QUALITY.html)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
from sources import PROXY_WARNING, versions_block, label  # noqa: E402

REP = ROOT / "reports"
DATA = ROOT / "data"

SETS = [
    ("PROXY_PAXG", "M15", DATA / "paxg_m15.csv", 15),
    ("PROXY_PAXG", "H1", DATA / "paxg_h1.csv", 60),
    ("FUTURES_GC", "M15", DATA / "gcf_m15.csv", 15),
    ("FUTURES_GC", "H1", DATA / "gcf_h1.csv", 60),
    ("FUTURES_GC", "D1", DATA / "gcf_d1.csv", 1440),
]
SPREAD_ASSUMPTION = {
    "PROXY_PAXG": "биржевой стакан Binance, спред ≈ 0.01–0.05 USD; в моделях консервативно 0.40–0.60 USD",
    "FUTURES_GC": "спред фьючерса не моделируется (данные OHLC); издержки те же 0.52 USD round-trip",
    "REAL_XAUUSD": "недоступен; при подключении — живой спред брокера",
}


def audit_df(df: pd.DataFrame, minutes: int) -> dict:
    t = pd.to_datetime(df["time"], utc=True)
    step = pd.Timedelta(minutes=minutes)
    dt = t.diff()
    gaps = dt[dt > step]
    dup = int(t.duplicated().sum())
    o, h, l, c = (df[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    tr = np.maximum(h - l, np.abs(np.diff(c, prepend=c[0])))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = tr / np.where(atr > 0, atr, np.nan)
    bad_ohlc = int(((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).sum())
    weekend = int(t.dt.dayofweek.isin([5, 6]).sum())
    return {
        "bars": len(df), "from": str(t.iloc[0])[:16], "to": str(t.iloc[-1])[:16],
        "dups": dup, "gaps": int(len(gaps)),
        "max_gap_h": float(dt.max().total_seconds() / 3600),
        "bad_ohlc": bad_ohlc,
        "weekend_bars": weekend,
        "max_move_atr": float(np.nanmax(rel)),
        "jumps_gt_8atr": int(np.nansum(rel > 8)),
        "tz": "UTC",
    }


def main() -> int:
    md = ["# DATA QUALITY v1 — аудит источников", "",
          versions_block(), "",
          label("PROXY_PAXG"), "", label("FUTURES_GC"), "",
          f"⚠ {PROXY_WARNING}", "",
          "**REAL XAUUSD validation unavailable** — спот-источник в среде отсутствует; "
          "все performance-метрики проекта помечены как PROXY до его подключения.", "",
          "## 1. Аудит наборов", "",
          "| Источник | ТФ | Баров | Период (UTC) | Дубли | Гэпы | Макс гэп, ч | Некорректный OHLC | Weekend-бары | Макс ход, ATR | Скачков >8 ATR |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    frames = {}
    for kind, tf, path, minutes in SETS:
        if not path.exists():
            md.append(f"| {kind} | {tf} | файл отсутствует | — | — | — | — | — | — | — | — |")
            continue
        df = pd.read_csv(path)
        a = audit_df(df, minutes)
        frames[(kind, tf)] = df
        md.append(f"| {kind} | {tf} | {a['bars']:,} | {a['from']} → {a['to']} | {a['dups']} | {a['gaps']} | "
                  f"{a['max_gap_h']:.1f} | {a['bad_ohlc']} | {a['weekend_bars']} | {a['max_move_atr']:.1f} | {a['jumps_gt_8atr']} |")
    md += ["", "## 2. Допущения по спредам и издержкам", ""]
    for k, v in SPREAD_ASSUMPTION.items():
        md.append(f"- **{k}:** {v}")
    md += ["", "## 3. Сравнение PAXG ↔ GC=F (overlap по дневным закрытиям)", ""]
    px = frames.get(("PROXY_PAXG", "H1"))
    gc = frames.get(("FUTURES_GC", "H1"))
    if px is not None and gc is not None:
        a = pd.DataFrame({"t": pd.to_datetime(px["time"], utc=True).dt.floor("D"),
                          "paxg": px["close"]}).groupby("t").last()
        b = pd.DataFrame({"t": pd.to_datetime(gc["time"], utc=True).dt.floor("D"),
                          "gc": gc["close"]}).groupby("t").last()
        j = a.join(b, how="inner").dropna()
        basis = (j["paxg"] - j["gc"])
        rets_p = j["paxg"].pct_change().dropna()
        rets_g = j["gc"].pct_change().dropna()
        common = rets_p.index.intersection(rets_g.index)
        corr = float(np.corrcoef(rets_p[common], rets_g[common])[0, 1])
        md += [f"- дней в overlap: {len(j)}",
               f"- корреляция дневных доходностей: **{corr:.4f}**",
               f"- базис PAXG−GC: медиана {basis.median():+.2f} USD, средний |базис| {basis.abs().mean():.2f} USD, "
               f"макс |базис| {basis.abs().max():.2f} USD",
               f"- шум базиса (|базис − медиана|): средний {(basis - basis.median()).abs().mean():.2f} USD",
               "",
               "Вывод: PAXG и GC=F движутся почти синхронно по доходностям, но базис шумный → "
               "PAXG пригоден как proxy для структуры и исследования, **не** как подтверждение XAUUSD.", ""]
    md += ["## 4. Статус источников", "",
           "| Источник | Доступен | Роль | Validation status |", "|---|---|---|---|",
           "| REAL_XAUUSD | ❌ нет | основной при подключении | VERIFIED (после подключения) |",
           "| PROXY_PAXG | ✅ | research / proxy only | PROXY |",
           "| FUTURES_GC | ✅ | supplementary validation | NOT VERIFIED |", "",
           "Правило: статистика разных источников **не смешивается** в одном агрегированном показателе; "
           "каждая таблица эффективности помечена своим источником.", ""]
    (REP / "DATA_QUALITY_v1.md").write_text("\n".join(md), encoding="utf-8")
    print(f"→ {REP/'DATA_QUALITY_v1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
