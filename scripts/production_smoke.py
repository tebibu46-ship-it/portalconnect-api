"""Run post-deploy checks against a PortalConnect base URL."""

from __future__ import annotations

import sys
import httpx


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    checks = ("/healthz", "/v1/terminals", "/api/v1/vessels/inbound", "/api/v1/ledger/export")
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for path in checks:
            response = client.get(base + path)
            response.raise_for_status()
            print(f"OK {response.status_code} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
