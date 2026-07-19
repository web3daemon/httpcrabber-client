<div align="center">

# 🦀 httpcrabber

**Network-level traffic interceptor for reverse-engineering web APIs.**
Invisible to in-page JavaScript protections — because it never touches the page.

**English** · [Русский](README.ru.md) · [Español](README.es.md) · [中文](README.zh.md)

[![Python](https://img.shields.io/badge/Python-3.11%2B-39ff14?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL--3.0-ff2fd0?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-00e5ff?style=flat-square&logo=windows&logoColor=white)](#requirements)
[![Built with](https://img.shields.io/badge/Built%20with-mitmproxy-ffcc00?style=flat-square)](https://mitmproxy.org/)

</div>

---

```
┌────────────────────────────── ● SESSION LIVE ───────────────────────────────┐
│                                                                             │
│    Session  TARGET RECON                                                    │
│   Upstream  socks5://user:****@1.2.3.4:1080                                 │
│  mitmproxy  127.0.0.1:8080                                                  │
│        Log  LOGS/target_recon                                               │
│                                                                             │
│   ⠸  LIVE INTERCEPT                                                         │
│   14:22:07  GET    200  https://cdn.target.com/static/js/main.a3f1c8.c…     │
│   14:22:07  POST   403  https://api.target.com/v2/auth/challenge            │
│   14:22:08  GET    304  https://target.com/assets/app.css                   │
│   14:22:08  POST   200  https://api.target.com/v2/graphql                   │
│   14:22:09  WS     →    wss://realtime.target.com/socket                    │
│   14:22:09  WS     ←    wss://realtime.target.com/socket                    │
│   14:22:10  GET    500  https://api.target.com/v2/telemetry/collect         │
│   14:22:11  ERR    ···  https://blocked.tracker.io/beacon                   │
│   14:22:12  DELETE 204  https://api.target.com/v2/session                   │
│                                                                             │
│   REQ 1478 RESP 1443 WS 12 JS 38 ERR 2        ▂▆█▄▂▁ ▁▄  03:41              │
│                                                                             │
│        Close Chrome or press Ctrl+C to finish and save the session.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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
| 💚 **Animated hacker CLI** | Matrix rain, glitch banner, typewriter, `[ OK ]` status lines, spinners |
| 📡 **Live intercept feed** | Requests in real time, colored methods and status codes, traffic sparkline |
| 🧅 **Any upstream proxy** | `socks5` / `http` / `https`, with or without auth, in every common notation |
| 🗂 **One folder per session** | Network dump + all scripts together — archive or share a session as a unit |
| 📜 **Full JavaScript capture** | External bundles and inline `<script>` blocks, complete and deduplicated |
| 🌐 **Chrome starts itself** | Launched through the proxy with a dedicated profile |
| 🔐 **Automatic CA setup** | Certificate is checked and installed on first run |
| ⏹ **Safe shutdown** | Ends on Chrome close *or* `Ctrl+C` — the dump is saved either way |
| 🌍 **Bilingual UI** | Russian and English, chosen at startup |

## Requirements

- **Python 3.11+**
- **Google Chrome**
- **Windows** — certificate installation uses `certutil` and Chrome is located via Windows
  paths. Linux and macOS are not supported yet (contributions welcome).

## Install

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client

python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell
# source .venv/bin/activate       # bash

pip install -r requirements.txt
```

## Quick start

```bash
python httpcrabber.py
```

The tool asks for three things and handles the rest:

1. **Language** — Russian or English
2. **Upstream proxy** — paste it in any format, or press <kbd>Enter</kbd> to go direct
3. **Session name** — e.g. `TARGET RECON`

Then it installs the CA certificate if needed (confirm the Windows dialog once), starts
Chrome through the proxy, and streams everything into the session folder. Browse
normally — every request, response, WebSocket frame and script is captured.

Prefer it without animation:

```bash
python httpcrabber.py --no-anim
```

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

Schemes: `http`, `https`, `socks5`, `socks5h`, `socks4`.
Passwords are masked in the interface.

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

```
  Chrome ──▶ mitmproxy ──▶ pproxy bridge ──▶ your upstream proxy ──▶ target
             (captures)     (scheme adapter)
```

mitmproxy natively supports only `http`/`https` upstream proxies. To make **SOCKS5** work
transparently, httpcrabber starts a local [pproxy](https://github.com/qwj/python-proxy)
bridge that speaks HTTP to mitmproxy and any scheme to your proxy. Both hops are on
loopback, so the overhead is negligible.

## ⚠️ Security

**Captured traffic contains live credentials.** Session dumps routinely include
`Cookie`, `Set-Cookie`, `Authorization` headers, API keys and tokens for every site you
visited during the session.

- `LOGS/` and `*.jsonl` are excluded by [`.gitignore`](.gitignore) — **keep it that way**.
- Never commit, upload or share a session dump before reviewing it.
- Treat a session folder as if it were your password manager export. Because effectively, it is.

## Responsible use

This is a tool for security research, API debugging, and interoperability work on systems
you own or are authorized to test. You are responsible for complying with applicable law,
the terms of service of the sites you access, and the privacy of any third-party data you
encounter. Do not use it to access systems without permission.

## License

[GNU General Public License v3.0](LICENSE) — see the license file for the full text.
