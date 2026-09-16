"""Causal ZigZag swing detection.

Ключевое свойство: каждый пивот хранит `confirm_idx` — индекс бара, на котором он
СТАЛ известен. Волновая разметка имеет право использовать только пивоты с
confirm_idx <= текущего бара. Это делает look-ahead структурно невозможным
(проверяется в tests/test_causality.py).

Замороженные параметры — см. PARAMETER_FREEZE_v1.md (секция A):
  SWING_K        = 2.0   порог разворота = K * ATR(14) того же ТФ  (PRIMARY, a priori)
  SWING_ATR_N    = 14
  SWING_MIN_BARS = 1     отключён: ATR-порог — единственный шумовой фильтр
  ATR берётся на баре-экстремуме (а не на баре подтверждения)
  Sensitivity-набор (публикуется полностью, лучший НЕ выбирается): k = 1.5 / 2.0 / 3.0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indicators import atr as atr_fn

SWING_K = 2.0   # PRIMARY (pre-registered)
SWING_ATR_N = 14
SWING_MIN_BARS = 1   # v1: ATR-порог сам фильтрует шум; min_bars=3 блокировал подтверждение навсегда


@dataclass(slots=True)
class Pivot:
    idx: int          # бар-экстремум
    price: float
    kind: str         # 'H' | 'L'
    confirm_idx: int  # бар, на котором пивот стал известен (causal watermark)

    def __repr__(self) -> str:
        return f"{self.kind}@{self.idx}={self.price:.2f}(c{self.confirm_idx})"


def zigzag(high: np.ndarray, low: np.ndarray, atr_arr: np.ndarray | None = None,
           k: float = SWING_K, min_bars: int = SWING_MIN_BARS) -> list[Pivot]:
    """Возвращает только ПОДТВЕРЖДЁННЫЕ пивоты (формирующийся экстремум не возвращается)."""
    n = len(high)
    if atr_arr is None:
        atr_arr = atr_fn(high, low, np.full(n, np.nan), SWING_ATR_N)  # TR без close — только H-L
        close_dummy = (high + low) / 2
        atr_arr = atr_fn(high, low, close_dummy, SWING_ATR_N)
    piv: list[Pivot] = []
    trend = 0                       # 0 = не определён, 1 = вверх, -1 = вниз
    hi_i, lo_i = 0, 0
    hi_v, lo_v = float(high[0]), float(low[0])

    def _thr(i: int) -> float:
        a = atr_arr[i]
        if a is None or np.isnan(a) or a <= 0:
            return np.inf
        return k * float(a)

    for i in range(1, n):
        if trend >= 0 and high[i] > hi_v:
            hi_v, hi_i = float(high[i]), i
        if trend <= 0 and low[i] < lo_v:
            lo_v, lo_i = float(low[i]), i

        last_idx = piv[-1].idx if piv else -10 ** 9

        # подтверждение HIGH-пивота (разворот вниз)
        if trend >= 0 and hi_i > last_idx and hi_i < i:
            if (hi_i - last_idx) >= min_bars and low[i] <= hi_v - _thr(hi_i):
                piv.append(Pivot(hi_i, hi_v, "H", i))
                seg = low[hi_i + 1:i + 1]          # СТРОГО после пивота, иначе lo_i == last_idx и подтверждение блокируется навсегда
                lo_i = int(hi_i + 1 + int(np.argmin(seg)))
                lo_v = float(low[lo_i])
                trend = -1
                continue

        # подтверждение LOW-пивота (разворот вверх)
        if trend <= 0 and lo_i > last_idx and lo_i < i:
            if (lo_i - last_idx) >= min_bars and high[i] >= lo_v + _thr(lo_i):
                piv.append(Pivot(lo_i, lo_v, "L", i))
                seg = high[lo_i + 1:i + 1]
                hi_i = int(lo_i + 1 + int(np.argmax(seg)))
                hi_v = float(high[hi_i])
                trend = 1
                continue

    return piv


def pivots_as_of(piv: list[Pivot], bar: int) -> list[Pivot]:
    """Пивоты, известные на момент закрытия бара `bar` (причинный срез)."""
    import bisect
    keys = [p.confirm_idx for p in piv]
    j = bisect.bisect_right(keys, bar)
    return piv[:j]


def provisional_extreme(high: np.ndarray, low: np.ndarray, atr_arr: np.ndarray,
                        piv: list[Pivot], bar: int, k: float = SWING_K) -> dict:
    """Незавершённый экстремум текущей ноги — только для live-диагностики, НЕ для входа."""
    known = pivots_as_of(piv, bar)
    start = known[-1].idx if known else 0
    seg_h, seg_l = high[start:bar + 1], low[start:bar + 1]
    return {"hi": float(seg_h.max()), "hi_i": int(start + np.argmax(seg_h)),
            "lo": float(seg_l.min()), "lo_i": int(start + np.argmin(seg_l)),
            "atr": float(atr_arr[bar]) if not np.isnan(atr_arr[bar]) else np.nan}
