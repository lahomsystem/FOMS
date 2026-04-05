"""Tests for tools.harness.build_context_bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HARNESS_DIR = _REPO_ROOT / "tools" / "harness"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from build_context_bundle import (
    build_bundle_text,
    load_manifest,
    load_profile,
    load_yaml_json_compatible,
    main,
    parse_args,
    registry_paths_for_ids,
    run_build,
)


def _write_registry_repo(root: Path) -> tuple[Path, Path]:
    """Minimal manifest + profile matching the Phase 1 registry schema."""
    (root / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (root / "beta.md").write_text("# Beta\n", encoding="utf-8")
    man = root / "tools" / "harness" / "manifest.yaml"
    man.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "schema_version": "1.0.0",
        "manifest_kind": "foms_harness_manifest",
        "title": "Test harness",
        "description": "AGENTS baseline description.",
        "bundle_defaults": {},
        "source_registry": {
            "a": {"path": "beta.md", "kind": "policy", "label": "Beta file"},
            "b": {"path": "alpha.md", "kind": "policy", "label": "Alpha file"},
        },
    }
    man.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    pdir = root / "tools" / "harness" / "profiles"
    pdir.mkdir(parents=True, exist_ok=True)
    profile_one = {
        "schema_version": "1.0.0",
        "profile_kind": "foms_harness_profile",
        "profile_name": "one",
        "output_bundle_path": "out/one.md",
        "default_shell": "powershell",
        "browser_mode": "test_browser",
        "policy_priority": ["b", "a"],
        "source_ids": ["b", "a"],
        "runner_notes": {
            "shell": "Use PowerShell.",
            "browser": "Use MCP.",
            "extra": "Other.",
        },
    }
    (pdir / "one.yaml").write_text(json.dumps(profile_one, indent=2), encoding="utf-8")
    return man, pdir


def test_load_manifest_and_json_compatible_round_trip(tmp_path: Path) -> None:
    """Manifest loads and round-trips through JSON (schema-friendly)."""
    manifest_path, _ = _write_registry_repo(tmp_path)
    m = load_manifest(manifest_path)
    assert m["title"] == "Test harness"
    assert "a" in m["source_registry"]
    json.loads(json.dumps(m))


def test_load_yaml_rejects_non_json_syntax(tmp_path: Path) -> None:
    """Non-JSON syntax inside `.yaml` must fail clearly."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("x: 2020-01-01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="strict JSON-compatible"):
        load_yaml_json_compatible(bad)


def test_registry_paths_preserve_profile_order(tmp_path: Path) -> None:
    """Resolved paths follow the declared profile source order."""
    manifest_path, _ = _write_registry_repo(tmp_path)
    m = load_manifest(manifest_path)
    assert registry_paths_for_ids(m, ["a", "b"]) == ["beta.md", "alpha.md"]


def test_generate_one_bundle_content_and_order(tmp_path: Path) -> None:
    """Single profile: policy sections present; files follow declared source order."""
    manifest_path, pdir = _write_registry_repo(tmp_path)
    m = load_manifest(manifest_path)
    prof = load_profile(pdir / "one.yaml")
    text = build_bundle_text(tmp_path, m, prof, "tools/harness/manifest.yaml")
    assert "# Test harness — one" in text
    assert "### Source of truth" in text
    assert "AGENTS baseline" in text
    assert "### Shell" in text
    assert "### Browser" in text
    assert "### Policy priority" in text
    assert "1. Alpha file" in text
    assert "## `alpha.md`" in text
    assert "## `beta.md`" in text
    assert text.index("## `alpha.md`") < text.index("## `beta.md`")
    assert "### Additional runner notes" in text
    assert "**extra**" in text


def test_run_build_all_profiles(tmp_path: Path) -> None:
    """Multiple profiles each receive an output file."""
    manifest_path, pdir = _write_registry_repo(tmp_path)
    profile_two = {
        "schema_version": "1.0.0",
        "profile_kind": "foms_harness_profile",
        "profile_name": "two",
        "output_bundle_path": "out/two.md",
        "default_shell": "powershell",
        "browser_mode": "test_browser",
        "policy_priority": ["b"],
        "source_ids": ["b"],
        "runner_notes": {"shell": "x", "browser": "y"},
    }
    (pdir / "two.yaml").write_text(json.dumps(profile_two, indent=2), encoding="utf-8")
    outs = run_build(tmp_path, manifest_path, pdir, ["one", "two"])
    assert len(outs) == 2
    assert (tmp_path / "out" / "one.md").is_file()
    assert (tmp_path / "out" / "two.md").is_file()


def test_cli_all_exits_zero(tmp_path: Path) -> None:
    """CLI --all returns 0 and writes bundles."""
    _write_registry_repo(tmp_path)
    profile_two = {
        "schema_version": "1.0.0",
        "profile_kind": "foms_harness_profile",
        "profile_name": "two",
        "output_bundle_path": "out/two.md",
        "default_shell": "powershell",
        "browser_mode": "test_browser",
        "policy_priority": ["b"],
        "source_ids": ["b"],
        "runner_notes": {"shell": "x", "browser": "y"},
    }
    (tmp_path / "tools" / "harness" / "profiles" / "two.yaml").write_text(
        json.dumps(profile_two, indent=2),
        encoding="utf-8",
    )
    argv = [
        "--repo-root",
        str(tmp_path),
        "--manifest",
        str(tmp_path / "tools" / "harness" / "manifest.yaml"),
        "--profiles-dir",
        str(tmp_path / "tools" / "harness" / "profiles"),
        "--all",
    ]
    assert main(argv) == 0
    assert (tmp_path / "out" / "one.md").is_file()
    assert (tmp_path / "out" / "two.md").is_file()


def test_missing_source_file_fails(tmp_path: Path) -> None:
    """Missing repo file referenced in registry raises FileNotFoundError."""
    manifest_path, pdir = _write_registry_repo(tmp_path)
    m = load_manifest(manifest_path)
    m = json.loads(json.dumps(m))
    m["source_registry"]["a"]["path"] = "missing.md"
    prof = load_profile(pdir / "one.yaml")
    with pytest.raises(FileNotFoundError, match="missing.md"):
        build_bundle_text(tmp_path, m, prof, "m.yaml")


def test_missing_profile_file_fails(tmp_path: Path) -> None:
    """run_build with unknown profile name fails clearly."""
    manifest_path, pdir = _write_registry_repo(tmp_path)
    with pytest.raises(FileNotFoundError, match="nope.yaml"):
        run_build(tmp_path, manifest_path, pdir, ["nope"])


def test_profile_priority_and_sources_must_match(tmp_path: Path) -> None:
    """Profile validation should reject mismatched source_ids/policy_priority."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "profile_kind": "foms_harness_profile",
                "profile_name": "bad",
                "output_bundle_path": "out/bad.md",
                "default_shell": "powershell",
                "browser_mode": "test_browser",
                "policy_priority": ["a"],
                "source_ids": ["a", "b"],
                "runner_notes": {"shell": "x", "browser": "y"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="same source ids"):
        load_profile(bad)


def test_manifest_defaults_apply_to_output_path(tmp_path: Path) -> None:
    """Manifest bundle defaults should fill missing directory and extension."""
    (tmp_path / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    manifest_path = tmp_path / "tools" / "harness" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "manifest_kind": "foms_harness_manifest",
                "title": "Defaults harness",
                "description": "Defaults description.",
                "bundle_defaults": {
                    "default_encoding": "utf-8",
                    "default_output_dir": "docs/context",
                    "default_bundle_extension": ".bundle.md",
                    "section_separator": "\n\n---\n\n",
                    "include_source_headers_in_bundle": True,
                },
                "source_registry": {
                    "a": {"path": "alpha.md", "kind": "policy", "label": "Alpha file"}
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    profiles_dir = tmp_path / "tools" / "harness" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "defaults.yaml").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "profile_kind": "foms_harness_profile",
                "profile_name": "defaults",
                "output_bundle_path": "defaults",
                "default_shell": "powershell",
                "browser_mode": "test_browser",
                "policy_priority": ["a"],
                "source_ids": ["a"],
                "runner_notes": {"shell": "x", "browser": "y"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    outs = run_build(tmp_path, manifest_path, profiles_dir, ["defaults"])
    assert len(outs) == 1
    assert (tmp_path / "docs" / "context" / "defaults.bundle.md").is_file()


def test_parse_args_defaults() -> None:
    """parse_args resolves default manifest and profiles paths under repo root."""
    ns = parse_args(["--all", "--repo-root", str(Path.cwd())])
    assert (ns.repo_root / "tools" / "harness" / "manifest.yaml") == ns.manifest
    assert (ns.repo_root / "tools" / "harness" / "profiles") == ns.profiles_dir
