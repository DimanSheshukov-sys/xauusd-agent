#!/usr/bin/env python3
"""ПУБЛИКАЦИЯ НА GITHUB PAGES — push + включение Pages + ожидание ссылки.

Токен берётся из --token или переменной окружения GH_TOKEN и **нигде не сохраняется**:
не пишется в .git/config, в лог, в отчёты; в выводе маскируется.

    export GH_TOKEN=github_pat_xxx
    python3 deploy_github.py --owner USER --repo xauusd-agent [--create] [--dry-run]

Что делает:
  1. git init/add/commit (локальная идентичность, global-конфиг не трогает);
  2. push в https://github.com/OWNER/REPO (токен только в аргументе команды push);
  3. POST /repos/OWNER/REPO/pages {build_type: workflow} — включает Pages на GitHub Actions;
  4. ждёт завершения workflow и появления https://OWNER.github.io/REPO/ (до 6 минут);
  5. печатает ссылку.

Требуемые права fine-grained PAT (только на этот репозиторий):
  Contents: Read and write • Pages: Read and write • (для --create) Administration: Read and write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"
MASK = "***"


def mask(s: str, token: str) -> str:
    return s.replace(token, MASK) if token else s


def run(cmd: list[str], token: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if not quiet:
        for line in (r.stdout or "").splitlines()[-6:]:
            print("   " + mask(line, token))
        if r.returncode != 0:
            for line in (r.stderr or "").splitlines()[-6:]:
                print("   !" + mask(line, token))
    if check and r.returncode != 0:
        raise SystemExit(f"команда завершилась с кодом {r.returncode}: {mask(' '.join(cmd), token)}")
    return r


def api(path: str, token: str, method: str = "GET", body: dict | None = None, ok_codes=(200, 201, 204)):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "xauusd-agent-deploy",
                                          "X-GitHub-Api-Version": "2022-11-28",
                                          **({"Content-Type": "application/json"} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    ap.add_argument("--create", action="store_true", help="создать репозиторий, если его нет (нужен Administration: write)")
    ap.add_argument("--private", action="store_true", help="создать приватным (Pages на приватном репо требует платный план)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=360)
    a = ap.parse_args()

    token = a.token.strip()
    if not token and not a.dry_run:
        raise SystemExit("нет токена: export GH_TOKEN=... или --token")
    if token and not re.match(r"^(github_pat_|ghp_)", token):
        print("⚠️ токен не похож на GitHub PAT (ожидается github_pat_… или ghp_…) — продолжаю, но проверьте")

    url = f"https://github.com/{a.owner}/{a.repo}"
    pages_url = f"https://{a.owner}.github.io/{a.repo}/"
    print(f"репозиторий : {url}")
    print(f"Pages URL   : {pages_url}")
    print(f"токен       : {MASK if token else '(нет)'} (длина {len(token)}, в лог не пишется)")
    print(f"каталог     : {ROOT}")
    if a.dry_run:
        print("\n[DRY-RUN] изменения не отправляются\n")

    # ── 1. локальный git ────────────────────────────────
    if not (ROOT / ".git").exists():
        run(["git", "init", "-q"], token)
    run(["git", "config", "user.email", "agent@xauusd.local"], token, quiet=True)
    run(["git", "config", "user.name", "xauusd-agent"], token, quiet=True)
    run(["git", "config", "core.autocrlf", "false"], token, quiet=True)

    # ── 2. сборка сайта до коммита ──────────────────────
    print("\n→ публичная сборка (SITE_PUBLIC=1): журнал диалога и sandbox-превью не публикуются")
    env = {**os.environ, "SITE_PUBLIC": "1"}
    for script in ["forward_collector.py", "dashboard.py", "build_site.py", "build_single_file.py"]:
        subprocess.run([sys.executable, script], cwd=str(ROOT), check=False, env=env)

    # контроль утечек перед коммитом
    leaks = []
    for f in list((ROOT / "site").rglob("*.html")) + [ROOT / "site_single.html"]:
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if "Журнал диалога" in txt or "Запись 1" in txt or "ghbdtn" in txt:
            leaks.append(str(f.relative_to(ROOT)))
    if leaks:
        raise SystemExit(f"СТОП: в публичной сборке найден журнал диалога: {leaks}")
    print("→ контроль утечек: журнал диалога в публичных файлах не найден ✓")

    run(["git", "add", "-A"], token, quiet=True)
    st = run(["git", "status", "--porcelain"], token, quiet=True)
    n_changed = len([x for x in (st.stdout or "").splitlines() if x.strip()])
    print(f"→ файлов к коммиту: {n_changed}")
    msg = f"site: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}"
    run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", msg], token, check=False)
    run(["git", "branch", "-M", "main"], token, quiet=True)

    tracked = [l for l in run(["git", "ls-files"], token, quiet=True).stdout.splitlines() if l.strip()]
    size = sum((ROOT / f).stat().st_size for f in tracked if (ROOT / f).exists())
    print(f"→ в репозиторий: {len(tracked)} файлов, {size/1024/1024:.1f} МБ (остальное в .gitignore)")

    if a.dry_run:
        print("\n[DRY-RUN] git push / Pages API пропущены")
        return 0

    # ── 3. существует ли репозиторий ────────────────────
    code, _ = api(f"/repos/{a.owner}/{a.repo}", token)
    if code == 404:
        if not a.create:
            raise SystemExit(f"репозитория {url} нет. Создайте пустой репозиторий (без README) "
                             f"или запустите с --create")
        print("→ создаю репозиторий")
        code, res = api("/user/repos", token, "POST",
                        {"name": a.repo, "private": bool(a.private), "auto_init": False,
                         "description": "XAUUSD Elliott Trading Agent — research dashboard"})
        if code not in (200, 201):
            raise SystemExit(f"не удалось создать репозиторий ({code}): {mask(str(res), token)}\n"
                             "Для --create токену нужно Administration: Read and write. "
                             "Либо создайте пустой репозиторий руками и повторите без --create.")
        if a.private:
            print("⚠️ репозиторий приватный: GitHub Pages для приватных репозиториев требует платный план. "
                  "Для бесплатной публичной ссылки нужен публичный репозиторий (или Netlify/Cloudflare Pages).")

    # ── 4. push (токен только здесь, в аргументе команды) ─
    print("→ git push")
    remote = f"https://x-access-token:{token}@github.com/{a.owner}/{a.repo}.git"
    r = subprocess.run(["git", "push", "--force", remote, "main"], cwd=str(ROOT),
                       capture_output=True, text=True)
    out = mask((r.stdout or "") + (r.stderr or ""), token)
    print("   " + "\n   ".join(out.strip().splitlines()[-6:]))
    if r.returncode != 0:
        raise SystemExit("push не удался — проверьте права токена (Contents: Read and write)")
    # подчищаем возможное попадание токена в конфиг
    run(["git", "remote", "remove", "origin"], token, check=False, quiet=True)

    # ── 5. включаем Pages на GitHub Actions ──────────────
    code, res = api(f"/repos/{a.owner}/{a.repo}/pages", token)
    if code == 404:
        print("→ включаю Pages (build_type=workflow)")
        code, res = api(f"/repos/{a.owner}/{a.repo}/pages", token, "POST", {"build_type": "workflow"})
        if code not in (200, 201, 204):
            print(f"⚠️ Pages API вернул {code}: {mask(str(res), token)}\n"
                  "   Включите вручную: Settings → Pages → Source: GitHub Actions")
    else:
        print(f"→ Pages уже настроен ({code})")

    # ── 6. ждём workflow и появления сайта ───────────────
    print(f"→ жду сборку и публикацию (до {a.timeout} c)")
    t0, seen_run = time.time(), False
    while time.time() - t0 < a.timeout:
        code, runs = api(f"/repos/{a.owner}/{a.repo}/actions/runs?per_page=5", token)
        if code == 200 and isinstance(runs, dict):
            for w in runs.get("workflow_runs", []):
                if not seen_run:
                    print(f"   workflow «{w.get('name')}» → {w.get('status')} / {w.get('conclusion')}")
                    seen_run = True
                if w.get("status") == "completed" and w.get("conclusion") == "success":
                    try:
                        with urllib.request.urlopen(pages_url, timeout=20) as pr:
                            if pr.status == 200:
                                print("\n✅ САЙТ ОПУБЛИКОВАН")
                                print(f"   {pages_url}")
                                print(f"   время: {time.time()-t0:.0f} c • автообновление: cron 06:30 и 20:30 UTC")
                                return 0
                    except Exception:
                        pass
        time.sleep(15)
    print(f"\n⚠️ за {a.timeout} c сайт не ответил. Проверьте:")
    print(f"   1. {url}/actions — статус workflow «site»")
    print(f"   2. {url}/settings/pages — Source: GitHub Actions")
    print(f"   3. {pages_url} (первая публикация занимает 1–3 минуты)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
