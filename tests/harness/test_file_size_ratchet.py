r"""파일 크기 래칫 계약 (검토 보고서 ④ '지금' 2번 · T2 ①).

CLAUDE.md 의 "함수 50줄 이하 / 인라인 script 300줄 초과 시 분리 / 템플릿 800줄 초과 시
partial 분리" 는 사람이 읽는 판단 규칙이라 에이전트 속도로는 지켜지지 않았다(실측 최대
파이썬 5,999줄 · JS 6,085줄). 이 계약은 그 규칙을 **동결 래칫**으로 옮긴다.

- 기준선 = 지금 임계 이상인 파일들의 **경로 집합**(`file_size_baseline.json`).
- red 가 되는 것은 **순증**뿐이다. 기준선에 없는 큰 파일이 새로 생기면 실패한다.
- 기존 큰 파일이 더 커지는 것, 임계 아래로 줄어드는 것(역방향 래칫)은 이 계약의 범위가 아니다.
  줄어든 파일을 red 로 만들면 분해 작업 자체가 벌을 받는다.

줄 수 정의는 `read().splitlines()` 의 길이다. `wc -l` 은 마지막 줄의 개행 유무로 값이
갈리므로 쓰지 않는다.

스캔 범위는 **저장소 전체에서 산출물·가상환경 계열만 뺀 것**이다. 추적하는 소스 트리를
`excluded_dirs` 에 넣어 스캔을 좁히면 그 트리의 새 대형 파일을 래칫이 영영 못 잡으므로,
`EXPECTED_EXCLUDED_DIRS` 정확 일치 assert 와 모집단 비어 있지 않음 assert 로 막아 둔다.

기준선 재생성 (저장소 루트에서 실행. 개행은 CRLF 로 유지된다):

    python -c "import json,sys; sys.path.insert(0,'tests/harness'); import test_file_size_ratchet as m; b=m.load_baseline(); b['known_large_python']=sorted(m.scan_large_files('.py',b['limits']['py'],set(b['excluded_dirs']))); b['known_large_javascript']=sorted(m.scan_large_files('.js',b['limits']['js'],set(b['excluded_dirs']))); m.BASELINE_PATH.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\r\n')"

재생성 후 diff 를 사람이 읽어 새 항목이 의도된 것인지 확인한다 — 무조건 재생성은 래칫을
자동 무력화한다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "file_size_baseline.json"
SCHEMA_ID = "file-size-ratchet/1"
EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "limits",
    "excluded_dirs",
    "known_large_python",
    "known_large_javascript",
}
# 스캔에서 뺄 수 있는 것은 산출물·가상환경 계열뿐이다. 추적하는 소스 트리를 여기에
# 넣는 것은 스캔 범위 축소이며, 아래 정확 일치 assert 가 그것을 red 로 만든다.
EXPECTED_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def load_baseline() -> dict[str, Any]:
    """기준선 JSON 을 읽어 dict 로 돌려준다.

    Returns:
        `file_size_baseline.json` 의 최상위 매핑.
    """
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def count_lines(path: Path) -> int:
    """파일의 줄 수를 센다 (`splitlines()` 기준, `wc -l` 아님).

    Args:
        path: 셀 파일의 절대 경로.

    Returns:
        `read().splitlines()` 의 길이.
    """
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def iter_source_files(suffix: str, excluded_dirs: set[str]) -> Iterator[Path]:
    """스캔 모집단(대상 확장자 파일)을 하나씩 돌려준다.

    Args:
        suffix: 대상 확장자 (`.py` 또는 `.js`).
        excluded_dirs: 이름이 일치하면 통째로 건너뛸 디렉토리 이름 집합.

    Yields:
        조건에 맞는 파일의 절대 경로.
    """
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        for filename in filenames:
            if filename.endswith(suffix):
                yield Path(dirpath) / filename


def scan_large_files(suffix: str, limit: int, excluded_dirs: set[str]) -> dict[str, int]:
    """저장소를 훑어 임계 이상인 파일을 찾는다.

    Args:
        suffix: 대상 확장자 (`.py` 또는 `.js`).
        limit: 이 줄 수 **이상**이면 큰 파일로 본다.
        excluded_dirs: 이름이 일치하면 통째로 건너뛸 디렉토리 이름 집합.

    Returns:
        저장소 상대 슬래시 경로 → 줄 수 매핑.
    """
    found: dict[str, int] = {}
    for absolute in iter_source_files(suffix, excluded_dirs):
        lines = count_lines(absolute)
        if lines >= limit:
            found[absolute.relative_to(REPO_ROOT).as_posix()] = lines
    return found


def format_new_violations(
    label: str, baseline_key: str, limit: int, new_files: dict[str, int]
) -> str:
    """실패 메시지를 만든다 (새 위반 목록 + 되돌리는 법 포함).

    Args:
        label: 사람이 읽을 언어 이름 ("파이썬" / "JavaScript").
        baseline_key: 예외 등재 시 손댈 기준선 배열 이름.
        limit: 임계 줄 수.
        new_files: 기준선에 없는 큰 파일들(경로 → 줄 수).

    Returns:
        assert 에 붙일 여러 줄 메시지.
    """
    rows = "\n".join(f"  {path} ({lines}줄)" for path, lines in sorted(new_files.items()))
    return (
        f"기준선에 없는 새 대형 {label} 파일 {len(new_files)}개 (임계 {limit}줄):\n"
        f"{rows}\n\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"되돌리는 법 (둘 중 하나):\n"
        f"  1) 권장 — 파일을 {limit}줄 미만으로 쪼갠다. 이 계약의 목적이 그것이다.\n"
        f"  2) 어쩔 수 없는 예외라면 위 경로를 기준선의 '{baseline_key}' 배열에\n"
        f"     저장소 상대 슬래시 경로로 넣고 정렬(sorted)을 유지한다.\n"
        f"     예외를 늘리는 것은 부채를 늘리는 것이니 이유를 커밋 메시지에 남긴다.\n"
        f"  * `excluded_dirs` 에 소스 트리를 넣어 스캔을 좁히는 것은 우회다 —\n"
        f"    EXPECTED_EXCLUDED_DIRS 정확 일치 assert 가 그 길을 막아 둔다."
    )


def collect_new_large_files(suffix: str, limit_key: str, baseline_key: str) -> dict[str, int]:
    """지금 스캔 결과에서 기준선에 없는 큰 파일만 골라낸다.

    Args:
        suffix: 대상 확장자.
        limit_key: `limits` 안의 키 ("py" 또는 "js").
        baseline_key: 기준선 배열 이름.

    Returns:
        기준선에 없는 큰 파일들(경로 → 줄 수).
    """
    baseline = load_baseline()
    limit = int(baseline["limits"][limit_key])
    excluded = set(baseline["excluded_dirs"])
    known = set(baseline[baseline_key])
    current = scan_large_files(suffix, limit, excluded)
    return {path: lines for path, lines in current.items() if path not in known}


def test_no_new_large_python_files() -> None:
    """기준선에 없는 500줄 이상 파이썬 파일이 새로 생기면 실패한다."""
    baseline = load_baseline()
    limit = int(baseline["limits"]["py"])
    new_files = collect_new_large_files(".py", "py", "known_large_python")
    assert not new_files, format_new_violations(
        "파이썬", "known_large_python", limit, new_files
    )


def test_no_new_large_javascript_files() -> None:
    """기준선에 없는 300줄 이상 JavaScript 파일이 새로 생기면 실패한다."""
    baseline = load_baseline()
    limit = int(baseline["limits"]["js"])
    new_files = collect_new_large_files(".js", "js", "known_large_javascript")
    assert not new_files, format_new_violations(
        "JavaScript", "known_large_javascript", limit, new_files
    )


def test_excluded_dirs_are_exactly_the_approved_set() -> None:
    """`excluded_dirs` 는 산출물·가상환경 계열과 **정확히 일치**해야 한다.

    한 줄만 더 넣으면(`foms`, `static` 등) 스캔이 통째로 비면서 두 래칫 테스트가
    조용히 항상 통과한다. 범위 축소는 승인 사항이므로 코드 상수로 못박는다.
    """
    baseline = load_baseline()
    excluded: list[str] = baseline["excluded_dirs"]
    assert len(excluded) == len(set(excluded)), f"excluded_dirs 에 중복 항목이 있다 ({BASELINE_PATH})."
    assert set(excluded) == EXPECTED_EXCLUDED_DIRS, (
        f"excluded_dirs 가 승인된 집합과 다르다:\n"
        f"  기준선: {sorted(excluded)}\n"
        f"  계약  : {sorted(EXPECTED_EXCLUDED_DIRS)}\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"스캔 범위 축소는 승인 사항이다. 정말 필요하면 이 테스트의 "
        f"EXPECTED_EXCLUDED_DIRS 를 먼저 고치고 그 이유를 커밋 메시지에 남겨라."
    )


def test_scan_population_is_not_empty() -> None:
    """스캔이 실제로 파일을 훑었는지 확인한다 (모집단 0 = 게이트 무력화)."""
    excluded = set(load_baseline()["excluded_dirs"])
    for suffix in (".py", ".js"):
        population = sum(1 for _ in iter_source_files(suffix, excluded))
        assert population > 0, (
            f"'{suffix}' 스캔 모집단이 0 이다 — 래칫이 아무 파일도 보지 않고 통과했다. "
            f"excluded_dirs({sorted(excluded)})가 저장소를 통째로 가렸는지 확인하라 "
            f"({BASELINE_PATH})."
        )


def test_size_baseline_file_matches_schema() -> None:
    """기준선 JSON 의 모양을 고정한다 (키 5개 · 임계값 · 정렬된 상대 경로)."""
    baseline = load_baseline()
    assert set(baseline) == EXPECTED_TOP_LEVEL_KEYS, (
        f"기준선 최상위 키가 계약과 다르다: {sorted(baseline)} != "
        f"{sorted(EXPECTED_TOP_LEVEL_KEYS)} ({BASELINE_PATH})"
    )
    assert baseline["schema"] == SCHEMA_ID, f"schema 는 '{SCHEMA_ID}' 로 고정이다."
    assert baseline["limits"] == {"py": 500, "js": 300}, (
        "임계값은 CLAUDE.md 코딩 규칙(py 500 / js 300)에 맞춘 고정값이다."
    )
    assert isinstance(baseline["excluded_dirs"], list) and baseline["excluded_dirs"], (
        "excluded_dirs 는 비어 있지 않은 배열이어야 한다."
    )
    for key in ("known_large_python", "known_large_javascript"):
        paths: list[str] = baseline[key]
        assert paths == sorted(paths), f"{key} 는 sorted 여야 한다 ({BASELINE_PATH})."
        assert len(paths) == len(set(paths)), f"{key} 에 중복 경로가 있다."
        for path in paths:
            assert not path.startswith("/") and "\\" not in path, (
                f"{key} 의 '{path}' 는 저장소 상대 슬래시 경로여야 한다."
            )
