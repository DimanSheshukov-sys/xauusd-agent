# LEARNING v1 — классификация ошибок и калибровка (§63–66)

Сформировано: 2026-09-16 10:19 UTC • freeze SHA-256: `560dbb724b744c11` • Правила НЕ изменяются: все кандидаты pre-registered и ждут нового validation cycle.

## research v2 (G_BASE47, PROXY)

- сделок: **163** • WR 60.1% • PF 1.373 • Exp +0.1562R • Net +25.5R
- MAE среднее -0.783R • MFE среднее 0.978R
- tier калибровки (§63): **50+ → FULL CALIBRATION**

| Класс ошибки (§66) | Кол-во |
|---|---|
| WIN | 89 |
| REGIME ERROR: шум против позиции | 44 |
| TRIGGER ERROR: вход против движения | 20 |
| WIN-RUNNER-CANDIDATE | 9 |
| EXECUTION ERROR: TP недосягаем / вход поздний | 1 |

## research v2 (G_PROD, PROXY)

- сделок: **243** • WR 41.6% • PF 0.876 • Exp -0.0818R • Net -19.9R
- MAE среднее -1.136R • MFE среднее 1.299R
- tier калибровки (§63): **50+ → FULL CALIBRATION**

| Класс ошибки (§66) | Кол-во |
|---|---|
| WIN-RUNNER-CANDIDATE | 101 |
| REGIME ERROR: шум против позиции | 70 |
| TRIGGER ERROR: вход против движения | 51 |
| EXECUTION ERROR: TP недосягаем / вход поздний | 21 |

## walk-forward OOS

- сделок: **57** • WR 64.9% • PF 1.813 • Exp +0.3160R • Net +18.0R
- MAE среднее -0.821R • MFE среднее 1.345R
- tier калибровки (§63): **50+ → FULL CALIBRATION**

| Класс ошибки (§66) | Кол-во |
|---|---|
| WIN | 23 |
| WIN-RUNNER-CANDIDATE | 14 |
| REGIME ERROR: шум против позиции | 11 |
| TRIGGER ERROR: вход против движения | 7 |
| EXECUTION ERROR: TP недосягаем / вход поздний | 2 |

## forward OOS (реальное золото)

_файл отсутствует_

## Сводные классы ошибок

| Класс | Всего |
|---|---|
| REGIME ERROR: шум против позиции | 125 |
| WIN-RUNNER-CANDIDATE | 124 |
| WIN | 112 |
| TRIGGER ERROR: вход против движения | 78 |
| EXECUTION ERROR: TP недосягаем / вход поздний | 24 |

## Pre-registered кандидаты (НЕ применены)

| ID | Изменение | Статус |
|---|---|---|
| H-TP | уменьшить TP до 0.8R ИЛИ ужесточить trigger до Donchian(6) | НЕ применено: walk-forward 365/90 на новом окне + costs (§65) |
| H-TRIG | подтверждение входа: close > EMA20(M15) на сигнальном баре | НЕ применено: pre-registration + отдельный OOS (§68–69) |
| H-VOL | фильтр волатильности: ATR(M15) ≤ 75-го перцентиля за 200 баров | НЕ применено: ablation → walk-forward → OOS (§68) |
| H-RUN | исследовать runner-ветку: trailed stop после +1R | НЕ применено: отдельная frozen branch, не трогая текущую (§25) |

## Протокол следующего шага (§65)

1. OBSERVATION — этот отчёт;
2. ERROR CLASSIFICATION — таблица выше;
3. HYPOTHESIS — кандидаты выше;
4. PRE-REGISTERED RULE — зафиксировать в `PARAMETER_FREEZE_vN` до прогона;
5. BACKTEST → VALIDATION → OOS на данных, которых не было в этом отчёте;
6. ACCEPT / REJECT / NEEDS MORE DATA.

**Запрещено:** менять правила по итогам этого отчёта (§64); калибровать по Final OOS; менять stop/target задним числом (§70).
