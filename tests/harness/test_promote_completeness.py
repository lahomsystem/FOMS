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


# ── 파일 단위 바탕 비교 (SPEC 2026-10-13-promote-completeness-content-aware §5) ──

_C = ("-c", "user.email=t@t", "-c", "user.name=t")


def _commit(local: Path, files: dict[str, str | None], msg: str) -> str:
    """files 를 쓰거나(None 이면 삭제) 커밋하고 SHA 반환."""
    for name, content in files.items():
        if content is None:
            _git(local, "rm", "-q", name)
        else:
            (local / name).write_text(content, encoding="utf-8")
            _git(local, "add", name)
    _git(local, *_C, "commit", "-m", msg)
    return _sha(local)


def _init(tmp_path: Path, files: dict[str, str]) -> Path:
    """production 에 files 를 올린 저장소(로컬 production 체크아웃)."""
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "production")
    _commit(local, dict(files), "base")
    _git(local, "push", "-u", "origin", "production")
    return local


def test_squashed_deps_are_content_same(tmp_path: Path) -> None:
    """의존 커밋을 squash 해 다른 patch-id 로 production 에 반영 → complete, content_same."""
    mod = _load()
    local = _init(tmp_path, {"shared.txt": "base\n"})
    _git(local, "checkout", "-b", "deploy")
    dep1 = _commit(local, {"shared.txt": "dep1\n"}, "dep1")
    dep2 = _commit(local, {"shared.txt": "dep2\n"}, "dep2")
    feat = _commit(local, {"shared.txt": "feat\n"}, "feat")
    _git(local, "checkout", "production")
    _commit(local, {"shared.txt": "dep2\n"}, "squashed promo")
    _git(local, "push", "origin", "production")
    _git(local, "checkout", "deploy")

    result = mod.analyze_promote_completeness(str(local), [feat], base_ref="origin/production")
    assert result.complete is True
    assert result.missing == ()
    assert result.files_status == {"shared.txt": "same"}
    assert result.equivalent_reasons.get(dep1) == "content_same"
    assert result.equivalent_reasons.get(dep2) == "content_same"


def test_pin_only_difference_is_complete(tmp_path: Path) -> None:
    """바탕이 자산 핀 줄만 다름 → complete, pin_only."""
    mod = _load()
    page = 'x\n<script src="a.js?v=20261012{}"></script>\n'
    local = _init(tmp_path, {"page.html": page.format("r")})
    _git(local, "checkout", "-b", "deploy")
    dep = _commit(local, {"page.html": page.format("d")}, "dep pin")
    feat = _commit(local, {"page.html": page.format("e").replace("x\n", "y\n")}, "feat")

    result = mod.analyze_promote_completeness(str(local), [feat], base_ref="origin/production")
    assert result.complete is True
    assert result.files_status == {"page.html": "pin_only"}
    assert result.equivalent_reasons.get(dep) == "content_same"
    assert mod.verdict_line(result).startswith("판정: 올려도 됨")
    assert "핀만 다름 1" in mod.verdict_line(result)


def test_real_difference_missing_only_that_file(tmp_path: Path) -> None:
    """실제 내용 다름 → incomplete, missing 은 그 파일 커밋만."""
    mod = _load()
    local = _init(tmp_path, {"a.txt": "a\n", "b.txt": "b\n"})
    _git(local, "checkout", "-b", "deploy")
    dep_a = _commit(local, {"a.txt": "a2\n"}, "dep a")
    dep_b = _commit(local, {"b.txt": "b2\n"}, "dep b")
    _git(local, "checkout", "production")
    _commit(local, {"b.txt": "b2\n"}, "b via other route")
    _git(local, "push", "origin", "production")
    _git(local, "checkout", "deploy")
    feat = _commit(local, {"a.txt": "a3\n", "b.txt": "b3\n"}, "feat")

    result = mod.analyze_promote_completeness(str(local), [feat], base_ref="origin/production")
    assert result.complete is False
    assert result.files_status == {"a.txt": "differs", "b.txt": "same"}
    assert {m.sha for m in result.missing} == {dep_a}
    assert result.equivalent_reasons.get(dep_b) == "content_same"
    assert mod.verdict_line(result) == "판정: 진짜 누락 1개 — 내용 다른 파일: a.txt"


def test_file_added_or_deleted_is_differs(tmp_path: Path) -> None:
    """파일이 한쪽에만 있음(추가·삭제) → differs."""
    mod = _load()
    local = _init(tmp_path, {"keep.txt": "k\n", "gone.txt": "g\n"})
    _git(local, "checkout", "-b", "deploy")
    dep = _commit(local, {"new.txt": "n\n", "gone.txt": None}, "dep add+del")
    feat = _commit(local, {"new.txt": "n2\n", "gone.txt": "back\n"}, "feat")

    result = mod.analyze_promote_completeness(str(local), [feat], base_ref="origin/production")
    assert result.files_status == {"gone.txt": "differs", "new.txt": "differs"}
    assert result.complete is False
    assert {m.sha for m in result.missing} == {dep}
