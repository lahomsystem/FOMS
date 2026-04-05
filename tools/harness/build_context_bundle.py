"""Generate deterministic Markdown context bundles from JSON-compatible `.yaml` files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MANIFEST_KEYS: tuple[str, ...] = (
    "schema_version",
    "manifest_kind",
    "title",
    "description",
    "bundle_defaults",
    "source_registry",
)
PROFILE_KEYS: tuple[str, ...] = (
    "schema_version",
    "profile_kind",
    "profile_name",
    "output_bundle_path",
    "default_shell",
    "browser_mode",
    "policy_priority",
    "source_ids",
    "runner_notes",
)


def default_repo_root() -> Path:
    """Return repository root inferred from this file location (`.../tools/harness/`)."""
    return Path(__file__).resolve().parent.parent.parent


def load_yaml_json_compatible(path: Path) -> dict[str, Any]:
    """
    Load a JSON-compatible `.yaml` document into plain Python data.

    Args:
        path: Path to a UTF-8 `.yaml` file containing strict JSON syntax.

    Returns:
        Parsed mapping loaded via `json.loads()`.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Harness file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Harness file must use strict JSON-compatible YAML syntax: {path}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root, got {type(data).__name__}: {path}")
    try:
        json.loads(json.dumps(data))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Harness YAML must be JSON-compatible: {path}") from exc
    return data  # type: ignore[return-value]


def _require_keys(data: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(f"{label} missing required key(s): {', '.join(missing)}")


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate harness manifest.yaml (registry schema)."""
    data = load_yaml_json_compatible(path)
    _require_keys(data, MANIFEST_KEYS, "Manifest")
    defaults = data["bundle_defaults"]
    if not isinstance(defaults, dict):
        raise ValueError("Manifest 'bundle_defaults' must be a mapping")
    reg = data["source_registry"]
    if not isinstance(reg, dict) or not reg:
        raise ValueError("Manifest 'source_registry' must be a non-empty mapping")
    for sid, entry in sorted(reg.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"source_registry[{sid!r}] must be a mapping")
        if "path" not in entry or "label" not in entry:
            raise ValueError(f"source_registry[{sid!r}] needs 'path' and 'label'")
    return data


def load_profile(path: Path) -> dict[str, Any]:
    """Load and validate a runner profile YAML."""
    data = load_yaml_json_compatible(path)
    _require_keys(data, PROFILE_KEYS, "Profile")
    if not isinstance(data["policy_priority"], list) or not isinstance(data["source_ids"], list):
        raise ValueError("Profile 'policy_priority' and 'source_ids' must be lists")
    source_ids = data["source_ids"]
    policy_priority = data["policy_priority"]
    if not all(isinstance(item, str) for item in source_ids + policy_priority):
        raise ValueError("Profile 'policy_priority' and 'source_ids' must contain only strings")
    if len(set(source_ids)) != len(source_ids) or len(set(policy_priority)) != len(policy_priority):
        raise ValueError("Profile 'policy_priority' and 'source_ids' must not contain duplicates")
    if set(source_ids) != set(policy_priority):
        raise ValueError("Profile 'policy_priority' and 'source_ids' must reference the same source ids")
    rn = data["runner_notes"]
    if not isinstance(rn, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rn.items()):
        raise ValueError("Profile 'runner_notes' must be a string->string mapping")
    return data


def registry_paths_for_ids(manifest: dict[str, Any], source_ids: list[str]) -> list[str]:
    """Resolve source ids to repo-relative paths while preserving declared profile order."""
    reg: dict[str, Any] = manifest["source_registry"]
    paths: list[str] = []
    for sid in source_ids:
        if sid not in reg:
            raise ValueError(f"Unknown source id {sid!r} (not in manifest source_registry)")
        paths.append(str(reg[sid]["path"]))
    return paths


def policy_priority_lines(manifest: dict[str, Any], policy_priority: list[str]) -> list[str]:
    """Human-readable ordered policy priority lines."""
    reg: dict[str, Any] = manifest["source_registry"]
    lines: list[str] = []
    for i, sid in enumerate(policy_priority, start=1):
        if sid not in reg:
            raise ValueError(f"Unknown policy id {sid!r} in policy_priority")
        label = str(reg[sid]["label"])
        lines.append(f"{i}. {label} (`{sid}`)")
    return lines


def manifest_defaults(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return validated manifest bundle defaults."""
    defaults = manifest.get("bundle_defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("Manifest 'bundle_defaults' must be a mapping")
    return defaults


def _append_profile_header(
    lines: list[str],
    manifest: dict[str, Any],
    profile: dict[str, Any],
    manifest_rel: str,
) -> None:
    """
    Append document title and profile metadata lines.

    Args:
        lines: Output buffer.
        manifest: Loaded manifest mapping.
        profile: Loaded profile mapping.
        manifest_rel: Display path for the manifest file.
    """
    lines.append(f"# {manifest['title']} — {profile['profile_name']}")
    lines.append("")
    lines.append("## Profile metadata")
    lines.append("")
    lines.append(f"- **Manifest schema**: `{manifest['schema_version']}`")
    lines.append(f"- **Profile schema**: `{profile['schema_version']}`")
    lines.append(f"- **Profile**: `{profile['profile_name']}`")
    lines.append(f"- **Manifest**: `{manifest_rel}`")
    lines.append(f"- **Output**: `{profile['output_bundle_path']}`")
    lines.append("")


def _append_policy_summary(lines: list[str], manifest: dict[str, Any], profile: dict[str, Any]) -> None:
    """
    Append policy summary sections (truth, shell, browser, priority, extra notes).

    Args:
        lines: Output buffer.
        manifest: Loaded manifest mapping.
        profile: Loaded profile mapping.
    """
    rn = profile["runner_notes"]
    shell_extra = rn.get("shell")
    browser_extra = rn.get("browser")
    other_keys = sorted(k for k in rn.keys() if k not in {"shell", "browser"})
    other_block = "\n".join(f"- **{k}**: {rn[k]}" for k in other_keys)

    lines.append("## Policy summary")
    lines.append("")
    lines.append("### Source of truth")
    lines.append("")
    lines.append(str(manifest["description"]).strip())
    lines.append("")
    lines.append("### Shell")
    lines.append("")
    lines.append(f"Default: `{profile['default_shell']}`")
    if shell_extra:
        lines.append("")
        lines.append(shell_extra.strip())
    lines.append("")
    lines.append("### Browser")
    lines.append("")
    lines.append(f"Mode: `{profile['browser_mode']}`")
    if browser_extra:
        lines.append("")
        lines.append(browser_extra.strip())
    lines.append("")
    lines.append("### Policy priority")
    lines.append("")
    lines.extend(policy_priority_lines(manifest, list(profile["policy_priority"])))
    lines.append("")
    if other_block:
        lines.append("### Additional runner notes")
        lines.append("")
        lines.append(other_block)
        lines.append("")


def render_bundle(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    manifest_rel: str,
    sources_content: list[tuple[str, str]],
) -> str:
    """Build deterministic Markdown for one profile."""
    lines: list[str] = []
    defaults = manifest_defaults(manifest)
    section_separator = str(defaults.get("section_separator", "\n\n---\n\n"))
    include_headers = bool(defaults.get("include_source_headers_in_bundle", True))
    _append_profile_header(lines, manifest, profile, manifest_rel)
    _append_policy_summary(lines, manifest, profile)
    lines.append("")
    lines.append("## Included source files")
    lines.append("")
    if not sources_content:
        lines.append("*(no source files configured)*")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    rendered_sections: list[str] = []
    for rel, body in sources_content:
        section_lines: list[str] = []
        if include_headers:
            section_lines.append(f"## `{rel}`")
            section_lines.append("")
        section_lines.append(body.rstrip("\n"))
        rendered_sections.append("\n".join(section_lines).rstrip())
    lines.append(section_separator.join(rendered_sections))
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def read_repo_file(repo_root: Path, rel_path: str, encoding: str) -> str:
    """Read a repo-relative file as UTF-8 text."""
    full = (repo_root / rel_path).resolve()
    try:
        full.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Source path escapes repository root: {rel_path}") from exc
    if not full.is_file():
        raise FileNotFoundError(f"Source file not found for bundle: {rel_path}")
    return full.read_text(encoding=encoding)


def build_bundle_text(repo_root: Path, manifest: dict[str, Any], profile: dict[str, Any], manifest_rel: str) -> str:
    """Assemble bundle text for one profile using manifest + resolved sources."""
    defaults = manifest_defaults(manifest)
    encoding = str(defaults.get("default_encoding", "utf-8"))
    rel_paths = registry_paths_for_ids(manifest, list(profile["source_ids"]))
    pairs: list[tuple[str, str]] = []
    for rel in rel_paths:
        pairs.append((rel, read_repo_file(repo_root, rel, encoding)))
    return render_bundle(manifest, profile, manifest_rel, pairs)


def manifest_display_path(repo_root: Path, manifest_path: Path) -> str:
    """Repo-relative manifest path for display, or absolute if outside repo root."""
    try:
        return manifest_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return manifest_path.resolve().as_posix()


def resolve_output_rel(manifest: dict[str, Any], output_rel: str) -> str:
    """Normalize profile output path with manifest defaults."""
    defaults = manifest_defaults(manifest)
    default_dir = str(defaults.get("default_output_dir", "")).strip()
    default_ext = str(defaults.get("default_bundle_extension", ".md")).strip() or ".md"
    rel_path = Path(output_rel)
    if rel_path.suffix == "":
        rel_path = rel_path.with_suffix(default_ext)
    if str(rel_path.parent) == "." and default_dir:
        rel_path = Path(default_dir) / rel_path
    return rel_path.as_posix()


def write_bundle(repo_root: Path, output_rel: str, text: str, encoding: str) -> Path:
    """Write bundle to repo-relative path, creating parent directories."""
    out = (repo_root / output_rel).resolve()
    try:
        out.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Output path escapes repository root: {output_rel}") from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding=encoding, newline="\n")
    return out


def list_profile_stems(profiles_dir: Path) -> list[str]:
    """Return sorted profile stems (one per *.yaml)."""
    if not profiles_dir.is_dir():
        raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")
    names = sorted(p.stem for p in profiles_dir.glob("*.yaml") if p.is_file())
    if not names:
        raise FileNotFoundError(f"No profile YAML files in: {profiles_dir}")
    return names


def profile_path_for_name(profiles_dir: Path, name: str) -> Path:
    """Resolve `profiles/<name>.yaml`."""
    path = profiles_dir / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Profile not found: {path}")
    return path


def generate_for_profile(
    repo_root: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    profile_data: dict[str, Any],
) -> Path:
    """Render and write bundle for a loaded profile dict."""
    manifest_rel = manifest_display_path(repo_root, manifest_path)
    text = build_bundle_text(repo_root, manifest, profile_data, manifest_rel)
    defaults = manifest_defaults(manifest)
    encoding = str(defaults.get("default_encoding", "utf-8"))
    output_rel = resolve_output_rel(manifest, str(profile_data["output_bundle_path"]))
    return write_bundle(repo_root, output_rel, text, encoding)


def run_build(
    repo_root: Path,
    manifest_path: Path,
    profiles_dir: Path,
    profile_names: list[str],
) -> list[Path]:
    """Generate bundles for each named profile."""
    manifest = load_manifest(manifest_path)
    outputs: list[Path] = []
    for name in profile_names:
        p_path = profile_path_for_name(profiles_dir, name)
        prof = load_profile(p_path)
        if prof.get("profile_name") != name:
            raise ValueError(
                f"Profile filename stem {name!r} must match profile_name "
                f"{prof.get('profile_name')!r}: {p_path}"
            )
        outputs.append(generate_for_profile(repo_root, manifest, manifest_path, prof))
    return outputs


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments."""
    repo = default_repo_root()
    parser = argparse.ArgumentParser(description="Build FOMS harness Markdown context bundles.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo,
        help="Repository root (default: inferred from script location)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to manifest.yaml (default: <repo-root>/tools/harness/manifest.yaml)",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=None,
        help="Directory containing <name>.yaml profiles (default: <repo-root>/tools/harness/profiles)",
    )
    parser.add_argument("--all", action="store_true", help="Generate bundles for every profile")
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        metavar="NAME",
        help="Profile name (without .yaml); repeatable",
    )
    ns = parser.parse_args(argv)
    root = ns.repo_root.resolve()
    ns.repo_root = root
    ns.manifest = (ns.manifest or (root / "tools" / "harness" / "manifest.yaml")).resolve()
    ns.profiles_dir = (ns.profiles_dir or (root / "tools" / "harness" / "profiles")).resolve()
    return ns


def main(argv: list[str] | None = None) -> int:
    """CLI entry: build one or more bundles."""
    args = parse_args(argv)
    if args.all and args.profiles:
        print("Cannot use --all together with --profile", file=sys.stderr)
        return 2
    if not args.all and not args.profiles:
        print("Specify --all or at least one --profile NAME", file=sys.stderr)
        return 2
    if args.all:
        names = list_profile_stems(args.profiles_dir)
    else:
        names = list(dict.fromkeys(args.profiles))

    try:
        run_build(args.repo_root, args.manifest, args.profiles_dir, names)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
