<div align="center">

<img src="assets/logo.svg" alt="httpcrabber" width="880">

<br>

**Перехватчик трафика сетевого уровня для реверс-инжиниринга веб-API.**
Невидим для JS-защит на странице — потому что вообще не заходит внутрь страницы.

[English](README.md) · **Русский** · [Español](README.es.md) · [中文](README.zh.md)

[![CI](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml/badge.svg)](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml)
[![Python 3.11+](assets/badge-python.svg)](https://www.python.org/)
[![Платформы Windows · macOS · Linux](assets/badge-platform.svg)](#требования)
[![Лицензия GPL-3.0](assets/badge-license.svg)](LICENSE)
[![На базе mitmproxy](assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

</div>

---

<p align="center">
  <img src="assets/screen-live.ru.svg" alt="Живая панель перехвата httpcrabber" width="100%">
</p>

<details>
<summary><b>Оглавление</b></summary>

- [Зачем](#зачем)
- [Возможности](#возможности)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Командная строка](#командная-строка)
- [Форматы прокси](#форматы-прокси)
- [Что сохраняется](#что-сохраняется)
- [Как это работает](#как-это-работает)
- [Безопасность](#-безопасность)
- [Ответственное использование](#ответственное-использование)
- [Участие в разработке](#участие-в-разработке)
- [Лицензия](#лицензия)

</details>

## Зачем

DevTools браузера можно обнаружить. Антибот-скрипты (Kasada, Cloudflare, Vercel BotID)
штатно проверяют, подключён ли отладчик, открыта ли панель разработчика и не подменён ли
сетевой стек изнутри страницы.

**httpcrabber работает ниже всего этого.** Это HTTPS-прокси на базе
[mitmproxy](https://mitmproxy.org/): трафик снимается на проводе, а не в странице.
С точки зрения JavaScript там просто ничего нет.

## Возможности

| | |
|---|---|
| 💚 **Анимированный hacker-CLI** | Матричный дождь, градиентный глитч-баннер, печатная машинка, цветные статус-бейджи, спиннеры на реальных ожиданиях |
| 📡 **Живая лента перехвата** | Запросы в реальном времени, подсветка методов и статус-кодов, счётчики, спарклайн трафика |
| 📊 **Аналитика сессии** | Топ хостов, разбивка по методам и статусам, длительность и размер дампа по завершении |
| 🧅 **Любой upstream-прокси** | `socks5` / `socks5h` / `socks4` / `http` / `https`, с авторизацией и без, во всех распространённых форматах |
| 🗂 **Своя папка на сессию** | Сетевой дамп и все скрипты вместе — сессию можно заархивировать или переслать целиком |
| 📜 **Полный сбор JavaScript** | Внешние бандлы и инлайновые `<script>`, целиком и с дедупликацией по SHA-256 |
| 🌐 **Chrome стартует сам** | Через прокси с отдельным профилем — или свой браузер через `--no-browser` |
| 🔐 **Автонастройка CA** | Сертификат проверяется и ставится при первом запуске — на Windows, macOS и Linux |
| ⌨️ **Скриптуется** | У каждого вопроса есть флаг; передай все — и ничего не спросит |
| ⏹ **Безопасное завершение** | Закрытие Chrome *или* `Ctrl+C` — дамп сохранён, дочерние процессы погашены в обоих случаях |
| 🌍 **Двуязычный интерфейс** | Русский и английский, выбор при старте или через `--lang` |

## Требования

- **Python 3.11+**
- **Google Chrome** или **Chromium** (не нужен при `--no-browser`)

| ОС | Поиск браузера | Установка CA-сертификата |
|---|---|---|
| **Windows** | Program Files, LocalAppData | `certutil -user` в пользовательское хранилище Root — Windows покажет один диалог подтверждения |
| **macOS** | `/Applications`, `~/Applications` | `security add-trusted-cert` в login keychain — macOS один раз спросит пароль |
| **Linux** | `google-chrome`, `chromium` в `PATH` | NSS-база `~/.pki/nssdb` через `certutil` из **libnss3-tools** (`sudo apt install libnss3-tools`) — именно её читает Chrome. У Firefox своё хранилище: там ставь через http://mitm.it |

Переменная `HTTPCRABBER_BROWSER=/путь/к/chrome` переопределяет поиск на любой ОС.

## Установка

```bash
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber --version
```

Или из клона, для разработки:

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client
python -m venv .venv && source .venv/bin/activate     # .venv\Scripts\Activate.ps1 на Windows
pip install -e ".[dev]"
```

Совсем без установки — `python run.py` прямо из клона.

## Быстрый старт

```bash
httpcrabber
```

Инструмент спросит три вещи, остальное сделает сам:

1. **Язык** — русский или английский
2. **Upstream-прокси** — вставь в любом формате или нажми <kbd>Enter</kbd> для прямого соединения
3. **Название сессии** — например `TARGET RECON`

<p align="center">
  <img src="assets/screen-start.ru.svg" alt="Старт httpcrabber: баннер, бриф сессии, статусы" width="100%">
</p>

Покажет бриф сессии, поставит CA-сертификат, если нужно, запустит Chrome через прокси и
начнёт писать всё в папку сессии. Просто пользуйся браузером — каждый запрос, ответ,
WebSocket-кадр и скрипт будут сохранены. Закрой Chrome (или нажми <kbd>Ctrl+C</kbd>) —
получишь панель аналитики и путь к папке.

<p align="center">
  <img src="assets/screen-summary.ru.svg" alt="Итоговая сводка сессии httpcrabber" width="100%">
</p>

## Командная строка

У каждого вопроса есть флаг. Передай все — и httpcrabber ничего не спросит, удобно для скриптов.

```bash
httpcrabber --lang ru --session "target recon" --proxy socks5://user:pass@1.2.3.4:1080
httpcrabber -l ru -s quick --direct --no-browser          # свой браузер / устройство
httpcrabber --no-anim                                      # без анимаций
```

| Флаг | Значение |
|---|---|
| `-l, --lang {ru,en}` | Язык интерфейса |
| `-s, --session NAME` | Название сессии → `LOGS/<name>/` |
| `-p, --proxy PROXY` | Upstream-прокси в любом [формате](#форматы-прокси) |
| `--direct` | Без upstream-прокси |
| `--port PORT` | Порт mitmproxy (по умолчанию `8080`; если занят — следующий свободный) |
| `-o, --output DIR` | Куда складывать сессии (по умолчанию `./LOGS`) |
| `--no-browser` | Не запускать Chrome — направь любой браузер или устройство на `127.0.0.1:<port>` |
| `--no-anim` | Отключить анимации |
| `-V, --version` | Показать версию |

## Форматы прокси

Понимаются все распространённые записи. Пустой ввод и <kbd>Enter</kbd> — прямое соединение.

```
host:port
host:port:user:pass
user:pass@host:port
socks5://user:pass@host:port
http://host:port
https://user:pass@host:port
```

Схемы: `http`, `https`, `socks5`, `socks5h`, `socks4`. Пароль в интерфейсе маскируется.

## Что сохраняется

Каждая сессия — самодостаточная папка:

```
LOGS/
└── target_recon/
    ├── target_recon.jsonl                     # сетевой дамп
    └── js/
        ├── index.json                         # манифест: url, файл, sha256, размер, hits
        ├── cdn.target.com/
        │   └── main.a3f1c8d4.js               # внешние скрипты
        └── target.com/
            └── inline/inline_0001.e5f6a7b8.js # инлайновые <script>
```

Если сессия с таким названием уже есть, добавляется `_2`, `_3` … — **ничего никогда не перезатирается**.

### Сетевой дамп

Один JSON-объект на строку, с полем `event`:
`request` · `response` · `ws_open` · `ws_msg` · `ws_close` · `error`.
Каждая запись сразу сбрасывается на диск — падение или жёсткое убийство процесса ничего не теряет.

### Собранный JavaScript

- **Скрипты сохраняются целиком.** Тела внутри `.jsonl` режутся на 200 КБ, а файлы в `js/` —
  полный исходник: минифицированный бандл на 5 МБ сохранится без обрезки.
- **Дубликаты схлопываются по SHA-256.** Один бандл, запрошенный сто раз, лежит на диске
  один раз, в манифесте у него `hits: 100`.
- **Инлайн-скрипты извлекаются** из HTML. Теги с `src=` пропускаются (они прилетят
  отдельным запросом), как и `application/ld+json` и `text/template` — это не код.
- В имени файла есть короткий хеш контента, поэтому разные сборки одного `app.js`
  не перезатирают друг друга.

## Как это работает

```mermaid
flowchart LR
    B["🌐 Chrome"] -->|HTTPS| M["🦀 mitmproxy<br/><sub>перехват</sub>"]
    M --> P["🔌 мост pproxy<br/><sub>адаптер схем</sub>"]
    P -->|"socks5 · http"| U["🧅 твой upstream-прокси"]
    U --> T["🎯 цель"]
    M -.-> F[("📁 LOGS/сессия<br/><sub>JSONL + JS</sub>")]

    classDef hop fill:#0b0f0c,stroke:#39ff14,color:#d6ded6,stroke-width:1.5px
    classDef core fill:#0b0f0c,stroke:#ff2fd0,color:#ffffff,stroke-width:2px
    classDef store fill:#0b0f0c,stroke:#00e5ff,color:#d6ded6,stroke-width:1.5px
    class B,P,U,T hop
    class M core
    class F store
```

mitmproxy нативно поддерживает только `http`/`https` в качестве upstream-прокси. Чтобы
**SOCKS5** работал прозрачно, httpcrabber поднимает локальный мост
[pproxy](https://github.com/qwj/python-proxy): он говорит по HTTP с mitmproxy и по любой
схеме — с твоим прокси. Оба перехода идут по loopback, накладные расходы ничтожны.

```
src/httpcrabber/
  cli.py       аргументы, диалог, main()
  session.py   оркестрация: мост → mitmproxy → CA → браузер → живой цикл
  capture.py   аддон mitmproxy: JSONL-дамп, сбор JS, живая статистика
  proxy.py     разбор upstream-прокси         bridge.py   мост pproxy
  ca.py        установка CA на каждой ОС      browser.py  поиск Chrome на каждой ОС
  ui.py        анимации, панели, лента        i18n.py     строки интерфейса
```

## ⚠️ Безопасность

**В перехваченном трафике лежат живые учётные данные.** Дампы сессий штатно содержат
заголовки `Cookie`, `Set-Cookie`, `Authorization`, API-ключи и токены всех сайтов,
которые ты открывал за сессию.

- `LOGS/` и `*.jsonl` исключены в [`.gitignore`](.gitignore) — **пусть так и остаётся**.
- Никогда не коммить, не выкладывать и не пересылать дамп сессии, не просмотрев его.
- Относись к папке сессии как к выгрузке из менеджера паролей. По сути это она и есть.
- Инструмент ставит локально сгенерированный корневой CA. В [SECURITY.md](SECURITY.md)
  описано, как его удалить, когда закончишь.

## Ответственное использование

Это инструмент для исследования безопасности, отладки API и работ по совместимости на
системах, которыми ты владеешь или которые тебе разрешено тестировать. Ответственность за
соблюдение законодательства, условий использования сайтов и приватности чужих данных лежит
на тебе. Не используй его для доступа к системам без разрешения.

## Участие в разработке

Issues и pull requests приветствуются — в [CONTRIBUTING.md](CONTRIBUTING.md) описаны
настройка, соглашения и добавление языка. Уязвимости — через [SECURITY.md](SECURITY.md).

```bash
ruff check src tests run.py && pytest
```

## Лицензия

[GNU General Public License v3.0](LICENSE) — полный текст в файле лицензии.
