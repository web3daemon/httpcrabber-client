"""Подкоманды для работы с записанными сессиями: redact, export, openapi."""

import argparse
import sys
from pathlib import Path

from httpcrabber import ui
from httpcrabber.config import CYAN, ERR, MAG, console

HELP = """commands (work on a recorded session — folder LOGS/<name> or its .jsonl):
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


COMMANDS = {"redact": redact_main, "export": export_main, "openapi": openapi_main}
