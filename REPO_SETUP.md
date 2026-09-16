# Создание репозитория — готовые значения для копирования

Всё, что нужно вставить в форму GitHub при создании репозитория, и что заполнить после деплоя.

---

## 1. Форма «Create a new repository»

| Поле | Что вставить |
|---|---|
| **Owner** | ваш аккаунт или организация |
| **Repository name** | `xauusd-elliott-agent` |
| **Description** | см. вариант A или B ниже (вставлять одним из) |
| **Public** ✅ / Private ❌ | **Public** — иначе GitHub Pages бесплатно не работает |
| Add a README file | ❌ **не отмечать** (README приедет из моего push) |
| Add .gitignore | ❌ **не отмечать** (свой `.gitignore` уже в проекте) |
| Add a license | ❌ **не отмечать** — см. раздел 4 |

### Description — вариант A (английский, рекомендуется: GitHub-поиск и About лучше работают на EN)

```text
Structure-first Elliott Wave research agent for XAUUSD: causal (no look-ahead) wave labeler, mandatory gate pipeline G00–G15, frozen-parameter walk-forward backtester with a transaction-cost model, forward out-of-sample tracker and a self-contained live dashboard.
```

### Description — вариант B (короткий английский, если хочется лаконичнее)

```text
Causal Elliott Wave research agent for XAUUSD — gate pipeline G00–G15, frozen-parameter walk-forward backtester with cost model, forward OOS tracker, live dashboard.
```

### Description — вариант C (русский)

```text
Исследовательский торговый агент по XAUUSD на базе волн Эллиотта: причинная разметка без look-ahead, конвейер обязательных гейтов G00–G15, бэктестер с замороженными параметрами и моделью издержек, walk-forward и forward OOS-трекер, живой дашборд.
```

---

## 2. После создания — заполнить в «About» (шестерёнка справа на странице репозитория)

**Website** (вставить после того, как Pages опубликован):
```text
https://<OWNER>.github.io/xauusd-elliott-agent/
```

**Topics** (скопировать списком):
```text
elliott-wave  xauusd  gold  trading-system  quantitative-finance  backtesting
walk-forward  algorithmic-trading  technical-analysis  trading-dashboard
no-look-ahead  python  finance  research
```

**Include in the home page**: ✅ Releases ❌ Packages ❌ Deployments (по желанию).

---

## 3. Что попадёт в публичный репозиторий

| Категория | Файлы |
|---|---|
| Канон и правила | `MASTER_SPEC_v1.8.md`, `PARAMETER_FREEZE_v1/v2.md`, `INTAKE_AUDIT_v1.md`, `NEXT_CYCLE_PREREGISTRATION_v2.md` |
| Код | `engine/` (10 модулей), `run_experiment.py`, `walkforward.py`, `v2_validation.py`, `forward_collector.py`, `dashboard.py`, `build_site.py`, `build_single_file.py`, `serve.py`, `deploy.sh`, `deploy_github.py`, `tests/` |
| Отчёты | `reports/EXPERIMENT_v2.md`, `EXPERIMENT_v3.md`, `WALKFORWARD_v2.md`, `results_*.json`, `causality.json` |
| Логи сделок | `reports/trades_*.csv` (243 + 163 + 141 + 57 сделок), `data/forward/forward_signals.csv` |
| Сайт | `site/` (12 страниц), `site_single.html` |
| **НЕ попадает** | `журнал.md` (вне папки репозитория), `docs/journal.html` (исключён PUBLIC-режимом), сырые датасеты `data/paxg_*.csv`, `data/gcf_*.csv`, `data/forward_sandbox/`, `dashboard/preview_sandbox.html`, `__pycache__`, `.bin` |

Объём: ~3.4 МБ.

---

## 4. Лицензия — решение за вами

* **Без лицензии** (рекомендую по умолчанию): код и методология видны всем, но юридически
  никто не вправе их копировать и использовать. Ровно то, что нужно, если цель — показать
  работу, а не открыть методику.
* **MIT / Apache-2.0**: любой может свободно использовать, в том числе коммерчески.
  Выбирайте, только если сознательно хотите open source.
* **CC BY-NC-SA 4.0**: компромисс для документов/исследований — можно делиться, нельзя
  в коммерцию, производные — под той же лицензией.

После публикации можно добавить файл `LICENSE` отдельным коммитом — я сделаю, если скажете какой.

---

## 5. Дисклеймер, который уже есть в README репозитория

> Проект носит исследовательский характер. Результаты получены на исторических данных
> (частично на прокси-инструменте PAXGUSDT), содержат объявленный selection bias и
> **не являются инвестиционной рекомендацией**. Торговля с плечом ведёт к потере капитала.

---

## 6. Что прислать мне для деплоя

```text
1) owner/repo        : например ivanov/xauusd-elliott-agent
2) fine-grained PAT  : Contents R/W + Pages R/W (+ Actions read, + Administration R/W если репозиторий создаю я)
3) срок токена       : 1–7 дней, отозвать сразу после деплоя
```

Команда, которую я выполню:
```bash
export GH_TOKEN=<ваш токен>
python3 deploy_github.py --owner <OWNER> --repo xauusd-elliott-agent
# или с созданием репозитория:  ... --create
```
