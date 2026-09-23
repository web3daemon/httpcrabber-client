"""Весь визуал: анимации, панели, живая лента, итоговая сводка."""

import random
import threading
import time
from collections import deque
from collections.abc import Iterable, Iterator, Sequence

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.live import Live
from rich.measure import Measurement
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from httpcrabber import __version__
from httpcrabber.config import (
    CYAN,
    DIM,
    ERR,
    FAINT,
    FEED_ROWS,
    GRADIENT,
    INK,
    MAG,
    MUTED,
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
_ART_WIDTH = max(len(line) for line in _LINES)
_SHADOW = set("╗╝╚╔═║")  # «тень» шрифта ANSI Shadow — рисуем приглушённой для объёма

_RAIN_CHARS = "01<>[]{}/\\|=+*#$%&@?!ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾅﾆﾇﾈﾊﾋﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ"
_RAIN_SHADES = ["#0a2f0a", "#0f5c0f", "#179317", "#25cc1b", "#39ff14", "#b9ffb0"]
_GLITCH_CHARS = "▓▒░#@%&$/\\|=+*<>"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_BLOCKS = " ▁▂▃▄▅▆▇█"

_METHOD_STYLE = {
    "GET": CYAN, "POST": MAG, "PUT": WARN, "PATCH": WARN,
    "DELETE": ERR, "WS": MAG, "ERR": ERR,
}
_CLASS_STYLE = {"1xx": MUTED, "2xx": NEON, "3xx": CYAN, "4xx": WARN, "5xx": ERR}

# Пиксельный краб — единый источник для терминала, логотипа и превью
# (scripts/gen_logo.py). Хранится левая половина с центральным столбцом, правая —
# зеркало. O — панцирь, H — блик, D — тень, W — белок глаза, K — зрачок и рот.
_CRAB_LEFT = (
    ".O...O.......",
    ".OO.OO.......",
    ".OOOOO..WWW..",
    "..OOO...WKW..",
    "...O....WWW..",
    "...OO....O...",
    "....OOOOOOOOO",
    "...OOOHHOOOOO",
    "OOOOOHHOOKOOO",
    "...OOOOOOOKKK",
    "OOOOOOOOOOOOO",
    "...OODDDDDDDD",
    "..O..O.......",
    ".O....O......",
)
PIXEL_CRAB = tuple(row + row[-2::-1] for row in _CRAB_LEFT)
CRAB_COLORS = {"O": "#ff5a36", "H": "#ff9a6e", "D": "#b8321b", "W": "#ffffff", "K": "#0b0f0c"}
CRAB_WIDTH = len(PIXEL_CRAB[0])


# ── цвет ─────────────────────────────────────────────────────────────────────

def _hex(style: str) -> str:
    """'bold #39ff14' → '#39ff14'."""
    return style.split()[-1]


def blend(a: str, b: str, k: float) -> str:
    """Линейная смесь двух цветов: k=0 → a, k=1 → b."""
    a, b = _hex(a).lstrip("#"), _hex(b).lstrip("#")
    ch = (round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k)
          for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*ch)


def ramp(k: float, stops: Sequence[str] = GRADIENT) -> str:
    """Цвет в точке k∈[0,1] многоточечного градиента."""
    k = min(1.0, max(0.0, k))
    pos = k * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    return blend(stops[i], stops[i + 1], pos - i)


def gradient_text(s: str, stops: Sequence[str] = GRADIENT, bold: bool = True) -> Text:
    out = Text()
    n = max(1, len(s) - 1)
    for i, ch in enumerate(s):
        out.append(ch, style=("bold " if bold else "") + ramp(i / n, stops))
    return out


def _soft(color: str, k: float = 0.45) -> str:
    """Приглушённый вариант акцента — для рамок, чтобы не спорили с содержимым."""
    return blend(color, "#000000", k)


# ── примитивы ────────────────────────────────────────────────────────────────

def gradient_banner(noise: float = 0.0) -> Text:
    """Баннер с диагональным градиентом и приглушённой «тенью»; noise>0 — помехи."""
    out = Text()
    last = max(1, len(_LINES) - 1)
    for y, line in enumerate(_LINES):
        for x, ch in enumerate(line):
            color = ramp(0.8 * x / _ART_WIDTH + 0.2 * y / last)
            if noise and ch != " " and random.random() < noise:
                out.append(random.choice(_GLITCH_CHARS), style=random.choice([MAG, CYAN, WARN]))
            elif ch in _SHADOW:
                out.append(ch, style=_soft(color, 0.55))
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


def sparkline_text(values: Iterable[int], width: int = 24) -> Text:
    """Та же спарклайн-строка, но каждый столбик окрашен по высоте."""
    out = Text()
    for ch in sparkline(values, width):
        level = _BLOCKS.index(ch) / 8
        out.append(ch, style=ramp(0.15 + 0.6 * level) if level else FAINT)
    return out


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


def _badge(label: str, color: str) -> str:
    """Плашка с тёмным текстом на цветном фоне (rich-разметка)."""
    return f"[bold {INK} on {_hex(color)}] {label} [/]"


def _title(icon: str, text: str, color: str) -> Text:
    return Text.assemble((f" {icon} ", color), (text, color), " ")


# ── анимации старта ──────────────────────────────────────────────────────────

def matrix_rain(seconds: float = 1.3, fps: int = 18) -> None:
    if not settings.anim:
        return
    width = max(20, min(console.width, 120))
    height = max(6, min(12, console.height - 4))
    frames = rain_frames(width, height)

    with Live(console=console, refresh_per_second=fps, transient=True) as live:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            live.update(next(frames))
            time.sleep(1 / fps)


def rain_frames(width: int, height: int) -> Iterator[Text]:
    """Бесконечный поток кадров матричного дождя (его же рисует демо для README)."""
    heads = [random.randint(-height, 0) for _ in range(width)]
    tail = len(_RAIN_SHADES)
    while True:
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
        yield frame


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
    return console.width >= _ART_WIDTH + 6


def pixel_crab() -> Text:
    """Краб полублоками: две строки пикселей на одну строку терминала."""
    out = Text()
    rows = list(PIXEL_CRAB) + ["." * CRAB_WIDTH] * (len(PIXEL_CRAB) % 2)
    for top, bottom in zip(rows[::2], rows[1::2], strict=True):
        for a, b in zip(top, bottom, strict=True):
            ca, cb = CRAB_COLORS.get(a), CRAB_COLORS.get(b)
            if ca and cb:
                out.append("▀", style=f"{ca} on {cb}")
            elif ca:
                out.append("▀", style=ca)
            elif cb:
                out.append("▄", style=cb)
            else:
                out.append(" ")
        out.append("\n")
    out.rstrip()
    return out


def compact_banner() -> Text:
    """Фолбэк для узкого терминала: градиентный заголовок вместо арта."""
    return gradient_text("H T T P C R A B B E R")


def banner_panel(fits: bool = True, noise: float = 0.0) -> Panel:
    if fits and console.width >= _ART_WIDTH + CRAB_WIDTH + 14:
        # Широкий терминал — краб слева от арта
        art = Table.grid(padding=(0, 3))
        art.add_column(vertical="middle")
        art.add_column(vertical="middle")
        art.add_row(pixel_crab(), gradient_banner(noise))
    elif fits:
        art = gradient_banner(noise)
    else:
        art = Group(Align.center(pixel_crab()), Text(""), Align.center(compact_banner()))
    title = Text.assemble(" 🦀 ", ("httpcrabber", NEON), (f"  v{__version__} ", DIM))
    tags = Text.assemble(
        " ", ("http", CYAN), (" · ", DIM), ("websocket", MAG), (" · ", DIM),
        ("socks5", WARN), (" · ", DIM), ("js capture", NEON), " ",
    )
    return Panel(Align.center(art), title=title, title_align="left", subtitle=tags,
                 subtitle_align="right", box=box.ROUNDED, border_style=_soft(MAG, 0.5),
                 padding=(1 if fits else 0, 2))


def banner() -> None:
    if settings.anim:
        console.clear()
    matrix_rain()
    fits = banner_fits()
    if fits:
        glitch_banner()
    console.print(banner_panel(fits))
    typewriter(t("tagline"), style=MUTED)
    console.print()


# ── статусные строки ─────────────────────────────────────────────────────────

_STEP = {"ok": ("OK", NEON), "fail": ("FAIL", ERR), "work": ("WAIT", WARN), "info": ("INFO", CYAN)}


def step(msg: str, status: str = "ok") -> None:
    label, color = _STEP[status]
    console.print(f"[{DIM}] {time.strftime('%H:%M:%S')}[/]  {_badge(f'{label:^4}', color)}  {msg}")


def spinner_line(msg: str, frame: int, elapsed: float) -> Text:
    """Строка ожидания — выровнена по статусным строкам step()."""
    return Text.assemble(
        (f" {time.strftime('%H:%M:%S')}  ", DIM),
        (f"  {SPINNER[frame % len(SPINNER)]}   ", f"bold {ramp((frame % 24) / 23)}"),
        ("  ", ""), (msg, WHITE), (f"  {elapsed:.1f}s", DIM),
    )


class Spinner:
    """`with Spinner(msg) as sp:` — крутит спиннер, пока идёт работа (синхронная
    или async), затем печатает итоговую строку-статус с бейджем OK / FAIL."""

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
        i, t0 = 0, time.monotonic()
        while not self._stop.is_set() and self._live is not None:
            self._live.update(spinner_line(self.msg, i, time.monotonic() - t0))
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
    tbl.add_column(no_wrap=True)
    tbl.add_column(style=DIM, no_wrap=True)
    tbl.add_column(style=WHITE)
    rows = [
        (t("b_session"), f"[{MAG}]{cfg.name}[/]"),
        (t("b_upstream"),
         f"[{CYAN}]{cfg.proxy.display}[/]" if cfg.proxy else f"[{MUTED}]{t('direct')}[/]"),
        (t("b_listen"), f"127.0.0.1:[{NEON}]{cfg.proxy_port}[/]"),
        (t("b_browser"),
         t("browser_auto") if cfg.launch_browser
         else f"[{WARN}]{t('browser_manual', port=cfg.proxy_port)}[/]"),
        (t("b_output"), f"[{MUTED}]{cfg.session_dir}[/]"),
    ]
    for i, (label, value) in enumerate(rows):
        tbl.add_row(Text("◆", style=ramp(i / (len(rows) - 1))), label, value)
    return Panel(tbl, title=_title("◈", t("brief_title"), CYAN), title_align="left",
                 box=box.ROUNDED, border_style=_soft(CYAN), padding=(1, 3), expand=False)


def _split_url(url: str) -> tuple[str, str]:
    """'https://host/path?q' → ('host', '/path?q') — хост ярче, путь тише."""
    rest = url.split("://", 1)[-1]
    slash = rest.find("/")
    return (rest, "") if slash < 0 else (rest[:slash], rest[slash:])


def render_feed(logger, rows: int, width: int) -> Text:
    tail = logger.feed_tail(rows)
    out = Text(no_wrap=True, overflow="ellipsis")
    if not tail:
        out.append(f"   {t('waiting')}", style=DIM)
        out.append("\n" * max(0, rows - 1))
        return out
    sep = ("│", FAINT)
    avail = max(12, width - 28)
    for i, (ts, tag, code, url) in enumerate(tail):
        newest = i == len(tail) - 1
        host, path = _split_url(url)
        if len(host) + len(path) > avail:
            if len(host) >= avail:
                host, path = host[: avail - 1] + "…", ""
            else:
                path = path[: avail - len(host) - 1] + "…"
        out.append("▸ " if newest else "  ", style=NEON)
        out.append(f"{ts} ", style=MUTED if newest else DIM)
        out.append(*sep)
        out.append(f" {str(tag)[:7]:<8}", style=_METHOD_STYLE.get(tag, WHITE))
        out.append(f"{str(code) if code is not None else '···':<4}", style=status_style(code))
        out.append(*sep)
        out.append(f" {host}", style=WHITE if newest else "white")
        out.append(path, style=MUTED if newest else DIM)
        if i < len(tail) - 1:
            out.append("\n")
    out.append("\n" * (rows - len(tail)))  # фиксированная высота — панель не «прыгает»
    return out


def render_live(cfg, logger, start_ts: float, rate: deque, frame: int) -> Panel:
    s = logger.stats
    width = min(console.width, 118) - 8

    head = Table.grid(padding=(0, 2), expand=True)
    head.add_column(justify="right", style=DIM, no_wrap=True)
    head.add_column(style=WHITE, ratio=1, no_wrap=True, overflow="ellipsis")
    head.add_column(justify="right", style=DIM, no_wrap=True)
    head.add_column(style=WHITE, ratio=1, no_wrap=True, overflow="ellipsis")
    head.add_row(t("l_session"), f"[{MAG}]{cfg.name}[/]",
                 t("l_proxy"), f"[{CYAN}]{cfg.proxy.display}[/]" if cfg.proxy
                 else f"[{MUTED}]{t('direct')}[/]")
    head.add_row(t("l_listen"), f"127.0.0.1:[{NEON}]{cfg.proxy_port}[/]",
                 t("l_log"), f"[{MUTED}]{cfg.session_dir}[/]")

    spin = SPINNER[frame % len(SPINNER)] if settings.anim else "●"
    feed_rule = Rule(Text.assemble((f" {spin} ", NEON), (t("feed_title"), NEON), " "),
                     align="left", style=FAINT)
    cols = Text(f"  {'TIME':<11}{'METHOD':<8}{'CODE':<4}  URL", style=_soft(DIM, 0.3))

    # Короткие теги, чтобы строка гарантированно влезала в одну линию.
    bar = Text(no_wrap=True, overflow="ellipsis")
    for label, value, color in (
        ("REQ", s["request"], CYAN), ("RESP", s["response"], NEON), ("WS", s["ws"], MAG),
        ("JS", s["js"], WARN), ("ERR", s["error"], ERR if s["error"] else DIM),
    ):
        bar.append(" ● ", style=color)
        bar.append(f"{label} ", style=DIM)
        bar.append(str(value), style=color)
    clock = Text.assemble(("  ", ""), sparkline_text(rate, 22),
                          (f"  {fmt_clock(time.monotonic() - start_ts)}", CYAN))
    stats = Table.grid(expand=True)
    stats.add_column(no_wrap=True)
    stats.add_column(justify="right", no_wrap=True)
    stats.add_row(bar, clock)

    # REC мигает раз в полсекунды — видно, что сессия жива, даже без трафика.
    rec_on = not settings.anim or (frame // 6) % 2 == 0
    title = Text.assemble(" 🦀 ", (t("live_title"), NEON), "  ",
                          ("● REC", ERR if rec_on else DIM), " ")
    hint = t("live_hint") if cfg.launch_browser else t("live_hint_manual")
    body = Group(head, Text(""), feed_rule, cols, render_feed(logger, FEED_ROWS, width),
                 Rule(style=FAINT), stats)
    return Panel(body, title=title, title_align="left", subtitle=Text(f" {hint} ", style=DIM),
                 subtitle_align="center", box=box.ROUNDED, border_style=_soft(NEON, 0.35),
                 padding=(1, 2))


def _hbar(value: int, top: int, width: int = 14) -> Text:
    """Горизонтальный бар с градиентной заливкой и тёмной «дорожкой»."""
    filled = max(1, round(value / top * width)) if top else 0
    out = Text()
    for i in range(width):
        out.append("━", style=ramp(i / max(1, width - 1) * 0.6) if i < filled else FAINT)
    return out


def _stacked(parts: list[tuple[str, int]], width: int = 28) -> Text:
    """Одна полоса, поделённая по долям классов статусов."""
    total = sum(n for _, n in parts)
    out = Text()
    if not total:
        return out.append("━" * width, style=FAINT)
    used = 0
    for i, (cls, n) in enumerate(parts):
        seg = width - used if i == len(parts) - 1 else max(1, round(n / total * width))
        seg = min(seg, width - used)
        out.append("━" * seg, style=_CLASS_STYLE.get(cls, MUTED))
        used += seg
    return out


def _tile(value: object, label: str, color: str) -> Text:
    return Text.assemble(("▎", color), (str(value), color), "\n",
                         ("▎", _soft(color, 0.6)), (label.upper(), DIM))


def summary_panel(cfg, logger, duration: float) -> RenderableType:
    s = logger.stats
    size = cfg.log_path.stat().st_size if cfg.log_path.exists() else 0

    tiles = Table.grid(expand=True, padding=(0, 1))
    cells = [
        (s["request"], t("l_req"), CYAN), (s["response"], t("l_resp"), NEON),
        (s["ws"], t("l_ws"), MAG), (s["js"], t("l_js"), WARN),
        (s["error"], t("l_err"), ERR if s["error"] else DIM),
        (fmt_clock(duration), t("s_duration"), "bold #e8f0e8"),
    ]
    for _ in cells:
        tiles.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    tiles.add_row(*(_tile(*c) for c in cells))

    # Топ хостов и «методы/статусы» — РАЗНЫЕ таблицы: в одной общей длинная
    # строка методов растягивала колонку баров и уезжала на перенос.
    hosts = Table.grid(padding=(0, 1))
    hosts.add_column(style=WHITE, no_wrap=True, max_width=30, overflow="ellipsis")
    hosts.add_column(no_wrap=True)
    hosts.add_column(justify="right", style=WHITE, no_wrap=True)
    hosts.add_column(justify="right", style=DIM, no_wrap=True)
    top = logger.hosts.most_common(6)
    if top:
        peak, total = top[0][1], sum(logger.hosts.values()) or 1
        for host, n in top:
            hosts.add_row(host, _hbar(n, peak), str(n), f"{n / total:.0%}")
    else:
        hosts.add_row(f"[{DIM}]{t('s_nothing')}[/]", "", "", "")

    def joined(items, style_of) -> Text:
        out = Text()
        for i, (k, n) in enumerate(items):
            if i:
                out.append(" · ", style=FAINT)
            out.append(f"{k} ", style=style_of(k))
            out.append(str(n), style=WHITE)
        return out if items else Text("—", style=DIM)

    classes = sorted(logger.status_classes.items())
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style=DIM, no_wrap=True)
    meta.add_column()
    meta.add_row(t("s_methods"),
                 joined(logger.methods.most_common(4), lambda m: _METHOD_STYLE.get(m, WHITE)))
    meta.add_row(t("s_status"), joined(classes, lambda c: _CLASS_STYLE.get(c, MUTED)))
    meta.add_row("", _stacked(classes))

    left = Group(Text(t("s_top_hosts"), style=CYAN), hosts)
    right = Group(Text(t("s_breakdown"), style=CYAN), meta)
    # Рядом — если обе колонки влезают целиком, иначе друг под другом: сжатая
    # таблица хостов резала бы и бары, и числа.
    inner = console.width - 6
    need = sum(Measurement.get(console, console.options, r).maximum for r in (left, right)) + 4
    if need <= inner:
        grid = Table.grid(padding=(0, 4))
        grid.add_column()
        grid.add_column()
        grid.add_row(left, right)
    else:
        grid = Group(left, Text(""), right)

    # Путь к папке — отдельной строкой на всю ширину: длинный путь в колонке
    # сжимал бы «топ хостов» до нечитаемого.
    footer = Table.grid(padding=(0, 2))
    footer.add_column(justify="right", style=DIM, no_wrap=True)
    footer.add_column(style=WHITE)
    footer.add_row(t("s_saved"), f"[{MAG}]{cfg.session_dir}[/]")
    footer.add_row(t("s_size"), f"[{WHITE}]{fmt_size(size)}[/]")

    body = Group(tiles, Rule(style=FAINT), grid, Rule(style=FAINT), footer)
    return Panel(body, title=_title("✓", t("summary"), NEON), title_align="left",
                 box=box.ROUNDED, border_style=_soft(MAG, 0.4), padding=(1, 2))


def farewell() -> None:
    console.print(Align.center(pixel_crab()))
    typewriter(t("bye"), style=CYAN, delay=0.02)
