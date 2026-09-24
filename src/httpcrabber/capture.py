"""Аддон mitmproxy: пишет сетевой дамп, собирает JavaScript и ведёт живую статистику."""

import base64
import contextlib
import fnmatch
import hashlib
import json
import os
import re
import threading
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from mitmproxy import http

from httpcrabber import sourcemaps
from httpcrabber.config import CAPTURE_BINARY, MAX_BODY_SIZE

_TEXTUAL = ("json", "text", "javascript", "xml", "html", "x-www-form")


def _truncate(text: str) -> str:
    if len(text) > MAX_BODY_SIZE:
        return text[:MAX_BODY_SIZE] + "...[TRUNCATED]"
    return text


def _host_dir(url: str) -> str:
    return re.sub(r"[^\w.\-]", "_", urlsplit(url).netloc) or "unknown"


def _headers(headers) -> dict:
    """Заголовки в двух видах: словарь (как раньше) и список пар без потерь.

    В словаре повторяющиеся заголовки склеиваются через ", " — для Set-Cookie
    с датой в Expires это необратимо, поэтому рядом пишем headers_raw.
    """
    return {"headers": dict(headers), "headers_raw": [list(kv) for kv in headers.items(multi=True)]}


def _binary_body(content: bytes, ct: str = ""):
    """Плейсхолдер для бинарного тела, либо base64 при CAPTURE_BINARY.

    Кодируем только тела <= MAX_BODY_SIZE — обрезанный base64 не декодируется.
    """
    label = f"[binary, {len(content)} bytes{f', {ct}' if ct else ''}]"
    if not CAPTURE_BINARY or len(content) > MAX_BODY_SIZE:
        return label
    return {
        "encoding": "base64",
        "bytes": len(content),
        "content_type": ct or None,
        "data": base64.b64encode(content).decode("ascii"),
    }


class JSCollector:
    """Складывает в папку сессии весь JavaScript, который прилетает браузеру.

    Два источника:
      • внешние скрипты — ответы с javascript-типом либо путём .js/.mjs;
      • инлайновые <script> из HTML-страниц (без src=).

    Скрипты сохраняются ЦЕЛИКОМ (тела в .jsonl режутся по MAX_BODY_SIZE).
    Дубликаты схлопываются по sha256 — один бандл, запрошенный сто раз, лежит
    на диске один раз, а в манифесте у него счётчик hits.
    """

    _JS_HINTS = ("javascript", "ecmascript")
    _SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
    _TYPE_RE = re.compile(r"""type\s*=\s*["']?([^"'\s>]+)""", re.I)
    _SRC_RE = re.compile(r"\bsrc\s*=", re.I)

    def __init__(self, root: Path, on_map_ref=None):
        self.root = root
        self.lock = threading.Lock()
        self.by_hash: dict[str, Path] = {}          # sha256 -> относительный путь
        self.index: dict[tuple[str, str], dict] = {}  # (url, sha256) -> запись манифеста
        self.saved = 0
        self.sources = 0                            # файлов, распакованных из source maps
        self._maps: set[str] = set()                # sha256 уже распакованных карт
        self._inline_n = 0
        self.on_map_ref = on_map_ref                # callback(url карты) для докачки

    @classmethod
    def is_js(cls, url: str, content_type: str) -> bool:
        ct = (content_type or "").lower()
        if any(h in ct for h in cls._JS_HINTS):
            return True
        return urlsplit(url).path.lower().endswith((".js", ".mjs"))

    def _rel_path(self, url: str, kind: str, digest: str) -> Path:
        parts = urlsplit(url)
        host = _host_dir(url)
        if kind == "inline":
            self._inline_n += 1
            return Path(host) / "inline" / f"inline_{self._inline_n:04d}.{digest[:8]}.js"
        stem, ext = os.path.splitext(os.path.basename(parts.path) or "script")
        if ext.lower() not in (".js", ".mjs"):
            ext = ".js"
        stem = re.sub(r"[^\w.\-]", "_", stem)[:60] or "script"
        return Path(host) / f"{stem}.{digest[:8]}{ext}"

    def _store(self, url: str, text: str, kind: str, headers=None) -> None:
        if not text or not text.strip():
            return
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        new = False
        with self.lock:
            rel = self.by_hash.get(digest)
            if rel is None:
                new = True
                rel = self._rel_path(url, kind, digest)
                try:
                    target = self.root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # newline="\n": без этого Windows превращает \n в \r\n, и файл
                    # на диске перестаёт соответствовать sha256 из манифеста.
                    target.write_text(text, encoding="utf-8", errors="replace", newline="\n")
                except OSError:
                    return  # длинный путь / нет прав — пропускаем
                self.by_hash[digest] = rel
                self.saved += 1

            entry = self.index.get((url, digest))
            if entry is None:
                self.index[(url, digest)] = {
                    "url": url,
                    "file": rel.as_posix(),
                    "kind": kind,
                    "sha256": digest,
                    "size": len(text),
                    "first_seen": datetime.now().isoformat(timespec="seconds"),
                    "hits": 1,
                }
            else:
                entry["hits"] += 1
        if new:
            self._follow_map(url, text, headers)

    def _follow_map(self, url: str, text: str, headers) -> None:
        """Ссылка на source map: встроенную распаковываем сразу, внешнюю — отдаём на докачку."""
        ref = sourcemaps.map_url(url, text, headers)
        if not ref:
            return
        if ref.startswith("data:"):
            decoded = sourcemaps.decode_data_url(ref)
            if decoded:
                self.store_sourcemap(url, decoded)
        elif self.on_map_ref:
            self.on_map_ref(ref)

    def store_sourcemap(self, url: str, text: str) -> int:
        """Сохраняет карту в js/<host>/maps/ и распаковывает её исходники в js/<host>/sources/."""
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        with self.lock:
            if digest in self._maps:
                return 0
            self._maps.add(digest)
        host = _host_dir(url)
        written = sourcemaps.unpack(text, self.root / host / "sources")
        stem = re.sub(r"[^\w.\-]", "_", os.path.basename(urlsplit(url).path))[:60] or "inline"
        rel = Path(host) / "maps" / f"{stem.removesuffix('.map')}.{digest[:8]}.map"
        with contextlib.suppress(OSError):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8", errors="replace", newline="\n")
        with self.lock:
            self.sources += len(written)
            self.index[(url, digest)] = {
                "url": url,
                "file": rel.as_posix(),
                "kind": "sourcemap",
                "sha256": digest,
                "size": len(text),
                "first_seen": datetime.now().isoformat(timespec="seconds"),
                "hits": 1,
                "sources": len(written),
            }
        return len(written)

    def store_external(self, url: str, text: str, headers=None) -> None:
        self._store(url, text, "external", headers)

    def harvest_html(self, url: str, html: str) -> None:
        """Инлайновые <script> из HTML. Теги с src= пропускаем — они прилетят
        отдельным запросом и сохранятся как external."""
        for attrs, body in self._SCRIPT_RE.findall(html):
            if self._SRC_RE.search(attrs):
                continue
            m = self._TYPE_RE.search(attrs)
            if m:
                stype = m.group(1).lower()
                if not any(h in stype for h in self._JS_HINTS) and "module" not in stype:
                    continue  # ld+json, x-template и прочее — не код
            self._store(url, body, "inline")

    def finalize(self) -> None:
        """Манифест index.json рядом со скриптами."""
        if not self.index:
            return
        manifest = sorted(self.index.values(), key=lambda e: (-e["hits"], e["url"]))
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / "index.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass


class Scope:
    """Какие хосты писать: --include / --exclude с glob-шаблонами (*.example.com).

    Пустой include — все хосты. exclude сильнее include.
    """

    def __init__(self, include=(), exclude=()):
        self.include = tuple(p.lower() for p in include)
        self.exclude = tuple(p.lower() for p in exclude)

    def __bool__(self) -> bool:
        return bool(self.include or self.exclude)

    def allows(self, host: str) -> bool:
        host = (host or "").lower()
        if any(fnmatch.fnmatch(host, p) for p in self.exclude):
            return False
        return not self.include or any(fnmatch.fnmatch(host, p) for p in self.include)


class NetworkLogger:
    """Пишет JSONL-дамп (строчная буферизация — каждая запись сразу на диске)
    и копит статистику для живой панели и итоговой сводки.

    Каждое событие несёт `id` потока mitmproxy: запрос, ответ, ошибка и кадры
    WebSocket одного соединения связываются по нему, даже при параллельных
    запросах на один и тот же URL.
    """

    def __init__(self, path: Path, js_dir: Path | None = None, *, scope: Scope | None = None,
                 fetcher: sourcemaps.Fetcher | None = None):
        self.path = path
        self.fp = path.open("w", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()
        self.scope = scope or Scope()
        self.fetcher = fetcher
        self.js = JSCollector(js_dir, on_map_ref=fetcher.submit if fetcher else None) \
            if js_dir else None
        self.stats = {"request": 0, "response": 0, "ws": 0, "error": 0, "js": 0}
        self.hosts: Counter[str] = Counter()
        self.methods: Counter[str] = Counter()
        self.status_classes: Counter[str] = Counter()
        self.feed: deque[tuple[str, str, object, str]] = deque(maxlen=200)

    # ── лента и статистика ─────────────────────────────────────────────────

    def _feed(self, tag: str, code: object, url: str | None) -> None:
        self.feed.append((datetime.now().strftime("%H:%M:%S"), tag, code, url or ""))

    def feed_tail(self, n: int) -> list:
        return list(self.feed)[-n:]

    def _log(self, event: str, stat_key: str, **data: object) -> None:
        entry = {"ts": datetime.now().isoformat(timespec="milliseconds"), "event": event, **data}
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self.lock:
            self.fp.write(line)
            self.stats[stat_key] += 1

    def _wanted(self, flow) -> bool:
        return flow.request is None or self.scope.allows(flow.request.pretty_host)

    # ── хуки mitmproxy ────────────────────────────────────────────────────

    def request(self, flow: http.HTTPFlow) -> None:
        if not self._wanted(flow):
            return
        req = flow.request
        body = None
        if req.content:
            try:
                body = _truncate(req.get_text(strict=False) or "")
            except Exception:
                body = _binary_body(req.content)
        with self.lock:
            self.hosts[req.pretty_host] += 1
            self.methods[req.method] += 1
        self._log(
            "request", "request",
            id=flow.id, url=req.pretty_url, method=req.method, http_version=req.http_version,
            client_addr=str(flow.client_conn.peername) if flow.client_conn else None,
            **_headers(req.headers), body=body,
            size=len(req.raw_content or b""),
            **({"fetched_by": req.headers[sourcemaps.FETCH_HEADER]}
               if sourcemaps.FETCH_HEADER in req.headers else {}),
        )

    def response(self, flow: http.HTTPFlow) -> None:
        if not flow.response or not self._wanted(flow):
            return
        resp = flow.response
        url = flow.request.pretty_url
        body = None
        if resp.content:
            ct = resp.headers.get("content-type", "").lower()
            # .map часто отдают как octet-stream — это всё равно JSON
            if any(x in ct for x in _TEXTUAL) or urlsplit(url).path.lower().endswith(".map"):
                full = None
                try:
                    full = resp.get_text(strict=False) or ""
                except Exception:
                    body = _binary_body(resp.content, ct)
                if full is not None:
                    self._collect_js(url, ct, full, resp.headers)  # из ПОЛНОГО тела
                    body = _truncate(full)
            else:
                body = _binary_body(resp.content, ct)

        with self.lock:
            self.status_classes[f"{resp.status_code // 100}xx"] += 1
        self._feed(flow.request.method, resp.status_code, url)
        start = flow.request.timestamp_start
        end = resp.timestamp_end or resp.timestamp_start
        self._log(
            "response", "response",
            id=flow.id, url=url, status=resp.status_code, reason=resp.reason,
            http_version=resp.http_version, **_headers(resp.headers), body=body,
            size=len(resp.raw_content or b""),
            duration_ms=round((end - start) * 1000, 1) if start and end else None,
        )

    def _collect_js(self, url: str, ct: str, full: str, headers=None) -> None:
        if not self.js:
            return
        try:
            if sourcemaps.looks_like_map(url, ct, full):
                self.js.store_sourcemap(url, full)
            elif JSCollector.is_js(url, ct):
                self.js.store_external(url, full, headers)
            elif "html" in ct:
                self.js.harvest_html(url, full)
            self.stats["js"] = self.js.saved
        except Exception:
            pass  # сбор скриптов не должен ронять перехват

    def websocket_start(self, flow: http.HTTPFlow) -> None:
        if self._wanted(flow):
            self._log("ws_open", "ws", id=flow.id, url=flow.request.pretty_url)

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if not flow.websocket or not flow.websocket.messages or not self._wanted(flow):
            return
        msg = flow.websocket.messages[-1]
        if msg.is_text:
            content = _truncate(msg.content.decode("utf-8", errors="replace"))
        else:
            # protobuf / msgpack и т.п.: decode(errors="replace") молча дал бы мусор
            content = _binary_body(msg.content)
        self._feed("WS", "→" if msg.from_client else "←", flow.request.pretty_url)
        self._log(
            "ws_msg", "ws",
            id=flow.id, url=flow.request.pretty_url, from_client=msg.from_client,
            type="text" if msg.is_text else "binary", content=content,
        )

    def websocket_end(self, flow: http.HTTPFlow) -> None:
        if self._wanted(flow):
            self._log("ws_close", "ws", id=flow.id, url=flow.request.pretty_url)

    def error(self, flow: http.HTTPFlow) -> None:
        if not self._wanted(flow):
            return
        url = flow.request.pretty_url if flow.request else None
        self._feed("ERR", None, url)
        self._log("error", "error", id=flow.id, url=url,
                  error=str(flow.error) if flow.error else None)

    def done(self) -> None:
        if self.fetcher:
            with contextlib.suppress(Exception):
                self.fetcher.close()
        if self.js:
            with contextlib.suppress(Exception):
                self.js.finalize()
        with contextlib.suppress(Exception):
            self.fp.close()

