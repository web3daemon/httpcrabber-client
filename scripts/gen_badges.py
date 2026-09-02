"""Генератор self-hosted SVG-бейджей для README (стиль flat-square, палитра проекта).

    python scripts/gen_badges.py

Бейджи лежат в репозитории, а не тянутся с shields.io: тот недоступен из ряда
сетей, и README с внешними картинками там выглядел бы сломанным.
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "assets"
FONT = "Verdana,DejaVu Sans,Geneva,sans-serif"
SIZE = 11
LABEL_BG = "#1b1f23"
LABEL_FG = "#ffffff"
VALUE_FG = "#08140a"  # тёмный текст на ярком фоне читается, белый — нет


def text_width(s: str, size: int = SIZE) -> float:
    w = 0.0
    for ch in s:
        if ch in "ijl.,:;'|!·":
            w += size * 0.30
        elif ch in "ftrI ":
            w += size * 0.40
        elif ch in "mwMW":
            w += size * 0.85
        elif ch.isupper():
            w += size * 0.70
        elif ch.isdigit():
            w += size * 0.62
        else:
            w += size * 0.58
    return w


def badge(label: str, value: str, color: str, filename: str) -> None:
    pad = 10.0
    lw = round(text_width(label) + pad * 2, 1)
    vw = round(text_width(value) + pad * 2, 1)
    total = round(lw + vw, 1)
    alt = f"{label}: {value}"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{escape(alt)}">
  <title>{escape(alt)}</title>
  <g shape-rendering="crispEdges">
    <rect width="{lw}" height="20" fill="{LABEL_BG}"/>
    <rect x="{lw}" width="{vw}" height="20" fill="{color}"/>
  </g>
  <g font-family="{FONT}" font-size="{SIZE}" text-anchor="middle">
    <text x="{round(lw / 2, 1)}" y="14" fill="{LABEL_FG}">{escape(label)}</text>
    <text x="{round(lw + vw / 2, 1)}" y="14" fill="{VALUE_FG}" font-weight="bold">{escape(value)}</text>
  </g>
</svg>
"""
    OUT.mkdir(exist_ok=True)
    (OUT / filename).write_text(svg, encoding="utf-8", newline="\n")
    print(f"  {filename:24} {total:6.1f}x20  {alt}")


if __name__ == "__main__":
    badge("Python", "3.11+", "#39ff14", "badge-python.svg")
    badge("License", "GPL-3.0", "#ff2fd0", "badge-license.svg")
    badge("Platform", "Windows · macOS · Linux", "#00e5ff", "badge-platform.svg")
    badge("Built with", "mitmproxy", "#ffcc00", "badge-mitmproxy.svg")
