import asyncio
import socket
import subprocess
import sys
import time

from httpcrabber import procs


def test_free_port_is_bindable():
    port = procs.free_port(9700)
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


def test_free_port_skips_busy():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        taken = busy.getsockname()[1]
        assert procs.free_port(taken) != taken


def test_wait_port_true_and_false():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert asyncio.run(procs.wait_port("127.0.0.1", port, timeout=2))
    assert not asyncio.run(procs.wait_port("127.0.0.1", procs.free_port(9800), timeout=0.5))


def test_cleanup_terminates_registered_children():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    procs.register(child)
    assert child.poll() is None
    procs.cleanup()
    for _ in range(50):
        if child.poll() is not None:
            break
        time.sleep(0.1)
    assert child.poll() is not None
