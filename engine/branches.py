"""BRANCH REGISTRY (G06) + EXECUTION GEOMETRY PROFILES (§25 vs §47).

Решение по расхождению §47 ↔ §25/§82: тестируем ОБЕ геометрии как отдельные
замороженные профили, ничего не подгоняя. Выбор — по OOS, а не по красоте.

Статусы веток — из §58 канона; новая ветка в live-анализе не изобретается (G06).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geometry:
    id: str
    long_sl_atr: float
    short_sl_atr: float
    tp_r: float
    max_hold_bars: int
    sl_compat: str = "tight"   # 'tight' = SL не шире structural invalidation (§26, умолчание)
    note: str = ""


GEOMETRIES = {
    # §25 / §82 production candidate
    "G_PROD": Geometry("G_PROD", 1.00, 0.75, 1.5, 96, note="§25/§82: LONG 1 ATR, SHORT 0.75 ATR, TP 1.5R"),
    # §47 frozen baseline — на нём получены headline-цифры §48
    "G_BASE47": Geometry("G_BASE47", 2.50, 2.50, 1.0, 96, note="§47: stop 2.5 ATR, target 1.0R, max hold 96"),
    # альтернативная трактовка §26 (SL шире структуры) — только как sensitivity
    "G_PROD_WIDE": Geometry("G_PROD_WIDE", 1.00, 0.75, 1.5, 96, sl_compat="wide",
                            note="как G_PROD, но §26 трактуется как 'SL за пределами invalidation'"),
}


@dataclass(frozen=True)
class Branch:
    id: str
    direction: int                 # +1 LONG, −1 SHORT
    kind: str                      # IMPULSE_W5 | ABC | FAILED_FIFTH
    w3_classes: tuple | None       # None = любой
    fib: bool | None               # True = Fib ON обязателен, False = Fib OFF, None = не важно
    regime: str                    # REQUIRED | CONTEXT_ONLY | DISABLED
    regime_side: str               # bull | bear | any
    h4_align: bool
    confirm: tuple                 # замороженные mandatory confirmations (§G08)
    status: str                    # P0..P4
    spec_ref: str

    @property
    def name(self) -> str:
        return self.id


BRANCHES = [
    Branch("B01_LONG_CORE",        +1, "IMPULSE_W5", None,  True,  "REQUIRED", "bull", False, (),          "P2",   "§12/§82"),
    Branch("B02_LONG_EMA200_FIBOFF", +1, "IMPULSE_W5", None, False, "REQUIRED", "bull", False, (),         "P1/P2", "§14"),
    Branch("B03_LONG_W3A_HV",      +1, "IMPULSE_W5", ("A",), False, "REQUIRED", "bull", False, (),         "P1",   "§13 high-conviction"),
    Branch("B04_LONG_EXTW3_RSI",   +1, "IMPULSE_W5", ("C",), False, "REQUIRED", "bull", False,
           (("rsi_h1_gt", 50.0),),                                             "P0",   "§24 momentum long"),
    Branch("B05_SHORT_CORE",       -1, "IMPULSE_W5", None,  True,  "REQUIRED", "bear", False,
           (("rsi_h1_lt", 50.0),),                                             "P1",   "§15"),
    Branch("B06_SHORT_RSI_FIBOFF", -1, "IMPULSE_W5", None, False,  "REQUIRED", "bear", False,
           (("rsi_h1_lt", 50.0),),                                             "P1",   "§16"),
    Branch("B07_SHORT_H4_ALIGNED", -1, "IMPULSE_W5", None, False,  "REQUIRED", "bear", True,
           (("rsi_h1_lt", 50.0),),                                             "P1",   "§48 H4-aligned"),
    Branch("B08_ABC_CONTEXT",      +1, "ABC",        None, False, "CONTEXT_ONLY", "any", False, (),        "P0",   "§6/§10 — research, не торгуется"),
]

TRADABLE = [b for b in BRANCHES if not (b.kind != "IMPULSE_W5" or b.status == "P0" and b.id == "B08_ABC_CONTEXT")]


def branch_table() -> str:
    rows = ["| Branch | Dir | Structure | W3 | Fib | Regime | H4 | Confirmations | Status | Spec |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for b in BRANCHES:
        rows.append(f"| `{b.id}` | {'LONG' if b.direction > 0 else 'SHORT'} | {b.kind} | "
                    f"{'/'.join(b.w3_classes) if b.w3_classes else 'any'} | "
                    f"{'ON' if b.fib else 'OFF' if b.fib is False else 'any'} | "
                    f"{b.regime}({b.regime_side}) | {'yes' if b.h4_align else '—'} | "
                    f"{', '.join(f'{k} {v}' for k, v in b.confirm) or '—'} | {b.status} | {b.spec_ref} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(branch_table())
    print()
    for g in GEOMETRIES.values():
        print(f"{g.id:14s} LONG SL={g.long_sl_atr} ATR  SHORT SL={g.short_sl_atr} ATR  TP={g.tp_r}R  "
              f"hold={g.max_hold_bars}  compat={g.sl_compat}  | {g.note}")


# ── замороженный приоритет атрибуции (PARAMETER_FREEZE_v1, секция H) ──
# Специфические ветки раньше общих: иначе B02 (Fib OFF, любой W3) перехватывает
# сигналы B03/B04 и их статистика оказывается пустой. На системный итог не влияет
# (проверено: priority_invariance = PASS в EXPERIMENT_v2).
PRIORITY = ["B03_LONG_W3A_HV", "B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF",
            "B07_SHORT_H4_ALIGNED", "B06_SHORT_RSI_FIBOFF", "B05_SHORT_CORE"]
BY_ID = {b.id: b for b in BRANCHES}
PRIO_BRANCHES = [BY_ID[i] for i in PRIORITY]
TRADABLE = [b for b in BRANCHES if b.kind == "IMPULSE_W5"]
