"""Обзор сохранённых сессий: `httpcrabber ls`.

Считаем быстро, без разбора всего дампа: события ищутся подстрокой (дамп пишет
json.dumps с разделителями по умолчанию), время — из первой и последней строк.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SessionInfo:
    path: Path
    dump: Path
    started: datetime | None
    ended: datetime | None
    requests: int
    ws: int
    errors: int
    size: int
    scripts: int
    sources: bool
    extras: list[str]

    @property
    def duration(self) -> float:
        if self.started and self.ended:
            return max(0.0, (self.ended - self.started).total_seconds())
        return 0.0


def _ts(line: str) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(line)["ts"])
    except (ValueError, KeyError, TypeError):
        return None


def _last_line(path: Path) -> str:
    with path.open("rb") as fp:
        fp.seek(0, 2)
        size = fp.tell()
        fp.seek(max(0, size - 65536))
        lines = fp.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
    return ""


def inspect(folder: Path) -> SessionInfo | None:
    dumps = sorted(p for p in folder.glob("*.jsonl") if not p.name.endswith(".redacted.jsonl"))
    if not dumps:
        return None
    dump = folder / f"{folder.name}.jsonl"
    dump = dump if dump in dumps else dumps[0]
    counts = {"request": 0, "ws_msg": 0, "error": 0}
    first = ""
    with dump.open(encoding="utf-8", errors="replace") as fp:
        for line in fp:
            if not first and line.startswith("{"):
                first = line
            for event in counts:
                if f'"event": "{event}"' in line:
                    counts[event] += 1
                    break
    js = folder / "js"
    extras = [name for name, pattern in (("har", "*.har"), ("openapi", "openapi.*"))
              if any(folder.glob(pattern))]
    if (folder.parent / f"{folder.name}_redacted").exists():
        extras.append("redacted")
    return SessionInfo(
        path=folder, dump=dump, started=_ts(first), ended=_ts(_last_line(dump)),
        requests=counts["request"], ws=counts["ws_msg"], errors=counts["error"],
        size=dump.stat().st_size,
        scripts=sum(1 for p in js.rglob("*") if p.suffix in (".js", ".mjs")) if js.is_dir() else 0,
        sources=js.is_dir() and any(js.glob("*/sources")),
        extras=extras,
    )


_REDACTED = re.compile(r"_redacted(_\d+)?$")


def discover(root: Path) -> list[SessionInfo]:
    """Сессии в папке (обычно LOGS), новые сверху. Замаскированные копии не показываем."""
    if not root.is_dir():
        return []
    found = [info for d in root.iterdir()
             if d.is_dir() and not _REDACTED.search(d.name) and (info := inspect(d))]
    return sorted(found, key=lambda s: s.started or datetime.min, reverse=True)


def latest(root: Path) -> Path | None:
    sessions = discover(root)
    return sessions[0].path if sessions else None
