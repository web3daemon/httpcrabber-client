"""Весь визуал: анимации, панели, живая лента, итоговая сводка."""

import random
import threading
import time
from collections import deque
from collections.abc import Iterable

from rich.align import Align
from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from httpcrabber import __version__
from httpcrabber.config import (
    CYAN,
    DIM,
    ERR,
    FEED_ROWS,
    GRADIENT,
    MAG,
    NEON,
    WARN,
    WHITE,
    console,
    settings,
)
from httpcrabber.i18n import t

BANNER = r"""
 ██╗  ██╗████████╗████████╗██████╗  ██████╗██████╗  █████╗ ██████╗ ██████╗ ███████╗██████╗
 ██║  ██║╚══██╔══╝╚══██╔══╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
 ███████║   ██║      ██║   ██████╔╝██║     ██████╔╝███████║██████╔╝██████╔╝█████╗  ██████╔╝
 ██╔══██║   ██║      ██║   ██╔═══╝ ██║     ██╔══██╗██╔══██║██╔══██╗██╔══██╗██╔══╝  ██╔══██╗
 ██║  ██║   ██║      ██║   ██║     ╚██████╗██║  ██║██║  ██║██████╔╝██████╔╝███████╗██║  ██║
 ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝      ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
"""
_LINES = BANNER.strip("\n").split("\n")

_RAIN_CHARS = "01<>[]{}/\\|=+*#$%&@?!ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾅﾆﾇﾈﾊﾋﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ"
_RAIN_SHADES = ["#0a2f0a", "#0f5c0f", "#179317", "#25cc1b", "#39ff14", "#b9ffb0"]
_GLITCH_CHARS = "▓▒░#@%&$/\\|=+*<>"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_BLOCKS = " ▁▂▃▄▅▆▇█"

_METHOD_STYLE = {
    "GET": CYAN, "POST": MAG, "PUT": WARN, "PATCH": WARN,
    "DELETE": ERR, "WS": MAG, "ERR": ERR,
}


# ── примитивы ────────────────────────────────────────────────────────────────

def gradient_banner(noise: float = 0.0) -> Text:
    """Баннер с вертикальным градиентом; noise>0 подмешивает помехи."""
    out = Text()
    for i, line in enumerate(_LINES):
        color = GRADIENT[i * (len(GRADIENT) - 1) // max(1, len(_LINES) - 1)]
        for ch in line:
            if noise and ch != " " and random.random() < noise:
                out.append(random.choice(_GLITCH_CHARS), style=random.choice([MAG, CYAN, WARN]))
            else:
                out.append(ch, style=f"bold {color}")
        out.append("\n")
    return out


def sparkline(values: Iterable[int], width: int = 24) -> str:
    vals = list(values)[-width:]
    if not vals:
        return ""
    top = max(vals) or 1
    return "".join(_BLOCKS[min(8, int(v / top * 8))] for v in vals)


def status_style(code: object) -> str:
    if not isinstance(code, int):
        return MAG
    if code < 300:
        return NEON
    if code < 400:
        return CYAN
    if code < 500:
        return WARN
    return ERR


def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    return f"{n / 1024:.1f} KB"


def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


# ── анимации старта ──────────────────────────────────────────────────────────

def matrix_rain(seconds: float = 1.3, fps: int = 18) -> None:
    if not settings.anim:
        return
    width = max(20, min(console.width, 120))
    height = max(6, min(12, console.height - 4))
    heads = [random.randint(-height, 0) for _ in range(width)]
    tail = len(_RAIN_SHADES)

    with Live(console=console, refresh_per_second=fps, transient=True) as live:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rows = [[(" ", None)] * width for _ in range(height)]
            for x, head in enumerate(heads):
                for depth in range(tail):
                    y = head - depth
                    if 0 <= y < height:
                        rows[y][x] = (random.choice(_RAIN_CHARS), _RAIN_SHADES[tail - 1 - depth])
                if random.random() > 0.12:
                    heads[x] += 1
                if heads[x] - tail > height:
                    heads[x] = random.randint(-height, 0)
            frame = Text()
            for row in rows:
                for ch, style in row:
                    frame.append(ch, style=style)
                frame.append("\n")
            live.update(frame)
            time.sleep(1 / fps)


def glitch_banner(frames: int = 9) -> None:
    if not settings.anim:
        return
    with Live(console=console, refresh_per_second=24, transient=True) as live:
        for i in range(frames):
            live.update(Align.center(gradient_banner(noise=0.45 * (1 - i / max(1, frames - 1)))))
            time.sleep(0.045)


def typewriter(text: str, style: str = CYAN, delay: float = 0.014) -> None:
    final = Align.center(Text(text, style=style))
    if settings.anim:
        with Live(console=console, refresh_per_second=60, transient=True) as live:
            for i in range(1, len(text) + 1):
                chunk = Text(text[:i], style=style)
                chunk.append("▌", style=NEON)
                live.update(Align.center(chunk))
                time.sleep(delay)
    console.print(final)


def banner_fits() -> bool:
    """ASCII-арт шириной ~91 символ; в узком терминале он бы развалился на переносы."""
    return console.width >= max(len(line) for line in _LINES) + 6


def compact_banner() -> Text:
    """Фолбэк для узкого терминала: градиентный заголовок вместо арта."""
    word = "H T T P C R A B B E R"
    out = Text()
    for i, ch in enumerate(word):
        color = GRADIENT[i * (len(GRADIENT) - 1) // max(1, len(word) - 1)]
        out.append(ch, style=f"bold {color}")
    return out


def banner() -> None:
    if settings.anim:
        console.clear()
    matrix_rain()
    fits = banner_fits()
    if fits:
        glitch_banner()
    art = gradient_banner() if fits else compact_banner()
    title = Text.assemble(("🦀 ", ""), ("httpcrabber ", NEON), (f"v{__version__}", DIM))
    console.print(Panel(Align.center(art), title=title, border_style=MAG, padding=(0, 2)))
    typewriter(t("tagline"))
    console.print()


# ── статусные строки ─────────────────────────────────────────────────────────

def step(msg: str, status: str = "ok") -> None:
    mark, color = {"ok": ("OK", NEON), "fail": ("!!", ERR), "work": ("··", WARN),
                   "info": ("--", CYAN)}[status]
    console.print(f"[{DIM}]\\[[/][{color}] {mark} [/][{DIM}]][/] {msg}")


class Spinner:
    """`with Spinner(msg) as sp:` — крутит спиннер, пока идёт работа (синхронная
    или async), затем печатает итоговую строку [ OK ] / [ !! ]."""

    def __init__(self, msg: str):
        self.msg = msg
        self._final = (msg, "ok")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._live: Live | None = None

    def ok(self, msg: str | None = None) -> None:
        self._final = (msg or self.msg, "ok")

    def fail(self, msg: str | None = None) -> None:
        self._final = (msg or self.msg, "fail")

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set() and self._live is not None:
            self._live.update(Text.assemble(
                (f" {SPINNER[i % len(SPINNER)]} ", WARN), (self.msg, WHITE)))
            i += 1
            self._stop.wait(0.08)

    def __enter__(self) -> "Spinner":
        if settings.anim:
            self._live = Live(console=console, refresh_per_second=15, transient=True)
            self._live.start()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._live:
            self._live.stop()
        if exc_type is not None:
            self._final = (self.msg, "fail")
        step(*self._final)


# ── панели ───────────────────────────────────────────────────────────────────

def brief_panel(cfg) -> Panel:
    """Панель «бриф сессии» перед запуском."""
    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(justify="right", style=DIM)
    tbl.add_column(style=WHITE)
    tbl.add_row(t("b_session"), f"[{MAG}]{cfg.name}[/]")
    tbl.add_row(t("b_upstream"),
                f"[{CYAN}]{cfg.proxy.display}[/]" if cfg.proxy else f"[{DIM}]{t('direct')}[/]")
    tbl.add_row(t("b_listen"), f"127.0.0.1:{cfg.proxy_port}")
    tbl.add_row(t("b_browser"),
                t("browser_auto") if cfg.launch_browser
                else t("browser_manual", port=cfg.proxy_port))
    tbl.add_row(t("b_output"), str(cfg.session_dir))
    return Panel(tbl, title=f"[{CYAN}]▸ {t('brief_title')}[/]", border_style=CYAN,
                 padding=(0, 2))


def render_feed(logger, rows: int, width: int) -> Text:
    tail = logger.feed_tail(rows)
    if not tail:
        return Text(f"   {t('waiting')}", style=DIM)
    out = Text()
    avail = max(12, width - 26)
    for ts, tag, code, url in tail:
        out.append(f" {ts}  ", style=DIM)
        out.append(f"{str(tag)[:6]:<7}", style=_METHOD_STYLE.get(tag, "white"))
        out.append(f"{str(code) if code is not None else '···':<4} ", style=status_style(code))
        out.append(url if len(url) <= avail else url[: avail - 1] + "…", style="white")
        out.append("\n")
    return out


def render_live(cfg, logger, start_ts: float, rate: deque, frame: int) -> Panel:
    s = logger.stats
    width = min(console.width, 118) - 8

    head = Table.grid(padding=(0, 2))
    head.add_column(justify="right", style=DIM)
    head.add_column(style=WHITE)
    head.add_row(t("l_session"), f"[{MAG}]{cfg.name}[/]")
    head.add_row(t("l_proxy"), cfg.proxy.display if cfg.proxy else t("direct"))
    head.add_row(t("l_listen"), f"127.0.0.1:{cfg.proxy_port}")
    head.add_row(t("l_log"), str(cfg.session_dir))

    spin = SPINNER[frame % len(SPINNER)] if settings.anim else "●"
    feed_head = Text(f" {spin}  {t('feed_title')}", style=NEON)

    # Короткие теги, чтобы строка гарантированно влезала в одну линию.
    bar = Text()
    for label, value, color in (
        ("REQ", s["request"], CYAN), ("RESP", s["response"], NEON), ("WS", s["ws"], MAG),
        ("JS", s["js"], WARN), ("ERR", s["error"], ERR if s["error"] else DIM),
    ):
        bar.append(" ● ", style=color)
        bar.append(f"{label} ", style=DIM)
        bar.append(str(value), style=color)
    bar.append(f"   {sparkline(rate, 22)}", style=NEON)
    bar.append(f"  {fmt_clock(time.monotonic() - start_ts)}", style=CYAN)

    hint = t("live_hint") if cfg.launch_browser else t("live_hint_manual")
    body = Group(head, Text(""), feed_head, render_feed(logger, FEED_ROWS, width),
                 Text(""), bar, Text(""), Align.center(Text(hint, style=DIM)))
    return Panel(body, title=f"[{NEON}]🦀 {t('live_title')}[/]", border_style=NEON,
                 padding=(1, 2))


def _hbar(value: int, top: int, width: int = 14) -> str:
    return "█" * max(1, round(value / top * width)) if top else ""


def summary_panel(cfg, logger, duration: float) -> RenderableType:
    s = logger.stats
    size = cfg.log_path.stat().st_size if cfg.log_path.exists() else 0

    left = Table.grid(padding=(0, 2))
    left.add_column(justify="right", style=DIM)
    left.add_column(style=WHITE)
    left.add_row(t("l_req"), f"[{CYAN}]{s['request']}[/]")
    left.add_row(t("l_resp"), f"[{NEON}]{s['response']}[/]")
    left.add_row(t("l_ws"), f"[{MAG}]{s['ws']}[/]")
    left.add_row(t("l_js"), f"[{WARN}]{s['js']}[/]")
    left.add_row(t("l_err"), f"[{ERR}]{s['error']}[/]" if s["error"] else "0")
    left.add_row(t("s_duration"), fmt_clock(duration))

    # Топ хостов и строки «методы/статусы» — РАЗНЫЕ таблицы: в одной общей длинная
    # строка методов растягивала колонку баров и уезжала на перенос.
    hosts = Table.grid(padding=(0, 1))
    hosts.add_column(style=WHITE, no_wrap=True)
    hosts.add_column(style=NEON, no_wrap=True)
    hosts.add_column(justify="right", style=DIM)
    top = logger.hosts.most_common(6)
    if top:
        peak = top[0][1]
        for host, n in top:
            hosts.add_row(host[:34], _hbar(n, peak), str(n))
    else:
        hosts.add_row(f"[{DIM}]{t('s_nothing')}[/]", "", "")

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style=DIM)
    meta.add_column(style=WHITE)
    methods = " · ".join(f"{m} {n}" for m, n in logger.methods.most_common(4))
    status = " · ".join(f"{c} {n}" for c, n in sorted(logger.status_classes.items()))
    meta.add_row(t("s_methods"), methods or "—")
    meta.add_row(t("s_status"), status or "—")

    right = Group(Text(t("s_top_hosts"), style=CYAN), hosts, Text(""), meta)

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()
    grid.add_row(left, right)

    # Путь к папке — отдельной строкой на всю ширину: длинный путь в левой
    # колонке сжимал бы «топ хостов» до нечитаемого.
    footer = Table.grid(padding=(0, 2))
    footer.add_column(justify="right", style=DIM)
    footer.add_column(style=WHITE)
    footer.add_row(t("s_saved"), f"[{MAG}]{cfg.session_dir}[/]")
    footer.add_row(t("s_size"), fmt_size(size))

    body = Group(grid, Text(""), footer)
    return Panel(body, title=f"[{NEON}]✓ {t('summary')}[/]", border_style=MAG, padding=(1, 2))


def farewell() -> None:
    typewriter(t("bye"), style=CYAN, delay=0.02)
