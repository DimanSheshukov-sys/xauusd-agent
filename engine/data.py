"""G00 DATA LAYER — загрузка, кэш и аудит данных XAUUSD.

Источники (по убыванию предпочтительности для спот XAUUSD):
  1. Dukascopy bi5            — НЕДОСТУПЕН из этой среды (HTTP 503)
  2. Yahoo GC=F               — реальный фьючерс COMEX: 15m=60d, 1h=730d, 1d=с 2000
  3. Binance PAXGUSDT         — токенизированное золото: 1m/15m/1h/1d с 2020-09 (ПРОКСИ)
  4. TradingView scanner/WS   — только текущий срез и live-цена

PAXG торгуется 24/7, спот XAUUSD — ~5 дней в неделю, поэтому для эмуляции спота
weekend-бары отбрасываются (drop_weekends=True).
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
COLS = ["time", "open", "high", "low", "close", "volume"]


def _get(url: str, timeout: int = 30) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.0 + attempt)


def _ms(d) -> int:
    if isinstance(d, (int, float)):
        return int(d)
    return int(pd.Timestamp(d, tz="UTC").timestamp() * 1000)


# ───────────────────────── источники ─────────────────────────
def fetch_binance(pair: str, interval: str, start, end=None) -> pd.DataFrame:
    """Пагинированная выгрузка klines (батчи по 1000)."""
    end_ms = _ms(end) if end else int(time.time() * 1000)
    cur = _ms(start)
    rows: list[list] = []
    while cur < end_ms:
        url = (f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}"
               f"&startTime={cur}&endTime={end_ms}&limit=1000")
        batch = json.loads(_get(url))
        if not batch:
            break
        rows += batch
        if len(batch) < 1000:
            break
        cur = batch[-1][0] + 1
        time.sleep(0.03)
    if not rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame([r[:6] for r in rows], columns=COLS)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    for c in COLS[1:]:
        df[c] = df[c].astype(float)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def fetch_yahoo(ticker: str, interval: str, start=None, end=None, days: int | None = None) -> pd.DataFrame:
    """Yahoo chart API с дроблением на окна (лимит баров на запрос)."""
    iv = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "60m": "1h", "1h": "1h",
          "1d": "1d", "1D": "1d", "1wk": "1wk", "1mo": "1mo"}[interval]
    step_days = {"1m": 6, "5m": 55, "15m": 55, "30m": 55, "1h": 700, "1d": 20 * 365,
                 "1wk": 60 * 365, "1mo": 60 * 365}[iv]
    e = _ms(end) // 1000 if end else int(time.time())
    s = _ms(start) // 1000 if start else e - (days or step_days) * 86400
    frames = []
    p1 = s
    while p1 < e:
        p2 = min(p1 + step_days * 86400, e)
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
               f"?interval={iv}&period1={p1}&period2={p2}")
        try:
            res = json.loads(_get(url))["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            f = pd.DataFrame({"time": pd.to_datetime(ts, unit="s", utc=True),
                              "open": q["open"], "high": q["high"], "low": q["low"],
                              "close": q["close"], "volume": q.get("volume", [np.nan] * len(ts))})
            frames.append(f)
        except Exception:
            pass
        p1 = p2
        time.sleep(0.03)
    if not frames:
        return pd.DataFrame(columns=COLS)
    df = pd.concat(frames).dropna(subset=["close"]).drop_duplicates("time").sort_values("time")
    return df.reset_index(drop=True)[COLS]


import urllib.parse  # noqa: E402  (нужен в fetch_yahoo)


# ───────────────────────── датасеты проекта ─────────────────────────
@dataclass
class DatasetSpec:
    key: str
    source: str
    symbol: str
    interval: str
    start: str | None = None
    end: str | None = None
    days: int | None = None
    drop_weekends: bool = False
    note: str = ""


DATASETS = {
    # основной тестовый стенд: глубокая M15-история (прокси золота)
    "paxg_m15": DatasetSpec("paxg_m15", "binance", "PAXGUSDT", "15m", "2022-01-24", "2026-09-16",
                            drop_weekends=True,
                            note="PROXY: токенизированное золото; weekends отброшены для эмуляции спот-сессий"),
    "paxg_m15_raw": DatasetSpec("paxg_m15_raw", "binance", "PAXGUSDT", "15m", "2022-01-24", "2026-09-16",
                                note="то же, но 24/7 без фильтра выходных"),
    "paxg_h1": DatasetSpec("paxg_h1", "binance", "PAXGUSDT", "1h", "2021-01-01", "2026-09-16",
                           drop_weekends=True, note="H1 для MTF-контекста (EMA200 D1/H4 считается из M15)"),
    # кросс-проверка на настоящем золоте (фьючерс COMEX)
    "gcf_h1": DatasetSpec("gcf_h1", "yahoo", "GC=F", "1h", days=720, note="реальное золото, H1, 730 дней"),
    "gcf_m15": DatasetSpec("gcf_m15", "yahoo", "GC=F", "15m", days=58, note="реальное золото, M15, 60 дней"),
    "gcf_d1": DatasetSpec("gcf_d1", "yahoo", "GC=F", "1d", start="2000-01-01", note="дневки COMEX с 2000"),
}


def load(key: str, force: bool = False) -> pd.DataFrame:
    """Загрузка датасета с кэшем в xauusd_agent/data/<key>.csv."""
    spec = DATASETS[key]
    cache = DATA_DIR / f"{key}.csv"
    if cache.exists() and not force:
        df = pd.read_csv(cache, parse_dates=["time"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df
    if spec.source == "binance":
        df = fetch_binance(spec.symbol, spec.interval, spec.start, spec.end)
    elif spec.source == "yahoo":
        df = fetch_yahoo(spec.symbol, spec.interval, spec.start, spec.end, spec.days)
    else:
        raise ValueError(spec.source)
    if spec.drop_weekends and not df.empty:
        df = df[df["time"].dt.dayofweek < 5].reset_index(drop=True)
    df.to_csv(cache, index=False)
    return df


# ───────────────────────── G00: аудит целостности ─────────────────────────
def audit(df: pd.DataFrame, expected_minutes: int = 15, drop_weekends: bool = True,
          max_gap_factor: int = 12) -> dict:
    """G00 DATA INTEGRITY: OHLC-корректность, монотонность, дубли, гэпы, покрытие сессий."""
    rep: dict = {"bars": len(df)}
    if df.empty:
        return {**rep, "verdict": "WAIT_DATA", "errors": ["empty dataset"]}
    errors, warnings = [], []

    t = df["time"]
    if not t.is_monotonic_increasing:
        errors.append("timestamps не монотонны")
    dups = int(t.duplicated().sum())
    if dups:
        errors.append(f"дублей timestamps: {dups}")

    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    bad_hl = int(((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).sum())
    if bad_hl:
        errors.append(f"нарушена OHLC-логика (high/low) на {bad_hl} барах")
    bad_px = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
    if bad_px:
        errors.append(f"неположительные цены на {bad_px} барах")
    nan_ct = int(df[["open", "high", "low", "close"]].isna().sum().sum())
    if nan_ct:
        warnings.append(f"NaN в OHLC: {nan_ct}")
    zero_range = int((h == l).sum())
    if zero_range:
        warnings.append(f"баров с zero-range (h==l): {zero_range}")

    step = pd.Timedelta(minutes=expected_minutes)
    dt = t.diff().dropna()
    gaps = dt[dt > step]
    big = gaps[gaps > step * max_gap_factor]
    rep["gaps_total"] = int(len(gaps))
    rep["gaps_big"] = int(len(big))
    rep["max_gap_hours"] = float(dt.max().total_seconds() / 3600)
    if len(big):
        warnings.append(f"крупных гэпов (> {max_gap_factor} интервалов): {len(big)}")
        rep["biggest_gaps"] = [{"at": str(t[i]), "hours": round(float(dt[i].total_seconds() / 3600), 1)}
                               for i in big.sort_values(ascending=False).index[:5]]

    rep["from"], rep["to"] = str(t.iloc[0]), str(t.iloc[-1])
    span_days = (t.iloc[-1] - t.iloc[0]).total_seconds() / 86400
    rep["span_days"] = round(span_days, 1)
    exp = span_days * (5 / 7 if drop_weekends else 1) * 24 * 60 / expected_minutes
    rep["expected_bars"] = int(exp)
    rep["coverage_pct"] = round(len(df) / exp * 100, 1) if exp else 0
    if rep["coverage_pct"] < 70:
        warnings.append(f"покрытие {rep['coverage_pct']}% от ожидаемого")

    wk = df["time"].dt.day_name().value_counts().to_dict()
    rep["bars_by_weekday"] = {k: int(v) for k, v in wk.items()}
    if drop_weekends and (wk.get("Saturday", 0) or wk.get("Sunday", 0)):
        errors.append("weekend-бары присутствуют, хотя заявлен спот-режим")

    rep["errors"], rep["warnings"] = errors, warnings
    rep["verdict"] = "OK" if not errors else "WAIT_DATA"
    return rep


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """M15 → H1/H4/D1 причинно: бар принадлежит интервалу, в котором он ЗАКРЫЛСЯ."""
    d = df.set_index("time")
    out = d.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    return out.reset_index()


if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or ["paxg_m15", "gcf_h1", "gcf_m15", "gcf_d1", "paxg_h1"]
    for k in keys:
        t0 = time.time()
        df = load(k, force="--force" in sys.argv)
        rep = audit(df, expected_minutes=15 if "m15" in k else 60 if "h1" in k else 1440,
                    drop_weekends=DATASETS[k].drop_weekends)
        print(f"\n=== {k} ({time.time()-t0:.0f}s) — {DATASETS[k].note}")
        print(json.dumps({kk: vv for kk, vv in rep.items() if kk != "bars_by_weekday"},
                         ensure_ascii=False, indent=1, default=str))
