import json

from httpcrabber.cli import main
from httpcrabber.redact import MASK, Redactor, is_secret_name, redact_session


def test_secret_names():
    for name in ("access_token", "csrfToken", "client_secret", "password", "x-api-key", "sid",
                 "code"):
        assert is_secret_name(name), name
    for name in ("status", "status_code", "country_code", "publicKey", "user", "id"):
        assert not is_secret_name(name), name


def test_headers_keep_shape_but_hide_values():
    r = Redactor()
    assert r.header("Authorization", "Bearer abc.def") == f"Bearer {MASK}"
    assert r.header("Cookie", "sid=1; theme=dark") == f"sid={MASK}; theme={MASK}"
    assert r.header("Set-Cookie", "sid=1; Path=/; HttpOnly") == f"sid={MASK}; Path=/; HttpOnly"
    assert r.header("X-Api-Key", "k") == MASK
    assert r.header("Content-Type", "application/json") == "application/json"


def test_url_form_and_json_bodies():
    r = Redactor()
    assert r.url("https://a/cb?code=XYZ&state=1&page=2") == f"https://a/cb?code={MASK}&state=1&page=2"
    assert r.text("user=bob&password=hunter2") == f"user=bob&password={MASK}"
    body = json.loads(r.text('{"user":{"name":"bob","accessToken":"t"},"code":404,"items":[]}'))
    assert body == {"user": {"name": "bob", "accessToken": MASK}, "code": 404, "items": []}
    # обрезанный JSON не парсится — пары маскируются регэкспом
    cut = r.text('{"token": "abc", "name": "x", "da...[TRUNCATED]')
    assert f'"token": "{MASK}"' in cut and '"name": "x"' in cut


def test_redact_session_copies_folder_and_leaves_original(tmp_path):
    src = tmp_path / "LOGS" / "s"
    (src / "js").mkdir(parents=True)
    (src / "js" / "a.js").write_text("var token='public code';", encoding="utf-8")
    original = [
        {"event": "request", "url": "https://a/?token=1", "headers": {"Cookie": "sid=9"},
         "headers_raw": [["Cookie", "sid=9"]], "body": '{"password":"p"}'},
        {"event": "ws_msg", "url": "wss://a/", "content": '{"jwt":"x"}'},
    ]
    (src / "s.jsonl").write_text("\n".join(json.dumps(e) for e in original) + "\n{broken",
                                 encoding="utf-8")

    dst, lines, masked = redact_session(src)
    assert dst.name == "s_redacted" and lines == 2 and masked == 5
    out = [json.loads(line) for line in (dst / "s.jsonl").read_text("utf-8").splitlines()]
    assert out[0]["url"] == f"https://a/?token={MASK}"
    assert out[0]["headers_raw"] == [["Cookie", f"sid={MASK}"]]
    assert "sid=9" not in json.dumps(out) and "\"p\"" not in json.dumps(out)
    assert (dst / "js" / "a.js").read_text(encoding="utf-8") == "var token='public code';"
    assert "sid=9" in (src / "s.jsonl").read_text("utf-8")      # оригинал не тронут
    assert redact_session(src)[0].name == "s_redacted_2"        # вторая копия не перезаписывает


def test_cli_redact_command(tmp_path, capsys):
    dump = tmp_path / "x.jsonl"
    dump.write_text(json.dumps({"event": "request", "url": "https://a/?api_key=1"}) + "\n",
                    encoding="utf-8")
    assert main(["redact", str(dump)]) == 0
    assert MASK in (tmp_path / "x.redacted.jsonl").read_text(encoding="utf-8")
    assert "1 values masked" in capsys.readouterr().out.replace("\n", " ")
    assert main(["redact", str(tmp_path / "missing")]) == 2


def test_echoed_request_inside_response_is_masked():
    """Эхо-сервисы (httpbin и т.п.) возвращают заголовки и тело запроса внутри JSON."""
    r = Redactor()
    echoed = json.dumps({
        "headers": {"Authorization": "Bearer abc", "Cookie": "sid=9; x=1", "Host": "h"},
        "data": json.dumps({"access_token": "t0k", "user": "bob"}),
        "note": "Basic dXNlcjpwYXNz",
    })
    out = r.text(echoed)
    for leaked in ("abc", "t0k", "sid=9", "dXNlcjpwYXNz"):
        assert leaked not in out, leaked
    body = json.loads(out)
    assert body["headers"]["Authorization"] == f"Bearer {MASK}"
    assert body["headers"]["Host"] == "h" and json.loads(body["data"])["user"] == "bob"


def test_secret_object_masks_all_leaves():
    r = Redactor()
    out = json.loads(r.text('{"cookies": {"sid": "s1", "prefs": {"t": "dark"}}, "page": "2"}'))
    assert out == {"cookies": {"sid": MASK, "prefs": {"t": MASK}}, "page": "2"}
