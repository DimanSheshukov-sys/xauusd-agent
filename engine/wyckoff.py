"""§18/§19 WYCKOFF — CONTEXT ONLY. Формальное причинное определение (закрывает gap D15).

Запрещено использовать как gate (§19): флаг только логируется и анализируется диагностически.

Определение (заморожено, v2):
  Точка измерения — пивот P4 (завершение W4) + 3 следующих бара.
  VOL_RATIO = mean(volume[P4-10 .. P4+3]) / mean(volume[P4-210 .. P4-11])
  STOPPING  = для бычьего P4 (low): (close − low) / (high − low) ≥ 0.50 в баре P4
              для медвежьего P4 (high): (high − close) / (high − low) ≥ 0.50
  WYCKOFF = (VOL_RATIO ≥ 1.30) AND STOPPING
  Смысл: кульминация объёма + остановка движения (absorption) — то, что в Wyckoff
  называется selling/buying climax. Если данных не хватает (мало баров до P4) → False.
"""
from __future__ import annotations

import numpy as np

VOL_LOOKBACK = 200
VOL_WINDOW = 10
POST_BARS = 3
VOL_RATIO_MIN = 1.30


def wyckoff_flag(volume: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 p4_idx: int, direction: int) -> tuple[bool, float]:
    """Возвращает (flag, vol_ratio). direction: +1 бычий W4 (low-пивот), −1 медвежий (high-пивот)."""
    a = p4_idx - VOL_WINDOW
    b = p4_idx + POST_BARS
    base_a = p4_idx - VOL_LOOKBACK - VOL_WINDOW
    if a < 0 or b >= len(volume) or base_a < 0:
        return False, float("nan")
    v_num = float(np.nanmean(volume[a:b + 1]))
    v_den = float(np.nanmean(volume[base_a:a]))
    if not np.isfinite(v_num) or not np.isfinite(v_den) or v_den <= 0:
        return False, float("nan")
    ratio = v_num / v_den
    rng = high[p4_idx] - low[p4_idx]
    if rng <= 0:
        return False, ratio
    stopping = ((close[p4_idx] - low[p4_idx]) / rng >= 0.50) if direction > 0 else \
               ((high[p4_idx] - close[p4_idx]) / rng >= 0.50)
    return bool(ratio >= VOL_RATIO_MIN and stopping), ratio


def wyckoff_series(volume: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   structs: dict, n: int) -> np.ndarray:
    """Массив флагов по барам: для каждого бара — флаг структуры, активной на этом баре."""
    out = np.zeros(n, dtype=bool)
    ratios = np.full(n, np.nan)
    for bar, st in structs.items():
        if st.kind != "IMPULSE_W5" or len(st.piv) < 5:
            continue
        p4 = st.piv[4]
        flag, ratio = wyckoff_flag(volume, high, low, close, p4.idx, st.direction)
        end = min(n - 1, bar + 400)
        out[bar:end + 1] = flag
        ratios[bar:end + 1] = ratio
    return out
