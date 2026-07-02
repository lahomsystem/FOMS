#!/usr/bin/env python3
"""Real Chrome (headed Playwright channel=chrome) 9-primary x N rounds stress.

SW registers in headed Chrome (unlike headless). Output compatible with L3 evidence merge.
For strict cursor-ide-browser MCP runs, use round checkpoints via real_chrome_stress_checkpoint.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS
from tools.perf.browser_primary_9x10_stress import _p50, _p95, stress_env

KST = timezone(timedelta(hours=9))


def stress_env_real_chrome(base: str, user: str, pw: str, rounds: int = 10) -> dict:
    """Same as stress_env but headed Chrome for SW registration."""
    from playwright.sync_api import sync_playwright

    from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

    cookie, _ = fetch_session_cookie(base, user, pw)
    cookie_name = cookie.split("=", 1)[0]
    cookie_val = cookie.split("=", 1)[1].split(";")[0]
    domain = base.replace("https://", "").split("/")[0]

    swaps: list[dict] = []
    by_path: dict[str, list[int]] = {p: [] for p in ERP_PRIMARY_NAV_PATHS}
    sw_active = None
    nav = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_cookies(
            [{"name": cookie_name, "value": cookie_val, "domain": domain, "path": "/"}]
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
        sw_active = page.evaluate(
            """async () => {
              if (!('serviceWorker' in navigator)) return false;
              const reg = await navigator.serviceWorker.getRegistration();
              return !!(reg && reg.active);
            }"""
        )

        idx = 0
        pause_s = 0.3
        for rnd in range(1, rounds + 1):
            for path in ERP_PRIMARY_NAV_PATHS:
                idx += 1
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
                swaps.append({"i": idx, "round": rnd, "path": path, "ms": ms})
                by_path[path].append(ms)
                time.sleep(pause_s)

        browser.close()

    all_ms = [s["ms"] for s in swaps]
    per_path = {
        p: {"p50_ms": _p50(v), "p95_ms": _p95(v), "max_ms": max(v), "samples": len(v)}
        for p, v in by_path.items()
    }
    return {
        "base": base,
        "rounds": rounds,
        "primary_count": len(ERP_PRIMARY_NAV_PATHS),
        "total_swaps": len(swaps),
        "dcl_ms": nav,
        "sw_active": sw_active,
        "summary": {
            "all_p50_ms": _p50(all_ms),
            "all_p95_ms": _p95(all_ms),
            "all_max_ms": max(all_ms),
        },
        "per_path": per_path,
        "swaps": swaps,
    }


def main() -> None:
    user = os.environ.get("FOMS_STAGING_USERNAME", "")
    pw = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD")

    rounds = int(os.environ.get("FOMS_STRESS_ROUNDS", "10"))
    bases = sys.argv[1:] or [
        "https://lahom-dev.up.railway.app",
        "https://lahom-production.up.railway.app",
    ]

    results = []
    for base in bases:
        results.append(stress_env_real_chrome(base, user, pw, rounds=rounds))

    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    out_path = ROOT / f"docs/harness/evidence/stress-9primary-x{rounds}-real-chrome-{ts}.json"
    payload = {
        "meta": {
            "run_id": datetime.now(KST).isoformat(),
            "rounds": rounds,
            "primary_paths": list(ERP_PRIMARY_NAV_PATHS),
            "pause_ms": 300,
            "tool": "browser_primary_9x10_real_chrome.py (headed Chrome, SW valid)",
            "note": "L3 Real Chrome — headed Playwright channel=chrome",
        },
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(out_path), "summary": [
        {"base": r["base"], "sw_active": r.get("sw_active"), **r["summary"]} for r in results
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
