"""Source maps: поиск, распаковка исходников и (по флагу) активная докачка.

Браузер скачивает .map только при открытых DevTools, поэтому в обычной сессии
карты сами не прилетают. Что умеем:
  • карта всё же пришла ответом (или встроена data:-URL'ом) — распаковываем её
    sourcesContent в js/<host>/sources/… — это исходники проекта до минификации;
  • с --sourcemaps сами запрашиваем карты, на которые ссылаются скрипты, через
    свой же mitmproxy: запрос попадает в дамп как обычный и проходит через
    upstream-прокси сессии.
"""

import base64
import json
import re
import ssl
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

FETCH_HEADER = "X-Httpcrabber-Fetch"  # помечает запросы, которые сделал сам инструмент

_URL_RE = re.compile(r"[#@]\s*sourceMappingURL\s*=\s*([^\s'\"*]+)\s*(?:\*/)?\s*$")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:/*", re.I)
_UNSAFE = re.compile(r"[^\w.\-@+]")


def map_url(js_url: str, js_text: str, headers=None) -> str | None:
    """URL карты для скрипта: заголовок SourceMap / X-SourceMap или комментарий в конце."""
    if headers is not None:
        for name in ("sourcemap", "x-sourcemap"):
            value = headers.get(name)
            if value:
                return urljoin(js_url, value.strip())
    m = _URL_RE.search(js_text[-2048:])
    if not m:
        return None
    ref = m.group(1)
    return ref if ref.startswith("data:") else urljoin(js_url, ref)


def decode_data_url(url: str) -> str | None:
    """data:application/json;base64,… → текст карты."""
    if not url.startswith("data:") or "," not in url:
        return None
    meta, payload = url[5:].split(",", 1)
    try:
        if meta.endswith(";base64"):
            return base64.b64decode(payload).decode("utf-8", "replace")
        return unquote(payload)
    except ValueError:
        return None


def looks_like_map(url: str, content_type: str, text: str) -> bool:
    if urlsplit(url).path.lower().endswith(".map"):
        return True
    head = text.lstrip()[:4096]
    return head.startswith("{") and '"mappings"' in head and '"version"' in head


def clean_source_path(source: str) -> PurePosixPath:
    """'webpack://app/./src/a.ts?1f2e' → app/src/a.ts; '..' и абсолютные пути отбрасываются."""
    source = _SCHEME_RE.sub("", source.split("?", 1)[0].split("#", 1)[0])
    parts = [_UNSAFE.sub("_", p)[:100] for p in source.replace("\\", "/").split("/")
             if p not in ("", ".", "..")]
    return PurePosixPath(*parts) if parts else PurePosixPath("unknown.js")


def unpack(map_text: str, dest: Path) -> list[str]:
    """Пишет sourcesContent карты в dest; возвращает относительные пути записанных файлов."""
    try:
        data = json.loads(map_text)
    except ValueError:
        return []
    maps = [s.get("map", {}) for s in data.get("sections", [])] if "sections" in data else [data]
    written = []
    root = dest.resolve()
    for sm in maps:
        prefix = sm.get("sourceRoot") or ""
        for src, content in zip(sm.get("sources") or [], sm.get("sourcesContent") or [],
                                strict=False):
            if not isinstance(content, str) or not content or not isinstance(src, str):
                continue
            rel = clean_source_path(prefix + src if prefix and not _SCHEME_RE.match(src) else src)
            target = (dest / rel).resolve()
            if root not in target.parents:
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", errors="replace", newline="\n")
            except OSError:
                continue
            written.append(rel.as_posix())
    return written


class Fetcher:
    """Фоновая докачка карт через локальный mitmproxy — по одной на URL."""

    def __init__(self, proxy_port: int, workers: int = 2):
        self.proxy = f"http://127.0.0.1:{proxy_port}"
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sourcemap")
        self.seen: set[str] = set()
        self.lock = threading.Lock()
        # До mitmproxy — loopback, сертификат его собственный; настоящий сертификат
        # сайта проверяет сам mitmproxy при соединении с сервером.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}),
            urllib.request.HTTPSHandler(context=ctx),
        )

    def submit(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            return
        with self.lock:
            if url in self.seen:
                return
            self.seen.add(url)
        self.pool.submit(self._get, url)

    def _get(self, url: str) -> None:
        req = urllib.request.Request(url, headers={FETCH_HEADER: "sourcemap"})
        try:
            with self.opener.open(req, timeout=15) as resp:
                resp.read()  # содержимое сохранит сам аддон, увидев ответ
        except Exception:
            pass  # карты нет (404) или сайт её прячет — это нормально

    def close(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
