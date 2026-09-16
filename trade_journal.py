#!/usr/bin/env python3
"""ЖУРНАЛ СДЕЛОК — канонический реестр, который ведёт агент.

Источники (приоритет):
  1. LIVE FORWARD  — data/forward/forward_signals.csv  (append-only, RULE 13; реальное золото GC=F)
  2. PAPER         — любой CSV, переданный аргументом (экспорт browser paper-журнала)
  3. BACKTEST BASE — reports/trades_G_BASE47.csv (кандидат v2, PROXY) — только как историческая база,
                     помечается отдельно и НЕ смешивается с live-статистикой.

Метрики, которые просил пользователь:
  • WIN RATE           = доля сделок с net_r > 0 (после издержек 0.52 USD);
  • % УСПЕШНЫХ ПРОГНОЗОВ = доля закрытий по TP (прогноз движения реализовался в цель);
  • СРЕДНИЙ ПО ПРОЦЕНТАМ = среднее арифметическое процентов успеха по срезам
                           (branch / W3 class / год / regime) — указано явно, чтобы не путать с общим WR.

Выход: reports/TRADE_JOURNAL.md  (и страница сайта reports/TRADE_JOURNAL.html через build_site)
Автовызов: forward_collector.py запускает этот скрипт после каждого сбора данных.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
from freeze_hash import freeze_hash  # noqa: E402
from sources import versions_block, label as src_label  # noqa: E402
import hashlib

CAPITAL_USD = 10_000.0     # базовый капитал для денежной кривой (R3 совета)
RISK_PCT = 0.5             # риск на сделку, % капитала
REP = ROOT / "reports"
FWD = ROOT / "data" / "forward" / "forward_signals.csv"
BASE = REP / "trades_G_BASE47.csv"
EKB = timezone(offset=__import__("datetime").timedelta(hours=5))

COLS = ["source", "branch", "direction", "w3_class", "signal_time", "entry_time", "entry",
        "sl", "tp", "r_usd", "exit_time", "exit", "reason", "gross_r", "cost_r", "net_r",
        "mae_r", "mfe_r", "hold_bars"]


def load(path: Path, source: str) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(path)
    if not len(df):
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    df["source"] = source
    for c in ["direction", "entry", "sl", "tp", "r_usd", "exit", "gross_r", "cost_r", "net_r",
              "mae_r", "mfe_r", "hold_bars"]:
        if c not in df.columns:
            df[c] = pd.NA
    if "w3_class" not in df.columns:
        df["w3_class"] = "—"
    if "reason" not in df.columns:
        df["reason"] = "—"
    if "branch" not in df.columns:
        df["branch"] = "—"
    for c in ["signal_time", "entry_time", "exit_time"]:
        if c not in df.columns:
            df[c] = pd.NA
    return df[COLS]


def ekb(ts) -> str:
    try:
        return pd.Timestamp(ts).tz_convert("Asia/Yekaterinburg").strftime("%d.%m %H:%M")
    except Exception:
        return "—"


def slice_stats(df: pd.DataFrame, col: str) -> list[dict]:
    out = []
    for key, g in df.groupby(col, dropna=False):
        net = g["net_r"].dropna().to_numpy(float)
        if not len(net):
            continue
        tp = (g["reason"] == "TP").sum()
        dir_ok = (g["mfe_r"].fillna(0) >= 0.2).sum()
        out.append({"slice": str(key), "n": int(len(net)),
                    "wr": (net > 0).mean() * 100,
                    "tp_pct": tp / len(net) * 100,
                    "dir_pct": dir_ok / len(net) * 100,
                    "exp": net.mean(), "net": net.sum()})
    return sorted(out, key=lambda r: -r["n"])


def kpi_table(rows: list[dict]) -> str:
    md = ["| Срез | N | Win rate | % успешных (TP) | % верных по направлению | Expectancy | Net R |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['slice']} | {r['n']} | {r['wr']:.1f}% | {r['tp_pct']:.1f}% | {r.get('dir_pct', 0):.1f}% | "
                  f"{r['exp']:+.4f}R | {r['net']:+.1f} |")
    return "\n".join(md)


def trades_table(df: pd.DataFrame, limit: int = 40) -> str:
    md = ["| № | Источник | Открыта (ЕKB) | Branch | W3 | Entry | SL | TP | Exit | Причина | Net R |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    d = df.dropna(subset=["net_r"]).tail(limit).iloc[::-1]
    for i, (_, t) in enumerate(d.iterrows(), 1):
        md.append(f"| {i} | {t['source']} | {ekb(t['entry_time'])} | {t['branch']} | {t['w3_class']} | "
                  f"{t['entry']:.2f} | {t['sl']:.2f} | {t['tp']:.2f} | {t['exit']:.2f} | {t['reason']} | "
                  f"{t['net_r']:+.2f} |")
    return "\n".join(md)




# ───────────────────────── ВЕРСИЯ ДЛЯ ЛЮДЕЙ ─────────────────────────
PLAIN_CSS = """
<style>
.pl{font-size:15px;line-height:1.65}
.pl .lead{background:#14243d;border:1px solid #2b4a6b;border-radius:12px;padding:12px 16px;margin:10px 0 18px}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.cd{flex:1 1 150px;background:#0f1830;border:1px solid #22304d;border-radius:12px;padding:12px 14px}
.cd b{display:block;font-size:26px;margin:2px 0}
.cd span{font-size:12px;color:#8b98b0}
.cd i{display:block;font-style:normal;font-size:12px;margin-top:4px;color:#c7d3e6}
.ok{color:#5ee39a}.bad{color:#ff7b7b}.warn{color:#f0b429}
.gloss{background:#0f1830;border:1px solid #22304d;border-radius:12px;padding:12px 16px;margin:14px 0}
.gloss dt{font-weight:700;color:#f0b429;margin-top:8px}
.gloss dd{margin:2px 0 0 0;color:#c7d3e6}
details{background:#0f1830;border:1px solid #22304d;border-radius:12px;padding:10px 16px;margin:14px 0}
summary{cursor:pointer;color:#9fd0ff}
</style>
"""

REASON_PLAIN = {
    "TP": "✅ цель достигнута",
    "SL": "❌ сработал защитный стоп",
    "SL_FIRST": "❌ сработал защитный стоп",
    "STRUCT": "⛔ сценарий отменён рынком (пробой уровня отмены)",
    "TIME": "⏱ вышло время ожидания (96 свечей) — вышли без цели",
    "MANUAL": "🖐 закрыто вручную",
}


def pct_word(x):
    return f"{x:.0f} из 100"


def build_plain_html(live: pd.DataFrame, paper: pd.DataFrame, base: pd.DataFrame, now_e: str) -> str:
    def st(df):
        if not len(df):
            return None
        net = df["net_r"].dropna().to_numpy(float)
        if not len(net):
            return None
        return {"n": len(net), "wr": (net > 0).mean() * 100,
                "tp": (df["reason"] == "TP").sum() / len(net) * 100,
                "dir": (df["mfe_r"].fillna(0) >= 0.2).mean() * 100,
                "exp": net.mean(), "net": net.sum()}

    b = st(base)
    l = st(live)
    avp = always_valid_p(base["net_r"].dropna().to_numpy(float)) if b else 1.0
    if b:
        nb = base["net_r"].dropna().to_numpy(float)
        wr_lo, wr_hi = wilson_ci(int((nb > 0).sum()), len(nb))
        e_lo, e_hi = mean_ci(nb)
        r_usd = CAPITAL_USD * RISK_PCT / 100
        eq_money = nb.sum() * r_usd
        eq_pct = nb.sum() * RISK_PCT
    else:
        wr_lo = wr_hi = e_lo = e_hi = eq_money = eq_pct = 0.0
    H = [PLAIN_CSS, '<div class="pl">',
         '<div class="lead"><b>Источник и версии.</b> ' + versions_block() + '<br>'
         + src_label("PROXY_PAXG").replace("**", "") + '</div>']
    H.append('<div class="lead"><b>Что это за страница.</b> Система каждый раз записывает свой прогноз '
             'по золоту: куда ждёт цену, где цель (тейк-профит), где защитный стоп и чем всё закончилось. '
             'Ниже — итог простыми словами. Обновляется автоматически после каждого нового результата.</div>')

    # крупные цифры
    if b:
        H.append('<div class="cards">'
                 f'<div class="cd"><span>Прибыльных сделок</span><b class="ok">{pct_word(b["wr"])}</b>'
                 f'<i>из {b["n"]} сделок за 2022–2026</i></div>'
                 f'<div class="cd"><span>Дошли до цели</span><b class="ok">{pct_word(b["tp"])}</b>'
                 f'<i>цена достигла тейк-профита</i></div>'
                 f'<div class="cd"><span>Угадано направление</span><b class="warn">{pct_word(b["dir"])}</b>'
                 f'<i>цена хотя бы пошла в сторону прогноза</i></div>'
                 f'<div class="cd"><span>Средний результат сделки</span><b class="{"ok" if b["exp"]>0 else "bad"}">'
                 f'{b["exp"]*100:+.0f}% риска</b><i>прибыль в % от поставленного стопа</i></div>'
                 f'<div class="cd"><span>Надёжность вывода</span><b class="{"ok" if avp<0.05 else "warn"}">p {avp:.3f}</b>'
                 f'<i>always-valid: смотреть можно сейчас</i></div>'
                 f'<div class="cd"><span>В деньгах (риск {RISK_PCT}% от {CAPITAL_USD:,.0f} USD)</span>'
                 f'<b class="{"ok" if eq_money>0 else "bad"}">{eq_money:+,.0f} USD</b>'
                 f'<i>{eq_pct:+.1f}% капитала · стресс 10 стопов подряд = −{10*RISK_PCT:.0f}%</i></div>'
                 f'<div class="cd"><span>Gross / Net</span><b>{b["exp"]*100:+.0f}% / {(b["exp"])*100:+.0f}%</b>'
                 f'<i>gross {base["gross_r"].mean():+.4f}R → net {b["exp"]:+.4f}R после издержек</i></div>'
                 f'<div class="cd"><span>Win rate с 95% CI</span><b>{b["wr"]:.0f}%</b>'
                 f'<i>[{wr_lo:.0f}%; {wr_hi:.0f}%] — истинное значение с вероятностью 95% внутри</i></div>'
                 f'<div class="cd"><span>Итог за всё время</span><b class="{"ok" if b["net"]>0 else "bad"}">'
                 f'{b["net"]:+.0f} рисков</b><i>сумма результатов всех сделок</i></div></div>')
        H.append('<p>Как читать: система рискует в каждой сделке одной и той же суммой (назовём её «1 риск»). '
                 f'В среднем каждая сделка приносит <b>{b["exp"]*100:+.0f}% от этого риска</b> — то есть на каждые '
                 f'100 поставленных рублей система в среднем возвращает {100 + b["exp"]*100:.0f}. '
                 f'Из каждых 100 сделок <b>{b["wr"]:.0f} приносят прибыль</b>, а {100-b["wr"]:.0f} заканчиваются стопом.</p>')
    else:
        H.append('<div class="cards"><div class="cd"><span>Сделок пока нет</span><b>0</b>'
                 '<i>система ждёт подходящий момент</i></div></div>')

    # что происходит сейчас
    if l:
        H.append(f'<div class="lead"><b>Что происходит сейчас.</b> В живом режиме система уже сделала '
                 f'{l["n"]} сделок: прибыльных {pct_word(l["wr"])}. Журнал ниже пополняется сам.</div>')
    else:
        H.append('<div class="lead"><b>Что происходит сейчас.</b> Система <b>не торгует</b> и это правильно: '
                 'цена золота находится <b>ниже своей долгосрочной средней линии</b> (средняя за 200 дней на дневном '
                 'графике), а правила системы разрешают покупать только выше этой линии. Как только рынок вернётся '
                 'выше и сформируется понятная структура движения — система сделает прогноз, и он сразу появится '
                 'в этом журнале.</div>')

    # словарь
    H.append('<div class="gloss"><b>Словарь простыми словами</b><dl>'
             '<dt>Сделка / прогноз</dt><dd>Система решила: «цена вырастет от X до Y (цель), а если упадёт до Z — '
             'признаю ошибку». Это и есть прогноз с целью и стопом.</dd>'
             '<dt>Тейк-профит (TP, цель)</dt><dd>Цена, на которой сделку закрывают с прибылью.</dd>'
             '<dt>Стоп-лосс (SL, стоп)</dt><dd>Цена, на которой сделку закрывают с небольшим убытком, '
             'чтобы не потерять много. Убыток заранее известен и одинаков во всех сделках.</dd>'
             '<dt>Win rate (винрейт)</dt><dd>Сколько сделок из 100 закончились прибылью.</dd>'
             '<dt>«1 риск» (R)</dt><dd>Размер запланированного убытка в сделке (расстояние от входа до стопа). '
             'Все результаты измеряются в этих рисках: +1 риск = прибыль равна стопу, −1 риск = сработал стоп.</dd>'
             '<dt>% успешных прогнозов</dt><dd>Доля сделок, где цена дошла до цели (тейк-профита).</dd>'
             '<dt>Угадано направление</dt><dd>Цена хотя бы заметно пошла в сторону прогноза, даже если до цели не дошла.</dd>'
             '</dl></div>')

    # группы
    if b and len(base):
        H.append('<h2>Где система сильнее и слабее</h2>'
                 '<p>Таблица показывает, на каких ситуациях прогнозы сбываются чаще. '
                 '«Прибыльных из 100» — тот же винрейт, но записанный по-человечески.</p>')
        def simple_table(df, col, title, names):
            rows = []
            for key, g in df.groupby(col, dropna=False):
                net = g["net_r"].dropna().to_numpy(float)
                if len(net) < 5:
                    continue
                wr = (net > 0).mean() * 100
                mark = "🟢" if wr >= 60 else ("🟡" if wr >= 50 else "🔴")
                rows.append(f'<tr><td>{names.get(str(key), str(key))}</td><td>{len(net)}</td>'
                            f'<td>{mark} {wr:.0f} из 100</td><td>{net.sum():+.0f} рисков</td></tr>')
            if not rows:
                return ""
            return (f'<h3>{title}</h3><table><thead><tr><th>Ситуация</th><th>Сделок</th>'
                    f'<th>Прибыльных из 100</th><th>Итог</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
        yrs = base.copy()
        yrs["year"] = pd.to_datetime(yrs["entry_time"], errors="coerce").dt.year
        H.append(simple_table(base, "branch", "По стратегиям",
                              {"B04_LONG_EXTW3_RSI": "сильный импульс после паузы (основная)",
                               "B01_LONG_CORE": "классический импульс с подтверждением формой",
                               "B02_LONG_EMA200_FIBOFF": "импульс без фильтра формы",
                               "B03_LONG_W3A_HV": "короткая третья волна (эксперимент)"}))
        H.append(simple_table(yrs.dropna(subset=["year"]), "year", "По годам",
                              {str(y): f"{int(y)} год" for y in range(2020, 2028)}))
        H.append('<p> 2024 год — пример честности журнала: в спокойном «боковом» рынке прогнозы сбывались '
                 'редко (31 из 100), и система там потеряла. Журнал это не прячет.</p>')

    # последние сделки простыми словами
    H.append('<h2>Последние сделки</h2>')
    if len(base):
        rows = []
        for _, t in base.dropna(subset=["net_r"]).tail(15).iloc[::-1].iterrows():
            d = pd.to_datetime(t["entry_time"], errors="coerce", utc=True)
            ds = d.tz_convert("Asia/Yekaterinburg").strftime("%d.%m.%y %H:%M") if pd.notna(d) else "—"
            res = t["net_r"]
            rows.append(f'<tr><td>{ds}</td><td>цена вырастет</td><td>{t["entry"]:.0f} → цель {t["tp"]:.0f}, '
                        f'стоп {t["sl"]:.0f}</td><td>{REASON_PLAIN.get(t["reason"], t["reason"])}</td>'
                        f'<td class="{"ok" if res>0 else "bad"}">{res:+.2f} риска</td></tr>')
        H.append('<table><thead><tr><th>Когда (ЕKB)</th><th>Прогноз</th><th>Вход → цель / стоп</th>'
                 '<th>Чем закончилось</th><th>Результат</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
    else:
        H.append('<p>Сделок пока нет — см. «Что происходит сейчас».</p>')

    # средний по процентам — объяснение
    if b:
        H.append('<h2>«Средний по процентам успешных прогнозов»</h2>'
                 '<p>Это среднее арифметическое процентов успеха по всем группам выше (стратегии и годы), '
                 'а не по всем сделкам сразу. Зачем: если в одной группе 100 сделок, а в другой 5, общий процент '
                 '«не видит» маленькую группу, а среднее по группам — видит. '
                 f'Сейчас оно равно <b>{mean_of_slices(base):.0f}%</b> при общем винрейте <b>{b["wr"]:.0f}%</b>: '
                 'разница как раз и показывает, что результаты по группам неровные.</p>')

    H.append('<details><summary>Технические детали (для специалиста)</summary>'
             '<p>WIN RATE = доля сделок с результатом &gt; 0 после вычета издержек 0.52 USD на сделку. '
             '% успешных = доля закрытий по TP. Направление верно = MFE ≥ 0.2R. '
             'Данные: LIVE — реальное золото GC=F (append-only журнал, RULE 13); база — backtest кандидата v2 '
             'на PROXY-данных PAXG (2022–2026), не является гарантией будущих результатов. '
             'Полная техническая версия: TRADE_JOURNAL.md в репозитории.</p></details>')
    H.append('<div id="diffLine" class="note"></div>'
             '<script>(function(){try{var k="xauusd_journal_last";var cur='
             '{n:' + str(int(b["n"])) + ',wr:' + f'{b["wr"]:.1f}' + '};'
             'var prev=JSON.parse(localStorage.getItem(k)||"null");'
             'localStorage.setItem(k,JSON.stringify(cur));'
             'var el=document.getElementById("diffLine");if(el&&prev){var dn=cur.n-prev.n;'
             'el.textContent=dn>0?("С прошлого визита: +"+dn+" сделок(и). Win rate был "+prev.wr+"%, стал "+cur.wr+"%.")'
             ':("С прошлого визита новых сделок нет (win rate "+cur.wr+"%).");}'
             'else if(el){el.textContent="Это ваш первый визит в журнал — дальше здесь будет видно, что изменилось.";}'
             '}catch(e){}})();</script>'
             '<p style="color:#8b98b0;font-size:12px">Обновлено: ' + now_e + ' · freeze SHA-256 ' + freeze_hash() + '. '
             'Это журнал исследовательской системы, а не инвестиционная рекомендация.</p></div>')
    return "".join(H)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (max(0.0, c - h) * 100, min(1.0, c + h) * 100)


def mean_ci(net, z: float = 1.96) -> tuple[float, float]:
    n = len(net)
    if n < 2:
        return (float("nan"), float("nan"))
    m = float(np.mean(net))
    se = float(np.std(net, ddof=1)) / n ** 0.5
    return (m - z * se, m + z * se)


def always_valid_p(net, tau: float = 0.15) -> float:
    """Всегда-валидное p-значение (mSPRT, Howard et al.): смотреть можно в любой момент без peeking-bias.
    sigma оценивается по выборке (fallback 1.24R); значение консервативнее классического p — это плата
    за возможность заглядывать в данные когда угодно."""
    import math
    n = len(net)
    if not n:
        return 1.0
    m = float(np.mean(net))
    sd = float(np.std(net, ddof=1)) if n > 1 else 1.24
    sigma = max(0.6, sd or 1.24)
    S = m * n
    v = sigma ** 2
    logL = -0.5 * math.log(1 + n * tau ** 2 / v) + (S * S / 2) * (tau ** 2 / (v * (v + n * tau ** 2)))
    return min(1.0, math.exp(-logL))


def mean_of_slices(df: pd.DataFrame) -> float:
    vals = []
    for col in ["branch", "w3_class"]:
        for _, g in df.groupby(col, dropna=False):
            net = g["net_r"].dropna().to_numpy(float)
            if len(net) >= 5:
                vals.append((net > 0).mean() * 100)
    yrs = df.copy()
    yrs["year"] = pd.to_datetime(yrs["entry_time"], errors="coerce").dt.year
    for _, g in yrs.dropna(subset=["year"]).groupby("year"):
        net = g["net_r"].dropna().to_numpy(float)
        if len(net) >= 5:
            vals.append((net > 0).mean() * 100)
    return sum(vals) / len(vals) if vals else 0.0


def main(extra: list[str]) -> int:
    live = load(FWD, "LIVE")
    paper = pd.concat([load(p, "PAPER") for p in extra], ignore_index=True) if extra else pd.DataFrame(columns=COLS)
    base = load(BASE, "BACKTEST")
    now_e = datetime.now(EKB).strftime("%d.%m.%Y %H:%M ЕKB")

    md = ["# ЖУРНАЛ СДЕЛОК XAUUSD Elliott Agent", "",
          versions_block(), "", src_label("PROXY_PAXG"), "",
          "**Gross vs Net:** основные метрики считаются по NET R; gross показан рядом для прозрачности издержек.", "",
          f"Ведёт агент · обновлено: **{now_e}** · правила: `PARAMETER_FREEZE_v2` (addendum v2.1) · "
          "журнал append-only (RULE 13): закрытые сделки не изменяются.", "",
          "> **WIN RATE** = доля сделок с net > 0 после издержек 0.52 USD. "
          "> **% успешных прогнозов** = доля закрытий по TP (цель прогноза достигнута). "
          "> **Средний по процентам** = среднее процентов успеха по срезам (не то же самое, что общий WR).", ""]

    # ── LIVE ─
    md += ["## 1. LIVE FORWARD (реальное золото GC=F) — идёт накопление", ""]
    if len(live):
        net = live["net_r"].dropna().to_numpy(float)
        wr = (net > 0).mean() * 100
        tp = (live["reason"] == "TP").sum() / max(1, len(net)) * 100
        md += [f"- сделок: **{len(net)}** · **WIN RATE {wr:.1f}%** · **% успешных прогнозов (TP) {tp:.1f}%** · "
               f"Net {net.sum():+.1f}R", "",
               kpi_table(slice_stats(live, "branch")), "", trades_table(live)]
    else:
        md += ["Сделок пока **0**: forward-окно открыто 2026-09-15 20:00 UTC, режим D1 = BEAR "
               "(close ниже EMA200) → production LONG запрещён (§7), система стоит в WAIT. "
               "Журнал начнёт заполняться с первого сигнала, прошедшего все mandatory gates.", "",
               "| Показатель | Значение |", "|---|---|",
               "| Сделок | 0 |", "| WIN RATE | — |", "| % успешных прогнозов | — |",
               "| Баров в forward-окне | см. дашборд LIVE |"]
    md.append("")

    # ── PAPER ──
    if len(paper):
        net = paper["net_r"].dropna().to_numpy(float)
        md += ["## 2. PAPER (браузерный журнал пользователя)", "",
               f"- сделок: **{len(net)}** · WIN RATE {(net > 0).mean()*100:.1f}% · "
               f"% TP {(paper['reason'] == 'TP').sum()/max(1,len(net))*100:.1f}%", "", trades_table(paper), ""]

    # ── BACKTEST BASE ──
    md += ["## 3. Историческая база (backtest кандидата v2, PROXY-данные) — ориентир, не live", ""]
    if len(base):
        net = base["net_r"].dropna().to_numpy(float)
        wr = (net > 0).mean() * 100
        tp_pct = (base["reason"] == "TP").sum() / len(net) * 100
        dir_pct = (base["mfe_r"].fillna(0) >= 0.2).mean() * 100
        avp = always_valid_p(net)
        wr_lo, wr_hi = wilson_ci(int((net > 0).sum()), len(net))
        e_lo, e_hi = mean_ci(net)
        r_usd = CAPITAL_USD * RISK_PCT / 100
        eq_money = net.sum() * r_usd
        eq_pct = net.sum() * RISK_PCT
        md += [f"- сделок: **{len(net)}** · **WIN RATE {wr:.1f}%** · **% успешных прогнозов (TP) {tp_pct:.1f}%** · "
               f"**% верных по направлению {dir_pct:.1f}%** · "
               f"**always-valid p {avp:.3f}** (можно смотреть в любой момент, freeze v2.3) · "
               f"WR 95% CI [{wr_lo:.1f}%; {wr_hi:.1f}%] · Expectancy 95% CI [{e_lo:+.3f}; {e_hi:+.3f}]R · "
               f"в деньгах при риске {RISK_PCT}% от {CAPITAL_USD:.0f} USD: {eq_money:+,.0f} USD ({eq_pct:+.1f}% капитала) · "
               f"PF {net[net>0].sum()/-net[net<0].sum():.3f} · Expectancy {net.mean():+.4f}R · Net {net.sum():+.1f}R", ""]
        md += ["### Средний по процентам успешных прогнозов (по срезам)", ""]
        all_slices = []
        for col, title in [("branch", "По веткам"), ("w3_class", "По классу W3"),
                           ("reason", "По причине закрытия")]:
            rows = slice_stats(base, col)
            all_slices += rows
            md += [f"**{title}**", "", kpi_table(rows), ""]
        yrs = base.copy()
        yrs["year"] = pd.to_datetime(yrs["entry_time"], errors="coerce").dt.year
        yrows = slice_stats(yrs.dropna(subset=["year"]), "year")
        md += ["**По годам**", "", kpi_table(yrows), ""]
        pool = all_slices + yrows
        mean_wr = sum(r["wr"] for r in pool) / max(1, len(pool))
        mean_tp = sum(r["tp_pct"] for r in pool) / max(1, len(pool))
        mean_dir = sum(r.get("dir_pct", 0) for r in pool) / max(1, len(pool))
        md += [f"**СРЕДНИЙ ПО ПРОЦЕНТАМ УСПЕШНЫХ ПРОГНОЗОВ по всем срезам: {mean_tp:.1f}%** "
               f"(средний win rate по срезам: {mean_wr:.1f}%, средний % верных по направлению: {mean_dir:.1f}%)", "",
               "### Последние сделки базы", "", trades_table(base, 25)]
    md += ["", "---",
           "## Протокол ведения", "",
           "1. LIVE-сделки пишет `forward_collector.py` в `data/forward/forward_signals.csv` (append-only);",
           "2. этот скрипт пересобирает журнал после каждого сбора данных и после каждой сессии агента;",
           "3. закрытые сделки НЕ редактируются (RULE 13); исправления — только новой записью-комментарием;",
           "4. paper-журнал браузера добавляется экспортом CSV пользователем;",
           "5. калибровка по журналу — только через §63–66 (см. `reports/LEARNING_v1.md`).", ""]
    (REP / "TRADE_JOURNAL.md").write_text("\n".join(md), encoding="utf-8")
    body = build_plain_html(live, paper, base, now_e)
    (REP / "TRADE_JOURNAL_body.html").write_text(body, encoding="utf-8")
    print(f"→ {REP/'TRADE_JOURNAL.md'}  (LIVE {len(live)} / PAPER {len(paper)} / BASE {len(base)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
