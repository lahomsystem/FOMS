"""FOMS Brain PG-B2 — Drawing Fixture Manifest CLI.

Manages the drawing fixture corpus for extraction accuracy testing.

Usage:
  python tools/designer/build_drawing_fixture_manifest.py status
  python tools/designer/build_drawing_fixture_manifest.py ingest --file path/to/drawing.jpg --id wrd_001
  python tools/designer/build_drawing_fixture_manifest.py approve --fixture-id wrd_001
  python tools/designer/build_drawing_fixture_manifest.py reject --fixture-id wrd_001 --reason "치수 오류"
  python tools/designer/build_drawing_fixture_manifest.py list --status pending
  python tools/designer/build_drawing_fixture_manifest.py validate

Windows PowerShell:
  python tools/designer/build_drawing_fixture_manifest.py status
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
DRAWINGS_DIR = MANIFEST_PATH.parent
EXPECTED_DIR = DRAWINGS_DIR / "expected_extractions"
SCHEMA_PATH = EXPECTED_DIR / "_SCHEMA.json"

VALID_FURNITURE_TYPES = {
    "wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"
}
VALID_APPROVAL_STATUSES = {"draft", "pending_approval", "approved", "rejected"}
VALID_FILE_STATUSES = {"pending", "available", "missing"}


# ── Manifest IO ────────────────────────────────────────────

def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(data: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Manifest saved: {MANIFEST_PATH}")


# ── Commands ───────────────────────────────────────────────

def cmd_status(args) -> None:
    """Show fixture corpus status summary."""
    data = load_manifest()
    fixtures = data.get("fixtures", [])

    total = len(fixtures)
    by_status = {}
    by_file = {}
    by_type = {}

    for f in fixtures:
        ast = f.get("approval_status", "draft")
        fst = f.get("file_status", "pending")
        ft = f.get("furniture_type_expected", "unknown")
        by_status[ast] = by_status.get(ast, 0) + 1
        by_file[fst] = by_file.get(fst, 0) + 1
        by_type[ft] = by_type.get(ft, 0) + 1

    print(f"\n=== Fixture Corpus Status ===")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Total fixtures: {total}")
    print(f"\nFile status:")
    for k, v in sorted(by_file.items()):
        print(f"  {k}: {v}")
    print(f"\nApproval status:")
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")
    print(f"\nBy furniture type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")

    # Gate check
    approved_count = by_status.get("approved", 0)
    available_count = by_file.get("available", 0)
    print(f"\nProduct gates:")
    print(f"  Corpus v1 (17 approved): {approved_count}/17 {'[PASS]' if approved_count >= 17 else '[PENDING]'}")
    print(f"  Files available: {available_count}/17 {'[PASS]' if available_count >= 17 else '[PENDING]'}")


def cmd_ingest(args) -> None:
    """Register a drawing file into the fixture corpus."""
    fixture_id = args.fixture_id
    file_path = Path(args.file).resolve()

    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    data = load_manifest()
    fixtures = data.get("fixtures", [])

    # Find fixture entry
    fixture = next((f for f in fixtures if f["id"] == fixture_id), None)
    if not fixture:
        print(f"[ERROR] Fixture ID '{fixture_id}' not found in manifest. "
              f"Available: {[f['id'] for f in fixtures]}", file=sys.stderr)
        sys.exit(1)

    # Copy file to drawings directory
    suffix = file_path.suffix.lower()
    dest = DRAWINGS_DIR / f"{fixture_id}{suffix}"
    shutil.copy2(file_path, dest)
    print(f"[OK] File copied: {dest}")

    # Update manifest entry
    fixture["file_path"] = str(dest.relative_to(ROOT)).replace("\\", "/")
    fixture["file_status"] = "available"
    if fixture.get("approval_status") == "draft":
        fixture["approval_status"] = "pending_approval"

    save_manifest(data)
    print(f"[OK] Fixture '{fixture_id}' registered. Run generate_expected_json.py to create AI draft.")


def cmd_approve(args) -> None:
    """Mark a fixture as approved by user."""
    fixture_id = args.fixture_id
    data = load_manifest()
    fixtures = data.get("fixtures", [])

    fixture = next((f for f in fixtures if f["id"] == fixture_id), None)
    if not fixture:
        print(f"[ERROR] Fixture '{fixture_id}' not found.", file=sys.stderr)
        sys.exit(1)

    # Check expected JSON exists
    expected_path = ROOT / fixture.get("expected_json_path", "")
    if not expected_path.exists():
        print(f"[ERROR] Expected JSON not found: {expected_path}. "
              "Run generate_expected_json.py first.", file=sys.stderr)
        sys.exit(1)

    # Update expected JSON approval status
    with open(expected_path, encoding="utf-8") as f:
        ej = json.load(f)
    ej["approval_status"] = "approved"
    ej["approved_by"] = args.user if hasattr(args, "user") and args.user else "user"
    ej["approved_at"] = datetime.now(timezone.utc).isoformat()
    with open(expected_path, "w", encoding="utf-8") as f:
        json.dump(ej, f, ensure_ascii=False, indent=2)

    # Update manifest
    fixture["approval_status"] = "approved"
    # Update corpus plan counts
    if "corpus_plan" in data:
        for v_key in ["v0", "v1"]:
            if v_key in data["corpus_plan"]:
                approved = sum(
                    1 for ff in fixtures if ff.get("approval_status") == "approved"
                )
                data["corpus_plan"][v_key]["approved"] = approved

    save_manifest(data)
    print(f"[OK] Fixture '{fixture_id}' approved.")


def cmd_reject(args) -> None:
    """Mark a fixture as rejected (needs correction)."""
    fixture_id = args.fixture_id
    reason = getattr(args, "reason", "") or ""
    data = load_manifest()
    fixtures = data.get("fixtures", [])

    fixture = next((f for f in fixtures if f["id"] == fixture_id), None)
    if not fixture:
        print(f"[ERROR] Fixture '{fixture_id}' not found.", file=sys.stderr)
        sys.exit(1)

    fixture["approval_status"] = "draft"
    if reason:
        fixture["rejection_reason"] = reason
    save_manifest(data)
    print(f"[OK] Fixture '{fixture_id}' rejected. Reason: {reason}")


def cmd_list(args) -> None:
    """List fixtures filtered by status."""
    data = load_manifest()
    fixtures = data.get("fixtures", [])
    status_filter = getattr(args, "status", None)

    for f in fixtures:
        fst = f.get("file_status", "pending")
        ast = f.get("approval_status", "draft")
        if status_filter and fst != status_filter and ast != status_filter:
            continue
        indicator = "[OK]" if ast == "approved" else ("[FILE]" if fst == "available" else "[WAIT]")
        desc = f['description'].replace('\u2014', '-').replace('\u2013', '-')
        print(f"{indicator:6} {f['id']:12} [{f['furniture_type_expected']:15}] "
              f"file={fst:10} approval={ast} | {desc}")


def cmd_validate(args) -> None:
    """Validate all expected JSONs against schema."""
    data = load_manifest()
    fixtures = data.get("fixtures", [])
    errors = []
    validated = 0

    required_fields = {
        "drawing_id", "page_no", "furniture_type",
        "parts_table", "dimension_candidates", "views"
    }

    for fixture in fixtures:
        ej_path = ROOT / fixture.get("expected_json_path", "")
        if not ej_path.exists():
            continue  # Pending — skip
        try:
            with open(ej_path, encoding="utf-8") as f:
                ej = json.load(f)
            missing = required_fields - set(ej.keys())
            if missing:
                errors.append(f"[SCHEMA] {fixture['id']}: missing fields {missing}")
            if ej.get("furniture_type") not in VALID_FURNITURE_TYPES:
                errors.append(f"[TYPE] {fixture['id']}: invalid furniture_type={ej.get('furniture_type')!r}")
            validated += 1
        except Exception as exc:
            errors.append(f"[JSON] {fixture['id']}: {exc}")

    if errors:
        print(f"[FAIL] {len(errors)} validation errors:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print(f"[OK] {validated} expected JSON files validated (no errors).")


# ── Main ───────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FOMS Brain Drawing Fixture Manifest Manager"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show corpus status")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Register a drawing file")
    p_ingest.add_argument("--file", required=True, help="Path to drawing file")
    p_ingest.add_argument("--id", dest="fixture_id", required=True, help="Fixture ID")

    # approve
    p_approve = sub.add_parser("approve", help="Mark fixture as approved")
    p_approve.add_argument("--fixture-id", required=True)
    p_approve.add_argument("--user", default="user", help="Approver name")

    # reject
    p_reject = sub.add_parser("reject", help="Mark fixture as rejected")
    p_reject.add_argument("--fixture-id", required=True)
    p_reject.add_argument("--reason", default="", help="Rejection reason")

    # list
    p_list = sub.add_parser("list", help="List fixtures")
    p_list.add_argument("--status", choices=["pending", "available", "approved", "draft"], default=None)

    # validate
    sub.add_parser("validate", help="Validate expected JSONs against schema")

    args = parser.parse_args()
    cmd_map = {
        "status": cmd_status,
        "ingest": cmd_ingest,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "list": cmd_list,
        "validate": cmd_validate,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
