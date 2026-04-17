"""
EPT-B8 staging HTTP evidence: wall-clock GET latency + B7 response headers.

Does not authenticate — pass a browser session cookie (DevTools → Application → Cookies).

PowerShell (Win11):
  $env:FOMS_STAGING_COOKIE = 'session_staging=eyJ...full-token...'
  python tools/harness/ept_b8_staging_http_evidence.py --base https://lahom-dev.up.railway.app --order-id 2732 --json

**Railway staging** uses ``SESSION_COOKIE_NAME = session_staging`` — the env value must be
``name=value`` (not the raw token alone). If ``final_url`` contains ``/login?next=``, the
cookie was wrong or expired.

**Legacy** ``/erp/orders/<id>``: the harness uses ``allow_redirects=False`` and checks
``302`` + ``Location`` → ``/edit/<id>?…erp-beta…`` (B5 contract). Following redirects
with ``requests`` could incorrectly end on ``/login?next=…`` even when the session is valid.

Environment:
  FOMS_STAGING_COOKIE — full ``Cookie`` header value for lahom-dev (required for /erp/*).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests

# Keep in sync with foms/services/common/ept_b7_profile.py (harness must run with `cwd` = repo root).
HEADER_ROUTE = "X-FOMS-EPT-B7-ROUTE"
HEADER_RENDER_MS = "X-FOMS-EPT-B7-RENDER-MS"

PRIMARY_PATHS: tuple[str, ...] = (
    "/erp/dashboard",
    "/erp/measurement",
    "/erp/drawing-workbench",
    "/erp/production/dashboard",
    "/erp/shipment",
    "/erp/as",
    "/erp/construction/dashboard",
    "/erp/completion",
    "/erp/history/",
)


def _subordinate_paths(order_id: int) -> tuple[str, ...]:
    return (
        f"/erp/drawing-workbench/{order_id}",
        f"/edit/{order_id}?open=erp-beta",
        f"/erp/orders/{order_id}",
        "/erp/shipment-settings",
    )


def _tier_e_optional() -> tuple[str, ...]:
    return ("/map_view", "/regional_dashboard", "/metropolitan_dashboard", "/self_measurement_dashboard")


def _measure_get(
    session: requests.Session,
    url: str,
    *,
    no_cache: bool,
    allow_redirects: bool = True,
) -> tuple[float, requests.Response]:
    headers: dict[str, str] = {}
    if no_cache:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    start = time.perf_counter()
    resp = session.get(
        url, headers=headers, allow_redirects=allow_redirects, timeout=120
    )
    elapsed = time.perf_counter() - start
    return elapsed, resp


def _b7_from_response(resp: requests.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    want = {HEADER_ROUTE.lower(), HEADER_RENDER_MS.lower()}
    for k, v in resp.headers.items():
        if k.lower() in want:
            out[k] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="EPT-B8 staging HTTP timing + B7 headers")
    parser.add_argument(
        "--base",
        default="https://lahom-dev.up.railway.app",
        help="Staging origin (no trailing slash)",
    )
    parser.add_argument("--order-id", type=int, default=2732, help="Order id for Tier B/C paths")
    parser.add_argument(
        "--cookie-env",
        default="FOMS_STAGING_COOKIE",
        help="Environment variable name holding the Cookie header value",
    )
    parser.add_argument("--json", action="store_true", help="Print one JSON object to stdout")
    parser.add_argument(
        "--include-tier-e",
        action="store_true",
        help="Also GET Tier E dashboards (may be heavy / auth-gated)",
    )
    args = parser.parse_args()

    cookie = os.environ.get(args.cookie_env, "").strip()
    if not cookie:
        print(
            f"ERROR: Set {args.cookie_env} to the browser Cookie string for staging.",
            file=sys.stderr,
        )
        return 2
    if "=" not in cookie:
        print(
            "WARNING: Cookie value should look like 'session_staging=<token>' (name=value). "
            "Raw token alone will not authenticate.",
            file=sys.stderr,
        )

    base = args.base.rstrip("/")
    session = requests.Session()
    session.headers.update({"Cookie": cookie, "User-Agent": "FOMS-EPT-B8-harness/1.0"})

    rows: dict[str, Any] = {}

    # Primary 9: full reload ~= no-cache first GET; warm ~= immediate second GET same URL
    for path in PRIMARY_PATHS:
        url = base + path
        full_s, r1 = _measure_get(session, url, no_cache=True)
        warm_s, r2 = _measure_get(session, url, no_cache=False)
        rows[path] = {
            "full_reload_s": round(full_s, 3),
            "warm_second_get_s": round(warm_s, 3),
            "final_url": r2.url,
            "status_code": r2.status_code,
            "b7_headers": _b7_from_response(r2),
        }

    # Cold-ish nav proxy: sequential first GETs (after shell "land" on dashboard)
    cold_chain: list[dict[str, Any]] = []
    session2 = requests.Session()
    session2.headers.update({"Cookie": cookie, "User-Agent": "FOMS-EPT-B8-harness/1.0"})
    land_s, _ = _measure_get(session2, base + "/erp/dashboard", no_cache=True)
    cold_chain.append({"step": "land_dashboard", "elapsed_s": round(land_s, 3)})
    for path in ("/erp/measurement", "/erp/shipment"):
        url = base + path
        es, resp = _measure_get(session2, url, no_cache=True)
        cold_chain.append(
            {
                "step": f"first_get_after_dashboard {path}",
                "elapsed_s": round(es, 3),
                "status": resp.status_code,
                "b7": _b7_from_response(resp),
            }
        )

    sub: dict[str, Any] = {}
    for path in _subordinate_paths(args.order_id):
        url = base + path
        # B5 legacy URL: 302 → /edit/<id>?open=erp-beta. Following redirects with
        # requests can end on /login?next=... (session/cookie edge on redirect chain);
        # contract is validated on the first hop only.
        if path.startswith("/erp/orders/"):
            es, resp = _measure_get(
                session, url, no_cache=True, allow_redirects=False
            )
            loc = (resp.headers.get("Location") or "").replace("\\", "/")
            contract_ok = (
                resp.status_code in (301, 302, 303, 307, 308)
                and f"/edit/{args.order_id}" in loc
                and "erp-beta" in loc.lower()
                and "/login" not in loc.lower()
            )
            sub[path] = {
                "full_reload_s": round(es, 3),
                "final_url": resp.url,
                "status_code": resp.status_code,
                "redirect_location": resp.headers.get("Location"),
                "legacy_redirect_contract_ok": contract_ok,
                "b7_headers": _b7_from_response(resp),
            }
        else:
            es, resp = _measure_get(session, url, no_cache=True)
            sub[path] = {
                "full_reload_s": round(es, 3),
                "final_url": resp.url,
                "status_code": resp.status_code,
                "b7_headers": _b7_from_response(resp),
            }

    optional: dict[str, Any] = {}
    if args.include_tier_e:
        for path in _tier_e_optional():
            url = base + path
            es, resp = _measure_get(session, url, no_cache=True)
            optional[path] = {
                "full_reload_s": round(es, 3),
                "status_code": resp.status_code,
                "final_url": resp.url,
            }

    out: dict[str, Any] = {
        "base": base,
        "primary": rows,
        "cold_nav_proxy": cold_chain,
        "subordinate": sub,
    }
    if optional:
        out["tier_e_optional"] = optional

    _emit_auth_warnings(rows, sub)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


def _emit_auth_warnings(primary: dict[str, Any], subordinate: dict[str, Any]) -> None:
    """If responses look like login redirects, warn — do not treat timings as ERP evidence."""
    bad: list[str] = []
    for path, data in primary.items():
        url = str(data.get("final_url", ""))
        if "/login" in url and "next=" in url:
            bad.append(path)
    for path, data in subordinate.items():
        if data.get("legacy_redirect_contract_ok"):
            continue
        url = str(data.get("final_url", ""))
        if "/login" in url and "next=" in url:
            bad.append(path)
    if bad:
        print(
            "ERROR (stderr): Responses redirect to /login?next=... — not authenticated. "
            "Fix: $env:FOMS_STAGING_COOKIE = 'session_staging=<paste value from DevTools>' "
            f"(paths affected: {len(bad)}). Timings below are login-page latency, not ERP.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
