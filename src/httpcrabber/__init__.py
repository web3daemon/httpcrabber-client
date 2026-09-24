"""httpcrabber — network-level traffic interceptor for reverse-engineering web APIs.

Copyright (C) 2026  web3daemon

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See <https://www.gnu.org/licenses/>.
"""

from httpcrabber._compat import patch_bcrypt_for_passlib

__version__ = "1.2.1"

__all__ = ["__version__"]

# До любого импорта mitmproxy: иначе на Python 3.11 со свежим bcrypt он падает сразу
patch_bcrypt_for_passlib()
