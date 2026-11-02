"""CI 본 스위트 조각 나누기(CI-SHARD-01) 계약.

ci.yml 의 조각 수와 FOMS_TEST_SHARD 의 N 이 어긋나면 일부 테스트 파일이 어느 조각에서도
돌지 않는다 — 조용히 빠지는 red 가 가장 비싸다. 1번 조각만 맡는 스텝(문서 계약·Redis·UI 구조·
디자인 lint)이 조각마다 세 번 돌거나 한 번도 안 도는 것도 막는다.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import ci_shard_of

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SHARD_ONE_STEPS = (
    "Run design SSOT lint",
    "Run docs-facing contracts (docs-only change)",
    "Run Redis lane (RQ positive path / rq API drift)",
    "Run UI structural tests (no Playwright PNG regression)",
)


def _ci_text() -> str:
    # CI 러너에는 PyYAML 이 없다(requirements 밖) — 글자로 읽는다.
    return CI_WORKFLOW.read_text(encoding="utf-8").replace("\r\n", "\n")


def _shards() -> list[int]:
    match = re.search(r"^\s+shard: \[([\d,\s]+)\]\s*$", _ci_text(), re.MULTILINE)
    assert match, "ci.yml test 잡에 matrix.shard 목록이 없다"
    return [int(x) for x in match.group(1).split(",")]


def _step_block(name: str) -> str:
    text = _ci_text()
    start = text.index(f"    - name: {name}\n")
    end = text.find("\n    - name:", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_matrix_and_shard_env_agree() -> None:
    shards = _shards()
    assert shards == list(range(1, len(shards) + 1)) and len(shards) >= 2
    assert re.search(r"^\s+fail-fast: false\s*$", _ci_text(), re.MULTILINE)
    expected = 'FOMS_TEST_SHARD: "${{ matrix.shard }}/' + str(len(shards)) + '"'
    assert expected in _step_block("Run tests")


def test_single_owner_steps_run_on_shard_one_only() -> None:
    for name in SHARD_ONE_STEPS:
        if_line = next(
            (line for line in _step_block(name).splitlines() if line.strip().startswith("if:")), ""
        )
        assert "matrix.shard == 1" in if_line, name


def test_every_test_file_lands_in_exactly_one_shard() -> None:
    total = len(_shards())
    files = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "tests").rglob("test_*.py")
    )
    assert len(files) > 500
    owners = [ci_shard_of(f, total) for f in files]
    assert all(1 <= o <= total for o in owners)
    assert set(owners) == set(range(1, total + 1))  # 빈 조각 없음
    # 같은 경로는 운영체제 구분자와 무관하게 같은 조각이다(Windows 로컬 = Linux CI).
    assert all(ci_shard_of(f.replace("/", "\\"), total) == ci_shard_of(f, total) for f in files[:50])


def test_conftest_hook_reads_shard_env() -> None:
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert re.search(r'os\.environ\.get\("FOMS_TEST_SHARD"', conftest)
    assert "config.hook.pytest_deselected(items=drop)" in conftest
