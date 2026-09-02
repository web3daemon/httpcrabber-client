"""Конфигурация и оркестрация сессии перехвата."""

import asyncio
import contextlib
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from rich.live import Live

from httpcrabber import browser, ca, procs, ui
from httpcrabber.bridge import start_bridge
from httpcrabber.capture import NetworkLogger
from httpcrabber.config import DEFAULT_BRIDGE_PORT, DEFAULT_PROXY_PORT, WARN, console, settings
from httpcrabber.i18n import t
from httpcrabber.proxy import Proxy


@dataclass
class SessionConfig:
    name: str
    proxy: Proxy | None
    session_dir: Path
    log_path: Path
    js_dir: Path
    proxy_port: int
    bridge_port: int
    launch_browser: bool = True


def sanitize_session(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name.strip()).strip("_").lower()
    return slug or "session"


def unique_session_dir(base: Path, slug: str) -> Path:
    """LOGS/<slug>/, при коллизии — <slug>_2, _3, … Старые сессии не перезатираются."""
    base.mkdir(parents=True, exist_ok=True)
    path = base / slug
    n = 2
    while path.exists():
        path = base / f"{slug}_{n}"
        n += 1
    path.mkdir(parents=True)
    return path


def make_config(name: str, proxy: Proxy | None, *, launch_browser: bool = True,
                port: int | None = None) -> SessionConfig:
    slug = sanitize_session(name)
    session_dir = unique_session_dir(settings.log_dir, slug)
    proxy_port = procs.free_port(port or DEFAULT_PROXY_PORT)
    return SessionConfig(
        name=name.strip(),
        proxy=proxy,
        session_dir=session_dir,
        log_path=session_dir / f"{slug}.jsonl",
        js_dir=session_dir / "js",
        proxy_port=proxy_port,
        bridge_port=procs.free_port(DEFAULT_BRIDGE_PORT if proxy_port != DEFAULT_BRIDGE_PORT
                                    else DEFAULT_BRIDGE_PORT + 1),
        launch_browser=launch_browser,
    )


def _terminate(*procs_: subprocess.Popen | None) -> None:
    for proc in procs_:
        if proc and proc.poll() is None:
            with contextlib.suppress(Exception):
                proc.terminate()


async def run_session(cfg: SessionConfig) -> NetworkLogger | None:
    """Поднимает мост, mitmproxy, CA и браузер; крутит живую панель до конца сессии.

    Возвращает логгер со статистикой или None, если старт не удался.
    """
    bridge_proc = chrome_proc = None

    # 1) upstream-мост
    if cfg.proxy:
        bridge_proc = start_bridge(cfg.proxy.pproxy_uri, cfg.bridge_port)
        with ui.Spinner(t("bridge_start")) as sp:
            ready = await procs.wait_port("127.0.0.1", cfg.bridge_port, timeout=8)
            sp.ok(t("bridge_ok")) if ready else sp.fail(t("bridge_fail"))
        if not ready:
            _terminate(bridge_proc)
            return None
        mode = [f"upstream:http://127.0.0.1:{cfg.bridge_port}"]
    else:
        mode = ["regular"]

    # 2) mitmproxy
    opts = options.Options(listen_host="127.0.0.1", listen_port=cfg.proxy_port, mode=mode)
    master = DumpMaster(opts, with_termlog=False, with_dumper=False)
    logger = NetworkLogger(cfg.log_path, cfg.js_dir)
    master.addons.add(logger)
    ui.step(t("mitm_start", port=cfg.proxy_port))

    # 3) CA-сертификат
    with ui.Spinner(t("ca_checking")) as sp:
        if ca.is_installed():
            ca.cert_path()
            sp.ok(t("ca_ok"))
        else:
            sp.msg = t("ca_installing")
            result = ca.install()
            if result == "installed":
                sp.ok(t("ca_done"))
            elif result == "no_tool":
                sp.fail(t("ca_no_tool"))
            else:
                sp.fail(t("ca_fail"))

    # 4) браузер
    if cfg.launch_browser:
        chrome_proc = browser.launch(cfg.proxy_port)
        ui.step(t("chrome_start") if chrome_proc else t("chrome_none"),
                "ok" if chrome_proc else "fail")
    else:
        ui.step(t("chrome_skip", port=cfg.proxy_port), "info")
    console.print()

    master_task = asyncio.ensure_future(master.run())
    start_ts = time.monotonic()
    fps = 12 if settings.anim else 2
    rate: deque[int] = deque(maxlen=34)
    last_total, last_sample, frame = 0, start_ts, 0

    try:
        with Live(ui.render_live(cfg, logger, start_ts, rate, 0), console=console,
                  refresh_per_second=fps) as live:
            while not master_task.done():
                # Конец по закрытию браузера (грейс на «форк» первого процесса Chrome).
                if chrome_proc and chrome_proc.poll() is not None \
                        and time.monotonic() - start_ts > 3:
                    break
                now = time.monotonic()
                if now - last_sample >= 0.5:
                    total = logger.stats["request"]
                    rate.append(total - last_total)
                    last_total, last_sample = total, now
                live.update(ui.render_live(cfg, logger, start_ts, rate, frame))
                frame += 1
                await asyncio.sleep(1 / fps)
    except KeyboardInterrupt:
        pass
    finally:
        # Синхронную очистку делаем ПЕРВОЙ — её нельзя прервать отменой: закрываем
        # дамп (данные уже на диске благодаря строчной буферизации) и гасим детей.
        with contextlib.suppress(Exception):
            console.print(f"\n[{WARN}]{t('ending')}[/]")
        master.shutdown()
        logger.done()
        _terminate(chrome_proc, bridge_proc)
        # CancelledError — BaseException, поэтому подавляем широко.
        with contextlib.suppress(BaseException):
            await asyncio.shield(master_task)

    logger.duration = time.monotonic() - start_ts
    return logger
