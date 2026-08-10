"""AUDIT-LOG P4 C2 — 쓰기 라우트 감사 커버리지 스캐너.

운영 실측(2026-08-08)이 드러낸 것: 쓰기 라우트 172개 중 102개(59%)가 감사 기록을 전혀
남기지 않았다. 배선을 한 번 채워도 **새 라우트가 기록 없이 들어오면 커버리지는 다시
떨어진다**. 그래서 커버리지를 인벤토리로 고정하고 드리프트를 CI 에서 막는다
(선례: ``failopen_scan.py`` / ``order_mutation_writer_scan.py``).

**쓰기 라우트**: ``@<bp>.route(..., methods=[... POST|PUT|PATCH|DELETE ...])`` 로 등록된
함수. GET 전용 라우트는 대상이 아니다(열람 기록은 P4 D 단계 소관).

**분류**

* ``AUDITED`` — 라우트 본문이, 또는 같은 모듈 안에서 그 라우트가 부르는 함수가
  감사 writer 를 호출한다. 감사 writer 신호는 :data:`AUDIT_SIGNALS`
  (``log_access`` · ``SecurityLog`` · ``emit_attachment_event`` · ``log_security_event``).
* ``EXEMPT`` — 기록할 가치가 없다고 판단해 allowlist 에 사유와 함께 올린 라우트
  (계산기 프리뷰·자동저장 draft·조회성 POST 등). "원장 도배 방지"가 이유다.
* ``UNAUDITED`` — 위 둘 중 어느 것도 아닌 쓰기 라우트. 인벤토리에 baseline 으로 핀 되고,
  **집합이 커지면 게이트가 red** 다(줄어드는 것은 언제나 허용).

호출 추적은 같은 모듈 안 고정점 + **``foms/`` 안 import 를 따라 :data:`MAX_DEPTH` 단계**
까지 본다. 얇은 위임 래퍼(``foms/api/orders/__init__.py`` 가 ``field_update.py`` 의
``*_response`` 를 부르는 구조)를 기록 없음으로 오판하지 않기 위해서다. 패키지 밖(서드파티)
호출은 따라가지 않는다.

재생성::

    python tools/harness/audit_coverage_scan.py            # 인벤토리 갱신
    python tools/harness/audit_coverage_scan.py --check    # 드리프트만 확인(비영속)
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
FOMS_DIR = REPO_ROOT / "foms"
ALLOWLIST_PATH = REPO_ROOT / "docs" / "harness" / "foms_audit_coverage_allowlist.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "harness" / "foms_audit_coverage_inventory.json"

#: 감사 원장(``security_logs``)에 행을 남기는 호출 이름. 이 중 하나에 도달하면 AUDITED.
AUDIT_SIGNALS = frozenset({
    "log_access",
    "SecurityLog",
    "emit_attachment_event",
})

#: 쓰기로 보는 HTTP 메서드.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

CLASSIFICATIONS = ("AUDITED", "EXEMPT", "UNAUDITED")


def _route_methods(decorator: ast.expr) -> set[str]:
    """``@bp.route(...)`` 데코레이터에서 methods 목록을 뽑는다.

    :param decorator: 데코레이터 AST 노드.
    :return: 대문자 메서드 집합. route 데코레이터가 아니면 빈 집합.
    """
    if not isinstance(decorator, ast.Call):
        return set()
    func = decorator.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in ("route", "post", "put", "patch", "delete", "add_url_rule"):
        return set()
    if name in ("post", "put", "patch", "delete"):
        return {name.upper()}
    for keyword in decorator.keywords:
        if keyword.arg != "methods":
            continue
        values = keyword.value
        if isinstance(values, (ast.List, ast.Tuple, ast.Set)):
            return {
                str(element.value).upper()
                for element in values.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return set()


def _called_names(node: ast.AST) -> set[str]:
    """함수 본문이 부르는 이름(호출·생성자)을 모은다.

    :param node: 함수 정의 노드.
    :return: 호출된 심볼 이름 집합(``a.b()`` 는 ``b``).
    """
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


#: import 를 따라 들어갈 최대 깊이(순환·비용 상한). 얇은 위임 래퍼는 1~2 로 충분하다.
MAX_DEPTH = 4


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """모듈 안 함수 정의(중첩 포함)를 이름으로 색인한다.

    :param tree: 모듈 AST.
    :return: ``{함수명: 정의 노드}`` (동명이인은 마지막 정의가 이긴다 — 스캐너 보수성).
    """
    found: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = node
    return found


def _resolve_import_target(path: Path, node: ast.ImportFrom) -> Path | None:
    """``from ... import`` 가 가리키는 ``foms/`` 안 모듈 파일을 찾는다.

    :param path: import 를 담고 있는 모듈 파일 경로.
    :param node: ImportFrom 노드.
    :return: 대상 모듈 파일 경로. 패키지 밖이거나 찾지 못하면 ``None``.
    """
    if node.level:  # 상대 import — 현재 패키지 기준으로 올라간다.
        base = path.parent
        for _ in range(node.level - 1):
            base = base.parent
        parts = (node.module or "").split(".") if node.module else []
    else:
        parts = (node.module or "").split(".")
        if not parts or parts[0] != "foms":
            return None
        base = REPO_ROOT
    target = base.joinpath(*parts) if parts else base
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


class _ModuleIndex:
    """모듈별 함수 색인·import 맵 캐시(파일 반복 파싱 방지)."""

    def __init__(self) -> None:
        self._functions: dict[Path, dict[str, ast.FunctionDef]] = {}
        self._imports: dict[Path, dict[str, Path]] = {}

    def load(self, path: Path) -> tuple[dict[str, ast.FunctionDef], dict[str, Path]]:
        """모듈의 ``(함수 색인, 이름→정의 모듈 경로)`` 를 돌려준다.

        :param path: 모듈 파일 경로.
        :return: 함수 색인과 import 맵.
        """
        if path in self._functions:
            return self._functions[path], self._imports[path]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            self._functions[path] = {}
            self._imports[path] = {}
            return {}, {}
        functions = _module_functions(tree)
        imports: dict[str, Path] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _resolve_import_target(path, node)
            if target is None:
                continue
            for alias in node.names:
                imports[alias.asname or alias.name] = target
        self._functions[path] = functions
        self._imports[path] = imports
        return functions, imports


def _audit_reachable(start: ast.AST, path: Path, index: _ModuleIndex) -> bool:
    """감사 writer 호출에 도달하는지 따라간다(같은 모듈 고정점 + import 추적).

    :param start: 시작 함수 정의 노드.
    :param path: 시작 함수가 있는 모듈 경로.
    :param index: 모듈 색인 캐시.
    :return: 감사 writer 에 도달하면 True.
    """
    seen: set[tuple[Path, int]] = set()
    stack: list[tuple[ast.AST, Path, int]] = [(start, path, 0)]
    while stack:
        node, node_path, depth = stack.pop()
        key = (node_path, id(node))
        if key in seen:
            continue
        seen.add(key)
        called = _called_names(node)
        if called & AUDIT_SIGNALS:
            return True
        if depth >= MAX_DEPTH:
            continue
        functions, imports = index.load(node_path)
        for name in called:
            local = functions.get(name)
            if local is not None:
                stack.append((local, node_path, depth))
                continue
            target_path = imports.get(name)
            if target_path is None:
                continue
            target_functions, _ = index.load(target_path)
            target = target_functions.get(name)
            if target is not None:
                stack.append((target, target_path, depth + 1))
    return False


def _scan_file(path: Path, allow: dict[str, str], index: _ModuleIndex) -> list[dict[str, Any]]:
    """파일 1개의 쓰기 라우트를 분류한다.

    :param path: 대상 ``.py`` 경로.
    :param allow: ``"경로::엔드포인트" -> 사유`` allowlist.
    :param index: 모듈 색인 캐시.
    :return: 라우트 레코드 목록.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    try:
        relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:  # 저장소 밖(테스트 픽스처) — 절대 경로를 그대로 쓴다.
        relative = path.as_posix()
    records: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods: set[str] = set()
        for decorator in node.decorator_list:
            methods |= _route_methods(decorator)
        if not methods & WRITE_METHODS:
            continue

        key = f"{relative}::{node.name}"
        if key in allow:
            classification = "EXEMPT"
        elif _audit_reachable(node, path, index):
            classification = "AUDITED"
        else:
            classification = "UNAUDITED"
        records.append({
            "path": relative,
            "endpoint": node.name,
            "lineno": node.lineno,
            "methods": sorted(methods & WRITE_METHODS),
            "classification": classification,
        })
    return records


def scan(allow: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """``foms/`` 전체의 쓰기 라우트를 스캔한다.

    :param allow: allowlist(생략 시 파일에서 읽는다).
    :return: ``(path, endpoint)`` 정렬된 레코드 목록.
    """
    allow = load_allowlist() if allow is None else allow
    index = _ModuleIndex()
    records: list[dict[str, Any]] = []
    for path in sorted(FOMS_DIR.rglob("*.py")):
        records.extend(_scan_file(path, allow, index))
    records.sort(key=lambda r: (r["path"], r["endpoint"]))
    return records


def load_allowlist() -> dict[str, str]:
    """기록 면제 라우트 allowlist 를 읽는다.

    :return: ``"경로::엔드포인트" -> 사유``. 파일이 없으면 빈 dict.
    """
    if not ALLOWLIST_PATH.exists():
        return {}
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {entry["key"]: entry["reason"] for entry in data.get("exempt", [])}


def build_inventory(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """스캔 결과를 인벤토리 문서 형태로 만든다.

    :param records: 스캔 레코드.
    :return: 커밋 대상 인벤토리 dict.
    """
    records = list(records)
    counts = Counter(r["classification"] for r in records)
    audited = counts.get("AUDITED", 0)
    covered_base = len(records) - counts.get("EXEMPT", 0)
    return {
        "packet": "AUDIT-LOG-P4-C2",
        "summary": (
            "Write-route audit coverage inventory for foms/. Every POST/PUT/PATCH/DELETE route "
            "is classified AUDITED (reaches a security_logs writer) / EXEMPT (allowlisted as "
            "not worth recording) / UNAUDITED (writes without leaving a trace). The gate keeps "
            "the UNAUDITED set from growing: a new write route must either record who did it or "
            "be added to the allowlist with a reason."
        ),
        "scope": "foms/**.py",
        "audit_signals": sorted(AUDIT_SIGNALS),
        "baselines": {
            "total": len(records),
            "unaudited": counts.get("UNAUDITED", 0),
        },
        "classification_counts": {key: counts.get(key, 0) for key in CLASSIFICATIONS},
        "coverage_percent": round(100.0 * audited / covered_base, 1) if covered_base else 100.0,
        "unaudited_sites": [
            {"path": r["path"], "endpoint": r["endpoint"], "lineno": r["lineno"],
             "methods": r["methods"]}
            for r in records if r["classification"] == "UNAUDITED"
        ],
        "routes": records,
    }


def main() -> int:
    """CLI 진입점.

    :return: 프로세스 exit code(``--check`` 에서 드리프트가 있으면 1).
    """
    parser = argparse.ArgumentParser(description="쓰기 라우트 감사 커버리지 스캔")
    parser.add_argument("--check", action="store_true",
                        help="커밋된 인벤토리와 비교만 하고 파일을 쓰지 않는다")
    args = parser.parse_args()

    inventory = build_inventory(scan())
    if args.check:
        if not INVENTORY_PATH.exists():
            print("[audit-coverage] 인벤토리 파일이 없다 — 먼저 생성하라")
            return 1
        committed = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        drifted = committed.get("routes") != inventory["routes"]
        print(f"[audit-coverage] total={inventory['baselines']['total']} "
              f"unaudited={inventory['baselines']['unaudited']} "
              f"coverage={inventory['coverage_percent']}% drift={'YES' if drifted else 'no'}")
        return 1 if drifted else 0

    INVENTORY_PATH.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"[audit-coverage] wrote {INVENTORY_PATH.relative_to(REPO_ROOT)} "
          f"(total={inventory['baselines']['total']}, "
          f"unaudited={inventory['baselines']['unaudited']}, "
          f"coverage={inventory['coverage_percent']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
