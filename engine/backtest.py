"""BACKTEST ENGINE (§44): воспроизводит live logical path, а не отдельный компонент.

Один прогон = одна State Machine: на каждом баре проверяются ВСЕ зарегистрированные
ветки в порядке приоритета реестра, открывается максимум одна позиция (§34/§35).

Порядок на каждом баре i (бар ЗАКРЫТ, все значения причинны):
  G00 data → G01 causality → G02 MTF → G03/G04 Elliott → G05 W3 → G06 branch
  → G07 regime → G08 confirmation/fib → G10 trigger → G11 invalidation
  → G12/G13 execution+target → G14 R:R → G15 DECISION
  entry = open[i+1]  (конвенция §47 "next M15 open")
Разрешение TP/SL внутри бара: при попадании обоих в один бар — SL FIRST (§28).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd

import elliott as ew
import indicators as ind
from branches import Branch, Geometry
from swings import zigzag, SWING_K


@dataclass
class Costs:
    """0.40 USD — замер спреда OANDA XAUUSD 2026-09-15 19:20 UTC (bid 4300.03 / ask 4300.43)."""
    spread_usd: float = 0.40
    commission_usd: float = 0.06
    slippage_usd: float = 0.00

    @property
    def round_trip_usd(self) -> float:
        return self.spread_usd + 2 * self.commission_usd + 2 * self.slippage_usd


@dataclass
class Trade:
    branch: str; geom: str; direction: int; k_swing: float
    signal_bar: int; signal_time: str
    entry_bar: int; entry_time: str; entry: float
    sl: float; tp: float; r_usd: float; invalidation: float
    exit_bar: int = -1; exit_time: str = ""; exit: float = np.nan; reason: str = ""
    gross_r: float = 0.0; cost_r: float = 0.0; net_r: float = 0.0
    mae_r: float = 0.0; mfe_r: float = 0.0; hold_bars: int = 0
    w3_class: str = ""; ratio31: float = np.nan; fib_ok: bool = False
    ret2: float = np.nan; ret4: float = np.nan
    d1_close: float = np.nan; d1_ema200: float = np.nan; h4_bear: bool = False
    rsi_h1: float = np.nan; atr_m15: float = np.nan
    kind: str = ""; wyckoff: bool = False; wyckoff_ratio: float = np.nan

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunResult:
    trades: list
    skipped: dict
    n_bars: int
    period: tuple
    structures_seen: int = 0


def prepare(df: pd.DataFrame, k: float = SWING_K) -> dict:
    """Все причинные массивы (считаются один раз на конфигурацию)."""
    o, h, l, c = (df[x].to_numpy(float) for x in ["open", "high", "low", "close"])
    v = df["volume"].to_numpy(float) if "volume" in df else np.zeros(len(df))
    atr15 = ind.atr(h, l, c, 14)
    rsi15 = ind.rsi(c, 14)
    dh, dl = ind.donchian(h, l, ew.TRIGGER_DONCHIAN_N)
    piv = zigzag(h, l, atr15, k=k)

    structs: dict[int, ew.Structure] = {}
    for i in range(1, len(piv) + 1):
        known = piv[:i]
        bar = known[-1].confirm_idx
        st = ew.detect_impulse(known[-5:]) if len(known) >= 5 else None
        if st is None and len(known) >= 3:
            st = ew.detect_abc(known[-3:])
        if st is not None:
            structs[bar] = st
    return {"t": df["time"].to_numpy(), "o": o, "h": h, "l": l, "c": c, "v": v,
            "atr": atr15, "rsi": rsi15, "dh": dh, "dl": dl,
            "pivots": piv, "structs": structs, "n": len(df), "k": k}


def _htf_closed(df_src: pd.DataFrame, rule: str) -> pd.DataFrame:
    """HTF-бары + EMA200/RSI, сдвинутые на 1 (берём только ЗАКРЫТЫЙ бар)."""
    idx = df_src.set_index("time")
    h = idx.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    h["ema200"] = ind.ema(h["close"].to_numpy(), 200)
    h["rsi14"] = ind.rsi(h["close"].to_numpy(), 14)
    out = pd.DataFrame({"time": pd.to_datetime(h.index).astype("datetime64[ns, UTC]")})
    for c in ["close", "ema200", "rsi14"]:
        out[c] = h[c].shift(1).to_numpy()
    return out.sort_values("time").reset_index(drop=True)


def build_context(df_exec: pd.DataFrame, df_h1: pd.DataFrame | None = None,
                  df_d1: pd.DataFrame | None = None) -> dict:
    """MTF-контекст, причинно выровненный по execution-барам.

    df_h1 / df_d1 — более длинные истории для H1/H4/D1. Это критично: D1 EMA200
    требует ≥200 закрытых дневных баров, иначе regime-гейт (G07) молча отключается
    и все сделки бракуются как mtf_nan (так было на gcf_m15: 0 сделок).
    """
    src_h1 = df_h1 if df_h1 is not None else df_exec
    src_d1 = df_d1 if df_d1 is not None else (df_h1 if df_h1 is not None else df_exec)
    exec_t = df_exec[["time"]].sort_values("time").reset_index(drop=True)
    exec_t["time"] = pd.to_datetime(exec_t["time"]).astype("datetime64[ns, UTC]")  # единая размерность для merge_asof
    out = {}
    for tag, rule, src in [("d1", "1D", src_d1), ("h4", "4h", src_h1), ("h1", "1h", src_h1)]:
        htf = _htf_closed(src, rule)
        al = pd.merge_asof(exec_t, htf, on="time", direction="backward")
        out[f"{tag}_close"] = al["close"].to_numpy()
        out[f"{tag}_ema200"] = al["ema200"].to_numpy()
        out[f"{tag}_rsi"] = al["rsi14"].to_numpy()
    return out


def _eligible(active, branch: Branch, i: int, ctx: dict, data: dict, skipped: dict):
    """Проверка gates G03–G10 для одной ветки на баре i. Возвращает (ok, extra)."""
    if active.kind != branch.kind:
        skipped["kind_mismatch"] += 1
        return False, None
    if active.direction != branch.direction:
        return False, None
    if branch.w3_classes is not None and active.w3_class not in branch.w3_classes:
        skipped["w3_class"] += 1
        return False, None
    d1c, d1e = ctx["d1_close"][i], ctx["d1_ema200"][i]
    if np.isnan(d1c) or np.isnan(d1e):
        skipped["mtf_nan"] += 1
        return False, None
    bull = d1c > d1e
    if branch.regime == "REQUIRED":
        need = bull if branch.regime_side == "bull" else (not bull)
        if not need:
            skipped["regime"] += 1
            return False, None
    h4_bear = (not np.isnan(ctx["h4_ema200"][i])) and ctx["h4_close"][i] < ctx["h4_ema200"][i]
    if branch.h4_align and not h4_bear:
        skipped["h4"] += 1
        return False, None
    r = ctx["h1_rsi"][i]
    for name, val in branch.confirm:
        if np.isnan(r):
            skipped["confirm"] += 1
            return False, None
        if name == "rsi_h1_lt" and not r < val:
            skipped["confirm"] += 1
            return False, None
        if name == "rsi_h1_gt" and not r > val:
            skipped["confirm"] += 1
            return False, None
    if branch.fib is True and not active.fib_ok:
        skipped["fib"] += 1
        return False, None
    dh, dl = data["dh"][i], data["dl"][i]
    if np.isnan(dh) or np.isnan(dl):
        skipped["trigger_absent"] += 1
        return False, None
    trig = data["c"][i] > dh if branch.direction > 0 else data["c"][i] < dl
    if not trig:
        return False, None
    return True, {"bull": bool(bull), "h4_bear": bool(h4_bear), "rsi_h1": float(r) if not np.isnan(r) else np.nan}


def run(data: dict, ctx: dict, branches, geom: Geometry, costs: Costs = Costs(),
        start=None, end=None, event_mask: np.ndarray | None = None,
        wyckoff: np.ndarray | None = None) -> RunResult:
    """branches: одна Branch или список (приоритет = порядок в списке).

    event_mask — §43: True на барах, где вход запрещён (FOMC/NFP ± 2h).
    wyckoff    — §18: контекстный флаг (только логируется, gate НЕ является).
    """
    if isinstance(branches, Branch):
        branches = [branches]
    n, t = data["n"], data["t"]
    o, h, l, c, atr_, structs = data["o"], data["h"], data["l"], data["c"], data["atr"], data["structs"]

    def _ts(x):
        x = pd.Timestamp(x)
        return x.tz_localize("UTC") if x.tzinfo is None else x.tz_convert("UTC")
    ti = pd.DatetimeIndex(pd.to_datetime(t).astype("datetime64[ns, UTC]"))
    i0 = 0 if start is None else int(ti.searchsorted(_ts(start)))
    i1 = n - 1 if end is None else int(ti.searchsorted(_ts(end)))

    trades: list[Trade] = []
    skipped = {"kind_mismatch": 0, "w3_class": 0, "regime": 0, "h4": 0, "confirm": 0, "fib": 0,
               "trigger_absent": 0, "sl_incompatible": 0, "atr_nan": 0, "in_position": 0,
               "expired": 0, "mtf_nan": 0, "no_structure": 0, "event_blocked": 0}
    active: ew.Structure | None = None
    pos_until = -1
    structs_seen = 0

    for i in range(max(i0, 1), min(i1, n - 2)):
        if i in structs:
            active = structs[i]
            structs_seen += 1
        if active is not None and active.dead(i, c[i]):
            if i - active.as_of > ew.SETUP_MAX_AGE:
                skipped["expired"] += 1
            active = None
        if active is None:
            skipped["no_structure"] += 1
            continue
        if i <= pos_until:
            skipped["in_position"] += 1
            continue

        if event_mask is not None and event_mask[i]:
            skipped["event_blocked"] += 1
            continue
        chosen = None
        for br in branches:
            ok, extra = _eligible(active, br, i, ctx, data, skipped)
            if ok:
                chosen, extra_info = br, extra
                break
        if chosen is None:
            continue
        branch = chosen

        if np.isnan(atr_[i]) or atr_[i] <= 0:
            skipped["atr_nan"] += 1
            continue
        entry = o[i + 1]
        sl_mult = geom.long_sl_atr if branch.direction > 0 else geom.short_sl_atr
        sl = entry - sl_mult * atr_[i] if branch.direction > 0 else entry + sl_mult * atr_[i]
        r_usd = abs(entry - sl)
        if r_usd <= 0:
            skipped["atr_nan"] += 1
            continue
        tp = entry + geom.tp_r * r_usd if branch.direction > 0 else entry - geom.tp_r * r_usd
        inv = active.invalidation
        if geom.sl_compat == "tight":
            compatible = sl >= inv if branch.direction > 0 else sl <= inv
        else:
            compatible = sl <= inv if branch.direction > 0 else sl >= inv
        if not compatible:
            skipped["sl_incompatible"] += 1
            continue
        if geom.tp_r < 1.0:
            skipped["sl_incompatible"] += 1
            continue

        tr = Trade(branch=branch.id, geom=geom.id, direction=branch.direction, k_swing=data["k"],
                   signal_bar=i, signal_time=str(pd.Timestamp(t[i]))[:19],
                   entry_bar=i + 1, entry_time=str(pd.Timestamp(t[i + 1]))[:19], entry=float(entry),
                   sl=float(sl), tp=float(tp), r_usd=float(r_usd), invalidation=float(inv),
                   w3_class=active.w3_class, ratio31=float(active.ratio31), fib_ok=bool(active.fib_ok),
                   ret2=float(active.ret2), ret4=float(active.ret4), kind=active.kind,
                   d1_close=float(ctx["d1_close"][i]), d1_ema200=float(ctx["d1_ema200"][i]),
                   h4_bear=extra_info["h4_bear"], rsi_h1=extra_info["rsi_h1"], atr_m15=float(atr_[i]),
                   wyckoff=bool(wyckoff[i]) if wyckoff is not None else False)

        cost_r = costs.round_trip_usd / r_usd
        exit_bar, exit_px, reason = -1, np.nan, ""
        last = min(i + geom.max_hold_bars, n - 1)
        mae = mfe = 0.0
        for j in range(i + 1, last + 1):
            lo_, hi_, cl_ = l[j], h[j], c[j]
            if branch.direction > 0:
                mae = min(mae, (lo_ - entry) / r_usd)
                mfe = max(mfe, (hi_ - entry) / r_usd)
                hit_sl, hit_tp = lo_ <= tr.sl, hi_ >= tr.tp
                if hit_sl and hit_tp:
                    exit_bar, exit_px, reason = j, tr.sl, "SL_FIRST"
                elif hit_sl:
                    exit_bar, exit_px, reason = j, tr.sl, "SL"
                elif hit_tp:
                    exit_bar, exit_px, reason = j, tr.tp, "TP"
                elif cl_ < inv:
                    exit_bar, exit_px, reason = j, cl_, "STRUCT"
            else:
                mae = min(mae, (entry - hi_) / r_usd)
                mfe = max(mfe, (entry - lo_) / r_usd)
                hit_sl, hit_tp = hi_ >= tr.sl, lo_ <= tr.tp
                if hit_sl and hit_tp:
                    exit_bar, exit_px, reason = j, tr.sl, "SL_FIRST"
                elif hit_sl:
                    exit_bar, exit_px, reason = j, tr.sl, "SL"
                elif hit_tp:
                    exit_bar, exit_px, reason = j, tr.tp, "TP"
                elif cl_ > inv:
                    exit_bar, exit_px, reason = j, cl_, "STRUCT"
            if exit_bar >= 0:
                break
        if exit_bar < 0:
            exit_bar, exit_px, reason = last, c[last], "TIME"

        gross = ((exit_px - entry) / r_usd) if branch.direction > 0 else ((entry - exit_px) / r_usd)
        tr.exit_bar, tr.exit_time, tr.exit = exit_bar, str(pd.Timestamp(t[exit_bar]))[:19], float(exit_px)
        tr.reason, tr.gross_r, tr.cost_r = reason, float(gross), float(cost_r)
        tr.net_r, tr.mae_r, tr.mfe_r = float(gross - cost_r), float(mae), float(mfe)
        tr.hold_bars = int(exit_bar - i)
        trades.append(tr)
        pos_until = exit_bar

    return RunResult(trades=trades, skipped=skipped, n_bars=n,
                     period=(str(pd.Timestamp(t[i0]))[:16], str(pd.Timestamp(t[min(i1, n - 1)]))[:16]),
                     structures_seen=structs_seen)
