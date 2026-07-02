"""PTC (Physical Tree Convergence) contract gates per
`docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`.

Uses **committed** tree (``git ls-tree HEAD`` / ``git ls-files``) for root and ``data/`` policy.
See ``docs/specs/2026-04-07-repo-structure-governance_SPEC.md`` §2.6.1–2.6.2.
Runtime/common rationale: ``docs/context/PTC_RUNTIME_COMMON_INVENTORY.md``.

File name is ``test_*.py`` so ``pytest tests`` collects these gates (unlike ``foms_namespace_surface_tests.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Three levels below repo root: tests/contracts/runtime/
_REPO_ROOT = Path(__file__).resolve().parents[3]

# §2.6.1 Final root allowlist (exact set; dual-spec lock)
_PTC_ROOT_ALLOWLIST: frozenset[str] = frozenset(
    {
        ".agents",
        ".claude",
        ".cursor",
        ".github",
        ".vscode",
        "Add In Program",
        "data",
        "docs",
        "foms",
        "migrations",
        "SCheduler",
        "scripts",
        "static",
        "templates",
        "tests",
        "tools",
        ".dockerignore",
        ".gcloudignore",
        ".gitattributes",
        ".gitignore",
        ".python-version",
        "AGENTS.md",
        "alembic.ini",
        "app.py",
        "CLAUDE.md",
        "db.py",
        "Dockerfile",
        "models.py",
        "Procfile",
        "predeploy.sh",
        "README.md",
        "railway.toml",
        "railway-worker.toml",
        "railway-cron.toml",
        "requirements.txt",
        "run.py",
        "skills-lock.json",
        "start.sh",
        "wdcalculator_db.py",
        "wdcalculator_models.py",
    }
)

# §4.5.1 static/js/runtime/
_PTC_RUNTIME_JS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "blueprint-viewer-global.js",
        "column-resizer.js",
        "common_utils.js",
        "erp-mobile-shell.js",
        "erp-shell.js",
        "foms-theme-boot.js",
        "layout-head-init.js",
        "layout-scripts-chat.js",
        "layout-scripts-core.js",
        "script.js",
        "upload-progress.js",
    }
)

# §4.5.2 foms/services/common/
_PTC_FOMS_SERVICES_COMMON_ALLOWLIST: frozenset[str] = frozenset(
    {
        "__init__.py",
        "address_ai_ops_loader.py",
        "address_converter.py",
        "business_calendar.py",
        "dashboard_cache.py",
        "ept_b7_profile.py",
        "erp_mine_filter.py",
        "erp_navigation_contract.py",
        "erp_shell_http.py",
        "geocode_config.py",
        "map_generator.py",
    }
)

# FR20 — page-first vs API-first authoritative README.md (§2.2.3 / §2.6.3)
_PTC_FR20_PAGE_FIRST: frozenset[str] = frozenset(
    {
        "orders",
        "measurement",
        "shipment",
        "drawing",
        "production",
        "construction",
        "cs",
        "wdcalculator",
        "admin",
        "auth",
    }
)
_PTC_FR20_API_FIRST: frozenset[str] = frozenset({"channel", "files", "notifications"})


def _git_repo_root() -> Path:
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(r.stdout.strip()).resolve()


def _git_ls_tree_root_names(repo_root: Path) -> set[str]:
    """Tracked top-level names at HEAD (committed tree)."""
    r = subprocess.run(
        ["git", "ls-tree", "--name-only", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def _git_ls_files_under(repo_root: Path, prefix: str) -> list[str]:
    r = subprocess.run(
        ["git", "ls-files", "--", prefix],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def test_ptc_committed_root_allowlist_exact() -> None:
    """Committed root entries must match §2.6.1 exact allowlist (no extras, no omissions)."""
    root = _git_repo_root()
    actual = _git_ls_tree_root_names(root)
    assert actual == _PTC_ROOT_ALLOWLIST, (
        "committed root allowlist drift (see 2026-04-07 §2.6.1):\n"
        f"  only_in_repo={sorted(actual - _PTC_ROOT_ALLOWLIST)}\n"
        f"  missing_from_repo={sorted(_PTC_ROOT_ALLOWLIST - actual)}"
    )


def test_ptc_static_js_runtime_inventory_exact() -> None:
    """``static/js/runtime/`` must contain exactly §4.5.1 files."""
    js_dir = _REPO_ROOT / "static" / "js" / "runtime"
    assert js_dir.is_dir(), f"missing {js_dir.relative_to(_REPO_ROOT)}"
    actual = {p.name for p in js_dir.iterdir() if p.is_file()}
    assert actual == _PTC_RUNTIME_JS_ALLOWLIST, (
        "static/js/runtime/ inventory drift (PTC §4.5.1):\n"
        f"  expected={sorted(_PTC_RUNTIME_JS_ALLOWLIST)}\n"
        f"  actual={sorted(actual)}"
    )


def test_ptc_foms_services_common_inventory_exact() -> None:
    """``foms/services/common/`` must contain exactly §4.5.2 files."""
    pkg = _REPO_ROOT / "foms" / "services" / "common"
    assert pkg.is_dir(), f"missing {pkg.relative_to(_REPO_ROOT)}"
    actual = {p.name for p in pkg.iterdir() if p.is_file()}
    assert actual == _PTC_FOMS_SERVICES_COMMON_ALLOWLIST, (
        "foms/services/common/ inventory drift (PTC §4.5.2):\n"
        f"  expected={sorted(_PTC_FOMS_SERVICES_COMMON_ALLOWLIST)}\n"
        f"  actual={sorted(actual)}"
    )


def test_ptc_tracked_data_forbids_runtime_output_paths() -> None:
    """Tracked ``data/`` must not include dumps/localdb trees or ``*.db`` (§2.6.2; PTC §4.3)."""
    root = _git_repo_root()
    tracked = _git_ls_files_under(root, "data/")
    bad: list[str] = []
    for rel in tracked:
        rp = rel.replace("\\", "/")
        if rp.startswith("data/dumps/") or rp.startswith("data/localdb/"):
            bad.append(rel)
        if rp.endswith(".db"):
            bad.append(rel)
    assert not bad, "tracked data/ must not include runtime output paths:\n" + "\n".join(bad)


def test_ptc_fr20_readme_authoritative_one_per_context() -> None:
    """Each FR20 context has exactly one authoritative README (§2.2.3 / §2.6.3)."""
    missing: list[str] = []
    for ctx in sorted(_PTC_FR20_PAGE_FIRST):
        p = _REPO_ROOT / "foms" / "web" / ctx / "README.md"
        if not p.is_file():
            missing.append(str(p.relative_to(_REPO_ROOT)))
    for ctx in sorted(_PTC_FR20_API_FIRST):
        p = _REPO_ROOT / "foms" / "api" / ctx / "README.md"
        if not p.is_file():
            missing.append(str(p.relative_to(_REPO_ROOT)))
    assert not missing, "FR20 authoritative README.md missing:\n" + "\n".join(missing)


def test_ptc_fr20_readme_no_extra_static_js_wdcalculator() -> None:
    """``static/js/wdcalculator/README.md`` must be absent (FAG-B1 uniqueness gate).

    FR20 authoritative home for wdcalculator is ``foms/web/wdcalculator/README.md``.
    The static-JS chunk map was relocated to ``docs/context/wdcalculator-static-js-chunk-map.md``.
    Any README inside ``static/js/wdcalculator/`` would create a duplicate FR20 home.
    """
    forbidden = _REPO_ROOT / "static" / "js" / "wdcalculator" / "README.md"
    assert not forbidden.exists(), (
        "Duplicate FR20 README found: static/js/wdcalculator/README.md must be absent. "
        "Chunk map technical doc belongs in docs/context/wdcalculator-static-js-chunk-map.md "
        "(FAG-B1 §3.3 uniqueness lock)."
    )


def test_ptc_fr20_chunk_map_doc_present() -> None:
    """``docs/context/wdcalculator-static-js-chunk-map.md`` must exist (FAG-B1 relocation gate).

    The chunk map was relocated from ``static/js/wdcalculator/README.md``.
    """
    chunk_map = _REPO_ROOT / "docs" / "context" / "wdcalculator-static-js-chunk-map.md"
    assert chunk_map.is_file(), (
        "Missing docs/context/wdcalculator-static-js-chunk-map.md — "
        "chunk map must be present after FAG-B1 relocation."
    )
