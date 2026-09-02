# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private reporting: **Security → Report a vulnerability** on
<https://github.com/web3daemon/httpcrabber-client/security/advisories/new>.

Include what you found, how to reproduce it, and what impact you believe it has.
You will get an acknowledgement within a few days. Fixes are released as soon as
they are ready; credit is given in the changelog unless you prefer otherwise.

## Supported versions

Only the latest release on `main` receives fixes.

## What this tool does — and what that means for you

httpcrabber is a man-in-the-middle proxy. By design it:

- installs a **root CA certificate** into your user trust store so HTTPS can be
  decrypted. This CA is generated locally by mitmproxy and never leaves your machine.
  Remove it when you no longer need the tool (see below);
- writes **every request and response**, including `Cookie`, `Set-Cookie`,
  `Authorization` headers, API keys and tokens, to `LOGS/<session>/` in plain text.

Treat a session folder as a credential dump. Never commit, upload or share it without
reviewing it first. The repository's `.gitignore` excludes `LOGS/` and `*.jsonl` — keep it.

### Removing the CA certificate

| OS | Command |
|---|---|
| Windows | `certutil -user -delstore Root mitmproxy` |
| macOS | `security delete-certificate -c mitmproxy ~/Library/Keychains/login.keychain-db` |
| Linux (Chrome) | `certutil -d sql:$HOME/.pki/nssdb -D -n mitmproxy` |

The private key lives in `~/.mitmproxy/` — delete that directory too.
