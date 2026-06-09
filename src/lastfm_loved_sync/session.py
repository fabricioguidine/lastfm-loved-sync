from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Map browser-export sameSite values to Playwright's accepted set.
_SAMESITE = {"lax": "Lax", "strict": "Strict", "no_restriction": "None", "none": "None"}


def import_cookies(cookies_path: Path, out_path: Path) -> int:
    """Convert a browser cookie export (JSON array) into a Playwright storage_state
    file, so the browser automation runs authenticated without an interactive login.
    """
    raw = json.loads(cookies_path.read_text(encoding="utf-8"))
    cookies: list[dict[str, Any]] = []
    for c in raw:
        same_site = _SAMESITE.get(str(c.get("sameSite", "")).lower(), "Lax")
        secure = bool(c.get("secure", False))
        if same_site == "None" and not secure:
            same_site = "Lax"
        cookies.append(
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "expires": float(c["expirationDate"]) if c.get("expirationDate") else -1,
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": secure,
                "sameSite": same_site,
            }
        )
    out_path.write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")
    return len(cookies)
