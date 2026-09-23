# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `HTTPCRABBER_MAX_BODY` overrides the 200 KB body cap in the dump.
- `HTTPCRABBER_BINARY_BODIES=1` stores binary bodies (≤ `MAX_BODY_SIZE`) as base64
  in the dump instead of a `[binary, N bytes]` placeholder. Off by default.

### Changed
- Redesigned terminal UI: diagonal-gradient banner with shaded depth, timestamped `OK` /
  `FAIL` / `INFO` status badges, spinners with elapsed time, card-style session brief.
- Live panel: two-column header, feed with a column header, bright host / muted path,
  a marker on the newest row and a fixed height (no jumping); blinking `● REC`,
  gradient sparkline, hint moved into the frame.
- Session summary: stat tiles, gradient host bars with share %, colored method and status
  breakdown with a stacked status bar; columns stack on narrow terminals.
- READMEs show real SVG renders of the UI (`scripts/gen_screenshots.py`, EN and RU) and a
  Mermaid architecture diagram; added a 1280×640 social preview image.

## [1.0.0] — 2026-07-19

First public release.

### Added
- Installable package: `pip install -e .` gives the `httpcrabber` command; `python run.py`
  works from a clone without installing.
- Cross-platform: Windows, macOS and Linux — browser discovery and CA certificate
  installation for each (`certutil` / `security` / NSS `certutil`).
- Non-interactive mode: `--lang`, `--session`, `--proxy` / `--direct`, `--port`, `--output`,
  `--no-browser`, `--no-anim`. Prompts appear only for what was not given.
- `--no-browser` for use with any browser or device pointed at the proxy.
- Upstream proxy support for `socks5` / `socks5h` / `socks4` / `http` / `https`, with or
  without auth, in every common notation — via a local pproxy bridge.
- One folder per session containing the JSONL dump and every captured script.
- Full JavaScript capture: external bundles and inline `<script>` blocks, stored complete
  (dump bodies are truncated at 200 KB, scripts are not), deduplicated by SHA-256, with an
  `index.json` manifest.
- Animated hacker CLI: matrix rain, gradient glitch banner, typewriter, real status lines,
  spinners for real waits, session brief panel.
- Live intercept feed with colored methods and status codes, counters and a traffic sparkline.
- End-of-session analytics: top hosts, method and status-class breakdown, duration, dump size.
- Safe shutdown on browser close or `Ctrl+C`; child processes are always cleaned up.
- Test suite (pytest) and CI on three operating systems.

### Fixed
- Saved JavaScript no longer gets `\r\n` line endings on Windows (the file on disk now
  matches the SHA-256 in the manifest).
- The mitmproxy listener is now closed explicitly when a session ends. mitmproxy 11 does
  not stop its servers on `shutdown()`, so on Linux/macOS the port stayed bound until the
  process exited.
- Free-port detection uses `bind` instead of `connect`, which could hang on filtered ports.
- Hard `Ctrl+C` on Windows no longer leaves Chrome or the pproxy bridge running.

[Unreleased]: https://github.com/web3daemon/httpcrabber-client/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/web3daemon/httpcrabber-client/releases/tag/v1.0.0
