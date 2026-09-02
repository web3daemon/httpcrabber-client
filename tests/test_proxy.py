import pytest

from httpcrabber.proxy import Proxy, parse_proxy


@pytest.mark.parametrize(
    ("raw", "scheme", "host", "port", "user", "password"),
    [
        ("host.com:8080", "http", "host.com", 8080, None, None),
        ("1.2.3.4:1080:user:pass", "http", "1.2.3.4", 1080, "user", "pass"),
        ("user:pass@1.2.3.4:8080", "http", "1.2.3.4", 8080, "user", "pass"),
        ("socks5://user:pass@1.2.3.4:1080", "socks5", "1.2.3.4", 1080, "user", "pass"),
        ("socks5://1.2.3.4:1080", "socks5", "1.2.3.4", 1080, None, None),
        ("socks5h://u:p@h:1", "socks5h", "h", 1, "u", "p"),
        ("https://u:p@proxy.io:3128", "https", "proxy.io", 3128, "u", "p"),
        ("http://h:1:u:p", "http", "h", 1, "u", "p"),
        ("  host:80  ", "http", "host", 80, None, None),
    ],
)
def test_parse_formats(raw, scheme, host, port, user, password):
    p = parse_proxy(raw)
    assert p == Proxy(scheme, host, port, user, password)


def test_empty_is_direct():
    assert parse_proxy("") is None
    assert parse_proxy("   ") is None
    assert parse_proxy(None) is None


@pytest.mark.parametrize("raw", ["garbage", "a:b:c:d:e", "host:notaport", "host:0", "host:70000",
                                 "ftp://host:21", ":8080"])
def test_invalid_raises(raw):
    with pytest.raises(ValueError):
        parse_proxy(raw)


def test_pproxy_uri_uses_hash_auth_and_maps_https_to_http():
    assert parse_proxy("https://u:p@h:1").pproxy_uri == "http://h:1#u:p"
    assert parse_proxy("socks5h://h:1").pproxy_uri == "socks5://h:1"
    assert parse_proxy("h:1").pproxy_uri == "http://h:1"


def test_display_masks_password():
    d = parse_proxy("socks5://user:secret@h:1").display
    assert "secret" not in d
    assert d == "socks5://user:******@h:1"
    assert parse_proxy("h:1").display == "http://h:1"
