import asyncio
import contextlib
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from httpcrabber import browser, ca, procs, session
from httpcrabber.config import settings
from httpcrabber.proxy import parse_proxy
from httpcrabber.session import make_config, run_session, sanitize_session, unique_session_dir


def test_sanitize():
    assert sanitize_session("GOOGLE LOG") == "google_log"
    assert sanitize_session("  Target / Recon!! ") == "target_recon"
    assert sanitize_session("Тест Сессия") == "тест_сессия"
    assert sanitize_session("!!!") == "session"


def test_unique_session_dir_never_overwrites(tmp_path):
    dirs = [unique_session_dir(tmp_path, "x") for _ in range(3)]
    assert [d.name for d in dirs] == ["x", "x_2", "x_3"]
    assert all(d.is_dir() for d in dirs)


def test_make_config_layout():
    cfg = make_config("My Session", parse_proxy("socks5://u:p@h:1"), launch_browser=False)
    assert cfg.name == "My Session"
    assert cfg.session_dir == settings.log_dir / "my_session"
    assert cfg.log_path == cfg.session_dir / "my_session.jsonl"
    assert cfg.js_dir == cfg.session_dir / "js"
    assert cfg.proxy_port != cfg.bridge_port
    assert cfg.launch_browser is False


# ── интеграция: реальный mitmproxy на loopback, браузер и CA заглушены ────

_HTML = b'<html><script>var T="tok";</script><script src="/app.js"></script></html>'
_JS = b"function solve(){return 42;}"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D102
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/app.js"):
            body, ct, code = _JS, "application/javascript", 200
        elif self.path.startswith("/403"):
            body, ct, code = b"no", "text/plain", 403
        else:
            body, ct, code = _HTML, "text/html", 200
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeBrowser:
    """«Chrome», который сам закрывается через ttl секунд."""

    def __init__(self, ttl):
        self.t0, self.ttl = time.monotonic(), ttl

    def poll(self):
        return None if time.monotonic() - self.t0 < self.ttl else 0

    def terminate(self):
        pass


@pytest.fixture
def origin():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.integration
def test_run_session_end_to_end(origin, monkeypatch):
    monkeypatch.setattr(ca, "is_installed", lambda: True)
    monkeypatch.setattr(ca, "cert_path", lambda: None)
    fake = _FakeBrowser(ttl=4.5)
    monkeypatch.setattr(browser, "launch", lambda port: fake)

    cfg = make_config("E2E", None)

    def traffic():
        time.sleep(1.0)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{cfg.proxy_port}"}))
        for path in ("/", "/app.js", "/app.js", "/403"):
            with contextlib.suppress(Exception):
                opener.open(f"{origin}{path}", timeout=10).read()

    threading.Thread(target=traffic, daemon=True).start()
    logger = asyncio.run(run_session(cfg))

    assert logger is not None
    assert logger.stats["request"] == 4 and logger.stats["response"] == 4
    assert logger.stats["js"] == 2                       # внешний + инлайн, дедуп сработал
    assert logger.status_classes == {"2xx": 3, "4xx": 1}
    assert cfg.log_path.exists()
    manifest = json.loads((cfg.js_dir / "index.json").read_text(encoding="utf-8"))
    assert {e["kind"] for e in manifest} == {"external", "inline"}
    assert not procs.port_open("127.0.0.1", cfg.proxy_port)   # mitmproxy остановлен


@pytest.mark.integration
def test_run_session_through_bridge(origin, monkeypatch):
    """Полная цепочка mitmproxy → мост pproxy → «внешний» прокси (тоже pproxy)."""
    import subprocess
    import sys

    monkeypatch.setattr(ca, "is_installed", lambda: True)
    monkeypatch.setattr(ca, "cert_path", lambda: None)
    monkeypatch.setattr(browser, "launch", lambda port: _FakeBrowser(ttl=4.5))

    up_port = procs.free_port(9500)
    upstream = subprocess.Popen(
        [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{up_port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.register(upstream)
    assert asyncio.run(procs.wait_port("127.0.0.1", up_port, 10))

    cfg = make_config("CHAIN", parse_proxy(f"http://127.0.0.1:{up_port}"))

    def traffic():
        time.sleep(1.5)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{cfg.proxy_port}"}))
        with contextlib.suppress(Exception):
            opener.open(f"{origin}/app.js", timeout=10).read()

    threading.Thread(target=traffic, daemon=True).start()
    try:
        logger = asyncio.run(run_session(cfg))
    finally:
        upstream.terminate()
    assert logger is not None and logger.stats["response"] == 1
    assert logger.status_classes["2xx"] == 1


def test_run_session_bridge_failure_returns_none(monkeypatch):
    monkeypatch.setattr(session, "start_bridge", lambda uri, port: _FakeBrowser(ttl=60))

    async def never(*a, **k):
        return False

    monkeypatch.setattr(procs, "wait_port", never)
    cfg = make_config("BAD", parse_proxy("socks5://127.0.0.1:1"))
    assert asyncio.run(run_session(cfg)) is None
