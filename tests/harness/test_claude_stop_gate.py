"""Deterministic Stop-gate tests for `.claude/hooks/quality_check.py`.

Covers the three contract paths:
  (a) no pending .py -> exit 0 (no block)
  (b) pending .py + successful `import app` -> exit 0 + pending cleared
  (c) pending .py + failing `import app` (mocked) -> exit 2 + "STOP GATE" on stderr
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_REL = ".claude/hooks/quality_check.py"


def _load_quality_check(module_name: str):
    """Load the quality_check hook module fresh from the repo path."""
    module_path = REPO_ROOT / HOOK_REL
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The hook inserts `.claude/hooks` at sys.path[0] and caches `shared_utils` in
    # sys.modules on import. Restore both afterwards so it doesn't shadow other
    # in-process module loads (e.g. .cursor/hooks/shared_utils).
    saved_path = list(sys.path)
    saved_shared = sys.modules.get("shared_utils")
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        if saved_shared is not None:
            sys.modules["shared_utils"] = saved_shared
        else:
            sys.modules.pop("shared_utils", None)
    return module


def _redirect_runtime(module, tmp_path: Path, monkeypatch) -> Path:
    """Point the module's runtime/log path helpers at a temp workspace."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime_dir.joinpath(*p)))
    monkeypatch.setattr(module, "harness_log_path", lambda *p: str(logs_dir.joinpath(*p)))
    monkeypatch.setattr(module, "read_stdin_json", lambda: {})
    return runtime_dir


def _write_pending(runtime_dir: Path, files: list[str]) -> Path:
    """Create a pending-verify state file with the given .py files."""
    pending = runtime_dir / ".claude_pending_verify.json"
    pending.write_text(
        json.dumps({"session_id": "testsess", "files": files, "updated": "now"}),
        encoding="utf-8",
    )
    return pending


def test_no_pending_exits_zero(tmp_path: Path, monkeypatch) -> None:
    """With no pending .py, the hook returns normally (no SystemExit / no block)."""
    module = _load_quality_check("qc_no_pending")
    _redirect_runtime(module, tmp_path, monkeypatch)

    # main() should simply return (checklist path); no SystemExit raised.
    module.main()


def test_pending_import_success_clears(tmp_path: Path, monkeypatch) -> None:
    """Pending .py + real successful `import app` -> exit 0 and pending removed."""
    module = _load_quality_check("qc_import_ok")
    runtime_dir = _redirect_runtime(module, tmp_path, monkeypatch)
    pending = _write_pending(runtime_dir, ["foms/api/address.py"])

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 0
    assert not pending.exists(), "pending should be cleared after successful gate"


def test_pending_import_failure_blocks(tmp_path: Path, monkeypatch, capsys) -> None:
    """Pending .py + failing `import app` (mocked) -> exit 2 with STOP GATE on stderr."""
    module = _load_quality_check("qc_import_fail")
    runtime_dir = _redirect_runtime(module, tmp_path, monkeypatch)
    pending = _write_pending(runtime_dir, ["foms/api/broken.py"])

    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Traceback (most recent call last):\nModuleNotFoundError: no module 'x'",
        )

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "STOP GATE" in captured.err
    assert "foms/api/broken.py" in captured.err
    assert pending.exists(), "pending should be retained after a failed gate"


def test_pending_timeout_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    """A subprocess timeout must fail-open (return, not block) and log the error."""
    module = _load_quality_check("qc_timeout")
    runtime_dir = _redirect_runtime(module, tmp_path, monkeypatch)
    _write_pending(runtime_dir, ["foms/api/slow.py"])

    def _fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="import app", timeout=120)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    # Should return normally (no SystemExit) — timeout is not a block.
    module.main()

    log_file = tmp_path / "logs" / "CLAUDE_HOOK_LOG.md"
    assert log_file.exists()
    assert "timeout" in log_file.read_text(encoding="utf-8").lower()
