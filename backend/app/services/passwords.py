"""Password hashing with scrypt from the standard library (no extra dependency).

Stored format: ``scrypt$N$r$p$salt$hash`` (base64). The parameters are stored with each hash,
so they can be raised later and old hashes still verify.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
from functools import lru_cache

_N, _R, _P = 2**15, 8, 1  # about 32 MiB and tens of milliseconds per hash
_MAXMEM = 128 * 1024 * 1024
MIN_LENGTH, MAX_LENGTH = 10, 128


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(_derive(password, salt, _N, _R, _P))}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. A malformed stored hash simply fails to verify."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return hash_password("not-a-real-password")


def burn_time_like_a_login() -> None:
    """Spend the same time as a real check, so an unknown email can't be told apart by speed."""
    verify_password("wrong-password", _dummy_hash())


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, stored: str) -> bool:
    return await asyncio.to_thread(verify_password, password, stored)


async def burn_time_async() -> None:
    await asyncio.to_thread(burn_time_like_a_login)
