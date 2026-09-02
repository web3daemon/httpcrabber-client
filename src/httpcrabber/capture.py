"""Аддон mitmproxy: пишет сетевой дамп, собирает JavaScript и ведёт живую статистику."""

import contextlib
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

from httpcrabber.config import MAX_BODY_SIZE

_TEXTUAL = ("json", "text", "javascript", "xml", "html", "x-www-form")


def _truncate(text: str) -> str:
    if len(text) > MAX_BODY_SIZE:
        return text[:MAX_BODY_SIZE] + "...[TRUNCATED]"
    return text


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

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.by_hash: dict[str, Path] = {}          # sha256 -> относительный путь
        self.index: dict[tuple[str, str], dict] = {}  # (url, sha256) -> запись манифеста
        self.saved = 0
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

    def _store(self, url: str, text: str, kind: str) -> None:
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

    def store_external(self, url: str, text: str) -> None:
        self._store(url, text, "external")

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


class NetworkLogger:
    """Пишет JSONL-дамп (строчная буферизация — каждая запись сразу на диске)
    и копит статистику для живой панели и итоговой сводки."""

    def __init__(self, path: Path, js_dir: Path | None = None):
        self.path = path
        self.fp = path.open("w", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()
        self.js = JSCollector(js_dir) if js_dir else None
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

    # ── хуки mitmproxy ────────────────────────────────────────────────────

    def request(self, flow: http.HTTPFlow) -> None:
        req = flow.request
        body = None
        if req.content:
            try:
                body = _truncate(req.get_text(strict=False) or "")
            except Exception:
                body = f"[binary, {len(req.content)} bytes]"
        with self.lock:
            self.hosts[req.pretty_host] += 1
            self.methods[req.method] += 1
        self._log(
            "request", "request",
            url=req.pretty_url, method=req.method, http_version=req.http_version,
            client_addr=str(flow.client_conn.peername) if flow.client_conn else None,
            headers=dict(req.headers), body=body,
        )

    def response(self, flow: http.HTTPFlow) -> None:
        if not flow.response:
            return
        resp = flow.response
        url = flow.request.pretty_url
        body = None
        if resp.content:
            ct = resp.headers.get("content-type", "").lower()
            if any(x in ct for x in _TEXTUAL):
                full = None
                try:
                    full = resp.get_text(strict=False) or ""
                except Exception:
                    body = f"[unreadable: {len(resp.content)} bytes]"
                if full is not None:
                    self._collect_js(url, ct, full)  # из ПОЛНОГО тела, до обрезки
                    body = _truncate(full)
            else:
                body = f"[binary, {len(resp.content)} bytes, {ct}]"

        with self.lock:
            self.status_classes[f"{resp.status_code // 100}xx"] += 1
        self._feed(flow.request.method, resp.status_code, url)
        self._log(
            "response", "response",
            url=url, status=resp.status_code, reason=resp.reason,
            http_version=resp.http_version, headers=dict(resp.headers), body=body,
        )

    def _collect_js(self, url: str, ct: str, full: str) -> None:
        if not self.js:
            return
        try:
            if JSCollector.is_js(url, ct):
                self.js.store_external(url, full)
            elif "html" in ct:
                self.js.harvest_html(url, full)
            self.stats["js"] = self.js.saved
        except Exception:
            pass  # сбор скриптов не должен ронять перехват

    def websocket_start(self, flow: http.HTTPFlow) -> None:
        self._log("ws_open", "ws", url=flow.request.pretty_url)

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if not flow.websocket or not flow.websocket.messages:
            return
        msg = flow.websocket.messages[-1]
        try:
            content = msg.content.decode("utf-8", errors="replace")
        except Exception:
            content = f"[binary, {len(msg.content)} bytes]"
        self._feed("WS", "→" if msg.from_client else "←", flow.request.pretty_url)
        self._log(
            "ws_msg", "ws",
            url=flow.request.pretty_url, from_client=msg.from_client, content=_truncate(content),
        )

    def websocket_end(self, flow: http.HTTPFlow) -> None:
        self._log("ws_close", "ws", url=flow.request.pretty_url)

    def error(self, flow: http.HTTPFlow) -> None:
        url = flow.request.pretty_url if flow.request else None
        self._feed("ERR", None, url)
        self._log("error", "error", url=url, error=str(flow.error) if flow.error else None)

    def done(self) -> None:
        if self.js:
            with contextlib.suppress(Exception):
                self.js.finalize()
        with contextlib.suppress(Exception):
            self.fp.close()
