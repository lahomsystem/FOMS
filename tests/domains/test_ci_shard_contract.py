"""CI 본 스위트 조각 나누기(CI-SHARD-01) 계약.

ci.yml 의 조각 수와 FOMS_TEST_SHARD 의 N 이 어긋나면 일부 테스트 파일이 어느 조각에서도
돌지 않는다 — 조용히 빠지는 red 가 가장 비싸다. 1번 조각만 맡는 스텝(문서 계약·Redis·UI 구조·
디자인 lint)이 조각마다 세 번 돌거나 한 번도 안 도는 것도 막는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import json

from tests.conftest import ci_shard_plan

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


def _test_files() -> list[str]:
    """본 스위트가 모으는 파일 — ci.yml `Run tests` 의 --ignore 와 같게 tests/visual·harness 를 뺀다."""
    return sorted(
        rel
        for rel in (p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "tests").rglob("test_*.py"))
        if not rel.startswith(("tests/visual/", "tests/harness/"))
    )


def test_every_test_file_lands_in_exactly_one_shard() -> None:
    total = len(_shards())
    files = _test_files()
    assert len(files) > 500
    plan = ci_shard_plan(files, total)
    assert sorted(plan) == files  # 모든 파일이 정확히 한 번
    assert set(plan.values()) == set(range(1, total + 1))  # 빈 조각 없음
    # Windows 구분자로 넘겨도 같은 배정이다(로컬 = Linux CI).
    assert ci_shard_plan([f.replace("/", "\\") for f in files], total) == plan
    # 순서를 바꿔 넘겨도 같은 배정이다(xdist 워커마다 수집 순서가 달라도 된다).
    assert ci_shard_plan(list(reversed(files)), total) == plan


def test_recorded_durations_balance_shards() -> None:
    """기록 시간 기준 가장 무거운 조각이 평균보다 15% 넘게 무겁지 않다(crc32 때는 +20%)."""
    total = len(_shards())
    seconds = json.loads((REPO_ROOT / "tests" / "ci_shard_durations.json").read_text(encoding="utf-8"))["seconds"]
    files = _test_files()
    covered = sum(1 for f in files if f in seconds) / len(files)
    assert covered >= 0.6, f"조각 시간 기록이 낡았다({covered:.0%}) — tools/harness/refresh_ci_shard_durations.py"
    plan = ci_shard_plan(files, total)
    loads = [0.0] * total
    for f, shard in plan.items():
        loads[shard - 1] += seconds.get(f, 0.0)
    assert max(loads) <= sum(loads) / total * 1.15, loads


def test_conftest_hook_reads_shard_env() -> None:
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert re.search(r'os\.environ\.get\("FOMS_TEST_SHARD"', conftest)
    assert "config.hook.pytest_deselected(items=drop)" in conftest
