"""
GNV-B6: Playwright browser metrics — G1-A full nav, optional back/forward, paint proxies.

Requires: pip install playwright ; playwright install chromium
Requires: FOMS_STAGING_USERNAME, FOMS_STAGING_PASSWORD

Scenarios:
  g1_full_nav — / → click 접수 (/?status=RECEIVED) full document; Performance API
  g1_trash_roundtrip — / → /trash via nav → browser Back
  g2_chat — /chat navigation + paint (FCP proxy)

Exits 0 with SKIP message if Playwright not installed (not a failure).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

DEFAULT_BASE = "https://lahom-dev.up.railway.app"


def _login(page: Any, origin: str) -> None:
    login_url = f"{origin}/login?next=/"
    page.goto(login_url, wait_until="domcontentloaded", timeout=120_000)
    page.fill('input[name="username"]', os.environ.get("FOMS_STAGING_USERNAME", "").strip())
    page.fill('input[name="password"]', os.environ.get("FOMS_STAGING_PASSWORD", ""))
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=120_000)


def _perf_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const nav = performance.getEntriesByType('navigation');
          const last = nav.length ? nav[nav.length - 1] : null;
          const paints = performance.getEntriesByType('paint');
          return {
            navigation_last: last ? {
              duration: last.duration,
              domContentLoadedEventEnd: last.domContentLoadedEventEnd,
              loadEventEnd: last.loadEventEnd,
              transferSize: last.transferSize,
              type: last.type,
            } : null,
            paint: paints.map(p => ({ name: p.name, startTime: p.startTime })),
          };
        }"""
    )


def _perf_snapshot_retry(page: Any, *, attempts: int = 5, delay_s: float = 0.4) -> dict[str, Any]:
    """After history navigation, client-side nav (e.g. G1-A swap) can destroy the execution context briefly."""
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            return _perf_snapshot(page)
        except Exception as exc:
            last_err = exc
            time.sleep(delay_s)
    assert last_err is not None
    raise last_err


def _scenario_g1_full_nav(page: Any, origin: str) -> dict[str, Any]:
    page.goto(origin + "/", wait_until="networkidle", timeout=120_000)
    page.wait_for_selector("nav.layout-global-nav", timeout=60_000)
    sel = 'nav.layout-global-nav a.nav-link[href*="status=RECEIVED"]'
    page.wait_for_selector(sel, timeout=30_000)
    t0 = time.perf_counter()
    with page.expect_navigation(wait_until="networkidle", timeout=120_000):
        page.click(sel)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    perf = _perf_snapshot(page)
    return {
        "scenario": "g1_full_nav",
        "click_to_networkidle_ms": round(wall_ms, 2),
        "final_url": page.url,
        "performance": perf,
        "note": "Full document navigation via top-nav; not fragment swap timing.",
    }


def _scenario_g1_trash_roundtrip(page: Any, origin: str) -> dict[str, Any]:
    page.goto(origin + "/", wait_until="networkidle", timeout=120_000)
    page.wait_for_selector("nav.layout-global-nav", timeout=60_000)
    trash_sel = 'nav.layout-global-nav a.nav-link[href="/trash"]'
    page.wait_for_selector(trash_sel, timeout=30_000)
    t0 = time.perf_counter()
    with page.expect_navigation(wait_until="networkidle", timeout=120_000):
        page.click(trash_sel)
    to_trash_ms = (time.perf_counter() - t0) * 1000.0
    t1 = time.perf_counter()
    page.go_back(wait_until="networkidle", timeout=120_000)
    back_ms = (time.perf_counter() - t1) * 1000.0
    page.wait_for_selector("nav.layout-global-nav", timeout=60_000)
    page.wait_for_load_state("networkidle", timeout=120_000)
    perf = _perf_snapshot_retry(page)
    return {
        "scenario": "g1_trash_roundtrip",
        "click_trash_full_document_ms": round(to_trash_ms, 2),
        "browser_back_ms": round(back_ms, 2),
        "url_after_back": page.url,
        "performance": perf,
        "note": "Document navigation + history Back; if deployed build has G1-A swap, may differ from fragment-only path.",
    }


def _scenario_g2_chat(page: Any, origin: str) -> dict[str, Any]:
    page.goto(origin + "/chat", wait_until="networkidle", timeout=120_000)
    perf = _perf_snapshot(page)
    return {
        "scenario": "g2_chat",
        "final_url": page.url,
        "performance": perf,
        "note": "G2 full document; FCP in paint array if available.",
    }


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "SKIP: pip install playwright ; playwright install chromium",
            file=sys.stderr,
        )
        return 0

    parser = argparse.ArgumentParser(description="GNV-B6 Playwright metrics")
    parser.add_argument("--base", default=os.environ.get("FOMS_STAGING_BASE_URL", DEFAULT_BASE))
    parser.add_argument(
        "--scenario",
        choices=("g1_full_nav", "g1_trash_roundtrip", "g2_chat"),
        default="g1_trash_roundtrip",
    )
    args = parser.parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not password:
        print("ERROR: Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD", file=sys.stderr)
        return 2

    origin = args.base.rstrip("/")
    out: dict[str, Any] = {"harness": "gnv_b6_staging_browser_metrics", "base": origin, "scenario": args.scenario}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="FOMS-GNV-B6-browser/1.0",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        _login(page, origin)

        if args.scenario == "g1_full_nav":
            out["metrics"] = _scenario_g1_full_nav(page, origin)
        elif args.scenario == "g2_chat":
            out["metrics"] = _scenario_g2_chat(page, origin)
        else:
            out["metrics"] = _scenario_g1_trash_roundtrip(page, origin)

        context.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
