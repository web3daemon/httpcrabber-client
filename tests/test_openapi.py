import json

from httpcrabber import openapi
from httpcrabber.cli import main
from httpcrabber.dump import Exchange


def _ex(method, url, status=200, resp=None, req=None, req_ct="application/json",
        resp_ct="application/json", headers=None):
    return Exchange(
        id=url, started="", method=method, url=url,
        req_headers=[("Content-Type", req_ct), *(headers or [])] if req is not None
        else list(headers or []),
        req_body=json.dumps(req) if isinstance(req, (dict, list)) else req,
        status=status, reason="", resp_headers=[("Content-Type", resp_ct)],
        resp_body=json.dumps(resp) if isinstance(resp, (dict, list)) else resp,
    )


def test_template_names_params_after_resource():
    assert openapi.template("/v2/users/42/orders/7f3e9a1c-0b1d-4e5f-9a8b-1c2d3e4f5a6b") == (
        "/v2/users/{userId}/orders/{orderId}",
        [("userId", "42", "integer"),
         ("orderId", "7f3e9a1c-0b1d-4e5f-9a8b-1c2d3e4f5a6b", "uuid")])
    assert openapi.template("/categories/5")[0] == "/categories/{categoryId}"
    assert openapi.template("/api/9/9")[0] == "/api/{id}/{id2}"
    assert openapi.template("/")[0] == "/"
    assert openapi.template("/items/65f1c0ffee00112233445566")[0] == "/items/{itemId}"


def test_infer_and_merge_schemas():
    a = openapi.infer({"id": 1, "tags": ["x"], "owner": None, "at": "2026-09-24T12:00:00Z"})
    b = openapi.infer({"id": 2.5, "tags": [], "owner": {"name": "n"}, "extra": True,
                       "at": "2026-09-24T13:00:00Z"})
    m = openapi.merge(a, b)
    assert m["type"] == "object"
    assert m["properties"]["id"] == {"type": "number"}
    assert m["properties"]["owner"]["type"] == ["object", "null"]
    assert m["properties"]["at"] == {"type": "string", "format": "date-time"}
    assert sorted(m["required"]) == ["at", "id", "owner", "tags"]   # extra был не везде
    assert "anyOf" in openapi.merge({"type": "string"}, {"type": "object"})


def test_is_api_call_skips_static_pages_and_self_fetches():
    assert openapi.is_api_call(_ex("GET", "https://h/api/x", resp={"a": 1}))
    assert not openapi.is_api_call(_ex("GET", "https://h/app.js", resp_ct="application/javascript"))
    page = _ex("GET", "https://h/", resp="<html>", resp_ct="text/html",
               headers=[("Content-Type", "application/json")])       # CT на GET без тела
    assert not openapi.is_api_call(page)
    fetched = _ex("GET", "https://h/a.map", resp={"version": 3})
    fetched.fetched_by = "sourcemap"
    assert not openapi.is_api_call(fetched)


def test_build_spec_end_to_end():
    auth = [("Authorization", "Bearer SECRET"), ("X-Client-Version", "4.2")]
    exs = [
        _ex("GET", "https://api.t.com/v1/users/1?expand=true", resp={"id": 1, "email": "a@b.co"},
            headers=auth),
        _ex("GET", "https://api.t.com/v1/users/2", resp={"id": 2, "email": "c@d.co",
                                                       "token": "LEAK"}, headers=auth),
        _ex("GET", "https://api.t.com/v1/users/3", status=404, resp={"error": "nope"},
            headers=auth),
        _ex("POST", "https://api.t.com/v1/users", status=201, req={"name": "x", "password": "p"},
            resp={"id": 4}, headers=auth),
        _ex("POST", "https://api.t.com/graphql", req={"operationName": "Viewer", "query": "q"},
            resp={"data": {}}),
        _ex("GET", "https://cdn.t.com/app.js", resp="x()", resp_ct="application/javascript"),
    ]
    spec = openapi.build(exs, session_name="demo")
    assert spec["openapi"] == "3.1.0" and spec["servers"][0]["url"] == "https://api.t.com"
    get = spec["paths"]["/v1/users/{userId}"]["get"]
    assert get["operationId"] == "getV1UsersByUserId" and get["tags"] == ["users"]
    params = {p["name"]: p for p in get["parameters"]}
    assert params["userId"]["schema"] == {"type": "integer"} and params["userId"]["required"]
    assert params["expand"]["required"] is False and params["expand"]["schema"]["type"] == "boolean"
    assert params["X-Client-Version"]["in"] == "header"
    ok = get["responses"]["200"]["content"]["application/json"]
    assert ok["schema"]["properties"]["email"]["format"] == "email"
    assert "404" in get["responses"] and get["security"] == [{"bearerAuth": []}]
    post = spec["paths"]["/v1/users"]["post"]
    assert post["requestBody"]["content"]["application/json"]["example"]["password"] == "[REDACTED]"
    assert spec["paths"]["/graphql"]["post"]["x-graphql-operations"] == ["Viewer"]
    assert "/app.js" not in spec["paths"]
    dumped = json.dumps(spec)
    assert "SECRET" not in dumped and "LEAK" not in dumped
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


def test_cli_openapi_json_and_yaml(tmp_path):
    session = tmp_path / "s"
    session.mkdir()
    lines = [
        {"event": "request", "id": "1", "url": "https://a.io/items/5", "method": "GET",
         "headers": {}, "ts": "2026-09-24T12:00:00"},
        {"event": "response", "id": "1", "url": "https://a.io/items/5", "status": 200,
         "headers": {"Content-Type": "application/json"}, "body": '{"id": 5}'},
    ]
    (session / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert main(["openapi", str(session)]) == 0
    spec = json.loads((session / "openapi.json").read_text(encoding="utf-8"))
    assert "/items/{itemId}" in spec["paths"]
    assert main(["openapi", str(session), "-o", str(tmp_path / "api.yaml")]) == 0
    assert "openapi: 3.1.0" in (tmp_path / "api.yaml").read_text(encoding="utf-8")
    assert main(["openapi", str(session), "--host", "other.io"]) == 1
