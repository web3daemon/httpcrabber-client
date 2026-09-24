"""Повтор записанного запроса — как есть или с правками (из браузера сессий)."""

import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from httpcrabber.dump import Exchange, body_text, is_truncated

# Их проставит сам urllib; accept-encoding убираем, чтобы получить тело несжатым
_SKIP = {"content-length", "host", "connection", "accept-encoding", "transfer-encoding"}
MAX_BODY = 5 * 1024 * 1024


@dataclass
class ReplayResult:
    status: int | None
    reason: str = ""
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: str = ""
    duration_ms: float = 0.0
    error: str | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Редирект показываем как есть (302 + Location), а не следуем за ним молча."""

    def redirect_request(self, *args, **kwargs):
        return None


def replay(ex: Exchange, proxy: str | None = None, timeout: float = 30,
           verify: bool = True) -> ReplayResult:
    if is_truncated(ex.req_body):
        return ReplayResult(None, error="request body was truncated in the dump — edit it first")
    if isinstance(ex.req_body, dict) or (isinstance(ex.req_body, str) and ex.req_body
                                         and body_text(ex.req_body) is None):
        return ReplayResult(None, error="binary request bodies can't be replayed yet")
    data = ex.req_body.encode("utf-8") if isinstance(ex.req_body, str) and ex.req_body else None
    headers = {k: v for k, v in ex.req_headers if not k.startswith(":") and k.lower() not in _SKIP}
    req = urllib.request.Request(ex.url, data=data, headers=headers, method=ex.method)

    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    handlers = [urllib.request.HTTPSHandler(context=ctx), _NoRedirect()]
    handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))
    opener = urllib.request.build_opener(*handlers)

    t0 = time.perf_counter()
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as err:  # 4xx/5xx/3xx — это тоже ответ
        resp = err
    except Exception as exc:  # сеть, DNS, TLS
        return ReplayResult(None, error=f"{type(exc).__name__}: {exc}",
                            duration_ms=(time.perf_counter() - t0) * 1000)
    with resp:
        raw = resp.read(MAX_BODY + 1)
        charset = resp.headers.get_content_charset() or "utf-8"
    body = raw[:MAX_BODY].decode(charset, "replace")
    if len(raw) > MAX_BODY:
        body += "\n…[shown first 5 MB]"
    return ReplayResult(
        status=resp.status, reason=getattr(resp, "reason", "") or "",
        headers=list(resp.headers.items()), body=body,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
