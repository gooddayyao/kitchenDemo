"""Smoke test for recipe-generator health endpoint."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("RECIPE_GENERATOR_URL", "http://127.0.0.1:8100")


def main() -> int:
    req = urllib.request.Request(f"{BASE}/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"FAILED: cannot reach {BASE}/health — {exc}")
        print("Start the service: uvicorn main:app --port 8100")
        return 1

    if body.get("status") != "ok" or body.get("service") != "recipe-generator":
        print(f"FAILED: unexpected health response: {body}")
        return 1

    print(f"PASSED: {BASE}/health -> {body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
