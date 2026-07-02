#!/usr/bin/env python3
"""Aggregate L1/L2 stress JSON + compute p50/p95 for final report."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))

PATHS = [
    "/erp/dashboard?view=fragment",
    "/erp/measurement?view=fragment",
    "/erp/drawing-workbench?view=fragment",
    "/erp/shipment?view=fragment",
]


def p50(vals: list[int | float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[len(s) // 2]


def p95(vals: list[int | float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]


def winner(a: float, b: float, lower_better: bool = True) -> str:
    if abs(a - b) < 50:  # ms tie band / 0.05s for seconds scaled to ms compare elsewhere
        return "tie"
    if lower_better:
        return "deploy" if a < b else "production"
    return "production" if a < b else "deploy"


def load_l1_l2(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_comparison(data: dict) -> dict:
    dev = data["environments"]["deploy"]["layers"]
    prod = data["environments"]["production"]["layers"]
    regressions = []

    frag_dev = dev.get("fragment_ttfb", {}).get("paths", {})
    frag_prod = prod.get("fragment_ttfb", {}).get("paths", {})

    frag_compare = {}
    for p in PATHS:
        d_ms = (frag_dev.get(p, {}).get("warm_median_s") or 0) * 1000
        pr_ms = (frag_prod.get(p, {}).get("warm_median_s") or 0) * 1000
        frag_compare[p] = {"deploy_ms": round(d_ms), "production_ms": round(pr_ms)}
        if abs(d_ms - pr_ms) > 300:
            regressions.append(
                {
                    "layer": "fragment_ttfb",
                    "path": p,
                    "deploy_ms": round(d_ms),
                    "production_ms": round(pr_ms),
                    "delta_ms": round(d_ms - pr_ms),
                    "hypothesis": "infra-tail-latency" if max(d_ms, pr_ms) > 800 else "payload",
                    "next_step": "Compare B7 render-ms vs wall-clock; EXPLAIN if render high",
                }
            )

    tab_dev = [x["ms"] for x in dev.get("tab_stress", {}).get("tab_switch", [])]
    tab_prod = [x["ms"] for x in prod.get("tab_stress", {}).get("tab_switch", [])]

    tab_compare = {
        "deploy": {"p50_ms": round(p50(tab_dev)), "p95_ms": round(p95(tab_dev))},
        "production": {"p50_ms": round(p50(tab_prod)), "p95_ms": round(p95(tab_prod))},
    }

    aba = {
        "deploy": dev.get("tab_stress", {}).get("aba", {}),
        "production": prod.get("tab_stress", {}).get("aba", {}),
    }

    dcl = {
        "deploy": dev.get("tab_stress", {}).get("dcl_ms", {}),
        "production": prod.get("tab_stress", {}).get("dcl_ms", {}),
    }

    # Sort regressions by abs delta
    regressions.sort(key=lambda r: abs(r["delta_ms"]), reverse=True)

    # Verdict heuristics (L1/L2 only unless real_chrome merged)
    dev_tab_p95 = tab_compare["deploy"]["p95_ms"]
    prod_tab_p95 = tab_compare["production"]["p95_ms"]
    # Ignore headless cold-start outlier >10s for production tab p95 if p50 sane
    prod_tab_clean = [x for x in tab_prod if x < 10000]
    if prod_tab_clean:
        prod_tab_p95_adj = round(p95(prod_tab_clean))
    else:
        prod_tab_p95_adj = prod_tab_p95

    overall = winner(tab_compare["deploy"]["p50_ms"], tab_compare["production"]["p50_ms"])
    if prod_tab_p95_adj > 1500 and tab_compare["deploy"]["p95_ms"] < prod_tab_p95_adj:
        overall = "deploy"

    bottleneck = "infra-tail-latency"
    if tab_compare["deploy"]["p95_ms"] > 1500:
        bottleneck = "interaction-debt-or-fragment-fetch"
    for p in PATHS:
        d_ms = frag_compare[p]["deploy_ms"]
        if d_ms > 800:
            bottleneck = "query-scale-or-infra-tail"

    return {
        "fragment_ttfb_warm_median_ms": frag_compare,
        "tab_swap": tab_compare,
        "tab_swap_production_p95_ex_outlier": prod_tab_p95_adj,
        "aba": aba,
        "dcl_ms": dcl,
        "bytes_median": {
            p: {
                "deploy": frag_dev.get(p, {}).get("bytes_median"),
                "production": frag_prod.get(p, {}).get("bytes_median"),
            }
            for p in PATHS
        },
        "winner_by_layer": {
            "fragment_ttfb_median": winner(
                statistics.median([frag_compare[p]["deploy_ms"] for p in PATHS]),
                statistics.median([frag_compare[p]["production_ms"] for p in PATHS]),
            ),
            "tab_swap_p50_ms": winner(tab_compare["deploy"]["p50_ms"], tab_compare["production"]["p50_ms"]),
            "tab_swap_p95_ms": winner(tab_compare["deploy"]["p95_ms"], prod_tab_p95_adj),
        },
        "regressions": regressions,
        "verdict": {
            "overall_faster": overall,
            "primary_bottleneck_dimension": bottleneck,
            "safe_to_promote": False,
            "notes": "L3 Real Chrome pending for SW/full-refresh; L2 production outlier on first tab (headless cold).",
        },
    }


def merge_final(
    l1_l2_path: Path,
    real_chrome: dict | None = None,
    postgres: dict | None = None,
    perf_radar: dict | None = None,
) -> dict:
    base = load_l1_l2(l1_l2_path)
    comparison = build_comparison(base)
    run_id = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S%z")

    final = {
        "meta": {
            "run_id": run_id,
            "operator": "cursor-agent",
            "viewport": "1920x1080",
            "scenarios": ["A_tab_round", "B_aba", "C_full_refresh", "D_fragment_ttfb"],
            "source_l1_l2": str(l1_l2_path),
        },
        "environments": {
            "deploy": {
                "base_url": base["environments"]["deploy"]["base_url"],
                "layers": {
                    **base["environments"]["deploy"]["layers"],
                    "real_chrome": (real_chrome or {}).get("deploy", {}),
                    "postgres_top_queries": (postgres or {}).get("deploy", []),
                },
            },
            "production": {
                "base_url": base["environments"]["production"]["base_url"],
                "layers": {
                    **base["environments"]["production"]["layers"],
                    "real_chrome": (real_chrome or {}).get("production", {}),
                    "postgres_top_queries": (postgres or {}).get("production", []),
                },
            },
        },
        "comparison": comparison,
        "verdict": comparison["verdict"],
        "perf_radar": perf_radar,
    }
    return final


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/harness/evidence/stress-compare-2026-07-02T101644.json"
    rc_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    real_chrome = json.loads(rc_path.read_text(encoding="utf-8")) if rc_path and rc_path.exists() else None
    postgres = {"deploy": [], "production": [], "note": "pg_stat_statements not installed on MCP target"}
    perf_radar_path = ROOT / "docs/harness/evidence/perf-radar-latest.json"
    perf_radar = json.loads(perf_radar_path.read_text(encoding="utf-8")) if perf_radar_path.exists() else None

    final = merge_final(src, real_chrome, postgres, perf_radar)
    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    out = ROOT / f"docs/harness/evidence/stress-compare-{ts}-final.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
