"""
httpcrabber — hackotron-style сетевой перехватчик на базе mitmproxy.

Возможности:
  • Красивый CLI (rich + questionary), выбор языка RU / ENG.
  • Свой upstream-прокси в любом формате (socks5 / http / https, с авторизацией
    и без) — подключается через локальный мост pproxy, поверх него mitmproxy.
  • Своя папка на сессию: LOGS/<имя_сессии>/ — внутри сетевой дамп <имя>.jsonl
    и js/ со всеми скриптами, которые прилетели браузеру.
  • Chrome стартует сам, через прокси и с отдельным профилем.
  • CA-сертификат mitmproxy проверяется и при отсутствии ставится автоматически.
  • Сессия завершается при закрытии Chrome ИЛИ по Ctrl+C — лог сохраняется в обоих
    случаях.

Запуск:
    python httpcrabber.py

---
Copyright (C) 2026  web3daemon

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. This program is distributed WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details <https://www.gnu.org/licenses/>.
"""

import asyncio
import atexit
import hashlib
import json
import os
import random
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from mitmproxy import http, options
from mitmproxy.certs import CertStore
from mitmproxy.tools.dump import DumpMaster

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import questionary
from questionary import Style as QStyle

# На Windows консоль по умолчанию может быть в cp1251 — юникод-рамки и символы
# роняют вывод с UnicodeEncodeError. Принудительно переводим потоки в UTF-8.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
#  Конфигурация
# ─────────────────────────────────────────────────────────────────────────────

LOG_DIR = Path("LOGS")
PROFILE_DIR = Path("chrome_profile_proxy")
CONFDIR = Path.home() / ".mitmproxy"
CA_CERT = CONFDIR / "mitmproxy-ca-cert.cer"

MAX_BODY_SIZE = 200_000
DEFAULT_PROXY_PORT = 8080      # порт, который слушает mitmproxy (в него ходит Chrome)
DEFAULT_BRIDGE_PORT = 8081     # порт локального моста pproxy (в него ходит mitmproxy)

# Палитра hackotron
C_NEON = "bold #39ff14"
C_CYAN = "bold #00e5ff"
C_MAG = "bold #ff2fd0"
C_DIM = "#5f6f5f"
C_WARN = "bold #ffcc00"
C_ERR = "bold #ff3b3b"

console = Console()

Q_STYLE = QStyle([
    ("qmark", "fg:#39ff14 bold"),
    ("question", "fg:#00e5ff bold"),
    ("answer", "fg:#ff2fd0 bold"),
    ("pointer", "fg:#39ff14 bold"),
    ("highlighted", "fg:#39ff14 bold"),
    ("selected", "fg:#00e5ff"),
    ("instruction", "fg:#5f6f5f"),
])


# ─────────────────────────────────────────────────────────────────────────────
#  Локализация
# ─────────────────────────────────────────────────────────────────────────────

STRINGS = {
    "ru": {
        "subtitle": "невидимый перехват трафика · mitmproxy + upstream-прокси",
        "ask_lang": "Выбери язык / Select language",
        "ask_proxy": "Твой upstream-прокси (Enter — без прокси, прямое соединение):",
        "proxy_hint": "форматы: host:port · host:port:user:pass · user:pass@host:port · socks5://user:pass@host:port",
        "proxy_none": "Прокси не задан — работаем напрямую через mitmproxy.",
        "proxy_ok": "Прокси распознан:",
        "proxy_bad": "Не смог разобрать прокси, попробуй ещё раз.",
        "ask_session": "Название сессии (напр. GOOGLE LOG):",
        "session_bad": "Название пустое — введи что-нибудь.",
        "log_to": "Папка сессии:",
        "ca_checking": "Проверяю CA-сертификат mitmproxy…",
        "ca_ok": "CA-сертификат уже установлен ✓",
        "ca_installing": "CA не найден — устанавливаю в хранилище (подтверди окно Windows)…",
        "ca_done": "CA-сертификат установлен ✓",
        "ca_fail": "Не удалось поставить CA автоматически. Открой http://mitm.it в этом Chrome и поставь вручную.",
        "bridge_start": "Поднимаю мост pproxy для upstream-прокси…",
        "bridge_ok": "Мост pproxy готов ✓",
        "bridge_fail": "Мост pproxy не поднялся — проверь прокси.",
        "chrome_start": "Запускаю Chrome через прокси…",
        "chrome_none": "Chrome не найден. Укажи путь к chrome.exe вручную.",
        "live_title": "СЕССИЯ АКТИВНА",
        "l_session": "Сессия",
        "l_proxy": "Upstream",
        "l_listen": "mitmproxy",
        "l_log": "Лог",
        "l_req": "Запросы",
        "l_resp": "Ответы",
        "l_ws": "WebSocket",
        "l_js": "JS-скрипты",
        "l_err": "Ошибки",
        "l_time": "Время",
        "feed_title": "ПЕРЕХВАТ В РЕАЛЬНОМ ВРЕМЕНИ",
        "waiting": "ожидание трафика…",
        "boot": "инициализация ядра перехвата",
        "live_hint": "Закрой Chrome или нажми Ctrl+C, чтобы завершить и сохранить сессию.",
        "ending": "Завершаю сессию, сохраняю лог…",
        "summary": "СЕССИЯ ЗАВЕРШЕНА",
        "s_saved": "Папка сессии",
        "s_size": "Размер дампа",
        "bye": "Удачной охоты, оператор.",
        "direct": "прямое соединение",
    },
    "en": {
        "subtitle": "invisible traffic capture · mitmproxy + upstream proxy",
        "ask_lang": "Select language / Выбери язык",
        "ask_proxy": "Your upstream proxy (Enter — no proxy, direct connection):",
        "proxy_hint": "formats: host:port · host:port:user:pass · user:pass@host:port · socks5://user:pass@host:port",
        "proxy_none": "No proxy set — going direct through mitmproxy.",
        "proxy_ok": "Proxy parsed:",
        "proxy_bad": "Could not parse the proxy, try again.",
        "ask_session": "Session name (e.g. GOOGLE LOG):",
        "session_bad": "Empty name — type something.",
        "log_to": "Session folder:",
        "ca_checking": "Checking mitmproxy CA certificate…",
        "ca_ok": "CA certificate already installed ✓",
        "ca_installing": "CA not found — installing into store (confirm the Windows dialog)…",
        "ca_done": "CA certificate installed ✓",
        "ca_fail": "Could not install CA automatically. Open http://mitm.it in this Chrome and install it manually.",
        "bridge_start": "Starting pproxy bridge for the upstream proxy…",
        "bridge_ok": "pproxy bridge ready ✓",
        "bridge_fail": "pproxy bridge failed to start — check the proxy.",
        "chrome_start": "Launching Chrome through the proxy…",
        "chrome_none": "Chrome not found. Provide the path to chrome.exe manually.",
        "live_title": "SESSION LIVE",
        "l_session": "Session",
        "l_proxy": "Upstream",
        "l_listen": "mitmproxy",
        "l_log": "Log",
        "l_req": "Requests",
        "l_resp": "Responses",
        "l_ws": "WebSocket",
        "l_js": "JS scripts",
        "l_err": "Errors",
        "l_time": "Uptime",
        "feed_title": "LIVE INTERCEPT",
        "waiting": "waiting for traffic…",
        "boot": "initializing intercept core",
        "live_hint": "Close Chrome or press Ctrl+C to finish and save the session.",
        "ending": "Finishing session, saving log…",
        "summary": "SESSION FINISHED",
        "s_saved": "Session folder",
        "s_size": "Dump size",
        "bye": "Happy hunting, operator.",
        "direct": "direct connection",
    },
}


class T:
    """Мини-хелпер для перевода по текущему языку."""
    lang = "ru"

    @classmethod
    def __call__(cls, key):
        return STRINGS[cls.lang].get(key, key)


t = T()


# ─────────────────────────────────────────────────────────────────────────────
#  Разбор прокси в любом формате
# ─────────────────────────────────────────────────────────────────────────────

_SCHEME_MAP = {
    "socks5": "socks5", "socks5h": "socks5", "socks": "socks5", "socks4": "socks4",
    "http": "http", "https": "http",  # https-прокси провайдеров = обычный HTTP CONNECT
}


def parse_proxy(raw: str):
    """Разбирает строку прокси в любом распространённом формате.

    Поддержка:
        host:port
        host:port:user:pass
        user:pass@host:port
        scheme://host:port
        scheme://user:pass@host:port
        scheme://host:port:user:pass
    Возвращает dict или None (если строка пустая). Кидает ValueError на мусоре.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    scheme = "http"
    rest = raw
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme = scheme.lower().strip()

    user = password = None

    if "@" in rest:
        cred, hostpart = rest.rsplit("@", 1)
        if ":" in cred:
            user, password = cred.split(":", 1)
        else:
            user = cred
    else:
        hostpart = rest

    parts = hostpart.split(":")
    if len(parts) == 2:
        host, port = parts
    elif len(parts) == 4:            # host:port:user:pass
        host, port, user, password = parts
    elif len(parts) == 3:            # host:port:user
        host, port, user = parts
    else:
        raise ValueError(f"bad proxy: {raw!r}")

    host = host.strip()
    port = int(str(port).strip())
    if not host or not (0 < port < 65536):
        raise ValueError(f"bad host/port: {raw!r}")

    pscheme = _SCHEME_MAP.get(scheme, "http")
    uri = f"{pscheme}://{host}:{port}"
    if user:
        uri += f"#{user}:{password or ''}"

    masked = f"{scheme}://"
    if user:
        masked += f"{user}:{'*' * len(password or '')}@"
    masked += f"{host}:{port}"

    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "pproxy_uri": uri,      # то, что скармливаем pproxy (-r ...)
        "display": masked,      # для показа в UI (пароль скрыт)
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Аддон-логгер mitmproxy
# ─────────────────────────────────────────────────────────────────────────────

class JSCollector:
    """Складывает в папку сессии весь JavaScript, который прилетает браузеру.

    Берём два источника:
      • внешние скрипты — ответы с javascript-типом либо путём .js/.mjs;
      • инлайновые <script> из HTML-страниц (у которых нет src=).

    Скрипты сохраняются ЦЕЛИКОМ (в отличие от тел в .jsonl, которые режутся по
    MAX_BODY_SIZE). Дубликаты схлопываются по sha256 — один и тот же бандл,
    запрошенный сто раз, лежит на диске один раз, а в манифесте у него счётчик.
    """

    _JS_HINTS = ("javascript", "ecmascript")
    _SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
    _TYPE_RE = re.compile(r"""type\s*=\s*["']?([^"'\s>]+)""", re.I)
    _SRC_RE = re.compile(r"\bsrc\s*=", re.I)

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.by_hash = {}        # sha256 -> относительный путь (дедупликация)
        self.index = {}          # (url, sha256) -> запись манифеста
        self.saved = 0           # сколько уникальных файлов записано
        self._inline_n = 0

    @classmethod
    def is_js(cls, url: str, content_type: str) -> bool:
        ct = (content_type or "").lower()
        if any(h in ct for h in cls._JS_HINTS):
            return True
        return urlsplit(url).path.lower().endswith((".js", ".mjs"))

    def _rel_path(self, url: str, kind: str, digest: str) -> Path:
        parts = urlsplit(url)
        host = re.sub(r"[^\w.\-]", "_", parts.netloc) or "unknown"
        if kind == "inline":
            self._inline_n += 1
            return Path(host) / "inline" / f"inline_{self._inline_n:04d}.{digest[:8]}.js"
        stem, ext = os.path.splitext(os.path.basename(parts.path) or "script")
        if ext.lower() not in (".js", ".mjs"):
            ext = ".js"
        stem = re.sub(r"[^\w.\-]", "_", stem)[:60] or "script"
        return Path(host) / f"{stem}.{digest[:8]}{ext}"

    def _store(self, url: str, text: str, kind: str):
        if not text or not text.strip():
            return
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        with self.lock:
            rel = self.by_hash.get(digest)
            if rel is None:
                rel = self._rel_path(url, kind, digest)
                try:
                    target = self.root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8", errors="replace")
                except OSError:
                    return          # длинный путь / нет прав — просто пропускаем
                self.by_hash[digest] = rel
                self.saved += 1

            key = (url, digest)
            entry = self.index.get(key)
            if entry is None:
                self.index[key] = {
                    "url": url,
                    "file": str(rel).replace("\\", "/"),
                    "kind": kind,
                    "sha256": digest,
                    "size": len(text),
                    "first_seen": datetime.now().isoformat(timespec="seconds"),
                    "hits": 1,
                }
            else:
                entry["hits"] += 1

    def store_external(self, url: str, text: str):
        self._store(url, text, "external")

    def harvest_html(self, url: str, html: str):
        """Достаёт инлайновые <script> из HTML. Внешние (src=) пропускаем —
        они прилетят отдельным запросом и сохранятся как external."""
        for attrs, body in self._SCRIPT_RE.findall(html):
            if self._SRC_RE.search(attrs):
                continue
            m = self._TYPE_RE.search(attrs)
            if m:
                stype = m.group(1).lower()
                if not any(h in stype for h in self._JS_HINTS) and "module" not in stype:
                    continue     # json-ld, x-template и прочее — не код
            self._store(url, body, "inline")

    def finalize(self):
        """Пишет манифест index.json рядом со скриптами."""
        if not self.index:
            return
        manifest = sorted(self.index.values(), key=lambda e: (-e["hits"], e["url"]))
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / "index.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


class NetworkLogger:
    def __init__(self, path: Path, js_dir: Path | None = None):
        self.path = path
        self.fp = path.open("w", encoding="utf-8", buffering=1)  # line-buffered = краш-безопасно
        self.lock = threading.Lock()
        self.js = JSCollector(js_dir) if js_dir else None
        self.stats = {"request": 0, "response": 0, "ws": 0, "error": 0, "js": 0}
        self.feed = deque(maxlen=200)   # живая лента для CLI: (время, тег, код, url)

    def _feed(self, tag, code, url):
        self.feed.append((datetime.now().strftime("%H:%M:%S"), tag, code, url or ""))

    def feed_tail(self, n):
        return list(self.feed)[-n:]

    def _log(self, event_type, stat_key, **data):
        entry = {"ts": datetime.now().isoformat(timespec="milliseconds"),
                 "event": event_type, **data}
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self.lock:
            self.fp.write(line)
            self.stats[stat_key] += 1

    def request(self, flow: http.HTTPFlow):
        req = flow.request
        body = None
        if req.content:
            try:
                body = req.get_text(strict=False)
                if len(body) > MAX_BODY_SIZE:
                    body = body[:MAX_BODY_SIZE] + "...[TRUNCATED]"
            except Exception:
                body = f"[binary, {len(req.content)} bytes]"
        self._log("request", "request",
                  url=req.pretty_url, method=req.method, http_version=req.http_version,
                  client_addr=str(flow.client_conn.peername) if flow.client_conn else None,
                  headers=dict(req.headers), body=body)

    def response(self, flow: http.HTTPFlow):
        if not flow.response:
            return
        resp = flow.response
        url = flow.request.pretty_url
        body = None
        if resp.content:
            ct = resp.headers.get("content-type", "").lower()
            if any(x in ct for x in ("json", "text", "javascript", "xml", "html", "x-www-form")):
                full = None
                try:
                    full = resp.get_text(strict=False)
                except Exception:
                    body = f"[unreadable: {len(resp.content)} bytes]"

                if full is not None:
                    # JS собираем из ПОЛНОГО тела — до обрезки для лога.
                    if self.js:
                        try:
                            if JSCollector.is_js(url, ct):
                                self.js.store_external(url, full)
                            elif "html" in ct:
                                self.js.harvest_html(url, full)
                            self.stats["js"] = self.js.saved
                        except Exception:
                            pass    # сбор скриптов не должен ронять перехват
                    body = full
                    if len(body) > MAX_BODY_SIZE:
                        body = body[:MAX_BODY_SIZE] + "...[TRUNCATED]"
            else:
                body = f"[binary, {len(resp.content)} bytes, {ct}]"
        self._feed(flow.request.method, resp.status_code, url)
        self._log("response", "response",
                  url=url, status=resp.status_code, reason=resp.reason,
                  http_version=resp.http_version, headers=dict(resp.headers), body=body)

    def websocket_start(self, flow):
        self._log("ws_open", "ws", url=flow.request.pretty_url)

    def websocket_message(self, flow):
        if not flow.websocket or not flow.websocket.messages:
            return
        msg = flow.websocket.messages[-1]
        try:
            content = msg.content.decode("utf-8", errors="replace")
        except Exception:
            content = f"[binary, {len(msg.content)} bytes]"
        if len(content) > MAX_BODY_SIZE:
            content = content[:MAX_BODY_SIZE] + "...[TRUNCATED]"
        self._feed("WS", "→" if msg.from_client else "←", flow.request.pretty_url)
        self._log("ws_msg", "ws", url=flow.request.pretty_url,
                  from_client=msg.from_client, content=content)

    def websocket_end(self, flow):
        self._log("ws_close", "ws", url=flow.request.pretty_url)

    def error(self, flow):
        url = flow.request.pretty_url if flow.request else None
        self._feed("ERR", None, url)
        self._log("error", "error", url=url, error=str(flow.error) if flow.error else None)

    def done(self):
        if self.js:
            try:
                self.js.finalize()
            except Exception:
                pass
        try:
            self.fp.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Инфраструктура: порты, CA, Chrome, мост
# ─────────────────────────────────────────────────────────────────────────────

# Реестр дочерних процессов (Chrome, мост pproxy). На жёстком Ctrl+C на Windows
# KeyboardInterrupt может пролететь мимо finally внутри сессии — тогда очистку
# гарантируют atexit и finally в main(), чтобы не оставлять процессы-сироты.
_CHILD_PROCS: list = []


def _register_proc(proc):
    if proc is not None:
        _CHILD_PROCS.append(proc)
    return proc


def cleanup_procs():
    for proc in _CHILD_PROCS:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    _CHILD_PROCS.clear()


atexit.register(cleanup_procs)


def free_port(preferred: int) -> int:
    """Возвращает preferred, если свободен, иначе первый свободный выше него.

    Проверяем через bind (мгновенно и надёжно), а не connect — connect к порту,
    который молча дропает SYN, может висеть на TCP-таймауте.
    """
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


async def wait_port(host: str, port: int, timeout: float = 8.0) -> bool:
    """Ждёт, пока порт начнёт принимать соединения."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)   # без таймаута connect может зависнуть
            try:
                if s.connect_ex((host, port)) == 0:
                    return True
            except OSError:
                pass
        await asyncio.sleep(0.15)
    return False


def ca_installed() -> bool:
    try:
        out = subprocess.run(["certutil", "-user", "-store", "Root"],
                             capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="ignore")
        return "mitmproxy" in (out.stdout or "").lower()
    except Exception:
        return False


def ensure_ca():
    """Генерирует CA (если нужно) и ставит его в пользовательское хранилище Root."""
    step(t("ca_checking"), "work")
    CONFDIR.mkdir(exist_ok=True)
    CertStore.from_store(str(CONFDIR), "mitmproxy", 2048)   # создаст файлы, если их нет

    if ca_installed():
        step(t("ca_ok"))
        return
    step(t("ca_installing"), "work")
    try:
        subprocess.run(["certutil", "-user", "-addstore", "-f", "Root", str(CA_CERT)],
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="ignore")
    except Exception:
        pass
    if ca_installed():
        step(t("ca_done"))
    else:
        step(t("ca_fail"), "fail")


def find_chrome():
    for var in ("%ProgramFiles%", "%ProgramFiles(x86)%", "%LocalAppData%"):
        path = Path(os.path.expandvars(var)) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if path.is_file():
            return str(path)
    return None


def launch_chrome(proxy_port: int):
    exe = find_chrome()
    if not exe:
        console.print(f"[{C_ERR}]{t('chrome_none')}[/]")
        return None
    PROFILE_DIR.mkdir(exist_ok=True)
    args = [
        exe,
        f"--proxy-server=http://127.0.0.1:{proxy_port}",
        f"--user-data-dir={PROFILE_DIR.absolute()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]
    return _register_proc(subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


def start_bridge(pproxy_uri: str, bridge_port: int):
    """Локальный мост: слушает http на bridge_port, форвардит в upstream (любая схема)."""
    args = [sys.executable, "-m", "pproxy",
            "-l", f"http://127.0.0.1:{bridge_port}",
            "-r", pproxy_uri]
    return _register_proc(subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


# ─────────────────────────────────────────────────────────────────────────────
#  Оформление
# ─────────────────────────────────────────────────────────────────────────────

BANNER = r"""
 ██╗  ██╗████████╗████████╗██████╗  ██████╗██████╗  █████╗ ██████╗ ███████╗██████╗
 ██║  ██║╚══██╔══╝╚══██╔══╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
 ███████║   ██║      ██║   ██████╔╝██║     ██████╔╝███████║██████╔╝█████╗  ██████╔╝
 ██╔══██║   ██║      ██║   ██╔═══╝ ██║     ██╔══██╗██╔══██║██╔══██╗██╔══╝  ██╔══██╗
 ██║  ██║   ██║      ██║   ██║     ╚██████╗██║  ██║██║  ██║██████╔╝███████╗██║  ██║
 ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝      ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
"""


# ── Анимации ────────────────────────────────────────────────────────────────

ANIM = "--no-anim" not in sys.argv     # запуск с --no-anim отключает всю анимацию

_RAIN_CHARS = "01<>[]{}/\\|=+*#$%&@?!ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾅﾆﾇﾈﾊﾋﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ"
_RAIN_SHADES = ["#0a2f0a", "#0f5c0f", "#179317", "#25cc1b", "#39ff14", "#b9ffb0"]
_GLITCH_CHARS = "▓▒░#@%&$/\\|=+*<>"
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_BLOCKS = " ▁▂▃▄▅▆▇█"


def matrix_rain(seconds=1.4, fps=18):
    """Матричный дождь на старте."""
    if not ANIM:
        return
    width = max(20, min(console.width, 120))
    height = max(6, min(12, console.height - 4))
    heads = [random.randint(-height, 0) for _ in range(width)]
    tail = len(_RAIN_SHADES)

    with Live(console=console, refresh_per_second=fps, transient=True) as live:
        end = time.time() + seconds
        while time.time() < end:
            rows = [[(" ", None)] * width for _ in range(height)]
            for x, head in enumerate(heads):
                for depth in range(tail):
                    y = head - depth
                    if 0 <= y < height:
                        shade = _RAIN_SHADES[tail - 1 - depth]
                        rows[y][x] = (random.choice(_RAIN_CHARS), shade)
                if random.random() > 0.12:
                    heads[x] += 1
                if heads[x] - tail > height:
                    heads[x] = random.randint(-height, 0)

            frame = Text()
            for row in rows:
                for ch, style in row:
                    frame.append(ch, style=style)
                frame.append("\n")
            live.update(frame)
            time.sleep(1 / fps)


def glitch_banner(frames=9):
    """Баннер «проявляется» из помех."""
    lines = BANNER.strip("\n").split("\n")
    if not ANIM:
        return
    with Live(console=console, refresh_per_second=24, transient=True) as live:
        for i in range(frames):
            noise = 0.45 * (1 - i / max(1, frames - 1))
            out = Text()
            for line in lines:
                for ch in line:
                    if ch != " " and random.random() < noise:
                        out.append(random.choice(_GLITCH_CHARS),
                                   style=random.choice([C_MAG, C_CYAN, C_WARN]))
                    else:
                        out.append(ch, style=C_NEON)
                out.append("\n")
            live.update(Align.center(out))
            time.sleep(0.045)


def typewriter(text, style=C_CYAN, delay=0.014, center=True):
    """Печатает строку посимвольно."""
    if not ANIM:
        console.print(Align.center(Text(text, style=style)) if center else Text(text, style=style))
        return
    with Live(console=console, refresh_per_second=60, transient=True) as live:
        for i in range(1, len(text) + 1):
            chunk = Text(text[:i], style=style)
            chunk.append("▌", style=C_NEON)
            live.update(Align.center(chunk) if center else chunk)
            time.sleep(delay)
    console.print(Align.center(Text(text, style=style)) if center else Text(text, style=style))


def step(msg, status="ok"):
    """Строка статуса вида [ OK ] сообщение."""
    mark, color = {"ok": ("OK", C_NEON), "fail": ("!!", C_ERR), "work": ("··", C_WARN)}[status]
    console.print(f"[{C_DIM}][[/][{color}] {mark} [/][{C_DIM}]][/] {msg}")


async def spin_until(coro_fn, msg, timeout=8.0):
    """Крутит спиннер, пока ждём готовности (используется для моста)."""
    task = asyncio.ensure_future(coro_fn())
    i = 0
    if ANIM:
        with Live(console=console, refresh_per_second=15, transient=True) as live:
            while not task.done():
                live.update(Text(f" {_SPINNER[i % len(_SPINNER)]}  {msg}", style=C_WARN))
                i += 1
                await asyncio.sleep(1 / 15)
    return await task


def sparkline(values, width=34):
    vals = list(values)[-width:]
    if not vals:
        return ""
    top = max(vals) or 1
    return "".join(_BLOCKS[min(8, int(v / top * 8))] for v in vals)


def show_banner():
    console.clear()
    matrix_rain()
    glitch_banner()
    art = Text(BANNER, style=C_NEON)
    console.print(Panel(Align.center(art), border_style=C_MAG, padding=(0, 2)))
    typewriter(t("subtitle"), style=C_CYAN)
    console.print()


_METHOD_STYLE = {"GET": C_CYAN, "POST": C_MAG, "PUT": C_WARN,
                 "PATCH": C_WARN, "DELETE": C_ERR, "WS": C_MAG, "ERR": C_ERR}


def _status_style(code):
    if not isinstance(code, int):
        return C_MAG
    if code < 300:
        return C_NEON
    if code < 400:
        return C_CYAN
    if code < 500:
        return C_WARN
    return C_ERR


def render_feed(logger, rows, width) -> Text:
    """Живая лента перехваченных запросов."""
    tail = logger.feed_tail(rows)
    if not tail:
        return Text(f"   {t('waiting')}", style=C_DIM)
    out = Text()
    avail = max(12, width - 24)
    for ts, tag, code, url in tail:
        out.append(f" {ts}  ", style=C_DIM)
        out.append(f"{str(tag)[:6]:<7}", style=_METHOD_STYLE.get(tag, "white"))
        out.append(f"{str(code) if code is not None else '···':<4} ", style=_status_style(code))
        out.append(url if len(url) <= avail else url[:avail - 1] + "…", style="white")
        out.append("\n")
    return out


def render_live(cfg, logger, start_ts, rate, frame) -> Panel:
    elapsed = int(time.time() - start_ts)
    clock = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
    s = logger.stats
    width = min(console.width, 118) - 8

    head = Table.grid(padding=(0, 2))
    head.add_column(justify="right", style=C_DIM)
    head.add_column(style="bold white")
    head.add_row(t("l_session"), f"[{C_MAG}]{cfg['session']}[/]")
    head.add_row(t("l_proxy"), cfg["proxy"]["display"] if cfg["proxy"] else t("direct"))
    head.add_row(t("l_listen"), f"127.0.0.1:{cfg['proxy_port']}")
    head.add_row(t("l_log"), str(cfg["session_dir"]))

    spin = _SPINNER[frame % len(_SPINNER)] if ANIM else "●"
    feed_head = Text(f" {spin}  {t('feed_title')}", style=C_NEON)

    # Короткие теги, а не полные подписи: строка должна влезать в одну линию,
    # иначе спарклайн переносится и панель разъезжается.
    bar = Text()
    for label, value, color in (
        ("REQ", s["request"], C_CYAN),
        ("RESP", s["response"], C_NEON),
        ("WS", s["ws"], C_MAG),
        ("JS", s.get("js", 0), C_WARN),
        ("ERR", s["error"], C_ERR if s["error"] else C_DIM),
    ):
        bar.append(f" {label} ", style=C_DIM)
        bar.append(f"{value}", style=color)
    bar.append(f"   {sparkline(rate, 22)}", style=C_NEON)
    bar.append(f"  {clock}", style=C_CYAN)

    body = Group(head, Text(""), feed_head, render_feed(logger, 12, width),
                 Text(""), bar, Text(""), Align.center(Text(t("live_hint"), style=C_DIM)))
    return Panel(body, title=f"[{C_NEON}]● {t('live_title')}[/]",
                 border_style=C_NEON, padding=(1, 2))


# ─────────────────────────────────────────────────────────────────────────────
#  Диалог настройки
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_session(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name.strip()).strip("_").lower()
    return slug or "session"


def unique_session_dir(slug: str) -> Path:
    """Отдельная папка на сессию: LOGS/<slug>/ (при коллизии — <slug>_2, _3, …).

    Внутри лежат и сетевой дамп, и все собранные скрипты — сессию можно целиком
    заархивировать или переслать одной папкой.
    """
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / slug
    n = 2
    while path.exists():
        path = LOG_DIR / f"{slug}_{n}"
        n += 1
    path.mkdir(parents=True)
    return path


def configure():
    """Интерактивный диалог. Возвращает cfg-словарь или None, если отменили."""
    lang = questionary.select(
        STRINGS["ru"]["ask_lang"],
        choices=[questionary.Choice("Русский", "ru"), questionary.Choice("English", "en")],
        style=Q_STYLE,
    ).ask()
    if lang is None:
        return None
    T.lang = lang

    # прокси
    proxy = None
    while True:
        raw = questionary.text(
            t("ask_proxy"), instruction=t("proxy_hint"), style=Q_STYLE,
        ).ask()
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            console.print(f"[{C_DIM}]{t('proxy_none')}[/]")
            break
        try:
            proxy = parse_proxy(raw)
            console.print(f"[{C_NEON}]{t('proxy_ok')}[/] [{C_CYAN}]{proxy['display']}[/]  "
                          f"[{C_DIM}]→ {proxy['pproxy_uri'].split('#')[0]}[/]")
            break
        except Exception:
            console.print(f"[{C_ERR}]{t('proxy_bad')}[/]")

    # имя сессии
    while True:
        name = questionary.text(t("ask_session"), style=Q_STYLE).ask()
        if name is None:
            return None
        if name.strip():
            break
        console.print(f"[{C_ERR}]{t('session_bad')}[/]")

    slug = sanitize_session(name)
    session_dir = unique_session_dir(slug)
    log_path = session_dir / f"{slug}.jsonl"
    console.print(f"[{C_DIM}]{t('log_to')}[/] [{C_MAG}]{session_dir}[/]\n")

    return {
        "lang": lang,
        "proxy": proxy,
        "session": name.strip(),
        "session_dir": session_dir,
        "log_path": log_path,
        "js_dir": session_dir / "js",
        "proxy_port": free_port(DEFAULT_PROXY_PORT),
        "bridge_port": free_port(DEFAULT_BRIDGE_PORT),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Запуск сессии
# ─────────────────────────────────────────────────────────────────────────────

async def run_session(cfg):
    bridge_proc = None
    chrome_proc = None

    # 1) upstream-мост (если задан прокси)
    if cfg["proxy"]:
        bridge_proc = start_bridge(cfg["proxy"]["pproxy_uri"], cfg["bridge_port"])
        ready = await spin_until(
            lambda: wait_port("127.0.0.1", cfg["bridge_port"], timeout=8),
            t("bridge_start"))
        if ready:
            step(t("bridge_ok"))
            mode = [f"upstream:http://127.0.0.1:{cfg['bridge_port']}"]
        else:
            step(t("bridge_fail"), "fail")
            if bridge_proc and bridge_proc.poll() is None:
                bridge_proc.terminate()
            return None
    else:
        mode = ["regular"]

    # 2) mitmproxy
    opts = options.Options(listen_host="127.0.0.1", listen_port=cfg["proxy_port"], mode=mode)
    master = DumpMaster(opts, with_termlog=False, with_dumper=False)
    logger = NetworkLogger(cfg["log_path"], cfg.get("js_dir"))
    master.addons.add(logger)

    # 3) CA-сертификат
    ensure_ca()

    # 4) Chrome
    step(t("chrome_start"))
    chrome_proc = launch_chrome(cfg["proxy_port"])
    console.print()

    master_task = asyncio.ensure_future(master.run())
    start_ts = time.time()

    # частота кадров и история интенсивности трафика для спарклайна
    fps = 12 if ANIM else 2
    rate = deque(maxlen=34)
    last_total, last_sample, frame = 0, time.time(), 0

    try:
        with Live(render_live(cfg, logger, start_ts, rate, 0), console=console,
                  refresh_per_second=fps, screen=False) as live:
            while not master_task.done():
                # завершение по закрытию Chrome (с грейс-периодом на «форк» браузера)
                if chrome_proc and chrome_proc.poll() is not None and time.time() - start_ts > 3:
                    break
                now = time.time()
                if now - last_sample >= 0.5:
                    total = logger.stats["request"]
                    rate.append(total - last_total)
                    last_total, last_sample = total, now
                live.update(render_live(cfg, logger, start_ts, rate, frame))
                frame += 1
                await asyncio.sleep(1 / fps)
    except KeyboardInterrupt:
        pass
    finally:
        # Синхронную очистку делаем ПЕРВОЙ — она не может быть прервана отменой:
        # закрываем лог (данные и так на диске из-за строчной буферизации) и гасим
        # дочерние процессы, чтобы не осталось сирот.
        try:
            console.print(f"\n[{C_WARN}]{t('ending')}[/]")
        except Exception:
            pass
        master.shutdown()
        logger.done()
        for proc in (chrome_proc, bridge_proc):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        # Дать mitmproxy штатно завершиться. CancelledError — это BaseException,
        # поэтому ловим широко, чтобы не свалиться в finally.
        try:
            await asyncio.shield(master_task)
        except BaseException:
            pass

    return logger.stats


def show_summary(cfg, stats):
    if stats is None:
        return
    size = cfg["log_path"].stat().st_size if cfg["log_path"].exists() else 0
    size_str = f"{size/1024/1024:.2f} MB" if size > 1024 * 1024 else f"{size/1024:.1f} KB"

    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(justify="right", style=C_DIM)
    tbl.add_column(style="bold white")
    tbl.add_row(t("l_req"), f"[{C_CYAN}]{stats['request']}[/]")
    tbl.add_row(t("l_resp"), f"[{C_NEON}]{stats['response']}[/]")
    tbl.add_row(t("l_ws"), f"[{C_MAG}]{stats['ws']}[/]")
    tbl.add_row(t("l_js"), f"[{C_WARN}]{stats.get('js', 0)}[/]")
    tbl.add_row(t("l_err"), f"[{C_ERR}]{stats['error']}[/]" if stats["error"] else "0")
    tbl.add_row("", "")
    tbl.add_row(t("s_saved"), f"[{C_MAG}]{cfg['session_dir']}[/]")
    tbl.add_row(t("s_size"), size_str)

    console.print(Panel(tbl, title=f"[{C_NEON}]✓ {t('summary')}[/]",
                        border_style=C_MAG, padding=(1, 2)))
    typewriter(t("bye"), style=C_CYAN, delay=0.02)


def main():
    # Диалог настройки (questionary) держим ВНЕ asyncio-цикла: внутри он сам
    # поднимает свой event loop, а вложенные циклы asyncio запрещены.
    show_banner()
    try:
        cfg = configure()
    except KeyboardInterrupt:
        return
    if cfg is None:
        return
    stats = None
    try:
        stats = asyncio.run(run_session(cfg))
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_procs()   # страховка: на жёстком Ctrl+C гасим Chrome и мост
    show_summary(cfg, stats)


if __name__ == "__main__":
    main()
