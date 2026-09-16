"""ИСТОЧНИКИ ДАННЫХ И ВЕРСИОНИРОВАНИЕ (P0 ТЗ).

Статус источника указывается у каждого теста/отчёта/сделки:
  REAL_XAUUSD  — спот XAUUSD (пока НЕДОСТУПЕН в этой среде → честно помечаем отсутствие)
  PROXY_PAXG   — токенизированное золото Binance (research only)
  FUTURES_GC   — фьючерс COMEX GC=F (supplementary validation)
  MIXED        — смешано (запрещено для агрегированных метрик эффективности)

Версии: ENGINE / PARAMETER / DATA / REPORT вшиваются в отчёты и записи журнала.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FREEZE = ROOT / "PARAMETER_FREEZE_v2.md"

ENGINE_VERSION = "3.0"
REPORT_VERSION = "2.0"

SOURCES = {
    "REAL_XAUUSD": {"available": False, "note": "спот-фид недоступен в среде; требуется брокерский API или CSV"},
    "PROXY_PAXG": {"available": True, "note": "Binance PAXGUSDT; research/proxy only, не валидация XAUUSD"},
    "FUTURES_GC": {"available": True, "note": "COMEX GC=F; supplementary validation only"},
}

PROXY_WARNING = ("Results are based on proxy data and must not be interpreted as validated "
                 "XAUUSD performance.")


def parameter_version() -> str:
    if not FREEZE.exists():
        return "v2.3-nohash"
    return "v2.3-" + hashlib.sha256(FREEZE.read_bytes()).hexdigest()[:8]


def data_version() -> str:
    return "D" + time.strftime("%Y.%m.%d", time.gmtime())


def versions_block() -> str:
    return (f"ENGINE v{ENGINE_VERSION} · PARAMETERS {parameter_version()} · "
            f"DATA {data_version()} · REPORT v{REPORT_VERSION}")


def source_status(kind: str) -> str:
    """VALIDATION STATUS по типу источника."""
    if kind == "REAL_XAUUSD":
        return "VERIFIED"
    if kind in ("PROXY_PAXG", "FUTURES_GC"):
        return "PROXY" if kind == "PROXY_PAXG" else "NOT VERIFIED (futures, supplementary)"
    return "NOT VERIFIED"


def label(kind: str) -> str:
    return (f"**DATA SOURCE:** {kind} · **VALIDATION STATUS:** {source_status(kind)}"
            + (f" · ⚠ {PROXY_WARNING}" if kind == "PROXY_PAXG" else "")
            + (" · ⚠ REAL XAUUSD validation unavailable" if not SOURCES["REAL_XAUUSD"]["available"] else ""))


if __name__ == "__main__":
    print(versions_block())
    for k in SOURCES:
        print(label(k))
