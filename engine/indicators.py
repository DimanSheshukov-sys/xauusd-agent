"""Causal indicators. Значение на баре i использует только бары ≤ i (закрытые).

Все функции возвращают np.ndarray той же длины, что и вход; неопределённые значения = NaN.
Решение, принятое на баре i, исполняется на открытии бара i+1 (конвенция §47).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """Экспоненциальная скользящая, seed = SMA(n) на первом валидном окне (как в TV)."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    if len(x) < n:
        return out
    alpha = 2.0 / (n + 1)
    seed = np.nanmean(x[:n])
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(x)):
        prev = alpha * x[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def sma(x: np.ndarray, n: int) -> np.ndarray:
    s = pd.Series(np.asarray(x, dtype=float)).rolling(n, min_periods=n).mean()
    return s.to_numpy()


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    h, l, c = map(lambda a: np.asarray(a, dtype=float), (high, low, close))
    pc = np.concatenate([[np.nan], c[:-1]])
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    """ATR по Уайлдеру (RMA) — так же, как в TradingView."""
    tr = true_range(high, low, close)
    out = np.full(len(tr), np.nan)
    if len(tr) < n + 1:
        return out
    seed = np.nanmean(tr[1:n + 1])
    out[n] = seed
    prev = seed
    for i in range(n + 1, len(tr)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI Уайлдера (RMA-сглаживание), как в TV."""
    c = np.asarray(close, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) < n + 1:
        return out
    d = np.diff(c)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = gain[:n].mean()
    al = loss[:n].mean()
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + gain[i]) / n
        al = (al * (n - 1) + loss[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def donchian(high: np.ndarray, low: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Канал по ПРЕДЫДУЩИМ n барам (без текущего) — причинная версия для trigger."""
    h = pd.Series(np.asarray(high, dtype=float)).rolling(n).max().shift(1).to_numpy()
    l = pd.Series(np.asarray(low, dtype=float)).rolling(n).min().shift(1).to_numpy()
    return h, l


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    c = np.asarray(close, dtype=float)
    line = ema(c, fast) - ema(c, slow)
    valid = ~np.isnan(line)
    sig = np.full_like(line, np.nan)
    if valid.sum() >= signal:
        idx = np.where(valid)[0]
        sub = ema(line[idx[0]:], signal)
        sig[idx[0]:] = sub
    return line, sig, line - sig


def htf_context(m15: pd.DataFrame, rule: str, ema_n: int = 200) -> pd.DataFrame:
    """Ресемпл M15 → H1/H4/D1 и EMA200, выровненные ПРИЧИННО:
    для каждого M15-бара возвращается значение последнего ЗАКРЫТОГО HTF-бара.

    label='left', closed='left' → HTF-бар с меткой T охватывает [T, T+step) и закрывается
    в T+step. Значит для M15-бара с временем t последний закрытый HTF-бар — тот, у которого
    T + step <= t. Реализовано через shift(1) после reindex.
    """
    idx = m15.set_index("time")
    htf = idx.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    htf["ema200"] = ema(htf["close"].to_numpy(), ema_n)
    htf["rsi14"] = rsi(htf["close"].to_numpy(), 14)
    htf["atr14"] = atr(htf["high"].to_numpy(), htf["low"].to_numpy(), htf["close"].to_numpy(), 14)
    # сдвиг: используем только закрытые HTF-бары
    for c in ["open", "high", "low", "close", "ema200", "rsi14", "atr14"]:
        htf[f"{c}_prev"] = htf[c].shift(1)
    # маппинг M15-бара на HTF-бар, который к этому моменту закрылся
    aligned = pd.merge_asof(m15[["time"]], htf.reset_index()[["time", "close_prev", "ema200_prev",
                                                             "rsi14_prev", "atr14_prev", "high_prev", "low_prev"]],
                            on="time", direction="backward")
    aligned = aligned.rename(columns={c: c.replace("_prev", "") for c in
                                      ["close_prev", "ema200_prev", "rsi14_prev", "atr14_prev", "high_prev", "low_prev"]})
    return aligned.set_index("time")
