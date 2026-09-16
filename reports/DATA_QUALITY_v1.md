# DATA QUALITY v1 — аудит источников

ENGINE v3.0 · PARAMETERS v2.3-560dbb72 · DATA D2026.09.16 · REPORT v2.0

**DATA SOURCE:** PROXY_PAXG · **VALIDATION STATUS:** PROXY · ⚠ Results are based on proxy data and must not be interpreted as validated XAUUSD performance. · ⚠ REAL XAUUSD validation unavailable

**DATA SOURCE:** FUTURES_GC · **VALIDATION STATUS:** NOT VERIFIED (futures, supplementary) · ⚠ REAL XAUUSD validation unavailable

⚠ Results are based on proxy data and must not be interpreted as validated XAUUSD performance.

**REAL XAUUSD validation unavailable** — спот-источник в среде отсутствует; все performance-метрики проекта помечены как PROXY до его подключения.

## 1. Аудит наборов

| Источник | ТФ | Баров | Период (UTC) | Дубли | Гэпы | Макс гэп, ч | Некорректный OHLC | Weekend-бары | Макс ход, ATR | Скачков >8 ATR |
|---|---|---|---|---|---|---|---|---|---|---|
| PROXY_PAXG | M15 | 116,330 | 2022-01-24 00:00 → 2026-09-15 19:30 | 0 | 243 | 48.2 | 0 | 0 | 11.8 | 26 |
| PROXY_PAXG | H1 | 35,698 | 2021-01-01 00:00 → 2026-09-15 19:00 | 0 | 303 | 49.0 | 0 | 0 | 9.0 | 3 |
| FUTURES_GC | M15 | 3,745 | 2026-07-19 22:00 → 2026-09-15 19:20 | 0 | 40 | 79.2 | 0 | 64 | 8.0 | 0 |
| FUTURES_GC | H1 | 11,279 | 2024-09-25 19:00 → 2026-09-15 19:20 | 0 | 507 | 80.0 | 0 | 158 | 6.9 | 0 |
| FUTURES_GC | D1 | 6,535 | 2000-08-30 04:00 → 2026-09-15 04:00 | 0 | 1434 | 120.0 | 441 | 0 | 8.1 | 1 |

## 2. Допущения по спредам и издержкам

- **PROXY_PAXG:** биржевой стакан Binance, спред ≈ 0.01–0.05 USD; в моделях консервативно 0.40–0.60 USD
- **FUTURES_GC:** спред фьючерса не моделируется (данные OHLC); издержки те же 0.52 USD round-trip
- **REAL_XAUUSD:** недоступен; при подключении — живой спред брокера

## 3. Сравнение PAXG ↔ GC=F (overlap по дневным закрытиям)

- дней в overlap: 506
- корреляция дневных доходностей: **0.9684**
- базис PAXG−GC: медиана -11.64 USD, средний |базис| 19.70 USD, макс |базис| 143.05 USD
- шум базиса (|базис − медиана|): средний 16.92 USD

Вывод: PAXG и GC=F движутся почти синхронно по доходностям, но базис шумный → PAXG пригоден как proxy для структуры и исследования, **не** как подтверждение XAUUSD.

## 4. Статус источников

| Источник | Доступен | Роль | Validation status |
|---|---|---|---|
| REAL_XAUUSD | ❌ нет | основной при подключении | VERIFIED (после подключения) |
| PROXY_PAXG | ✅ | research / proxy only | PROXY |
| FUTURES_GC | ✅ | supplementary validation | NOT VERIFIED |

Правило: статистика разных источников **не смешивается** в одном агрегированном показателе; каждая таблица эффективности помечена своим источником.
