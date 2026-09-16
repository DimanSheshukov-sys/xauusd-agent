#!/usr/bin/env python3
"""ОДИН ФАЙЛ ВМЕСТО САЙТА — `site_single.html`.

Весь проект в одном self-contained HTML: дашборд + канон + freeze + аудит +
pre-registration + README + деплой + все отчёты + журнал. Табы переключаются JS'ом,
внешних зависимостей нет → файл можно открыть двойным кликом, отправить в мессенджере,
положить на любой хостинг или приложить к письму.

Запуск:  python3 build_single_file.py     →  site_single.html
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_site import md_to_html, CSS          # noqa: E402

TABS = [
    ("dash", "Дашборд", None),
    ("exp3", "Эксперимент v3", ROOT / "reports" / "EXPERIMENT_v3.md"),
    ("wf", "Walk-forward", ROOT / "reports" / "WALKFORWARD_v2.md"),
    ("exp2", "Эксперимент v2", ROOT / "reports" / "EXPERIMENT_v2.md"),
    ("freeze2", "Freeze v2", ROOT / "PARAMETER_FREEZE_v2.md"),
    ("spec", "Канон v1.8", ROOT / "MASTER_SPEC_v1.8.md"),
    ("audit", "Аудит", ROOT / "INTAKE_AUDIT_v1.md"),
    ("prereg", "Pre-registration", ROOT / "NEXT_CYCLE_PREREGISTRATION_v2.md"),
    ("freeze1", "Freeze v1", ROOT / "PARAMETER_FREEZE_v1.md"),
    ("readme", "README", ROOT / "README.md"),
    ("deploy", "Деплой", ROOT / "DEPLOY.md"),
    ("journal", "Журнал", ROOT.parent / "журнал.md"),
]
if os.environ.get("SITE_PUBLIC"):      # публичная сборка: журнал диалога не вкладываем
    TABS = [t for t in TABS if t[0] != "journal"]

EXTRA_CSS = """
#tabbar{position:sticky;top:0;z-index:60;background:rgba(11,18,32,.97);border-bottom:1px solid #22304d;
 padding:8px 14px;display:flex;gap:5px;flex-wrap:wrap;align-items:center}
#tabbar b{color:#f0b429;font-size:12.5px;margin-right:8px;letter-spacing:.4px}
#tabbar button{background:#0f1830;border:1px solid #22304d;color:#a9b7cf;font-size:12px;padding:4px 10px;
 border-radius:7px;cursor:pointer;font-family:inherit}
#tabbar button:hover{background:#182338;color:#e6edf7}
#tabbar button.active{border-color:#5c4a17;background:#241d0c;color:#f0b429}
.pane{display:none}.pane.active{display:block}
.docpane{max-width:1200px;margin:0 auto;padding:20px}
.docpane .doc{background:#131d33;border:1px solid #22304d;border-radius:14px;padding:22px 26px}
.doc h1{font-size:23px;margin:0 0 12px;border-bottom:1px solid #22304d;padding-bottom:9px}
.doc h2{font-size:17px;margin:24px 0 9px;color:#dbe4f2}
.doc h3{font-size:14.5px;margin:18px 0 7px;color:#c3cede}
.doc table{display:block;overflow-x:auto}
.doc pre{background:#0a1122;border:1px solid #22304d;border-radius:10px;padding:12px 14px;overflow-x:auto;font-size:12px;color:#cfe3ff}
.doc blockquote{border-left:3px solid #f0b429;margin:11px 0;padding:6px 14px;background:#141d33;border-radius:0 8px 8px 0}
.doc a{color:#7fb2ff}
"""

JS = """
<script>
(function(){
  function show(id){
    document.querySelectorAll('.pane').forEach(function(p){p.classList.remove('active');});
    document.querySelectorAll('#tabbar button').forEach(function(b){b.classList.remove('active');});
    var p=document.getElementById('pane-'+id), b=document.getElementById('tab-'+id);
    if(p)p.classList.add('active'); if(b)b.classList.add('active');
    try{history.replaceState(null,'','#'+id);}catch(e){}
    window.scrollTo(0,0);
  }
  document.querySelectorAll('#tabbar button').forEach(function(b){
    b.addEventListener('click',function(){show(b.dataset.pane);});
  });
  var h=(location.hash||'').replace('#','');
  show(h && document.getElementById('pane-'+h) ? h : 'dash');
})();
</script>
"""


def build() -> Path:
    dash_path = ROOT / "dashboard" / "index.html"
    if not dash_path.exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "dashboard.py")], cwd=str(ROOT), check=False)
    dash = dash_path.read_text(encoding="utf-8")

    # встраиваем доп. CSS
    dash = dash.replace("</style>", EXTRA_CSS + "</style>", 1)

    # панель табов + оборачиваем дашборд в pane
    buttons = "".join(f'<button id="tab-{tid}" data-pane="{tid}">{label}</button>' for tid, label, _ in TABS)
    buttons += ('<button onclick="window.open(\'https://dimansheshukov-sys.github.io/xauusd-agent/\')" '
                'style="border-color:#1d4a33;color:#5ee39a">LIVE онлайн ↗</button>')
    tabbar = f'<div id="tabbar"><b>XAUUSD ELLIOTT AGENT</b>{buttons}</div>'
    dash = dash.replace('<body>', f'<body>{tabbar}<div class="pane active" id="pane-dash">', 1)

    # остальные вкладки
    panes = []
    for tid, label, src in TABS:
        if src is None:
            continue
        if not src.exists():
            continue
        body = md_to_html(src.read_text(encoding="utf-8"))
        panes.append(f'<div class="pane docpane" id="pane-{tid}"><div class="doc">'
                     f'<h1>{label}</h1><div class="meta" style="color:#8b98b0;font-size:11.5px;margin-bottom:14px">'
                     f'источник: <code>{src.name}</code></div>{body}</div></div>')

    tail = "".join(panes) + JS + "</body></html>"
    # закрываем pane-dash перед хвостом: ищем последний </div></body></html>
    if dash.rstrip().endswith("</body></html>"):
        idx = dash.rstrip().rfind("</body></html>")
        dash = dash[:idx] + "</div>" + tail
    else:
        dash = dash + "</div>" + tail

    out = ROOT / "site_single.html"
    out.write_text(dash, encoding="utf-8")
    return out


if __name__ == "__main__":
    t0 = time.time()
    p = build()
    print(f"→ {p}  ({p.stat().st_size/1024:.0f} КБ, {len(TABS)} вкладок, {time.time()-t0:.1f}s)")
