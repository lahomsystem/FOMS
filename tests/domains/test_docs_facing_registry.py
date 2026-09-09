"""CI-DOCSCOPE-01 레지스트리 계약 — 문서를 읽는 테스트가 목록 밖으로 새지 않는다.

문서만 바뀐 커밋(최근 100 런 중 44 건)에는 ``.github/workflows/ci.yml`` 이 전체
스위트 대신 "문서를 런타임에 읽는" 서브셋만 돌린다. 그 목록이 낡으면 문서 드리프트를
잡던 게이트가 조용히 빠진다 — 통과했는데 아무도 안 본 상태가 된다.

이 계약이 목록을 정직하게 유지한다. 메인 레인(tests/visual·tests/harness 제외)에서
docs/ 를 실제로 읽는 파일을 스캔해, 하나도 빠짐없이 ci.yml 서브셋에 들어 있는지 본다.
간접 노출(다른 테스트 모듈이 import 해서 실행되는 경우)도 인정한다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
TESTS_ROOT = REPO_ROOT / "tests"

# 메인 레인이 돌지 않는 트리(각자 별도 job 이 전담한다).
_OTHER_LANES = ("tests/visual/", "tests/harness/", "tests/postgres/")

# docs/ 경로 문자열을 담고 있는지.
_DOCS_REF = re.compile(r"""["']docs/|["']docs["']|DOCS_(?:ROOT|DIR|PATH)""")
# 파일시스템을 실제로 읽는지.
_FS_READ = re.compile(r"""read_text|read_bytes|open\(|rglob|\.glob\(|iterdir|is_file\(|exists\(\)""")


def _main_lane_test_files() -> list[Path]:
    """메인 레인이 수집하는 트리의 .py 파일 목록."""
    out: list[Path] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(f"{lane}") for lane in _OTHER_LANES):
            continue
        out.append(path)
    return out


def _docs_reading_files() -> set[str]:
    """docs/ 를 런타임에 읽는 메인 레인 파일의 저장소 상대 경로 집합."""
    found: set[str] = set()
    for path in _main_lane_test_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if _DOCS_REF.search(text) and _FS_READ.search(text):
            found.add(path.relative_to(REPO_ROOT).as_posix())
    return found


# 파일명이 ``test_*.py`` 가 아니라 pytest 가 직접 수집하지 않는다. 아래 러너가
# ``import *`` 로 재수출해 함께 돈다. 매핑이 낡으면
# test_indirect_runner_map_is_accurate 가 빨강이 된다.
_INDIRECTLY_RUN = {
    "tests/contracts/runtime/foms_namespace_surface_tests.py":
        "tests/domains/test_foms_namespace_imports.py",
}


def _declared_subset() -> set[str]:
    """ci.yml 의 문서 전용 스텝이 명시한 테스트 경로 집합."""
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    marker = "Run docs-facing contracts (docs-only change)"
    assert marker in text, f"ci.yml 에 문서 전용 스텝이 없다: {marker}"
    tail = text.split(marker, 1)[1]
    # 다음 스텝 경계에서 끊는다. 끊지 않으면 뒤따르는 Redis lane·UI 구조 스텝의
    # 경로까지 "등재됨" 으로 세어, 서브셋에서 빠진 파일을 놓칠 수 있다.
    boundary = re.search(r"\n    - name:", tail)
    if boundary:
        tail = tail[: boundary.start()]
    return set(re.findall(r"(tests/[\w/]+\.py)", tail))


def test_docs_only_subset_paths_all_exist() -> None:
    """ci.yml 이 가리키는 테스트 파일이 전부 실재한다(오타·이동 감지)."""
    declared = _declared_subset()
    assert declared, "ci.yml 문서 전용 스텝에서 테스트 경로를 못 찾았다"
    missing = sorted(p for p in declared if not (REPO_ROOT / p).is_file())
    assert not missing, f"ci.yml 문서 전용 서브셋이 없는 파일을 가리킨다: {missing}"


def test_every_docs_reading_test_is_covered_by_the_subset() -> None:
    """docs/ 를 읽는 메인 레인 테스트가 문서 전용 서브셋에서 빠지지 않았다."""
    declared = _declared_subset()

    uncovered: list[str] = []
    for rel in sorted(_docs_reading_files()):
        if rel in declared:
            continue
        runner = _INDIRECTLY_RUN.get(rel)
        if runner and runner in declared:
            continue
        uncovered.append(rel)

    assert not uncovered, (
        "docs/ 를 읽는데 ci.yml 문서 전용 서브셋에 없는 테스트: "
        + ", ".join(uncovered)
        + " — 문서만 바뀐 커밋에서 이 게이트가 조용히 빠진다. "
        ".github/workflows/ci.yml 의 'Run docs-facing contracts' 스텝에 추가하라."
    )


def test_indirect_runner_map_is_accurate() -> None:
    """간접 실행 매핑이 실제 import 관계와 일치한다(매핑이 거짓말하지 않는다)."""
    for target, runner in _INDIRECTLY_RUN.items():
        target_path = REPO_ROOT / target
        runner_path = REPO_ROOT / runner
        assert target_path.is_file(), f"간접 실행 대상이 없다: {target}"
        assert runner_path.is_file(), f"간접 실행 러너가 없다: {runner}"
        module_stem = Path(target).stem
        runner_text = runner_path.read_text(encoding="utf-8", errors="replace")
        assert module_stem in runner_text, (
            f"{runner} 가 더 이상 {module_stem} 를 실행하지 않는다 — "
            "_INDIRECTLY_RUN 매핑을 갱신하라."
        )
