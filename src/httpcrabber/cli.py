"""Точка входа: аргументы, интерактивный диалог, запуск сессии."""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import questionary
from questionary import Style as QStyle

from httpcrabber import __version__, procs, profiles, ui
from httpcrabber.commands import COMMANDS
from httpcrabber.commands import HELP as COMMANDS_HELP
from httpcrabber.config import CYAN, DIM, ERR, MAG, MAX_BODY_SIZE, MONO, REPO_URL, console, settings
from httpcrabber.i18n import LANGUAGES, t
from httpcrabber.launcher import interactive_terminal
from httpcrabber.proxy import Proxy, parse_proxy
from httpcrabber.regions import REGIONS, locale_tag
from httpcrabber.session import make_config, run_session

Q_STYLE = QStyle([
    ("qmark", "fg:#39ff14 bold"),
    ("question", "fg:#00e5ff bold"),
    ("answer", "fg:#ff2fd0 bold"),
    ("pointer", "fg:#39ff14 bold"),
    ("highlighted", "fg:#39ff14 bold"),
    ("selected", "fg:#00e5ff"),
    ("instruction", "fg:#5f6f5f italic"),
    ("text", "fg:#d6ded6"),
])
if MONO:
    Q_STYLE = QStyle([("qmark", "fg:#ffffff bold"), ("question", "fg:#eeeeee bold"),
                      ("answer", "fg:#cccccc"), ("pointer", "fg:#ffffff"),
                      ("highlighted", "fg:#101010 bg:#eeeeee"), ("instruction", "fg:#aaaaaa"),
                      ("text", "fg:#dddddd")])
QMARK = "◆"


def body_size(value: str) -> int:
    if value.strip().lower() == "default":
        return MAX_BODY_SIZE
    match = re.fullmatch(r"([0-9]{1,18})\s*(b|kb|mb|gb|kib|mib|gib)?", value.strip(), re.I)
    if not match:
        raise argparse.ArgumentTypeError("Use bytes, e.g. 20000000, 20MB, 2MiB, or default.")
    units = {"b": 1, "kb": 1000, "mb": 10**6, "gb": 10**9,
             "kib": 1024, "mib": 1024**2, "gib": 1024**3}
    return int(match[1]) * units[(match[2] or "b").lower()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="httpcrabber",
        description="Network-level traffic interceptor for reverse-engineering web APIs.",
        epilog=f"{COMMANDS_HELP}\nDocs: {REPO_URL}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-l", "--lang", metavar="TAG", help="Chrome locale and session UI language (ru, pl, en, en-GB, …)")
    p.add_argument("-s", "--session", metavar="NAME", help="session name (skips the prompt)")
    p.add_argument("--max-body", type=body_size, metavar="SIZE",
                   help="maximum body in JSONL, e.g. 20MB (default 200000 bytes)")
    p.add_argument("--binary-bodies", action=argparse.BooleanOptionalAction, default=None,
                   help="save binary bodies within the limit as base64")
    p.add_argument("--theme", choices=("ink", "neon"), help="save the terminal theme")
    p.add_argument("--setup", action="store_true", help="open the interactive launch settings")
    profile = p.add_mutually_exclusive_group()
    profile.add_argument("--profile", type=profiles.profile_name, help="create or reuse a named Chrome profile")
    profile.add_argument("--profile-dir", type=Path, help="use an existing Chrome user-data directory")
    g = p.add_mutually_exclusive_group()
    g.add_argument("-p", "--proxy", metavar="PROXY", help="upstream proxy in any common format")
    g.add_argument("--direct", action="store_true", help="no upstream proxy (skips the prompt)")
    p.add_argument("--port", type=int, metavar="PORT", help="mitmproxy listen port (default 8080)")
    p.add_argument("-o", "--output", metavar="DIR", help="sessions folder (default ./LOGS)")
    p.add_argument("--no-browser", action="store_true",
                   help="do not launch Chrome — point your own browser at the proxy")
    p.add_argument("--include", action="append", default=[], metavar="HOST",
                   help="record only matching hosts, glob, repeatable (*.example.com)")
    p.add_argument("--exclude", action="append", default=[], metavar="HOST",
                   help="never record matching hosts, glob, repeatable")
    p.add_argument("--sourcemaps", action="store_true",
                   help="fetch source maps referenced by scripts and unpack original sources")
    p.add_argument("--no-anim", action="store_true", help="disable animations")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _ask_lang() -> str | None:
    return questionary.select(
        "Язык и регион / Language & region / Język i region",
        choices=[questionary.Choice(f"{tag}  {label}  ·  {aliases}", tag)
                 for tag, (label, aliases) in REGIONS.items()],
        use_search_filter=True, use_jk_keys=False,
        qmark=QMARK, pointer="❯", style=Q_STYLE,
    ).ask()


def _ask_proxy() -> Proxy | None | bool:
    """Proxy | None (прямое) | False (отмена)."""
    while True:
        raw = questionary.text(t("ask_proxy"), instruction=t("proxy_hint"), qmark=QMARK,
                                 style=Q_STYLE).ask()
        if raw is None:
            return False
        if not raw.strip():
            ui.step(t("proxy_none"), "info")
            return None
        try:
            proxy = parse_proxy(raw)
        except ValueError:
            console.print(f"[{ERR}]{t('proxy_bad')}[/]")
            continue
        ui.step(f"{t('proxy_ok')} [{CYAN}]{proxy.display}[/]  "
                f"[{DIM}]→ {proxy.pproxy_uri.split('#')[0]}[/]")
        return proxy


def _ask_session() -> str | None:
    while True:
        name = questionary.text(t("ask_session"), qmark=QMARK, style=Q_STYLE).ask()
        if name is None:
            return None
        if name.strip():
            return name.strip()
        console.print(f"[{ERR}]{t('session_bad')}[/]")


def _choose_profile() -> Path | None:
    preferred = profiles.preferred()
    choices = [questionary.Choice(str(preferred), preferred)]
    for name in profiles.names():
        path = profiles.root() / name
        if path != preferred:
            choices.append(questionary.Choice(name, path))
    choices.append(questionary.Choice(t("new_profile"), "+"))
    picked = questionary.select(t("ask_profile"), choices=choices, style=Q_STYLE).ask()
    if picked != "+":
        return picked
    while True:
        name = questionary.text(t("name_profile"), style=Q_STYLE).ask()
        if name is None:
            return None
        try:
            return profiles.root() / profiles.profile_name(name)
        except ValueError as exc:
            console.print(str(exc), style=ERR)


def configure(args: argparse.Namespace):
    """Собирает SessionConfig из аргументов, спрашивая только недостающее."""
    interactive = interactive_terminal()

    wizard = interactive and (args.setup or not args.session or not args.lang
                              or (not args.direct and args.proxy is None))
    lang = args.lang
    if not lang:
        if not interactive:
            console.print(f"[{ERR}]{t('not_tty')}[/]")
            return None
        lang = _ask_lang()
        if lang is None:
            return None
    locale = locale_tag(lang)
    language = locale.split("-")[0]
    settings.lang = language if language in LANGUAGES else "en"
    ui.banner()

    if args.proxy is not None:
        proxy = parse_proxy(args.proxy)
        ui.step(f"{t('proxy_ok')} [{CYAN}]{proxy.display}[/]")
    elif args.direct:
        proxy = None
        ui.step(t("proxy_none"), "info")
    else:
        if not interactive:
            console.print(f"[{ERR}]{t('not_tty')}[/]")
            return None
        proxy = _ask_proxy()
        if proxy is False:
            return None

    name = args.session
    if not name:
        if not interactive:
            console.print(f"[{ERR}]{t('not_tty')}[/]")
            return None
        name = _ask_session()
        if name is None:
            return None

    limit = args.max_body
    if limit is None:
        raw = os.environ.get("HTTPCRABBER_MAX_BODY", str(MAX_BODY_SIZE))
        if wizard:
            while True:
                raw = questionary.text(t("ask_limit"), default=raw, style=Q_STYLE).ask()
                if raw is None:
                    return None
                try:
                    limit = body_size(raw)
                    break
                except argparse.ArgumentTypeError as exc:
                    console.print(str(exc), style=ERR)
        else:
            limit = body_size(raw)
    binary = args.binary_bodies
    if binary is None:
        binary = os.environ.get("HTTPCRABBER_BINARY_BODIES", "").lower() in ("1", "true", "yes")
    profile_dir = args.profile_dir
    if profile_dir is not None:
        profile_dir = profile_dir.expanduser().absolute()
        if not profile_dir.is_dir():
            raise ValueError(f"Chrome profile directory does not exist: {profile_dir}")
    elif args.profile:
        profile_dir = profiles.root() / args.profile
    elif wizard and not args.no_browser:
        profile_dir = _choose_profile()
        if profile_dir is None:
            return None
    cfg = make_config(name, proxy, launch_browser=not args.no_browser, port=args.port,
                      include=args.include, exclude=args.exclude,
                      fetch_sourcemaps=args.sourcemaps, max_body=limit, binary_bodies=binary,
                      profile_dir=profile_dir, locale=locale)
    console.print()
    console.print(ui.brief_panel(cfg))
    console.print()
    return cfg


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] and argv[0] in COMMANDS:
        return COMMANDS[argv[0]](argv[1:])
    args = build_parser().parse_args(argv)
    settings.anim = not args.no_anim
    if args.output:
        settings.log_dir = Path(args.output)
    if args.proxy is not None:
        try:
            parse_proxy(args.proxy)
        except ValueError as exc:
            console.print(f"[{ERR}]{exc}[/]")
            return 2

    # Диалог (questionary) держим ВНЕ asyncio-цикла: внутри он сам поднимает
    # свой event loop, а вложенные циклы asyncio запрещены.
    try:
        cfg = configure(args)
    except (argparse.ArgumentTypeError, ValueError, OSError) as exc:
        console.print(str(exc), style=ERR, markup=False)
        return 2
    except KeyboardInterrupt:
        console.print(f"\n[{DIM}]{t('cancelled')}[/]")
        return 130
    if cfg is None:
        return 1

    logger = None
    try:
        logger = asyncio.run(run_session(cfg))
    except KeyboardInterrupt:
        pass
    finally:
        procs.cleanup()  # страховка: на жёстком Ctrl+C гасим браузер и мост

    if logger is None:
        return 1
    console.print(ui.summary_panel(cfg, logger, getattr(logger, "duration", 0.0)))
    console.print(t("next_steps", browse=f"[{CYAN}]httpcrabber browse {cfg.session_dir}[/]",
                    openapi=f"[{CYAN}]httpcrabber openapi {cfg.session_dir}[/]"),
                  justify="center", style=DIM)
    console.print(f"[{DIM}]{REPO_URL}[/]", justify="center", style=MAG)
    ui.farewell()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
