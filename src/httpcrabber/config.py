"""Константы, палитра и изменяемые настройки времени выполнения."""

import contextlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from httpcrabber.launcher import saved_theme

APP_NAME = "httpcrabber"
REPO_URL = "https://github.com/web3daemon/httpcrabber-client"

DEFAULT_LOG_DIR = Path("LOGS")
PROFILE_DIR = Path("chrome_profile_proxy")
CONFDIR = Path.home() / ".mitmproxy"

# Тела в .jsonl режутся по этой границе (скрипты в js/ — всегда целиком).
# Переопределяется через HTTPCRABBER_MAX_BODY: тяжёлые HTML/JSON-ответы (например,
# залогиненный x.com/home или таймлайны) не влезают в 200 КБ.
MAX_BODY_SIZE = 200_000

# Бинарные тела по умолчанию заменяются плейсхолдером [binary, N bytes].
# С HTTPCRABBER_BINARY_BODIES=1 тело <= MAX_BODY_SIZE сохраняется в дампе как
# base64 (поле body: {"encoding":"base64", ...}) — иначе такие payload'ы теряются.
CAPTURE_BINARY = False

DEFAULT_PROXY_PORT = 8080      # слушает mitmproxy (в него ходит браузер)
DEFAULT_BRIDGE_PORT = 8081     # локальный мост pproxy (в него ходит mitmproxy)
FEED_ROWS = 12                 # строк живой ленты в панели

# Палитра hackotron
NEON = "bold #39ff14"
CYAN = "bold #00e5ff"
MAG = "bold #ff2fd0"
DIM = "#5f6f5f"
WARN = "bold #ffcc00"
ERR = "bold #ff3b3b"
WHITE = "bold white"
MUTED = "#9aa89a"   # вторичный текст: светлее DIM, но не спорит с акцентами
FAINT = "#344036"   # дорожки баров, разделители
INK = "#07110a"     # тёмный текст на ярких плашках-бейджах
# Градиент баннера и акцентов: неон → циан → магента
GRADIENT = ["#39ff14", "#33f56a", "#1fe9b8", "#00e5ff", "#7f8cff", "#ff2fd0"]


MONO = saved_theme() == "ink"
if MONO:
    NEON, CYAN, MAG = "bold #fafafa", "bold #dedede", "bold #c2c2c2"
    DIM, MUTED, FAINT, INK = "#929292", "#bdbdbd", "#4a4a4a", "#101010"
    WARN, ERR = "bold #d0d0d0", "bold underline #ffffff"
    GRADIENT = ["#fafafa", "#dedede", "#f4f4f4", "#a0a0a0"]


@dataclass
class Settings:
    """Настройки, которые выставляет CLI и читают остальные модули."""

    anim: bool = True
    lang: str = "ru"
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)


settings = Settings()

# На Windows консоль по умолчанию может быть в cp1251 — юникод-рамки и символы
# роняют вывод с UnicodeEncodeError. Принудительно переводим потоки в UTF-8.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8")

console = Console(style="#e5e5e5 on #101010" if MONO else None, highlight=not MONO)
