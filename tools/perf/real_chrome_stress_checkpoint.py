#!/usr/bin/env python3
"""Merge Real Chrome ERP 9-primary stress round checkpoints into final JSON."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
EVIDENCE = ROOT / "docs" / "harness" / "evidence"


def _p50(vals: list[int]) -> int:
    s = sorted(vals)
    return int(s[len(s) // 2])


def _p95(vals: list[int]) -> int:
    s = sorted(vals)
    return int(s[max(0, int(len(s) * 0.95) - 1)])


def merge_checkpoints(glob_pat: str, out_name: str) -> Path:
    """Load round-*.json checkpoints and emit summary evidence file."""
    files = sorted(EVIDENCE.glob(glob_pat))
    if not files:
        raise SystemExit(f"No checkpoints matching {glob_pat}")

    by_env: dict[str, dict] = {}
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        label = data["env"]
        by_env.setdefault(label, {"base": data["base"], "swaps": [], "meta": data.get("meta", {})})
        by_env[label]["swaps"].extend(data.get("swaps", []))

    results = []
    for label, block in by_env.items():
        swaps = block["swaps"]
        by_path: dict[str, list[int]] = {}
        for s in swaps:
            by_path.setdefault(s["path"], []).append(s["ms"])
        all_ms = [s["ms"] for s in swaps]
        per_path = {
            p: {"p50_ms": _p50(v), "p95_ms": _p95(v), "max_ms": max(v), "samples": len(v)}
            for p, v in by_path.items()
        }
        results.append(
            {
                "env": label,
                "base": block["base"],
                "rounds": max(s.get("round", 0) for s in swaps) if swaps else 0,
                "total_swaps": len(swaps),
                "summary": {
                    "all_p50_ms": _p50(all_ms),
                    "all_p95_ms": _p95(all_ms),
                    "all_max_ms": max(all_ms) if all_ms else 0,
                },
                "per_path": per_path,
                "swaps": swaps,
                "sw_active": block["meta"].get("sw_active"),
                "dcl_ms": block["meta"].get("dcl_ms"),
            }
        )

    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    out = EVIDENCE / out_name.replace("{ts}", ts)
    payload = {
        "meta": {
            "run_id": datetime.now(KST).isoformat(),
            "tool": "cursor-ide-browser CDP Real Chrome",
            "checkpoints": [str(f) for f in files],
            "note": "L3 Real Chrome 9-primary x10; SW verdict valid",
        },
        "results": results,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(out), "summary": [r["summary"] for r in results]}, indent=2))
    return out


def write_round(env: str, base: str, round_num: int, swaps: list[dict], meta: dict | None = None) -> Path:
    """Write one round checkpoint (called after each MCP round)."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y-%m-%dT%H%M%S")
    fp = EVIDENCE / f"real-chrome-{env}-r{round_num:02d}-{ts}.json"
    fp.write_text(
        json.dumps(
            {"env": env, "base": base, "round": round_num, "swaps": swaps, "meta": meta or {}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return fp


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: merge <glob> <out-name-with-{ts}>")
    merge_checkpoints(sys.argv[1], sys.argv[2])
