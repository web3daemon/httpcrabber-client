"""Генератор логотипа и social preview из пиксельного краба ui.PIXEL_CRAB.

    python scripts/gen_logo.py

assets/logo.svg           — шапка README, анимирована: краб щёлкает клешнями,
                            моргает и покачивается (CSS-анимация, играет как GIF)
assets/social-preview.svg — картинка 1280×640 для превью ссылок на репозиторий
assets/social-preview.png — она же растром (нужен установленный Chrome/Chromium)

Надпись набрана встроенным пиксельным шрифтом, а не системным: SVG внутри <img>
не подгружает веб-шрифты, и моноширинный фолбэк на каждой ОС выглядел бы по-своему.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from httpcrabber.ui import CRAB_COLORS, PIXEL_CRAB  # noqa: E402

OUT = ROOT / "assets"
BG = "#0b0f0c"
MONO = "ui-monospace, 'JetBrains Mono', 'Fira Code', Consolas, monospace"

# Строчный пиксельный шрифт 5×9: строки 0–1 — выносные вверх, 2–6 — x-высота,
# 7–8 — выносные вниз. Нужны только буквы названия.
GLYPHS = {
    "h": ["X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "X...X", ".....", "....."],
    "t": [".X...", ".X...", "XXXX.", ".X...", ".X...", ".X..X", "..XX.", ".....", "....."],
    "p": [".....", ".....", "XXXX.", "X...X", "X...X", "X...X", "XXXX.", "X....", "X...."],
    "c": [".....", ".....", ".XXX.", "X...X", "X....", "X...X", ".XXX.", ".....", "....."],
    "r": [".....", ".....", "X.XX.", "XX..X", "X....", "X....", "X....", ".....", "....."],
    "a": [".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX", ".....", "....."],
    "b": ["X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX.", ".....", "....."],
    "e": [".....", ".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXX.", ".....", "....."],
}

# Кадры анимации: клешни (строки 0–1, столбцы 0–5 и зеркало) и глаза (строки 2–4)
CLAW_ROWS, CLAW_COLS = (0, 1), range(0, 6)
CLAW_CLOSED = ["..OO..", ".OOOO."]
EYE_ROWS, EYE_COLS = (2, 3, 4), range(8, 11)
EYE_CLOSED = ["...", "WWW", "..."]


def _mirror(col: int) -> int:
    return len(PIXEL_CRAB[0]) - 1 - col


def _rects(cells, px: int) -> str:
    return "".join(
        f'<rect x="{x * px}" y="{y * px}" width="{px}" height="{px}" fill="{CRAB_COLORS[ch]}"/>'
        for x, y, ch in cells if ch in CRAB_COLORS
    )


def crab_layers(px: int) -> dict[str, str]:
    """Краб, разложенный на неподвижную основу и сменные кадры клешней и глаз."""
    claw = {(c, r) for r in CLAW_ROWS for c in CLAW_COLS}
    claw |= {(_mirror(c), r) for c, r in claw}
    eye = {(c, r) for r in EYE_ROWS for c in EYE_COLS}
    eye |= {(_mirror(c), r) for c, r in eye}

    cells = [(x, y, ch) for y, row in enumerate(PIXEL_CRAB) for x, ch in enumerate(row)]
    closed_claw = []
    for i, r in enumerate(CLAW_ROWS):
        for j, c in enumerate(CLAW_COLS):
            closed_claw += [(c, r, CLAW_CLOSED[i][j]), (_mirror(c), r, CLAW_CLOSED[i][j])]
    closed_eye = []
    for i, r in enumerate(EYE_ROWS):
        for j, c in enumerate(EYE_COLS):
            closed_eye += [(c, r, EYE_CLOSED[i][j]), (_mirror(c), r, EYE_CLOSED[i][j])]
    return {
        "base": _rects([cl for cl in cells if cl[:2] not in claw | eye], px),
        "claw-open": _rects([cl for cl in cells if cl[:2] in claw], px),
        "claw-closed": _rects(closed_claw, px),
        "eye-open": _rects([cl for cl in cells if cl[:2] in eye], px),
        "eye-closed": _rects(closed_eye, px),
    }


def crab_static(px: int) -> str:
    return _rects([(x, y, ch) for y, row in enumerate(PIXEL_CRAB) for x, ch in enumerate(row)], px)


def wordmark(text: str, px: int, fill: str) -> tuple[str, int]:
    """Пиксельная надпись; возвращает (svg, ширина в px)."""
    rects, x0 = [], 0
    for ch in text:
        for y, row in enumerate(GLYPHS[ch]):
            for x, bit in enumerate(row):
                if bit == "X":
                    rects.append(f'<rect x="{(x0 + x) * px}" y="{y * px}" width="{px}" height="{px}"/>')
        x0 += len(GLYPHS[ch][0]) + 1
    width = (x0 - 1) * px
    return f'<g fill="{fill}">{"".join(rects)}</g>', width


def defs(grad_x1: float, grad_x2: float, grid: int) -> str:
    return f"""<defs>
    <linearGradient id="word" gradientUnits="userSpaceOnUse" x1="{grad_x1}" y1="0" x2="{grad_x2}" y2="0">
      <stop offset="0" stop-color="#39ff14"/><stop offset="0.5" stop-color="#00e5ff"/><stop offset="1" stop-color="#ff2fd0"/>
    </linearGradient>
    <filter id="glow" x="-10%" y="-30%" width="120%" height="160%">
      <feGaussianBlur stdDeviation="5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <pattern id="grid" width="{grid}" height="{grid}" patternUnits="userSpaceOnUse">
      <path d="M{grid} 0H0V{grid}" fill="none" stroke="#39ff14" stroke-opacity="0.07"/>
    </pattern>
  </defs>"""


ANIM_CSS = """<style>
    .claw-closed, .eye-closed { opacity: 0 }
    .claw-open   { animation: on-off 3.2s step-end infinite }
    .claw-closed { animation: off-on 3.2s step-end infinite }
    .eye-open    { animation: blink-o 4.3s step-end infinite }
    .eye-closed  { animation: blink-c 4.3s step-end infinite }
    .bob         { animation: bob 1.2s step-end infinite }
    @keyframes on-off  { 0% {opacity:1} 60% {opacity:0} 66% {opacity:1} 72% {opacity:0} 78% {opacity:1} }
    @keyframes off-on  { 0% {opacity:0} 60% {opacity:1} 66% {opacity:0} 72% {opacity:1} 78% {opacity:0} }
    @keyframes blink-o { 0% {opacity:1} 90% {opacity:0} 94% {opacity:1} }
    @keyframes blink-c { 0% {opacity:0} 90% {opacity:1} 94% {opacity:0} }
    @keyframes bob     { 0% {transform:translateY(0)} 50% {transform:translateY(-PXpx)} }
  </style>"""


def logo() -> str:
    w, h, px, wpx = 880, 240, 8, 7
    crab_w, crab_h = len(PIXEL_CRAB[0]) * px, len(PIXEL_CRAB) * px
    cx, cy = 56, (h - crab_h) // 2 + 4
    word, word_w = wordmark("httpcrabber", wpx, "url(#word)")
    wx, wy = cx + crab_w + 52, 50
    layers = crab_layers(px)
    crab = "".join(f'<g class="{k}">{v}</g>' if k != "base" else v for k, v in layers.items())
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="httpcrabber">
  <title>httpcrabber</title>
  {ANIM_CSS.replace("PX", str(px // 2))}
  {defs(0, word_w, 24)}
  <rect width="{w}" height="{h}" rx="18" fill="{BG}"/>
  <rect width="{w}" height="{h}" rx="18" fill="url(#grid)"/>
  <rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="#ff2fd0" stroke-opacity="0.45"/>
  <g transform="translate({cx} {cy})" shape-rendering="crispEdges">
    <g class="bob">{crab}</g>
  </g>
  <g transform="translate({wx} {wy})" shape-rendering="crispEdges" filter="url(#glow)">{word}</g>
  <g font-family="{MONO}">
    <text x="{wx}" y="{wy + 9 * wpx + 34}" font-size="20" fill="#00e5ff">network-level traffic interceptor</text>
    <text x="{wx}" y="{wy + 9 * wpx + 62}" font-size="14" fill="#6f7f6f">invisible to in-page JavaScript · built on mitmproxy</text>
  </g>
</svg>
"""


def _feed_row(y: int, t: str, method: str, mcolor: str, code: str, host: str, path: str,
              newest: bool = False) -> str:
    sp = "&#160;"
    mark = f'<tspan fill="#39ff14">▸{sp}</tspan>' if newest else f"<tspan>{sp * 2}</tspan>"
    bold = ' font-weight="700"' if newest else ""
    return (f'<text x="584" y="{y}">{mark}'
            f'<tspan fill="{"#9aa89a" if newest else "#5f6f5f"}">{t}{sp}│{sp}</tspan>'
            f'<tspan fill="{mcolor}" font-weight="700">{method.ljust(7).replace(" ", sp)}</tspan>'
            f'<tspan fill="#39ff14" font-weight="700">{code.ljust(4).replace(" ", sp)}</tspan>'
            f'<tspan fill="#5f6f5f">│{sp}</tspan>'
            f'<tspan fill="#ffffff"{bold}>{host}</tspan>'
            f'<tspan fill="{"#9aa89a" if newest else "#5f6f5f"}">{path}</tspan></text>')


def social() -> str:
    w, h, px, wpx = 1280, 640, 14, 10
    crab_h = len(PIXEL_CRAB) * px
    cx, cy = 90, (h - crab_h) // 2 - 10
    word, word_w = wordmark("httpcrabber", wpx, "url(#word)")
    wx, wy = 560, 150
    rows = [
        _feed_row(462, "14:22:07", "POST", "#ff2fd0", "200", "api.target.com", "/v2/graphql"),
        _feed_row(492, "14:22:08", "WS", "#ff2fd0", "→", "realtime.target.com", "/socket"),
        _feed_row(522, "14:22:09", "GET", "#00e5ff", "200", "cdn.target.com", "/main.js", True),
    ]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="httpcrabber — network-level traffic interceptor">
  <title>httpcrabber — network-level traffic interceptor</title>
  {defs(0, word_w, 32)}
  <radialGradient id="halo" cx="0.2" cy="0.5" r="0.45">
    <stop offset="0" stop-color="#ff5a36" stop-opacity="0.2"/><stop offset="1" stop-color="#ff5a36" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="halo2" cx="0.85" cy="0.1" r="0.6">
    <stop offset="0" stop-color="#ff2fd0" stop-opacity="0.14"/><stop offset="1" stop-color="#ff2fd0" stop-opacity="0"/>
  </radialGradient>
  <rect width="{w}" height="{h}" fill="{BG}"/>
  <rect width="{w}" height="{h}" fill="url(#grid)"/>
  <rect width="{w}" height="{h}" fill="url(#halo)"/>
  <rect width="{w}" height="{h}" fill="url(#halo2)"/>
  <rect x="24" y="24" width="{w - 48}" height="{h - 48}" rx="22" fill="none" stroke="#ff2fd0" stroke-opacity="0.35"/>
  <g transform="translate({cx} {cy})" shape-rendering="crispEdges">{crab_static(px)}</g>
  <g transform="translate({wx} {wy})" shape-rendering="crispEdges" filter="url(#glow)">{word}</g>
  <g font-family="{MONO}">
    <text x="{wx}" y="304" font-size="27" fill="#d6ded6">Network-level traffic interceptor</text>
    <text x="{wx}" y="342" font-size="27" fill="#d6ded6">for reverse-engineering web APIs.</text>
    <text x="{wx}" y="390" font-size="21" fill="#00e5ff">invisible to in-page JavaScript protections</text>
    <g font-size="17">
      <rect x="560" y="428" width="620" height="112" rx="10" fill="#0f1511" stroke="#39ff14" stroke-opacity="0.25"/>
      {"".join(rows)}
    </g>
    <text x="96" y="582" font-size="18" fill="#5f6f5f">mitmproxy · socks5 · websocket · js capture · windows · macos · linux</text>
  </g>
</svg>
"""


def find_chrome() -> str | None:
    env = os.environ.get("HTTPCRABBER_BROWSER")
    if env:
        return env
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(p).exists():
            return p
    return next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser")
                 if shutil.which(n)), None)


def rasterize(svg: Path, png: Path, size: tuple[int, int]) -> bool:
    chrome = find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(f'<html><body style="margin:0;background:{BG}">{svg.read_text("utf-8")}'
                        "</body></html>", encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--user-data-dir={Path(tmp) / 'profile'}",
                        f"--window-size={size[0]},{size[1]}", f"--screenshot={png}",
                        page.as_uri()], check=True, capture_output=True)
    return True


def write(name: str, svg: str) -> Path:
    path = OUT / name
    path.write_text(svg, encoding="utf-8", newline="\n")
    print(f"  {path.relative_to(ROOT)}")
    return path


def main() -> None:
    write("logo.svg", logo())
    sp = write("social-preview.svg", social())
    png = OUT / "social-preview.png"
    if rasterize(sp, png, (1280, 640)):
        print(f"  {png.relative_to(ROOT)}")
    else:
        print("  social-preview.png skipped: Chrome not found (set HTTPCRABBER_BROWSER)")


if __name__ == "__main__":
    main()
