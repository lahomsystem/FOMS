"""CI-VISUAL-01 레지스트리 계약 — tests/visual 이 CI 밖으로 새지 않는다.

본 스위트는 ``--ignore=tests/visual`` 라 tests/visual 은 ``.github/workflows/ci.yml``
의 "Run UI structural tests" 스텝에 **명시 등재된 파일만** 돈다. 목록이 낡으면 red 가
조용히 산다 — ``test_erp_order_edit_mobile_form.py`` 의 red 가 2주 반 살아 있었다.

이 계약이 목록을 정직하게 유지한다. tests/visual 의 모든 ``test_*.py`` 는
(1) ci.yml 스텝에 등재됐거나 (2) 아래 ``_BROWSER_REQUIRED`` 에 이유와 함께 제외돼야
한다. 새 파일은 둘 중 하나를 고르기 전까지 빨강이다.

분류가 장부로만 남지 않도록 양쪽을 실제 코드로 대조한다 — 제외 목록의 파일은 정말
브라우저 픽스처를 요구해야 하고, 등재된 파일의 브라우저 테스트에는 skip 가드가 있어야
한다(가드 없이 등재하면 CI 가 ``-p no:playwright`` 에서 error 를 낸다).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
VISUAL_ROOT = REPO_ROOT / "tests" / "visual"
CI_STEP_MARKER = "Run UI structural tests (no Playwright PNG regression)"

# 실제 브라우저(Playwright page)나 파일 SQLite 라이브 서버가 있어야 도는 파일.
# CI 의 UI 구조 스텝은 -p no:playwright + sqlite:///:memory: 라 여기 것들은 error 가 된다.
# 로컬/전용 레인에서만 돈다(pre_push_smoke 의 `pytest tests/visual`).
_BROWSER_REQUIRED: dict[str, str] = {
    "tests/visual/test_erp_mobile_v2_shell_regression.py":
        "ERP v2 셸 PNG 회귀 — page + 파일 SQLite 라이브 서버",
    "tests/visual/test_mobile_date_chip_compact.py":
        "모바일 날짜 칩 레이아웃 실측 — page + 라이브 서버",
    "tests/visual/test_p1_mobile_ux_smoke.py":
        "P1 모바일/태블릿 UX 스모크 — page + 라이브 서버",
    "tests/visual/test_scheduler_panel_compact.py":
        "레거시 스케줄러 패널 실측 — page + 라이브 서버",
    "tests/visual/test_visual_regression.py":
        "주문 목록 PNG 베이스라인 비교 — page + 라이브 서버",
}

# tests/visual/conftest.py 가 제공하는 브라우저·라이브 서버 픽스처.
_BROWSER_FIXTURES = frozenset({
    "page",
    "dark_mode_page",
    "visual_live_server",
    "visual_live_server_legacy",
    "visual_live_server_erp_v2",
    "visual_cohort_user_id",
})


def _visual_test_files() -> set[str]:
    """tests/visual 의 저장소 상대 경로 집합(``test_*.py`` 만)."""
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(VISUAL_ROOT.glob("test_*.py"))
    }


def _registered_paths() -> set[str]:
    """ci.yml UI 구조 스텝이 명시한 테스트 경로 집합."""
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert CI_STEP_MARKER in text, f"ci.yml 에 UI 구조 스텝이 없다: {CI_STEP_MARKER}"
    tail = text.split(CI_STEP_MARKER, 1)[1]
    # 다음 스텝 경계에서 끊는다 — 안 끊으면 뒤 스텝 경로까지 "등재됨" 으로 샌다.
    boundary = re.search(r"\n    - name:", tail)
    if boundary:
        tail = tail[: boundary.start()]
    return set(re.findall(r"(tests/visual/[\w/]+\.py)", tail))


def _browser_tests(rel_path: str) -> dict[str, bool]:
    """
    파일 안 브라우저 픽스처를 요구하는 테스트 → skip 가드 보유 여부.

    Args:
        rel_path: 저장소 상대 경로.

    Returns:
        {테스트 함수명: skip 데코레이터 보유 여부}.
    """
    tree = ast.parse((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    out: dict[str, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        params = {arg.arg for arg in node.args.args} | {
            arg.arg for arg in node.args.kwonlyargs
        }
        if not (params & _BROWSER_FIXTURES):
            continue
        guarded = any(
            "skip" in ast.dump(decorator) for decorator in node.decorator_list
        )
        out[node.name] = guarded
    return out


def test_every_visual_file_is_registered_or_excluded() -> None:
    """새 tests/visual 파일은 등재하거나 이유를 붙여 제외해야 한다."""
    classified = _registered_paths() | set(_BROWSER_REQUIRED)
    unclassified = sorted(_visual_test_files() - classified)
    assert not unclassified, (
        "tests/visual 파일이 CI 등재도 제외 목록도 아니다 — ci.yml UI 구조 스텝에 넣거나 "
        f"_BROWSER_REQUIRED 에 이유와 함께 올려라: {unclassified}"
    )


def test_registry_paths_all_exist() -> None:
    """등재·제외 목록이 실재하는 파일만 가리킨다(이름 변경·삭제 감지)."""
    declared = _registered_paths() | set(_BROWSER_REQUIRED)
    assert declared, "ci.yml UI 구조 스텝에서 테스트 경로를 못 찾았다"
    missing = sorted(p for p in declared if not (REPO_ROOT / p).is_file())
    assert not missing, f"레지스트리가 없는 파일을 가리킨다: {missing}"


def test_registered_and_excluded_do_not_overlap() -> None:
    """같은 파일이 등재와 제외에 동시에 있으면 분류가 거짓말이다."""
    overlap = sorted(_registered_paths() & set(_BROWSER_REQUIRED))
    assert not overlap, f"등재와 제외에 동시에 있다: {overlap}"


def test_excluded_files_really_need_a_browser() -> None:
    """제외 목록은 장부가 아니다 — 실제로 브라우저 픽스처를 요구해야 한다."""
    wrongly_excluded = sorted(
        rel for rel in _BROWSER_REQUIRED if not _browser_tests(rel)
    )
    assert not wrongly_excluded, (
        "브라우저 픽스처를 안 쓰는데 제외돼 있다 — CI 에 등재하라: "
        f"{wrongly_excluded}"
    )


def test_registered_browser_tests_carry_a_skip_guard() -> None:
    """등재 파일 안 브라우저 테스트는 skip 가드가 있어야 CI 가 error 를 안 낸다."""
    unguarded: list[str] = []
    for rel in sorted(_registered_paths()):
        for name, guarded in _browser_tests(rel).items():
            if not guarded:
                unguarded.append(f"{rel}::{name}")
    assert not unguarded, (
        "CI 등재 파일에 가드 없는 브라우저 테스트가 있다 — -p no:playwright 에서 error 다: "
        f"{unguarded}"
    )


def test_every_excluded_file_has_a_reason() -> None:
    """제외 사유가 빈 문자열이면 다음 사람이 판단할 근거가 없다."""
    blank = sorted(rel for rel, why in _BROWSER_REQUIRED.items() if not why.strip())
    assert not blank, f"제외 사유가 비었다: {blank}"
