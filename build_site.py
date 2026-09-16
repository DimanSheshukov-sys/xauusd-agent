#!/usr/bin/env python3
"""СБОРКА САЙТА — статический self-contained сайт (можно положить на любой хостинг).

    python3 build_site.py            → site/

Структура site/:
    index.html            дашборд (живые KPI работают при отдаче через serve.py)
    reports/*.html        EXPERIMENT_v2, EXPERIMENT_v3, WALKFORWARD_v2
    docs/*.html           канон, freeze v1/v2, аудит, pre-registration, README, журнал
    data/*                CSV-логи сделок и forward-журнал (скачиваются)
    data/status.json      машинное состояние системы

Сайт полностью автономный: инлайн CSS, никаких CDN/шрифтов/скриптов (кроме виджета
TradingView, который в sandbox-превью просто не загрузится).

Деплой: site/ целиком → GitHub Pages / Netlify / Cloudflare Pages / Vercel / nginx.
Автообновление на хостинге: GitHub Actions по cron (см. .github/workflows/site.yml).
"""
from __future__ import annotations

import html as H
import json
import re
import shutil
import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
# SITE_PUBLIC=1 → не публикуем журнал диалога (в нём вся переписка и внутренняя кухня)
PUBLIC = bool(os.environ.get("SITE_PUBLIC"))

BG, CARD, LINE, GOLD, MUTED = "#0b1220", "#131d33", "#22304d", "#f0b429", "#8b98b0"

NAV = [
    ("index.html", "LIVE"),
    ("reports/TRADE_JOURNAL.html", "Журнал сделок"),
    ("reports/index.html", "Отчёты"),
    ("docs/index.html", "Документы"),
    ("data/", "Данные"),
]

CSS = f"""
*{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:#e6edf7;font-family:ui-sans-serif,system-ui,'Segoe UI',Roboto,Arial;font-size:14px;line-height:1.6}}
nav.top{{position:sticky;top:0;z-index:20;background:rgba(11,18,32,.96);backdrop-filter:blur(6px);
 border-bottom:1px solid {LINE};padding:9px 18px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
nav.top b{{color:{GOLD};margin-right:10px;font-size:13px;letter-spacing:.4px}}
nav.top a{{color:#a9b7cf;text-decoration:none;font-size:12.5px;padding:4px 9px;border-radius:7px;border:1px solid transparent}}
nav.top a:hover{{background:#182338;color:#e6edf7}}
nav.top a.active{{border-color:{LINE};background:#16213a;color:{GOLD}}}
main{{max-width:1440px;margin:0 auto;padding:20px}}
.doc{{background:{CARD};border:1px solid {LINE};border-radius:14px;padding:22px 26px}}
.doc h1{{font-size:24px;margin:0 0 14px;border-bottom:1px solid {LINE};padding-bottom:10px}}
.doc h2{{font-size:18px;margin:26px 0 10px;color:#dbe4f2}}
.doc h3{{font-size:15px;margin:20px 0 8px;color:#c3cede}}
.doc p{{margin:9px 0}}
.doc a{{color:#7fb2ff}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin:12px 0;display:block;overflow-x:auto}}
th,td{{padding:6px 9px;border-bottom:1px solid #1b2740;text-align:left;vertical-align:top}}
th{{color:#93a3bd;background:#0f1830;font-size:11px;text-transform:uppercase;letter-spacing:.05em}}
pre{{background:#0a1122;border:1px solid {LINE};border-radius:10px;padding:12px 14px;overflow-x:auto;
 font-size:12px;line-height:1.5;color:#cfe3ff}}
code{{background:#0f1830;border:1px solid {LINE};padding:1px 5px;border-radius:5px;font-size:12px}}
pre code{{background:none;border:none;padding:0}}
blockquote{{border-left:3px solid {GOLD};margin:12px 0;padding:6px 14px;background:#141d33;color:#d7e0ee;border-radius:0 8px 8px 0}}
hr{{border:none;border-top:1px solid {LINE};margin:22px 0}}
ul,ol{{padding-left:22px}}
li{{margin:4px 0}}
footer{{color:{MUTED};font-size:11.5px;padding:18px 4px 40px;text-align:center}}
.files a{{display:inline-block;margin:4px 8px 4px 0;padding:6px 11px;background:#0f1830;border:1px solid {LINE};
 border-radius:8px;color:#c7d3e6;text-decoration:none;font-size:12.5px}}
.files a:hover{{border-color:{GOLD};color:{GOLD}}}
"""


def md_to_html(md: str) -> str:
    """Минимальный Markdown → HTML (заголовки, таблицы, код, списки, цитаты, инлайн)."""
    lines = md.split("\n")
    out, i, in_code, in_ul, in_ol, in_tbl = [], 0, False, False, False, False

    def inline(t: str) -> str:
        t = H.escape(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    def close_lists():
        nonlocal in_ul, in_ol, in_tbl
        if in_ul:
            out.append("</ul>"); in_ul = False
        if in_ol:
            out.append("</ol>"); in_ol = False
        if in_tbl:
            out.append("</tbody></table>"); in_tbl = False

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>"); in_code = False
            else:
                close_lists(); out.append("<pre><code>"); in_code = True
            i += 1
            continue
        if in_code:
            out.append(H.escape(ln)); i += 1; continue
        s = ln.strip()
        if not s:
            close_lists(); i += 1; continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            close_lists()
            hdr = [c.strip() for c in s.strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr></thead><tbody>")
            in_tbl = True; i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>"); in_tbl = False
            continue
        if in_tbl and not s.startswith("|"):
            out.append("</tbody></table>"); in_tbl = False
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            close_lists()
            lv = min(len(m.group(1)), 4)
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>"); i += 1; continue
        if re.match(r"^(\*\*\*|---|___)$", s):
            close_lists(); out.append("<hr>"); i += 1; continue
        if s.startswith(">"):
            close_lists(); out.append(f"<blockquote>{inline(s.lstrip('> ').strip())}</blockquote>"); i += 1; continue
        if re.match(r"^[-*+]\s+", s):
            if in_ol:
                out.append("</ol>"); in_ol = False
            if not in_ul:
                out.append("<ul>"); in_ul = True
            item = re.sub(r"^[-*+]\s+", "", s)
            out.append(f"<li>{inline(item)}</li>"); i += 1; continue
        if re.match(r"^\d+[.)]\s+", s):
            if in_ul:
                out.append("</ul>"); in_ul = False
            if not in_ol:
                out.append("<ol>"); in_ol = True
            item = re.sub(r"^[0-9.)]+\s+", "", s)
            out.append(f"<li>{inline(item)}</li>"); i += 1; continue
        if s.startswith("<svg") or s.startswith("<script"):
            close_lists(); out.append(ln); i += 1; continue
        close_lists()
        out.append(f"<p>{inline(s)}</p>"); i += 1
    close_lists()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def nav_links(active: str = "", base: str = "") -> str:
    out = []
    for h, t in NAV:
        if h is None:
            continue
        href = h if h.startswith("http") else base + h
        cls = ' class="active"' if h == active else ""
        out.append(f'<a href="{href}"{cls}>{t}</a>')
    return "".join(out)


THEME_JS = """<script>
(function(){
  var t = localStorage.getItem("xauusd_theme");
  if (t === "tech") document.documentElement.classList.add("tech");
  window.toggleTheme = function(){
    var on = document.documentElement.classList.toggle("tech");
    localStorage.setItem("xauusd_theme", on ? "tech" : "magic");
    var b = document.getElementById("themeBtn");
    if (b) b.textContent = on ? "🪄 Зачарованный режим" : "⚙ Строгий режим";
  };
  document.addEventListener("DOMContentLoaded", function(){
    var b = document.getElementById("themeBtn");
    if (b) b.textContent = document.documentElement.classList.contains("tech") ? "🪄 Зачарованный режим" : "⚙ Строгий режим";
  });
})();
</script>"""

FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
           '%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E'
           '%3Crect width=%2732%27 height=%2732%27 rx=%276%27 fill=%27%230b1220%27/%3E'
           '%3Crect x=%2714.5%27 y=%276%27 width=%273%27 height=%2720%27 fill=%27%23f0b429%27/%3E'
           '%3Crect x=%2710%27 y=%2711%27 width=%2712%27 height=%2710%27 fill=%27%23f0b429%27/%3E%3C/svg%3E">')

DOCS_STEMS = {"MASTER_SPEC_v1.8", "PARAMETER_FREEZE_v1", "PARAMETER_FREEZE_v2", "INTAKE_AUDIT_v1",
              "NEXT_CYCLE_PREREGISTRATION_v2", "README", "DEPLOY", "REPO_SETUP"}


def fix_md_links(html: str, page_dir: str) -> str:
    """Ссылки вида reports/X.md превращает в рабочие .html с учётом каталога страницы."""
    def rep(m):
        href = m.group(1)
        if not href.endswith(".md") or href.startswith("http"):
            return m.group(0)
        stem = href[:-3].split("/")[-1]
        if href.startswith("reports/"):
            site = "reports/" + stem + ".html"
        elif stem in DOCS_STEMS:
            site = "docs/" + stem + ".html"
        elif href.startswith("data/"):
            site = href
        else:
            site = "docs/" + stem + ".html"
        rel = ("../" + site) if page_dir else site
        return 'href="' + rel + '"'
    return re.sub(r'href="([^"]+)"', rep, html)


def page(title: str, body: str, active: str = "", base: str = "") -> str:
    links = nav_links(active, base)
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{H.escape(title)} · XAUUSD Elliott Agent</title>' + FAVICON
            + f'<link rel="stylesheet" href="{base}magic.css"></head><body>'
            f'<nav class="top"><b>XAUUSD ELLIOTT AGENT</b>{links}</nav>'
            f'<main>{body}</main>'
            f'<footer>spec v1.8 · freeze v2 · engine v2 · собрано {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}'
            f'<br>build {BUILD_ID} · не является инвестиционной рекомендацией.</footer>'
            + THEME_JS + '</body></html>')


import hashlib as _hl
BUILD_ID = time.strftime("%y%m%d") + "-" + _hl.sha256(
    (ROOT / "web" / "live.html").read_bytes()).hexdigest()[:6]

REP_PREBUILT = {
    "TRADE_JOURNAL": ROOT / "reports" / "TRADE_JOURNAL_body.html",
}


def build() -> dict:
    SITE.mkdir(exist_ok=True)
    (SITE / "reports").mkdir(exist_ok=True)
    (SITE / "docs").mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    made = []

    # 1) главная = LIVE-страница
    live_src = ROOT / "web" / "live.html"
    lv = live_src.read_text(encoding="utf-8")
    links = nav_links("index.html")
    nav_html = ('<nav style="position:sticky;top:0;z-index:50;background:rgba(11,18,32,.97);'
                'border-bottom:1px solid #22304d;padding:9px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                '<b style="color:#f0b429;font-size:13px;margin-right:6px">XAUUSD ELLIOTT AGENT</b>' + links + '</nav>')
    lv = lv.replace(lv[lv.index("<nav>"):lv.index("</nav>") + 6], nav_html, 1)
    lv = lv.replace("</body>", THEME_JS + "</body>", 1)
    (SITE / "index.html").write_text(lv, encoding="utf-8")
    made.append("index.html")

    # 2) markdown-страницы
    docs = [("MASTER_SPEC_v1.8.md", "docs", "Канон MASTER SPEC v1.8"),
            ("PARAMETER_FREEZE_v2.md", "docs", "PARAMETER FREEZE v2 (действующий)"),
            ("INTAKE_AUDIT_v1.md", "docs", "Аудит исполнимости и данных"),
            ("NEXT_CYCLE_PREREGISTRATION_v2.md", "docs", "Pre-registration следующего цикла")]
    for fname, sub, title in docs:
        src = ROOT / fname
        if not src.exists():
            continue
        rel = f"{sub}/{src.stem}.html"
        body = f'<div class="doc">{md_to_html(src.read_text(encoding="utf-8"))}</div>'
        (SITE / sub / f"{src.stem}.html").write_text(
            page(title, fix_md_links(body, sub), rel, base="../"), encoding="utf-8")
        made.append(rel)

    jrnl = ROOT.parent / "журнал.md"
    if jrnl.exists() and not PUBLIC:
        body = f'<div class="doc">{md_to_html(jrnl.read_text(encoding="utf-8"))}</div>'
        (SITE / "docs" / "journal.html").write_text(
            page("Журнал диалога", fix_md_links(body, "docs"), "docs/journal.html", base="../"), encoding="utf-8")
        made.append("docs/journal.html")

    for rep in [ROOT / "reports" / n for n in
                ["TRADE_JOURNAL.md", "DATA_QUALITY_v1.md", "VALIDATION_v1.md", "EXPERT_COUNCIL_v1.md",
                 "BRANCH_REGISTRY_v1.md", "RISK_SENSITIVITY_v1.md", "EXPERIMENT_v3.md",
                 "WALKFORWARD_v2.md", "EXPERIMENT_v2.md", "LEARNING_v1.md"]
                if (ROOT / "reports" / n).exists()]:
        rel = f"reports/{rep.stem}.html"
        pre = REP_PREBUILT.get(rep.stem)
        if pre and pre.exists():
            body = f'<div class="doc">{pre.read_text(encoding="utf-8")}</div>'
        else:
            body = f'<div class="doc">{md_to_html(rep.read_text(encoding="utf-8"))}</div>'
        (SITE / "reports" / f"{rep.stem}.html").write_text(
            page(rep.stem, fix_md_links(body, "reports"), rel, base="../"), encoding="utf-8")
        made.append(rel)

    # 2.5) движки и тема для LIVE-страницы
    shutil.copy2(ROOT / "web" / "magic.css", SITE / "magic.css")
    made.append("magic.css")
    for f in ["live_engine.js", "paper.js"]:
        src = ROOT / "web" / f
        if src.exists():
            (SITE / f).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            made.append(f)

    # 2.7) страницы-каталоги
    rep_desc = {"DATA_QUALITY_v1": "Аудит источников: PROXY vs REAL, гэпы, дубли, спреды",
                "VALIDATION_v1": "Bootstrap, Monte Carlo, stability, regime, walk-forward, attribution",
                "BRANCH_REGISTRY_v1": "Реестр жизненного цикла веток (active/retired/candidate)",
                "RISK_SENSITIVITY_v1": "Чувствительность к slippage и гэпам золота",
                "EXPERT_COUNCIL_v1": "Совет специалистов: аудит системы и дорожная карта",
                "TRADE_JOURNAL": "Журнал сделок: win rate, % успешных прогнозов, срезы",
                "EXPERIMENT_v3": "Кандидат v2: метрики, абляции, валидация прокси",
                "WALKFORWARD_v2": "Walk-forward OOS с отбором внутри train-окна",
                "EXPERIMENT_v2": "Матрица конфигураций × издержки, реестр веток",
                "LEARNING_v1": "Классификация ошибок §66 и калибровка §63"}
    rows = "".join(f'<li><a href="{n}.html">{n}</a> — {rep_desc.get(n, "")}</li>'
                   for n in ["TRADE_JOURNAL", "DATA_QUALITY_v1", "VALIDATION_v1", "EXPERT_COUNCIL_v1",
                              "BRANCH_REGISTRY_v1", "RISK_SENSITIVITY_v1", "EXPERIMENT_v3",
                              "WALKFORWARD_v2", "EXPERIMENT_v2", "LEARNING_v1"])
    (SITE / "reports" / "index.html").write_text(
        page("Отчёты", f'<div class="doc"><h1>Отчёты</h1><ul>{rows}</ul></div>', "reports/index.html", base="../"),
        encoding="utf-8")
    made.append("reports/index.html")
    doc_desc = {"MASTER_SPEC_v1.8": "Канон системы (86 разделов, правила G00–G15, State Machine)",
                "PARAMETER_FREEZE_v2": "Замороженные параметры v2 + addendum live paper-режима",
                "INTAKE_AUDIT_v1": "Аудит: данные, расхождения канона, 30 gap-параметров",
                "NEXT_CYCLE_PREREGISTRATION_v2": "Гипотезы H1–H6 и план валидации"}
    rows = "".join(f'<li><a href="{n}.html">{t}</a> — {d}</li>'
                   for n, t, d in [(stem, t, doc_desc[stem]) for stem, t in
                                   [(x[0][:-3], x[2]) for x in docs]])
    (SITE / "docs" / "index.html").write_text(
        page("Документы", f'<div class="doc"><h1>Документы</h1><ul>{rows}</ul></div>', "docs/index.html", base="../"),
        encoding="utf-8")
    made.append("docs/index.html")

    # 3) данные
    # сырой датасет paxg_m15.csv (7 МБ) на сайт не кладём — только логи сделок и forward-журнал
    for pat in ["reports/trades_*.csv", "data/forward/forward_signals.csv", "data/forward/collection_log.jsonl"]:
        for f in ROOT.glob(pat):
            if f.stat().st_size > 40 * 1024 * 1024:
                continue
            shutil.copy2(f, SITE / "data" / f.name)
    files = sorted(p.name for p in (SITE / "data").iterdir())
    idx = ['<div class="doc"><h1>Данные и логи</h1><p>Файлы для скачивания:</p><div class="files">'
           + "".join(f'<a href="{n}" download>{n}</a>' for n in files)
           + '</div><hr><h2>Как обновляется</h2><ul>'
             '<li><code>python3 forward_collector.py</code> — дописывает бары GC=F, считает forward-сделки, пересобирает дашборд.</li>'
             '<li><code>python3 build_site.py</code> — пересобирает сайт целиком.</li>'
             '<li><code>python3 serve.py</code> — отдаёт сайт на <code>http://localhost:8000</code> с живым API '
             '(<code>/api/live</code>, <code>/api/status</code>, <code>/api/refresh</code>) и автообновлением.</li></ul></div>']
    (SITE / "data" / "index.html").write_text(page("Данные", "".join(idx), "data/", base="../"), encoding="utf-8")
    made.append("data/index.html")

    # 4) машинный статус
    try:
        sys.path.insert(0, str(ROOT))
        from serve import _status
        (SITE / "data" / "status.json").write_text(json.dumps(_status(), ensure_ascii=False, indent=1, default=str),
                                                   encoding="utf-8")
        made.append("data/status.json")
    except Exception as e:
        print(f"status.json не записан: {type(e).__name__}: {e}")
    return {"pages": made, "data_files": files}


if __name__ == "__main__":
    t0 = time.time()
    r = build()
    total = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"→ {SITE}/  ({len(r['pages'])} страниц, {total/1024:.0f} КБ, {time.time()-t0:.1f}s)")
    for p in r["pages"]:
        print("   ", p)
