"""레이어 의존 방향 래칫 계약 — 금지 방향과 지연 import 의 **순증만** 빨강으로 만든다.

foms/ 의 레이어 경계는 지금 디렉토리 이름일 뿐이라, 에이전트 속도로 역방향 의존이 계속
늘어난다. 이 계약은 코드를 한 줄도 고치지 않고 **오늘의 위반을 항목 집합으로 동결**한 뒤,
기준선에 없는 새 위반이 생길 때만 실패한다.

줄어드는 것은 절대 실패시키지 않는다. "기준선에 있는데 지금 없다" 를 빨강으로 만들면
위반을 하나 고칠 때마다 CI 가 빨개져 래칫이 거꾸로 돌기 때문이다. 기준선 배열은 분해
진척의 척도이므로, 항목이 줄면 기준선에서 지워 새 바닥을 굳히면 된다.

금지 방향 정본은 modular monolith rebaseline 스펙(2026-04-13) §2.4 레이어별 경계 규칙 표.
저장소 경로는 docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md 이며, 여기에
따옴표로 감싼 문자열 리터럴로 적지 않는다 — 그러면 CI-DOCSCOPE-01 계약이 이 파일을
"문서를 읽는 테스트" 로 보고 ci.yml 문서 서브셋 등재를 강제한다.

기준선 재생성(항목이 줄었거나 의도한 구조 변경을 반영할 때) — 저장소 루트에서 한 줄:

    PYTHONIOENCODING=utf-8 python -c "import sys; sys.path.insert(0, 'tests/contracts/runtime'); import test_layer_dependency_ratchet as m; print(m.regenerate_baseline())"

재생성 후 diff 를 사람이 읽어 새 항목이 의도된 것인지 확인한다 — 무조건 재생성은 래칫을
자동 무력화한다. 기준선은 손편집하지 마라(정렬·중복 계약이 스스로 빨강이 된다).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOT_NAME = "foms"
BASELINE_PATH = Path(__file__).resolve().parent / "layer_dependency_baseline.json"
BASELINE_SCHEMA = "layer-dependency-ratchet/1"
BASELINE_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "scan_root",
        "forbidden_directions",
        "forbidden_edges",
        "lazy_imports",
    }
)

# 스펙 §2.4 표(services 는 blueprint import 금지 · persistence 는 web/api/platform import 금지)와
# 검토 보고서가 실제로 센 4방향의 합집합. 늘리지도 줄이지도 않는다.
FORBIDDEN_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("services", "web"),
    ("services", "api"),
    ("api", "web"),
    ("persistence", "services"),
    ("persistence", "web"),
    ("persistence", "api"),
    ("persistence", "platform"),
)

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

_FIX_HINT = (
    "되돌리는 법: 새 import 를 지우거나, 의도한 구조 변경이면 기준선 JSON 에 항목을 "
    "추가하고 리뷰를 받아라. 기준선 재생성 명령은 이 모듈 docstring 끝에 있다 — "
    "무조건 재생성은 래칫을 자동 무력화하니 diff 를 사람이 읽어라."
)


def _python_files() -> list[Path]:
    """스캔 루트(foms/) 아래 .py 파일 목록. __pycache__ 는 제외하고 정렬해 돌려준다."""
    return [
        path
        for path in sorted((REPO_ROOT / SCAN_ROOT_NAME).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _relative_posix(path: Path) -> str:
    """저장소 루트 기준 슬래시 상대 경로."""
    return path.relative_to(REPO_ROOT).as_posix()


def _file_layer(rel_path: str) -> str | None:
    """foms/<layer>/... 의 레이어 이름. foms/__init__.py 처럼 조각이 없으면 None."""
    parts = rel_path.split("/")
    return parts[1] if len(parts) >= 3 else None


def _module_layer(module: str) -> str | None:
    """점표기 모듈(foms.<layer>...)의 레이어 이름. 조각이 없으면 None."""
    parts = module.split(".")
    return parts[1] if len(parts) >= 2 else None


def _package_parts(rel_path: str) -> list[str]:
    """파일이 속한 패키지의 점표기 조각 — 상대 import 를 절대 이름으로 풀 기준점."""
    return rel_path.split("/")[:-1]


def _iter_import_nodes(node: ast.AST, inside_function: bool) -> Iterator[tuple[ast.stmt, bool]]:
    """(import 노드, 함수 조상 존재 여부) 쌍을 트리 순서대로 낸다.

    함수마다 ast.walk 를 다시 돌리면 중첩 def 안의 import 가 바깥·안쪽에서 두 번
    세어진다. 부모를 따라 내려가며 "함수 조상이 하나라도 있는가" 로 한 번만 판정한다.

    Args:
        node: 훑을 AST 노드(최초 호출은 Module).
        inside_function: 지금 노드가 이미 함수 조상 아래인지.

    Yields:
        (Import 또는 ImportFrom 노드, 함수 조상 존재 여부) 쌍.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child, inside_function
        nested = inside_function or isinstance(child, _FUNCTION_NODES)
        yield from _iter_import_nodes(child, nested)


def _import_from_base(node: ast.ImportFrom, package_parts: list[str]) -> str:
    """ImportFrom 이 가리키는 base 를 절대 점표기로 푼다. 못 풀면 빈 문자열.

    Args:
        node: ImportFrom 노드.
        package_parts: 소스 파일이 속한 패키지의 점표기 조각.

    Returns:
        `from a.b import c` 의 "a.b". 상대 import 는 package_parts 기준으로 절대화한다.
    """
    if node.level == 0:
        return node.module or ""
    cut = len(package_parts) - (node.level - 1)
    if cut <= 0:
        return ""
    return ".".join(package_parts[:cut] + ([node.module] if node.module else []))


def _imported_modules(node: ast.stmt, package_parts: list[str]) -> list[str]:
    """import 노드가 가리키는 절대 점표기 모듈 목록. foms 밖으로 나가는 것은 뺀다.

    `from foms import web` · `from .. import web` 는 base 가 foms 에서 끝나 _module_layer 가
    None 을 돌려준다. base 만 보면 이 합법 표기가 금지 방향 판정을 그대로 통과하므로,
    base 가 레이어를 못 내는 경우에 한해 alias 이름을 붙인 후보를 함께 낸다. base 가 이미
    레이어를 내면(foms.web...) alias 를 붙여도 레이어 조각이 그대로라 판정이 바뀌지 않고,
    기준선만 심볼 단위로 부풀어 분해 진척의 척도가 망가진다.

    Args:
        node: Import 또는 ImportFrom 노드.
        package_parts: 소스 파일이 속한 패키지의 점표기 조각.

    Returns:
        foms 로 시작하는 절대 모듈 이름 목록.
    """
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        base = _import_from_base(node, package_parts)
        if not base:
            return []
        names = [base]
        if _module_layer(base) is None:
            names += [f"{base}.{alias.name}" for alias in node.names if alias.name != "*"]
    else:
        return []
    return [name for name in names if name.split(".")[0] == SCAN_ROOT_NAME]


@lru_cache(maxsize=1)
def _scan_violations_cached() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """foms/ 를 한 번만 파싱해 스캔 결과를 튜플로 캐시한다.

    테스트마다 452 파일을 다시 파싱하면 같은 워커에서 1.3 초를 그냥 버린다(메인 CI 레인은
    --dist loadfile 이라 두 테스트가 같은 워커에서 잇달아 돈다). 캐시는 프로세스 수명 안에서만
    유효하고 pytest 는 매번 새 프로세스라, 파일을 고쳐 가며 다시 돌리는 시나리오에서도 낡은
    결과를 돌려주지 않는다.

    Returns:
        (forbidden_edges, lazy_imports) 정렬 튜플.
    """
    forbidden = set(FORBIDDEN_DIRECTIONS)
    edges: set[str] = set()
    lazy: set[str] = set()
    for path in _python_files():
        rel = _relative_posix(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        package_parts = _package_parts(rel)
        layer = _file_layer(rel)
        for node, inside_function in _iter_import_nodes(tree, False):
            for module in _imported_modules(node, package_parts):
                item = f"{rel}::{module}"
                if inside_function:
                    lazy.add(item)
                target = _module_layer(module)
                if layer is not None and target is not None and (layer, target) in forbidden:
                    edges.add(item)
    return tuple(sorted(edges)), tuple(sorted(lazy))


def scan_violations() -> tuple[list[str], list[str]]:
    """지금 트리를 훑어 (금지 방향 edge, 지연 foms import) 항목을 정렬해 돌려준다.

    Returns:
        (forbidden_edges, lazy_imports). 항목 형식은 둘 다
        "<저장소 상대 소스 경로>::<import 된 점표기 모듈>" 이고 중복은 없다.
    """
    edges, lazy = _scan_violations_cached()
    return list(edges), list(lazy)


@lru_cache(maxsize=1)
def _load_baseline() -> dict[str, Any]:
    """기준선 JSON 을 프로세스당 한 번만 읽어 돌려준다. 반환 dict 는 읽기 전용으로 쓴다."""
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def regenerate_baseline() -> tuple[int, int]:
    """지금 트리 스캔 결과로 기준선 JSON 의 항목 배열을 다시 쓴다.

    손편집은 정렬·중복 계약에 걸려 스스로 빨강이 되므로 재생성은 이 함수가 정본이다.
    개행 방식은 기존 파일을 따르고(Windows 체크아웃의 CRLF 보존), generated_at 은 건드리지
    않는다 — 재생성이 늘 diff 를 만들면 "안 바뀌는 게 정상" 확인이 불가능해진다.

    무조건 재생성은 래칫을 자동 무력화한다. 실행 뒤 diff 를 사람이 읽어 새 항목이 의도된
    구조 변경인지 확인하고 리뷰를 받아라.

    Returns:
        (기록한 forbidden_edges 개수, lazy_imports 개수).
    """
    raw = BASELINE_PATH.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    baseline = json.loads(raw.decode("utf-8"))
    edges, lazy = scan_violations()
    baseline["forbidden_edges"] = edges
    baseline["lazy_imports"] = lazy
    with BASELINE_PATH.open("w", encoding="utf-8", newline=newline) as handle:
        handle.write(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
    _load_baseline.cache_clear()
    return len(edges), len(lazy)


def _added_report(title: str, added: list[str]) -> str:
    """새 위반 목록을 기준선 경로·되돌리는 법과 함께 실패 메시지로 만든다."""
    lines = [
        title,
        f"기준선 파일: {_relative_posix(BASELINE_PATH)}",
        f"새 위반 {len(added)}건:",
    ]
    lines.extend(f"  - {item}" for item in added)
    lines.append(_FIX_HINT)
    return "\n".join(lines)


def test_no_new_forbidden_layer_edges() -> None:
    """기준선에 없는 금지 방향 import 가 새로 생기면 실패한다(줄어드는 것은 통과)."""
    edges, _ = scan_violations()
    added = sorted(set(edges) - set(_load_baseline()["forbidden_edges"]))
    assert not added, _added_report("레이어 금지 방향 import 가 새로 늘었다.", added)


def test_no_new_lazy_foms_imports() -> None:
    """기준선에 없는 함수 안 지연 foms import 가 새로 생기면 실패한다."""
    _, lazy = scan_violations()
    added = sorted(set(lazy) - set(_load_baseline()["lazy_imports"]))
    assert not added, _added_report("함수 안 지연 foms import 가 새로 늘었다.", added)


def test_baseline_file_matches_schema() -> None:
    """기준선 JSON 이 스키마·키·정렬·중복 없음 계약을 지킨다."""
    where = _relative_posix(BASELINE_PATH)
    baseline = _load_baseline()

    assert baseline.get("schema") == BASELINE_SCHEMA, f"{where}: schema 값이 다르다"
    assert set(baseline) == set(BASELINE_KEYS), f"{where}: 최상위 키가 계약과 다르다"
    assert baseline["scan_root"] == SCAN_ROOT_NAME, f"{where}: scan_root 가 다르다"

    directions = [tuple(pair) for pair in baseline["forbidden_directions"]]
    assert directions == list(FORBIDDEN_DIRECTIONS), f"{where}: 금지 방향 표가 계약과 다르다"

    for key in ("forbidden_edges", "lazy_imports"):
        items = baseline[key]
        assert all(isinstance(item, str) for item in items), f"{where}: {key} 항목은 문자열이다"
        assert items == sorted(items), f"{where}: {key} 가 정렬되어 있지 않다"
        assert len(items) == len(set(items)), f"{where}: {key} 에 중복 항목이 있다"
