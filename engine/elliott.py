"""ELLIOTT LAYER (G03/G04/G05, S04–S06).

Causal-разметка импульса W1-W2-W3-W4 → forecast W5 + классификация W3 + ABC/Failed Fifth.

ЗАМОРОЖЕННЫЕ ПРАВИЛА ВАЛИДНОСТИ (все проверяются только на уже подтверждённых пивотах):
  R1  W2 не ретрейсит 100% W1          → L2 > L0  (для up)
  R2  W4 не заходит на территорию W1   → L4 > H1  (для up)
  R3  W4 короче W3                     → ret4 < 1
  R4  «W3 не самая короткая» — причинно НЕПРОВЕРЯЕМА до завершения W5,
      поэтому помечается как PENDING, а не как фильтр. Именно поэтому
      CLASS A (W3/W1 < 1) достижим — иначе §8/§9 канона были бы невыполнимы.

W3 CLASS (§8):  A = ratio < 1 | B = 1 ≤ ratio < 1.618 | C = ratio ≥ 1.618
FIB ON (§20/§21, определение закрыто):  0.382 ≤ ret2 ≤ 0.786  AND  0.236 ≤ ret4 ≤ 0.5
STRUCTURAL INVALIDATION (§11/§26):      L4 для LONG, H4 для SHORT
SETUP_MAX_AGE = 200 M15-баров           (после этого setup считается устаревшим → S19)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from swings import Pivot, pivots_as_of

SETUP_MAX_AGE = 200
TRIGGER_DONCHIAN_N = 8
FIB_W2 = (0.382, 0.786)
FIB_W4 = (0.236, 0.500)
W3_EXT = 1.618


@dataclass(slots=True)
class Structure:
    direction: int                 # +1 = бычий импульс (forecast W5 вверх), −1 = медвежий
    kind: str                      # IMPULSE_W5 | ABC | FAILED_FIFTH
    piv: tuple                     # 5 пивотов (P0..P4)
    w1: float; w2: float; w3: float; w4: float
    ret2: float; ret4: float
    ratio31: float
    w3_class: str                  # A | B | C | UNAVAILABLE
    invalidation: float
    rules: dict = field(default_factory=dict)
    fib_ok: bool = False
    as_of: int = -1                # бар, на котором структура стала известна
    w5_target_fib: float = np.nan  # диагностическая структурная цель (не используется как TP)

    @property
    def is_long(self) -> bool:
        return self.direction > 0

    def dead(self, bar: int, close: float) -> bool:
        """Структура мертва: пробой invalidation или истёк срок годности."""
        if bar - self.as_of > SETUP_MAX_AGE:
            return True
        return close < self.invalidation if self.is_long else close > self.invalidation


def _w3_class(ratio: float) -> str:
    if not np.isfinite(ratio):
        return "UNAVAILABLE"
    if ratio < 1.0:
        return "A"
    if ratio < W3_EXT:
        return "B"
    return "C"


def detect_impulse(piv5: list[Pivot]) -> Structure | None:
    """5 подтверждённых пивотов → валидный импульс или None."""
    if len(piv5) != 5:
        return None
    p0, p1, p2, p3, p4 = piv5
    kinds = "".join(p.kind for p in piv5)
    d = None
    if kinds == "LHLHL":
        d = 1
    elif kinds == "HLHLH":
        d = -1
    else:
        return None
    if d > 0:
        w1 = p1.price - p0.price
        w2 = p1.price - p2.price
        w3 = p3.price - p2.price
        w4 = p3.price - p4.price
        rules = {"R1_w2_not_full_retrace": p2.price > p0.price,
                 "R2_w4_no_overlap_w1": p4.price > p1.price,
                 "R3_w4_shorter_than_w3": w4 < w3,
                 "R_pos_w1": w1 > 0, "R_pos_w3": w3 > 0}
        invalidation = p4.price
        fib_ok = (FIB_W2[0] <= (w2 / w1 if w1 else 9) <= FIB_W2[1]) and \
                 (FIB_W4[0] <= (w4 / w3 if w3 else 9) <= FIB_W4[1])
        w5_target = p3.price + w3 * 0.618 if w3 else np.nan
    else:
        w1 = p0.price - p1.price
        w2 = p2.price - p1.price
        w3 = p2.price - p3.price
        w4 = p4.price - p3.price
        rules = {"R1_w2_not_full_retrace": p2.price < p0.price,
                 "R2_w4_no_overlap_w1": p4.price < p1.price,
                 "R3_w4_shorter_than_w3": w4 < w3,
                 "R_pos_w1": w1 > 0, "R_pos_w3": w3 > 0}
        invalidation = p4.price
        fib_ok = (FIB_W2[0] <= (w2 / w1 if w1 else 9) <= FIB_W2[1]) and \
                 (FIB_W4[0] <= (w4 / w3 if w3 else 9) <= FIB_W4[1])
        w5_target = p3.price - w3 * 0.618 if w3 else np.nan

    if not all(rules.values()):
        return None
    ratio = w3 / w1 if w1 else np.nan
    return Structure(direction=d, kind="IMPULSE_W5", piv=tuple(piv5),
                     w1=w1, w2=w2, w3=w3, w4=w4,
                     ret2=(w2 / w1 if w1 else np.nan), ret4=(w4 / w3 if w3 else np.nan),
                     ratio31=ratio, w3_class=_w3_class(ratio), invalidation=invalidation,
                     rules=rules, fib_ok=fib_ok, as_of=p4.confirm_idx, w5_target_fib=w5_target)


def detect_abc(piv3: list[Pivot]) -> Structure | None:
    """3-волновая коррекция (отдельная branch, §6/§10 — не смешивать с W5)."""
    if len(piv3) != 3:
        return None
    a, b, c = piv3
    kinds = "".join(p.kind for p in piv3)
    if kinds == "HLH":
        d = -1
    elif kinds == "LHL":
        d = 1
    else:
        return None
    wa = abs(b.price - a.price)
    wc = abs(c.price - b.price)
    if wa <= 0 or wc <= 0:
        return None
    return Structure(direction=d, kind="ABC", piv=tuple(piv3),
                     w1=wa, w2=np.nan, w3=wc, w4=np.nan, ret2=np.nan, ret4=np.nan,
                     ratio31=np.nan, w3_class="UNAVAILABLE", invalidation=c.price,
                     rules={"abc": True}, fib_ok=False, as_of=c.confirm_idx)


def structures_online(pivots: list[Pivot], n_bars: int) -> list[tuple[int, Structure]]:
    """Для каждого бара — структура, известная на этот момент (причинно).

    Возвращает список (bar_index, Structure) — по одной «свежей» структуре на момент
    её появления. Дальше структура живёт, пока не умерла по dead().
    """
    out: list[tuple[int, Structure]] = []
    seen: set[tuple] = set()
    for i in range(n_bars):
        known = pivots_as_of(pivots, i)
        if len(known) < 5:
            continue
        st = detect_impulse(known[-5:])
        if st is None and len(known) >= 3:
            st = detect_abc(known[-3:])
        if st is None:
            continue
        key = (st.kind, st.direction, tuple(p.idx for p in st.piv))
        if key in seen:
            continue
        seen.add(key)
        out.append((i, st))
    return out


def trigger_level(high: np.ndarray, low: np.ndarray, i: int, n: int = TRIGGER_DONCHIAN_N):
    """Причинный Donchian-канал по ПРЕДЫДУЩИМ n барам (текущий бар не участвует)."""
    if i - n < 0:
        return np.nan, np.nan
    return float(high[i - n:i].max()), float(low[i - n:i].min())
