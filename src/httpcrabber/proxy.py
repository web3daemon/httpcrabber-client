"""Разбор upstream-прокси в любом распространённом формате."""

from dataclasses import dataclass

# https-прокси провайдеров — это обычный HTTP CONNECT, для pproxy это `http`.
_SCHEME_MAP = {
    "socks5": "socks5",
    "socks5h": "socks5",
    "socks": "socks5",
    "socks4": "socks4",
    "http": "http",
    "https": "http",
}
SCHEMES = tuple(_SCHEME_MAP)


@dataclass(frozen=True)
class Proxy:
    scheme: str
    host: str
    port: int
    user: str | None = None
    password: str | None = None

    @property
    def pproxy_uri(self) -> str:
        """URI для pproxy (`-r …`); авторизация у него через `#user:pass`."""
        uri = f"{_SCHEME_MAP.get(self.scheme, 'http')}://{self.host}:{self.port}"
        if self.user:
            uri += f"#{self.user}:{self.password or ''}"
        return uri

    @property
    def display(self) -> str:
        """Строка для интерфейса — пароль скрыт."""
        auth = f"{self.user}:{'*' * len(self.password or '')}@" if self.user else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"


def parse_proxy(raw: str | None) -> Proxy | None:
    """Понимает все распространённые записи прокси.

        host:port
        host:port:user:pass
        user:pass@host:port
        scheme://host:port
        scheme://user:pass@host:port
        scheme://host:port:user:pass

    Пустая строка → None (прямое соединение). Мусор → ValueError.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    scheme, rest = "http", raw
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme = scheme.lower().strip()
        if scheme not in _SCHEME_MAP:
            raise ValueError(f"unknown proxy scheme: {scheme!r}")

    user = password = None
    if "@" in rest:
        cred, hostpart = rest.rsplit("@", 1)
        user, _, password = cred.partition(":")
        password = password or None
    else:
        hostpart = rest

    parts = hostpart.split(":")
    if len(parts) == 2:
        host, port = parts
    elif len(parts) == 4:  # host:port:user:pass
        host, port, user, password = parts
    elif len(parts) == 3:  # host:port:user
        host, port, user = parts
    else:
        raise ValueError(f"bad proxy: {raw!r}")

    host = host.strip()
    try:
        port_n = int(port.strip())
    except ValueError as exc:
        raise ValueError(f"bad port in {raw!r}") from exc
    if not host or not 0 < port_n < 65536:
        raise ValueError(f"bad host/port: {raw!r}")

    return Proxy(scheme, host, port_n, user or None, password or None)
