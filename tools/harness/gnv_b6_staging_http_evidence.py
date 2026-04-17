"""
GNV-B6: Railway staging HTTP evidence for global-nav real speed (G1-A full vs fragment, G2 warm doc).

Requires authenticated staging session:
  $env:FOMS_STAGING_COOKIE = 'session_staging=<token>'
  python tools/harness/gnv_b6_staging_http_evidence.py --base https://lahom-dev.up.railway.app --json \\
    > docs/harness/evidence/YYYY-MM-DD-gnv-b6-staging-http-evidence.json

Does not invent timings — exits 2 if cookie missing. If final_url contains /login?next=, not authenticated.

See: docs/plans/2026-04-17-gnv-run-record.md §GNV-B6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests

HEADER_GNAV = "X-FOMS-GNAV"
HEADER_GNAV_FRAGMENT = "X-FOMS-GNAV-FRAGMENT"

# G1-A swap-eligible (taxonomy freeze)
G1A_PATHS: tuple[str, ...] = (
    "/",
    "/?status=RECEIVED",
    "/trash",
)

# G2 cross-surface (document warmup; no body swap)
G2_PATHS: tuple[str, ...] = (
    "/erp/dashboard",
    "/chat",
)


def _with_nav_fragment(path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}view=nav-fragment"


def _measure_get(
    session: requests.Session,
    url: str,
    *,
    no_cache: bool,
    extra_headers: dict[str, str] | None = None,
) -> tuple[float, requests.Response]:
    headers: dict[str, str] = {}
    if no_cache:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    if extra_headers:
        headers.update(extra_headers)
    start = time.perf_counter()
    resp = session.get(url, headers=headers, timeout=120)
    elapsed = time.perf_counter() - start
    return elapsed, resp


def _row_from_response(elapsed: float, resp: requests.Response) -> dict[str, Any]:
    return {
        "elapsed_s": round(elapsed, 3),
        "status_code": resp.status_code,
        "final_url": resp.url,
        "x_foms_gnav_fragment": resp.headers.get(HEADER_GNAV_FRAGMENT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GNV-B6 staging HTTP timing (G1-A + G2)")
    parser.add_argument(
        "--base",
        default="https://lahom-dev.up.railway.app",
        help="Staging origin (no trailing slash)",
    )
    parser.add_argument(
        "--cookie-env",
        default="FOMS_STAGING_COOKIE",
        help="Env var for Cookie header (name=value)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args()

    cookie = os.environ.get(args.cookie_env, "").strip()
    if not cookie:
        print(
            f"ERROR: Set {args.cookie_env} to staging Cookie (session_staging=...).",
            file=sys.stderr,
        )
        return 2
    if "=" not in cookie:
        print(
            "WARNING: Cookie should be 'session_staging=<token>' (name=value).",
            file=sys.stderr,
        )

    base = args.base.rstrip("/")
    session = requests.Session()
    session.headers.update({"Cookie": cookie, "User-Agent": "FOMS-GNV-B6-harness/1.0"})

    g1a_full: dict[str, Any] = {}
    g1a_fragment: dict[str, Any] = {}
    g2_document: dict[str, Any] = {}

    for path in G1A_PATHS:
        url = base + path
        cold_s, r1 = _measure_get(session, url, no_cache=True)
        warm_s, r2 = _measure_get(session, url, no_cache=False)
        g1a_full[path] = {
            "cold_no_cache_s": round(cold_s, 3),
            "warm_second_get_s": round(warm_s, 3),
            "final_url": r2.url,
            "status_code": r2.status_code,
        }

    frag_headers = {HEADER_GNAV: "1"}
    for path in G1A_PATHS:
        url = base + _with_nav_fragment(path)
        cold_s, r1 = _measure_get(session, url, no_cache=True, extra_headers=frag_headers)
        warm_s, r2 = _measure_get(session, url, no_cache=False, extra_headers=frag_headers)
        ok = r2.headers.get(HEADER_GNAV_FRAGMENT) == "1" and r2.status_code == 200
        g1a_fragment[path] = {
            "cold_no_cache_s": round(cold_s, 3),
            "warm_second_get_s": round(warm_s, 3),
            "fragment_header_ok": ok,
            "x_foms_gnav_fragment": r2.headers.get(HEADER_GNAV_FRAGMENT),
            "final_url": r2.url,
            "status_code": r2.status_code,
        }

    for path in G2_PATHS:
        url = base + path
        cold_s, r1 = _measure_get(session, url, no_cache=True)
        warm_s, r2 = _measure_get(session, url, no_cache=False)
        g2_document[path] = {
            "cold_no_cache_s": round(cold_s, 3),
            "warm_second_get_s": round(warm_s, 3),
            "final_url": r2.url,
            "status_code": r2.status_code,
        }

    out: dict[str, Any] = {
        "harness": "gnv_b6_staging_http_evidence",
        "base": base,
        "g1a_full_document": g1a_full,
        "g1a_nav_fragment": g1a_fragment,
        "g2_warm_document": g2_document,
        "notes": {
            "cold_no_cache_s": "Proxy for first navigation (Cache-Control: no-cache).",
            "warm_second_get_s": "Immediate second GET same URL (browser cache warm).",
            "g1a_nav_fragment": "GET with view=nav-fragment + X-FOMS-GNAV: 1; not browser #main-content swap ms.",
            "miss_taxonomy": "If targets missed: HTML | render | asset | query | prefetch miss",
        },
    }

    _warn_login(g1a_full, g1a_fragment, g2_document)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _warn_login(
    g1a_full: dict[str, Any],
    g1a_fragment: dict[str, Any],
    g2_document: dict[str, Any],
) -> None:
    bad: list[str] = []
    for label, d in (
        ("g1a_full", g1a_full),
        ("g1a_fragment", g1a_fragment),
        ("g2", g2_document),
    ):
        for path, data in d.items():
            url = str(data.get("final_url", ""))
            if "/login" in url and "next=" in url:
                bad.append(f"{label}:{path}")
    if bad:
        print(
            "ERROR (stderr): Some responses redirect to /login — timings are NOT app pages. "
            f"Fix cookie. Affected: {bad}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
