"""Чтение записанной сессии: JSONL-дамп → список обменов «запрос + ответ».

Общая основа для экспорта (HAR, curl) и вывода OpenAPI. Запросы и ответы
связываются по `id` (дампы 1.2+); у старых дампов без `id` — по порядку
на каждый URL, как их и писал mitmproxy.
"""

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

TRUNCATED = "...[TRUNCATED]"


@dataclass
class Exchange:
    id: str
    started: str                       # ISO-время запроса из дампа (локальное)
    method: str
    url: str
    http_version: str = "HTTP/1.1"
    req_headers: list[tuple[str, str]] = field(default_factory=list)
    req_body: object = None            # str | {"encoding": "base64", …} | "[binary, …]" | None
    req_size: int | None = None
    status: int | None = None
    reason: str = ""
    resp_http_version: str = ""
    resp_headers: list[tuple[str, str]] = field(default_factory=list)
    resp_body: object = None
    resp_size: int | None = None
    duration_ms: float | None = None
    error: str | None = None
    ws: list[dict] = field(default_factory=list)   # кадры WebSocket этого соединения
    fetched_by: str | None = None                  # запрос сделал сам httpcrabber

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    def header(self, name: str, where: str = "req") -> str | None:
        name = name.lower()
        pairs = self.req_headers if where == "req" else self.resp_headers
        return next((v for k, v in pairs if k.lower() == name), None)

    def headers_all(self, name: str, where: str = "req") -> list[str]:
        name = name.lower()
        pairs = self.req_headers if where == "req" else self.resp_headers
        return [v for k, v in pairs if k.lower() == name]


def body_text(body: object) -> str | None:
    """Тело как текст, если оно текстовое; None для бинарных плейсхолдеров и base64."""
    if not isinstance(body, str) or not body:
        return None
    if body.startswith("[binary, ") and body.endswith("]"):
        return None
    return body


def is_truncated(body: object) -> bool:
    return isinstance(body, str) and body.endswith(TRUNCATED)


def _pairs(entry: dict) -> list[tuple[str, str]]:
    raw = entry.get("headers_raw")
    if isinstance(raw, list):
        return [(str(k), str(v)) for k, v in raw]
    return [(str(k), str(v)) for k, v in (entry.get("headers") or {}).items()]


def find_dump(path: Path) -> Path:
    """Папка сессии → её .jsonl; файл возвращается как есть."""
    if path.is_file():
        return path
    dumps = sorted(p for p in path.glob("*.jsonl") if not p.name.endswith(".redacted.jsonl"))
    preferred = path / f"{path.name}.jsonl"
    if preferred in dumps:
        return preferred
    if not dumps:
        raise FileNotFoundError(f"no .jsonl dump in {path}")
    return dumps[0]


def load(path: Path) -> list[Exchange]:
    """Все обмены сессии в порядке запросов. Битые строки (оборванные kill'ом) пропускаются."""
    exchanges: list[Exchange] = []
    by_id: dict[str, Exchange] = {}
    pending: dict[str, deque[Exchange]] = defaultdict(deque)   # старые дампы: url → ждут ответа
    ws_by_url: dict[str, Exchange] = {}

    with find_dump(path).open(encoding="utf-8") as fp:
        for n, line in enumerate(fp):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            event, url, fid = e.get("event"), e.get("url") or "", e.get("id")
            if event == "request":
                ex = Exchange(
                    id=fid or f"legacy-{n}", started=e.get("ts", ""), method=e.get("method", "GET"),
                    url=url, http_version=e.get("http_version") or "HTTP/1.1",
                    req_headers=_pairs(e), req_body=e.get("body"), req_size=e.get("size"),
                    fetched_by=e.get("fetched_by"),
                )
                exchanges.append(ex)
                if fid:
                    by_id[fid] = ex
                else:
                    pending[url].append(ex)
                continue

            ex = by_id.get(fid) if fid else None
            if event in ("response", "error") and ex is None and not fid and pending[url]:
                ex = pending[url].popleft()
            if event == "response":
                if ex is None:  # ответ без записанного запроса (запись начата посреди потока)
                    ex = Exchange(id=fid or f"legacy-{n}", started=e.get("ts", ""), method="GET",
                                  url=url)
                    exchanges.append(ex)
                ex.status, ex.reason = e.get("status"), e.get("reason") or ""
                ex.resp_http_version = e.get("http_version") or ""
                ex.resp_headers, ex.resp_body = _pairs(e), e.get("body")
                ex.resp_size, ex.duration_ms = e.get("size"), e.get("duration_ms")
            elif event == "error" and ex is not None:
                ex.error = e.get("error")
            elif event in ("ws_open", "ws_msg", "ws_close"):
                target = ex or ws_by_url.get(url)
                if target is None:
                    target = next((x for x in reversed(exchanges) if x.url == url), None)
                if target is not None:
                    ws_by_url[url] = target
                    if event == "ws_msg":
                        target.ws.append(e)
    return exchanges


def parse_ts(ts: str) -> datetime:
    """Время из дампа (локальное, без зоны) → aware datetime."""
    try:
        return datetime.fromisoformat(ts).astimezone()
    except (TypeError, ValueError):
        return datetime.now().astimezone()
