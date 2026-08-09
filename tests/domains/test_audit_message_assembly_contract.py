"""AUDIT-LOG P4 B2: 감사 문장 조립 SSOT 계약.

라우트가 로그 문장을 직접 f-string 으로 조립하면, 새 경로가 생길 때마다 표기가 갈라진다
(이번 작업의 발단이 정확히 그것이다 — 한 라우트만 한글이고 나머지는 영문 필드명이었다).
그래서 **주문 변경 문장은 반드시**
:func:`foms.services.audit_message_display.describe_field_change` 를 거치게 하고,
직접 조립을 grep 계약으로 막는다.
"""

from __future__ import annotations

import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 감사 문장을 만드는 코드가 있는 곳(주문 변경 경로).
_WRITE_PATHS = (
    "foms/api/orders/field_update.py",
    "foms/api/orders/regional.py",
    "foms/api/orders/status.py",
    "foms/web/orders/listing.py",
)

#: 금지 패턴 — 필드/상태 변경 문장을 라우트에서 직접 만드는 형태.
_FORBIDDEN = (
    re.compile(r"f\"[^\"]*필드를[^\"]*\(으\)로 변경"),
    re.compile(r"f\"[^\"]*상태를[^\"]*\(으\)로 변경"),
    re.compile(r"f\"주문 #\{[^}]+\}\s*상태 변경"),
)


def test_order_change_messages_are_built_by_the_display_ssot():
    """주문 변경 경로는 문장 생성기를 거친다(직접 조립 금지)."""
    missing = [
        path for path in _WRITE_PATHS
        if "describe_field_change" not in (_REPO_ROOT / path).read_text(encoding="utf-8")
    ]
    assert not missing, f"문장 SSOT 를 쓰지 않는 경로: {missing}"


def test_no_route_assembles_change_sentences_by_hand():
    """``log_access`` 인자를 f-string 으로 손수 조립하는 코드가 남아 있지 않다.

    검사 범위는 **``log_access(`` 호출 안**이다 — 화면 flash 문구까지 막으면 사용자에게
    보여줄 안내문을 못 만든다(감사 문장과 안내문은 서로 다른 물건이다).
    """
    offenders: list[str] = []
    for path in _WRITE_PATHS:
        lines = (_REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "log_access(" not in line:
                continue
            window = "\n".join(lines[index:index + 4])
            if any(pattern.search(window) for pattern in _FORBIDDEN):
                offenders.append(f"{path}:{index + 1}")
    assert not offenders, f"라우트가 감사 문장을 직접 조립한다: {offenders}"


def test_structured_audit_arguments_accompany_order_change_logs():
    """주문 변경 로그는 구조화 인자(action·target·detail)를 함께 남긴다."""
    for path in _WRITE_PATHS:
        source = (_REPO_ROOT / path).read_text(encoding="utf-8")
        assert 'target_type="order"' in source, f"{path}: target_type 미기록"
        assert '"before"' in source or "before=" in source, f"{path}: before 미기록"
