#!/usr/bin/env python3
"""РЕЕСТР ЖИЗНЕННОГО ЦИКЛА ВЕТОК (Q4 совета): research → candidate → active → retired.

Статусы меняются только по формальным критериям и только с датой и причиной.
Выход: reports/BRANCH_REGISTRY_v1.md
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
from freeze_hash import freeze_hash  # noqa: E402

REP = ROOT / "reports"

REG = [
    # id, статус, дата решения, причина/ evidence
    ("B01_LONG_CORE", "active", "2026-09-16", "база v2: N=21, WR 66.7%, Exp +0.284R; forward-подтверждение ожидается"),
    ("B02_LONG_EMA200_FIBOFF", "active", "2026-09-16", "база v2: N=13, WR 76.9%, Exp +0.496R; малый N — следить за CI"),
    ("B04_LONG_EXTW3_RSI", "active", "2026-09-16", "база v2: N=90, WR 62.2%, Exp +0.204R — основная по объёму"),
    ("B03_LONG_W3A_HV", "retired", "2026-09-16", "N=19, WR 47.4%, Exp −0.095R: класс W3-A не подтверждён (канон §9 не воспроизвёлся)"),
    ("B05_SHORT_CORE", "retired", "2026-09-16", "N=5 в базе v2, Exp отрицательный; SHORT не воспроизводится"),
    ("B06_SHORT_RSI_FIBOFF", "retired", "2026-09-16", "N=2, Exp −1.105R; канон §16 (PF 2.25) не воспроизвёлся"),
    ("B07_SHORT_H4_ALIGNED", "retired", "2026-09-16", "N=18, WR 50.0%, Exp −0.070R; канон §48 не воспроизвёлся"),
    ("ABC", "research", "2026-09-16", "коррекции размечаются, не торгуются (§6/§10)"),
    ("FAILED_FIFTH", "research", "2026-09-16", "только причинная разметка, без торговли (§6)"),
    ("H-MTF-ALIGN", "candidate", "2026-09-16", "pre-registered (freeze v2.2): вход при согласии H4+M15+M5; ждёт walk-forward"),
]

CRIT = [
    "active → retired: Exp < 0 при N ≥ 20 в базе ИЛИ forward-выборке, либо 95% CI для Exp исключает 0;",
    "candidate → active: только после walk-forward 365/90 с positive OOS и N ≥ 50 (§63–65);",
    "research → candidate: формальное причинное определение + pre-registration в freeze;",
    "retired → candidate: только новая pre-registered гипотеза и новые данные, не прежние.",
]


def main() -> int:
    md = ["# РЕЕСТР ВЕТОК v1 — жизненный цикл", "",
          f"freeze SHA-256: `{freeze_hash()}` · обновлено: 2026-09-16 · ведёт агент.", "",
          "| Branch | Статус | Дата решения | Обоснование |", "|---|---|---|---|"]
    for b, st, d, why in REG:
        md.append(f"| `{b}` | **{st}** | {d} | {why} |")
    md += ["", "## Критерии перехода", ""] + [f"- {c}" for c in CRIT] + ["",
           "## Правило ведения", "",
           "Статус меняется только записью в этом реестре с датой и причиной; одновременное изменение "
           "правил ветки и её статуса запрещено (§64). Реестр публикуется на сайте в каталоге отчётов.", ""]
    (REP / "BRANCH_REGISTRY_v1.md").write_text("\n".join(md), encoding="utf-8")
    print(f"→ {REP/'BRANCH_REGISTRY_v1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
