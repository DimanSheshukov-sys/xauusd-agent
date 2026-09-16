#!/usr/bin/env python3
"""Публикация БЕЗ workflow-файла: main (код/отчёты) + gh-pages (готовый сайт).

Зачем: пуш файлов `.github/workflows/*` требует у токена Actions: Read and write.
Если этого права нет (403), сайт всё равно публикуется:
  • main     — весь проект, но без .github/ (он в .gitignore, лежит на диске для будущего);
  • gh-pages — собранный `site/` в корне отдельной ветки;
  • Pages включается через API с source = branch gh-pages (legacy-режим).

Автообновления через Actions появятся позже, когда у токена будет Actions: R/W
(или при пуше с машины с classic-токеном scope=repo+workflow). До того сайт
обновляется повторным запуском этого скрипта.

    export GH_TOKEN=...
    python3 deploy_pages_branch.py --owner OWNER --repo REPO
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
MASK = "***"


def mask(s: str, token: str) -> str:
    return s.replace(token, MASK) if token else s


def api(path: str, token: str, method: str = "GET", body=None, base: str | None = None):
    url = (base or f"https://api.github.com/repos/{OWNER}/{REPO}") + path
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "xauusd-deploy",
                                          **({"Content-Type": "application/json"} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def sh(cmd: list[str], cwd: Path, token: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    out = mask((r.stdout or "") + (r.stderr or ""), token)
    if r.returncode != 0 and check:
        raise SystemExit(f"FAIL {' '.join(cmd)}\n{out[-800:]}")
    return r


OWNER = REPO = ""


def main() -> int:
    global OWNER, REPO
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    OWNER, REPO, token = a.owner, a.repo, a.token.strip()
    if not token:
        raise SystemExit("нет токена")
    pages_url = f"https://{OWNER.lower()}.github.io/{REPO}/"
    remote = f"https://x-access-token:{token}@github.com/{OWNER}/{REPO}.git"

    # 0) уборка возможных probe-файлов
    for p in ["/contents/_probe.txt"]:
        st, res = api(p, token)
        if st == 200 and isinstance(res, dict) and res.get("sha"):
            api(p, token, "DELETE", {"message": "cleanup probe", "sha": res["sha"]})
            print("→ probe-файл удалён")

    # 1) .github не должен попадать в git (лежит на диске для будущего пуша с Actions-write)
    gi = ROOT / ".gitignore"
    txt = gi.read_text(encoding="utf-8")
    if "\n.github/\n" not in f"\n{txt}":
        gi.write_text(txt.rstrip() + "\n\n# workflow публикуется отдельно, когда токен получит Actions: R/W\n.github/\n",
                      encoding="utf-8")

    # 2) публичная сборка
    print("→ публичная сборка (SITE_PUBLIC=1)")
    env = {**os.environ, "SITE_PUBLIC": "1"}
    for s in ["forward_collector.py", "dashboard.py", "build_site.py", "build_single_file.py"]:
        subprocess.run([sys.executable, s], cwd=str(ROOT), check=False, env=env)
    for f in list((ROOT / "site").rglob("*.html")) + [ROOT / "site_single.html"]:
        t = f.read_text(encoding="utf-8", errors="ignore")
        if "Журнал диалога" in t or "ghbdtn" in t:
            raise SystemExit(f"СТОП: утечка журнала в {f}")
    print("→ контроль утечек: OK")

    # 3) main одним коммитом без .github
    print("→ пересборка main (один коммит, без .github)")
    sh(["git", "branch", "-D", "main2"], ROOT, token, check=False)
    sh(["git", "checkout", "--orphan", "main2"], ROOT, token)
    sh(["git", "rm", "-r", "--cached", ".", "-q", "-f"], ROOT, token)
    sh(["git", "add", "-A"], ROOT, token)
    sh(["git", "-c", "commit.gpgsign=false", "commit", "-qm",
        f"site: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}"], ROOT, token)
    sh(["git", "branch", "-M", "main2", "main"], ROOT, token)
    n = len(sh(["git", "ls-files"], ROOT, token).stdout.splitlines())
    print(f"→ в main: {n} файлов")

    # 4) push main
    print("→ push main")
    r = subprocess.run(["git", "push", "--force", remote, "main"], cwd=str(ROOT), capture_output=True, text=True)
    print("   " + mask((r.stdout or r.stderr or "")[-300:], token).strip())
    if r.returncode != 0:
        raise SystemExit("push main не удался")

    # 5) gh-pages из site/
    print("→ gh-pages из site/")
    tmp = Path(tempfile.mkdtemp(prefix="ghpages_"))
    for item in (ROOT / "site").iterdir():
        dst = tmp / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)
    sh(["git", "init", "-q", "-b", "gh-pages"], tmp, token)
    sh(["git", "config", "user.email", "agent@xauusd.local"], tmp, token)
    sh(["git", "config", "user.name", "xauusd-agent"], tmp, token)
    sh(["git", "add", "-A"], tmp, token)
    sh(["git", "-c", "commit.gpgsign=false", "commit", "-qm",
        f"site build {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}"], tmp, token)
    r = subprocess.run(["git", "push", "--force", remote, "gh-pages"], cwd=str(tmp), capture_output=True, text=True)
    print("   " + mask((r.stdout or r.stderr or "")[-300:], token).strip())
    if r.returncode != 0:
        raise SystemExit("push gh-pages не удался")
    shutil.rmtree(tmp, ignore_errors=True)

    # 6) Pages: source = gh-pages
    st, res = api("/pages", token)
    if st == 404:
        print("→ включаю Pages (source: gh-pages /)")
        st, res = api("/pages", token, "POST", {"source": {"branch": "gh-pages", "path": "/"}})
        if st not in (200, 201, 204):
            raise SystemExit(f"Pages API: {st} {mask(str(res), token)}")
    elif st == 200 and isinstance(res, dict):
        cur = (res.get("source") or {}).get("branch")
        if cur != "gh-pages":
            api("/pages", token, "PUT", {"source": {"branch": "gh-pages", "path": "/"}})
            print("→ Pages переведён на ветку gh-pages")
        else:
            print("→ Pages уже на gh-pages")
    else:
        print(f"→ Pages статус {st}: {mask(str(res), token)}")

    # 7) ждём сайт
    print(f"→ жду {pages_url} (до {a.timeout} c)")
    t0 = time.time()
    while time.time() - t0 < a.timeout:
        try:
            with urllib.request.urlopen(pages_url, timeout=20) as pr:
                if pr.status == 200 and len(pr.read()) > 1000:
                    print(f"\n✅ САЙТ ОПУБЛИКОВАН: {pages_url}   ({time.time()-t0:.0f} c)")
                    print("   обновление: повторный запуск этого скрипта (Actions появятся позже)")
                    return 0
        except Exception:
            pass
        time.sleep(10)
    print(f"\n⚠️ сайт не ответил за {a.timeout} c — обычно публикуется за 1–3 минуты, проверьте {pages_url}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
