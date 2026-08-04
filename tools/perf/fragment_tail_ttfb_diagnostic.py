#!/usr/bin/env python3
"""Deploy construction/history fragment tail — 20-round TTFB vs total diagnostic."""
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

from tools.harness.ept_b8_staging_session_from_login import fetch_session_cookie

KST = timezone(timedelta(hours=9))
PATHS = [
    "/erp/construction/dashboard?view=fragment",
    "/erp/history/?view=fragment",
]
HEAD = {
    "X-FOMS-ERP-SHELL": "1",
    "Accept": "text/html",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def measure_round(session, base: str, path: str) -> dict:
    """Single fragment GET with TTFB proxy (response elapsed) and total time."""
    import requests

    t0 = time.perf_counter()
    r = session.get(base + path, headers=HEAD, timeout=120, stream=True)
    t_headers = time.perf_counter()
    body = r.content
    t_total = time.perf_counter()
    return {
        "path": path,
        "status": r.status_code,
        "ttfb_ms": round((t_headers - t0) * 1000),
        "total_ms": round((t_total - t0) * 1000),
        "transfer_ms": round((t_total - t_headers) * 1000),
        "bytes": len(body),
        "b7_render_ms": r.headers.get("X-FOMS-EPT-B7-RENDER-MS"),
        "erp_fragment": r.headers.get("X-FOMS-ERP-FRAGMENT"),
        "fragment_tier": r.headers.get("X-FOMS-ERP-FRAGMENT-TIER"),
    }


def run_env(base: str, user: str, pw: str, rounds: int = 20) -> dict:
    """Run sequential fragment GETs for tail paths."""
    import requests

    cookie, _ = fetch_session_cookie(base, user, pw)
    s = requests.Session()
    s.headers["Cookie"] = cookie
    label = "deploy" if "dev" in base else "production"
    rows: list[dict] = []
    for path in PATHS:
        for i in range(1, rounds + 1):
            row = measure_round(s, base, path)
            row["round"] = i
            row["env"] = label
            rows.append(row)
            time.sleep(0.3)
    by_path: dict[str, list[dict]] = {}
    for row in rows:
        by_path.setdefault(row["path"], []).append(row)
    summary = {}
    for path, items in by_path.items():
        warm = items[2:] if len(items) > 2 else items
        totals = sorted(x["total_ms"] for x in warm)
        ttfbs = sorted(x["ttfb_ms"] for x in warm)
        summary[path] = {
            "med_total_ms": int(statistics.median(totals)),
            "p95_total_ms": int(totals[int(len(totals) * 0.95) - 1]),
            "med_ttfb_ms": int(statistics.median(ttfbs)),
            "med_transfer_ms": int(statistics.median(x["transfer_ms"] for x in warm)),
            "med_bytes": int(statistics.median(x["bytes"] for x in warm)),
            "b7_present_count": sum(1 for x in warm if x["b7_render_ms"]),
        }
    return {"env": label, "base": base, "rounds": rounds, "rows": rows, "summary": summary}


def main() -> None:
    user = os.environ.get("FOMS_STAGING_USERNAME", "")
    pw = os.environ.get("FOMS_STAGING_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD")

    bases = sys.argv[1:] or ["https://lahom-dev.up.railway.app"]
    rounds = int(os.environ.get("FRAGMENT_TAIL_ROUNDS", "20"))
    out = {"meta": {"rounds": rounds, "paths": PATHS}, "environments": []}
    for base in bases:
        out["environments"].append(run_env(base, user, pw, rounds=rounds))

    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    fp = ROOT / f"docs/harness/evidence/fragment-tail-ttfb-{ts}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(fp), "summary": [e["summary"] for e in out["environments"]]}, indent=2))


if __name__ == "__main__":
    main()
