"""Подкоманды для работы с записанными сессиями: redact, export, openapi."""

import argparse
import sys
from pathlib import Path

from httpcrabber import ui
from httpcrabber.config import CYAN, ERR, MAG, console

HELP = """commands (work on a recorded session — folder LOGS/<name> or its .jsonl):
  httpcrabber ls [DIR]               saved sessions, newest first (default ./LOGS)
  httpcrabber browse [SESSION]       explore a session in the terminal, replay requests
  httpcrabber export har SESSION     HAR 1.2 for DevTools, Charles, Insomnia, Burp
  httpcrabber export curl SESSION    requests as ready-to-run curl commands
  httpcrabber openapi SESSION        OpenAPI 3.1 spec inferred from the recorded API calls
  httpcrabber redact SESSION         copy of a session with secrets masked, for sharing
"""


def _session_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("session", type=Path, help="session folder (LOGS/<name>) or a .jsonl dump")


def _exists(path: Path) -> bool:
    if path.exists():
        return True
    console.print(f"[{ERR}]{path}: not found[/]")
    return False


def redact_main(argv: list[str]) -> int:
    from httpcrabber.redact import redact_session

    p = argparse.ArgumentParser(
        prog="httpcrabber redact",
        description="Write a copy of a session (folder or .jsonl) with tokens, cookies, "
                    "auth headers and secret-looking fields masked. The original is untouched.",
    )
    _session_arg(p)
    p.add_argument("-o", "--output", type=Path, help="where to write the copy")
    args = p.parse_args(argv)
    if not _exists(args.session):
        return 2
    dst, lines, masked = redact_session(args.session, args.output)
    ui.step(f"{lines} records, [{MAG}]{masked}[/] values masked → [{CYAN}]{dst}[/]")
    return 0


def export_main(argv: list[str]) -> int:
    from httpcrabber import export
    from httpcrabber.dump import load

    p = argparse.ArgumentParser(prog="httpcrabber export",
                                description="Export a recorded session to other tools.")
    sub = p.add_subparsers(dest="format", required=True)
    har = sub.add_parser("har", help="HAR 1.2 archive (DevTools, Charles, Insomnia, Burp)")
    _session_arg(har)
    har.add_argument("-o", "--output", type=Path, help="default: <session>/<name>.har")
    curl = sub.add_parser("curl", help="requests as curl commands")
    _session_arg(curl)
    curl.add_argument("-m", "--match", help="only URLs containing this text")
    curl.add_argument("-X", "--method", help="only this HTTP method")
    curl.add_argument("--id", action="append", help="only this request id (prefix is enough)")
    curl.add_argument("--shell", choices=("posix", "powershell"),
                      default="powershell" if sys.platform == "win32" else "posix",
                      help="quoting style (default: this OS)")
    curl.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")
    args = p.parse_args(argv)
    if not _exists(args.session):
        return 2

    if args.format == "har":
        out, n = export.export_har(args.session, args.output)
        ui.step(f"{n} requests → [{CYAN}]{out}[/]")
        return 0

    chosen = export.select(load(args.session), args.match, args.method, args.id)
    text = "\n\n".join(export.to_curl(ex, args.shell) for ex in chosen) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        ui.step(f"{len(chosen)} requests → [{CYAN}]{args.output}[/]")
    else:
        # Сырой вывод, без rich: команды должны копироваться и перенаправляться как есть
        sys.stdout.write(text)
    return 0 if chosen else 1


def openapi_main(argv: list[str]) -> int:
    from httpcrabber.openapi import export_openapi

    p = argparse.ArgumentParser(
        prog="httpcrabber openapi",
        description="Infer an OpenAPI 3.1 spec from the API calls recorded in a session: "
                    "path templates, parameters, JSON schemas, auth schemes.",
    )
    _session_arg(p)
    p.add_argument("-o", "--output", type=Path,
                   help="default: <session>/openapi.json; .yaml / .yml writes YAML")
    p.add_argument("--host", action="append", metavar="HOST",
                   help="only these hosts, glob, repeatable (*.target.com)")
    args = p.parse_args(argv)
    if not _exists(args.session):
        return 2
    out, spec = export_openapi(args.session, args.output, args.host)
    ops = sum(len([k for k in item if k != "servers"]) for item in spec["paths"].values())
    if not ops:
        console.print(f"[{ERR}]no API calls (JSON / form requests) found in {args.session}[/]")
        return 1
    ui.step(f"{len(spec['paths'])} paths, {ops} operations → [{CYAN}]{out}[/]")
    return 0


def ls_main(argv: list[str]) -> int:
    from rich.table import Table

    from httpcrabber.config import DIM, NEON, WHITE, settings
    from httpcrabber.sessions import discover

    p = argparse.ArgumentParser(prog="httpcrabber ls", description="List saved sessions.")
    p.add_argument("dir", nargs="?", type=Path, help="sessions folder (default ./LOGS)")
    args = p.parse_args(argv)
    root = args.dir or settings.log_dir
    found = discover(root)
    if not found:
        console.print(f"[{DIM}]no sessions in {root}[/]")
        return 1
    # Мелкие счётчики и пометки — в одной колонке с переносом: таблица влезает и в 80 колонок
    table = Table(box=None, header_style=f"bold {CYAN}", pad_edge=False, padding=(0, 2))
    table.add_column("Session", no_wrap=True, overflow="ellipsis", max_width=28)
    table.add_column("Started", no_wrap=True)
    table.add_column("Time", justify="right", no_wrap=True)
    table.add_column("Reqs", justify="right", no_wrap=True)
    table.add_column("Dump", justify="right", no_wrap=True)
    table.add_column("Notes", ratio=1, overflow="fold")
    for s in found:
        notes = [f"{s.scripts} js" if s.scripts else "",
                 f"{s.ws} ws" if s.ws else "",
                 f"[{ERR}]{s.errors} err[/]" if s.errors else "",
                 *([f"[{NEON}]sources[/]"] if s.sources else []),
                 *(f"[{NEON}]{x}[/]" for x in s.extras)]
        table.add_row(
            f"[{MAG}]{s.path.name}[/]",
            s.started.strftime("%Y-%m-%d %H:%M") if s.started else "—",
            ui.fmt_clock(s.duration), f"[{WHITE}]{s.requests}[/]", ui.fmt_size(s.size),
            f"[{DIM}] · [/]".join(n for n in notes if n),
        )
    console.print(table)
    console.print(f"[{DIM}]→ httpcrabber browse {found[0].path}[/]", soft_wrap=True)
    return 0


def browse_main(argv: list[str]) -> int:
    from httpcrabber.config import settings
    from httpcrabber.sessions import latest

    p = argparse.ArgumentParser(
        prog="httpcrabber browse",
        description="Explore a recorded session in the terminal: filter requests, read bodies, "
                    "copy curl, replay a request as is or after editing it.",
    )
    p.add_argument("session", nargs="?", type=Path,
                   help="session folder or .jsonl (default: the newest in ./LOGS)")
    p.add_argument("--proxy", metavar="URL", help="send replays through this HTTP proxy")
    p.add_argument("--shell", choices=("posix", "powershell"),
                   default="powershell" if sys.platform == "win32" else "posix",
                   help="quoting for curl commands (default: this OS)")
    args = p.parse_args(argv)
    session = args.session or latest(settings.log_dir)
    if session is None:
        console.print(f"[{ERR}]no sessions in {settings.log_dir} — pass a session path[/]")
        return 2
    if not _exists(session):
        return 2
    from httpcrabber.browse import BrowseApp

    BrowseApp(session, proxy=args.proxy, shell=args.shell).run()
    return 0


COMMANDS = {"redact": redact_main, "export": export_main, "openapi": openapi_main,
            "ls": ls_main, "browse": browse_main, "show": browse_main}
