import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from httpcrabber import browse
from httpcrabber.cli import main
from httpcrabber.dump import Exchange
from httpcrabber.replay import replay
from httpcrabber.sessions import discover, latest


class _Echo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.dumps({"method": self.command, "path": self.path,
                           "auth": self.headers.get("Authorization"),
                           "body": self.rfile.read(n).decode()}).encode()
        code = 404 if self.path.startswith("/missing") else 200
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = _reply


@pytest.fixture
def origin():
    srv = HTTPServer(("127.0.0.1", 0), _Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _session(root, name, origin, started="2026-09-24T12:00:00.000"):
    d = root / name
    d.mkdir(parents=True)
    ev = []
    for i, (method, path, status, body) in enumerate([
        ("GET", "/users/1", 200, None), ("POST", "/users", 201, '{"name": "x"}'),
        ("GET", "/missing", 404, None), ("PUT", "/users/1", 200, '{"name": "y"}'),
    ]):
        fid = f"id{i}"
        ev.append({"ts": started, "event": "request", "id": fid, "url": origin + path,
                   "method": method, "headers": {"Authorization": "Bearer t"},
                   "headers_raw": [["Authorization", "Bearer t"],
                                   ["Content-Type", "application/json"]], "body": body})
        ev.append({"ts": started, "event": "response", "id": fid, "url": origin + path,
                   "status": status, "headers_raw": [["Content-Type", "application/json"]],
                   "body": '{"ok": true}', "size": 12, "duration_ms": 3.0})
    ev.append({"ts": started, "event": "ws_msg", "id": "id0", "url": origin + "/users/1",
               "from_client": False, "type": "text", "content": "ping"})
    (d / f"{name}.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n", encoding="utf-8")
    return d


def test_filter_syntax():
    ex = Exchange(id="1", started="", method="POST", url="https://api.t.com/v2/graphql", status=403)
    assert browse.matches(ex, "graphql method:post status:4xx host:api")
    assert browse.matches(ex, "status:403")
    assert not browse.matches(ex, "status:2xx")
    assert not browse.matches(ex, "method:GET")
    assert not browse.matches(ex, "host:cdn")
    assert not browse.matches(ex, "rest")


def test_replay_as_is_and_edited(origin):
    ex = Exchange(id="1", started="", method="POST", url=origin + "/users",
                  req_headers=[("Authorization", "Bearer t"), ("Content-Length", "999"),
                               ("Content-Type", "application/json")],
                  req_body='{"name": "x"}')
    r = replay(ex)
    assert r.status == 200 and r.error is None
    echoed = json.loads(r.body)
    assert echoed == {"method": "POST", "path": "/users", "auth": "Bearer t",
                      "body": '{"name": "x"}'}
    ex.url = origin + "/missing"
    assert replay(ex).status == 404                     # 4xx — тоже ответ, не ошибка
    ex.req_body = "{" + "...[TRUNCATED]"
    assert "truncated" in replay(ex).error
    down = Exchange(id="2", started="", method="GET", url="http://127.0.0.1:9/")
    assert replay(down, timeout=2).error


def test_sessions_discover_latest_and_ls(tmp_path, origin, capsys):
    root = tmp_path / "LOGS"
    _session(root, "old", origin, "2026-09-20T10:00:00.000")
    newest = _session(root, "new", origin, "2026-09-24T10:00:00.000")
    (root / "new_redacted").mkdir()
    (root / "new_redacted" / "new.jsonl").write_text("", encoding="utf-8")
    found = discover(root)
    assert [s.path.name for s in found] == ["new", "old"]
    assert found[0].requests == 4 and found[0].ws == 1 and "redacted" in found[0].extras
    assert latest(root) == newest
    assert main(["ls", str(root)]) == 0
    out = capsys.readouterr().out
    assert "new" in out and "old" in out and "redacted" in out
    assert main(["ls", str(tmp_path / "empty")]) == 1


def test_tui_filter_details_replay_and_edit(tmp_path, origin):
    session = _session(tmp_path, "s", origin)
    app = browse.BrowseApp(session, shell="posix")

    async def run():
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            table = app.query_one(browse.DataTable)
            assert table.row_count == 4 and "4 requests" in app.sub_title
            assert "ping" in str(browse.render_ws(app.current).columns[2]._cells)

            await pilot.press("slash", *"method:put")
            await pilot.pause()
            assert table.row_count == 1 and app.current.method == "PUT"
            await pilot.press("enter", "r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            result = app.replays[app.current.id]
            assert result.status == 200 and json.loads(result.body)["body"] == '{"name": "y"}'
            assert app.query_one(browse.TabbedContent).active == "t-replay"

            await pilot.press("e")
            await pilot.pause()
            assert isinstance(app.screen, browse.EditScreen)
            app.screen.query_one("#url", browse.Input).value = origin + "/edited"
            await pilot.press("ctrl+s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert json.loads(app.replays[app.current.id].body)["path"] == "/edited"

            await pilot.press("escape")          # фильтр очищается, видны все запросы
            await pilot.pause()
            assert table.row_count == 4
            await pilot.press("c")
            await pilot.press("q")

    asyncio.run(run())


def test_cli_browse_without_sessions(tmp_path, monkeypatch):
    from httpcrabber.config import settings

    monkeypatch.setattr(settings, "log_dir", tmp_path / "nothing")
    assert main(["browse"]) == 2
    assert main(["browse", str(tmp_path / "missing")]) == 2
