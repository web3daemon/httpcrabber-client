"""Совместимость со сторонними пакетами, которую нужно применить до импорта mitmproxy."""

import importlib.util
import types


def patch_bcrypt_for_passlib() -> None:
    """mitmproxy 11.0 — последний для Python 3.11 — при импорте тянет passlib 1.7.4,
    а тот не дружит со свежим bcrypt:

      • bcrypt >= 4.1 убрал `bcrypt.__about__` — passlib пишет трейсбек про версию;
      • bcrypt >= 5 бросает ValueError на пароль длиннее 72 байт, а passlib именно
        таким паролем проверяет «wrap bug» — и импорт mitmproxy падает целиком.

    Возвращаем поведение bcrypt < 5 (молча обрезать до 72 байт — так bcrypt работал
    всегда) и только внутри нашего процесса. На Python 3.12+ mitmproxy passlib не
    использует, и патч не применяется.
    """
    if importlib.util.find_spec("passlib") is None or importlib.util.find_spec("bcrypt") is None:
        return
    import bcrypt

    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = types.SimpleNamespace(__version__=getattr(bcrypt, "__version__", ""))
    original = bcrypt.hashpw
    if getattr(original, "_httpcrabber_compat", False):
        return

    def hashpw(password: bytes, salt: bytes) -> bytes:
        return original(password[:72], salt)

    hashpw._httpcrabber_compat = True
    bcrypt.hashpw = hashpw
