import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mitmproxy.test import tflow

from httpcrabber import browser, cli, profiles
from httpcrabber.capture import NetworkLogger
from httpcrabber.config import settings
from httpcrabber.launcher import main as launch
from httpcrabber.regions import regions_main


def test_body_settings_precedence_and_locales(monkeypatch):
    parser = cli.build_parser()
    args = ["--session", "demo", "--direct", "--lang", "PL", "--no-browser"]
    monkeypatch.setenv("HTTPCRABBER_MAX_BODY", "20MB")
    monkeypatch.setenv("HTTPCRABBER_BINARY_BODIES", "1")
    env = cli.configure(parser.parse_args(args))
    assert (env.max_body, env.binary_bodies, env.locale, settings.lang) == (20_000_000, True, "pl-PL", "pl")
    monkeypatch.setenv("HTTPCRABBER_MAX_BODY", "invalid")
    override = cli.configure(parser.parse_args([*args, "--max-body", "default", "--no-binary-bodies"]))
    assert (override.max_body, override.binary_bodies) == (200_000, False)
    assert cli.main(args) == 2
    assert cli.body_size("2 MiB") == 2 * 1024**2


def test_utf8_and_binary_body_boundaries(tmp_path):
    logger = NetworkLogger(tmp_path / "log", max_body=3, binary_bodies=True)
    flow = tflow.tflow(resp=True)
    flow.request.headers["content-type"] = "application/octet-stream"
    flow.request.content = b"\xff\x00\xff"
    flow.response.headers["content-type"] = "text/plain; charset=utf-8"
    flow.response.text = "ππ"
    logger.request(flow)
    logger.response(flow)
    flow.response.headers["content-type"] = "image/png"
    flow.response.content = b"1234"
    logger.response(flow)
    logger.done()
    rows = [json.loads(line) for line in (tmp_path / "log").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["body"]["bytes"] == 3
    assert rows[1]["body"] == "π...[TRUNCATED]"
    assert rows[2]["body"].startswith("[binary, 4 bytes")


def test_profiles_survive_directory_changes(tmp_path, monkeypatch):
    old = tmp_path / "chrome_profile_proxy"
    old.mkdir()
    assert profiles.preferred() == old
    for name in ("first", "second"):
        assert profiles.profiles_main(["create", name]) == 0
    assert profiles.profiles_main(["use", "second"]) == 0
    monkeypatch.chdir(tmp_path.parent)
    assert profiles.preferred() == profiles.root() / "second"
    assert profiles.names() == ["first", "second"]
    with pytest.raises(ValueError):
        profiles.profile_name("../escape")


def test_browser_receives_profile_and_locale(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(browser, "find_browser", lambda: "chrome")
    monkeypatch.setattr(browser.subprocess, "Popen", lambda args, **kw: calls.append(args))
    browser.launch(8080, tmp_path, "pl-PL")
    assert f"--user-data-dir={tmp_path}" in calls[0]
    assert "--lang=pl-PL" in calls[0] and "--accept-lang=pl-PL,pl" in calls[0]


def test_region_search(capsys):
    assert regions_main(["Польша"]) == 0
    assert "pl-PL" in capsys.readouterr().out
    assert regions_main(["missing123"]) == 1


def test_theme_persists_across_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTPCRABBER_CONFIG_DIR", str(tmp_path / "config"))
    assert launch(["theme", "ink"]) == 0
    # Use the same package tree that pytest loaded (source checkout or installed wheel).
    env = dict(os.environ, PYTHONPATH=str(Path(cli.__file__).resolve().parents[1]))
    code = ("from httpcrabber import ui; from httpcrabber.config import MONO; "
            "print(MONO, ui.CRAB_COLORS['O'])")
    result = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
    assert result.strip() == "True #cccccc"
    assert launch(["theme", "neon"]) == 0
    assert "False" in subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
