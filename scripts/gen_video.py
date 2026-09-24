"""Демо-видео для соцсетей: те же кадры, что в assets/demo.svg, но в MP4.

    python scripts/gen_video.py [OUT_DIR]        # по умолчанию build/media

Нужны Chrome/Chromium (рендер кадров) и ffmpeg в PATH. Результат:

    x-en.mp4, x-ru.mp4            1920×1080 — X / YouTube
    feed-en.mp4, feed-ru.mp4      1080×1350 — лента Instagram (4:5)
    reels-en.mp4, reels-ru.mp4    1080×1920 — Reels / Stories / TikTok (9:16)

Кадр терминала рендерится один раз на язык, фон с логотипом и подписями — один
раз на формат; ffmpeg накладывает кадры на фон с их длительностями из сценария.
"""

import io
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_demo import ROWS, WIDTH, Lines, scenario  # noqa: E402
from gen_logo import find_chrome  # noqa: E402
from gen_screenshots import THEME  # noqa: E402
from rich.console import Console  # noqa: E402

from httpcrabber import __version__, ui  # noqa: E402
from httpcrabber.config import settings  # noqa: E402

FPS = 30
TEXT = {
    "en": {
        "tagline": "network-level traffic interceptor for reverse-engineering web APIs",
        "points": ["record a browsing session at the network level",
                   "OpenAPI spec, HAR and curl from the traffic",
                   "browse and replay requests in the terminal"],
    },
    "ru": {
        "tagline": "перехват трафика на уровне сети для реверса веб-API",
        "points": ["записывает сессию браузера на уровне сети",
                   "OpenAPI-спека, HAR и curl из трафика",
                   "разбор и повтор запросов в терминале"],
    },
}
# формат: (ширина, высота, ширина кадра терминала, y кадра, шаблон подложки)
LAYOUTS = {
    "x": (1920, 1080, 1500, 140, "wide"),
    "feed": (1080, 1350, 1000, 320, "feed"),
    "reels": (1080, 1920, 1000, 500, "reels"),
}


def chrome_png(chrome: str, html: Path, png: Path, size: tuple[int, int], scale: int = 1) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--allow-file-access-from-files", f"--user-data-dir={profile}",
                        f"--force-device-scale-factor={scale}", "--virtual-time-budget=4000",
                        f"--window-size={size[0]},{size[1]}", f"--screenshot={png}",
                        html.as_uri()], check=True, capture_output=True)


def render_frames(chrome: str, lang: str, work: Path) -> tuple[list[tuple[Path, float]], int, int]:
    """Кадры сценария → PNG; возвращает [(png, длительность)], ширину и высоту кадра.

    PNG кэшируются в work: при повторном запуске (правки подложки) рендерится
    только то, чего нет. Удали папку .frames, чтобы перерисовать всё.
    """
    random.seed(7)
    settings.lang, settings.anim = lang, False
    frames = scenario()
    out, size = [], (0, 0)
    work.mkdir(parents=True, exist_ok=True)
    for i, (renderables, duration) in enumerate(frames):
        con = Console(record=True, width=WIDTH, force_terminal=True, color_system="truecolor",
                      file=io.StringIO())
        con.print(Lines(renderables, ROWS))
        svg = con.export_svg(title="httpcrabber", theme=THEME, unique_id=f"v{i}")
        w = int(float(svg.split('viewBox="0 0 ', 1)[1].split()[0]))
        h = int(float(svg.split('viewBox="0 0 ', 1)[1].split()[1].rstrip('"')))
        size = (w, h)
        page = work / f"{lang}_{i:03d}.html"
        page.write_text(f'<html><body style="margin:0;background:transparent">{svg}</body></html>',
                        encoding="utf-8")
        png = work / f"{lang}_{i:03d}.png"
        if not png.exists():
            chrome_png(chrome, page, png, (w, h), scale=2)
        out.append((png, duration))
        print(f"\r  frames {lang}: {i + 1}/{len(frames)}", end="", flush=True)
    print()
    return out, *size


def background(chrome: str, layout: str, lang: str, work: Path, frame_h: int) -> Path:
    width, height, fw, fy, kind = LAYOUTS[layout]
    logo = (ROOT / "assets" / "logo.svg").as_uri()
    t = TEXT[lang]
    points = "".join(f"<li>{p}</li>" for p in t["points"])
    bottom = fy + frame_h + 36
    foot = f'<div class="foot">github.com/web3daemon/httpcrabber-client · v{__version__}</div>'
    if kind == "wide":  # текст поста в X скажет остальное — здесь только логотип и видео
        body = f"""
        <img src="{logo}" style="position:absolute;left:{(width - 400) // 2}px;top:14px;width:400px">"""
    elif kind == "feed":  # 4:5 — места мало: без слогана, логотип уже его содержит
        body = f"""
        <img src="{logo}" style="position:absolute;left:40px;top:{fy - 285}px;width:1000px">
        <ul style="top:{bottom}px">{points}</ul>
        <div class="cmd" style="top:{bottom + 195}px">$ pipx install httpcrabber</div>{foot}"""
    else:
        body = f"""
        <img src="{logo}" style="position:absolute;left:40px;top:{fy - 290}px;width:1000px">
        <div class="tag" style="top:{bottom + 6}px">{t['tagline']}</div>
        <ul style="top:{bottom + 110}px">{points}</ul>
        <div class="cmd" style="top:{bottom + 320}px">$ pipx install httpcrabber</div>{foot}"""
    html = work / f"bg_{layout}_{lang}.html"
    html.write_text(f"""<html><head><style>
    body {{ margin:0; width:{width}px; height:{height}px; overflow:hidden; position:relative;
           background: radial-gradient(circle at 20% 15%, rgba(255,90,54,.16), transparent 45%),
                       radial-gradient(circle at 85% 90%, rgba(255,47,208,.14), transparent 50%), #0b0f0c;
           font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace; color:#d6ded6; }}
    body::before {{ content:""; position:absolute; inset:0;
           background-image: linear-gradient(rgba(57,255,20,.06) 1px, transparent 1px),
                             linear-gradient(90deg, rgba(57,255,20,.06) 1px, transparent 1px);
           background-size: 32px 32px; }}
    .tag {{ position:absolute; left:0; right:0; text-align:center; color:#00e5ff; font-size:32px; padding:0 60px; line-height:1.4; }}
    .tag b {{ color:#39ff14; font-weight:700; }}
    ul {{ position:absolute; left:90px; right:60px; margin:0; padding:0; list-style:none; font-size:30px; line-height:1.9; }}
    li::before {{ content:"◆  "; color:#ff2fd0; }}
    .cmd {{ position:absolute; left:90px; right:90px; padding:22px 30px; border:2px solid rgba(57,255,20,.45);
            border-radius:14px; background:#0f1511; color:#39ff14; font-size:34px; font-weight:700; }}
    .foot {{ position:absolute; left:0; right:0; bottom:{36 if kind == 'feed' else 70}px; text-align:center; color:#5f6f5f; font-size:24px; }}
    </style></head><body>{body}</body></html>""", encoding="utf-8")
    png = work / f"bg_{layout}_{lang}.png"
    chrome_png(chrome, html, png, (width, height))
    return png


def encode(frames: list[tuple[Path, float]], bg: Path, layout: str, out: Path) -> None:
    width, height, fw, fy, _ = LAYOUTS[layout]
    listing = out.with_suffix(".txt")
    lines = []
    for png, duration in frames:
        lines += [f"file '{png.as_posix()}'", f"duration {duration:.3f}"]
    lines.append(f"file '{frames[-1][0].as_posix()}'")  # concat требует повторить последний кадр
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", str(bg),
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",  # немая дорожка: так видео принимают все площадки
        "-filter_complex",
        f"[1:v]scale={fw}:-2:flags=lanczos,fps={FPS}[fg];"
        f"[0:v][fg]overlay=({width}-w)/2:{fy}:shortest=1,format=yuv420p[v]",
        "-map", "[v]", "-map", "2:a", "-t", f"{sum(d for _, d in frames):.2f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out),
    ], check=True)
    listing.unlink()


def main() -> None:
    chrome = find_chrome()
    if not chrome or not shutil.which("ffmpeg"):
        sys.exit("needs Chrome/Chromium (set HTTPCRABBER_BROWSER) and ffmpeg in PATH")
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "media"
    out_dir.mkdir(parents=True, exist_ok=True)
    ui.time.strftime = lambda fmt, *a: "14:22:05"
    ui.console = Console(width=WIDTH, file=io.StringIO())
    cache = out_dir / ".frames" / f"v{__version__}-{ROWS}"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for lang in ("en", "ru"):
            frames, fw_px, fh_px = render_frames(chrome, lang, cache)
            for layout, (_, _, fw, _, _) in LAYOUTS.items():
                frame_h = round(fh_px * fw / fw_px)
                bg = background(chrome, layout, lang, work, frame_h)
                target = out_dir / f"{layout}-{lang}.mp4"
                encode(frames, bg, layout, target)
                print(f"  {target}  {target.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
