"""Structured verification runner for the shared verify-result workflow."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from spec_utils import find_latest_spec


APP_OK_SNIPPET = 'import app; print("APP_OK")'
APP_OK_TIMEOUT_SECONDS = 120
MANUAL_CHECKS = [
    "에러 처리(try-except, 상태 코드 변환 등)가 적절한가?",
    "하드코딩된 비밀키, DB URL 등 민감 정보가 없는가?",
    "raw SQL 사용 시 파라미터 바인딩이 되어 있는가?",
    "사용자 입력이 |safe 없이 렌더링되는가?",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to verify.",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        help="Optional explicit spec path. Relative paths are resolved from repo root.",
    )
    parser.add_argument(
        "--require-spec",
        action="store_true",
        help="Fail if no *_SPEC.md file is available.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of plain text.",
    )
    return parser.parse_args(argv)


def resolve_repo_root(repo_root: Path) -> Path:
    """Resolve and validate the repository root path."""
    resolved = repo_root.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Repository root not found: {resolved}")
    return resolved


def make_repo_relative(repo_root: Path, target: Path | None) -> str | None:
    """Return a repo-relative POSIX path when possible."""
    if target is None:
        return None
    try:
        return target.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return target.resolve().as_posix()


def resolve_spec_path(repo_root: Path, spec_path: Path | None) -> Path | None:
    """Resolve an explicit spec path or fall back to the latest matching spec."""
    if spec_path is None:
        return find_latest_spec(repo_root)

    candidate = spec_path if spec_path.is_absolute() else repo_root / spec_path
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Spec file not found: {resolved}")
    return resolved


def build_error_report(
    *,
    repo_root: Path | None,
    requested_repo_root: Path,
    spec_path: Path | None,
    require_spec: bool,
    error: Exception,
) -> dict[str, Any]:
    """Build a structured failure report for path-resolution errors."""
    effective_repo_root = repo_root or requested_repo_root.resolve()
    requested_spec = None
    if spec_path is not None:
        candidate = spec_path if spec_path.is_absolute() else effective_repo_root / spec_path
        requested_spec = make_repo_relative(effective_repo_root, candidate)

    return {
        "success": False,
        "repo_root": effective_repo_root.as_posix(),
        "app_import": None,
        "spec": {
            "required": require_spec,
            "found": False,
            "path": requested_spec,
            "verification_items": [],
        },
        "manual_checks": MANUAL_CHECKS,
        "error": {
            "kind": error.__class__.__name__,
            "message": str(error),
        },
    }


def extract_verification_items(text: str) -> list[str]:
    """Extract checklist lines from the '## 4. 검증 기준' section."""
    in_section = False
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.match(r"^##\s*4\.\s*검증 기준\s*$", line):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line:
            continue
        if line.startswith(("- ", "* ", "- [", "* [")) or re.match(r"^\d+\.\s+", line):
            items.append(line)
    return items


def run_app_import_check(repo_root: Path) -> dict[str, Any]:
    """Run the shared APP_OK import baseline."""
    completed = subprocess.run(
        [sys.executable, "-c", APP_OK_SNIPPET],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=APP_OK_TIMEOUT_SECONDS,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    ok = completed.returncode == 0 and "APP_OK" in stdout
    return {
        "command": f'{sys.executable} -c "{APP_OK_SNIPPET}"',
        "ok": ok,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def build_report(repo_root: Path, spec_path: Path | None, require_spec: bool) -> dict[str, Any]:
    """Build the structured verification report."""
    app_import = run_app_import_check(repo_root)

    spec_info: dict[str, Any] = {
        "required": require_spec,
        "found": False,
        "path": None,
        "verification_items": [],
    }
    if spec_path is not None:
        spec_info["found"] = True
        spec_info["path"] = make_repo_relative(repo_root, spec_path)
        spec_info["verification_items"] = extract_verification_items(spec_path.read_text(encoding="utf-8"))

    success = app_import["ok"] and (spec_info["found"] or not require_spec)
    return {
        "success": success,
        "repo_root": repo_root.as_posix(),
        "app_import": app_import,
        "spec": spec_info,
        "manual_checks": MANUAL_CHECKS,
    }


def render_text_report(report: dict[str, Any]) -> str:
    """Render a concise human-readable report."""
    if not report.get("success") and report.get("error"):
        lines = [
            "## Verify Result",
            f"- repo_root: `{report['repo_root']}`",
        ]
        spec = report["spec"]
        lines.append(f"- spec: `{spec['path']}`" if spec["path"] else "- spec: 없음")
        lines.append(f"- error: {report['error']['kind']} - {report['error']['message']}")
        lines.append("- result: FAIL")
        return "\n".join(lines)

    lines = [
        "## Verify Result",
        f"- repo_root: `{report['repo_root']}`",
        f"- app_import: {'PASS' if report['app_import']['ok'] else 'FAIL'}",
    ]

    spec = report["spec"]
    if spec["found"]:
        lines.append(f"- spec: `{spec['path']}`")
        if spec["verification_items"]:
            lines.append("- spec_items:")
            lines.extend(f"  {item}" for item in spec["verification_items"])
        else:
            lines.append("- spec_items: 없음")
    else:
        lines.append("- spec: 없음")

    lines.append("- manual_checks:")
    lines.extend(f"  - {item}" for item in report["manual_checks"])

    if not report["success"]:
        lines.append("- result: FAIL")
        if not report["app_import"]["ok"]:
            lines.append("  - APP_OK baseline failed")
        if report["spec"]["required"] and not report["spec"]["found"]:
            lines.append("  - required spec missing")
    else:
        lines.append("- result: PASS")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    repo_root: Path | None = None
    try:
        repo_root = resolve_repo_root(args.repo_root)
        spec_path = resolve_spec_path(repo_root, args.spec)
        report = build_report(repo_root, spec_path, args.require_spec)
    except (FileNotFoundError, OSError) as exc:
        report = build_error_report(
            repo_root=repo_root,
            requested_repo_root=args.repo_root,
            spec_path=args.spec,
            require_spec=args.require_spec,
            error=exc,
        )

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        sys.stdout.write(render_text_report(report) + "\n")

    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
