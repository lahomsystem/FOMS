"""생산 넘어간 주문의 도면 수정 — 도면 열쇠 · 막힘 판정(도면별) · 글 꼴(설계서 2026-11-25 §3-2 · §3-3 · §3-6 · §10). 순수 함수(쿼리 0).

자료는 주문 JSON 의 **서버 소유** 칸 ``structured_data.drawing_fix`` 하나다(안 ⓐ — 마이그레이션 없음, 칸이 없으면 "고치는 중 없음")::

    {"fixing": {"sheet:<시트 id>": {"no", "by_user_id", "by_name", "at"}, "file:<저장 key>": {...}},
     "requests": [{"id", "from": "factory", "targets": ["sheet:…"], "numbers", "note", "photos", "factory", "state": "open|done|rejected", …}],
     "log": [{"act", "idents", "numbers", "by_name", "at"}]}

* **열쇠**(:func:`fix_ident`) = ``sheet:<sheet_id>``(마법사 시트 — 판이 바뀌어도 같다) 또는 ``file:<저장 key>``(직접 올린 파일). 공장 꼴 패킹 줄
  열쇠(``packing_factory``)와 같은 꼴이다. 막힘 · 풀림 · 패킹을 보는 모든 자리가 이 함수 하나만 쓴다.
* **막힘**(:func:`blocked`) — 통째 = :func:`~foms.services.orders.confirm_drawing_gate.drawing_revision_in_progress`(TRANSFERRED · 대상을 못 고른
  RETURNED, 지금 그대로) · 도면별 = (대상을 고른 영업 요청의 ``target_idents``) ∪ ``fixing`` 열쇠 ∪ 열린 공장 요청 ``targets``. 도면별은 단계가
  생산 · 시공일 때만 본다(고객컨펌 단계 영업 요청은 지금처럼 통째 — §3-3 4).
* 쓰기(풀림 · 시작 · 취소 · 요청 · 반려)는 이 모듈에 없다 — D2 ~ D4 가 따로 이름을 붙여 더한다(§8-5). 폼 저장 · 초안 · 주문 만들기는 이 칸을 못
  바꾼다(``structured_form_projection.SERVER_LOCKED_KEYS`` · ``drawing_factory.strip_client_factory_state``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import (
    drawing_revision_in_progress,
    per_drawing_stage,
    revision_request_target_keys,
    targeted_revision_request,
)
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY, current_factories
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.production.factory_constants import FACTORIES

SHEET_PREFIX = "sheet:"
FILE_PREFIX = "file:"
#: 도면별 막힘의 까닭(``Block.why`` 값) — 영업 요청 · 도면팀 [수정 시작] · 공장 요청.
WHY_SALES = "sales"
WHY_FIXING = "fixing"
WHY_FACTORY = "factory"
REQUEST_OPEN = "open"

#: 숫자를 읽을 때 끝소리에 받침이 있는 끝자리(일 · 삼 · 육 · 칠 · 팔 · 영 → 은, 이 · 사 · 오 · 구 → 는) — §2-3 조사.
_FINAL_DIGITS = frozenset("136780")


@dataclass(frozen=True)
class Block:
    """한 주문의 막힘 — ``whole`` = 주문 통째, ``idents`` = 도면별로 막힌 열쇠, ``why`` = 열쇠마다 까닭(:data:`WHY_SALES` …)."""

    whole: bool
    idents: frozenset[str] = frozenset()
    why: dict[str, tuple[str, ...]] = field(default_factory=dict, compare=False, hash=False)


# --------------------------------------------------------------------------- #
# 열쇠
# --------------------------------------------------------------------------- #
def fix_ident(entry: Any) -> str:
    """도면 항목(확정 도면 한 줄 · ``{sheet_id}`` · ``{key}``)의 열쇠 — ``sheet:<id>`` 우선, 없으면 ``file:<key>``, 둘 다 없으면 빈 글."""
    if not isinstance(entry, dict):
        return ""
    sid = clean_sheet_id(entry.get("sheet_id"))
    if sid:
        return f"{SHEET_PREFIX}{sid}"
    key = str(entry.get("key") or "").strip()
    return f"{FILE_PREFIX}{key}" if key else ""


def idents_for_keys(sd: Any, keys: Iterable[str]) -> list[str]:
    """지금 확정 도면 저장 key → 열쇠(``keys`` 순서, 지금 도면에 없는 key 는 버림) — 영업 요청 줄의 ``target_idents``."""
    by_key = {entry["key"]: fix_ident(entry) for entry in resolve_final_drawing_files(sd)}
    return list(dict.fromkeys(by_key[k] for k in keys if by_key.get(k)))


def _clean_idents(raw: Iterable[Any]) -> list[str]:
    return [x.strip() for x in raw if isinstance(x, str) and x.strip()]


def _fix_table(sd: Any) -> dict[str, Any]:
    raw = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    return raw if isinstance(raw, dict) else {}


# --------------------------------------------------------------------------- #
# 막힘
# --------------------------------------------------------------------------- #
def sales_request_idents(sd: Any) -> frozenset[str]:
    """대상을 고른 영업 요청(생산 · 시공 단계 RETURNED)이 막는 열쇠 — 새 줄은 ``target_idents``, 옛 줄은 ``target_drawing_keys`` 를 지금
    도면으로 푼다(§3-2). 통째 요청 · 요청 없음은 빈 것(통째는 :func:`blocked` 의 ``whole``)."""
    request = targeted_revision_request(sd)
    if request is None:
        return frozenset()
    stored = _clean_idents(request.get("target_idents") or []) if isinstance(request.get("target_idents"), list) else []
    return frozenset(stored or idents_for_keys(sd, revision_request_target_keys(request)))


def fixing_idents(sd: Any) -> frozenset[str]:
    """도면팀 [수정 시작] 열쇠(``drawing_fix.fixing``)."""
    fixing = _fix_table(sd).get("fixing")
    return frozenset(_clean_idents(fixing)) if isinstance(fixing, dict) else frozenset()


def open_request_idents(sd: Any) -> frozenset[str]:
    """열린 공장 요청의 대상 열쇠(사장님 답 "요청하면 바로 막기")."""
    requests = _fix_table(sd).get("requests")
    out: list[str] = []
    for request in requests if isinstance(requests, list) else []:
        if isinstance(request, dict) and request.get("state") == REQUEST_OPEN and isinstance(request.get("targets"), list):
            out += _clean_idents(request["targets"])
    return frozenset(out)


def blocked(sd: Any) -> Block:
    """주문 하나의 막힘(§3-3) — 통째(지금 규칙) + 도면별(생산 · 시공 단계에서만: 영업 요청 대상 ∪ 고치는 중 ∪ 열린 공장 요청).

    Args:
        sd: 주문 ``structured_data``(읽기만).

    Returns:
        :class:`Block`. 생산 · 시공 단계가 아니면 ``idents`` 는 늘 비어 있다.
    """
    whole = drawing_revision_in_progress(sd)
    if not per_drawing_stage(sd):
        return Block(whole)
    why: dict[str, list[str]] = {}
    for reason, idents in ((WHY_SALES, sales_request_idents(sd)), (WHY_FIXING, fixing_idents(sd)),
                           (WHY_FACTORY, open_request_idents(sd))):
        for ident in sorted(idents):
            why.setdefault(ident, []).append(reason)
    return Block(whole, frozenset(why), {ident: tuple(reasons) for ident, reasons in why.items()})


def entry_blocked(block: Block, entry: Any) -> bool:
    """도면 한 장이 막혔는지 — 통째거나 그 장 열쇠가 도면별로 막힘."""
    return block.whole or (fix_ident(entry) in block.idents)


def drawing_blocked(sd: Any, entry: Any, *, block: Optional[Block] = None) -> bool:
    """도면 한 장이 막혔는지(:func:`blocked` 를 한 번 계산해 둔 값이 있으면 ``block`` 으로 넘긴다)."""
    return entry_blocked(block if block is not None else blocked(sd), entry)


def blocked_entries(sd: Any, *, block: Optional[Block] = None, factory: Optional[int] = None) -> list[dict[str, Any]]:
    """지금 확정 도면 중 막힌 장(통째면 모두) — ``[{no, key, ident, factory}]`` 도면 번호 순. ``factory`` 를 주면 그 공장 장만."""
    block = block if block is not None else blocked(sd)
    out = []
    for no, (entry, owner) in enumerate(current_factories(sd), 1):
        if (factory is None or owner == factory) and entry_blocked(block, entry):
            out.append({"no": no, "key": entry["key"], "ident": fix_ident(entry), "factory": owner})
    return out


def per_drawing_numbers(sd: Any, *, block: Optional[Block] = None, factory: Optional[int] = None) -> list[int]:
    """도면별로 막힌 장 번호(통째면 빈 목록 — 통째 글은 지금 글 그대로)."""
    block = block if block is not None else blocked(sd)
    if block.whole or not block.idents:
        return []
    return [row["no"] for row in blocked_entries(sd, block=block, factory=factory)]


def factory_has_blocked(sd: Any, factory: int, *, block: Optional[Block] = None) -> bool:
    """그 공장에 막힌 도면이 있는지([N공장 완료] 막힘 — 통째면 늘 참)."""
    block = block if block is not None else blocked(sd)
    return block.whole or bool(blocked_entries(sd, block=block, factory=factory))


def complete_blocked(sd: Any, *, block: Optional[Block] = None) -> bool:
    """[제작 완료]가 막히는지 — 통째 또는 막힌 도면이 하나라도(사장님 답 Q7 "그 도면이 끝날 때까지 막힘")."""
    block = block if block is not None else blocked(sd)
    return block.whole or bool(blocked_entries(sd, block=block))


def factory_complete_blocked(sd: Any, factory: int, *, final: bool, block: Optional[Block] = None) -> bool:
    """[N공장 완료]가 막히는지 — 그 공장에 막힌 도면 · 마지막 공장(= 주문 제작 완료)이면 [제작 완료]와 같은 판정."""
    block = block if block is not None else blocked(sd)
    return complete_blocked(sd, block=block) if final else factory_has_blocked(sd, factory, block=block)


# --------------------------------------------------------------------------- #
# 통째 작업에서 막힌 도면 빼기(§3-6 ①)
# --------------------------------------------------------------------------- #
def expand_plan(sd: Any, factories: Iterable[int] = FACTORIES) -> Optional[dict[str, Any]]:
    """통째 작업을 도면별 표시로 풀어 적을지 — 통째가 아니고 지금 도면 중 막힌 장이 1장 이상일 때만(풀이 §11-6).

    Args:
        sd: 주문 ``structured_data``.
        factories: 누른 사람이 쓸 수 있는 공장(반장은 자기 공장 장만 — ``factory_gate`` 와 같은 규칙, §3-6).

    Returns:
        ``{total, numbers, skip_keys, keys}`` — ``numbers`` = 막힌 장 번호, ``skip_keys`` = 막힌 장 key, ``keys`` = 풀어 적을 장 key
        (막히지 않은 · 쓸 수 있는 공장 장). 풀어 적을 일이 아니면 None(지금처럼 칸만 켬).
    """
    block = blocked(sd)
    if block.whole or not block.idents:
        return None
    allowed = set(factories)
    rows = current_factories(sd)
    skipped = [(no, entry) for no, (entry, _f) in enumerate(rows, 1) if entry_blocked(block, entry)]
    if not skipped:
        return None
    keys = [entry["key"] for entry, owner in rows if owner in allowed and not entry_blocked(block, entry)]
    return {"total": len(rows), "numbers": [no for no, _e in skipped], "skip_keys": [e["key"] for _no, e in skipped],
            "keys": keys}


def expand_confirm(sd: Any, factories: Iterable[int] = FACTORIES) -> Optional[dict[str, Any]]:
    """통째 작업 확인 창 본문 재료(§2-4 · §10) — ``{done, numbers, tail}`` 또는 None(지금 글 그대로).

    화면(``foms-production-sheet-parts.js``)이 "이 주문의 도면 {sheets}장 중 {done}장이 {파트} 완료로 처리돼요. " + ``tail`` 로 잇는다.
    """
    plan = expand_plan(sd, factories)
    if plan is None:
        return None
    return {"done": len(plan["keys"]), "numbers": plan["numbers"], "tail": skip_tail(plan["numbers"])}


def confirm_extras(sd: Any, factories: Iterable[int] = FACTORIES) -> dict[str, Any]:
    """공정 API · 작업 시트 · '내 공정' [끝] 확인 창 자료에 더할 값 — 막힌 도면이 있으면 ``{"fix": …}``, 없으면 ``{}``(응답 그대로)."""
    fix = expand_confirm(sd, factories)
    return {"fix": fix} if fix else {}


# --------------------------------------------------------------------------- #
# 글 꼴(새 글 둘 — §10)
# --------------------------------------------------------------------------- #
def numbers_text(numbers: Iterable[int]) -> str:
    """도면 번호 줄 — "2" · "2 · 3"."""
    return " · ".join(str(n) for n in numbers)


def number_topic(n: int) -> str:
    """숫자 뒤 토씨(은/는) — 끝자리 소리로(1 · 3 · 6 · 7 · 8 · 0 → 은, 2 · 4 · 5 · 9 → 는)."""
    return "은" if str(abs(int(n)))[-1] in _FINAL_DIGITS else "는"


def fixing_label(numbers: Iterable[int]) -> str:
    """도면별 막힘 글 "도면 2 고치는 중" · "도면 2 · 3 고치는 중"(배지 · 공정 줄 · 작업 시트, §10 '공장 막힘(번호)')."""
    return f"도면 {numbers_text(numbers)} 고치는 중"


def skip_tail(numbers: list[int]) -> str:
    """확인 창 본문 뒤 문장 — "도면 2는 고치는 중이라 빼요." · "도면 2 · 3은 고치는 중이라 빼요."."""
    return f"도면 {numbers_text(numbers)}{number_topic(numbers[-1])} 고치는 중이라 빼요."


def expand_confirm_body(sheets: int, done: int, part_label: str, numbers: list[int]) -> str:
    """통째 작업 확인 창 본문 전부(시험 · 서버 쪽 글 — 화면 JS 와 같은 글)."""
    return f"이 주문의 도면 {sheets}장 중 {done}장이 {part_label} 완료로 처리돼요. {skip_tail(numbers)}"


__all__ = [
    "Block", "DRAWING_FIX_KEY", "FILE_PREFIX", "REQUEST_OPEN", "SHEET_PREFIX", "WHY_FACTORY", "WHY_FIXING", "WHY_SALES",
    "blocked", "blocked_entries", "complete_blocked", "confirm_extras", "drawing_blocked", "entry_blocked", "expand_confirm", "expand_confirm_body",
    "expand_plan", "factory_complete_blocked", "factory_has_blocked", "fix_ident", "fixing_idents", "fixing_label", "idents_for_keys",
    "number_topic", "numbers_text", "open_request_idents", "per_drawing_numbers", "sales_request_idents", "skip_tail",
]
