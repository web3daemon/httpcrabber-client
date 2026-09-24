import subprocess
import sys

import bcrypt

from httpcrabber import _compat


def test_mitmproxy_imports_in_a_fresh_interpreter():
    """Python 3.11 + mitmproxy 11.0 + bcrypt 5: без патча импорт падал с ValueError."""
    code = "import httpcrabber.session, mitmproxy.tools.dump; print('ok')"
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    assert "error reading bcrypt version" not in run.stderr


def test_patch_is_idempotent_and_truncates_like_old_bcrypt():
    _compat.patch_bcrypt_for_passlib()
    _compat.patch_bcrypt_for_passlib()
    if _compat.importlib.util.find_spec("passlib") is None:
        return  # Python 3.12+: mitmproxy без passlib, патч не нужен и не применяется
    salt = bcrypt.gensalt(rounds=4)
    assert bcrypt.hashpw(b"x" * 100, salt) == bcrypt.hashpw(b"x" * 72, salt)
