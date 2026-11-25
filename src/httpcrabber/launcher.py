"""Resolve the saved theme before loading the terminal UI."""

import argparse
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

THEMES = ("neon", "ink")


def preference_path() -> Path:
    return Path(os.environ.get("HTTPCRABBER_CONFIG_DIR") or Path.home() / ".httpcrabber") / "theme"


def saved_theme() -> str | None:
    try:
        value = preference_path().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value if value in THEMES else None


def save_theme(value: str) -> None:
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(value.encode("ascii"))
    try:
        Path(temp.name).replace(path)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def choose_theme() -> str | None:
    import questionary

    return questionary.select(
        "Тема / Theme / Motyw",
        choices=[questionary.Choice("Neon   ▰  Neon · Неон", "neon"),
                 questionary.Choice("Ink    ▧  Monochrome · Монохром", "ink")],
        default=saved_theme() or "neon",
        style=questionary.Style([("highlighted", "reverse bold"), ("question", "bold")]),
    ).ask()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    theme_command = argv[:1] == ["theme"]
    parser = argparse.ArgumentParser(prog="httpcrabber theme" if theme_command else "httpcrabber",
                                     add_help=theme_command, allow_abbrev=False)
    if theme_command:
        parser.add_argument("theme", choices=THEMES, nargs="?")
        choice = parser.parse_args(argv[1:]).theme
    else:
        parser.add_argument("--theme", choices=THEMES)
        options, argv = parser.parse_known_args(argv)
        choice = options.theme
    if choice is None and interactive_terminal() and (theme_command or (not argv and not saved_theme())):
        choice = choose_theme()
        if choice is None:
            return 1
    if choice:
        try:
            save_theme(choice)
        except OSError as exc:
            parser.error(str(exc))
    if theme_command:
        print(saved_theme() or "neon")
        return 0
    from httpcrabber.cli import main as run

    return run(argv)
