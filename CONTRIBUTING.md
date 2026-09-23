# Contributing to httpcrabber

Thanks for taking the time. This document is short on purpose — read it once.

## Ground rules

- **Never commit captured traffic.** `LOGS/`, `*.jsonl` and the Chrome profile are
  git-ignored for a reason: dumps contain live cookies and tokens. If a PR adds a fixture
  with real traffic, it will be closed.
- **Be kind.** See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- **Security issues go through [SECURITY.md](SECURITY.md)**, not public issues.

## Setup

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\Activate.ps1 on Windows
pip install -e ".[dev]"
```

## Run checks

```bash
ruff check src tests run.py     # lint — must be clean
pytest                          # ~15 s, spins up real mitmproxy/pproxy on loopback
```

CI runs the same on Ubuntu, Windows and macOS for Python 3.11 and 3.12. A PR that fails
CI will not be reviewed until it is green.

## Layout

```
src/httpcrabber/
  cli.py       arguments, prompts, main()
  session.py   orchestration: bridge → mitmproxy → CA → browser → live loop
  capture.py   mitmproxy addon: JSONL dump, JS collector, live stats
  proxy.py     upstream proxy parser (every common notation)
  bridge.py    pproxy bridge (socks5/http/https → http for mitmproxy)
  ca.py        CA certificate install per OS
  browser.py   Chrome/Chromium discovery and launch per OS
  ui.py        all rendering: animations, panels, live feed, summary
  i18n.py      UI strings (ru, en)
  procs.py     child-process registry, ports
  config.py    constants, palette, runtime settings
```

## Conventions

- **i18n:** every UI string lives in `i18n.py`, in *every* language. A test enforces
  identical key sets and matching `{placeholders}` — add the key to both `ru` and `en`.
- **No fake progress.** Status lines (`OK` / `FAIL` badges, spinners) must reflect real work. Don't add
  decorative "system check" steps that verify nothing.
- **Crash-safety over cleverness.** The dump is line-buffered so every record is on disk
  immediately; cleanup runs even on a hard `Ctrl+C`. Keep it that way.
- **Cross-platform.** Anything touching the OS (paths, certificates, browsers) must handle
  Windows, macOS and Linux, or fail with a clear message.
- **Visuals follow the UI.** The terminal images in the READMEs are real renders of `ui.py`
  on demo data. After changing anything visual, regenerate and commit them:
  `python scripts/gen_screenshots.py` (static screens), `python scripts/gen_demo.py`
  (animated demo), `python scripts/gen_logo.py` (logo and social preview — the crab lives in
  `ui.PIXEL_CRAB`), `python scripts/gen_badges.py` (badges, including the release version).
- **Style:** `ruff` is the only arbiter. Line length 100. Comments explain *why*, not *what*.

## Pull requests

1. Branch from `main`, keep the PR focused on one thing.
2. Add or update tests. Bug fixes come with a regression test.
3. Update `CHANGELOG.md` under **Unreleased**.
4. Fill in the PR template.

## Adding a language

1. Add the dictionary to `STRINGS` in `src/httpcrabber/i18n.py` — copy `en`, translate values.
2. Add the choice in `cli._ask_lang()`.
3. Optionally add `README.<code>.md` and link it from the language switcher in every README.
4. `pytest tests/test_i18n.py` must pass.
