"""promote_completeness TDD — baseline 구멍 vs cherry-pick 동등."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    path = REPO_ROOT / "tools" / "harness" / "promote_completeness.py"
    name = "promote_completeness_ut"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def _sha(cwd: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cwd, text=True
    ).strip()


def _setup_repo(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """production=base, deploy=dep→feat on shared.txt. Returns local, bare, dep, feat."""
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "production")
    (local / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")
    _git(local, "push", "-u", "origin", "production")

    _git(local, "checkout", "-b", "deploy")
    (local / "shared.txt").write_text("dep\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "dep")
    dep = _sha(local)

    (local / "shared.txt").write_text("feat\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "feat")
    feat = _sha(local)
    _git(local, "push", "-u", "origin", "deploy")
    return local, bare, dep, feat


def test_feat_only_reports_missing_dep(tmp_path: Path) -> None:
    """feat만 승격 시 같은 파일 dep 이 cherry+ 로 missing."""
    mod = _load()
    local, _bare, dep, feat = _setup_repo(tmp_path)
    result = mod.analyze_promote_completeness(
        str(local), [feat], base_ref="origin/production"
    )
    assert result.complete is False
    missing = {m.sha.lower() for m in result.missing}
    assert dep.lower() in missing
    assert feat.lower() not in missing


def test_cherry_equivalent_dep_not_missing(tmp_path: Path) -> None:
    """dep를 production에 cherry-pick 하면 원본 dep SHA는 missing에서 제외."""
    mod = _load()
    local, _bare, dep, feat = _setup_repo(tmp_path)

    _git(local, "fetch", "origin", "production")
    _git(local, "checkout", "production")
    _git(local, "reset", "--hard", "origin/production")
    _git(
        local,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "cherry-pick",
        dep,
    )
    _git(local, "push", "origin", "HEAD:production")
    _git(local, "checkout", "deploy")

    result = mod.analyze_promote_completeness(
        str(local), [feat], base_ref="origin/production"
    )
    assert result.complete is True
    missing = {m.sha.lower() for m in result.missing}
    assert dep.lower() not in missing


def test_promote_set_includes_dep_is_complete(tmp_path: Path) -> None:
    """dep+feat 모두 promote 집합이면 missing 없음."""
    mod = _load()
    local, _bare, dep, feat = _setup_repo(tmp_path)
    result = mod.analyze_promote_completeness(
        str(local), [dep, feat], base_ref="origin/production"
    )
    assert result.complete is True
    assert result.missing == ()


def test_already_cherry_equivalent_promote_sha_is_complete(tmp_path: Path) -> None:
    """승격 SHA 자체가 cherry - 이면 dep 스캔 없이 COMPLETE."""
    mod = _load()
    local, _bare, dep, feat = _setup_repo(tmp_path)
    _git(local, "fetch", "origin", "production")
    _git(local, "checkout", "production")
    _git(local, "reset", "--hard", "origin/production")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "cherry-pick", dep)
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "cherry-pick", feat)
    _git(local, "push", "origin", "HEAD:production")
    _git(local, "checkout", "deploy")

    result = mod.analyze_promote_completeness(
        str(local), [feat], base_ref="origin/production"
    )
    assert result.complete is True
    assert result.missing == ()
