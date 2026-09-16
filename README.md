# XAUUSD Elliott Trading Agent

**Structure-first исследовательский торговый агент по XAUUSD на волнах Эллиотта**: причинная разметка
волн без look-ahead, конвейер обязательных гейтов G00–G15, бэктестер с замороженными параметрами и
моделью издержек, walk-forward и forward out-of-sample трекер, живой дашборд.

`spec v1.8` · `parameter freeze v2` · `engine v2` · **status: P2 (walk-forward validated, PROXY data)** · `G01 causality: PASS`

| | |
|---|---|
| 📊 **Дашборд** | `dashboard/index.html` (или `site/index.html` после сборки, `site_single.html` — всё в одном файле) |
| 🔴 **LIVE** | `site/live.html` — реальное время в браузере: свечи Binance (CORS) + спот gold-api, живой график, гейты, прогноз-сценарии |
| 🧪 **Результаты** | [`reports/EXPERIMENT_v3.md`](reports/EXPERIMENT_v3.md) · [`reports/WALKFORWARD_v2.md`](reports/WALKFORWARD_v2.md) · [`reports/EXPERIMENT_v2.md`](reports/EXPERIMENT_v2.md) |
| 📜 **Правила** | [`MASTER_SPEC_v1.8.md`](MASTER_SPEC_v1.8.md) (канон) · [`PARAMETER_FREEZE_v2.md`](PARAMETER_FREEZE_v2.md) (замороженные параметры) |
| 🔍 **Методология** | [`INTAKE_AUDIT_v1.md`](INTAKE_AUDIT_v1.md) · [`NEXT_CYCLE_PREREGISTRATION_v2.md`](NEXT_CYCLE_PREREGISTRATION_v2.md) · [`REPO_SETUP.md`](REPO_SETUP.md) |
| 🚀 **Запуск** | `python3 serve.py` → http://localhost:8000 · деплой — [`DEPLOY.md`](DEPLOY.md) |

## Главный результат

Кандидат v2 = `LONG_ONLY (B04→B01→B02)` + геометрия `2.5 ATR / 1.0R / 96 баров` + news-фильтр FOMC/NFP + издержки 0.52 USD:

| N | Win rate | PF net | Expectancy | Net R | MaxDD | p-value | N для 95% |
|---|---|---|---|---|---|---|---|
| 141 | 63.1% | 1.573 | **+0.2204R** | **+31.07R** | −9.93R | **0.007** | 74 ✅ |

Walk-forward с отбором внутри train-окна (14 фолдов): статичная конфигурация — N=122, Exp +0.205R, Net +25.0R, p=0.020.
Адаптивный отбор дал больший Exp на сделку, но меньший суммарный R → **запрещён** (подтверждает вывод §48 канона).

**Не воспроизведено из канона независимо:** SHORT-ветки (PF 0.706 против заявленных 2.25) и приоритет W3 CLASS A
(PF 0.947 против 2.217) → понижены до P0 / CONTEXT_ONLY.

> ⚠️ **Дисклеймер.** Исследовательский проект. Результаты получены на исторических данных, частично на
> прокси-инструменте PAXGUSDT (не спот XAUUSD), правила v2 сформированы по итогам того же периода —
> selection bias объявлен явно. **Не является инвестиционной рекомендацией.**

---

## Устройство проекта

Реализация канона `MASTER_SPEC_v1.8.md` с нуля (прежний код и датасет в эту среду не передавались).
Действующая версия параметров: **`PARAMETER_FREEZE_v2.md`** (v1 сохранён как история).

## Структура

```text
xauusd_agent/
├── MASTER_SPEC_v1.8.md               ← канон (дословно, read-only)
├── INTAKE_AUDIT_v1.md                ← аудит: данные, расхождение §47 vs §25, 30 gap-параметров
├── PARAMETER_FREEZE_v1.md            ← первый freeze (pre-registered до прогона)
├── PARAMETER_FREEZE_v2.md            ← ДЕЙСТВУЮЩИЙ freeze: 12 решений + forward OOS протокол
├── NEXT_CYCLE_PREREGISTRATION_v2.md  ← гипотезы H1–H6 (реализованы в v2)
├── live_analysis.py                  ← §72 decision template по живому рынку (конфигурация v2)
├── run_experiment.py                 ← end-to-end прогон (§44) → reports/EXPERIMENT_v2.md
├── walkforward.py                    ← WF §45/§46 с отбором внутри train → reports/WALKFORWARD_v2.md
├── v2_validation.py                  ← кандидат v2, абляции, валидация прокси → reports/EXPERIMENT_v3.md
├── engine/
│   ├── data.py                       ← G00: загрузка, кэш, аудит целостности
│   ├── indicators.py                 ← причинные EMA/ATR/RSI/Donchian + MTF по закрытым барам
│   ├── swings.py                     ← causal ZigZag с confirm_idx (watermark причинности)
│   ├── elliott.py                    ← W1–W5, W3 class, ABC, invalidation
│   ├── branches.py                   ← реестр B01–B08, геометрии, приоритет (frozen)
│   ├── events.py                     ← §43 news filter: FOMC + NFP ±2h
│   ├── wyckoff.py                    ← Wyckoff-флаг (CONTEXT ONLY, §19)
│   ├── analyze.py                    ← единая функция анализа рынка (CLI + дашборд)
│   ├── backtest.py                   ← gates G00–G15, execution, costs, SL-first
│   └── metrics.py                    ← §54 метрики, §62 rolling, §60 sample sufficiency
├── tests/test_causality.py           ← G01: T1 truncation, T2 future perturbation, T3 watermark → PASS
├── data/                             ← кэш датасетов (+ data/forward/ — накопление forward OOS)
├── data/forward/                     ← forward OOS: бары GC=F, журнал сигналов (append-only), лог запусков
├── data/forward_sandbox/             ← то же для sandbox-проверок
└── reports/                          ← EXPERIMENT_v2/v3.md, WALKFORWARD_v2.md, trades_*.csv, *.json
```

## Запуск

```bash
pip install numpy pandas websocket-client

python3 engine/data.py              # G00: скачать и проаудировать датасеты
python3 tests/test_causality.py 8   # G01: доказательство отсутствия look-ahead
python3 run_experiment.py           # §44 end-to-end: матрица конфигураций
python3 walkforward.py              # §45/§46 walk-forward с отбором внутри train
python3 v2_validation.py            # кандидат v2 + абляции + валидация прокси
python3 live_analysis.py            # §72: решение по текущему рынку (конфигурация v2)
python3 forward_collector.py        # forward OOS: дописать бары GC+F + вердикт + АВТОСБОРКА дашборда
python3 dashboard.py                # пересобрать дашборд вручную (если нужно без коллектора)

# САЙТ И ССЫЛКА
./deploy.sh serve                   # локально → http://localhost:8000 (живой API)
./deploy.sh tunnel                  # ПУБЛИЧНАЯ ссылка без аккаунта (cloudflared quick tunnel)
./deploy.sh pages git@github.com:USER/REPO.git   # постоянная ссылка на GitHub Pages + автообновление
./deploy.sh netlify  |  ./deploy.sh vercel       # приватный репозиторий допустим
./deploy.sh single                  # один файл site_single.html — открыть/отправить куда угодно
python3 build_site.py               # только пересобрать site/
python3 build_single_file.py        # только пересобрать site_single.html

# песочница (проверка forward-контура на истории, боевой журнал не трогает):
python3 forward_collector.py --sandbox --epoch=2026-08-01   # → dashboard/preview_sandbox.html
python3 forward_collector.py --no-dashboard                 # только сбор данных
```

## Конфигурация v2 (заморожена)

```text
BRANCHES   LONG_ONLY: B04 (ExtW3+RSI) → B01 (Fib ON) → B02 (EMA200+Fib OFF)
DISABLED   B05/B06/B07 (SHORT) — Exp −0.174R, N=20;  B03 (W3 CLASS A) — CONTEXT_ONLY
GEOMETRY   G_BASE47: SL 2.5 ATR(14,M15) • TP 1.0R • max hold 96 баров • entry open[i+1] • SL FIRST
REGIME     D1 close > D1 EMA200 (последний закрытый бар) — REQUIRED для LONG
TRIGGER    причинный Donchian(8) breakout на M15
INVALID    close < L4; SL-совместимость `tight` (SL ≥ L4), иначе WAIT_RISK
EVENTS     вход запрещён в FOMC/NFP ± 2h (§43)
COSTS      0.40 спред + 0.06 комиссия/сторону; gate G14a: cost/R ≤ 0.05
SWING      causal ZigZag, K = 2.0 × ATR(14,M15), min_bars отключён
CONTEXT    Wyckoff-флаг, W3 CLASS A, DXY/macro — только контекст, не gate
```

## Результаты

**Кандидат v2, research sample 2022-01-24 → 2026-09-15 (PAXG PROXY, costs REAL):**

| N | WR | PF net | Exp net | Net R | MaxDD | t / p | N для 95% |
|---|---|---|---|---|---|---|---|
| 141 | 63.1% | 1.573 | **+0.2204R** | **+31.07R** | −9.93R | 2.70 / **0.007** | 74 ✅ |

**Walk-forward OOS (отбор внутри train, 14 фолдов):** статичный `LONG_ONLY + G_BASE47` — N=122, Exp +0.205R, Net +25.0R, p=0.020. Адаптивный отбор дал больший Exp (+0.316R), но меньший Net R (+18.0R) → **адаптивность запрещена** (подтверждает §48 «FROZEN > ADAPTIVE»).

**Сравнение геометрий (§47 vs §25/§82), costs REAL:**

| Геометрия | N | PF net | Exp net | Net R | p | Вердикт |
|---|---|---|---|---|---|---|
| §25/§82 `1 ATR / 1.5R` | 243 | 0.876 | −0.082R | −19.9R | 0.306 | ❌ убита издержками (cost/R = 0.07) |
| §47 `2.5 ATR / 1.0R` | 163 | 1.373 | +0.156R | +25.5R | 0.043 | ✅ 11/11 критериев §60 |

**Не воспроизведено из канона:** SHORT-ветки (§16 PF 2.25 → 0.706; §48 → 0.456) и приоритет W3 CLASS A (§9 PF 2.217 → 0.947). **Воспроизведено:** направление §14 (EMA200 + Fib OFF LONG) на выборке в 5,5 раза больше канонной.

**Валидация прокси:** PAXG vs GC=F — корреляция доходностей 0.9614 (M15) / 0.9288 (H1), но **шум базиса 16.2 USD = 1.98 × ATR(M15)** и совпадение сигналов **2 из 9**. Вывод: PAXG — directional/robustness стенд, **не** замена споту для structural-валидации.

## Статусы (§57)

| Компонент | Статус |
|---|---|
| LONG_ONLY + G_BASE47 (кандидат v2) | **P2** walk-forward validated (на PROXY-данных) |
| Full State Machine | **P2** — end-to-end пройден, G01 CAUSALITY = PASS |
| B04 ExtW3+RSI | P1 |
| Wyckoff flag | P1 contextual (реализован, gate запрещён) |
| §25/§82 geometry `1 ATR / 1.5R` | понижена до P1 |
| SHORT B05–B07 | **P0 DISABLED** |
| W3 CLASS A high-conviction (§13) | **P0 → CONTEXT_ONLY** |
| Schiff / ABC / Failed Fifth | P0 (не реализовано / не торгуется) |

**Для P3 → P4:** forward OOS после 2026-09-15 20:00 UTC (N ≥ 74, Exp > 0, p < 0.10, rolling ≥ 60%, MaxDD ≤ 15R) **и** спот XAUUSD M15 вместо прокси. Протокол — в `PARAMETER_FREEZE_v2.md` §4.

## Дашборд

`dashboard/index.html` — self-contained (инлайн CSS/SVG, без внешних зависимостей), 18 панелей:
живая цена и спред TV • DXY • MTF-режим D1/H4/H1 • решение §72 с причинами • gate-конвейер G00→G15 •
Elliott-структура с пивотами и волнами • M15-график с invalidation • event-риск FOMC/NFP •
метрики кандидата v2 + equity/drawdown • year-by-year • rolling §62 • walk-forward по фолдам •
матрица геометрий × издержки • реестр веток • валидация прокси • causality T1/T2/T3 •
**forward OOS трекер + append-only журнал замороженных сигналов + история запусков** • виджет TradingView.

Автообновление: каждый запуск `forward_collector.py` пересобирает дашборд.
Журнал сигналов `data/forward/forward_signals.csv` — **append-only**: entry/SL/TP/R/invalidation/branch
заморожены в момент выдачи (S18, RULE 13) и никогда не перезаписываются; обновляются только поля исхода,
а расхождение замороженных полей поднимает INTEGRITY WARNING на дашборде.

## Волны по таймфреймам (степени, freeze v2.2)

Система размечает волны на **H4 ⊃ M15 ⊃ M5 ⊃ M1**: каждая степень — своим причинным ZigZag
(K = 2.0 × ATR своего ТФ), поэтому на мелких ТФ автоматически получаются мелкие субволны внутри волны
крупного. Цепочка вложенности (например `H4:W3↑ ⊃ M15:W4↑ ⊃ M5:W2↓ ⊃ M1:W5↑`) и согласованность
степеней показываются на LIVE-странице; по каждой степени — свой invalidation и W3 class.
Согласованность — контекст, не сигнал: торговые правила канона (execution M15, SL 2.5 ATR / TP 1.0R) не изменены;
кандидат H-MTF-ALIGN зафиксирован для будущей валидации.

## Время, прогнозы, сделки, обучение

* **Все времена на live-странице — Екатеринбург (UTC+5)** (в данных и журналах хранится UTC).
* **Прогноз** = сценарий §37 с триггером, entry, **STOP-LOSS (2.5 ATR)** и **TAKE-PROFIT (1.0R)**, R:R,
  invalidation и fib-целью W5; расстояния до уровней в USD показываются живьём.
* **Закрытие сделок**: live paper-позиция закрывается по TP / SL (SL FIRST при совпадении в баре, §28) /
  structural invalidation (§11) / max hold 96 / вручную (MANUAL — вне статистики правил).
  Журнал append-only (RULE 13), экспорт CSV, live P&L в R и USD. Тесты логики: 21/21 PASS.
* **Калибровка и обучение (§63–66)**: `learn.py` строит `reports/LEARNING_v1.md` — классы ошибок §66,
  tier калибровки §63, pre-registered кандидаты; **правила никогда не меняются автоматически** (§64–65).
  Панель «Обучение и калибровка» на live-странице показывает то же по paper-журналу.

## LIVE-режим (реальное время без сервера)

`live.html` работает целиком в браузере: каждые 10 секунд тянет PAXGUSDT M15/H1/D1 с Binance
(`Access-Control-Allow-Origin: *`) и спот XAU с gold-api.com, прогоняет JS-порт причинного движка
(`web/live_engine.js`, кросс-валидирован с Python-движком до совпадения всех чисел) и рисует:
живой график M15 со свечами, причинными пивотами и волнами W1–W4; уровни trigger/SL/TP/invalidation/W5-fib;
решение по §72 с причинами; гейт-чипы G00–G15; countdown до FOMC/NFP с блокировкой входов по §43;
статус forward OOS. На статическом хостинге сервер не нужен вообще.

## Сайт

`site/` — статический self-contained сайт (692 КБ, 13 страниц): дашборд + все отчёты + канон +
freeze + аудит + pre-registration + README + журнал + CSV-логи. Навигация сверху на всех страницах.

`serve.py` (только stdlib) отдаёт сайт и добавляет живое:
`/api/live` (цена, спред, DXY, MTF, структура, решение §72 — кэш 60 c), `/api/status`
(forward OOS, датасеты, версии), `/api/refresh` (пересборка), `/healthz`. Фронт дашборда опрашивает
`/api/live` каждые 20 c и обновляет KPI и решение без перезагрузки; при открытии файла
(`file://`) опрос молча отключается — страница остаётся полноценным снимком.

Варианты деплоя и systemd/nginx-конфиги — в `DEPLOY.md`. Автопубликация на GitHub Pages —
`.github/workflows/site.yml` (cron 06:30 и 20:30 UTC).

## Ограничения

1. **PROXY-данные** (PAXGUSDT): спот XAUUSD M15 из этой среды недоступен (Dukascopy 503, Yahoo M15 = 60 дней).
2. Правила v2 сформированы по итогам прогона на 2022–2026 → все цифры на этом периоде **in-sample-оптимистичны** (selection bias объявлен явно).
3. News filter покрывает FOMC + NFP, **без CPI**.
4. Один wave degree; альтернативные counts (§37) не формализованы; swaps не моделируются.
5. Всё опубликовано полностью, лучшая конфигурация не «выбиралась задним числом» (§70) — кроме явно помеченного выбора кандидата v2.

Ничего из посчитанного не является инвестиционной рекомендацией.
