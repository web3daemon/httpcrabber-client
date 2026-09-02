"""Дочерние процессы и порты."""

import asyncio
import atexit
import socket
import subprocess
import time

# Реестр дочерних процессов (браузер, мост pproxy). На жёстком Ctrl+C на Windows
# KeyboardInterrupt может пролететь мимо finally внутри сессии — тогда очистку
# гарантируют atexit и finally в main(), чтобы не оставлять процессы-сироты.
_CHILDREN: list[subprocess.Popen] = []


def register(proc: subprocess.Popen | None) -> subprocess.Popen | None:
    if proc is not None:
        _CHILDREN.append(proc)
    return proc


def cleanup() -> None:
    for proc in _CHILDREN:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    _CHILDREN.clear()


atexit.register(cleanup)


def free_port(preferred: int, span: int = 50) -> int:
    """preferred, если свободен, иначе первый свободный выше него.

    Проверяем через bind (мгновенно и надёжно), а не connect — connect к порту,
    который молча дропает SYN, может висеть на TCP-таймауте.
    """
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


async def wait_port(host: str, port: int, timeout: float = 8.0) -> bool:
    """Ждёт, пока порт начнёт принимать соединения."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(host, port):
            return True
        await asyncio.sleep(0.15)
    return False
