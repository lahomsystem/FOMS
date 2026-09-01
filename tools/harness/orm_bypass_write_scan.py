"""HB-S1 — ORM 우회 쓰기 스캔 게이트.

테이블 버전 카운터(:mod:`foms.services.common.table_version_counter`)의 신호원은
전역 SQLAlchemy 세션 훅이다. 훅은 **ORM 엔티티 상태를 거치는 쓰기**만 본다. 따라서
남는 구멍은 ORM 을 우회하는 쓰기뿐이고, 그 수는 셀 수 있다(S0 조사, 원장
``docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md`` §P7 판정 2).

이 스캐너는 그 우회 쓰기를 전부 찾아 분류한다:

- ``query_bulk_update`` / ``query_bulk_delete`` — query-level ``update()``/``delete()``
  (ORM 인스턴스를 만들지 않고 UPDATE/DELETE 를 직접 낸다).
- ``bulk_mappings`` — ``bulk_insert_mappings`` / ``bulk_update_mappings`` /
  ``bulk_save_objects``.
- ``raw_dml`` — ``execute(text("INSERT|UPDATE|DELETE ..."))``.

분류(``signal``):

- ``MARKED`` — 그 쓰기를 감싼 함수가 :func:`~foms.services.common.table_version_counter.mark_tables_dirty`
  (또는 ``bump_table_versions``)를 부른다. 커밋 시점에 카운터가 오른다.
- allowlist 등재값(``UNTRACKED_TABLE`` / ``TEMP_TABLE``) — 쓰는 테이블이
  ``VERSIONED_TABLES`` 밖이라 카운터와 무관하다. 사유를 함께 적는다.
- ``UNSIGNALED`` — 위 어디에도 없다. **게이트는 이 값을 0 으로 강제한다** — 하나라도
  남으면 그 쓰기는 카운터를 못 올리고, 읽는 쪽(S2)이 낡은 304 를 내보낸다.

정확도 한계(의도된 천장): ``MARKED`` 판정은 **함수 단위**다. 한 함수 안에서 우회 쓰기를
두 개 하고 하나만 등재해도 둘 다 ``MARKED`` 로 보인다. 기존
``order_mutation_writer_scan.py`` 의 파일 단위 천장보다는 좁고, 드리프트 게이트 +
리뷰가 그 격차를 덮는다. 필요해지면 문(statement) 단위 분석으로 올린다.

인벤토리 재생성: ``python tools/harness/orm_bypass_write_scan.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("foms", "scripts")
ALLOWLIST_PATH = REPO_ROOT / "docs" / "harness" / "foms_orm_bypass_write_allowlist.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "harness" / "foms_orm_bypass_write_inventory.json"

KIND_QUERY_UPDATE = "query_bulk_update"
KIND_QUERY_DELETE = "query_bulk_delete"
KIND_BULK_MAPPINGS = "bulk_mappings"
KIND_RAW_DML = "raw_dml"

KINDS = (KIND_QUERY_UPDATE, KIND_QUERY_DELETE, KIND_BULK_MAPPINGS, KIND_RAW_DML)

SIGNAL_MARKED = "MARKED"
SIGNAL_UNSIGNALED = "UNSIGNALED"
#: allowlist 에서 쓸 수 있는 "카운터와 무관" 사유값.
ALLOWED_SIGNALS = ("UNTRACKED_TABLE", "TEMP_TABLE")
SIGNALS = (SIGNAL_MARKED, SIGNAL_UNSIGNALED, *ALLOWED_SIGNALS)

#: 이 이름의 호출이 함수 안에 있으면 그 함수의 우회 쓰기는 신호를 남긴다.
_MARK_CALLS = frozenset({"mark_tables_dirty", "bump_table_versions"})

#: query-level 연산자 판정용 — 수신자 체인에 이 호출이 있으면 dict.update 가 아니다.
_QUERY_CHAIN_CALLS = frozenset(
    {"query", "filter", "filter_by", "where", "with_entities", "with_for_update"}
)

_BULK_MAPPING_CALLS = frozenset(
    {"bulk_insert_mappings", "bulk_update_mappings", "bulk_save_objects"}
)

_DML_PREFIXES = ("insert", "update", "delete")


def load_allowlist() -> list[dict[str, str]]:
    """allowlist JSON 을 읽어 엔트리 목록으로 돌려준다(없으면 빈 목록)."""
    if not ALLOWLIST_PATH.exists():
        return []
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return list(data.get("entries") or [])


def _first_text_literal(node: ast.AST) -> str | None:
    """``text(...)`` 호출의 첫 인자에서 정적으로 읽히는 SQL 앞부분을 돌려준다.

    Args:
        node: 검사할 AST 노드.

    Returns:
        f-string 이면 첫 상수 조각, 순수 문자열이면 그 전체. 정적으로 못 읽으면 ``None``.
    """
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
    if name != "text" or not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        for piece in arg.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                return piece.value
    return None


def _is_dml_sql(sql: str) -> bool:
    """SQL 문자열이 INSERT/UPDATE/DELETE 로 시작하는지(주석·공백 무시)."""
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        return stripped.split(None, 1)[0].lower() in _DML_PREFIXES
    return False


def _receiver_is_query_chain(node: ast.Call) -> bool:
    """``x.update(...)`` 의 수신자가 SQLAlchemy 쿼리 체인인지.

    ``dict.update({...})`` 같은 동명이인을 걸러내는 유일한 판정이다. 수신자 체인에
    ``query()``/``filter()`` 류 호출이 있거나 ``synchronize_session`` 키워드가 붙어
    있으면 query-level 연산으로 본다.
    """
    if any(kw.arg == "synchronize_session" for kw in node.keywords):
        return True
    cursor: ast.AST | None = node.func.value if isinstance(node.func, ast.Attribute) else None
    while cursor is not None:
        if isinstance(cursor, ast.Call):
            fn = cursor.func
            attr = fn.attr if isinstance(fn, ast.Attribute) else None
            if attr in _QUERY_CHAIN_CALLS:
                return True
            cursor = fn.value if isinstance(fn, ast.Attribute) else None
            continue
        if isinstance(cursor, ast.Attribute):
            cursor = cursor.value
            continue
        return False
    return False


def site_kind(node: ast.AST) -> str | None:
    """AST 노드가 ORM 우회 쓰기이면 그 종류를, 아니면 ``None`` 을 돌려준다.

    Args:
        node: 검사할 AST 노드.

    Returns:
        :data:`KINDS` 중 하나 또는 ``None``.
    """
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    attr = fn.attr if isinstance(fn, ast.Attribute) else None
    if attr in _BULK_MAPPING_CALLS:
        return KIND_BULK_MAPPINGS
    if attr == "execute" and node.args:
        sql = _first_text_literal(node.args[0])
        if sql is not None and _is_dml_sql(sql):
            return KIND_RAW_DML
        return None
    if attr == "update" and _receiver_is_query_chain(node):
        return KIND_QUERY_UPDATE
    if attr == "delete" and _receiver_is_query_chain(node):
        return KIND_QUERY_DELETE
    return None


def _function_marks(func_node: ast.AST) -> bool:
    """함수 본문에 ``mark_tables_dirty``/``bump_table_versions`` 호출이 있는지."""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if name in _MARK_CALLS:
            return True
    return False


def _enclosing_functions(tree: ast.AST) -> dict[int, tuple[str, bool]]:
    """AST 노드 id → ``(감싼 함수 이름, 그 함수가 등재하는가)`` 매핑.

    중첩 함수는 가장 안쪽 함수가 이긴다(바깥 함수를 나중에 덮어쓰지 않도록 바깥부터
    채운 뒤 안쪽으로 내려간다).
    """
    mapping: dict[int, tuple[str, bool]] = {}
    stack: list[ast.AST] = [tree]
    while stack:
        current = stack.pop()
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                marks = _function_marks(child)
                for node in ast.walk(child):
                    mapping[id(node)] = (child.name, marks)
            stack.append(child)
    return mapping


def _classify(rel_path: str, func: str, marks: bool, allow: list[dict[str, str]]) -> tuple[str, str]:
    """``(signal, reason)`` 판정. 등재 호출이 allowlist 보다 우선한다."""
    if marks:
        return (SIGNAL_MARKED, "")
    norm = rel_path.replace("\\", "/")
    for entry in allow:
        if norm.endswith(entry["path"].replace("\\", "/")) and entry.get("func") == func:
            return (entry["signal"], entry.get("reason", ""))
    return (SIGNAL_UNSIGNALED, "")


def _iter_files() -> list[Path]:
    """스캔 대상 ``.py`` 파일(바이트코드 캐시 제외), 경로순."""
    files: list[Path] = []
    for name in SCAN_DIRS:
        root = REPO_ROOT / name
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def scan(allowlist: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """스캔 대상 전체에서 ORM 우회 쓰기를 찾아 분류해 돌려준다.

    Args:
        allowlist: allowlist 엔트리(생략하면 디스크에서 읽는다).

    Returns:
        ``path``·``lineno``·``kind``·``func``·``signal``·``reason`` 을 담은 레코드 목록
        (``(path, lineno, kind)`` 정렬).
    """
    allow = allowlist if allowlist is not None else load_allowlist()
    records: list[dict[str, Any]] = []
    for path in _iter_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        enclosing = _enclosing_functions(tree)
        for node in ast.walk(tree):
            kind = site_kind(node)
            if kind is None:
                continue
            func, marks = enclosing.get(id(node), ("<module>", False))
            signal, reason = _classify(rel, func, marks, allow)
            records.append({
                "path": rel,
                "lineno": getattr(node, "lineno", 0),
                "kind": kind,
                "func": func,
                "signal": signal,
                "reason": reason,
            })
    records.sort(key=lambda r: (r["path"], r["lineno"], r["kind"]))
    return records


def build_inventory() -> dict[str, Any]:
    """인벤토리 문서(요약 + 카운트 + 사이트 전량)를 조립한다."""
    records = scan()
    signal_counts = Counter(r["signal"] for r in records)
    kind_counts = Counter(r["kind"] for r in records)
    unsignaled = [
        {"path": r["path"], "lineno": r["lineno"], "kind": r["kind"], "func": r["func"]}
        for r in records if r["signal"] == SIGNAL_UNSIGNALED
    ]
    return {
        "packet": "HB-S1",
        "summary": (
            "ORM-bypass write inventory for foms/ and scripts/. The table version "
            "counter's signal source is a global SQLAlchemy session hook, which only "
            "sees writes that go through ORM entity state. Query-level update()/delete(), "
            "bulk_*_mappings and raw execute(text(DML)) bypass it. Every such site is "
            "classified MARKED (its enclosing function calls mark_tables_dirty / "
            "bump_table_versions), UNTRACKED_TABLE / TEMP_TABLE (writes a table outside "
            "VERSIONED_TABLES — allowlisted with a reason), or UNSIGNALED. Gate target: "
            "UNSIGNALED == 0. A new bypass write with no signal turns the gate red."
        ),
        "scope": "foms/**.py, scripts/**.py",
        "baselines": {
            "total": len(records),
            "unsignaled": signal_counts.get(SIGNAL_UNSIGNALED, 0),
        },
        "signal_counts": dict(sorted(signal_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "unsignaled_sites": unsignaled,
        "sites": records,
    }


def write_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    """인벤토리를 생성해 ``path`` 에 pretty JSON 으로 쓴다."""
    inventory = build_inventory()
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return inventory


def main(argv: list[str] | None = None) -> int:
    """CLI: 인벤토리 재생성, ``--check`` 면 카운트만 출력."""
    parser = argparse.ArgumentParser(description="HB-S1 ORM-bypass write scan gate")
    parser.add_argument("--check", action="store_true",
                        help="Print counts without writing the inventory file.")
    args = parser.parse_args(argv)
    if args.check:
        inv = build_inventory()
        print(json.dumps({
            "total": inv["baselines"]["total"],
            "signals": inv["signal_counts"],
            "unsignaled_sites": inv["unsignaled_sites"],
        }, ensure_ascii=False, indent=2))
        return 0
    inv = write_inventory()
    print(
        f"wrote {INVENTORY_PATH.relative_to(REPO_ROOT)}: "
        f"{inv['baselines']['total']} bypass writes, "
        f"{inv['baselines']['unsignaled']} unsignaled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
