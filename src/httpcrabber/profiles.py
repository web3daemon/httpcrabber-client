"""Persistent, named Chrome user-data directories."""

import argparse
import os
import re
import tempfile
from pathlib import Path, PureWindowsPath

from httpcrabber.config import PROFILE_DIR, console


def root() -> Path:
    return Path(os.environ.get("HTTPCRABBER_PROFILES_DIR") or Path.home() / ".httpcrabber" / "profiles").expanduser().absolute()


def profile_name(value: str) -> str:
    if not re.fullmatch(r"[\w-]{1,64}", value) or PureWindowsPath(value).is_reserved():
        raise ValueError("Profile name must contain 1–64 letters, digits, underscores or hyphens.")
    return value.casefold()


def names() -> list[str]:
    folder = root()
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def preferred() -> Path:
    active = root() / ".active"
    if active.is_file():
        selected = root() / profile_name(active.read_text(encoding="utf-8").strip())
        if selected.is_dir():
            return selected
    if PROFILE_DIR.is_dir():
        return PROFILE_DIR.absolute()
    return root() / "default"


def profiles_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="httpcrabber profiles", description="Manage Chrome profiles.")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("list", help="list named profiles and show the default path")
    for action, help_text in [("create", "create a profile"), ("use", "select the default profile")]:
        sub.add_parser(action, help=help_text).add_argument("name", type=profile_name)
    args = parser.parse_args(argv)
    try:
        if args.action in (None, "list"):
            chosen = preferred()
            for name in names():
                console.print(("* " if root() / name == chosen else "  ") + name, markup=False, soft_wrap=True)
            console.print(f"→ {chosen}", markup=False, soft_wrap=True)
            return 0
        path = root() / args.name
        if args.action == "create":
            path.mkdir(parents=True, exist_ok=True)
        else:
            if not path.is_dir():
                parser.error(f"Unknown profile '{args.name}'. Run httpcrabber profiles create {args.name}")
            with tempfile.NamedTemporaryFile(dir=root(), prefix=".active-", delete=False) as f:
                f.write(args.name.encode("utf-8"))
            try:
                Path(f.name).replace(root() / ".active")
            finally:
                Path(f.name).unlink(missing_ok=True)
        console.print(str(path), markup=False, soft_wrap=True)
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
