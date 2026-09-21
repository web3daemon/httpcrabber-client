import json

from mitmproxy.test import tflow

from httpcrabber.capture import JSCollector, NetworkLogger
from httpcrabber.config import MAX_BODY_SIZE

# ── JSCollector ────────────────────────────────────────────────────────────

def test_is_js_by_content_type_and_path():
    assert JSCollector.is_js("https://a/x", "application/javascript; charset=utf-8")
    assert JSCollector.is_js("https://a/app.min.js?v=3", "text/plain")
    assert JSCollector.is_js("https://a/m.mjs", "")
    assert not JSCollector.is_js("https://a/", "text/html")


def test_dedup_by_hash_and_manifest(tmp_path):
    c = JSCollector(tmp_path)
    for _ in range(3):
        c.store_external("https://cdn/bundle.js?v=1", "console.log(1);")
    c.store_external("https://cdn/other.js", "var x=2;")
    c.finalize()

    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.js"))
    assert len(files) == 2 and c.saved == 2
    manifest = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    hits = {e["url"]: e["hits"] for e in manifest}
    assert hits["https://cdn/bundle.js?v=1"] == 3
    assert all(e["sha256"] and e["size"] > 0 for e in manifest)


def test_harvest_inline_scripts_skips_non_code(tmp_path):
    c = JSCollector(tmp_path)
    html = """<html>
    <script>var inline1=1;</script>
    <script type="module">export const a=1;</script>
    <script src="/ext.js"></script>
    <script type="application/ld+json">{"a":1}</script>
    <script type="text/template"><div></div></script>
    <script type="text/javascript">var inline2=2;</script>
    </html>"""
    c.harvest_html("https://site/page", html)
    assert c.saved == 3
    kinds = {e["kind"] for e in c.index.values()}
    assert kinds == {"inline"}


def test_empty_script_ignored(tmp_path):
    c = JSCollector(tmp_path)
    c.store_external("https://a/e.js", "   \n")
    assert c.saved == 0


# ── NetworkLogger с синтетическими flow ───────────────────────────────────

def _flow(url="http://example.com/app.js", ct="application/javascript", body=b"function f(){}",
          method="GET", status=200):
    f = tflow.tflow(resp=True)
    f.request.url = url
    f.request.method = method
    f.response.status_code = status
    f.response.headers["content-type"] = ct
    f.response.content = body
    return f


def test_logger_writes_jsonl_and_collects_js(tmp_path):
    log = tmp_path / "s.jsonl"
    lg = NetworkLogger(log, tmp_path / "js")
    f = _flow()
    lg.request(f)
    lg.response(f)
    lg.done()

    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in lines] == ["request", "response"]
    assert lines[1]["status"] == 200 and lines[1]["body"] == "function f(){}"
    assert lg.stats == {"request": 1, "response": 1, "ws": 0, "error": 0, "js": 1}
    assert lg.hosts["example.com"] == 1
    assert lg.methods["GET"] == 1
    assert lg.status_classes["2xx"] == 1
    assert list((tmp_path / "js").rglob("*.js"))


def test_big_script_saved_complete_but_log_truncated(tmp_path):
    big = ("// big\n" + "var x=1;" * (MAX_BODY_SIZE // 4)).encode()
    lg = NetworkLogger(tmp_path / "s.jsonl", tmp_path / "js")
    f = _flow(url="http://h/huge.js", body=big)
    lg.response(f)
    lg.done()

    saved = next((tmp_path / "js").rglob("*.js"))
    assert len(saved.read_bytes()) == len(big)
    logged = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8"))["body"]
    assert logged.endswith("...[TRUNCATED]") and len(logged) < len(big)


def test_inline_from_html_response(tmp_path):
    lg = NetworkLogger(tmp_path / "s.jsonl", tmp_path / "js")
    html = b'<html><script>var T="x";</script><script src="/a.js"></script></html>'
    lg.response(_flow(url="http://h/", ct="text/html; charset=utf-8", body=html))
    lg.done()
    files = list((tmp_path / "js").rglob("*.js"))
    assert len(files) == 1 and "inline" in files[0].as_posix()


def test_binary_response_not_decoded(tmp_path):
    lg = NetworkLogger(tmp_path / "s.jsonl")
    lg.response(_flow(url="http://h/i.png", ct="image/png", body=b"\x89PNG\x00\x01"))
    lg.done()
    entry = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8"))
    assert entry["body"].startswith("[binary, 6 bytes")


def test_binary_body_base64_when_enabled(tmp_path, monkeypatch):
    import base64 as b64

    from httpcrabber import capture

    monkeypatch.setattr(capture, "CAPTURE_BINARY", True)
    raw = b"\x89PNG\x00\x01\x02\x03"
    lg = NetworkLogger(tmp_path / "s.jsonl")
    lg.response(_flow(url="http://h/i.png", ct="image/png", body=raw))
    lg.done()
    body = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8"))["body"]
    assert body["encoding"] == "base64" and body["bytes"] == len(raw)
    assert b64.b64decode(body["data"]) == raw


def test_feed_and_error(tmp_path):
    lg = NetworkLogger(tmp_path / "s.jsonl")
    f = _flow(status=503)
    lg.response(f)
    lg.error(tflow.tflow(err=True))
    lg.done()
    tail = lg.feed_tail(5)
    assert tail[0][1] == "GET" and tail[0][2] == 503
    assert tail[1][1] == "ERR"
    assert lg.stats["error"] == 1
