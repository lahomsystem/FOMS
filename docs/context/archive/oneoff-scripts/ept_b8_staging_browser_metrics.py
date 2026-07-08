"""
EPT-B8 optional: browser Performance API + shell tab swap timing on staging.

Requires: ``pip install playwright`` then ``playwright install chromium`` (once).

Environment (same as login harness):
  FOMS_STAGING_BASE_URL, FOMS_STAGING_USERNAME, FOMS_STAGING_PASSWORD

Scenarios:
  navigation — Performance API after GET ``--path`` (default /erp/dashboard)
  erp_shell_tab_swap — click fast-tab to 실측; measure time until fragment GET completes
  g1_document_nav — full document click 주문 목록 → 휴지통 (G1 family; not shell swap)
  primary_subordinate_roundtrip — dashboard → Tier B detail GET → **browser Back** (document proxy; not shell HAR)

If Playwright is not installed, prints a SKIP message to stderr and exits 0.
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
    login_url = f"{origin}/login?next=/erp/dashboard"
    page.goto(login_url, wait_until="domcontentloaded", timeout=120_000)
    page.fill('input[name="username"]', os.environ.get("FOMS_STAGING_USERNAME", "").strip())
    page.fill('input[name="password"]', os.environ.get("FOMS_STAGING_PASSWORD", ""))
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=120_000)


def _scenario_navigation(page: Any, origin: str, path: str) -> dict[str, Any]:
    target = origin + path
    page.goto(target, wait_until="networkidle", timeout=120_000)
    return page.evaluate(
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


def _scenario_erp_shell_tab_swap(page: Any, origin: str) -> dict[str, Any]:
    """Click-to-fragment-response proxy (not full paint); B8 §6.3 supplement."""
    page.goto(origin + "/erp/dashboard", wait_until="networkidle", timeout=120_000)
    sel = "a[data-foms-erp-fast-tab][href*='/erp/measurement']"
    page.wait_for_selector(sel, timeout=60_000)

    def _is_measurement_fragment(resp: Any) -> bool:
        u = resp.url or ""
        return (
            resp.request.method == "GET"
            and resp.status == 200
            and "view=fragment" in u
            and "/erp/measurement" in u
        )

    t0 = time.perf_counter()
    with page.expect_response(_is_measurement_fragment, timeout=120_000) as resp_info:
        page.click(sel)
    resp = resp_info.value
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "click_to_fragment_response_ms": round(elapsed_ms, 2),
        "fragment_request_url": resp.url,
        "note": "Server round-trip for shell fragment fetch; not LCP/paint.",
    }


def _scenario_primary_subordinate_roundtrip(page: Any, origin: str, order_id: int) -> dict[str, Any]:
    """Primary → subordinate (document) → Back; proxy until full HAR (B8 §6.4)."""
    page.goto(origin + "/erp/dashboard", wait_until="networkidle", timeout=120_000)
    detail = f"{origin}/erp/drawing-workbench/{order_id}"
    page.goto(detail, wait_until="networkidle", timeout=120_000)
    t0 = time.perf_counter()
    page.go_back(wait_until="networkidle", timeout=120_000)
    back_ms = (time.perf_counter() - t0) * 1000.0
    perf = page.evaluate(
        """() => {
          const nav = performance.getEntriesByType('navigation');
          const last = nav.length ? nav[nav.length - 1] : null;
          return last ? { duration: last.duration, type: last.type } : null;
        }"""
    )
    return {
        "order_id": order_id,
        "back_to_dashboard_ms": round(back_ms, 2),
        "url_after_back": page.url,
        "navigation_entry_last": perf,
        "note": "Full document navigation + history Back; not in-shell swap. Complement with HAR for popstate/shell.",
    }


def _scenario_g1_document_nav(page: Any, origin: str) -> dict[str, Any]:
    """G1: full document navigation (global nav, not ERP shell body swap)."""
    page.goto(origin + "/", wait_until="networkidle", timeout=120_000)
    page.wait_for_selector("nav.layout-global-nav", timeout=60_000)
    trash_sel = 'nav.layout-global-nav a.nav-link[href="/trash"]'
    page.wait_for_selector(trash_sel, timeout=30_000)
    t0 = time.perf_counter()
    with page.expect_navigation(wait_until="networkidle", timeout=120_000):
        page.click(trash_sel)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "g1_click_trash_full_document_ms": round(elapsed_ms, 2),
        "final_url": page.url,
        "note": "Full navigation to /trash via layout-global-nav; document load, not fragment swap.",
    }


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
    parser.add_argument("--path", default="/erp/dashboard", help="Path for scenario=navigation")
    parser.add_argument(
        "--order-id",
        type=int,
        default=int(os.environ.get("FOMS_STAGING_ORDER_ID", "2732")),
        help="Order id for primary_subordinate_roundtrip (default 2732 or env)",
    )
    parser.add_argument(
        "--scenario",
        choices=(
            "navigation",
            "erp_shell_tab_swap",
            "g1_document_nav",
            "primary_subordinate_roundtrip",
        ),
        default="navigation",
    )
    args = parser.parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not password:
        print("ERROR: Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD", file=sys.stderr)
        return 2

    origin = args.base.rstrip("/")

    out: dict[str, Any] = {"base": origin, "scenario": args.scenario}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="FOMS-EPT-B8-browser-metrics/1.0",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        _login(page, origin)

        if args.scenario == "navigation":
            out["path"] = args.path
            out["metrics"] = _scenario_navigation(page, origin, args.path)
        elif args.scenario == "erp_shell_tab_swap":
            out["metrics"] = _scenario_erp_shell_tab_swap(page, origin)
        elif args.scenario == "primary_subordinate_roundtrip":
            out["metrics"] = _scenario_primary_subordinate_roundtrip(
                page, origin, args.order_id
            )
        else:
            out["metrics"] = _scenario_g1_document_nav(page, origin)

        context.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
