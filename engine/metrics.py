"""PERFORMANCE METRICS (§54) + ROLLING STABILITY (§62) + статзначимость (§60 SAMPLE SUFFICIENT)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

Z95 = 1.959963985


def profit_factor(net: np.ndarray) -> float:
    g = net[net > 0].sum()
    l = -net[net < 0].sum()
    return float("inf") if l == 0 and g > 0 else (g / l if l > 0 else float("nan"))


def max_drawdown_r(net: np.ndarray) -> tuple[float, int, int]:
    eq = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq])[:-1])
    dd = eq - peak
    i = int(np.argmin(dd))
    j = int(np.argmax(eq[:i + 1])) if i > 0 else 0
    return float(dd[i]) if len(dd) else 0.0, j, i


def max_losing_streak(net: np.ndarray) -> int:
    best = cur = 0
    for x in net:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def required_n(expectancy: float, sd: float, z: float = Z95) -> float:
    """Сколько сделок нужно, чтобы с вероятностью 95% отличить expectancy от нуля."""
    if expectancy <= 0 or sd <= 0:
        return float("inf")
    return (z * sd / expectancy) ** 2


def metrics(trades: list, net_key: str = "net_r") -> dict:
    if not trades:
        return {"trades": 0}
    df = pd.DataFrame([t.to_dict() for t in trades])
    net = df[net_key].to_numpy(float)
    gross = df["gross_r"].to_numpy(float)
    wins, losses = net[net > 0], net[net < 0]
    mdd, _, _ = max_drawdown_r(net)
    sd = float(net.std(ddof=1)) if len(net) > 1 else float("nan")
    exp = float(net.mean())
    t_stat = exp / (sd / math.sqrt(len(net))) if sd and not math.isnan(sd) and sd > 0 else float("nan")
    from statistics import NormalDist
    p_val = 2 * (1 - NormalDist().cdf(abs(t_stat))) if not math.isnan(t_stat) else float("nan")
    longs, shorts = df[df.direction > 0], df[df.direction < 0]

    out = {
        "trades": len(df),
        "win_rate_pct": float((net > 0).mean() * 100),
        "pf_net": profit_factor(net),
        "pf_gross": profit_factor(gross),
        "expectancy_r": exp,
        "expectancy_gross_r": float(gross.mean()),
        "net_r": float(net.sum()),
        "cost_r_total": float(df["cost_r"].sum()),
        "avg_win_r": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_r": float(losses.mean()) if len(losses) else 0.0,
        "max_dd_r": mdd,
        "recovery_factor": float(net.sum() / abs(mdd)) if mdd else float("inf"),
        "max_losing_streak": max_losing_streak(net),
        "avg_mae_r": float(df["mae_r"].mean()),
        "avg_mfe_r": float(df["mfe_r"].mean()),
        "tp_hit_pct": float((df.reason.isin(["TP"])).mean() * 100),
        "sl_before_tp_pct": float((df.reason.isin(["SL", "SL_FIRST"])).mean() * 100),
        "sl_first_pct": float((df.reason == "SL_FIRST").mean() * 100),
        "struct_exit_pct": float((df.reason == "STRUCT").mean() * 100),
        "time_exit_pct": float((df.reason == "TIME").mean() * 100),
        "avg_hold_bars": float(df["hold_bars"].mean()),
        "long_n": len(longs), "long_pf": profit_factor(longs[net_key].to_numpy(float)) if len(longs) else float("nan"),
        "long_exp_r": float(longs[net_key].mean()) if len(longs) else float("nan"),
        "short_n": len(shorts), "short_pf": profit_factor(shorts[net_key].to_numpy(float)) if len(shorts) else float("nan"),
        "short_exp_r": float(shorts[net_key].mean()) if len(shorts) else float("nan"),
        "sd_per_trade_r": sd,
        "t_stat": t_stat, "p_value": p_val,
        "significant_95": bool(p_val < 0.05) if not math.isnan(p_val) else False,
        "required_n_95": required_n(exp, sd),
        "first": str(df["entry_time"].iloc[0])[:16], "last": str(df["entry_time"].iloc[-1])[:16],
    }
    return out


def by_year(trades: list, net_key: str = "net_r") -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame([t.to_dict() for t in trades])
    df["year"] = pd.to_datetime(df["entry_time"]).dt.year
    rows = []
    for y, g in df.groupby("year"):
        net = g[net_key].to_numpy(float)
        rows.append({"year": int(y), "trades": len(g), "win_rate_pct": round((net > 0).mean() * 100, 1),
                     "pf": round(profit_factor(net), 3), "net_r": round(net.sum(), 2),
                     "exp_r": round(net.mean(), 4), "max_dd_r": round(max_drawdown_r(net)[0], 2)})
    return rows


def rolling(trades: list, windows=(20, 30, 50), net_key: str = "net_r") -> dict:
    """§62: rolling PF/expectancy по окнам сделок. Возвращает долю окон с exp > 0 и минимум."""
    if not trades:
        return {}
    net = np.array([getattr(t, net_key) for t in trades], dtype=float)
    out = {}
    for w in windows:
        if len(net) < w:
            out[w] = {"windows": 0}
            continue
        exps, pfs = [], []
        for i in range(len(net) - w + 1):
            seg = net[i:i + w]
            exps.append(seg.mean())
            pfs.append(profit_factor(seg))
        exps = np.array(exps)
        out[w] = {"windows": len(exps), "pct_positive": round(float((exps > 0).mean() * 100), 1),
                  "min_exp_r": round(float(exps.min()), 3), "max_exp_r": round(float(exps.max()), 3),
                  "median_exp_r": round(float(np.median(exps)), 3),
                  "median_pf": round(float(np.median(pfs)), 3)}
    return out


def walk_forward(trades: list, test_days: int = 90, net_key: str = "net_r") -> list[dict]:
    """§45: последовательные test-окна по 90 дней. Параметры frozen → оконная OOS-нарезка."""
    if not trades:
        return []
    df = pd.DataFrame([t.to_dict() for t in trades])
    df["ts"] = pd.to_datetime(df["entry_time"])
    start = df["ts"].min().normalize()
    end = df["ts"].max()
    rows, cur = [], start
    while cur <= end:
        nxt = cur + pd.Timedelta(days=test_days)
        g = df[(df.ts >= cur) & (df.ts < nxt)]
        net = g[net_key].to_numpy(float)
        rows.append({"window": f"{cur.date()} → {nxt.date()}", "trades": len(net),
                     "win_rate_pct": round((net > 0).mean() * 100, 1) if len(net) else None,
                     "pf": round(profit_factor(net), 3) if len(net) else None,
                     "net_r": round(net.sum(), 2) if len(net) else 0.0,
                     "exp_r": round(net.mean(), 4) if len(net) else None})
        cur = nxt
    return rows


def by_w3_class(trades: list, net_key: str = "net_r") -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame([t.to_dict() for t in trades])
    rows = []
    for cls, g in df.groupby("w3_class"):
        net = g[net_key].to_numpy(float)
        rows.append({"w3_class": cls, "trades": len(g), "win_rate_pct": round((net > 0).mean() * 100, 1),
                     "pf": round(profit_factor(net), 3), "exp_r": round(net.mean(), 4),
                     "net_r": round(net.sum(), 2)})
    return rows


def fmt_metrics(m: dict) -> str:
    if not m.get("trades"):
        return "trades = 0"
    return (f"N={m['trades']}  WR={m['win_rate_pct']:.1f}%  PF(net)={m['pf_net']:.3f}  "
            f"PF(gross)={m['pf_gross']:.3f}  Exp={m['expectancy_r']:+.4f}R  Net={m['net_r']:+.2f}R  "
            f"MaxDD={m['max_dd_r']:.2f}R  costs={m['cost_r_total']:.2f}R  "
            f"t={m['t_stat']:.2f} p={m['p_value']:.3f}  N_95%={m['required_n_95']:.0f}")
