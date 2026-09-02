import pytest

from httpcrabber import __version__, cli
from httpcrabber.config import settings


def test_parser_defaults_and_flags(tmp_path):
    p = cli.build_parser()
    a = p.parse_args([])
    assert a.lang is None and a.proxy is None and not a.direct and not a.no_browser
    a = p.parse_args(["-l", "en", "-s", "X", "--direct", "--no-browser", "--no-anim",
                      "--port", "9090", "-o", str(tmp_path)])
    assert (a.lang, a.session, a.direct, a.no_browser, a.no_anim, a.port) == \
        ("en", "X", True, True, True, 9090)


def test_proxy_and_direct_are_exclusive():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--proxy", "h:1", "--direct"])


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_bad_proxy_exits_2(capsys):
    assert cli.main(["--no-anim", "--proxy", "garbage"]) == 2


def test_non_tty_without_args_fails_cleanly(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.main(["--no-anim"]) == 1
    assert "interactive terminal" in capsys.readouterr().out


def test_configure_from_args_skips_prompts(monkeypatch):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    args = cli.build_parser().parse_args(
        ["-l", "en", "-s", "From Args", "--proxy", "socks5://u:p@h:1", "--no-browser"])
    cfg = cli.configure(args)
    assert cfg is not None
    assert cfg.name == "From Args" and cfg.proxy.scheme == "socks5"
    assert cfg.launch_browser is False
    assert settings.lang == "en"
