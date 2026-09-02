#!/usr/bin/env python3
"""Запуск из клона без установки: `python run.py`.

Предпочтительный способ — `pip install -e .` и команда `httpcrabber`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from httpcrabber.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
