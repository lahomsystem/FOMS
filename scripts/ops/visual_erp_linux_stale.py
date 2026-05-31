"""Exit 1 when linux erp_v2 baselines are older than win32 (git commit time).

Used by CI visual job to refresh Linux SSOT after win32-only baseline updates.
Win32-vs-source staleness: ``python scripts/ops/visual_baseline_stale.py --check-win32-vs-sources``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_policy_module():
    """Load sibling visual_baseline_stale.py without package layout."""
    policy_path = Path(__file__).resolve().parent / "visual_baseline_stale.py"
    spec = importlib.util.spec_from_file_location("visual_baseline_stale", policy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    policy = _load_policy_module()
    stale = policy.erp_linux_baselines_stale()
    for name in stale:
        print(f"stale: {name}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
