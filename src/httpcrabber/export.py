"""Экспорт записанной сессии: HAR 1.2 и curl-команды."""

import json
import re
import shlex
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from httpcrabber import __version__
from httpcrabber.dump import TRUNCATED, Exchange, body_text, is_truncated, load, parse_ts

# ── HAR ──────────────────────────────────────────────────────────────────────

_BINARY_RE = re.compile(r"^\[binary, (\d+) bytes")


def _cookies(ex: Exchange) -> tuple[list[dict], list[dict]]:
    req = []
    for header in ex.headers_all("cookie"):
        for part in header.split(";"):
            name, sep, value = part.strip().partition("=")
            if sep:
                req.append({"name": name, "value": value})
    resp = []
    for header in ex.headers_all("set-cookie", "resp"):
        first, *attrs = header.split(";")
        name, _, value = first.strip().partition("=")
        cookie = {"name": name, "value": value}
        for attr in attrs:
            key, _, val = attr.strip().partition("=")
            key = key.lower()
            if key == "path":
                cookie["path"] = val
            elif key == "domain":
                cookie["domain"] = val
            elif key == "expires":
                cookie["expires"] = val
            elif key == "httponly":
                cookie["httpOnly"] = True
            elif key == "secure":
                cookie["secure"] = True
        resp.append(cookie)
    return req, resp


def _content(body: object, mime: str, size: int | None) -> dict:
    content: dict = {"size": size if size is not None else -1, "mimeType": mime}
    if isinstance(body, dict) and body.get("encoding") == "base64":
        content.update(text=body.get("data", ""), encoding="base64")
    elif (text := body_text(body)) is not None:
        if is_truncated(text):
            content["text"] = text[: -len(TRUNCATED)]
            content["comment"] = "truncated by httpcrabber (HTTPCRABBER_MAX_BODY)"
        else:
            content["text"] = text
    elif isinstance(body, str) and (m := _BINARY_RE.match(body)):
        content["comment"] = f"binary body ({m.group(1)} bytes) not stored"
    return content


def _headers(pairs) -> list[dict]:
    return [{"name": k, "value": v} for k, v in pairs if not k.startswith(":")]


def har_entry(ex: Exchange) -> dict:
    req_cookies, resp_cookies = _cookies(ex)
    req_mime = ex.header("content-type") or ""
    entry: dict = {
        "startedDateTime": parse_ts(ex.started).isoformat(timespec="milliseconds"),
        "time": ex.duration_ms or 0,
        "request": {
            "method": ex.method,
            "url": ex.url,
            "httpVersion": ex.http_version,
            "cookies": req_cookies,
            "headers": _headers(ex.req_headers),
            "queryString": [{"name": k, "value": v}
                            for k, v in parse_qsl(urlsplit(ex.url).query, keep_blank_values=True)],
            "headersSize": -1,
            "bodySize": ex.req_size if ex.req_size is not None else -1,
        },
        "response": {
            "status": ex.status or 0,
            "statusText": ex.reason or ("" if ex.error is None else ex.error),
            "httpVersion": ex.resp_http_version or ex.http_version,
            "cookies": resp_cookies,
            "headers": _headers(ex.resp_headers),
            "content": _content(ex.resp_body, ex.header("content-type", "resp") or "",
                                ex.resp_size),
            "redirectURL": ex.header("location", "resp") or "",
            "headersSize": -1,
            "bodySize": ex.resp_size if ex.resp_size is not None else -1,
        },
        "cache": {},
        "timings": {"send": 0, "wait": ex.duration_ms or 0, "receive": 0},
    }
    if ex.req_body is not None:
        post = _content(ex.req_body, req_mime, ex.req_size)
        entry["request"]["postData"] = {"mimeType": req_mime, "text": post.get("text", ""),
                                        **({"comment": post["comment"]} if "comment" in post else {})}
        if req_mime.startswith("application/x-www-form-urlencoded") and "text" in post:
            entry["request"]["postData"]["params"] = [
                {"name": k, "value": v} for k, v in parse_qsl(post["text"], keep_blank_values=True)]
    if ex.error:
        entry["_error"] = ex.error
    if ex.ws:  # формат Chrome DevTools для кадров WebSocket
        entry["_resourceType"] = "websocket"
        entry["_webSocketMessages"] = [
            {"type": "send" if m.get("from_client") else "receive",
             "time": parse_ts(m.get("ts", "")).timestamp(),
             "opcode": 2 if m.get("type") == "binary" else 1,
             "data": m["content"]["data"] if isinstance(m.get("content"), dict)
             else (m.get("content") or "")}
            for m in ex.ws
        ]
    return entry


def to_har(exchanges: list[Exchange]) -> dict:
    return {"log": {
        "version": "1.2",
        "creator": {"name": "httpcrabber", "version": __version__},
        "pages": [],
        "entries": [har_entry(ex) for ex in exchanges],
    }}


def export_har(session: Path, out: Path | None = None) -> tuple[Path, int]:
    exchanges = load(session)
    out = out or _default_out(session, ".har")
    out.write_text(json.dumps(to_har(exchanges), ensure_ascii=False, indent=1), encoding="utf-8")
    return out, len(exchanges)


def _default_out(session: Path, suffix: str) -> Path:
    base = session if session.is_dir() else session.parent
    stem = session.name if session.is_dir() else session.stem
    return base / f"{stem}{suffix}"


# ── curl ─────────────────────────────────────────────────────────────────────

# Эти заголовки curl проставит сам — с ними команда часто ломается (длина тела,
# HTTP/2-псевдозаголовки, сжатие вместо которого ставим --compressed).
_SKIP = {"content-length", "host", "connection", "accept-encoding", "transfer-encoding"}


def _quote(value: str, shell: str) -> str:
    if shell == "powershell":
        return "'" + value.replace("'", "''") + "'"
    return shlex.quote(value)


def to_curl(ex: Exchange, shell: str = "posix") -> str:
    cont = {"posix": " \\\n  ", "powershell": " `\n  "}[shell]
    exe = "curl.exe" if shell == "powershell" else "curl"
    parts = [exe]
    if ex.method != "GET" or ex.req_body is not None:  # с телом curl сам сделал бы POST
        parts.append(f"-X {ex.method}")
    parts.append(_quote(ex.url, shell))
    for name, value in ex.req_headers:
        if name.startswith(":") or name.lower() in _SKIP:
            continue
        parts.append(f"-H {_quote(f'{name}: {value}', shell)}")
    if ex.header("accept-encoding"):
        parts.append("--compressed")
    note = ""
    text = body_text(ex.req_body)
    if isinstance(ex.req_body, dict) and ex.req_body.get("encoding") == "base64":
        note = "# binary body: decode the base64 from the dump into a file and use --data-binary @file\n"
    elif isinstance(ex.req_body, str) and ex.req_body and text is None:
        note = "# binary body was not stored in the dump\n"
    elif text is not None:
        if is_truncated(text):
            note = "# body was truncated in the dump — the request below is incomplete\n"
            text = text[: -len(TRUNCATED)]
        parts.append(f"--data-raw {_quote(text, shell)}")
    head = f"# {ex.status or '···'} {ex.method} {ex.url}\n"
    return head + note + cont.join(parts)


def select(exchanges: list[Exchange], match: str | None = None, method: str | None = None,
           ids: list[str] | None = None) -> list[Exchange]:
    out = exchanges
    if ids:
        out = [ex for ex in out if any(ex.id.startswith(i) for i in ids)]
    if match:
        out = [ex for ex in out if match.lower() in ex.url.lower()]
    if method:
        out = [ex for ex in out if ex.method.upper() == method.upper()]
    return out
