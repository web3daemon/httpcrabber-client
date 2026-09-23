<div align="center">

<img src="assets/logo.svg" alt="httpcrabber" width="880">

### Network-level traffic interceptor for reverse-engineering web APIs

Invisible to in-page JavaScript protections — because it never touches the page.

[![CI](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml/badge.svg)](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml)
[![Release v1.1.0](assets/badge-version.svg)](https://github.com/web3daemon/httpcrabber-client/releases/latest)
[![Python 3.11+](assets/badge-python.svg)](https://www.python.org/)
[![Platform Windows · macOS · Linux](assets/badge-platform.svg)](#requirements)
[![License GPL-3.0](assets/badge-license.svg)](LICENSE)
[![Built with mitmproxy](assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

**English** · [Русский](README.ru.md) · [Español](README.es.md) · [中文](README.zh.md)

<br>

<img src="assets/demo.svg" alt="httpcrabber demo: startup, live intercept, session summary" width="100%">

[**Features**](#features) · [**Install**](#install) · [**Quick start**](#quick-start) · [**Command line**](#command-line) · [**Session output**](#session-output) · [**How it works**](#how-it-works) · [**Security**](#-security)

</div>

## ⚡ 30-second start

```bash
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber
```

Answer three prompts, browse as usual, close Chrome — every request, response, WebSocket frame and script of the session is in `LOGS/<name>/`.

## Why

Browser DevTools can be detected. Anti-bot JavaScript (Kasada, Cloudflare, Vercel BotID)
routinely checks whether a debugger is attached, whether `devtools` is open, or whether
the network stack has been tampered with from inside the page.

**httpcrabber sits below all of that.** It is an HTTPS proxy based on
[mitmproxy](https://mitmproxy.org/): traffic is captured on the wire, not in the page.
From the JavaScript's point of view, nothing is there.

## Features

| | |
|---|---|
| 💚 **Animated hacker CLI** | Matrix rain, gradient glitch banner, typewriter, color-coded status badges, spinners for real waits |
| 📡 **Live intercept feed** | Requests in real time, colored methods and status codes, counters, traffic sparkline |
| 📊 **Session analytics** | Top hosts, method and status breakdown, duration and dump size when the session ends |
| 🧅 **Any upstream proxy** | `socks5` / `socks5h` / `socks4` / `http` / `https`, with or without auth, every common notation |
| 🗂 **One folder per session** | Network dump + every script together — archive or share a session as a unit |
| 📜 **Full JavaScript capture** | External bundles and inline `<script>` blocks, complete and deduplicated by SHA-256 |
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
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber --version
```

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
  <img src="assets/screen-start.svg" alt="httpcrabber startup: banner, session brief, status lines" width="100%">
</p>

It shows a session brief, installs the CA certificate if needed, starts Chrome through the
proxy, and streams everything into the session folder. Browse normally — every request,
response, WebSocket frame and script is captured. Close Chrome (or press <kbd>Ctrl+C</kbd>)
to finish; you get an analytics panel and the folder path.

<p align="center">
  <img src="assets/screen-summary.svg" alt="httpcrabber session summary" width="100%">
</p>

## Command line

Every prompt has a flag. Pass them all and httpcrabber asks nothing — handy for scripts.

```bash
httpcrabber --lang en --session "target recon" --proxy socks5://user:pass@1.2.3.4:1080
httpcrabber -l en -s quick --direct --no-browser          # use your own browser / device
httpcrabber --no-anim                                      # plain output, no animations
```

| Flag | Meaning |
|---|---|
| `-l, --lang {ru,en}` | Interface language |
| `-s, --session NAME` | Session name → `LOGS/<name>/` |
| `-p, --proxy PROXY` | Upstream proxy, any [format](#proxy-formats) |
| `--direct` | No upstream proxy |
| `--port PORT` | mitmproxy listen port (default `8080`, next free one if busy) |
| `-o, --output DIR` | Where sessions go (default `./LOGS`) |
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
        │   └── main.a3f1c8d4.js               # external scripts
        └── target.com/
            └── inline/inline_0001.e5f6a7b8.js # inline <script> blocks
```

If a session name already exists, `_2`, `_3` … is appended. **Nothing is ever overwritten.**

### Network dump

One JSON object per line, with an `event` field:
`request` · `response` · `ws_open` · `ws_msg` · `ws_close` · `error`.
Each record is flushed to disk immediately, so a crash or a hard kill loses nothing.

### Captured JavaScript

- **Scripts are stored complete.** Bodies inside the `.jsonl` are truncated at 200 KB,
  but files in `js/` are the full source — a 5 MB minified bundle is saved whole.
- **Duplicates collapse by SHA-256.** One bundle requested a hundred times is stored once,
  with `hits: 100` in the manifest.
- **Inline scripts are extracted** from HTML. Tags with `src=` are skipped (they arrive as
  their own request), as are `application/ld+json` and `text/template` — those are not code.
- Filenames carry a short content hash, so different builds of the same `app.js` never
  overwrite each other.

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
```

## ⚠️ Security

**Captured traffic contains live credentials.** Session dumps routinely include
`Cookie`, `Set-Cookie`, `Authorization` headers, API keys and tokens for every site you
visited during the session.

- `LOGS/` and `*.jsonl` are excluded by [`.gitignore`](.gitignore) — **keep it that way**.
- Never commit, upload or share a session dump before reviewing it.
- Treat a session folder as if it were your password manager export. Because effectively, it is.
- The tool installs a locally generated root CA. [SECURITY.md](SECURITY.md) explains how to
  remove it when you are done.

## Responsible use

This is a tool for security research, API debugging, and interoperability work on systems
you own or are authorized to test. You are responsible for complying with applicable law,
the terms of service of the sites you access, and the privacy of any third-party data you
encounter. Do not use it to access systems without permission.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
conventions and how to add a language. Security reports go through [SECURITY.md](SECURITY.md).

```bash
ruff check src tests run.py && pytest
```

## License

[GNU General Public License v3.0](LICENSE) — see the license file for the full text.
