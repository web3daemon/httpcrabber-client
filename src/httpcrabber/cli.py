"""Точка входа: аргументы, интерактивный диалог, запуск сессии."""

import argparse
import asyncio
import sys
from pathlib import Path

import questionary
from questionary import Style as QStyle

from httpcrabber import __version__, procs, ui
from httpcrabber.commands import COMMANDS
from httpcrabber.commands import HELP as COMMANDS_HELP
from httpcrabber.config import CYAN, DIM, ERR, MAG, REPO_URL, console, settings
from httpcrabber.i18n import LANGUAGES, STRINGS, t
from httpcrabber.proxy import Proxy, parse_proxy
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
QMARK = "◆"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="httpcrabber",
        description="Network-level traffic interceptor for reverse-engineering web APIs.",
        epilog=f"{COMMANDS_HELP}\nDocs: {REPO_URL}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-l", "--lang", choices=LANGUAGES, help="interface language (skips the prompt)")
    p.add_argument("-s", "--session", metavar="NAME", help="session name (skips the prompt)")
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
        STRINGS["ru"]["ask_lang"],
        choices=[questionary.Choice("Русский", "ru"), questionary.Choice("English", "en")],
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


def configure(args: argparse.Namespace):
    """Собирает SessionConfig из аргументов, спрашивая только недостающее."""
    interactive = sys.stdin.isatty()

    lang = args.lang
    if not lang:
        if not interactive:
            console.print(f"[{ERR}]{t('not_tty')}[/]")
            return None
        lang = _ask_lang()
        if lang is None:
            return None
    settings.lang = lang

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

    cfg = make_config(name, proxy, launch_browser=not args.no_browser, port=args.port,
                      include=args.include, exclude=args.exclude,
                      fetch_sourcemaps=args.sourcemaps)
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

    ui.banner()
    # Диалог (questionary) держим ВНЕ asyncio-цикла: внутри он сам поднимает
    # свой event loop, а вложенные циклы asyncio запрещены.
    try:
        cfg = configure(args)
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
