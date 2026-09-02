"""Поиск и запуск Chrome/Chromium через прокси с отдельным профилем."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from httpcrabber import procs
from httpcrabber.config import PROFILE_DIR

ENV_VAR = "HTTPCRABBER_BROWSER"

_WINDOWS = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Chromium\Application\chrome.exe",
    r"%LocalAppData%\Chromium\Application\chrome.exe",
]
_MACOS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
_LINUX_BINS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def find_browser() -> str | None:
    """Путь к бинарнику браузера. HTTPCRABBER_BROWSER имеет приоритет."""
    override = os.environ.get(ENV_VAR)
    if override and Path(override).is_file():
        return override

    if sys.platform == "win32":
        candidates = [os.path.expandvars(p) for p in _WINDOWS]
    elif sys.platform == "darwin":
        candidates = [os.path.expanduser(p) for p in _MACOS]
    else:
        candidates = [shutil.which(b) or "" for b in _LINUX_BINS]

    return next((c for c in candidates if c and Path(c).is_file()), None)


def launch(proxy_port: int, profile_dir: Path = PROFILE_DIR) -> subprocess.Popen | None:
    exe = find_browser()
    if not exe:
        return None
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--proxy-server=http://127.0.0.1:{proxy_port}",
        f"--user-data-dir={profile_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.register(proc)
    return proc
