# ДЕПЛОЙ САЙТА — от одной команды до постоянного хостинга

**Самое быстрое:**
```bash
cd xauusd_agent
./deploy.sh tunnel      # публичная ссылка https://<случайное>.trycloudflare.com — без аккаунта
./deploy.sh pages git@github.com:USER/REPO.git   # постоянная ссылка + автообновление 2 раза в сутки
./deploy.sh single      # один HTML-файл (site_single.html) — открыть или отправить куда угодно
```
Все режимы: `serve | tunnel | pages | netlify | vercel | single`.

Сайт — обычная статика (`site/`, 692 КБ, 13 страниц, без внешних зависимостей).
Живые KPI (цена/спред/решение) обновляются, когда сайт отдан **нашим сервером** `serve.py`
(фронт опрашивает `/api/live` каждые 20 c). При открытии `index.html` как файла или на
статическом хостинге он тоже работает — просто показывает последний собранный снимок
и живой график TradingView.

---

## Вариант T. Публичная ссылка без аккаунта — cloudflared quick tunnel

```bash
./deploy.sh tunnel
```
Скрипт поднимет `serve.py` на 127.0.0.1:8000, при необходимости скачает `cloudflared`
и откроет туннель — в консоли появится ссылка вида `https://xxxx-yyyy.trycloudflare.com`,
доступная из интернета. Работает живой API (`/api/live`), т.е. цена и решение обновляются
каждые 20 секунд. Ссылка жива, пока работает команда; адрес меняется при перезапуске.
Для постоянного адреса — варианты B (Pages) или N (Netlify/Vercel).

⚠️ Туннель публичный и без авторизации: не оставляйте его висящим надолго,
содержимое — ваша торговая методология.

---

## Вариант A. Локально или на своём VPS — живой сайт (рекомендую)

```bash
cd xauusd_agent
pip install numpy pandas websocket-client

python3 serve.py                                   # → http://localhost:8000
python3 serve.py --host 0.0.0.0 --port 8000 --interval 900   # доступно из сети + автообновление каждые 15 мин
```

Что получите:
- `/` — дашборд, **живая цена/спред/решение обновляются каждые 20 секунд** без перезагрузки;
- `/api/live` — JSON с текущей ценой, спредом, DXY, MTF-режимом, структурой и решением по §72;
- `/api/status` — состояние системы (forward OOS, датасеты, версия freeze, causality);
- `/api/refresh` — принудительно пересобрать (запускает `forward_collector.py` + `build_site.py`);
- `/healthz` — для мониторинга;
- фоновый поток раз в `--interval` секунд сам добирает бары GC=F и пересобирает сайт.

### systemd (чтобы жил постоянно)

`/etc/systemd/system/xauusd-site.service`:
```ini
[Unit]
Description=XAUUSD Elliott Agent site
After=network-online.target

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/xauusd_agent
ExecStart=/usr/bin/python3 /opt/xauusd_agent/serve.py --host 127.0.0.1 --port 8000 --interval 900
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now xauusd-site
journalctl -u xauusd-site -f
```

### nginx + TLS (порт наружу)

```nginx
server {
    listen 443 ssl http2;
    server_name agent.example.com;
    ssl_certificate     /etc/letsencrypt/live/agent.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agent.example.com/privkey.pem;

    # базовая авторизация — сайт содержит торговую аналитику, не публикуйте открыто
    auth_basic "restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 120s;          # /api/live может считаться до ~10 c
    }
}
```

⚠️ **Без авторизации наружу не выкладывайте**: `/api/refresh` запускает процессы,
а содержимое — ваша торговая методология. Минимум: basic auth, лучше — Cloudflare Access / VPN / WireGuard.

---

## Вариант B. Публичный URL без своего сервера — GitHub Pages

1. Создайте репозиторий, положите в него содержимое папки `xauusd_agent/` (включая `.github/workflows/site.yml`).
2. Settings → Pages → **Source: GitHub Actions**.
3. Готово: workflow уже настроен — дважды в сутки (06:30 и 20:30 UTC) он запускает
   `forward_collector.py` (добирает бары GC=F, считает forward-сделки, пересобирает дашборд)
   и `build_site.py`, затем публикует `site/`.
4. Адрес будет вида `https://<user>.github.io/<repo>/`.

Нюансы:
* **Живой цены не будет** (нет серверной части) — снимок обновляется по расписанию, а виджет
  TradingView на странице показывает реальный график в любом случае.
* Репозиторий для бесплатного Pages должен быть **публичным**. Если методологию публиковать
  не хочется — возьмите приватный репозиторий + Cloudflare Pages / Netlify / Vercel (там приватные
  репозитории поддерживаются), а доступ закройте Cloudflare Access.
* Для Cloudflare Pages: build command `pip install numpy pandas websocket-client && python forward_collector.py && python build_site.py`, output directory `site`.

---

## Вариант S. Один файл вместо сайта

```bash
./deploy.sh single        # → site_single.html (358 КБ, 12 вкладок)
```
Внутри: дашборд + Experiment v2/v3 + Walk-forward + канон v1.8 + freeze v1/v2 + аудит +
pre-registration + README + деплой + журнал. Никаких внешних зависимостей, открывается
двойным кликом, можно отправить в мессенджере, приложить к письму или залить на любой хостинг.
Живой опрос `/api/live` в режиме файла молча отключается — остаётся снимок и виджет TradingView.

---

## Вариант C. Просто открыть собранный сайт

```bash
python3 build_site.py          # пересобрать
xdg-open site/index.html       # или открыть в браузере
```
Работает всё, кроме автообновления KPI (нужен сервер) — виджет TradingView грузится, если есть сеть.

---

## Регламент обновления

| Что | Как часто | Команда |
|---|---|---|
| Данные forward OOS + дашборд + сайт | раз в сутки (достаточно) | `python3 forward_collector.py` (сам пересоберёт дашборд, а в варианте B — и сайт) |
| Полный пересчёт исследований | после изменений freeze | `python3 run_experiment.py && python3 walkforward.py && python3 v2_validation.py` |
| Тест причинности | после любых правок движка | `python3 tests/test_causality.py 8` |
| Сайт целиком | после отчётов | `python3 build_site.py` |

## Структура сайта

```text
site/
├── index.html                     дашборд (18 панелей, живые KPI через /api/live)
├── reports/                       EXPERIMENT_v2, EXPERIMENT_v3, WALKFORWARD_v2
├── docs/                          канон v1.8, freeze v1/v2, аудит, pre-registration, README, журнал
└── data/                          trades_*.csv, forward_signals.csv, collection_log.jsonl, status.json
```

## Проверено

* `serve.py`: `/` 200 (114 КБ), `/api/live` 200 (живая цена/спред/решение, кэш 60 c → повторный запрос 0.00 s),
  `/api/status` 200, `/api/refresh` 200 (запускает коллектор и сборку), `/docs/*`, `/reports/*`, `/data/*` 200.
* `build_site.py`: 13 страниц, 692 КБ, навигация с корректными относительными путями на всех уровнях.
