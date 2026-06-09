from __future__ import annotations

import hashlib


def sign(params: dict[str, str], secret: str) -> str:
    """Last.fm API signature: md5 of sorted name+value pairs plus the secret.

    ``format`` and ``callback`` are excluded from the signature per the spec.
    """
    payload = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in ("format", "callback"))
    return hashlib.md5(f"{payload}{secret}".encode()).hexdigest()
