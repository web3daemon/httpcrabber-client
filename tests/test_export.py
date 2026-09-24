import json
import shlex

import pytest

from httpcrabber import dump, export
from httpcrabber.cli import main


def _write(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n{broken", encoding="utf-8")
    return path


def _req(i, url, method="GET", body=None, headers=None, **extra):
    h = headers or {"Accept": "*/*"}
    return {"ts": "2026-09-24T12:00:00.000", "event": "request", "id": i, "url": url,
            "method": method, "http_version": "HTTP/2.0", "headers": h,
            "headers_raw": [[k, v] for k, v in h.items()], "body": body, **extra}


def _resp(i, url, status=200, body=None, ct="application/json", headers_raw=None):
    raw = headers_raw or [["Content-Type", ct]]
    return {"ts": "2026-09-24T12:00:00.100", "event": "response", "id": i, "url": url,
            "status": status, "reason": "OK", "http_version": "HTTP/2.0",
            "headers": dict(raw), "headers_raw": raw, "body": body, "size": 10,
            "duration_ms": 12.5}


@pytest.fixture
def session(tmp_path):
    d = tmp_path / "LOGS" / "demo"
    d.mkdir(parents=True)
    _write(d / "demo.jsonl", [
        _req("a", "https://api.t.com/users/1?x=1", headers={
            "Authorization": "Bearer tok", "Cookie": "sid=9; t=dark", "Accept-Encoding": "gzip",
            "Content-Length": "0", ":authority": "api.t.com"}),
        _req("b", "https://api.t.com/users/1"),                    # параллельный тот же URL
        _resp("b", "https://api.t.com/users/1", body='{"id": 1}'),
        _resp("a", "https://api.t.com/users/1?x=1", body='{"id": 1, "name": "it\'s"}',
              headers_raw=[["Content-Type", "application/json"], ["Set-Cookie", "a=1; Path=/"],
                           ["Set-Cookie", "b=2; HttpOnly"]]),
        _req("c", "https://api.t.com/login", "POST", body="user=bob&pass=o'k",
             headers={"Content-Type": "application/x-www-form-urlencoded"}),
        _resp("c", "https://api.t.com/login", 302, body="", ct="text/plain"),
        _req("d", "wss://rt.t.com/socket"),
        {"ts": "2026-09-24T12:00:01.000", "event": "ws_msg", "id": "d", "url": "wss://rt.t.com/socket",
         "from_client": True, "type": "text", "content": "hello"},
        {"ts": "2026-09-24T12:00:02.000", "event": "error", "id": "e", "url": "https://x/"},
    ])
    return d


def test_load_pairs_by_id_and_keeps_order(session):
    exs = dump.load(session)
    assert [e.id for e in exs] == ["a", "b", "c", "d"]
    a, b = exs[0], exs[1]
    assert a.url.endswith("?x=1") and a.resp_body.endswith('"it\'s"}') and b.resp_body == '{"id": 1}'
    assert a.headers_all("set-cookie", "resp") == ["a=1; Path=/", "b=2; HttpOnly"]
    assert exs[3].ws[0]["content"] == "hello"


def test_load_legacy_dump_without_ids(tmp_path):
    events = [
        {"event": "request", "url": "https://h/a", "method": "GET", "headers": {"A": "1"}},
        {"event": "request", "url": "https://h/a", "method": "GET", "headers": {"A": "2"}},
        {"event": "response", "url": "https://h/a", "status": 200, "headers": {}, "body": "one"},
        {"event": "response", "url": "https://h/a", "status": 404, "headers": {}, "body": "two"},
    ]
    exs = dump.load(_write(tmp_path / "old.jsonl", events))
    assert [(e.header("a"), e.status) for e in exs] == [("1", 200), ("2", 404)]


def test_har_structure(session):
    har = export.to_har(dump.load(session))["log"]
    assert har["version"] == "1.2" and har["creator"]["name"] == "httpcrabber"
    a = har["entries"][0]
    for key in ("startedDateTime", "time", "request", "response", "cache", "timings"):
        assert key in a
    assert a["startedDateTime"][-6] in "+-" or a["startedDateTime"].endswith("Z")   # с зоной
    assert {"name": "x", "value": "1"} in a["request"]["queryString"]
    assert {"name": "sid", "value": "9"} in a["request"]["cookies"]
    assert [c["name"] for c in a["response"]["cookies"]] == ["a", "b"]
    assert a["response"]["cookies"][1]["httpOnly"] is True
    assert all(not h["name"].startswith(":") for h in a["request"]["headers"])
    assert a["response"]["content"]["text"].startswith('{"id": 1')
    login = har["entries"][2]
    assert login["request"]["postData"]["params"] == [{"name": "user", "value": "bob"},
                                                      {"name": "pass", "value": "o'k"}]
    ws = har["entries"][3]
    assert ws["_resourceType"] == "websocket" and ws["_webSocketMessages"][0]["type"] == "send"


def test_har_truncated_and_binary_bodies():
    ex = dump.Exchange(id="x", started="", method="GET", url="https://h/",
                       resp_body="abc" + dump.TRUNCATED)
    content = export.har_entry(ex)["response"]["content"]
    assert content["text"] == "abc" and "truncated" in content["comment"]
    ex.resp_body = {"encoding": "base64", "data": "AAEC", "bytes": 3}
    assert export.har_entry(ex)["response"]["content"]["encoding"] == "base64"
    ex.resp_body = "[binary, 7 bytes, image/png]"
    assert "text" not in export.har_entry(ex)["response"]["content"]


def test_curl_posix_round_trips_through_shlex(session):
    exs = dump.load(session)
    cmd = export.to_curl(exs[0], "posix")
    argv = shlex.split(cmd.split("\n", 1)[1].replace("\\\n", " "))
    assert argv[:2] == ["curl", "https://api.t.com/users/1?x=1"]
    assert "Authorization: Bearer tok" in argv and "--compressed" in argv
    assert not any(a.startswith(("Content-Length", ":authority", "Accept-Encoding")) for a in argv)

    post = export.to_curl(exs[2], "posix")
    argv = shlex.split(post.split("\n", 1)[1].replace("\\\n", " "))
    assert argv[argv.index("-X") + 1] == "POST"
    assert argv[argv.index("--data-raw") + 1] == "user=bob&pass=o'k"


def test_curl_powershell_quotes_single_quotes():
    ex = dump.Exchange(id="x", started="", method="POST", url="https://h/", req_body="it's")
    out = export.to_curl(ex, "powershell")
    assert out.splitlines()[1] == "curl.exe `" and "--data-raw 'it''s'" in out


def test_curl_notes_truncated_body():
    ex = dump.Exchange(id="x", started="", method="POST", url="https://h/",
                       req_body="{" + dump.TRUNCATED)
    assert "truncated" in export.to_curl(ex)


def test_select_filters(session):
    exs = dump.load(session)
    assert [e.id for e in export.select(exs, match="LOGIN")] == ["c"]
    assert [e.id for e in export.select(exs, method="post")] == ["c"]
    assert [e.id for e in export.select(exs, ids=["b"])] == ["b"]


def test_cli_export_commands(session, capsys):
    assert main(["export", "har", str(session)]) == 0
    har = json.loads((session / "demo.har").read_text(encoding="utf-8"))
    assert len(har["log"]["entries"]) == 4
    capsys.readouterr()
    assert main(["export", "curl", str(session), "-m", "login", "--shell", "posix"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# 302 POST https://api.t.com/login") and "--data-raw" in out
    assert main(["export", "curl", str(session), "-m", "nothing-matches"]) == 1
    assert main(["export", "har", str(session / "missing")]) == 2
