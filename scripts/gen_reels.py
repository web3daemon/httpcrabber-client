"""Reels 9:16 с вшитыми субтитрами — серия коротких роликов про httpcrabber.

    python scripts/gen_reels.py [NAME ...]        # по умолчанию все; результат в build/media/reels

Каждый ролик — список сцен: картинка (кадры терминала, скриншот, карточка) и
подпись. Кадр 1080×1920 собирается в Chrome из HTML-шаблона: логотип сверху,
содержимое по центру, субтитр ниже — вне зоны кнопок Instagram (правые 140 px и
нижние 320 px). Рядом с MP4 кладётся .srt с теми же подписями.

Нужны Chrome/Chromium и ffmpeg. Кадры терминала берутся из кэша gen_video.py.
"""

import hashlib
import html
import io
import json
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_demo import ROWS, WIDTH, Lines, scenario  # noqa: E402
from gen_logo import find_chrome  # noqa: E402
from gen_screenshots import THEME  # noqa: E402
from gen_video import chrome_png, render_frames  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.text import Text  # noqa: E402

from httpcrabber import __version__, openapi, ui  # noqa: E402
from httpcrabber.config import settings  # noqa: E402
from httpcrabber.dump import Exchange  # noqa: E402

OUT = ROOT / "build" / "media" / "reels"
CACHE = ROOT / "build" / "media" / ".frames"
W, H, FPS = 1080, 1920, 30


@dataclass
class Scene:
    caption: str                                   # **так** — выделение неоном
    frames: list[tuple[Path, float]] = field(default_factory=list)
    card: str | None = None                        # HTML вместо картинки (финальная карточка)


# ── содержимое: терминал ─────────────────────────────────────────────────────

def terminal_png(renderables, key: str, rows: int, chrome: str, width: int = WIDTH) -> Path:
    """Кадр терминала (как в демо) → PNG, с кэшем по содержимому.

    Узкий терминал (width < 100) — для крупного текста на экране телефона.
    """
    con = Console(record=True, width=width, force_terminal=True, color_system="truecolor",
                  file=io.StringIO())
    con.print(Lines(renderables, rows))
    uid = "r" + hashlib.sha1(key.encode()).hexdigest()[:10]  # только [a-z0-9]: это имя CSS-класса
    svg = con.export_svg(title="httpcrabber", theme=THEME, unique_id=uid)
    digest = hashlib.sha1(svg.encode()).hexdigest()[:16]
    png = CACHE / "reels" / f"term_{digest}.png"
    if not png.exists():
        png.parent.mkdir(parents=True, exist_ok=True)
        view = svg.split('viewBox="0 0 ', 1)[1].split('"', 1)[0].split()
        page = png.with_suffix(".html")
        page.write_text(f'<html><body style="margin:0">{svg}</body></html>', encoding="utf-8")
        chrome_png(chrome, page, png, (int(float(view[0])), int(float(view[1]))), scale=2)
    return png


def live_frames(chrome: str, lang: str, limit: int = 14) -> list[tuple[Path, float]]:
    """Кадры живого перехвата из сценария демо (уже отрендерены gen_video.py)."""
    frames, _, _ = render_frames(chrome, lang, CACHE / f"v{__version__}-{ROWS}")
    random.seed(7)
    settings.lang = lang
    live_title = {"en": "SESSION LIVE", "ru": "СЕССИЯ АКТИВНА"}[lang]
    picked = []
    for (png, _), (renderables, _) in zip(frames, scenario(), strict=True):
        con = Console(record=True, width=WIDTH, file=io.StringIO())
        con.print(*renderables)
        if live_title in con.export_text() and "✓" not in con.export_text():
            picked.append((png, 0.26))
    return picked[1:limit + 1]


def command_frames(chrome: str, command: str, result: str,
                   width: int = 46) -> list[tuple[Path, float]]:
    """Набор команды по буквам, затем строка результата — в узком терминале."""
    prompt = Text("$ ", style=ui.NEON)
    out = []
    steps = [int(len(command) * k) for k in (0.25, 0.5, 0.75, 1.0)]
    for n in steps:
        line = prompt + Text(command[:n], style="bold white") + Text("▌", style=ui.NEON)
        out.append((terminal_png([line], f"c{n}{command}", 7, chrome, width), 0.18))
    done = [prompt + Text(command, style="bold white"), Text(""), Text.from_markup(result)]
    out.append((terminal_png(done, "r" + result, 7, chrome, width), 1.9))
    return out


# ── содержимое: Swagger UI ───────────────────────────────────────────────────

def demo_spec() -> dict:
    """Спека «api.target.com» — тот же вымышленный сайт, что в демо и скриншотах."""
    auth = [("Authorization", "Bearer eyJhbGciOiJIUzI1NiJ9.demo"), ("X-Client-Version", "4.2.0")]

    def ex(method, path, status, resp, req=None, headers=auth):
        return Exchange(
            id=path, started="", method=method, url="https://api.target.com" + path,
            req_headers=[("Content-Type", "application/json"), *headers] if req else list(headers),
            req_body=json.dumps(req) if req else None, status=status,
            resp_headers=[("Content-Type", "application/json")],
            resp_body=json.dumps(resp) if resp is not None else "")

    user = {"id": 42, "handle": "crab", "email": "crab@target.com", "plan": "pro",
            "created_at": "2026-03-14T09:26:53Z", "avatar_url": "https://cdn.target.com/a/42.png"}
    post = {"id": 912, "title": "Launch notes", "author": {"id": 7, "handle": "crab"},
            "likes": 128, "created_at": "2026-09-24T14:22:11Z", "tags": ["release"]}
    exchanges = [
        ex("POST", "/v2/auth/login", 200, {"token": "eyJhbGciOi...", "expires_in": 3600},
           {"email": "crab@target.com", "password": "hunter2"}, headers=[]),
        ex("GET", "/v2/users/42", 200, user), ex("GET", "/v2/users/57", 200, {**user, "id": 57}),
        ex("GET", "/v2/users/57/posts?limit=20", 200, {"items": [post], "next": None}),
        ex("GET", "/v2/posts/912", 200, post),
        ex("GET", "/v2/posts/912/comments?page=1", 200, {"items": [{"id": 1, "text": "gg"}]}),
        ex("GET", "/v2/feed?cursor=eyJpZCI6MTQ3OH0", 200, {"items": [post], "next": "eyJpZCI6OTEyfQ"}),
        ex("PUT", "/v2/profile/settings", 200, {"ok": True}, {"theme": "dark", "lang": "ru"}),
        ex("POST", "/v2/graphql", 200, {"data": {"viewer": {"id": 42}}},
           {"operationName": "Viewer", "query": "query Viewer { viewer { id } }"}),
        ex("DELETE", "/v2/session", 204, None),
    ]
    spec = openapi.build(exchanges, session_name="target_recon")
    spec["info"]["title"] = "api.target.com API"
    return spec


def swagger_png(chrome: str, spec: dict, name: str, only: str | None = None,
                width: int = 760, height: int = 880) -> Path:
    """Скриншот Swagger UI. only — путь, который показать одним раскрытым блоком.

    Узкое окно (760 CSS px) потом растягивается до 1000 px — текст крупнее на телефоне.
    """
    png = CACHE / "reels" / f"swagger_{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    if only:
        spec = {**spec, "paths": {only: spec["paths"][only]}}
        spec["info"] = {**spec["info"], "description": ""}
    scroll = """
      setTimeout(() => document.querySelector('.opblock-summary-control')?.click(), 300);
    """ if only else ""
    page = png.with_suffix(".html")
    page.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>body{{margin:0;background:#fff}} .swagger-ui .topbar{{display:none}}
.swagger-ui .information-container{{padding-top:6px}} .swagger-ui .info{{margin:18px 0}}</style>
</head><body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({{spec: {json.dumps(spec)}, dom_id: '#ui', docExpansion: 'list',
  defaultModelsExpandDepth: -1, defaultModelExpandDepth: 4, tryItOutEnabled: false,
  onComplete() {{ {scroll} }} }});</script></body></html>""", encoding="utf-8")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--allow-file-access-from-files", "--force-device-scale-factor=2",
                    "--virtual-time-budget=9000", f"--window-size={width},{height}",
                    f"--screenshot={png}", page.as_uri()], check=True, capture_output=True)
    return png


# ── сборка кадра и ролика ────────────────────────────────────────────────────

def _caption_html(text: str) -> str:
    out = html.escape(text)
    parts = out.split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


CSS = f"""
body {{ margin:0; width:{W}px; height:{H}px; overflow:hidden; position:relative; color:#e8f0e8;
  font-family:'JetBrains Mono','Cascadia Code',Consolas,monospace;
  background: radial-gradient(circle at 20% 12%, rgba(255,90,54,.18), transparent 42%),
              radial-gradient(circle at 85% 88%, rgba(255,47,208,.15), transparent 48%), #0b0f0c; }}
body::before {{ content:""; position:absolute; inset:0;
  background-image: linear-gradient(rgba(57,255,20,.06) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(57,255,20,.06) 1px, transparent 1px);
  background-size: 32px 32px; }}
.logo {{ position:absolute; left:{(W - 520) // 2}px; top:96px; width:520px; }}
.stage {{ position:absolute; left:40px; right:40px; top:300px; height:1060px;
  display:flex; align-items:center; justify-content:center; }}
.stage img {{ width:1000px; max-height:1060px; object-fit:contain; object-position:top; border-radius:16px;
  box-shadow: 0 0 0 2px rgba(57,255,20,.35), 0 20px 60px rgba(0,0,0,.6); }}
.cap {{ position:absolute; left:60px; right:150px; top:1395px; font-size:50px; line-height:1.28;
  font-weight:700; text-shadow:0 2px 12px #000; }}
.cap b {{ color:#39ff14; }}
.card {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:56px; padding-bottom:260px; }}
.card img {{ width:980px; }}
.card .cmd {{ font-size:52px; font-weight:700; color:#39ff14; padding:26px 40px;
  border:3px solid rgba(57,255,20,.5); border-radius:18px; background:#0f1511; }}
.card .sub {{ font-size:40px; color:#00e5ff; }}
"""


def compose(chrome: str, scene: Scene, content: Path | None, work: Path) -> Path:
    logo = (ROOT / "assets" / "logo.svg").as_uri()
    key = hashlib.sha1(f"{content}|{scene.caption}|{scene.card}|{CSS}".encode()).hexdigest()[:16]
    png = work / f"frame_{key}.png"
    if png.exists():
        return png
    if scene.card is not None:
        body = f'<div class="card"><img src="{logo}">{scene.card}</div>'
    else:
        body = (f'<img class="logo" src="{logo}"><div class="stage"><img src="{content.as_uri()}">'
                f'</div><div class="cap">{_caption_html(scene.caption)}</div>')
    page = png.with_suffix(".html")
    page.write_text(f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
                    f"<body>{body}</body></html>", encoding="utf-8")
    chrome_png(chrome, page, png, (W, H))
    return png


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build(chrome: str, name: str, scenes: list[Scene], work: Path) -> Path:
    timeline: list[tuple[Path, float]] = []
    srt, t = [], 0.0
    for scene in scenes:
        start = t
        items = scene.frames or [(None, 3.0)]
        for content, duration in items:
            timeline.append((compose(chrome, scene, content, work), duration))
            t += duration
        if scene.card is None:
            srt.append(f"{len(srt) + 1}\n{_srt_time(start)} --> {_srt_time(t)}\n"
                       f"{scene.caption.replace('**', '')}\n")
    OUT.mkdir(parents=True, exist_ok=True)
    listing = work / f"{name}.txt"
    lines = []
    for png, duration in timeline:
        lines += [f"file '{png.as_posix()}'", f"duration {duration:.3f}"]
    lines.append(f"file '{timeline[-1][0].as_posix()}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target = OUT / f"{name}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", f"fps={FPS},format=yuv420p", "-map", "0:v", "-map", "1:a", "-t", f"{t:.2f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart", str(target)], check=True)
    target.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"  {target.relative_to(ROOT)}  {t:.1f}s  {target.stat().st_size / 1024 / 1024:.1f} MB")
    return target


# ── ролики ───────────────────────────────────────────────────────────────────

END = {
    "ru": '<div class="cmd">$ pipx install httpcrabber</div><div class="sub">open source · ссылка в профиле</div>',
    "en": '<div class="cmd">$ pipx install httpcrabber</div><div class="sub">open source · link in bio</div>',
}


def reel_openapi(chrome: str, lang: str) -> list[Scene]:
    spec = demo_spec()
    paths = len(spec["paths"])
    ops = sum(len(item) for item in spec["paths"].values())
    overview = swagger_png(chrome, spec, "overview")
    user_op = swagger_png(chrome, spec, "user", "/v2/users/{userId}")
    login_op = swagger_png(chrome, spec, "login", "/v2/auth/login")
    ui.time.strftime = lambda fmt, *a: "14:25:02"
    result = (f"[{ui.DIM}] 14:25:02[/]  {ui._badge(' OK ', ui.NEON)}  {paths} paths, {ops} "
              f"operations → [{ui.CYAN}]LOGS/target_recon/openapi.json[/]")
    command = command_frames(chrome, "httpcrabber openapi LOGS/target_recon", result)
    text = {
        "ru": ["Спека API любого сайта — **из обычного сёрфинга**",
               "① Пользуешься сайтом — httpcrabber **пишет весь трафик**",
               "② Одна команда — и **OpenAPI-спека готова**",
               "/users/42 и /users/57 → **/users/{userId}**",
               "Параметры и **JSON-схемы** — выведены из ответов",
               "Токены и пароли в примерах **замаскированы**"],
        "en": ["An API spec of any site — **from normal browsing**",
               "① Use the site — httpcrabber **records all traffic**",
               "② One command — **the OpenAPI spec is ready**",
               "/users/42 and /users/57 → **/users/{userId}**",
               "Parameters and **JSON schemas** — inferred from responses",
               "Tokens and passwords in examples are **redacted**"],
    }[lang]
    return [
        Scene(text[0], [(overview, 2.8)]),
        Scene(text[1], live_frames(chrome, lang)),
        Scene(text[2], command),
        Scene(text[3], [(overview, 2.6)]),
        Scene(text[4], [(user_op, 3.4)]),
        Scene(text[5], [(login_op, 3.0)]),
        Scene("", card=END[lang]),
    ]


REELS = {"openapi": reel_openapi}


def main() -> None:
    chrome = find_chrome()
    if not chrome:
        sys.exit("needs Chrome/Chromium (set HTTPCRABBER_BROWSER) and ffmpeg")
    ui.console = Console(width=WIDTH, file=io.StringIO())
    names = sys.argv[1:] or list(REELS)
    work = CACHE / "reels"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory():
        for name in names:
            for lang in ("ru", "en"):
                build(chrome, f"{name}-{lang}", REELS[name](chrome, lang), work)


if __name__ == "__main__":
    main()
