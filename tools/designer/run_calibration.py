"""FOMS Brain Enhancement — Template Calibration CLI.

Runs the extraction scorecard against available fixture drawings.
Reports W/D/H accuracy, parts table recall, and per-fixture results.

Usage:
  python tools/designer/run_calibration.py
  python tools/designer/run_calibration.py --output docs/plans/calibration-2026-05.json
  python tools/designer/run_calibration.py --dry-run  # count fixtures without running

Requirements:
  GEMINI_API_KEY environment variable (for real extraction)
  OR DESIGNER_FAKE_VISION=1 (for fake extraction)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

MANIFEST_PATH = ROOT / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
EXPECTED_DIR = MANIFEST_PATH.parent / "expected_extractions"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_calibration(dry_run: bool = False, output: Path | None = None) -> dict:
    """Run calibration scorecard over available fixtures."""
    manifest = load_manifest()
    fixtures = manifest.get("fixtures", [])

    available = [
        f for f in fixtures
        if f.get("file_status") == "available"
    ]
    approved = [
        f for f in available
        if f.get("approval_status") == "approved"
        and (EXPECTED_DIR / f"{f['id']}_expected.json").exists()
    ]

    print(f"[CALIBRATION] Total fixtures: {len(fixtures)}")
    print(f"[CALIBRATION] Available (files present): {len(available)}")
    print(f"[CALIBRATION] Approved (expected JSON approved): {len(approved)}")
    print(f"[CALIBRATION] Pending (no file/approval): {len(fixtures) - len(available)}")

    if dry_run:
        print("\n[DRY RUN] Would run calibration on", len(approved), "fixtures.")
        return {"dry_run": True, "available": len(available), "approved": len(approved)}

    if not approved:
        print("\n[CALIBRATION] No approved fixtures to calibrate against.")
        print("  → Upload drawings via /wdplanner-v2 and approve expected JSONs first.")
        return {"total": 0, "message": "no approved fixtures"}

    # Import scorecard
    from foms.services.designer.extraction_scorecard import (
        run_scorecard_from_manifest, ScorecardReport,
    )
    from foms.services.designer.gemini_provider import extract_from_image_path

    def extractor(image_path: str) -> dict:
        return extract_from_image_path(image_path)

    print(f"\n[CALIBRATION] Running scorecard on {len(approved)} approved fixtures...")
    t0 = time.monotonic()
    report = run_scorecard_from_manifest(MANIFEST_PATH, extractor)
    elapsed = time.monotonic() - t0

    summary = report.to_dict()["summary"]
    summary["elapsed_s"] = round(elapsed, 1)
    summary["run_at"] = datetime.now(timezone.utc).isoformat()
    summary["targets"] = {"wdh_accuracy_min": 0.95, "parts_recall_min": 0.90}
    summary["target_wdh_met"] = report.wdh_gate_pass
    summary["target_parts_met"] = report.parts_gate_pass

    print("\n=== CALIBRATION RESULTS ===")
    print(f"  Fixtures tested:     {summary['total_fixtures']}")
    print(f"  Errors:              {summary['error_count']}")
    print(f"  W/D/H accuracy:      {summary['mean_wdh_accuracy']:.1%}  {'✅' if summary['target_wdh_met'] else '❌'} (target ≥95%)")
    print(f"  Parts recall:        {summary['mean_parts_recall']:.1%}  {'✅' if summary['target_parts_met'] else '❌'} (target ≥90%)")
    print(f"  Overall score:       {summary['mean_overall_score']:.1%}")
    print(f"  Total cost:          ${summary['total_cost_usd']:.4f}")
    print(f"  Latency p95:         {summary['latency_p95_ms']}ms")
    print(f"  Elapsed:             {summary['elapsed_s']}s")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        full = report.to_dict()
        full["summary"] = summary
        with open(output, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        print(f"\n[CALIBRATION] Report saved → {output}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="FOMS Brain Template Calibration")
    parser.add_argument("--output", help="Save JSON report to this path")
    parser.add_argument("--dry-run", action="store_true", help="Count fixtures without running")
    args = parser.parse_args()

    output = Path(args.output) if args.output else None
    result = run_calibration(dry_run=args.dry_run, output=output)
    print("\nSummary:", json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
