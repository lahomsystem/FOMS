"""'승인 대기' 네 묶음(설계서 7.9 · 사장님 11-03 · D151) — 제안 하나가 어느 묶음인지 서버가 정한다(순수 함수).

- ``names`` ① 한글 이름 붙이기 — 고침인데 바뀐 칸이 실음 칸의 이름표(대표 이름 · 다른 이름 · 숨은 이름)뿐.
- ``content`` ② 새로 들어가거나 바뀌는 지식 — 만들기 · 글 · 값 · 규칙 고침 · 은퇴 · 지우기 · 그 밖 링크(한 장씩).
- ``decide`` ③ 사장님이 정해 주실 것 — 엇갈림 · 질문 항목 만들기. **ADMIN 만 보고 정한다**(D167 '① 만 상담팀장, 나머지는
  사장님' — 판정은 :func:`.access.approval_problem`, 이 묶음인지는 :func:`owner_decides`).
- ``mark`` ④ 같은 값이 적힌 곳 표시 — 사본 자리 링크(``copy_in``) 더하기.

- ``calc`` ⑤ 계산기 제품 · 옵션(설계서 2026-11-12 온톨로지 4.1 · D191) — 옮기기 묶음(``import``)이 계산기 정본에서 만든 제품 라인 ·
  옵션 **만들기**(실음 칸에 금액 칸 없음)와 그 항목에서 ``calc:`` 로 가는 ``value_from`` 링크. 값은 계산기가 정본이라(D179) 글 ·
  금액을 하나씩 확인할 것이 없다.

- ``rules`` ⑥ 규칙 · 제품 잇기(온톨로지 4.2 · D194) — 옮기기 묶음이 넣은 규칙 → 계산기 제품 라인 · 옵션 ``applies_to`` 링크 더하기.

①과 ④ · ⑤ · ⑥ 은 글 · 금액 · 규칙이 바뀌지 않아 관리자가 한꺼번에 승인할 수 있다(:func:`bulk_ok_any_grade` — D151 · D192).
① 은 상담팀장도(D167 — 묶음은 :func:`.access.wide_bins`). ⑤ · ⑥ 은 사장님(관리자)만(D192 · D194).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from foms.services.brain.constants import AGENT_WORK_TYPES, OP_CREATE, OP_LINK_ADD, OP_UPDATE

__all__ = ["ADMIN_WIDE_BINS", "BINS", "BIN_CALC", "BIN_CONTENT", "BIN_DECIDE", "BIN_MARK", "BIN_NAMES", "BIN_RULES",
           "LABEL_KEYS", "bulk_ok_any_grade", "calc_change", "card_bin", "change_ends", "label_only_change", "owner_decides",
           "ref_label", "rule_link_change"]

BIN_NAMES, BIN_CONTENT, BIN_DECIDE, BIN_MARK = "names", "content", "decide", "mark"
BIN_CALC, BIN_RULES = "calc", "rules"
#: 화면 차례.
BINS: tuple[str, ...] = (BIN_NAMES, BIN_CONTENT, BIN_DECIDE, BIN_MARK, BIN_CALC, BIN_RULES)
#: 관리자가 등급과 상관없이 한꺼번에 승인하는 묶음(D151 · ⑤ 는 D192 · ⑥ 은 D194).
ADMIN_WIDE_BINS: frozenset[str] = frozenset({BIN_NAMES, BIN_MARK, BIN_CALC, BIN_RULES})
#: ⑤ — 계산기에서 만든 항목 유형 · 키 머리(:mod:`.catalog_plan`) · 만든 쪽(:data:`.proposals.IMPORT_PROPOSER` 이름) · 값 링크.
CALC_TYPES: frozenset[str] = frozenset({"product_line", "option"})
CALC_KEY_HEADS: tuple[str, ...] = ("product_line/", "option/")
CALC_PROPOSER, CALC_REF, VALUE_LINK, RULE_LINK = "import", "calc:", "value_from", "applies_to"
#: ⑤ 에 들지 못하게 하는 실음 칸(금액 · 값 사본 — 계산기 값은 ``value_from`` 으로만 가리킨다, D179).
_AMOUNT_KEYS: frozenset[str] = frozenset({"price", "prices", "amount", "values", "price_30cm", "price_1cm", "price_1m",
                                          "coupon_value"})
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


def _amount_free(fields: Optional[Mapping[str, Any]]) -> bool:
    """만들기 제안의 실음 칸 '후' 값에 금액 · 값 사본 칸이 없나."""
    entry = (fields or {}).get("payload") or {}
    after = entry.get("after") if isinstance(entry, Mapping) else None
    return not (isinstance(after, Mapping) and _AMOUNT_KEYS.intersection(after))


def calc_change(op: str, item_type: Optional[str], fields: Optional[Mapping[str, Any]], link_kind: Optional[str], *,
                proposed_by: Optional[str] = None, link_from: Optional[str] = None,
                link_to: Optional[str] = None) -> bool:
    """⑤ 계산기 제품 · 옵션인가 — 옮기기 묶음이 만든 제품 라인 · 옵션 만들기(금액 칸 없음) 또는 그 항목 → ``calc:`` 값 링크."""
    if proposed_by != CALC_PROPOSER:
        return False
    if op == OP_CREATE:
        return item_type in CALC_TYPES and _amount_free(fields)
    return (op == OP_LINK_ADD and link_kind == VALUE_LINK and str(link_from or "").startswith(CALC_KEY_HEADS)
            and str(link_to or "").startswith(CALC_REF))


def rule_link_change(op: str, link_kind: Optional[str], *, proposed_by: Optional[str] = None,
                     link_to: Optional[str] = None) -> bool:
    """⑥ 규칙 · 제품 잇기인가 — 옮기기 묶음이 넣은 규칙 → 계산기 제품 라인 · 옵션 ``applies_to`` 더하기(허용 짝은 넣을 때 이미 봤다)."""
    return (proposed_by == CALC_PROPOSER and op == OP_LINK_ADD and link_kind == RULE_LINK
            and str(link_to or "").startswith(CALC_KEY_HEADS))


def change_ends(change: Any) -> dict[str, Any]:
    """제안 줄 → :func:`card_bin` 의 ⑤ 판정 칸(만든 쪽 · 링크 두 끝)."""
    return {"proposed_by": getattr(change, "proposed_by", None), "link_from": getattr(change, "link_from", None),
            "link_to": getattr(change, "link_to", None)}


def card_bin(op: str, item_type: Optional[str], fields: Optional[Mapping[str, Any]], link_kind: Optional[str],
             **ends: Any) -> str:
    """제안 하나의 묶음. ``ends`` = :func:`change_ends`(없으면 ⑤ 는 판정하지 않는다 — 예전 네 묶음 그대로)."""
    if calc_change(op, item_type, fields, link_kind, **ends):
        return BIN_CALC
    if rule_link_change(op, link_kind, proposed_by=ends.get("proposed_by"), link_to=ends.get("link_to")):
        return BIN_RULES
    if label_only_change(op, fields):
        return BIN_NAMES
    if owner_decides(op, item_type):
        return BIN_DECIDE
    if op == OP_LINK_ADD and link_kind == COPY_LINK:
        return BIN_MARK
    return BIN_CONTENT


def owner_decides(op: str, item_type: Optional[str]) -> bool:
    """③ 사장님이 정해 주실 것(엇갈림 · 물어볼 것 항목 만들기)인가 — ADMIN 만 보고 정한다(D167). 그 항목의 고침 · 은퇴 · 링크는 ②."""
    return op == OP_CREATE and item_type in AGENT_WORK_TYPES


def label_only_change(op: str, fields: Optional[Mapping[str, Any]]) -> bool:
    """이름표 칸만 바뀌는 고침(①)인가 — 상담팀장도 결정하는 제안(D167)."""
    return op == OP_UPDATE and _label_only(fields)


def bulk_ok_any_grade(op: str, item_type: Optional[str], fields: Optional[Mapping[str, Any]],
                      link_kind: Optional[str], bins: frozenset[str] = ADMIN_WIDE_BINS, **ends: Any) -> bool:
    """등급과 상관없이 한꺼번에 승인할 수 있나 — 이 사람의 넓은 묶음(관리자 ① · ④ · ⑤ — D151 · D192, 상담팀장 ① — D167) 안이면."""
    return card_bin(op, item_type, fields, link_kind, **ends) in bins


def ref_label(ref: Optional[str]) -> str:
    """링크 끝 하나의 화면 이름 — 바깥 사본 자리는 사람이 읽는 이름, 그 밖은 그대로."""
    if not ref:
        return ""
    if ref in REF_LABELS:
        return REF_LABELS[ref]
    head = next((h for h in _REF_HEADS if ref.startswith(h)), None)
    return f"{_REF_HEADS[head]} · {ref[len(head):]}" if head else ref
