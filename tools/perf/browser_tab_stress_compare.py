#!/usr/bin/env python3
"""Browser ERP tab-switch stress: dev vs prod (Playwright + staging login)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS

# Full primary nav round ×2 (18 swaps) — SSOT 9-primary order
PATHS = list(ERP_PRIMARY_NAV_PATHS) + list(ERP_PRIMARY_NAV_PATHS)


def login_and_stress(base: str, user: str, pw: str) -> dict:
    from playwright.sync_api import sync_playwright

    from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

    cookie, _ = fetch_session_cookie(base, user, pw)
    cookie_name = cookie.split("=", 1)[0]
    cookie_val = cookie.split("=", 1)[1].split(";")[0]

    out: dict = {"base": base, "dcl_ms": None, "tab_switch": [], "aba": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_cookies(
            [
                {
                    "name": cookie_name,
                    "value": cookie_val,
                    "domain": base.replace("https://", "").split("/")[0],
                    "path": "/",
                }
            ]
        )
        page = context.new_page()
        page.goto(base + "/erp/dashboard", wait_until="load", timeout=120_000)
        nav = page.evaluate(
            """() => {
              const n = performance.getEntriesByType('navigation')[0];
              return n ? {
                dcl: Math.round(n.domContentLoadedEventEnd),
                load: Math.round(n.loadEventEnd),
                ttfb: Math.round(n.responseStart)
              } : null;
            }"""
        )
        out["dcl_ms"] = nav

        for i, path in enumerate(PATHS):
            ms = page.evaluate(
                """async (path) => {
                  const t0 = performance.now();
                  await new Promise((res) => {
                    document.addEventListener('foms:main-content-swapped', function h() {
                      document.removeEventListener('foms:main-content-swapped', h);
                      res();
                    }, { once: true });
                    window.FOMS_ERP_SHELL.navigateByShell(path);
                  });
                  return Math.round(performance.now() - t0);
                }""",
                path,
            )
            out["tab_switch"].append({"i": i + 1, "path": path, "ms": ms})
            time.sleep(0.3)

        # A→B→A: dashboard warm return should use client fragment cache
        for label, a, b in [
            ("dashboard_aba", "/erp/dashboard", "/erp/measurement"),
            ("measurement_aba", "/erp/measurement", "/erp/dashboard"),
        ]:
            page.evaluate("(p) => FOMS_ERP_SHELL.navigateByShell(p)", a)
            page.wait_for_timeout(300)
            page.evaluate("(p) => FOMS_ERP_SHELL.navigateByShell(p)", b)
            page.wait_for_timeout(300)
            ms = page.evaluate(
                """async (path) => {
                  const t0 = performance.now();
                  await new Promise((res) => {
                    document.addEventListener('foms:main-content-swapped', function h() {
                      document.removeEventListener('foms:main-content-swapped', h);
                      res();
                    }, { once: true });
                    window.FOMS_ERP_SHELL.navigateByShell(path);
                  });
                  return Math.round(performance.now() - t0);
                }""",
                a,
            )
            out["aba"][label] = ms

        browser.close()
    return out


def main() -> None:
    user = os.environ.get("FOMS_STAGING_USERNAME", "")
    pw = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD")
    bases = sys.argv[1:] or [
        "https://lahom-dev.up.railway.app",
        "https://lahom-production.up.railway.app",
    ]
    results = [login_and_stress(b, user, pw) for b in bases]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
