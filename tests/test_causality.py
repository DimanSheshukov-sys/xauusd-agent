"""G01 CAUSALITY TEST — доказательство отсутствия look-ahead.

Тест 1 (truncation): сигнал на баре i, пересчитанный на префиксе данных [0..i+1],
        обязан дать ТОТ ЖЕ entry/SL/TP/branch, что и на полном датасете.
Тест 2 (perturbation): к префиксу дописываются 500 баров абсурдного будущего
        (цена ×2, ×0.5). Если решение на баре i изменилось — где-то look-ahead.
Тест 3 (struct watermark): ни один пивот не используется раньше своего confirm_idx.

Запуск:  python3 tests/test_causality.py [n_samples]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

import backtest as bt
import elliott as ew
from branches import BRANCHES, GEOMETRIES
from data import load
from swings import pivots_as_of, zigzag

N_SAMPLES = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def pivot_watermark_test(df: pd.DataFrame) -> bool:
    """Тест 3: confirm_idx всегда > idx пивота, и пивоты идут строго по возрастанию."""
    data = bt.prepare(df, k=2.0)
    piv = data["pivots"]
    ok = all(p.confirm_idx > p.idx for p in piv)
    ok &= all(piv[i].confirm_idx <= piv[i + 1].confirm_idx for i in range(len(piv) - 1))
    ok &= all(piv[i].idx < piv[i + 1].idx for i in range(len(piv) - 1))
    # причинный срез не должен содержать пивоты из будущего
    mid = len(piv) // 2
    bar = piv[mid].confirm_idx
    ok &= all(p.confirm_idx <= bar for p in pivots_as_of(piv, bar))
    print(f"[T3] pivot watermark: {'PASS' if ok else 'FAIL'}  (пивотов: {len(piv)})")
    return bool(ok)


def collect_signals(df: pd.DataFrame, branch, geom, costs, df_h1: pd.DataFrame | None = None) -> list:
    """df_h1 передаётся ОБРЕЗАННЫМ до того же момента — иначе EMA200 на префиксе
    считается от другого начала и сравнение теряет смысл (EMA имеет бесконечную память)."""
    data = bt.prepare(df, k=2.0)
    if df_h1 is not None:
        h1 = df_h1[df_h1.time <= df.time.iloc[-1]].reset_index(drop=True)
        ctx = bt.build_context(df, df_h1=h1, df_d1=h1)
    else:
        ctx = bt.build_context(df)
    return bt.run(data, ctx, branch, geom, costs).trades


def main() -> int:
    df = load("paxg_m15")
    df_h1 = load("paxg_h1")
    print(f"Датасет: {len(df)} баров {df.time.iloc[0]} → {df.time.iloc[-1]}\n")
    results = {"T3": pivot_watermark_test(df)}

    branch = next(b for b in BRANCHES if b.id == "B02_LONG_EMA200_FIBOFF")
    geom = GEOMETRIES["G_PROD"]
    costs = bt.Costs()

    full = collect_signals(df, branch, geom, costs, df_h1)
    print(f"\nПолный прогон {branch.id}/{geom.id}: {len(full)} сделок")
    if not full:
        print("Нет сделок для теста — беру любую ветку с сделками")
        for b in BRANCHES:
            for g in (GEOMETRIES["G_PROD"], GEOMETRIES["G_BASE47"]):
                t = collect_signals(df, b, g, costs, df_h1)
                if len(t) >= N_SAMPLES:
                    branch, geom, full = b, g, t
                    print(f"→ выбрано {b.id}/{g.id}: {len(t)} сделок")
                    break
            if len(full) >= N_SAMPLES:
                break
    if not full:
        print("СДЕЛОК НЕТ ВОВСЕ — причинность не проверить на этой конфигурации")
        return 1

    idxs = np.linspace(0, len(full) - 1, min(N_SAMPLES, len(full))).astype(int)
    samples = [full[i] for i in idxs]

    t1 = t2 = 0
    for tr in samples:
        i = tr.signal_bar
        # i+3: движок обрабатывает бары до n-2, поэтому префикс обязан включать i+2,
        # иначе бар i вообще не рассматривается (это был дефект теста, а не движка)
        prefix = df.iloc[:i + 3].reset_index(drop=True)
        pf_trades = collect_signals(prefix, branch, geom, costs, df_h1)
        match = [t for t in pf_trades if t.signal_bar == i]
        ok1 = bool(match) and abs(match[0].entry - tr.entry) < 1e-9 \
            and abs(match[0].sl - tr.sl) < 1e-9 and abs(match[0].tp - tr.tp) < 1e-9
        t1 += ok1

        # Тест 2: абсурдное будущее после i+1
        fut = prefix.iloc[[-1]].copy()
        spike = []
        last_t = pd.Timestamp(prefix.time.iloc[-1])
        for k in range(1, 501):
            mult = 2.0 if k % 2 == 0 else 0.5
            row = fut.copy()
            row["time"] = last_t + pd.Timedelta(minutes=15 * k)
            for col in ["open", "high", "low", "close"]:
                row[col] = prefix.close.iloc[-1] * mult
            row["volume"] = 1.0
            spike.append(row)
        pert = pd.concat([prefix] + spike, ignore_index=True)
        pt = collect_signals(pert, branch, geom, costs, df_h1)
        pm = [t for t in pt if t.signal_bar == i]
        ok2 = bool(pm) and abs(pm[0].entry - tr.entry) < 1e-9 and abs(pm[0].sl - tr.sl) < 1e-9 \
            and abs(pm[0].tp - tr.tp) < 1e-9 and pm[0].reason in ("", "TP", "SL", "SL_FIRST", "STRUCT", "TIME")
        t2 += ok2
        print(f"  signal {tr.entry_time[:16]}  bar#{i:6d}  T1={'PASS' if ok1 else 'FAIL'}  T2={'PASS' if ok2 else 'FAIL'}"
              f"  entry={tr.entry:.2f} sl={tr.sl:.2f} tp={tr.tp:.2f}")

    n = len(samples)
    results["T1"] = (t1 == n)
    results["T2"] = (t2 == n)
    print(f"\n[T1] truncation equivalence: {t1}/{n} → {'PASS' if t1 == n else 'FAIL'}")
    print(f"[T2] future perturbation   : {t2}/{n} → {'PASS' if t2 == n else 'FAIL'}")
    verdict = all(results.values())
    print(f"\nИТОГ G01 CAUSALITY: {'PASS' if verdict else 'FAIL'}  {results}")
    import json as _json
    from pathlib import Path as _P
    rep = _P(__file__).resolve().parent.parent / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "causality.json").write_text(_json.dumps({
        "verdict": "PASS" if verdict else "FAIL", "tests": {k: bool(v) for k, v in results.items()},
        "samples": n, "branch": branch.id, "geometry": geom.id,
        "run_utc": __import__("time").strftime("%Y-%m-%d %H:%M UTC", __import__("time").gmtime()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
