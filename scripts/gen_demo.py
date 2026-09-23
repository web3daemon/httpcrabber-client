"""Генератор анимированного демо для README: настоящие кадры ui.py, склеенные
в один SVG с CSS-анимацией (без GIF, без записи экрана, без сети).

    python scripts/gen_demo.py

assets/demo.svg     — английский интерфейс (README на en/es/zh)
assets/demo.ru.svg  — русский (README.ru.md)

Сценарий повторяет реальный запуск: матричный дождь → глитч-баннер → вопросы →
бриф → старт компонентов → живой перехват → сводка. Экран «прокручивается», как
настоящий терминал: видны последние ROWS строк вывода.
"""

import io
import random
import re
import sys
import time
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_screenshots import THEME, demo_cfg  # noqa: E402
from rich.console import Console, Group  # noqa: E402
from rich.segment import Segment  # noqa: E402
from rich.text import Text  # noqa: E402

from httpcrabber import ui  # noqa: E402
from httpcrabber.cli import QMARK  # noqa: E402
from httpcrabber.config import REPO_URL, settings  # noqa: E402
from httpcrabber.i18n import t  # noqa: E402

WIDTH, ROWS = 100, 26
OUT = ROOT / "assets"
SEP = "\x1f"
FMT = SEP.join(["{styles}", "{lines}", "{backgrounds}", "{matrix}", "{chrome}", "{width}",
                "{height}", "{terminal_x}", "{terminal_y}", "{terminal_width}",
                "{terminal_height}", "{char_height}", "{line_height}"])

PROXY = "socks5://user:pass@1.2.3.4:1080"
TRAFFIC = [
    ("GET", 200, "https://target.com/"),
    ("GET", 200, "https://cdn.target.com/static/js/main.a3f1c8d4e5b6.chunk.js"),
    ("GET", 200, "https://static.target.com/fonts/inter-var.woff2"),
    ("POST", 403, "https://api.target.com/v2/auth/challenge"),
    ("POST", 200, "https://api.target.com/v2/auth/challenge?retry=1"),
    ("GET", 304, "https://target.com/assets/app.css"),
    ("WS", "→", "wss://realtime.target.com/socket"),
    ("POST", 200, "https://api.target.com/v2/graphql?op=Viewer"),
    ("OPTIONS", 204, "https://api.target.com/v2/feed"),
    ("GET", 200, "https://api.target.com/v2/feed?cursor=eyJpZCI6MTQ3OH0"),
    ("ERR", None, "https://blocked.tracker.io/beacon"),
    ("GET", 500, "https://api.target.com/v2/telemetry/collect"),
    ("POST", 200, "https://api.target.com/v2/graphql?op=Timeline"),
    ("PUT", 201, "https://api.target.com/v2/profile/settings"),
    ("GET", 200, "https://cdn.target.com/static/js/vendor.9b2e41.js"),
    ("POST", 200, "https://api.target.com/v2/graphql?op=Notifications"),
    ("GET", 200, "https://api.target.com/v2/me"),
    ("DELETE", 204, "https://api.target.com/v2/session"),
]


class Lines:
    """Отрисовывает только последние `rows` строк — как прокрученный терминал."""

    def __init__(self, renderables, rows: int):
        self.renderables, self.rows = renderables, rows

    def __rich_console__(self, console, options):
        lines = console.render_lines(Group(*self.renderables), options, pad=False)
        lines = lines[-self.rows:]
        lines += [[]] * (self.rows - len(lines))
        for line in lines:
            yield from line
            yield Segment.line()


class LiveLogger:
    """Демо-логгер, «наполняющийся» трафиком от кадра к кадру."""

    def __init__(self):
        self.feed: list = []
        self.stats = {"request": 0, "response": 0, "ws": 0, "js": 0, "error": 0}
        self.hosts, self.methods, self.status_classes = Counter(), Counter(), Counter()

    def feed_tail(self, n):
        return self.feed[-n:]

    def tick(self, i: int, clock: str) -> None:
        tag, code, url = TRAFFIC[i % len(TRAFFIC)]
        self.feed.append((clock, tag, code, url))
        burst = random.randint(30, 110)
        self.stats["request"] += burst
        self.stats["response"] += burst - random.randint(0, 3)
        self.stats["ws"] += tag == "WS"
        self.stats["js"] += random.randint(0, 3)
        self.stats["error"] += tag == "ERR"


def prompt(question: str, answer: str = "", typing: bool = False) -> Text:
    """Строка questionary: ◆ вопрос ответ (с курсором, пока ответ печатается)."""
    line = Text.assemble((f"{QMARK} ", "bold #39ff14"), (question, "bold #00e5ff"), " ",
                         (answer, "bold #ff2fd0" if not typing else "#d6ded6"))
    if typing:
        line.append("▌", style="#39ff14")
    return line


def step_line(msg: str, status: str = "ok") -> Text:
    label, color = ui._STEP[status]
    return Text.from_markup(f"[{ui.DIM}] 14:22:05[/]  {ui._badge(f'{label:^4}', color)}  {msg}")


def scenario():
    """Кадры: (список renderables для экрана, длительность в секундах)."""
    screen: list = []
    frames = []

    def show(duration: float, *extra):
        frames.append((list(screen) + list(extra), duration))

    rain = ui.rain_frames(WIDTH, 14)
    for _ in range(9):
        frames.append(([next(rain)], 0.07))
    for noise in (0.5, 0.35, 0.2, 0.08):
        frames.append(([ui.banner_panel(True, noise)], 0.06))

    screen += [ui.banner_panel(True)]
    tagline = t("tagline")
    for k in (0.4, 0.8):
        show(0.08, ui.Align.center(Text(tagline[: int(len(tagline) * k)] + "▌", style=ui.MUTED)))
    screen += [ui.Align.center(Text(tagline, style=ui.MUTED)), Text("")]
    show(0.5)

    show(0.7, prompt(t("ask_lang"), "", True))
    screen += [prompt(t("ask_lang"), "English" if settings.lang == "en" else "Русский")]
    for k in (0.35, 0.75):
        show(0.1, prompt(t("ask_proxy"), PROXY[: int(len(PROXY) * k)], True))
    screen += [prompt(t("ask_proxy"), PROXY),
               step_line(f"{t('proxy_ok')} [{ui.CYAN}]socks5://user:****@1.2.3.4:1080[/]")]
    show(0.4)
    for part in ("TARGET", "TARGET RE"):
        show(0.1, prompt(t("ask_session"), part, True))
    screen += [prompt(t("ask_session"), "TARGET RECON"), Text("")]
    screen += [ui.brief_panel(demo_cfg()), Text("")]
    show(1.2)

    for i in range(3):
        show(0.12, ui.spinner_line(t("bridge_start"), i, i * 0.12))
    screen += [step_line(t("bridge_ok")), step_line(t("mitm_start", port=8080))]
    for i in range(2):
        show(0.12, ui.spinner_line(t("ca_checking"), i + 4, i * 0.12))
    screen += [step_line(t("ca_ok")), step_line(t("chrome_start")), Text("")]
    show(0.9)

    # живой перехват: панель перерисовывается на месте, как в Live
    logger, rate = LiveLogger(), deque(maxlen=34)
    settings.anim = True
    elapsed = 0
    for i in range(22):
        elapsed += random.randint(6, 14)
        if i:
            logger.tick(i - 1, f"14:{22 + elapsed // 60:02d}:{elapsed % 60:02d}")
            if i % 3 == 0:
                logger.tick(i + 5, f"14:{22 + elapsed // 60:02d}:{elapsed % 60:02d}")
            rate.append(random.randint(3, 25))
        panel = ui.render_live(demo_cfg(), logger, time.monotonic() - elapsed, rate, i * 3)
        frames.append(([panel], 0.32 if i else 0.6))
    settings.anim = False

    final = [ui.render_live(demo_cfg(), logger, time.monotonic() - elapsed, rate, 0),
             Text(f"\n{t('ending')}", style=ui.WARN)]
    frames.append((list(final), 0.6))
    demo = ScreenshotLogger()
    final += [ui.summary_panel(demo_cfg(), demo, 221),
              Text(REPO_URL, style=ui.DIM, justify="center"),
              ui.Align.center(ui.pixel_crab()),
              ui.Align.center(Text(t("bye"), style=ui.CYAN))]
    frames.append((final, 5.0))
    return frames


class ScreenshotLogger:
    """Итоговая статистика — та же, что на статичном скриншоте сводки."""

    def __init__(self):
        from gen_screenshots import DemoLogger
        self.__dict__.update({k: getattr(DemoLogger, k) for k in
                              ("stats", "hosts", "methods", "status_classes")})


def render(frames, title: str) -> str:
    total = sum(d for _, d in frames)
    css, body, shared = [], [], {}
    head = None
    t0 = 0.0
    for i, (renderables, duration) in enumerate(frames):
        con = Console(record=True, width=WIDTH, force_terminal=True, color_system="truecolor",
                      file=io.StringIO())
        con.print(Lines(renderables, ROWS))
        (styles, _lines, backgrounds, matrix, chrome, width, height, tx, ty, tw, th, ch,
         lh) = con.export_svg(code_format=FMT, unique_id=f"f{i}", title=title,
                              theme=THEME).split(SEP)
        if head is None:
            head = (chrome, width, height, tx, ty, tw, th, ch, lh)
        # Rich заводит свои CSS-классы и clipPath на каждую строку каждого кадра:
        # одинаковые стили сводим к общим классам, построчные клипы выбрасываем.
        local = {}
        for rule, css_body in re.findall(rf"\.f{i}-(r\d+) \{{ (.*?) \}}", styles):
            local[rule] = shared.setdefault(css_body, f"c{len(shared)}")
        backgrounds, matrix = (
            re.sub(r' clip-path="url\(#[^)]*\)"', "",
                   re.sub(rf'class="f{i}-(r\d+)"', lambda m, lc=local: f'class="{lc[m.group(1)]}"', part))
            for part in (backgrounds, matrix)
        )
        a, b = t0 / total * 100, (t0 + duration) / total * 100
        keys = f"0%{{opacity:1}}{b:.3f}%{{opacity:0}}" if i == 0 else \
            f"0%{{opacity:0}}{a:.3f}%{{opacity:1}}{b:.3f}%{{opacity:0}}"
        css.append(f"@keyframes k{i}{{{keys}}}.f{i}{{animation:k{i} {total:.2f}s step-end infinite}}")
        body.append(f'<g class="fr f{i}">{backgrounds}<g class="mx">{matrix}</g></g>')
        t0 += duration
    chrome, width, height, tx, ty, tw, th, ch, lh = head
    style = f"""
    .mx {{ font-family: "Fira Code", ui-monospace, Menlo, Consolas, monospace; font-size: {ch}px; line-height: {lh}px; font-variant-east-asian: full-width }}
    .f0-title {{ font-size: 18px; font-weight: bold; font-family: arial }}
    .fr {{ opacity: 0 }}
    {"".join(f".{c}{{{v}}}" for v, c in shared.items())}
    {"".join(css)}
    """
    svg = f"""<svg class="rich-terminal" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">
<!-- Generated by scripts/gen_demo.py from real httpcrabber UI frames (Rich) -->
<style>{style}</style>
<defs><clipPath id="clip-terminal"><rect x="0" y="0" width="{tw}" height="{th}"/></clipPath></defs>
{chrome}
<g transform="translate({tx}, {ty})" clip-path="url(#clip-terminal)">
{"".join(body)}
</g>
</svg>
"""
    # rich дублирует одинаковые CSS-правила в каждом кадре — схлопываем пробелы
    return re.sub(r"\n\s+", "\n", svg)


def main() -> None:
    ui.time.strftime = lambda fmt, *a: "14:22:05"
    # раскладка панелей зависит от ширины глобальной консоли ui — фиксируем её
    ui.console = Console(width=WIDTH, file=io.StringIO())
    for lang, suffix in (("en", ""), ("ru", ".ru")):
        random.seed(7)
        settings.lang, settings.anim = lang, False
        frames = scenario()
        path = OUT / f"demo{suffix}.svg"
        path.write_text(render(frames, "httpcrabber"), encoding="utf-8", newline="\n")
        total = sum(d for _, d in frames)
        print(f"  {path.relative_to(ROOT)}  {len(frames)} frames, {total:.1f}s, "
              f"{path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
