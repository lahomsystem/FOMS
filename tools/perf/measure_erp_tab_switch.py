#!/usr/bin/env python3
"""Measure ERP fragment TTFB for tab-switch paths (authenticated)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS

def _fragment_query_path(path: str) -> str:
    """Map ERP primary path to shell fragment GET path."""
    return f"{path.rstrip('/')}?view=fragment"


PATHS = tuple(_fragment_query_path(p) for p in ERP_PRIMARY_NAV_PATHS)

HEADERS_BASE = {
    "X-FOMS-ERP-SHELL": "1",
    "Accept": "text/html",
}


def login_cookie(base: str) -> str:
    user = os.environ.get("FOMS_STAGING_USERNAME", "")
    pw = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD")
    from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

    cookie, _resp = fetch_session_cookie(base, user, pw)
    return cookie


def measure(base: str, cookie: str, rounds: int = 3) -> dict:
    session = requests.Session()
    session.headers["Cookie"] = cookie
    out: dict = {"base": base, "paths": {}}
    for path in PATHS:
        url = base.rstrip("/") + path
        samples: list[dict] = []
        for i in range(rounds):
            t0 = time.perf_counter()
            r = session.get(url, headers=HEADERS_BASE, timeout=120)
            elapsed = time.perf_counter() - t0
            b7 = {
                k.lower(): v
                for k, v in r.headers.items()
                if k.lower().startswith("x-foms-ept-b7")
            }
            samples.append(
                {
                    "round": i + 1,
                    "status": r.status_code,
                    "elapsed_s": round(elapsed, 3),
                    "bytes": len(r.content),
                    "fragment": r.headers.get("X-FOMS-ERP-FRAGMENT"),
                    "b7": b7,
                }
            )
            time.sleep(0.15)
        warm = [s["elapsed_s"] for s in samples[1:]]
        out["paths"][path] = {
            "samples": samples,
            "warm_median_s": round(sorted(warm)[len(warm) // 2], 3) if warm else None,
            "bytes_median": sorted(s["bytes"] for s in samples)[len(samples) // 2],
        }
    return out


def main() -> None:
    bases = sys.argv[1:] or [
        "https://lahom-dev.up.railway.app",
        "https://lahom-production.up.railway.app",
    ]
    cookie = os.environ.get("FOMS_STAGING_COOKIE") or login_cookie(bases[0])
    results = [measure(b, cookie) for b in bases]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
