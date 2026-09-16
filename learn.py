#!/usr/bin/env python3
"""ОБУЧЕНИЕ И КАЛИБРОВКА (§63–66) — отчёт LEARNING_v1.md.

Принципы канона, зашитые в код:
  • сначала классификация ошибок (§66), только потом гипотеза;
  • кандидаты на изменение правил фиксируются как PRE-REGISTERED и НЕ применяются (§64–65);
  • tier калибровки зависит от объёма выборки (§63): <10 — NO PARAMETER CHANGES,
    10–29 — SOFT RESEARCH, 30–49 — NORMAL, 50+ — FULL (и всё равно только после нового validation cycle);
  • Final OOS для калибровки не используется (§64).

Запуск:  python3 learn.py [paper_journal.csv ...]
Выход:   reports/LEARNING_v1.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
import metrics as mt                                    # noqa: E402
from freeze_hash import freeze_hash                     # noqa: E402

REP = ROOT / "reports"
SOURCES = {
    "research v2 (G_BASE47, PROXY)": REP / "trades_G_BASE47.csv",
    "research v2 (G_PROD, PROXY)": REP / "trades_G_PROD.csv",
    "walk-forward OOS": REP / "trades_walkforward_oos.csv",
    "forward OOS (реальное золото)": ROOT / "data" / "forward" / "forward_signals.csv",
}


def classify(t: pd.Series) -> str:
    net, reason, mfe = t.get("net_r"), t.get("reason"), t.get("mfe_r")
    if pd.isna(net):
        return "OPEN"
    if net > 0:
        return "WIN-RUNNER-CANDIDATE" if (pd.notna(mfe) and mfe >= 1.5) else "WIN"
    if reason in ("SL", "SL_FIRST"):
        if pd.notna(mfe) and mfe >= 1.0:
            return "EXECUTION ERROR: TP недосягаем / вход поздний"
        if pd.notna(mfe) and mfe < 0.2:
            return "TRIGGER ERROR: вход против движения"
        return "REGIME ERROR: шум против позиции"
    if reason == "STRUCT":
        return "STRUCTURE ERROR: invalidation сработал"
    if reason == "TIME":
        return "HOLD ERROR: не реализовалась за 96 баров"
    if reason == "MANUAL":
        return "MANUAL EXIT (исключить из статистики правил)"
    return "UNKNOWN"


def candidates(counts: dict) -> list[dict]:
    out = []
    def add(cid, text, why):
        out.append({"id": cid, "text": text,
                    "status": f"НЕ применено: {why}"})
    if counts.get("EXECUTION ERROR: TP недосягаем / вход поздний", 0) >= 3:
        add("H-TP", "уменьшить TP до 0.8R ИЛИ ужесточить trigger до Donchian(6)",
            "walk-forward 365/90 на новом окне + costs (§65)")
    if counts.get("TRIGGER ERROR: вход против движения", 0) >= 3:
        add("H-TRIG", "подтверждение входа: close > EMA20(M15) на сигнальном баре",
            "pre-registration + отдельный OOS (§68–69)")
    if counts.get("HOLD ERROR: не реализовалась за 96 баров", 0) >= 3:
        add("H-HOLD", "max hold 96 → 144 баров", "валидация на новом окне (§46 freeze)")
    if counts.get("REGIME ERROR: шум против позиции", 0) >= 5:
        add("H-VOL", "фильтр волатильности: ATR(M15) ≤ 75-го перцентиля за 200 баров",
            "ablation → walk-forward → OOS (§68)")
    if counts.get("WIN-RUNNER-CANDIDATE", 0) >= 3:
        add("H-RUN", "исследовать runner-ветку: trailed stop после +1R",
            "отдельная frozen branch, не трогая текущую (§25)")
    return out


def main(extra: list[str]) -> int:
    md = ["# LEARNING v1 — классификация ошибок и калибровка (§63–66)", "",
          f"Сформировано: {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M UTC} • freeze SHA-256: `{freeze_hash()}` • "
          "Правила НЕ изменяются: все кандидаты pre-registered и ждут нового validation cycle.", ""]
    total_counts: dict[str, int] = {}
    for name, path in list(SOURCES.items()) + [(f"paper: {Path(p).name}", Path(p)) for p in extra]:
        p = Path(path)
        if not p.exists():
            md += [f"## {name}", "", "_файл отсутствует_", ""]
            continue
        df = pd.read_csv(p)
        if not len(df) or "net_r" not in df.columns:
            md += [f"## {name}", "", f"_сделок: 0 (накопление)_", ""]
            continue
        df = df[df.get("reason", "") != "MANUAL"] if "reason" in df.columns else df
        df["error_class"] = df.apply(classify, axis=1)
        m = mt.metrics_from_df(df) if hasattr(mt, "metrics_from_df") else None
        net = df["net_r"].dropna().to_numpy(float)
        wr = (net > 0).mean() * 100 if len(net) else 0
        gw, gl = net[net > 0].sum(), -net[net < 0].sum()
        pf = gw / gl if gl > 0 else float("inf")
        counts = df["error_class"].value_counts().to_dict()
        for k, v in counts.items():
            total_counts[k] = total_counts.get(k, 0) + int(v)
        tier = ("**<10 сделок → NO PARAMETER CHANGES**" if len(net) < 10 else
                "**10–29 → SOFT RESEARCH**" if len(net) < 30 else
                "**30–49 → NORMAL CALIBRATION**" if len(net) < 50 else "**50+ → FULL CALIBRATION**")
        md += [f"## {name}", "",
               f"- сделок: **{len(net)}** • WR {wr:.1f}% • PF {pf:.3f} • Exp {net.mean():+.4f}R • Net {net.sum():+.1f}R",
               f"- MAE среднее {df['mae_r'].mean():.3f}R • MFE среднее {df['mfe_r'].mean():.3f}R",
               f"- tier калибровки (§63): {tier}", "",
               "| Класс ошибки (§66) | Кол-во |", "|---|---|"]
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
            md.append(f"| {k} | {v} |")
        md.append("")
    md += ["## Сводные классы ошибок", "", "| Класс | Всего |", "|---|---|"]
    for k, v in sorted(total_counts.items(), key=lambda kv: -kv[1]):
        md.append(f"| {k} | {v} |")
    cand = candidates(total_counts)
    md += ["", "## Pre-registered кандидаты (НЕ применены)", ""]
    if cand:
        md += ["| ID | Изменение | Статус |", "|---|---|---|"]
        md += [f"| {c['id']} | {c['text']} | {c['status']} |" for c in cand]
    else:
        md.append("Порог ≥3 ошибок одного класса не достигнут — кандидатов нет. "
                  "Система продолжает наблюдение без изменений (§63).")
    md += ["", "## Протокол следующего шага (§65)", "",
           "1. OBSERVATION — этот отчёт;",
           "2. ERROR CLASSIFICATION — таблица выше;",
           "3. HYPOTHESIS — кандидаты выше;",
           "4. PRE-REGISTERED RULE — зафиксировать в `PARAMETER_FREEZE_vN` до прогона;",
           "5. BACKTEST → VALIDATION → OOS на данных, которых не было в этом отчёте;",
           "6. ACCEPT / REJECT / NEEDS MORE DATA.",
           "", "**Запрещено:** менять правила по итогам этого отчёта (§64); калибровать по Final OOS; "
           "менять stop/target задним числом (§70).", ""]
    (REP / "LEARNING_v1.md").write_text("\n".join(md), encoding="utf-8")
    print(f"→ {REP/'LEARNING_v1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
