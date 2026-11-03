"""'확인할 것' 네 묶음(설계서 7.9 · 사장님 11-03 · D151) — 제안 하나가 어느 묶음인지 서버가 정한다(순수 함수).

- ``names`` ① 한글 이름 붙이기 — 고침인데 바뀐 칸이 실음 칸의 이름표(대표 이름 · 다른 이름 · 숨은 이름)뿐.
- ``content`` ② 새로 들어가거나 바뀌는 지식 — 만들기 · 글 · 값 · 규칙 고침 · 은퇴 · 지우기 · 그 밖 링크(한 장씩).
- ``decide`` ③ 사장님이 정해 주실 것 — 엇갈림 · 질문 항목 만들기.
- ``mark`` ④ 같은 값이 적힌 곳 표시 — 사본 자리 링크(``copy_in``) 더하기.

①과 ④ 는 글 · 금액 · 규칙이 바뀌지 않아 관리자가 한꺼번에 승인할 수 있다(:func:`bulk_ok_any_grade` — D151).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from foms.services.brain.constants import AGENT_WORK_TYPES, OP_CREATE, OP_LINK_ADD, OP_UPDATE

__all__ = ["BINS", "BIN_CONTENT", "BIN_DECIDE", "BIN_MARK", "BIN_NAMES", "LABEL_KEYS", "bulk_ok_any_grade", "card_bin",
           "ref_label"]

BIN_NAMES, BIN_CONTENT, BIN_DECIDE, BIN_MARK = "names", "content", "decide", "mark"
#: 화면 차례.
BINS: tuple[str, ...] = (BIN_NAMES, BIN_CONTENT, BIN_DECIDE, BIN_MARK)
#: 이름표 칸(실음 칸 안) — 찾기 · 이름만 바꾸고 답 글 · 금액은 건드리지 않는다.
LABEL_KEYS: frozenset[str] = frozenset({"pref_label", "aliases", "hidden_labels"})
COPY_LINK = "copy_in"
#: 바깥 사본 자리 이름(④ 표 — 사람이 읽는 이름). 모르는 자리는 머리 이름 + 나머지.
REF_LABELS: dict[str, str] = {"form:lahom-option-table": "기본 옵션표"}
_REF_HEADS: dict[str, str] = {"form:": "양식", "macro:": "채널톡 상용구", "store:": "스마트스토어 상세", "screen:": "화면"}


def _label_only(fields: Optional[Mapping[str, Any]]) -> bool:
    """바뀐 칸이 실음 칸 하나이고, 그 안에서 달라진 칸이 이름표뿐인가."""
    if not fields or set(fields) != {"payload"}:
        return False
    entry = fields["payload"] or {}
    before = entry.get("before") if isinstance(entry.get("before"), dict) else {}
    after = entry.get("after") if isinstance(entry.get("after"), dict) else {}
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    return bool(changed) and changed <= LABEL_KEYS


def card_bin(op: str, item_type: Optional[str], fields: Optional[Mapping[str, Any]], link_kind: Optional[str]) -> str:
    """제안 하나의 묶음."""
    if op == OP_UPDATE and _label_only(fields):
        return BIN_NAMES
    if op == OP_CREATE and item_type in AGENT_WORK_TYPES:
        return BIN_DECIDE
    if op == OP_LINK_ADD and link_kind == COPY_LINK:
        return BIN_MARK
    return BIN_CONTENT


def bulk_ok_any_grade(op: str, item_type: Optional[str], fields: Optional[Mapping[str, Any]],
                      link_kind: Optional[str]) -> bool:
    """등급과 상관없이 관리자가 한꺼번에 승인할 수 있나 — ① 이름표만 · ④ 사본 링크만(D151)."""
    return card_bin(op, item_type, fields, link_kind) in (BIN_NAMES, BIN_MARK)


def ref_label(ref: Optional[str]) -> str:
    """링크 끝 하나의 화면 이름 — 바깥 사본 자리는 사람이 읽는 이름, 그 밖은 그대로."""
    if not ref:
        return ""
    if ref in REF_LABELS:
        return REF_LABELS[ref]
    head = next((h for h in _REF_HEADS if ref.startswith(h)), None)
    return f"{_REF_HEADS[head]} · {ref[len(head):]}" if head else ref
