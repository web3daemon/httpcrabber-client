"""Общие фикстуры: без анимаций, изолированная папка сессий."""

import pytest

from httpcrabber.config import settings


@pytest.fixture(autouse=True)
def _quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "anim", False)
    monkeypatch.setattr(settings, "lang", "en")
    monkeypatch.setattr(settings, "log_dir", tmp_path / "LOGS")
    yield
