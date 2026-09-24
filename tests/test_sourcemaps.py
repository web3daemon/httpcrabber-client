import base64
import json

from mitmproxy.http import Headers

from httpcrabber import sourcemaps
from httpcrabber.capture import JSCollector

MAP = json.dumps({
    "version": 3,
    "sources": ["webpack://app/./src/index.ts", "webpack://app/../../etc/passwd", "noc.ts"],
    "sourcesContent": ["export const a = 1;\n", "root:x:0:0", None],
    "mappings": "AAAA",
})


def test_map_url_from_comment_header_and_data():
    assert sourcemaps.map_url("https://c/js/app.js", "x()\n//# sourceMappingURL=app.js.map\n") \
        == "https://c/js/app.js.map"
    assert sourcemaps.map_url("https://c/a.js", "/*# sourceMappingURL=/m/a.map */") \
        == "https://c/m/a.map"
    headers = Headers(SourceMap="a.map")
    assert sourcemaps.map_url("https://c/js/a.js", "x()", headers) == "https://c/js/a.map"
    assert sourcemaps.map_url("https://c/a.js", "no map here") is None
    data = "data:application/json;base64," + base64.b64encode(MAP.encode()).decode()
    assert sourcemaps.decode_data_url(data) == MAP


def test_clean_source_path_blocks_traversal():
    assert sourcemaps.clean_source_path("webpack://app/./src/a.ts?1f").as_posix() == "app/src/a.ts"
    assert ".." not in sourcemaps.clean_source_path("../../etc/passwd").parts
    assert sourcemaps.clean_source_path("").as_posix() == "unknown.js"


def test_unpack_writes_sources_inside_dest(tmp_path):
    written = sourcemaps.unpack(MAP, tmp_path / "sources")
    assert "app/src/index.ts" in written and len(written) == 2
    assert (tmp_path / "sources/app/src/index.ts").read_text(encoding="utf-8") == \
        "export const a = 1;\n"
    assert all((tmp_path / "sources").resolve() in p.resolve().parents
               for p in (tmp_path / "sources").rglob("*") if p.is_file())


def test_collector_unpacks_inline_data_map_and_reports_external(tmp_path):
    refs = []
    c = JSCollector(tmp_path, on_map_ref=refs.append)
    data = "data:application/json;base64," + base64.b64encode(MAP.encode()).decode()
    c.store_external("https://cdn/a.js", f"a()\n//# sourceMappingURL={data}")
    c.store_external("https://cdn/b.js", "b()\n//# sourceMappingURL=b.js.map")
    c.store_external("https://cdn/b.js", "b()\n//# sourceMappingURL=b.js.map")  # дубль
    c.finalize()
    assert c.sources == 2 and refs == ["https://cdn/b.js.map"]
    assert (tmp_path / "cdn/sources/app/src/index.ts").exists()
    kinds = {e["kind"] for e in json.loads((tmp_path / "index.json").read_text("utf-8"))}
    assert kinds == {"external", "sourcemap"}


def test_same_map_unpacked_once(tmp_path):
    c = JSCollector(tmp_path)
    assert c.store_sourcemap("https://cdn/a.js.map", MAP) == 2
    assert c.store_sourcemap("https://cdn/a.js.map", MAP) == 0
    assert c.sources == 2
