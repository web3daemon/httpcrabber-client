<div align="center">

<img src="https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/logo.svg" alt="httpcrabber" width="880">

### Network-level traffic interceptor for reverse-engineering and debugging web APIs

Captures on the wire and saves everything to disk — no extensions, no injected code, the page runs untouched.

[![CI](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml/badge.svg)](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml)
[![Release v1.3.0](https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/badge-version.svg)](https://pypi.org/project/httpcrabber/)
[![Python 3.11+](https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/badge-python.svg)](https://www.python.org/)
[![Platform Windows · macOS · Linux](https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/badge-platform.svg)](#requirements)
[![License GPL-3.0](https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/badge-license.svg)](https://github.com/web3daemon/httpcrabber-client/blob/main/LICENSE)
[![Built with mitmproxy](https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

**English** · [Русский](https://github.com/web3daemon/httpcrabber-client/blob/main/README.ru.md) · [Español](https://github.com/web3daemon/httpcrabber-client/blob/main/README.es.md) · [中文](https://github.com/web3daemon/httpcrabber-client/blob/main/README.zh.md)

<br>

<img src="https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/demo.svg" alt="httpcrabber demo: startup, live intercept, session summary" width="100%">

[**Features**](#features) · [**Install**](#install) · [**Quick start**](#quick-start) · [**Command line**](#command-line) · [**Session output**](#session-output) · [**Working with a session**](#working-with-a-session) · [**How it works**](#how-it-works) · [**Security**](#-security)

</div>

## ⚡ 30-second start

```bash
pipx install httpcrabber          # or: pip install httpcrabber inside a venv
httpcrabber
```

Answer three prompts, browse as usual, close Chrome — every request, response, WebSocket frame and script of the session is in `LOGS/<name>/`.

## Why

DevTools is great for a quick look, but it is a poor recorder: the log lives only as long as
the tab, large bodies and WebSocket frames are awkward to export, scripts are scattered across
requests, and a HAR file is one huge snapshot of one tab.

**httpcrabber records a whole session to disk.** It is an HTTPS proxy based on
[mitmproxy](https://mitmproxy.org/): every request, response, WebSocket frame and script is
captured on the wire and written to a per-session folder as line-by-line JSONL — ready for
`grep`, `jq`, diffs and scripts. Nothing is installed into the browser or injected into the
page, so the site runs exactly as it does on a normal visit, and any browser or device that
can use a proxy works.

## Features

| | |
|---|---|
| 💚 **Animated hacker CLI** | Matrix rain, gradient glitch banner, typewriter, color-coded status badges, spinners for real waits |
| 📡 **Live intercept feed** | Requests in real time, colored methods and status codes, counters, traffic sparkline |
| 📊 **Session analytics** | Top hosts, method and status breakdown, duration and dump size when the session ends |
| 🧅 **Any upstream proxy** | `socks5` / `socks5h` / `socks4` / `http` / `https`, with or without auth, every common notation |
| 🗂 **One folder per session** | Network dump + every script together — archive or share a session as a unit |
| 📜 **Full JavaScript capture** | External bundles and inline `<script>` blocks, complete and deduplicated by SHA-256 |
| 🗺 **Source maps → original sources** | Maps are unpacked into the project's original file tree; `--sourcemaps` fetches the ones scripts reference |
| 🕶 **Safe sharing** | `httpcrabber redact` makes a copy with tokens, cookies and auth headers masked |
| 🧬 **OpenAPI from traffic** | `httpcrabber openapi` turns a session into an OpenAPI 3.1 spec — path templates, parameters, JSON schemas, auth |
| 📤 **HAR & curl export** | Open a session in DevTools, Charles, Insomnia or Burp, or replay any request as a curl command |
| 🌐 **Chrome starts itself** | Launched through the proxy with a dedicated profile — or bring your own browser with `--no-browser` |
| 🔐 **Automatic CA setup** | Certificate checked and installed on first run, on Windows, macOS and Linux |
| ⌨️ **Scriptable** | Every prompt has a flag; pass them all and nothing is asked |
| ⏹ **Safe shutdown** | Ends on Chrome close *or* `Ctrl+C` — the dump is saved and child processes are cleaned up either way |
| 🌍 **Bilingual UI** | Russian and English, chosen at startup or with `--lang` |

## Requirements

- **Python 3.11+**
- **Google Chrome** or **Chromium** (optional with `--no-browser`)

| OS | Browser discovery | CA certificate install |
|---|---|---|
| **Windows** | Program Files, LocalAppData | `certutil -user` into the user Root store — Windows shows one confirmation dialog |
| **macOS** | `/Applications`, `~/Applications` | `security add-trusted-cert` into the login keychain — macOS asks for your password once |
| **Linux** | `google-chrome`, `chromium` on `PATH` | NSS database `~/.pki/nssdb` via `certutil` from **libnss3-tools** (`sudo apt install libnss3-tools`) — this is what Chrome reads. Firefox keeps its own store; install from http://mitm.it there |

Set `HTTPCRABBER_BROWSER=/path/to/chrome` to override discovery on any OS.

## Install

```bash
pipx install httpcrabber
httpcrabber --version
```

Why `pipx`: mitmproxy pins exact versions of its dependencies (`cryptography`, `h2`, …),
so installing into your global Python can downgrade packages that other tools rely on.
`pipx` keeps httpcrabber in its own environment; `pip install httpcrabber` inside a venv
works just as well.

Or from a clone, for development:

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client
python -m venv .venv && source .venv/bin/activate     # .venv\Scripts\Activate.ps1 on Windows
pip install -e ".[dev]"
```

No install at all? `python run.py` works straight from the clone.

## Quick start

```bash
httpcrabber
```

The tool asks for three things and handles the rest:

1. **Language** — Russian or English
2. **Upstream proxy** — paste it in any format, or press <kbd>Enter</kbd> to go direct
3. **Session name** — e.g. `TARGET RECON`

<p align="center">
  <img src="https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/screen-start.svg" alt="httpcrabber startup: banner, session brief, status lines" width="100%">
</p>

It shows a session brief, installs the CA certificate if needed, starts Chrome through the
proxy, and streams everything into the session folder. Browse normally — every request,
response, WebSocket frame and script is captured. Close Chrome (or press <kbd>Ctrl+C</kbd>)
to finish; you get an analytics panel and the folder path.

<p align="center">
  <img src="https://raw.githubusercontent.com/web3daemon/httpcrabber-client/main/assets/screen-summary.svg" alt="httpcrabber session summary" width="100%">
</p>

## Command line

Every prompt has a flag. Pass them all and httpcrabber asks nothing — handy for scripts.

```bash
httpcrabber --lang en --session "target recon" --proxy socks5://user:pass@1.2.3.4:1080
httpcrabber -l en -s quick --direct --no-browser          # use your own browser / device
httpcrabber --no-anim                                      # plain output, no animations
httpcrabber -s api --include '*.target.com' --sourcemaps  # only the target + original sources
```

| Flag | Meaning |
|---|---|
| `-l, --lang {ru,en}` | Interface language |
| `-s, --session NAME` | Session name → `LOGS/<name>/` |
| `-p, --proxy PROXY` | Upstream proxy, any [format](#proxy-formats) |
| `--direct` | No upstream proxy |
| `--port PORT` | mitmproxy listen port (default `8080`, next free one if busy) |
| `-o, --output DIR` | Where sessions go (default `./LOGS`) |
| `--include HOST` | Record only matching hosts — glob, repeatable (`*.target.com`) |
| `--exclude HOST` | Never record matching hosts — glob, repeatable |
| `--sourcemaps` | Fetch source maps referenced by scripts and unpack the original sources |
| `--no-browser` | Don't launch Chrome — point any browser or device at `127.0.0.1:<port>` |
| `--no-anim` | Disable animations |
| `-V, --version` | Print version |

## Proxy formats

Every common notation is accepted. Press <kbd>Enter</kbd> with an empty input for a direct connection.

```
host:port
host:port:user:pass
user:pass@host:port
socks5://user:pass@host:port
http://host:port
https://user:pass@host:port
```

Schemes: `http`, `https`, `socks5`, `socks5h`, `socks4`. Passwords are masked in the interface.

## Session output

Each session is a self-contained folder:

```
LOGS/
└── target_recon/
    ├── target_recon.jsonl                     # network dump
    └── js/
        ├── index.json                         # manifest: url, file, sha256, size, hits
        ├── cdn.target.com/
        │   ├── main.a3f1c8d4.js               # external scripts
        │   ├── maps/main.js.9c1d2e3f.map      # source maps
        │   └── sources/app/src/…              # original sources unpacked from maps
        └── target.com/
            └── inline/inline_0001.e5f6a7b8.js # inline <script> blocks
```

If a session name already exists, `_2`, `_3` … is appended. **Nothing is ever overwritten.**

### Network dump

One JSON object per line, with an `event` field:
`request` · `response` · `ws_open` · `ws_msg` · `ws_close` · `error`.
Each record is flushed to disk immediately, so a crash or a hard kill loses nothing.

Every record carries an `id`: a request, its response, its error and the WebSocket frames of
one connection share it, even when the same URL is fetched in parallel. Responses add
`duration_ms` and `size`. Headers are written twice — `headers` (a dict, as before) and
`headers_raw` (a list of pairs that keeps repeated headers such as several `Set-Cookie`).
WebSocket frames have a `type`, `text` or `binary`; binary frames are stored like binary bodies.

### Captured JavaScript

- **Scripts are stored complete.** Bodies inside the `.jsonl` are truncated at 200 KB,
  but files in `js/` are the full source — a 5 MB minified bundle is saved whole.
- **Duplicates collapse by SHA-256.** One bundle requested a hundred times is stored once,
  with `hits: 100` in the manifest.
- **Inline scripts are extracted** from HTML. Tags with `src=` are skipped (they arrive as
  their own request), as are `application/ld+json` and `text/template` — those are not code.
- Filenames carry a short content hash, so different builds of the same `app.js` never
  overwrite each other.

### Source maps

Browsers download source maps only while DevTools is open, so normally they never cross
the wire. httpcrabber unpacks every map it does see — inline `data:` maps and any `.map`
response — into `js/<host>/sources/`. With `--sourcemaps` it also requests the maps that
scripts reference, through its own proxy and your upstream, so they land in the dump too,
marked `fetched_by: "sourcemap"`. Many production sites don't publish maps; when one does,
you get the original project tree instead of a minified bundle.

## Working with a session

Everything below works on a finished session — pass its folder or its `.jsonl`.

```bash
httpcrabber openapi LOGS/target_recon                  # → LOGS/target_recon/openapi.json
httpcrabber openapi LOGS/target_recon -o api.yaml --host 'api.*'
httpcrabber export har LOGS/target_recon               # → LOGS/target_recon/target_recon.har
httpcrabber export curl LOGS/target_recon -m /graphql -X POST
httpcrabber redact LOGS/target_recon                   # masked copy for sharing
```

| Command | What you get |
|---|---|
| `openapi` | An OpenAPI 3.1 spec of the API calls: path templates (`/users/42` → `/users/{userId}`), query and header parameters, JSON schemas merged across every sample, status codes, Bearer / Basic / API-key auth, GraphQL operation names. Example values are redacted. Open it in Swagger UI, Postman, Insomnia or feed it to a code generator. |
| `export har` | A HAR 1.2 archive for Chrome DevTools (Network → Import HAR), Charles, Fiddler, Insomnia or Burp — with cookies, query strings, form fields and WebSocket frames. |
| `export curl` | Ready-to-run curl commands, filtered by `--match`, `--method` or `--id`. Quoting follows your OS (`--shell posix` / `powershell`). |
| `redact` | A copy that is safe to share — see [Security](#-security). |

The spec describes only what was observed: an endpoint you never called is missing, and a field seen in only some responses is optional. It is a head start, not a contract.

## How it works

```mermaid
flowchart LR
    B["🌐 Chrome"] -->|HTTPS| M["🦀 mitmproxy<br/><sub>capture</sub>"]
    M --> P["🔌 pproxy bridge<br/><sub>scheme adapter</sub>"]
    P -->|"socks5 · http"| U["🧅 your upstream proxy"]
    U --> T["🎯 target"]
    M -.-> F[("📁 LOGS/session<br/><sub>JSONL + JS</sub>")]

    classDef hop fill:#0b0f0c,stroke:#39ff14,color:#d6ded6,stroke-width:1.5px
    classDef core fill:#0b0f0c,stroke:#ff2fd0,color:#ffffff,stroke-width:2px
    classDef store fill:#0b0f0c,stroke:#00e5ff,color:#d6ded6,stroke-width:1.5px
    class B,P,U,T hop
    class M core
    class F store
```

mitmproxy natively supports only `http`/`https` upstream proxies. To make **SOCKS5** work
transparently, httpcrabber starts a local [pproxy](https://github.com/qwj/python-proxy)
bridge that speaks HTTP to mitmproxy and any scheme to your proxy. Both hops are on
loopback, so the overhead is negligible.

```
src/httpcrabber/
  cli.py       arguments, prompts, main()
  session.py   orchestration: bridge → mitmproxy → CA → browser → live loop
  capture.py   mitmproxy addon: JSONL dump, JS collector, live stats
  proxy.py     upstream proxy parser        bridge.py   pproxy bridge
  ca.py        CA install per OS            browser.py  Chrome discovery per OS
  ui.py        animations, panels, feed     i18n.py     UI strings
  commands.py  redact / export / openapi    dump.py     reads a recorded session
  export.py    HAR and curl                 openapi.py  OpenAPI inference
  sourcemaps.py unpacking source maps       redact.py   masking secrets
```

## ⚠️ Security

**Captured traffic contains live credentials.** Session dumps routinely include
`Cookie`, `Set-Cookie`, `Authorization` headers, API keys and tokens for every site you
visited during the session.

- `LOGS/` and `*.jsonl` are excluded by [`.gitignore`](https://github.com/web3daemon/httpcrabber-client/blob/main/.gitignore) — **keep it that way**.
- **To share a session, make a masked copy:** `httpcrabber redact LOGS/target_recon` →
  `LOGS/target_recon_redacted/`. Auth headers, cookies and tokens in URLs, forms and JSON become
  `[REDACTED]`; scripts are copied as is, the original session stays untouched.
- Never commit, upload or share a session dump before reviewing it.
- Treat a session folder as if it were your password manager export. Because effectively, it is.
- The tool installs a locally generated root CA. [SECURITY.md](https://github.com/web3daemon/httpcrabber-client/blob/main/SECURITY.md) explains how to
  remove it when you are done.

## Responsible use

This is a tool for security research, API debugging, and interoperability work on systems
you own or are authorized to test. You are responsible for complying with applicable law,
the terms of service of the sites you access, and the privacy of any third-party data you
encounter. Do not use it to access systems without permission.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](https://github.com/web3daemon/httpcrabber-client/blob/main/CONTRIBUTING.md) for setup,
conventions and how to add a language. Security reports go through [SECURITY.md](https://github.com/web3daemon/httpcrabber-client/blob/main/SECURITY.md).

```bash
ruff check src tests run.py && pytest
```

## License

[GNU General Public License v3.0](https://github.com/web3daemon/httpcrabber-client/blob/main/LICENSE) — see the license file for the full text.
