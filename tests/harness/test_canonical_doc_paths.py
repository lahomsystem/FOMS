"""정본 문서의 백틱 경로 실존 계약 (검토 보고서 ④ '지금' 2번 · T2 ②③).

정본·안내서가 가리키는 경로가 저장소에 없으면 규칙 자체가 거짓말이 된다. 실측으로
`CLAUDE.md` · `.cursor/rules/00-project-context.mdc` · `foms/README.md` 는 2026-04 strict
canonical tree 작업으로 사라진 `apps/` · 루트 `services/` · 루트 상수 모듈을 계속 가리키고
있었고, 새 세션은 그 지시를 그대로 따라 없는 트리에 코드를 넣으려 했다.

이 계약이 지키는 것 두 가지:

1. 대상 문서의 백틱 경로가 전부 실존한다. 남아 있는 예외는 기준선
   (`canonical_doc_paths_baseline.json`)의 `known_missing` 에 동결하고 **순증만** red 로 만든다.
2. 제거된 최상위 경로(`removed_top_level_paths`)를 문서가 **백틱 경로로** 다시 가리키지 않는다.

두 검사 모두 판정 범위는 **백틱 토큰 안**이다. 백틱은 "여기로 가라" 는 지시로 읽히지만,
백틱 밖 산문은 기록(승격 이력·마이그레이션 서술)이다. 사라진 트리를 역사로 인용해야 한다면
백틱을 벗기고 산문으로 적으면 통과한다.

`known_missing` 을 줄이려고 아래 추출 규칙에 예외를 덧붙이지 마라 — 그러면 게이트가
무력해진다. 고칠 수 있는 것은 문서를 고치고, 못 고치는 것은 기준선에 남긴다.
기준선 배열을 비워 통과시키는 우회는 `REQUIRED_DOCUMENTS` · `REQUIRED_REMOVED`
부분집합 assert 로 막혀 있다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "canonical_doc_paths_baseline.json"
SCHEMA_ID = "canonical-doc-paths/1"
EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "documents",
    "removed_top_level_paths",
    "known_missing",
}
# 기준선 배열을 비우면 두 테스트가 조용히 항상 통과한다(빨개진 세션이 택하기 쉬운 최단
# 경로). 최소 집합은 코드 상수로 못박고 부분집합 포함만 확인한다 — 늘리는 것은 자유다.
REQUIRED_DOCUMENTS = {
    "CLAUDE.md",
    "AGENTS.md",
    "foms/README.md",
    ".cursor/rules/00-project-context.mdc",
}
REQUIRED_REMOVED = {"apps/", "services/", "constants.py"}

# 백틱으로 감싼 토큰. 줄을 넘지 않는다.
BACKTICK_TOKEN = re.compile(r"`([^`\n]+)`")
# 경로로 볼 수 있는 모양만 남긴다 (문장 부호·한글·따옴표가 섞인 것은 버린다).
SAFE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./\-]*$")
# 제거된 경로 판정 시 "앞 글자가 경로 문자면 더 긴 경로의 일부" 로 본다.
# 이래야 `foms/services/` 가 루트 `services/` 로, erp_policy_constants.py 가
# 루트 상수 모듈로 오인되지 않는다.
PATHISH_CHAR = re.compile(r"[A-Za-z0-9_/.\-]")


def load_baseline() -> dict[str, Any]:
    """기준선 JSON 을 읽어 dict 로 돌려준다.

    Returns:
        `canonical_doc_paths_baseline.json` 의 최상위 매핑.
    """
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def assert_baseline_schema(baseline: dict[str, Any]) -> None:
    """기준선의 모양을 고정한다 (키 4개 · schema id · 최소 집합 · known_missing 정렬).

    Args:
        baseline: `load_baseline()` 결과.
    """
    assert set(baseline) == EXPECTED_TOP_LEVEL_KEYS, (
        f"기준선 최상위 키가 계약과 다르다: {sorted(baseline)} != "
        f"{sorted(EXPECTED_TOP_LEVEL_KEYS)} ({BASELINE_PATH})"
    )
    assert baseline["schema"] == SCHEMA_ID, f"schema 는 '{SCHEMA_ID}' 로 고정이다."
    documents = set(baseline["documents"])
    assert REQUIRED_DOCUMENTS <= documents, (
        f"documents 에서 정본 문서가 빠졌다: {sorted(REQUIRED_DOCUMENTS - documents)}\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"배열을 비우거나 줄이면 검사 대상이 사라져 테스트가 항상 통과한다. 늘리는 것은 자유다."
    )
    removed = set(baseline["removed_top_level_paths"])
    assert REQUIRED_REMOVED <= removed, (
        f"removed_top_level_paths 에서 제거 경로가 빠졌다: {sorted(REQUIRED_REMOVED - removed)}\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"2026-04 strict canonical tree 작업으로 사라진 트리들이라 되돌아올 수 없다."
    )
    known: list[dict[str, str]] = baseline["known_missing"]
    pairs = [(entry["document"], entry["path"]) for entry in known]
    assert pairs == sorted(pairs), "known_missing 은 (document, path) 오름차순이어야 한다."
    assert len(pairs) == len(set(pairs)), "known_missing 에 중복 항목이 있다."


def extract_path_candidates(text: str) -> list[str]:
    """문서 본문에서 실존 검사 대상 백틱 경로 후보를 뽑는다.

    규칙은 순서대로 적용한다: 공백 포함 폐기 → 첫 `:` 앞만 취함(`파일:줄` 표기) →
    `/` 없으면 폐기 → 절대경로/URL/`.git` 접두 폐기 → `..` 폐기 → 글롭(`*`, `{`) 폐기 →
    `SAFE_PATH` 불일치 폐기.

    Args:
        text: 문서 전문.

    Returns:
        등장 순서를 유지한 중복 없는 후보 경로 목록.
    """
    candidates: list[str] = []
    for raw in BACKTICK_TOKEN.findall(text):
        token = raw.strip()
        if " " in token:
            continue
        token = token.split(":", 1)[0]
        if "/" not in token:
            continue
        if token.startswith("/") or token.startswith("http") or token.startswith(".git"):
            continue
        if ".." in token or "*" in token or "{" in token:
            continue
        if not SAFE_PATH.match(token):
            continue
        if token not in candidates:
            candidates.append(token)
    return candidates


def find_removed_path_mentions(text: str, removed_path: str) -> list[tuple[int, str]]:
    """제거된 최상위 경로를 다시 가리키는 **백틱 토큰**을 찾는다.

    판정 범위는 백틱 안이다. 백틱은 "여기로 가라" 는 지시로 읽히지만 백틱 밖 산문은
    기록이라, 정본이 사라진 트리를 역사로 서술하는 것까지 red 로 만들지 않는다.
    토큰 안에서도 앞 글자가 경로 문자(`PATHISH_CHAR`)면 더 긴 경로의 꼬리로 보고
    건너뛴다.

    Args:
        text: 문서 전문.
        removed_path: 저장소에서 사라진 경로 (예 `apps/`).

    Returns:
        (줄 번호, 그 줄 전문) 목록.
    """
    hits: list[tuple[int, str]] = []
    lines = text.splitlines()
    for token in BACKTICK_TOKEN.finditer(text):
        body = token.group(1)
        for local in _offsets(body, removed_path):
            if local > 0 and PATHISH_CHAR.match(body[local - 1]):
                continue
            offset = token.start(1) + local
            line_no = text.count("\n", 0, offset) + 1
            hits.append((line_no, lines[line_no - 1].strip()))
    return hits


def _offsets(text: str, needle: str) -> list[int]:
    """`needle` 이 나타나는 모든 시작 위치를 돌려준다.

    Args:
        text: 대상 문자열.
        needle: 찾을 문자열.

    Returns:
        0 기준 시작 오프셋 목록.
    """
    return [match.start() for match in re.finditer(re.escape(needle), text)]


def read_document(document: str) -> str:
    """대상 문서를 읽는다 (없으면 그 자리에서 실패시킨다).

    Args:
        document: 저장소 상대 슬래시 경로.

    Returns:
        문서 전문.
    """
    path = REPO_ROOT / document
    assert path.is_file(), (
        f"기준선의 documents 에 있는 '{document}' 가 저장소에 없다 ({BASELINE_PATH}). "
        f"문서를 옮겼다면 기준선의 documents 배열도 같이 고쳐라."
    )
    return path.read_text(encoding="utf-8")


def test_canonical_docs_have_no_missing_backtick_paths() -> None:
    """정본 문서의 백틱 경로가 전부 실존한다 (기준선에 동결된 예외 제외)."""
    baseline = load_baseline()
    assert_baseline_schema(baseline)
    known = {
        (entry["document"], entry["path"])
        for entry in baseline["known_missing"]
    }
    missing: list[tuple[str, str]] = []
    for document in baseline["documents"]:
        text = read_document(document)
        for candidate in extract_path_candidates(text):
            if (REPO_ROOT / candidate.rstrip("/")).exists():
                continue
            if (document, candidate) in known:
                continue
            missing.append((document, candidate))
    rows = "\n".join(f"  {doc}: `{path}`" for doc, path in sorted(missing))
    assert not missing, (
        f"정본 문서가 저장소에 없는 경로 {len(missing)}개를 가리킨다:\n{rows}\n\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"되돌리는 법 (둘 중 하나):\n"
        f"  1) 권장 — 문서의 그 백틱 경로를 실제로 존재하는 경로로 고친다.\n"
        f"     삭제가 아니라 정정이다. 없어진 트리라면 '어디로 갔는지' 를 사실 문장으로 남긴다.\n"
        f"  2) 저장소 밖 대상(런타임 산출물·git ref·슬래시 명령 등)이라면 기준선의\n"
        f"     'known_missing' 에 {{\"document\": ..., \"path\": ...}} 로 넣고 오름차순을 유지한다.\n"
        f"     추출 규칙(extract_path_candidates)에 예외를 덧붙여 숨기지 마라 — 게이트가 죽는다."
    )


def test_canonical_docs_do_not_mention_removed_top_level_paths() -> None:
    """제거된 최상위 경로를 정본 문서가 백틱 경로로 다시 가리키지 않는다."""
    baseline = load_baseline()
    assert_baseline_schema(baseline)
    hits: list[str] = []
    for document in baseline["documents"]:
        text = read_document(document)
        for removed_path in baseline["removed_top_level_paths"]:
            for line_no, line in find_removed_path_mentions(text, removed_path):
                hits.append(f"  {document}:{line_no} ('{removed_path}') {line}")
    rows = "\n".join(hits)
    assert not hits, (
        f"2026-04 strict canonical tree 작업으로 사라진 경로를 문서가 백틱 경로로 다시 "
        f"가리킨다 ({len(hits)}곳):\n{rows}\n\n"
        f"기준선 파일: {BASELINE_PATH}\n"
        f"실경로: 새 라우트는 foms/api/(JSON·API·webhook)·foms/web/(HTML 페이지),\n"
        f"        등록 정본은 foms/platform/blueprints.py, 비즈니스 로직은 foms/services/,\n"
        f"        상수는 도메인 모듈 옆(예 foms/services/orders/erp_policy_constants.py).\n"
        f"되돌리는 법 (둘 중 하나):\n"
        f"  1) 지시라면 — 위 줄을 실경로로 고친다.\n"
        f"  2) 역사 서술이라면 — 백틱을 벗기고 산문으로 적는다. 판정은 백틱 안만 본다\n"
        f"     (예: '구 overlay 트리는 2026-04 에 제거됐다')."
    )
