#!/usr/bin/env python3
"""СЕРВЕР САЙТА — stdlib only (никаких зависимостей), живой API + автообновление.

    python3 serve.py                      → http://localhost:8000
    python3 serve.py --port 8080 --host 0.0.0.0 --interval 900
    python3 serve.py --no-refresh         → без фонового сбора данных

Эндпоинты:
    /                сайт (site/, иначе dashboard/)
    /api/live        живые данные: цена/спред/DXY + решение §72 (кэш 60 c, фон-обновление)
    /api/status      состояние системы: forward OOS, датасеты, отчёты, версия freeze
    /api/refresh     принудительно пересобрать дашборд и сайт

Фоновый поток раз в --interval секунд запускает forward_collector.py (дописывает бары
GC=F, считает forward-сделки, пересобирает дашборд) и build_site.py.

Для внешнего доступа: запустить на VPS и открыть http://<ip>:8000, либо отдать через
nginx/caddy с TLS. Порт наружу без авторентификации не публикуйте — см. README сайта.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))
SITE = ROOT / "site"
DASH = ROOT / "dashboard"

CACHE_TTL = 60
_cache: dict = {"live": (0.0, None), "status": (0.0, None)}
_lock = threading.Lock()


def _analyze_live() -> dict:
    from analyze import analyze
    A = analyze(chart_bars=0)
    tv, live = A.get("tv", {}), A.get("tv", {}).get("live", {})
    price, spread = live.get("lp"), tv.get("spread")
    atr = A["m15"]["atr"]
    dec = A["decision"]
    return {"ok": True, "now_utc": A["now_utc"],
            "price": f"{price:,.2f}" if price else "—",
            "bidask": f"bid {live.get('bid','—')} / ask {live.get('ask','—')}",
            "chg": f"{live.get('chp', 0):+.2f}%" if live.get("chp") is not None else "—",
            "chg_usd": f"{live.get('ch', 0):+,.2f} USD",
            "spread": f"{spread:.2f} USD" if spread else "—",
            "spread_hint": f"{(spread / (atr * 2.5) * 100 if spread and atr else 0):.1f}% от R (2.5 ATR)",
            "dxy": tv.get("dxy", {}).get("close"),
            "decision": dec["decision"], "state": dec["state"], "reasons": dec["reason"],
            "structure": (A["structure"] or {}).get("kind"),
            "m15_close": A["m15"]["close"], "m15_atr": atr,
            "mtf": A["mtf"], "signal": dec.get("signal")}


def _status() -> dict:
    fwd = ROOT / "data" / "forward"
    log = []
    if (fwd / "collection_log.jsonl").exists():
        log = [json.loads(x) for x in (fwd / "collection_log.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
    sig = fwd / "forward_signals.csv"
    n_sig = 0
    if sig.exists():
        n_sig = max(0, len(sig.read_text(encoding="utf-8").strip().split("\n")) - 1)
    rep = ROOT / "reports"
    v3 = json.loads((rep / "results_v3.json").read_text(encoding="utf-8")) if (rep / "results_v3.json").exists() else {}
    caus = json.loads((rep / "causality.json").read_text(encoding="utf-8")) if (rep / "causality.json").exists() else {}
    return {"ok": True, "generated_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "spec": "MASTER_SPEC v1.8", "freeze": "PARAMETER_FREEZE_v2", "engine": "v2",
            "status_level": "P2 (PROXY)", "causality": caus.get("verdict"),
            "candidate": {k: v3.get("candidate", {}).get(k) for k in
                          ["trades", "win_rate_pct", "pf_net", "expectancy_r", "net_r", "max_dd_r", "p_value"]},
            "forward": {"runs": len(log), "last_run": log[-1].get("run_utc") if log else None,
                        "bars_stored": log[-1].get("m15_rows") if log else 0,
                        "forward_bars": log[-1].get("forward_bars") if log else 0,
                        "signals": n_sig, "state": log[-1].get("status") if log else "—",
                        "metrics": (log[-1] or {}).get("forward_metrics", {}) if log else {},
                        "integrity_warnings": (log[-1] or {}).get("integrity_warnings", []) if log else [],
                        "accept_target_n": 74},
            "datasets": {p.stem: p.stat().st_size for p in (ROOT / "data").glob("*.csv")},
            "reports": sorted(p.name for p in rep.glob("*.md"))}


def cached(key: str, fn, ttl: int = CACHE_TTL):
    with _lock:
        ts, val = _cache[key]
        if val is not None and time.time() - ts < ttl:
            return val
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def rebuild() -> dict:
    out = {}
    for script in ["forward_collector.py", "build_site.py"]:
        p = ROOT / script
        if not p.exists():
            continue
        r = subprocess.run([sys.executable, str(p)], cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        out[script] = {"rc": r.returncode, "tail": (r.stdout or r.stderr)[-400:]}
    return out


def refresher(interval: int):
    while True:
        time.sleep(interval)
        try:
            rebuild()
            with _lock:
                _cache["live"] = (0.0, None)
                _cache["status"] = (0.0, None)
        except Exception as e:
            print(f"[refresher] {type(e).__name__}: {e}", flush=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        root = SITE if (SITE / "index.html").exists() else DASH
        super().__init__(*a, directory=str(root), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/live":
            try:
                self._json(cached("live", _analyze_live))
            except Exception as e:
                self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
            return
        if path == "/api/status":
            try:
                self._json(cached("status", _status, ttl=120))
            except Exception as e:
                self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
            return
        if path == "/api/refresh":
            self._json({"ok": True, "result": rebuild()})
            return
        if path == "/healthz":
            self._json({"ok": True})
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        if "/api/" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--interval", type=int, default=900, help="секунд между автообновлениями (0 = выключить)")
    ap.add_argument("--no-refresh", action="store_true")
    a = ap.parse_args()

    root = SITE if (SITE / "index.html").exists() else DASH
    print(f"XAUUSD Elliott Agent — сервер сайта")
    print(f"  каталог : {root.relative_to(ROOT)}")
    print(f"  адрес   : http://{a.host}:{a.port}")
    print(f"  API     : /api/live  /api/status  /api/refresh  /healthz")
    if a.interval and not a.no_refresh:
        t = threading.Thread(target=refresher, args=(a.interval,), daemon=True)
        t.start()
        print(f"  автообновление: каждые {a.interval} c (forward_collector + build_site)")
    else:
        print("  автообновление: выключено")
    try:
        ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
