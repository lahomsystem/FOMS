"""PG-L6: Fine-Tuning Dataset Export Tests."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent.parent


class TestFinetuneExportModule:
    def test_export_tool_exists(self):
        p = ROOT / "tools" / "designer" / "export_finetune_dataset.py"
        assert p.exists()

    def test_export_tool_importable(self):
        import sys; sys.path.insert(0, str(ROOT))
        from tools.designer.export_finetune_dataset import (
            export_dataset, _strip_pii, EXPORT_TYPES
        )
        assert callable(export_dataset)
        assert "all" in EXPORT_TYPES

    def test_strip_pii_removes_customer_name(self):
        from tools.designer.export_finetune_dataset import _strip_pii
        row = {"design": {"customer_name": "홍길동", "width_mm": 2400}}
        clean = _strip_pii(row)
        assert "customer_name" not in clean["design"]
        assert clean["design"]["width_mm"] == 2400

    def test_strip_pii_nested(self):
        from tools.designer.export_finetune_dataset import _strip_pii
        row = {"outer": {"inner": {"phone": "010-1234-5678", "data": "ok"}}}
        clean = _strip_pii(row)
        assert "phone" not in clean["outer"]["inner"]
        assert clean["outer"]["inner"]["data"] == "ok"

    def test_dry_run_no_file_written(self, tmp_path):
        from tools.designer.export_finetune_dataset import export_dataset
        out = tmp_path / "test_export.jsonl"
        summary = export_dataset(out, export_type="design_case", dry_run=True)
        assert summary["dry_run"] is True
        assert not out.exists()

    def test_export_creates_file_when_not_dry_run(self, tmp_path):
        from tools.designer.export_finetune_dataset import export_dataset
        out = tmp_path / "export.jsonl"
        summary = export_dataset(out, export_type="all", dry_run=False)
        # File should be created even if 0 rows (empty DB in tests)
        assert out.exists()
        assert summary["pii_blocked"] == 0

    def test_exported_jsonl_valid_json(self, tmp_path):
        from tools.designer.export_finetune_dataset import export_dataset
        out = tmp_path / "export.jsonl"
        export_dataset(out, export_type="all")
        with open(out, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    row = json.loads(line)  # must not raise
                    assert "type" in row

    def test_export_summary_has_required_fields(self, tmp_path):
        from tools.designer.export_finetune_dataset import export_dataset
        out = tmp_path / "export.jsonl"
        summary = export_dataset(out)
        assert "total_rows" in summary
        assert "pii_blocked" in summary
        assert "exported_at" in summary
        assert "dry_run" in summary

    def test_pii_scan_blocks_leakage(self):
        """PII in any row must be blocked before writing."""
        from tools.designer.export_finetune_dataset import _strip_pii
        row = {
            "furniture_type": "wardrobe",
            "customer_name": "홍길동",  # should be stripped
            "width_mm": 2400,
        }
        clean = _strip_pii(row)
        assert "customer_name" not in clean
        # PII scan
        row_str = json.dumps(clean, ensure_ascii=False)
        pii_keys = {"customer_name", "phone", "address"}
        assert not any(k in row_str for k in pii_keys)
