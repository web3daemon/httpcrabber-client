import time
from collections import Counter, deque

from rich.console import Console
from rich.panel import Panel

from httpcrabber import ui
from httpcrabber.session import make_config


class _Logger:
    def __init__(self):
        self.stats = {"request": 147, "response": 143, "ws": 6, "error": 2, "js": 38}
        self.hosts = Counter({"api.target.com": 90, "cdn.target.com": 40, "x.io": 17})
        self.methods = Counter({"GET": 120, "POST": 27})
        self.status_classes = Counter({"2xx": 130, "4xx": 11, "5xx": 2})
        self.feed = deque([
            ("12:00:00", "GET", 200, "https://cdn.target.com/a.js"),
            ("12:00:01", "POST", 403, "https://api.target.com/auth"),
            ("12:00:02", "WS", "→", "wss://rt.target.com/socket"),
            ("12:00:03", "ERR", None, "https://blocked.io/beacon"),
            ("12:00:04", "GET", 500, "https://api.target.com/" + "x" * 200),
        ])

    def feed_tail(self, n):
        return list(self.feed)[-n:]


def _render(renderable) -> str:
    c = Console(record=True, width=100, force_terminal=False)
    c.print(renderable)
    return c.export_text()


def test_sparkline_and_formatters():
    assert ui.sparkline([]) == ""
    assert ui.sparkline([0, 9]) == " █"
    assert len(ui.sparkline(range(100), width=10)) == 10
    assert ui.fmt_size(512) == "0.5 KB"
    assert ui.fmt_size(3 * 1024 * 1024) == "3.00 MB"
    assert ui.fmt_clock(65) == "01:05"
    assert ui.fmt_clock(3725) == "01:02:05"


def test_status_style_buckets():
    assert ui.status_style(200) == ui.NEON
    assert ui.status_style(301) == ui.CYAN
    assert ui.status_style(404) == ui.WARN
    assert ui.status_style(503) == ui.ERR
    assert ui.status_style(None) == ui.MAG


def test_gradient_banner_spells_name():
    plain = ui.gradient_banner().plain
    assert plain.count("\n") == 6
    assert plain.startswith("\n") is False


def test_compact_banner_for_narrow_terminals(monkeypatch):
    assert ui.compact_banner().plain.replace(" ", "") == "HTTPCRABBER"
    monkeypatch.setattr(type(ui.console), "width", property(lambda self: 80))
    assert ui.banner_fits() is False
    monkeypatch.setattr(type(ui.console), "width", property(lambda self: 120))
    assert ui.banner_fits() is True


def test_live_panel_fits_and_shows_feed():
    cfg = make_config("TARGET RECON", None)
    out = _render(ui.render_live(cfg, _Logger(), time.monotonic() - 221, deque([1, 5, 3]), 3))
    assert "TARGET RECON" in out and "LIVE INTERCEPT" in out
    assert "POST" in out and "403" in out and "blocked.io" in out
    assert "REQ 147" in out and "03:41" in out
    # длинный URL обрезан, а не перенесён
    assert "…" in out
    assert all(len(line) <= 100 for line in out.splitlines())


def test_brief_and_summary_panels():
    cfg = make_config("S", None, launch_browser=False)
    brief = _render(ui.brief_panel(cfg))
    assert "SESSION BRIEF" in brief and "127.0.0.1" in brief

    summ = _render(ui.summary_panel(cfg, _Logger(), 221))
    assert "SESSION FINISHED" in summ
    assert "api.target.com" in summ and "TOP HOSTS" in summ
    assert "GET 120" in summ and "2xx 130" in summ
    assert "03:41" in summ


def test_summary_without_traffic():
    cfg = make_config("EMPTY", None)
    lg = _Logger()
    lg.hosts.clear()
    lg.methods.clear()
    lg.status_classes.clear()
    out = _render(ui.summary_panel(cfg, lg, 1))
    assert "no traffic" in out and "Methods" in out


def test_spinner_without_anim_prints_final_line(capsys):
    with ui.Spinner("working") as sp:
        sp.ok("done ✓")
    assert "done" in capsys.readouterr().out

    with ui.Spinner("boom") as sp:
        sp.fail("failed")
    assert "failed" in capsys.readouterr().out


def test_animations_are_noops_without_anim():
    t0 = time.monotonic()
    ui.matrix_rain()
    ui.glitch_banner()
    ui.typewriter("x")
    assert time.monotonic() - t0 < 0.5


def test_panels_are_panels():
    cfg = make_config("P", None)
    assert isinstance(ui.render_live(cfg, _Logger(), time.monotonic(), deque(), 0), Panel)
    assert isinstance(ui.brief_panel(cfg), Panel)
