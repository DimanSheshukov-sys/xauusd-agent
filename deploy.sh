#!/usr/bin/env bash
# Деплой сайта XAUUSD Elliott Agent — одна команда до публичной ссылки.
#
#   ./deploy.sh serve              локальный сервер  → http://localhost:8000 (живой API)
#   ./deploy.sh tunnel             ПУБЛИЧНАЯ ссылка без аккаунта (cloudflared quick tunnel)
#   ./deploy.sh pages  <repo-url>  постоянная ссылка на GitHub Pages (автообновление 2 раза в сутки)
#   ./deploy.sh netlify            Netlify (приватный репозиторий допустим)
#   ./deploy.sh vercel             Vercel
#   ./deploy.sh single             собрать один self-contained HTML-файл
#
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}

need_py_deps() {
  $PY -c "import numpy, pandas, websocket" 2>/dev/null || {
    echo "→ ставлю зависимости (numpy, pandas, websocket-client)"; $PY -m pip install --quiet numpy pandas websocket-client; }
}

build_all() {
  need_py_deps
  echo "→ forward_collector (данные + дашборд)"; $PY forward_collector.py || true
  echo "→ build_site (сайт)";                      $PY build_site.py
}

cmd=${1:-serve}
case "$cmd" in

  serve)
    build_all
    echo; echo "Открывайте: http://localhost:${PORT:-8000}"
    exec $PY serve.py --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --interval "${INTERVAL:-900}"
    ;;

  tunnel)
    build_all
    CF=$(command -v cloudflared || true)
    if [ -z "$CF" ]; then
      OS=$(uname -s | tr '[:upper:]' '[:lower:]'); ARCH=$(uname -m)
      case "$OS-$ARCH" in
        linux-x86_64)  URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;;
        linux-aarch64) URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64" ;;
        darwin-*)      URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz" ;;
        *) echo "cloudflared для $OS-$ARCH скачайте вручную: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; exit 1 ;;
      esac
      echo "→ скачиваю cloudflared"; mkdir -p .bin
      case "$URL" in
        *.tgz) curl -fsSL "$URL" -o .bin/cf.tgz && tar -xzf .bin/cf.tgz -C .bin && mv .bin/cloudflared .bin/cloudflared-bin ;;
        *)     curl -fsSL "$URL" -o .bin/cloudflared-bin ;;
      esac
      chmod +x .bin/cloudflared-bin; CF=".bin/cloudflared-bin"
    fi
    $PY serve.py --host 127.0.0.1 --port "${PORT:-8000}" --interval "${INTERVAL:-900}" >.serve.log 2>&1 &
    SERVE_PID=$!
    trap 'kill $SERVE_PID 2>/dev/null || true' EXIT
    sleep 3
    echo; echo "→ поднимаю туннель. Публичная ссылка появится ниже (вида https://<случайное>.trycloudflare.com)"
    echo "  Ссылка жива, пока работает эта команда. Для постоянной — ./deploy.sh pages"
    echo "  Лог сервера: .serve.log"; echo
    exec $CF tunnel --url "http://127.0.0.1:${PORT:-8000}"
    ;;

  pages)
    REPO=${2:?"нужен URL репозитория: ./deploy.sh pages git@github.com:user/repo.git"}
    build_all
    git init -q 2>/dev/null || true
    [ -f .gitignore ] || printf '__pycache__/\n*.pyc\n.bin/\n.serve.log\ndata/*.csv\ndata/forward/*.csv\ndata/forward_sandbox/\n' > .gitignore
    git add -A
    git -c user.email="${GIT_EMAIL:-agent@local}" -c user.name="${GIT_NAME:-agent}" commit -qm "site: $(date -u +%F\ %H:%M) UTC" || echo "нечего коммитить"
    git branch -M main
    git remote remove origin 2>/dev/null || true
    git remote add origin "$REPO"
    git push -u origin main
    cat <<'TXT'

→ Готово. Теперь один раз включите публикацию:
   GitHub → Settings → Pages → Source: "GitHub Actions"
   (workflow .github/workflows/site.yml уже в репозитории — он будет обновлять сайт 2 раза в сутки)

   Ссылка будет вида: https://<user>.github.io/<repo>/
   Ручной перезапуск: вкладка Actions → site → Run workflow
TXT
    ;;

  netlify)
    build_all
    echo "→ netlify-cli (войдёте через браузер); сайт в site/"
    npx --yes netlify-cli deploy --dir=site --prod
    ;;

  vercel)
    build_all
    echo "→ vercel (войдёте через браузер)"
    npx --yes vercel --prod site
    ;;

  single)
    need_py_deps
    $PY forward_collector.py --no-dashboard || true
    $PY dashboard.py
    $PY build_single_file.py
    echo; echo "→ один файл: $(pwd)/site_single.html — открывается двойным кликом, можно отправить куда угодно"
    ;;

  *)
    echo "использование: ./deploy.sh {serve|tunnel|pages <repo-url>|netlify|vercel|single}"; exit 1 ;;
esac
