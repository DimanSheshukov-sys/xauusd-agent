"""§43 NEWS / EVENT FILTER — причинный фильтр high-impact событий.

Правило (заморожено): НОВЫЕ входы запрещены, если бар сигнала попадает в окно
[event − PRE_H, event + POST_H]. Позиции, уже открытые до окна, не трогаются
(фильтр относится к entry, а не к exit).

Источники:
  • FOMC decision day — официальный календарь federalreserve.gov (публикуется за год
    вперёд → на момент сделки расписание было известно, look-ahead отсутствует).
    Заявление выходит в 14:00 America/New_York.
  • NFP (BLS Employment Situation) — первый четверг/пятница месяца, 08:30 America/New_York
    (детерминированное правило, внешний источник не нужен).
  • CPI НЕ покрыт (нет надёжного исторического календаря без внешнего API) — ограничение v2.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRE_H = 2.0
POST_H = 2.0
NY = "America/New_York"

# Decision days (2-й день заседания). Источник: federalreserve.gov/monetarypolicy/fomccalendars.htm
# (доступ 2026-09-16). 2026 подтверждён со страницы; 2022–2025 — опубликованное расписание.
FOMC = [
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def event_times(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Все события (UTC) в диапазоне."""
    rows = []
    for d in FOMC:
        t = pd.Timestamp(f"{d} 14:00", tz=NY).tz_convert("UTC")
        if start <= t <= end:
            rows.append({"event": "FOMC", "time": t})
    # NFP: первая пятница месяца, 08:30 NY
    for m in pd.period_range(start.tz_localize(None), end.tz_localize(None), freq="M"):
        days = pd.date_range(m.start_time, m.end_time, freq="D")
        fridays = days[days.dayofweek == 4]
        if len(fridays):
            t = pd.Timestamp(f"{fridays[0].date()} 08:30", tz=NY).tz_convert("UTC")
            if start <= t <= end:
                rows.append({"event": "NFP", "time": t})
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True) if rows else \
        pd.DataFrame(columns=["event", "time"])


def blocked_mask(times: np.ndarray, pre_h: float = PRE_H, post_h: float = POST_H) -> tuple[np.ndarray, pd.DataFrame]:
    """Булева маска: True = бар попадает в event-окно (вход запрещён)."""
    t = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    ev = event_times(t[0], t[-1])
    mask = np.zeros(len(t), dtype=bool)
    for _, r in ev.iterrows():
        lo = r["time"] - pd.Timedelta(hours=pre_h)
        hi = r["time"] + pd.Timedelta(hours=post_h)
        mask |= (t >= lo) & (t <= hi)
    return mask, ev


if __name__ == "__main__":
    t = pd.date_range("2022-01-24", "2026-09-16", freq="15min", tz="UTC").to_numpy()
    m, ev = blocked_mask(t)
    print(f"баров {len(t):,} • событий {len(ev)} • заблокировано {m.sum():,} баров ({m.mean()*100:.2f}%)")
    print(ev.head(8).to_string())
    print("...")
    print(ev.tail(4).to_string())
