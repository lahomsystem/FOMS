"""Adapter that drives a SketchUp analyzer subprocess and validates output.

The intake worker delegates the actual parsing to an external binary:
- B3: `tools/sketchup_analyzer/fake_analyzer.py` (this codebase)
- B4: `sketchup_analyzer.exe` (built from `tools/sketchup_analyzer/cpp/`)

`run_analyzer()` keeps both paths identical from the worker's view:
  1. Resolve the analyzer command for the configured `worker_kind`.
  2. Run it with a timeout. Capture stdout/stderr for diagnostics.
  3. Read the output JSON.
  4. Validate against `foms-sketchup-raw-v1`.
  5. Return an `AnalyzerRunResult` — the worker translates failure modes
     into job error_code/error_text + status transitions.

Anything subtler than this (model snapshots, candidate creation) belongs
to `sketchup_intake_pipeline.py`. This module never touches the DB.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foms.services.designer.sketchup_raw_schema import (
    SchemaValidationResult,
    validate_raw_model_json,
)


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent.parent
FAKE_ANALYZER_PATH = ROOT / "tools" / "sketchup_analyzer" / "fake_analyzer.py"


class AnalyzerNotConfigured(RuntimeError):
    """The configured analyzer binary cannot be located."""


@dataclass
class AnalyzerRunResult:
    """Outcome of a single subprocess run + schema validation."""

    success: bool
    worker_kind: str
    duration_seconds: float
    raw_model_json: dict[str, Any] | None = None
    validation: SchemaValidationResult | None = None
    stdout: str = ""
    stderr: str = ""
    return_code: int | None = None
    timed_out: bool = False
    error_code: str | None = None
    error_text: str | None = None
    output_path: Path | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def _resolve_command(
    *,
    worker_kind: str,
    input_path: Path,
    output_path: Path,
    preview_dir: Path | None,
    fixture_id: str | None,
) -> list[str]:
    """Build the analyzer command line for the given worker_kind.

    `fake_contract` runs the bundled Python fixture analyzer. `c_api` runs
    `sketchup_analyzer.exe` (built in B4). `desktop_ruby` is a bootstrap
    fallback that drives SketchUp Desktop via its Ruby exporter — its
    invocation is wrapped by a CLI shim in B4 so it presents the same
    `--input/--output` shape.
    """
    if worker_kind == "fake_contract":
        if not FAKE_ANALYZER_PATH.exists():
            raise AnalyzerNotConfigured(
                f"fake_analyzer.py missing at {FAKE_ANALYZER_PATH}"
            )
        cmd = [
            sys.executable,
            str(FAKE_ANALYZER_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--format", "foms-sketchup-raw-v1",
        ]
        if preview_dir is not None:
            cmd += ["--preview-dir", str(preview_dir)]
        if fixture_id:
            cmd += ["--fixture-id", fixture_id]
        return cmd

    if worker_kind == "c_api":
        exe = os.environ.get("DESIGNER_SKETCHUP_ANALYZER_EXE", "").strip()
        if not exe or not Path(exe).exists():
            raise AnalyzerNotConfigured(
                "DESIGNER_SKETCHUP_ANALYZER_EXE is not set or file does not exist."
            )
        cmd = [
            exe,
            "--input", str(input_path),
            "--output", str(output_path),
            "--format", "foms-sketchup-raw-v1",
        ]
        if preview_dir is not None:
            cmd += ["--preview-dir", str(preview_dir)]
        return cmd

    if worker_kind == "desktop_ruby":
        shim = os.environ.get("DESIGNER_SKETCHUP_RUBY_SHIM", "").strip()
        if not shim or not Path(shim).exists():
            raise AnalyzerNotConfigured(
                "DESIGNER_SKETCHUP_RUBY_SHIM is not set or file does not exist."
            )
        cmd = [
            shim,
            "--input", str(input_path),
            "--output", str(output_path),
            "--format", "foms-sketchup-raw-v1",
        ]
        if preview_dir is not None:
            cmd += ["--preview-dir", str(preview_dir)]
        return cmd

    raise AnalyzerNotConfigured(f"unknown worker_kind: {worker_kind!r}")


def is_production_environment() -> bool:
    """Plan §B3/§11.3 — production must refuse `fake_contract` workers.

    Drives off `FLASK_ENV`, `APP_ENV`, or the Railway-injected
    `RAILWAY_ENVIRONMENT` (typically "production"). Defaults to false so
    local dev / CI stays unblocked.
    """
    for var in ("FLASK_ENV", "APP_ENV", "RAILWAY_ENVIRONMENT"):
        val = os.environ.get(var, "").strip().lower()
        if val in {"production", "prod"}:
            return True
    return False


def guard_worker_kind(worker_kind: str) -> None:
    """Refuse fake_contract in production. Raises if violated."""
    if worker_kind == "fake_contract" and is_production_environment():
        raise AnalyzerNotConfigured(
            "fake_contract analyzer is forbidden in production. "
            "Set DESIGNER_SKETCHUP_WORKER_KIND to c_api or desktop_ruby."
        )


def run_analyzer(
    *,
    worker_kind: str,
    input_path: Path,
    output_path: Path,
    preview_dir: Path | None = None,
    fixture_id: str | None = None,
    timeout_seconds: int,
) -> AnalyzerRunResult:
    """Run the configured analyzer once and validate its output.

    Never raises on subprocess/validation failure — the worker needs a
    structured result envelope so it can update the parse job row.
    """
    guard_worker_kind(worker_kind)
    cmd = _resolve_command(
        worker_kind=worker_kind,
        input_path=input_path,
        output_path=output_path,
        preview_dir=preview_dir,
        fixture_id=fixture_id,
    )

    started = time.monotonic()
    timed_out = False
    rc: int | None = None
    stdout = stderr = ""
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        rc = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    except (OSError, FileNotFoundError) as exc:
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=time.monotonic() - started,
            return_code=None,
            error_code="ANALYZER_EXEC_FAILED",
            error_text=f"{type(exc).__name__}: {exc}",
        )

    duration = time.monotonic() - started

    if timed_out:
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=duration,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            error_code="ANALYZER_TIMEOUT",
            error_text=f"analyzer exceeded {timeout_seconds}s timeout",
        )

    if rc != 0:
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=duration,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
            error_code="ANALYZER_NONZERO_EXIT",
            error_text=f"analyzer exit code={rc}: {stderr.strip()[-500:]}",
        )

    if not output_path.exists():
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=duration,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
            error_code="ANALYZER_OUTPUT_MISSING",
            error_text=f"analyzer reported success but output file is missing: {output_path}",
        )

    try:
        raw = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=duration,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
            error_code="ANALYZER_OUTPUT_INVALID_JSON",
            error_text=f"json decode failed at line {exc.lineno}, col {exc.colno}: {exc.msg}",
        )

    validation = validate_raw_model_json(raw)
    if not validation.is_valid:
        return AnalyzerRunResult(
            success=False,
            worker_kind=worker_kind,
            duration_seconds=duration,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
            raw_model_json=raw,
            validation=validation,
            output_path=output_path,
            error_code="ANALYZER_OUTPUT_SCHEMA_INVALID",
            error_text=validation.as_error_text(),
        )

    # Successful run. Pull a few summary metrics so they can be stored
    # on the parse job without redownloading the JSON.
    model = raw.get("model") or {}
    metrics = {
        "node_count": len(raw.get("nodes") or []),
        "definition_count": len(raw.get("definitions") or []),
        "material_count": len(raw.get("materials") or []),
        "face_count": int(model.get("face_count") or 0),
        "edge_count": int(model.get("edge_count") or 0),
        "duration_seconds": duration,
    }

    return AnalyzerRunResult(
        success=True,
        worker_kind=worker_kind,
        duration_seconds=duration,
        raw_model_json=raw,
        validation=validation,
        stdout=stdout,
        stderr=stderr,
        return_code=rc,
        output_path=output_path,
        metrics=metrics,
    )


__all__ = [
    "AnalyzerNotConfigured",
    "AnalyzerRunResult",
    "FAKE_ANALYZER_PATH",
    "guard_worker_kind",
    "is_production_environment",
    "run_analyzer",
]
