"""Общие фикстуры: без анимаций, изолированная папка сессий."""

import pytest

from httpcrabber.config import settings


@pytest.fixture(autouse=True)
def _quiet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HTTPCRABBER_PROFILES_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(settings, "anim", False)
    monkeypatch.setattr(settings, "lang", "en")
    monkeypatch.setattr(settings, "log_dir", tmp_path / "LOGS")
    yield
