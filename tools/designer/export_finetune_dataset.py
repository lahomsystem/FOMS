"""FOMS Brain PG-L6 — Fine-Tuning Dataset Export CLI.

Exports approved, PII-free design cases and correction patterns
as JSONL files suitable for fine-tuning or evaluation harness.

Contract:
- Only approved design cases (approved_at is not null) are exported.
- Raw customer_name/phone/address are NEVER included.
- Each row includes source IDs for audit traceability.
- Export format: JSONL (one JSON object per line).

Usage:
  python tools/designer/export_finetune_dataset.py --output dataset.jsonl
  python tools/designer/export_finetune_dataset.py --type extraction --min-quality 0.8
  python tools/designer/export_finetune_dataset.py --dry-run

Windows PowerShell:
  python tools/designer/export_finetune_dataset.py --output export\foms_brain_v1.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

_PII_KEYS = frozenset({
    "customer_name", "phone", "address", "customer_phone",
    "customer_address", "client_name",
})

EXPORT_TYPES = ("extraction", "design_case", "correction_pattern", "all")


# ──────────────────────────────────────────────────────────
# Row builders
# ──────────────────────────────────────────────────────────

def _strip_pii(obj: dict) -> dict:
    """Recursively remove PII keys from a dict."""
    import copy
    clean = copy.deepcopy(obj)
    for k in list(clean.keys()):
        if k in _PII_KEYS:
            del clean[k]
        elif isinstance(clean[k], dict):
            clean[k] = _strip_pii(clean[k])
    return clean


def build_extraction_rows(min_quality: float = 0.5) -> list[dict]:
    """Build fine-tuning rows from approved drawing extractions."""
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerDrawingExtraction
        from sqlalchemy import and_

        rows = []
        extractions = db_session.query(DesignerDrawingExtraction).filter(
            and_(
                DesignerDrawingExtraction.status == "approved",
                DesignerDrawingExtraction.approved_at.isnot(None),
            )
        ).all()

        for ext in extractions:
            parsed = _strip_pii(ext.parsed_json or {})
            conf_data = ext.confidence_json or {}
            overall_conf = conf_data.get("confidence", 0.0) if isinstance(conf_data, dict) else 0.0

            if overall_conf < min_quality:
                continue

            rows.append({
                "type": "extraction",
                "source_id": ext.id,
                "page_id": ext.page_id,
                "extractor_version": ext.extractor_version,
                "input_description": "도면 이미지 (이미지 URL은 보안상 제외)",
                "output": parsed,
                "confidence": overall_conf,
                "model_name": ext.model_name,
                "approved_at": ext.approved_at.isoformat() if ext.approved_at else None,
            })
        return rows

    except Exception as exc:
        print(f"[WARN] extraction export failed: {exc}", file=sys.stderr)
        return []


def build_design_case_rows(min_quality: float = 0.5) -> list[dict]:
    """Build fine-tuning rows from approved design cases."""
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerDesignCase

        rows = []
        cases = db_session.query(DesignerDesignCase).filter(
            DesignerDesignCase.approved_at.isnot(None)
        ).all()

        for case in cases:
            if case.source_quality_score < min_quality:
                continue

            rows.append({
                "type": "design_case",
                "source_id": case.id,
                "furniture_type": case.furniture_type,
                "product_name": case.product_name,
                "dimensions": {
                    "width_mm": case.width_mm,
                    "height_mm": case.height_mm,
                    "depth_mm": case.depth_mm,
                    "module_count": case.module_count,
                },
                "design_graph": case.design_graph_json,
                "bom": case.bom_json,
                "options": _strip_pii(case.options_json or {}),
                "tags": case.tags_json or [],
                "source_quality_score": case.source_quality_score,
                "approved_at": case.approved_at.isoformat() if case.approved_at else None,
            })
        return rows

    except Exception as exc:
        print(f"[WARN] design_case export failed: {exc}", file=sys.stderr)
        return []


def build_correction_pattern_rows() -> list[dict]:
    """Build correction pattern rows for training AI to avoid common mistakes."""
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerRuleCandidate
        from sqlalchemy import or_

        rows = []
        candidates = db_session.query(DesignerRuleCandidate).filter(
            or_(
                DesignerRuleCandidate.status == "approved",
                DesignerRuleCandidate.status == "promoted",
            )
        ).all()

        for rc in candidates:
            rj = rc.replay_report_json or {}
            if rj.get("fail_count", 1) > 0:
                continue
            cj = rc.candidate_json or {}
            rows.append({
                "type": "correction_pattern",
                "source_id": rc.id,
                "rule_hint": cj.get("rule_hint", ""),
                "evidence_count": cj.get("correction_count", 0),
                "sample_deltas": cj.get("sample_deltas", [])[:3],
                "evidence_strength": cj.get("evidence_strength", 0.0),
                "replay_passed": True,
                "status": rc.status,
            })
        return rows

    except Exception as exc:
        print(f"[WARN] correction_pattern export failed: {exc}", file=sys.stderr)
        return []


# ──────────────────────────────────────────────────────────
# Export runner
# ──────────────────────────────────────────────────────────

def export_dataset(
    output_path: Path,
    export_type: str = "all",
    min_quality: float = 0.5,
    dry_run: bool = False,
) -> dict:
    """Export approved, PII-free dataset to JSONL.

    Args:
        output_path: Output JSONL file path.
        export_type: "extraction" | "design_case" | "correction_pattern" | "all"
        min_quality: Minimum quality score threshold.
        dry_run: If True, show stats without writing file.

    Returns:
        Summary dict.
    """
    rows: list[dict] = []

    if export_type in ("extraction", "all"):
        ext_rows = build_extraction_rows(min_quality)
        rows.extend(ext_rows)
        print(f"[EXPORT] extraction rows: {len(ext_rows)}")

    if export_type in ("design_case", "all"):
        case_rows = build_design_case_rows(min_quality)
        rows.extend(case_rows)
        print(f"[EXPORT] design_case rows: {len(case_rows)}")

    if export_type in ("correction_pattern", "all"):
        corr_rows = build_correction_pattern_rows()
        rows.extend(corr_rows)
        print(f"[EXPORT] correction_pattern rows: {len(corr_rows)}")

    # Final PII safety scan
    clean_rows = []
    pii_blocked = 0
    for row in rows:
        row_str = json.dumps(row, ensure_ascii=False)
        pii_found = any(k in row_str for k in _PII_KEYS)
        if pii_found:
            pii_blocked += 1
            print(f"[WARN] PII found in row, skipping: {row.get('source_id')}", file=sys.stderr)
            continue
        clean_rows.append(row)

    summary = {
        "total_rows": len(clean_rows),
        "pii_blocked": pii_blocked,
        "export_type": export_type,
        "min_quality": min_quality,
        "output_path": str(output_path),
        "dry_run": dry_run,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"\n[DRY RUN] Would export {len(clean_rows)} rows to {output_path}")
        print(f"[DRY RUN] PII blocked: {pii_blocked} rows")
        return summary

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for row in clean_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n[OK] Exported {len(clean_rows)} rows to {output_path}")
    return summary


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FOMS Brain Fine-Tuning Dataset Export"
    )
    parser.add_argument("--output", default="export/foms_brain_dataset.jsonl",
                        help="Output JSONL file path")
    parser.add_argument("--type", dest="export_type", default="all",
                        choices=EXPORT_TYPES, help="Export type")
    parser.add_argument("--min-quality", type=float, default=0.5,
                        help="Minimum quality score (0.0-1.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show stats without writing file")
    args = parser.parse_args()

    summary = export_dataset(
        output_path=Path(args.output),
        export_type=args.export_type,
        min_quality=args.min_quality,
        dry_run=args.dry_run,
    )
    print(f"\nSummary: {json.dumps(summary, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
