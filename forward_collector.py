"""FORWARD OOS COLLECTOR — накопление реального золота (GC=F) для протокола freeze v2 §4.

Зачем: спот XAUUSD M15 из этой среды недоступен, а PAXG признан непригодным для
structural-валидации (шум базиса 1.98 × ATR, совпадение сигналов 2/9). Но Yahoo отдаёт
скользящие 60 дней M15 по GC=F (реальный фьючерс COMEX) → каждый запуск дописывает новые
бары, и со временем накапливается честный forward-датасет, не затронутый research sample.

Что делает запуск:
  1. дописывает новые бары M15/H1 в data/forward/*.csv (дедупликация по времени);
  2. если баров после точки отсчёта (2026-09-15 20:00 UTC) достаточно — прогоняет
     кандидата v2 ТОЛЬКО по forward-окну и печатает сигналы (freeze в момент выдачи, S18);
  3. пишет лог запусков data/forward/collection_log.jsonl.

Запуск:  python3 forward_collector.py [--no-dashboard]   (можно cron-ом раз в сутки)

RULE 13 / §35: журнал сигналов `data/forward/forward_signals.csv` — append-only.
Замороженные поля (entry/SL/TP/R/invalidation/branch) НЕ перезаписываются никогда;
обновляются только поля исхода (exit/reason/net_r...). Расхождение замороженных полей
логируется как INTEGRITY WARNING.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))

import backtest as bt                                 # noqa: E402
import events as ev                                   # noqa: E402
import metrics as mt                                  # noqa: E402
import wyckoff as wk                                  # noqa: E402
from branches import BY_ID, GEOMETRIES                # noqa: E402
from data import fetch_yahoo                          # noqa: E402

import os                                                # noqa: E402

SANDBOX = "--sandbox" in sys.argv
FWD = ROOT / ("data/forward_sandbox" if SANDBOX else "data/forward")
FWD.mkdir(parents=True, exist_ok=True)
_ep = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--epoch=")), None)
EPOCH = (pd.Timestamp(_ep, tz="UTC") if _ep else pd.Timestamp("2026-09-15 20:00", tz="UTC"))
if os.environ.get("XAU_FWD_DIR") is None:
    os.environ["XAU_FWD_DIR"] = str(FWD)
CAND = [BY_ID[b] for b in ["B04_LONG_EXTW3_RSI", "B01_LONG_CORE", "B02_LONG_EMA200_FIBOFF"]]
GEOM = GEOMETRIES["G_BASE47"]
RT = 0.40 + 2 * 0.06
ACCEPT_N, ACCEPT_P, MAX_DD = 74, 0.10, 15.0


FROZEN_FIELDS = ["signal_time", "entry_time", "branch", "geom", "direction", "k_swing",
                 "entry", "sl", "tp", "r_usd", "invalidation", "w3_class"]
OUTCOME_FIELDS = ["exit_time", "exit", "reason", "gross_r", "net_r", "cost_r",
                  "mae_r", "mfe_r", "hold_bars"]


def update_signal_journal(trades: list) -> tuple[pd.DataFrame, int, list[str]]:
    """Append-only журнал замороженных сигналов + обновление только исходов."""
    p = FWD / "forward_signals.csv"
    new = pd.DataFrame([t.to_dict() for t in trades])
    warns: list[str] = []
    if not p.exists():
        if new.empty:
            return pd.DataFrame(), 0, warns
        new.to_csv(p, index=False)
        return new, len(new), warns
    old = pd.read_csv(p)
    if new.empty:
        return old, 0, warns
    key = ["entry_time", "branch"]
    idx = {(r["entry_time"], r["branch"]): i for i, r in old.iterrows()}
    added = 0
    for _, row in new.iterrows():
        k = (row["entry_time"], row["branch"])
        if k in idx:
            i = idx[k]
            for f in FROZEN_FIELDS:                       # контроль неизменности (RULE 13)
                if f in old.columns and f in row.index:
                    a, b = old.at[i, f], row[f]
                    if isinstance(a, float) and isinstance(b, float):
                        if abs(a - b) > 1e-9:
                            warns.append(f"{k}: замороженное поле {f} изменилось {a} → {b}")
                    elif str(a) != str(b):
                        warns.append(f"{k}: замороженное поле {f} изменилось {a} → {b}")
            for f in OUTCOME_FIELDS:                      # обновляем только исход
                if f in row.index:
                    old.at[i, f] = row[f]
        else:
            old = pd.concat([old, row.to_frame().T], ignore_index=True)
            added += 1
    old = old.sort_values("entry_time").reset_index(drop=True)
    old.to_csv(p, index=False)
    return old, added, warns


def append_store(fname: str, fresh: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    p = FWD / fname
    if p.exists():
        old = pd.read_csv(p, parse_dates=["time"])
        old["time"] = pd.to_datetime(old["time"], utc=True)
        merged = pd.concat([old, fresh]).drop_duplicates("time").sort_values("time")
    else:
        merged = fresh
    added = len(merged) - (len(pd.read_csv(p)) if p.exists() else 0)
    merged.to_csv(p, index=False)
    return merged.reset_index(drop=True), int(added)


def main(no_dashboard: bool = False) -> int:
    t0 = time.time()
    m15 = fetch_yahoo("GC=F", "15m", days=58)
    h1 = fetch_yahoo("GC=F", "1h", days=720)
    m15["time"] = pd.to_datetime(m15["time"], utc=True)
    h1["time"] = pd.to_datetime(h1["time"], utc=True)
    s15, a15 = append_store("gcf_m15_forward.csv", m15)
    s1, a1 = append_store("gcf_h1_forward.csv", h1)

    log = {"run_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
           "m15_rows": len(s15), "m15_added": a15, "h1_rows": len(s1), "h1_added": a1,
           "m15_from": str(s15.time.iloc[0]), "m15_to": str(s15.time.iloc[-1])}

    print(f"=== FORWARD OOS COLLECTOR (GC=F, реальное золото){' · SANDBOX' if SANDBOX else ''} ===")
    print(f"эпоха forward-окна: {EPOCH} • каталог: {FWD.relative_to(ROOT)}")
    print(f"M15: {len(s15):,} баров (+{a15})  {s15.time.iloc[0]} → {s15.time.iloc[-1]}")
    print(f"H1 : {len(s1):,} баров (+{a1})   {s1.time.iloc[0]} → {s1.time.iloc[-1]}")

    fwd = s15[s15.time > EPOCH].reset_index(drop=True)
    log["forward_bars"] = len(fwd)
    print(f"\nForward-окно (после {EPOCH}): {len(fwd):,} M15-баров")

    if len(fwd) < 200:
        print("Недостаточно баров для прогона — только накопление. "
              f"Нужно ≥200 M15-баров (~2 торговых дня), сейчас {len(fwd)}.")
        log["status"] = "ACCUMULATING"
    else:
        data = bt.prepare(s15, k=2.0)          # разметка на всей истории (прогрев), сигналы — только в forward-окне
        ctx = bt.build_context(s15, df_h1=s1, df_d1=s1)
        mask, events = ev.blocked_mask(data["t"])
        wy = wk.wyckoff_series(data["v"], data["h"], data["l"], data["c"], data["structs"], data["n"])
        res = bt.run(data, ctx, CAND, GEOM, bt.Costs(0, 0), start=EPOCH, event_mask=mask, wyckoff=wy)
        for t in res.trades:
            t.cost_r = RT / t.r_usd
            t.net_r = t.gross_r - t.cost_r
        m = mt.metrics(res.trades)
        log["status"] = "RUNNING"
        journal, added, warns = update_signal_journal(res.trades)
        log["signals_total"] = len(journal)
        log["signals_new"] = added
        log["integrity_warnings"] = warns
        if warns:
            print("\n⚠️ INTEGRITY WARNING (RULE 13):")
            for w in warns[:5]:
                print("   ", w)
        else:
            print(f"\nЖурнал сигналов: {len(journal)} записей (+{added} новых), замороженные поля не изменялись ✓")
        log["forward_metrics"] = {k: m.get(k) for k in ["trades", "win_rate_pct", "pf_net", "expectancy_r",
                                                        "net_r", "max_dd_r", "p_value", "required_n_95"]}
        print(f"\nКандидат v2 на forward-окне: {mt.fmt_metrics(m)}")
        if res.trades:
            print("\nСигналы (freeze в момент выдачи, S18 → RULE 13, переписыванию не подлежат):")
            for t in res.trades:
                print(f"  {t.entry_time}  {'LONG' if t.direction>0 else 'SHORT'} {t.branch}  "
                      f"entry {t.entry:.2f} SL {t.sl:.2f} TP {t.tp:.2f} R {t.r_usd:.2f} USD  "
                      f"W3={t.w3_class} wyckoff={t.wyckoff} → {t.reason} {t.net_r:+.2f}R")
        verdict = "NEEDS_MORE_DATA (S27)"
        if m.get("trades", 0) >= ACCEPT_N:
            ok = (m["expectancy_r"] > 0 and m["p_value"] < ACCEPT_P and abs(m["max_dd_r"]) <= MAX_DD)
            verdict = "ACCEPT → P3" if ok else "REJECT"
        log["acceptance"] = verdict
        print(f"\nACCEPTANCE (§60, freeze v2 §4): {verdict} "
              f"(нужно N ≥ {ACCEPT_N}, сейчас {m.get('trades', 0)})")

    if "signals_total" not in log:
        j = FWD / "forward_signals.csv"
        log["signals_total"] = len(pd.read_csv(j)) if j.exists() else 0
        log["signals_new"] = 0
        log["integrity_warnings"] = []
    with (FWD / "collection_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False, default=str) + "\n")
    print(f"лог: {FWD.relative_to(ROOT)}/collection_log.jsonl")

    if not no_dashboard:
        try:
            sys.path.insert(0, str(ROOT))
            import importlib
            import dashboard
            importlib.reload(dashboard)
            html = dashboard.build()
            target = ROOT / "dashboard" / ("preview_sandbox.html" if SANDBOX else "index.html")
            target.write_text(html, encoding="utf-8")
            print(f"дашборд пересобран: {target.relative_to(ROOT)} ({len(html)//1024} КБ)"
                  + ("  [PREVIEW — sandbox-эпоха, не боевой]" if SANDBOX else ""))
        except Exception as e:
            print(f"⚠️ дашборд не пересобран: {type(e).__name__}: {e}")
    print(f"готово за {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(no_dashboard="--no-dashboard" in sys.argv))
