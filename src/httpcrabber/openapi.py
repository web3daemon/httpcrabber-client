"""Вывод OpenAPI 3.1 из записанного трафика.

Что выводится:
  • эндпоинты с шаблонами путей — /users/123 и /users/456 сворачиваются в
    /users/{userId} (числа, UUID, длинные hex и токены считаются параметрами);
  • query-параметры (required — если были в каждом запросе), нестандартные x-заголовки;
  • JSON-схемы тел запросов и ответов, слитые по всем образцам: поле, которое
    встречалось не везде, не попадает в required; null делает тип nullable;
  • схемы авторизации (Bearer, Basic, API-ключ в заголовке);
  • для GraphQL — список operationName, которые ходили через эндпоинт.

Примеры в спеке проходят через redact: спекой делятся, токенов в ней быть не должно.
Схемы отражают только увиденный трафик — это отправная точка, а не контракт.
"""

import fnmatch
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from httpcrabber import __version__
from httpcrabber.dump import Exchange, body_text, is_truncated, load
from httpcrabber.redact import Redactor, is_secret_name

_STATIC_EXT = (
    ".js", ".mjs", ".css", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".avif", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm", ".mp3", ".ogg",
    ".wav", ".wasm", ".html", ".htm", ".txt", ".pdf", ".zip",
)
_SEGMENT_KINDS = (
    ("integer", re.compile(r"^\d+$")),
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)),
    ("hex", re.compile(r"^[0-9a-f]{16,}$", re.I)),
    ("token", re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9_\-]{20,}$")),
)
_FORMATS = (
    ("date-time", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")),
    ("date", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("uuid", _SEGMENT_KINDS[1][1]),
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)),
    ("uri", re.compile(r"^https?://\S+$")),
)
_VERSION_SEG = re.compile(r"^(v\d+(\.\d+)*|api|rest|public|internal)$", re.I)


# ── отбор и шаблоны путей ────────────────────────────────────────────────────

def _mime(value: str | None) -> str:
    return (value or "").split(";")[0].strip().lower()


def is_api_call(ex: Exchange) -> bool:
    """Похоже ли на вызов API, а не на статику или страницу."""
    if ex.fetched_by or ex.status is None:
        return False
    path = urlsplit(ex.url).path.lower()
    if path.endswith(_STATIC_EXT):
        return False
    # Content-Type запроса имеет смысл только при теле: некоторые клиенты шлют его и на GET
    req_type = _mime(ex.header("content-type")) if ex.req_body not in (None, "") else ""
    types = req_type + " " + _mime(ex.header("content-type", "resp"))
    if "json" in types or "x-www-form-urlencoded" in types or "graphql" in types:
        return True
    return ex.method in ("POST", "PUT", "PATCH", "DELETE") and "html" not in types


def _segment_kind(segment: str) -> str | None:
    return next((kind for kind, rx in _SEGMENT_KINDS if rx.match(segment)), None)


def _param_name(previous: str | None, used: set[str]) -> str:
    base = "id"
    if previous and previous.isidentifier() and not _VERSION_SEG.match(previous):
        stem = previous[:-3] + "y" if previous.endswith("ies") else previous.rstrip("s") or previous
        base = re.sub(r"[^A-Za-z0-9]", "", stem) + "Id"
    name, n = base, 2
    while name in used:
        name, n = f"{base}{n}", n + 1
    used.add(name)
    return name


def template(path: str) -> tuple[str, list[tuple[str, str, str]]]:
    """'/v2/users/42/orders' → ('/v2/users/{userId}/orders', [('userId', '42', 'integer')])."""
    out, params, used, previous = [], [], set(), None
    for seg in path.split("/"):
        kind = _segment_kind(seg) if seg else None
        if kind:
            name = _param_name(previous, used)
            out.append("{" + name + "}")
            params.append((name, seg, kind))
        else:
            out.append(seg)
            previous = seg or previous
    return "/".join(out) or "/", params


# ── вывод схем ───────────────────────────────────────────────────────────────

def _str_schema(value: str) -> dict:
    fmt = next((name for name, rx in _FORMATS if rx.match(value)), None)
    return {"type": "string", **({"format": fmt} if fmt else {})}


def infer(value) -> dict:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return _str_schema(value)
    if isinstance(value, list):
        items: dict = {}
        for item in value[:50]:
            items = merge(items, infer(item))
        return {"type": "array", "items": items}
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: infer(v) for k, v in value.items()},
                "required": sorted(value)}
    return {}


def _types(schema: dict) -> set[str]:
    t = schema.get("type")
    return set(t) if isinstance(t, list) else ({t} if t else set())


def _any_of(a: dict, b: dict) -> dict:
    options, seen = [], set()
    for s in a.get("anyOf", [a]) + b.get("anyOf", [b]):
        key = json.dumps(s, sort_keys=True)
        if key not in seen:
            seen.add(key)
            options.append(s)
    return {"anyOf": options[:8]}


def _merge_same(a: dict, b: dict, kind: str) -> dict:
    if kind == "object":
        pa, pb = a.get("properties", {}), b.get("properties", {})
        props = {k: merge(pa.get(k, {}), pb.get(k, {})) for k in {**pa, **pb}}
        required = sorted(set(a.get("required", [])) & set(b.get("required", [])))
        return {"type": "object", "properties": props, **({"required": required} if required else {})}
    if kind == "array":
        return {"type": "array", "items": merge(a.get("items", {}), b.get("items", {}))}
    out = {"type": kind}
    if kind == "string" and a.get("format") and a.get("format") == b.get("format"):
        out["format"] = a["format"]
    return out


def merge(a: dict, b: dict) -> dict:
    """Схема, которой удовлетворяют оба образца."""
    if not a:
        return b
    if not b:
        return a
    if "anyOf" in a or "anyOf" in b:
        return _any_of(a, b)
    ta, tb = _types(a) - {"null"}, _types(b) - {"null"}
    nullable = "null" in _types(a) | _types(b)
    if not ta or not tb:
        base = dict(b if not ta else a)
    elif ta == tb and len(ta) == 1:
        base = _merge_same(a, b, next(iter(ta)))
    elif ta | tb <= {"integer", "number"}:
        base = {"type": "number"}
    else:
        return _any_of(a, b)
    if nullable:
        kinds = sorted(_types(base) - {"null"})
        base["type"] = [*kinds, "null"] if kinds else "null"
    return base


def _scalar_schema(values: list[str]) -> dict:
    if values and all(v.isdigit() for v in values):
        return {"type": "integer"}
    if values and all(v.lower() in ("true", "false") for v in values):
        return {"type": "boolean"}
    return _str_schema(values[0]) if values and len(set(values)) == 1 else {"type": "string"}


# ── примеры без секретов ─────────────────────────────────────────────────────

def _trim(value, depth: int = 0):
    """Пример покороче: массивы до 3 элементов, строки до 200 символов, глубина до 8."""
    if depth > 8:
        return None
    if isinstance(value, list):
        return [_trim(v, depth + 1) for v in value[:3]]
    if isinstance(value, dict):
        return {k: _trim(v, depth + 1) for k, v in value.items()}
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return value


def _json_body(body) -> object | None:
    text = body_text(body)
    if text is None or is_truncated(text) or text.lstrip()[:1] not in "{[":
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# ── сборка спеки ─────────────────────────────────────────────────────────────

def _content(samples: list[tuple[str, object]], redactor: Redactor) -> dict:
    """{media type: {schema, example}} по образцам (mime, тело)."""
    by_mime: dict[str, dict] = {}
    for mime, body in samples:
        mime = mime or "application/octet-stream"
        slot = by_mime.setdefault(mime, {"schema": {}})
        if "json" in mime:
            parsed = _json_body(body)
            if parsed is not None:
                slot["schema"] = merge(slot["schema"], infer(parsed))
                slot.setdefault("example", _trim(redactor.value(parsed)))
        elif "x-www-form-urlencoded" in mime and (text := body_text(body)):
            fields = parse_qsl(text, keep_blank_values=True)
            slot["schema"] = merge(slot["schema"], {
                "type": "object", "properties": {k: {"type": "string"} for k, _ in fields},
                "required": sorted({k for k, _ in fields})})
        elif not slot["schema"]:
            slot["schema"] = {"type": "string", **({} if body_text(body) else {"format": "binary"})}
    return by_mime


def _operation_id(method: str, path: str, used: set[str]) -> str:
    words = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{"):
            words.append("By" + seg[1:-1][:1].upper() + seg[1:-1][1:])
        elif seg:
            words.extend(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", seg) if w)
    base = method.lower() + "".join(words) if words else method.lower() + "Root"
    name, n = base, 2
    while name in used:
        name, n = f"{base}{n}", n + 1
    used.add(name)
    return name


def _tag(path: str) -> str | None:
    for seg in path.strip("/").split("/"):
        if seg and not seg.startswith("{") and not _VERSION_SEG.match(seg):
            return seg
    return None


def _security(samples: list[Exchange], schemes: dict) -> list[dict]:
    needed = []
    for ex in samples:
        auth = ex.header("authorization") or ""
        scheme = auth.split(" ", 1)[0].lower()
        if scheme == "bearer":
            schemes["bearerAuth"] = {"type": "http", "scheme": "bearer"}
            needed.append("bearerAuth")
        elif scheme == "basic":
            schemes["basicAuth"] = {"type": "http", "scheme": "basic"}
            needed.append("basicAuth")
        for name, _ in ex.req_headers:
            if name.lower() in ("x-api-key", "api-key", "x-auth-token", "x-access-token"):
                key = "apiKey_" + re.sub(r"[^A-Za-z0-9]", "", name)
                schemes[key] = {"type": "apiKey", "in": "header", "name": name}
                needed.append(key)
    return [{name: []} for name in sorted(set(needed))]


def build(exchanges: list[Exchange], hosts: list[str] | None = None,
          session_name: str = "") -> dict:
    calls = [ex for ex in exchanges if is_api_call(ex)]
    if hosts:
        calls = [ex for ex in calls if any(fnmatch.fnmatch(ex.host, h) for h in hosts)]
    redactor = Redactor()

    grouped: dict[tuple[str, str], list[tuple[Exchange, list]]] = defaultdict(list)
    origins: dict[str, Counter] = defaultdict(Counter)
    for ex in calls:
        parts = urlsplit(ex.url)
        path, params = template(parts.path or "/")
        grouped[(path, ex.method.lower())].append((ex, params))
        origins[path][f"{parts.scheme}://{parts.netloc}"] += 1

    all_origins = Counter()
    for counts in origins.values():
        all_origins.update(counts)
    servers = [o for o, _ in all_origins.most_common()]

    paths: dict[str, dict] = {}
    schemes: dict[str, dict] = {}
    op_ids: set[str] = set()
    for (path, method), items in sorted(grouped.items()):
        samples = [ex for ex, _ in items]
        op: dict = {"operationId": _operation_id(method, path, op_ids)}
        if tag := _tag(path):
            op["tags"] = [tag]
        op["summary"] = f"{method.upper()} {path}"

        parameters = []
        path_values: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for _, params in items:
            for name, value, kind in params:
                path_values[name].append((value, kind))
        for name, values in path_values.items():
            kinds = {k for _, k in values}
            schema = {"type": "integer"} if kinds == {"integer"} else \
                {"type": "string", "format": "uuid"} if kinds == {"uuid"} else {"type": "string"}
            parameters.append({"name": name, "in": "path", "required": True, "schema": schema,
                               "example": values[0][0]})

        query: dict[str, list[str]] = defaultdict(list)
        for ex in samples:
            for k, v in parse_qsl(urlsplit(ex.url).query, keep_blank_values=True):
                query[k].append(v)
        for name, values in sorted(query.items()):
            param = {"name": name, "in": "query",
                     "required": all(name in dict(parse_qsl(urlsplit(ex.url).query)) for ex in samples),
                     "schema": _scalar_schema(values)}
            if not is_secret_name(name):
                param["example"] = values[0][:200]
            parameters.append(param)

        custom = Counter(name for ex in samples for name, _ in ex.req_headers
                         if name.lower().startswith("x-") and name.lower() not in
                         ("x-api-key", "x-auth-token", "x-access-token"))
        for name, count in sorted(custom.items()):
            param = {"name": name, "in": "header", "required": count == len(samples),
                     "schema": {"type": "string"}}
            value = next(v for ex in samples for k, v in ex.req_headers if k == name)
            if not is_secret_name(name):
                param["example"] = value[:200]
            parameters.append(param)
        if parameters:
            op["parameters"] = parameters

        bodies = [(_mime(ex.header("content-type")), ex.req_body) for ex in samples
                  if ex.req_body not in (None, "")]
        if bodies:
            op["requestBody"] = {"content": _content(bodies, redactor)}

        responses: dict[str, dict] = {}
        by_status: dict[int, list[Exchange]] = defaultdict(list)
        for ex in samples:
            by_status[ex.status].append(ex)
        for status, group in sorted(by_status.items()):
            try:
                description = HTTPStatus(status).phrase
            except ValueError:
                description = group[0].reason or "Response"
            response: dict = {"description": description}
            with_body = [(_mime(ex.header("content-type", "resp")), ex.resp_body) for ex in group
                         if ex.resp_body not in (None, "")]
            if with_body:
                response["content"] = _content(with_body, redactor)
            responses[str(status)] = response
        op["responses"] = responses

        if security := _security(samples, schemes):
            op["security"] = security
        graphql = sorted({b["operationName"] for ex in samples
                          if isinstance(b := _json_body(ex.req_body), dict)
                          and isinstance(b.get("operationName"), str)})
        if graphql:
            op["x-graphql-operations"] = graphql
        op["x-httpcrabber-samples"] = len(samples)

        item = paths.setdefault(path, {})
        item[method] = op
        path_origins = sorted(origins[path])
        if len(servers) > 1 and path_origins != sorted(servers):
            item["servers"] = [{"url": o} for o in path_origins]

    top = urlsplit(servers[0]).hostname if servers else "api"
    spec: dict = {
        "openapi": "3.1.0",
        "info": {
            "title": f"{top} API",
            "version": "0.0.0-inferred",
            "description": (
                f"Inferred by httpcrabber {__version__} from {len(calls)} recorded API calls"
                f"{f' in session {session_name!r}' if session_name else ''} on "
                f"{datetime.now():%Y-%m-%d}. Schemas describe only the traffic that was "
                "observed — a starting point, not a contract. Example values are redacted."
            ),
        },
        "servers": [{"url": o} for o in servers],
        "paths": paths,
    }
    if schemes:
        spec["components"] = {"securitySchemes": schemes}
    return spec


def write(spec: dict, out: Path) -> None:
    if out.suffix.lower() in (".yaml", ".yml"):
        from ruamel.yaml import YAML  # идёт вместе с mitmproxy

        yaml = YAML()
        yaml.default_flow_style = False
        with out.open("w", encoding="utf-8") as fp:
            yaml.dump(spec, fp)
    else:
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")


def export_openapi(session: Path, out: Path | None = None,
                   hosts: list[str] | None = None) -> tuple[Path, dict]:
    spec = build(load(session), hosts, session.stem if session.is_file() else session.name)
    out = out or (session if session.is_dir() else session.parent) / "openapi.json"
    write(spec, out)
    return out, spec
