"""Хеш замороженных правил: SHA-256 freeze-документа вшивается в шапки отчётов (C3 совета)."""
from __future__ import annotations

import hashlib
from pathlib import Path

FREEZE = Path(__file__).resolve().parent.parent / "PARAMETER_FREEZE_v2.md"


def freeze_hash() -> str:
    if not FREEZE.exists():
        return "no-freeze-file"
    return hashlib.sha256(FREEZE.read_bytes()).hexdigest()[:16]


if __name__ == "__main__":
    print(freeze_hash())
