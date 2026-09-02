"""Локальный мост pproxy: HTTP для mitmproxy ↔ любая схема для upstream-прокси.

mitmproxy в upstream-режиме умеет только http/https. Чтобы socks5 работал
прозрачно, поднимаем pproxy на loopback: он слушает http и форвардит в
socks5/http/https с авторизацией. Обе «ноги» локальные — накладных расходов нет.
"""

import subprocess
import sys

from httpcrabber import procs


def start_bridge(pproxy_uri: str, bridge_port: int) -> subprocess.Popen:
    args = [
        sys.executable, "-m", "pproxy",
        "-l", f"http://127.0.0.1:{bridge_port}",
        "-r", pproxy_uri,
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.register(proc)
    return proc
