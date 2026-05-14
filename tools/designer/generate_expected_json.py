"""FOMS Brain PG-B2 — Gemini Expected JSON Draft Generator.

Generates AI draft expected extraction JSON for a fixture drawing.
The draft MUST be reviewed and approved by a human before it becomes
the scorecard baseline.

Usage:
  python tools/designer/generate_expected_json.py --fixture-id wrd_001
  python tools/designer/generate_expected_json.py --fixture-id wrd_001 --force  # overwrite existing draft
  python tools/designer/generate_expected_json.py --all-available  # draft all available fixtures

Requirements:
  GEMINI_API_KEY environment variable must be set.
  The fixture file must be in 'available' status in the manifest.

Windows PowerShell:
  $env:GEMINI_API_KEY = "your-key"
  python tools/designer/generate_expected_json.py --fixture-id wrd_001
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
EXPECTED_DIR = MANIFEST_PATH.parent / "expected_extractions"

sys.path.insert(0, str(ROOT))


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(data: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_DRAFT_PROMPT = """당신은 한국 가구 도면 전문 데이터 추출 AI입니다.
제공된 가구 도면 이미지를 분석하여 아래 JSON 형식으로 정확하게 정보를 추출하세요.
이 결과는 사용자 검토 후 승인되는 AI 초안입니다.

규칙:
1. 모든 치수는 밀리미터(mm) 단위입니다.
2. 도면에서 명확히 읽을 수 있는 값만 추출하세요. 추측하지 마세요.
3. 읽을 수 없는 필드는 null로 남기거나 빈 배열로 두세요.
4. 고객명/전화/주소는 raw 값 그대로 추출합니다 (내부 사용, 외부 전송 금지).
5. parts_table의 code는 [SR], [EP], [DOOR], [마이다], [옷봉], 보조목 등을 그대로 추출합니다.

다음 JSON 구조로만 응답하세요 (JSON 외 텍스트 금지):
{
  "drawing_id": "<fixture_id>",
  "page_no": 1,
  "approval_status": "draft",
  "approved_by": null,
  "approved_at": null,
  "customer_name": null,
  "product_name": null,
  "site_size": {
    "width_mm": null,
    "height_mm": null,
    "depth_mm": null,
    "notes": ""
  },
  "furniture_type": "wardrobe",
  "module_widths_mm": [],
  "parts_table": [
    {"code": "[SR]", "description": "선반", "quantity": 0, "note": ""}
  ],
  "dimension_candidates": [
    {"value_mm": 0, "axis": "width", "view": "front", "source": "drawing"}
  ],
  "views": ["front"],
  "drawing_style": "technical",
  "notes": "",
  "color": null,
  "hardware": null
}"""


def generate_draft(fixture: dict, force: bool = False) -> dict | None:
    """Generate Gemini AI draft expected JSON for a fixture.

    Returns:
        Generated expected JSON dict, or None on failure.
    """
    fixture_id = fixture["id"]
    file_path = ROOT / fixture.get("file_path", "")
    expected_path = ROOT / fixture.get("expected_json_path", "")

    if not file_path.exists():
        print(f"[SKIP] {fixture_id}: file not found at {file_path}")
        return None

    if expected_path.exists() and not force:
        # Check if already approved — don't overwrite
        with open(expected_path, encoding="utf-8") as f:
            existing = json.load(f)
        if existing.get("approval_status") == "approved":
            print(f"[SKIP] {fixture_id}: already approved — use --force to overwrite")
            return None
        print(f"[INFO] {fixture_id}: existing draft found, overwriting with --force")

    try:
        from foms.services.designer.gemini_provider import (
            extract_from_image_path,
            GeminiProviderError,
            GeminiAPIKeyMissing,
        )
    except ImportError:
        print("[ERROR] Cannot import gemini_provider. "
              "Ensure you're running from the FOMS project root.", file=sys.stderr)
        return None

    if not os.environ.get("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        print("  PowerShell: $env:GEMINI_API_KEY = 'your-key'", file=sys.stderr)
        return None

    print(f"[RUN] {fixture_id}: extracting from {file_path.name}...")
    try:
        raw = extract_from_image_path(file_path)
    except GeminiAPIKeyMissing as e:
        print(f"[ERROR] API key missing: {e}", file=sys.stderr)
        return None
    except GeminiProviderError as e:
        print(f"[ERROR] Gemini extraction failed for {fixture_id}: {e}", file=sys.stderr)
        return None

    # Build expected JSON structure from Gemini output
    metrics = raw.pop("_metrics", {})
    customer_info = raw.get("extracted_params", {}).pop("_customer_info", {}) or {}
    parts_table = raw.get("extracted_params", {}).pop("_parts_table", []) or []
    drawing_meta = raw.get("extracted_params", {}).pop("_drawing_meta", {}) or {}
    extracted_params = raw.get("extracted_params", {})
    gemini_parts = raw.get("parts_table", parts_table) or []
    gemini_customer = raw.get("customer_info", customer_info) or {}
    gemini_meta = raw.get("drawing_meta", drawing_meta) or {}

    expected_json = {
        "drawing_id": fixture_id,
        "page_no": gemini_meta.get("page_number") or 1,
        "approval_status": "draft",
        "approved_by": None,
        "approved_at": None,
        "_ai_draft_model": metrics.get("model", "unknown"),
        "_ai_draft_latency_ms": metrics.get("latency_ms", 0),
        "_ai_draft_cost_usd": metrics.get("cost_usd", 0.0),
        "customer_name": gemini_customer.get("customer_name"),
        "product_name": gemini_customer.get("product_name"),
        "site_size": {
            "width_mm": extracted_params.get("width"),
            "height_mm": extracted_params.get("height"),
            "depth_mm": extracted_params.get("depth"),
            "notes": ""
        },
        "furniture_type": raw.get("furniture_type", "wardrobe"),
        "module_widths_mm": extracted_params.get("module_widths", []) or [],
        "parts_table": [
            {
                "code": p.get("code", ""),
                "description": p.get("description", ""),
                "quantity": p.get("quantity", 0),
                "note": ""
            }
            for p in gemini_parts
        ],
        "dimension_candidates": [
            {"value_mm": extracted_params.get("width"), "axis": "width", "view": "front", "source": "drawing"},
            {"value_mm": extracted_params.get("height"), "axis": "height", "view": "front", "source": "drawing"},
            {"value_mm": extracted_params.get("depth"), "axis": "depth", "view": "side", "source": "drawing"},
        ],
        "views": [gemini_meta.get("view_type") or "front"],
        "drawing_style": gemini_meta.get("drawing_style") or "technical",
        "notes": raw.get("_notes", ""),
        "color": gemini_customer.get("color"),
        "hardware": None,
        "unresolved_fields": raw.get("unresolved_fields", []),
        "confidence": raw.get("confidence", 0.0),
    }

    # Remove null dimension candidates
    expected_json["dimension_candidates"] = [
        d for d in expected_json["dimension_candidates"] if d.get("value_mm") is not None
    ]

    # Save draft
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    with open(expected_path, "w", encoding="utf-8") as f:
        json.dump(expected_json, f, ensure_ascii=False, indent=2)

    print(f"[OK] {fixture_id}: draft saved → {expected_path.name}")
    print(f"     furniture_type={expected_json['furniture_type']} "
          f"confidence={expected_json['confidence']:.2f} "
          f"cost=${metrics.get('cost_usd', 0):.5f} "
          f"latency={metrics.get('latency_ms', 0)}ms")
    print(f"     ACTION: Review and approve: "
          f"python tools/designer/build_drawing_fixture_manifest.py approve --fixture-id {fixture_id}")

    return expected_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Gemini AI draft expected JSON for drawing fixtures"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture-id", help="Single fixture ID to process")
    group.add_argument("--all-available", action="store_true",
                       help="Process all fixtures with file_status=available")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing draft (NOT approved)")
    args = parser.parse_args()

    data = load_manifest()
    fixtures = data.get("fixtures", [])

    if args.fixture_id:
        fixture = next((f for f in fixtures if f["id"] == args.fixture_id), None)
        if not fixture:
            print(f"[ERROR] Fixture '{args.fixture_id}' not found. "
                  f"Available: {[f['id'] for f in fixtures]}", file=sys.stderr)
            sys.exit(1)
        generate_draft(fixture, force=args.force)
    else:
        # All available fixtures
        available = [f for f in fixtures if f.get("file_status") == "available"]
        if not available:
            print("[INFO] No available fixtures found. "
                  "Use 'ingest' command to register drawing files first.")
            return
        print(f"[RUN] Processing {len(available)} available fixtures...")
        success = 0
        for fixture in available:
            result = generate_draft(fixture, force=args.force)
            if result:
                success += 1
        print(f"\n[DONE] {success}/{len(available)} drafts generated.")
        print("Review and approve each draft before using as scorecard baseline.")


if __name__ == "__main__":
    main()
