"""Маскирование секретов в записанной сессии — перед тем как ею поделиться.

Запись всегда идёт как есть (для реверса нужны настоящие токены), а
`httpcrabber redact <сессия>` делает рядом замаскированную копию:

  • заголовки Authorization / Cookie / Set-Cookie / X-Api-Key и подобные —
    схема авторизации, имена кук и атрибуты остаются, значения скрываются;
  • параметры URL и формы, JSON-поля с «секретными» именами (token, secret,
    password, api_key, session, …) — и в запросах, и в ответах, и в WebSocket.

JS-файлы копируются без изменений: это публичный код сайта.
"""

import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MASK = "[REDACTED]"

_SECRET_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "api-key",
    "x-auth-token", "x-access-token", "x-csrf-token", "x-xsrf-token", "x-amz-security-token",
}
_EXACT = {
    "code", "sid", "sig", "signature", "auth", "session", "sessionid", "jwt", "otp", "key",
    "apikey", "api_key", "password", "passwd", "pwd", "secret", "token", "bearer", "cookies",
}
_SUFFIX = ("token", "secret", "password", "_key", "-key", "apikey", "sessionid", "_sid",
           "signature")
_JSON_PAIR = re.compile(r'"([^"\\]{1,64})"\s*:\s*"((?:[^"\\]|\\.)*)"')
_AUTH_VALUE = re.compile(r"^(bearer|basic|digest|token)\s+\S+", re.I)


def is_secret_name(name: str) -> bool:
    n = name.strip().lower()
    return n in _EXACT or n in _SECRET_HEADERS or n.endswith(_SUFFIX)


class Redactor:
    def __init__(self):
        self.masked = 0

    def _mask(self) -> str:
        self.masked += 1
        return MASK

    # ── заголовки ─────────────────────────────────────────────────────────

    def header(self, name: str, value: str) -> str:
        n = name.lower()
        if n in ("authorization", "proxy-authorization"):
            scheme, sep, _ = value.partition(" ")
            return f"{scheme} {self._mask()}" if sep else self._mask()
        if n == "cookie":
            return "; ".join(self._pair(p, force=True) for p in value.split(";") if p.strip())
        if n == "set-cookie":
            first, *attrs = value.split(";")
            return ";".join([self._pair(first, force=True), *attrs])
        if n in _SECRET_HEADERS or is_secret_name(n):
            return self._mask()
        return value

    def _pair(self, part: str, force: bool = False) -> str:
        name, sep, value = part.strip().partition("=")
        if sep and value and (force or is_secret_name(name)):
            return f"{name}={self._mask()}"
        return part.strip()

    # ── URL, формы, JSON ─────────────────────────────────────────────────

    def query(self, qs: str) -> str:
        return "&".join(self._pair(p) if "=" in p else p for p in qs.split("&"))

    def url(self, url: str) -> str:
        if not url or "?" not in url:
            return url
        parts = urlsplit(url)
        return urlunsplit(parts._replace(query=self.query(parts.query)))

    def _json(self, obj, key: str = ""):
        if isinstance(obj, dict):
            if key and is_secret_name(key):  # {"cookies": {"sid": "…"}} — скрываем всё внутри
                return {k: self._json(v, key) for k, v in obj.items()}
            return {k: self._json(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._json(v, key) for v in obj]
        if not isinstance(obj, str) or not obj:
            return obj  # только строки: токены — строки, а {"code": 404} маскировать незачем
        if key and is_secret_name(key):
            return self.header(key, obj) if key.lower() in _SECRET_HEADERS else self._mask()
        if _AUTH_VALUE.match(obj):
            return f"{obj.split(None, 1)[0]} {self._mask()}"
        if obj.lstrip()[:1] in "{[":
            return self.text(obj)  # JSON внутри строки: эхо-сервисы, GraphQL variables и т.п.
        return obj

    def text(self, text):
        """Тело или WS-кадр: JSON, форма или (обрезанный) текст с JSON-парами."""
        if not isinstance(text, str) or not text:
            return text  # None или {"encoding": "base64", …} — не трогаем
        stripped = text.lstrip()
        if stripped[:1] in "{[":
            try:
                return json.dumps(self._json(json.loads(text)), ensure_ascii=False)
            except ValueError:
                pass  # обрезанный JSON — ниже маскируем пары регэкспом
        elif "=" in text and "\n" not in text and " " not in text.strip():
            return self.query(text)
        return _JSON_PAIR.sub(
            lambda m: f'"{m.group(1)}": "{self._mask()}"' if is_secret_name(m.group(1))
            else m.group(0), text)

    # ── событие дампа ────────────────────────────────────────────────────

    def entry(self, e: dict) -> dict:
        e = dict(e)
        if isinstance(e.get("url"), str):
            e["url"] = self.url(e["url"])
        if isinstance(e.get("headers"), dict):
            e["headers"] = {k: self.header(k, str(v)) for k, v in e["headers"].items()}
        if isinstance(e.get("headers_raw"), list):
            e["headers_raw"] = [[k, self.header(k, str(v))] for k, v in e["headers_raw"]]
        for key in ("body", "content"):
            if key in e:
                e[key] = self.text(e[key])
        return e


def redact_jsonl(src: Path, dst: Path, redactor: Redactor) -> int:
    lines = 0
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8", newline="\n") as fout:
        for line in fin:
            if not line.strip():
                continue
            try:
                entry = redactor.entry(json.loads(line))
            except ValueError:
                continue  # битую строку (оборванную на kill) не переносим
            fout.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            lines += 1
    return lines


def _free(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}_{n}")
        n += 1
    return candidate


def redact_session(src: Path, out: Path | None = None) -> tuple[Path, int, int]:
    """Копия сессии (папки или одного .jsonl) с замаскированными секретами.

    Возвращает (путь копии, строк дампа, замаскированных значений).
    """
    redactor = Redactor()
    if src.is_file():
        dst = out or src.with_name(f"{src.stem}.redacted.jsonl")
        return dst, redact_jsonl(src, dst, redactor), redactor.masked

    dst = out or _free(src.with_name(f"{src.name}_redacted"))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.jsonl"))
    lines = sum(redact_jsonl(f, dst / f.relative_to(src), redactor) for f in src.rglob("*.jsonl"))
    return dst, lines, redactor.masked
