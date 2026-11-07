"""큰 시험 줄 서기 · 문서만 바뀐 푸시의 빠른 길 — 설계서 docs/specs/2026-11-07-test-run-speed_SPEC.md."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tests import _big_run_lock as lock

ROOT = Path(__file__).resolve().parents[2]


def _docs_only_module():
    spec = importlib.util.spec_from_file_location("smoke_docs_only", ROOT / "tools/harness/smoke_docs_only.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- §2.1 줄 서기 판정 -------------------------------------------------------------
def test_big_run_locks_only_windows_master_with_two_or_more_workers() -> None:
    assert lock.should_lock("win32", False, 4, {}) is True
    assert lock.should_lock("win32", False, "auto", {}) is True
    assert lock.should_lock("win32", False, 1, {}) is False  # 한 프로세스로 몇 파일 — 기다리지 않는다
    assert lock.should_lock("win32", False, None, {}) is False  # xdist 없이
    assert lock.should_lock("win32", True, 4, {}) is False  # xdist 일꾼은 줄을 서지 않는다(주인이 선다)
    assert lock.should_lock("linux", False, 4, {}) is False  # CI 무변화
    assert lock.should_lock("win32", False, 4, {"FOMS_PYTEST_NO_LOCK": "1"}) is False


def test_conftest_wires_the_lock_into_configure_and_unconfigure() -> None:
    src = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    assert "_big_run_lock.configure(config)" in src
    assert "_big_run_lock.unconfigure(config)" in src


def test_lock_survives_a_dead_holder_and_has_an_upper_bound() -> None:
    src = (ROOT / "tests/_big_run_lock.py").read_text(encoding="utf-8")
    assert "_WAIT_ABANDONED" in src  # 죽은 시험이 줄을 막지 못한다
    assert lock.MAX_WAIT_S == 30 * 60  # 걸린 시험이 모두를 영영 막지 못한다


# --- §2.2 문서만 바뀐 푸시 -----------------------------------------------------------
def test_docs_only_classification() -> None:
    m = _docs_only_module()
    assert m.is_docs_only(["docs/AI_STATUS.md"]) is True
    assert m.is_docs_only(["docs/specs/a_SPEC.md", "docs/guides/b.md"]) is True
    assert m.is_docs_only(["docs/AI_STATUS.md", "app.py"]) is False
    assert m.is_docs_only(["docs/harness/foms_failopen_inventory.json"]) is False  # 코드에서 만드는 파일
    assert m.is_docs_only(["CLAUDE.md"]) is False  # 하네스 정본은 전체 스위트
    assert m.is_docs_only([]) is False


def test_docs_reading_tests_are_found_not_listed_by_hand() -> None:
    m = _docs_only_module()
    found = m.doc_reading_tests(ROOT)
    assert "tests/harness/test_hook_log_hygiene.py" in found  # AI_STATUS 상단 4,000자 예산
    assert "tests/harness/test_test_run_speed.py" in found or len(found) > 50
    every = [p for p in (ROOT / "tests").rglob("test_*.py") if "__pycache__" not in p.parts]
    assert len(found) < len(every)  # 전체가 아니라 고른 것


def test_smoke_keeps_the_full_suite_and_adds_the_fast_path_only_for_docs() -> None:
    src = (ROOT / "scripts/ops/pre_push_smoke.ps1").read_text(encoding="utf-8-sig")
    assert "tools/harness/smoke_docs_only.py --since-ref origin/deploy" in src
    assert "-not $Full -and -not $Visual" in src
    assert "-m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright -n auto --dist loadfile" in src
    assert "-m pytest -q tests/visual -p no:playwright -n auto --dist loadfile" in src
