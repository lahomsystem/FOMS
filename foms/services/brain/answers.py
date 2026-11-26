"""③ 사장님이 정해 주실 것 — 질문 카드에 남는 **사장님 답**(설계서 2026-11-26 온톨로지 잇기 3.2 · 카드 비평 S4 · S5 · S1).

답(:data:`.constants.ANSWER_CODES`)으로 닫힌 질문 카드 줄(``brain_changes`` — 엇갈림 · 물어볼 것 만들기 제안)의 실음 칸 '후' 값에
:data:`ANSWER_FIELD` 하나를 둔다(새 DB 칸 없음): ``{"code": 답 코드, "text": 사장님이 실제로 적은 글 또는 없음, "edit": 그 답으로
넣은 지식 고침 제안 번호 또는 없음, "key": 답이 다룬 지식 키}``. 고친 글은 고침 제안에도 있지만 '둘 다 맞아요'는 지식 글 끝에 붙인
한 줄만이 사장님 글이라, 적은 글 그대로를 카드 줄에 남긴다. 쓰는 곳은 한 번에 저장(:mod:`.question_answer`) 하나, 지우는 곳은 방금
정한 것 되돌리기(:func:`.decide.reopen_decision`) 하나다.

읽는 곳: 놓을 자리 판정자의 '사장님이 이미 정한 것'(:func:`foms.services.cs_agent.handoff_learning_place.decided_lines` — 적은
글을 싣는다) · 밤 배우기의 '사장님이 정한 지식'(:mod:`foms.services.cs_agent.handoff_learning_owner` — 사람 없는 길을 막는다).
둘 다 :func:`answered_about` 하나로 대상 키를 찾는다(날짜 창 없이 — 같은 지식에 대해 정한 것은 오래돼도).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement

from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import AGENT_WORK_TYPES, ANSWER_CODES, CHANGE_REJECTED, OP_CREATE

__all__ = ["ANSWER_ACTION", "ANSWER_FIELD", "answered_about", "card_answer", "drop_answer", "keep_answer"]

#: 한 번에 저장 액션 이름(:mod:`.actions`) — 그 답으로 만든 지식 고침 제안의 ``action`` 칸에도 남는다.
ANSWER_ACTION = "answer_question"
#: 질문 카드 실음 칸('후') 안에서 사장님 답을 담는 칸 이름.
ANSWER_FIELD = "answer"


def answered_about(keys: Sequence[str]) -> ColumnElement[bool]:
    """답으로 닫힌 ③ 질문 카드 가운데 다룬 지식이 ``keys`` 안인 것(질의 조건) — 카드 실음 칸 ``target`` 또는 답 칸 ``key``.

    다시 연 카드(:func:`.decide.reopen_decision`)는 열려 있어 들지 않는다. 키는 실음 칸 JSON 경로로 읽는다(제안함 보기 범위와 같은
    꼴 — :mod:`.inbox`)."""
    wanted = [k for k in keys if isinstance(k, str) and k]
    target = BrainChange.fields[("payload", "after", "target")].as_string()
    answered = BrainChange.fields[("payload", "after", ANSWER_FIELD, "key")].as_string()
    return and_(BrainChange.status == CHANGE_REJECTED, BrainChange.op == OP_CREATE,
                BrainChange.item_type.in_(AGENT_WORK_TYPES), BrainChange.reject_code.in_(ANSWER_CODES),
                or_(target.in_(wanted), answered.in_(wanted)))


def card_answer(fields: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """질문 카드 줄 ``fields`` → 남긴 사장님 답(없으면 빈 dict — 한 번에 저장 앞에 닫힌 카드)."""
    payload = ((fields or {}).get("payload") or {}).get("after")
    answer = payload.get(ANSWER_FIELD) if isinstance(payload, dict) else None
    return dict(answer) if isinstance(answer, dict) else {}


def keep_answer(card: BrainChange, *, code: str, text: Optional[str], edit: Optional[int], key: Optional[str]) -> None:
    """질문 카드 줄에 사장님 답을 남긴다(실음 칸 '후' 값 — deepcopy → 고침 → 다시 넣기 → ``flag_modified``). flush 는 부르는 쪽."""
    fields = copy.deepcopy(card.fields or {})
    entry = fields.get("payload") if isinstance(fields.get("payload"), dict) else {"before": None, "after": {}}
    after = dict(entry.get("after") or {})
    after[ANSWER_FIELD] = {"code": code, "text": text or None, "edit": edit, "key": key}
    entry["after"] = after
    fields["payload"] = entry
    card.fields = fields
    flag_modified(card, "fields")


def drop_answer(card: BrainChange) -> None:
    """다시 연 질문 카드에서 남긴 답을 뺀다(없으면 그대로). flush 는 부르는 쪽."""
    if not card_answer(card.fields):
        return
    fields = copy.deepcopy(card.fields)
    fields["payload"]["after"].pop(ANSWER_FIELD, None)
    card.fields = fields
    flag_modified(card, "fields")
