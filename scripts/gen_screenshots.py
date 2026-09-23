"""Генератор SVG-скриншотов интерфейса для README — рендерит настоящие панели ui.py
на демо-данных, без сети, mitmproxy и создания папок сессий.

    python scripts/gen_screenshots.py

Скриншоты лежат в репозитории (assets/screen-*.svg): после правок ui.py
перегенерируй их, чтобы README не расходился с тем, что видит пользователь.
"""

import io
import sys
import time
from collections import Counter, deque
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rich.console import Console  # noqa: E402
from rich.terminal_theme import TerminalTheme  # noqa: E402

from httpcrabber import ui  # noqa: E402
from httpcrabber.config import settings  # noqa: E402

OUT = ROOT / "assets"
WIDTH = 100

# Тёмная тема в тон логотипу: почти чёрный с зеленцой
THEME = TerminalTheme(
    (11, 15, 12), (214, 222, 214),
    [(11, 15, 12), (255, 59, 59), (57, 255, 20), (255, 204, 0),
     (127, 140, 255), (255, 47, 208), (0, 229, 255), (214, 222, 214)],
    [(95, 111, 95), (255, 110, 110), (150, 255, 130), (255, 225, 110),
     (170, 180, 255), (255, 130, 230), (120, 245, 255), (255, 255, 255)],
)

FEED = [
    ("14:22:07", "GET", 200, "https://cdn.target.com/static/js/main.a3f1c8d4e5b6.chunk.js?v=20260919"),
    ("14:22:07", "POST", 403, "https://api.target.com/v2/auth/challenge"),
    ("14:22:08", "GET", 304, "https://target.com/assets/app.css"),
    ("14:22:08", "POST", 200, "https://api.target.com/v2/graphql?op=Viewer"),
    ("14:22:09", "WS", "→", "wss://realtime.target.com/socket"),
    ("14:22:09", "GET", 200, "https://static.target.com/fonts/inter-var.woff2"),
    ("14:22:10", "GET", 500, "https://api.target.com/v2/telemetry/collect"),
    ("14:22:10", "OPTIONS", 204, "https://api.target.com/v2/feed"),
    ("14:22:11", "ERR", None, "https://blocked.tracker.io/beacon"),
    ("14:22:11", "GET", 200, "https://api.target.com/v2/feed?cursor=eyJpZCI6MTQ3OH0"),
    ("14:22:12", "PUT", 201, "https://api.target.com/v2/profile/settings"),
    ("14:22:12", "DELETE", 204, "https://api.target.com/v2/session"),
]


class DemoLogger:
    stats = {"request": 1478, "response": 1443, "ws": 12, "js": 38, "error": 2}
    hosts = Counter({"api.target.com": 612, "cdn.target.com": 380, "static.target.com": 214,
                     "target.com": 131, "tracker.io": 96, "fonts.gstatic.com": 45})
    methods = Counter({"GET": 1201, "POST": 260, "OPTIONS": 17})
    status_classes = Counter({"2xx": 1380, "3xx": 12, "4xx": 51, "5xx": 3})

    def feed_tail(self, n):
        return FEED[-n:]


class DemoPath:
    def __init__(self, size: int):
        self.size = size

    def exists(self) -> bool:
        return True

    def stat(self):
        return SimpleNamespace(st_size=self.size)


def demo_cfg(launch_browser: bool = True):
    return SimpleNamespace(
        name="TARGET RECON",
        proxy=SimpleNamespace(display="socks5://user:****@1.2.3.4:1080"),
        proxy_port=8080,
        session_dir=PurePosixPath("LOGS/target_recon"),
        log_path=DemoPath(2_422_000),
        launch_browser=launch_browser,
    )


def shoot(name: str, title: str, draw, suffix: str = "") -> None:
    rec = Console(record=True, width=WIDTH, force_terminal=True, color_system="truecolor",
                  file=io.StringIO())
    saved = ui.console
    ui.console = rec
    try:
        draw(rec)
    finally:
        ui.console = saved
    path = OUT / f"screen-{name}{suffix}.svg"
    rec.save_svg(str(path), title=title, theme=THEME)
    # rich пишет CRLF на Windows — нормализуем, как и всё остальное в репозитории
    path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    print(f"  {path.relative_to(ROOT)}")


def start(c: Console) -> None:
    c.print(ui.banner_panel())
    ui.typewriter(ui.t("tagline"), style=ui.MUTED)
    c.print()
    ui.step(f"{ui.t('proxy_ok')} [{ui.CYAN}]socks5://user:****@1.2.3.4:1080[/]")
    c.print()
    c.print(ui.brief_panel(demo_cfg()))
    c.print()
    ui.step(ui.t("bridge_ok"))
    ui.step(ui.t("mitm_start", port=8080))
    ui.step(ui.t("ca_ok"))
    ui.step(ui.t("chrome_start"))


def live(c: Console) -> None:
    rate = deque([1, 3, 2, 6, 9, 14, 8, 5, 11, 18, 22, 15, 9, 6, 12, 19, 25, 17, 10, 7, 13, 16])
    c.print(ui.render_live(demo_cfg(), DemoLogger(), time.monotonic() - 221, rate, 3))


def summary(c: Console) -> None:
    c.print(ui.summary_panel(demo_cfg(), DemoLogger(), 221))


def main() -> None:
    settings.anim = False
    # Штамп времени у статусных строк — фиксированный, чтобы скриншоты не «дрожали» в диффах
    ui.time.strftime = lambda fmt, *a: "14:22:05"
    # Английские — для README на en/es/zh, русские (*.ru.svg) — для README.ru.md
    for lang, suffix in (("en", ""), ("ru", ".ru")):
        settings.lang = lang
        shoot("start", "httpcrabber", start, suffix)
        shoot("live", "httpcrabber — live intercept", live, suffix)
        shoot("summary", "httpcrabber — session summary", summary, suffix)


if __name__ == "__main__":
    main()
