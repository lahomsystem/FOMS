"""Contracts for indexed JSONB text ILIKE perf exemptions."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILES = [
    ROOT / "migrations" / "versions" / "phase_d_trgm_indexes.py",
    ROOT / "migrations" / "versions" / "phase_e_trgm_perm_indexes.py",
]
PERF_OK_RE = re.compile(r"#\s*perf-ok:\s*(ix_[a-zA-Z0-9_]+)")


def test_jsonb_text_ilike_perf_ok_comments_cite_real_trgm_indexes() -> None:
    migration_text = "\n".join(path.read_text(encoding="utf-8") for path in MIGRATION_FILES)
    cited_indexes: set[str] = set()

    for path in ROOT.glob("foms/**/*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel:
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "structured_data" not in line or ".ilike(" not in line or "# perf-ok" not in line:
                continue
            match = PERF_OK_RE.search(line)
            assert match, f"perf-ok must cite an index name: {rel}: {line.strip()}"
            cited_indexes.add(match.group(1))

    assert cited_indexes
    for index_name in cited_indexes:
        assert index_name in migration_text
