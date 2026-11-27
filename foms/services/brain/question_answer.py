"""③ 사장님이 정해 주실 것 — 질문 카드 답 **한 번에 저장**(설계서 2026-11-26 온톨로지 잇기 3.2 · 카드 비평 S4 · S8 · S3).

예전 화면은 답 하나를 세 번 따로 보냈다(고침 제안 → 승인 → 카드 닫기). 가운데서 끊기면 열린 고침 제안이 고아로 남거나, 지식은
바뀌었는데 카드는 열린 채였다(S4). 이제 액션 :data:`.answers.ANSWER_ACTION` 하나가 한 트랜잭션(커밋은 부르는 쪽 — API 는 막히면 통째
되돌린다)에서:

1. 질문 카드를 잠가 읽고 결정할 사람인지 본다(:func:`.decide._locked_open` — ③ 은 사장님만, 볼 수 없으면 없는 카드와 같은 답).
2. 고칠 글이 있으면(바깥 글이 맞아요 = 적은 글로 바꿈 · 둘 다 맞아요 = 지금 글 끝에 적은 한 줄을 붙임) 카드가 다루는 지식(근거
   ``about:<키>`` 가운데 볼 수 있는 첫 것 — 화면과 같은 고름)의 고침 제안을 만들고 곧바로 넣는다(:func:`.decide.apply_decision` —
   기준 판 · 권한 · 등급 B 확인은 그대로 지난다. 확인 글은 사장님이 적은 글이 곧 확인이라 서버가 채운다).
3. 카드를 그 답 코드로 닫는다(:func:`.decide.reject_decision` — 결정 시간 ``view_ms`` 는 이 줄에만 싣는다).
4. 카드 줄에 사장님이 적은 글과 그 고침 번호를 남긴다(:func:`.answers.keep_answer`).

**금액 알림(S3)**: 다루는 지식이 견적 계산기가 원본인 가격 규칙 · 옵션(:func:`calc_sourced`)이고 사장님이 적은 글에 금액 꼴
(:data:`MONEY_RE`)이 있으면, 아무것도 쓰지 않고 알림 한 줄(:data:`MONEY_ASK`)을 돌려준다(``saved`` 거짓). 화면은 그 줄을 보이고,
같은 글로 한 번 더 누르면 ``money_ok`` 를 실어 저장한다 — 막지는 않는다.

**카드가 생긴 뒤 지식이 바뀐 답(결함 2026-11-27)**: 막지 않는다(화면이 그때는 지금 글만 칸에 넣어 사장님이 지금 글을 보고
고친다). 응답에 ``changed_since``(:func:`.about_fresh.about_changed`) 한 칸을 싣고 로그 한 줄을 남긴다 — 뒤 분석용.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain.about_fresh import about_changed
from foms.services.brain.answers import ANSWER_ACTION, keep_answer
from foms.services.brain.constants import ANSWER_CODES, PRICE_RULE_TYPE, basis_of
from foms.services.brain.decide import (
    _locked_open, apply_decision, expire_ai_proposals, record_proposal, reject_decision,
)
from foms.services.brain.errors import BrainConflictError, BrainShapeError, BrainTargetError
from foms.services.brain.inbox import ABOUT_REF, about_items
from foms.services.brain.inbox_bins import CALC_REF, VALUE_LINK, owner_decides
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.review_rules import confirm_value
from foms.services.brain.scope import Viewer, viewer_of
from foms.services.brain.store import current_object, is_current
from foms.services.datetime_kst import now_utc_naive

__all__ = ["ASK_MONEY", "CALC_TYPES", "MONEY_ASK", "MONEY_RE", "answer_question", "calc_sourced"]

OUTSIDE_RIGHT, BOTH_RIGHT = "outside_right", "both_right"
#: 고침 제안 까닭 글 — 예전 화면이 보내던 글 그대로 + 어느 카드의 답인지. 여기 없는 답은 지식 글을 고치지 않는다.
REASON_HEAD = "사장님 답 — "
SAID = {OUTSIDE_RIGHT: "바깥 글이 맞아요", BOTH_RIGHT: "둘 다 맞아요"}
#: 값의 원본이 견적 계산기일 수 있는 유형(가격 규칙 · 옵션).
CALC_TYPES: tuple[str, ...] = (PRICE_RULE_TYPE, "option")
#: 금액 꼴 — 숫자 뒤 (십 · 백 · 천 · 만 · 억) 원. '원본 · 원래 · 원목 · 원형 · 원칙 · 원단 · 원리' 같은 낱말은 뺀다.
MONEY_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:[십백천만억]\s*)*원(?![본래목형칙단리])")
ASK_MONEY = "calc_money"
MONEY_ASK = "이 지식의 값은 견적 계산기가 원본이에요. 글에도 금액을 적을까요? 적으려면 한 번 더 눌러 주세요."

logger = logging.getLogger(__name__)


def calc_sourced(session: Any, row: BrainObject) -> bool:
    """값의 원본이 견적 계산기인 가격 규칙 · 옵션인가 — 근거 종류(``payload.basis``) 가 계산기 · 근거 자리가 ``calc:`` · 지금
    계산기 자리로 가는 값 링크(``value_from``)가 있다."""
    if row.item_type not in CALC_TYPES:
        return False
    if basis_of(row.payload) == "calc" or str(row.evidence_ref or "").startswith(CALC_REF):
        return True
    return session.execute(select(BrainLink.id).where(
        is_current(BrainLink), BrainLink.kind == VALUE_LINK, BrainLink.from_key == row.item_key,
        BrainLink.to_key.like(CALC_REF + "%")).limit(1)).first() is not None


def _about(session: Any, viewer: Viewer, card: BrainChange) -> Optional[dict[str, Any]]:
    """카드가 다루는 지식 — 근거 ``about:<키>`` 가운데 이 사람이 볼 수 있는 첫 것(화면의 첫 '회사 지식' 칸과 같다)."""
    found = about_items(session, viewer, [card])
    for ref in card.evidence or []:
        key = ref[len(ABOUT_REF):] if isinstance(ref, str) and ref.startswith(ABOUT_REF) else None
        if key in found:
            return found[key]
    return None


def _rewrite(session: Any, card: BrainChange, row: BrainObject, text: str, code: str, *, actor: Any,
             now: datetime.datetime) -> int:
    """다루는 지식 글을 ``text`` 로 고치는 사람 제안 → 곧바로 넣기. 넣은 제안 번호."""
    user_id = int(viewer_of(actor).user_id or 0)
    edit = propose_update(session, key=row.item_key, base_version=row.version, after={"text": text},
                          reason=f"{REASON_HEAD}{SAID[code]} · 질문 카드 {card.id}", proposer=Proposer.user(user_id),
                          now=now, action=ANSWER_ACTION)
    record_proposal(session, edit, actor_id=user_id, now=now)
    field, value = confirm_value(edit.op, edit.fields, edit.item_type)
    apply_decision(session, edit.id, actor=actor, base_version=row.version, confirm={"field": field or "", "value": value},
                   now=now)
    return int(edit.id)


def answer_question(session: Any, card_id: Any, *, actor: Any, code: str, text: Optional[str] = None,
                    base_version: Optional[int] = None, money_ok: bool = False, view_ms: Any = None,
                    now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """질문 카드 답 하나를 한 번에 저장한다(모듈 설명). ``text`` 는 사장님이 적은 글(바깥 글이 맞아요 = 새 지식 글 전체 · 둘 다
    맞아요 = 끝에 붙일 한 줄 · 회사 지식이 맞아요 = 없음), ``base_version`` 은 화면이 본 그 지식의 판.

    돌려주는 값: 저장했으면 ``{"change_id", "code", "edit", "saved": True, "changed_since"}``, 금액 알림이면 ``{"change_id",
    "saved": False, "ask", "message", "changed_since"}``(아무것도 쓰지 않음). ``changed_since`` = 카드가 생긴 뒤 다루는 지식이
    바뀌었나(다루는 지식이 없으면 거짓 — 막지 않는다).

    Raises:
        BrainPermissionError(결정할 수 없음 · 볼 수 없음 · 없는 카드) · BrainTargetError(닫힌 카드 · 질문 카드 아님 · 다루는 지식
        없음 · 바뀐 글 없음) · BrainShapeError · BrainConflictError(기준 판) · BrainRejectedError · BrainDocSyncError.
    """
    now = now or now_utc_naive()
    if code not in ANSWER_CODES:
        raise BrainShapeError([f"code: {' / '.join(ANSWER_CODES)} 가운데 하나여야 한다"])
    expire_ai_proposals(session, now=now)  # 4주 지난 AI 카드는 쓰기 전에 닫혀 대상 오류가 된다(반쯤 쓰지 않게)
    card = _locked_open(session, card_id, actor)
    if not owner_decides(card.op, card.item_type):
        raise BrainTargetError(f"③ 질문 카드가 아니다: {card.id}")
    typed = text.strip() if isinstance(text, str) else ""
    about = _about(session, viewer_of(actor), card)
    changed = about is not None and about_changed(card, about)
    edit_id: Optional[int] = None
    if code not in SAID:  # 회사 지식이 맞아요 — 지식 글은 그대로
        if typed:
            raise BrainShapeError(["text: 이 답은 고칠 글을 받지 않는다"])
    else:
        if not typed:
            raise BrainShapeError(["text: 고칠 글이 있어야 한다"])
        row = current_object(session, about["key"]) if about is not None else None
        if row is None:
            raise BrainTargetError("다루는 지식을 찾지 못했다")
        if base_version != row.version:
            raise BrainConflictError(row.version)
        after = typed if code == OUTSIDE_RIGHT else f"{(row.text or '').rstrip()}\n{typed}"
        if not money_ok and MONEY_RE.search(typed) and calc_sourced(session, row):
            return {"change_id": card.id, "saved": False, "ask": ASK_MONEY, "message": MONEY_ASK, "changed_since": changed}
        edit_id = _rewrite(session, card, row, after, code, actor=actor, now=now)
    reject_decision(session, card.id, actor=actor, code=code, view_ms=view_ms, now=now)
    keep_answer(card, code=code, text=typed or None, edit=edit_id, key=about["key"] if about is not None else None)
    session.flush()
    if changed:
        logger.info("brain answer after target changed: card=%s code=%s edit=%s", card.id, code, edit_id)
    return {"change_id": card.id, "code": code, "edit": edit_id, "saved": True, "changed_since": changed}
