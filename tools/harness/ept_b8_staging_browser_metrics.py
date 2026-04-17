"""
EPT-B8 optional: browser Performance API (navigation timing + paint) on staging after login.

Requires: ``pip install playwright`` then ``playwright install chromium`` (once).

Environment (same as login harness):
  FOMS_STAGING_BASE_URL, FOMS_STAGING_USERNAME, FOMS_STAGING_PASSWORD

Prints JSON to stdout: navigation entry, paint entries, and optional long tasks sample.
If Playwright is not installed, prints a SKIP message to stderr and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

DEFAULT_BASE = "https://lahom-dev.up.railway.app"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "SKIP: install Playwright — pip install playwright ; playwright install chromium",
            file=sys.stderr,
        )
        return 0

    parser = argparse.ArgumentParser(description="EPT-B8 staging browser metrics (Playwright)")
    parser.add_argument("--base", default=os.environ.get("FOMS_STAGING_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--path", default="/erp/dashboard", help="Path after login")
    args = parser.parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not password:
        print("ERROR: Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD", file=sys.stderr)
        return 2

    origin = args.base.rstrip("/")
    login_url = f"{origin}/login?next=/erp/dashboard"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="FOMS-EPT-B8-browser-metrics/1.0",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=120_000)
        page.fill('input[name="username"]', user)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=120_000)

        target = origin + args.path
        page.goto(target, wait_until="networkidle", timeout=120_000)

        metrics: dict[str, Any] = page.evaluate(
            """() => {
              const nav = performance.getEntriesByType('navigation')[0];
              const paints = performance.getEntriesByType('paint');
              const longTasks = performance.getEntriesByType('longtask').slice(0, 20);
              return {
                navigation: nav ? {
                  type: nav.entryType,
                  duration: nav.duration,
                  domContentLoadedEventEnd: nav.domContentLoadedEventEnd,
                  loadEventEnd: nav.loadEventEnd,
                  transferSize: nav.transferSize,
                } : null,
                paint: paints.map(p => ({ name: p.name, startTime: p.startTime })),
                longtask_sample: longTasks.map(t => ({ duration: t.duration, startTime: t.startTime })),
              };
            }"""
        )

        context.close()
        browser.close()

    print(json.dumps({"base": origin, "path": args.path, "metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
