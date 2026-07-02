#!/usr/bin/env python3
"""ERP 9-primary shell tabs × N rounds — deploy vs production swap stress."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS

KST = timezone(timedelta(hours=9))
PAUSE_S = 0.3


def _p50(vals: list[int]) -> int:
    s = sorted(vals)
    return int(s[len(s) // 2])


def _p95(vals: list[int]) -> int:
    s = sorted(vals)
    return int(s[max(0, int(len(s) * 0.95) - 1)])


def stress_env(base: str, user: str, pw: str, rounds: int = 10) -> dict:
    """Run rounds × len(ERP_PRIMARY_NAV_PATHS) shell tab swaps via Playwright."""
    from playwright.sync_api import sync_playwright

    from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

    cookie, _ = fetch_session_cookie(base, user, pw)
    cookie_name = cookie.split("=", 1)[0]
    cookie_val = cookie.split("=", 1)[1].split(";")[0]

    swaps: list[dict] = []
    by_path: dict[str, list[int]] = {p: [] for p in ERP_PRIMARY_NAV_PATHS}

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

        idx = 0
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
                time.sleep(PAUSE_S)

        browser.close()

    per_path = {
        p: {"p50_ms": _p50(v), "p95_ms": _p95(v), "max_ms": max(v), "samples": len(v)}
        for p, v in by_path.items()
    }
    all_ms = [s["ms"] for s in swaps]
    return {
        "base": base,
        "rounds": rounds,
        "primary_count": len(ERP_PRIMARY_NAV_PATHS),
        "total_swaps": len(swaps),
        "dcl_ms": nav,
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

    results = [stress_env(b, user, pw, rounds=rounds) for b in bases]

    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    out_path = ROOT / f"docs/harness/evidence/stress-9primary-x{rounds}-{ts}.json"
    payload = {
        "meta": {
            "run_id": datetime.now(KST).isoformat(),
            "rounds": rounds,
            "primary_paths": list(ERP_PRIMARY_NAV_PATHS),
            "pause_ms": int(PAUSE_S * 1000),
            "tool": "browser_primary_9x10_stress.py (Playwright headless)",
            "note": "Swap ms = client shell; SW verdict requires Real Chrome separately",
        },
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(out_path), "summary": [
        {"base": r["base"], **r["summary"]} for r in results
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
