"""CA-сертификат mitmproxy: генерация и установка в доверенные на каждой ОС.

  Windows — пользовательское хранилище Root через certutil (без прав админа,
            Windows покажет один диалог подтверждения).
  macOS   — login keychain через `security add-trusted-cert` (GUI-запрос пароля).
  Linux   — Chrome читает NSS-базу ~/.pki/nssdb; кладём туда через certutil
            из libnss3-tools. Firefox использует свою базу — ему нужен http://mitm.it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from mitmproxy.certs import CertStore

from httpcrabber.config import CONFDIR

CA_NAME = "mitmproxy"
_RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="ignore")


def cert_path() -> Path:
    """Файл CA (генерируется при первом вызове)."""
    CONFDIR.mkdir(parents=True, exist_ok=True)
    CertStore.from_store(str(CONFDIR), CA_NAME, 2048)  # создаёт файлы, если их нет
    ext = "cer" if sys.platform == "win32" else "pem"
    return CONFDIR / f"{CA_NAME}-ca-cert.{ext}"


def _nss_db() -> Path:
    return Path.home() / ".pki" / "nssdb"


def is_installed() -> bool:
    try:
        if sys.platform == "win32":
            out = subprocess.run(["certutil", "-user", "-store", "Root"], timeout=30, **_RUN)
            return CA_NAME in (out.stdout or "").lower()
        if sys.platform == "darwin":
            out = subprocess.run(["security", "find-certificate", "-c", CA_NAME], timeout=30, **_RUN)
            return out.returncode == 0
        # linux / прочие unix — NSS-база Chrome
        if not shutil.which("certutil") or not _nss_db().exists():
            return False
        out = subprocess.run(["certutil", "-d", f"sql:{_nss_db()}", "-L"], timeout=30, **_RUN)
        return CA_NAME in (out.stdout or "").lower()
    except Exception:
        return False


def install() -> str:
    """Ставит CA. Возвращает 'installed' | 'failed' | 'no_tool'."""
    cert = cert_path()
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["certutil", "-user", "-addstore", "-f", "Root", str(cert)], timeout=120, **_RUN
            )
        elif sys.platform == "darwin":
            keychain = Path.home() / "Library" / "Keychains" / "login.keychain-db"
            subprocess.run(
                ["security", "add-trusted-cert", "-r", "trustRoot", "-k", str(keychain), str(cert)],
                timeout=180, **_RUN,
            )
        else:
            if not shutil.which("certutil"):
                return "no_tool"
            db = _nss_db()
            if not db.exists():
                db.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["certutil", "-d", f"sql:{db}", "-N", "--empty-password"], timeout=30, **_RUN
                )
            subprocess.run(
                ["certutil", "-d", f"sql:{db}", "-A", "-t", "C,,", "-n", CA_NAME, "-i", str(cert)],
                timeout=30, **_RUN,
            )
    except Exception:
        return "failed"
    return "installed" if is_installed() else "failed"


def ensure() -> str:
    """'present' если уже стоит, иначе результат install()."""
    cert_path()
    return "present" if is_installed() else install()
