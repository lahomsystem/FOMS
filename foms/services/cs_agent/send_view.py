"""[보내기] · [수정하기] 짧은 화면의 재료 — GET 은 보여 주기만 한다(보내지 않고 · 표를 쓰지 않고 · DB 를 쓰지 않는다).

플랜 C10-3 · 설계서 17.2.1(링크 길 — 열기(GET)는 한 번용 표를 쓰지 않는다: 메신저 링크 미리 읽기 대비). 화면이 보일 글은 그 상담의
메모를 Open API 로 다시 읽은 '손님께 보낼 답'이다(DB 에는 가린 사본만 있다). 이 화면을 연 직원 · 그 차례 · 그 메모로 서명한 표를
싣는다 — POST 는 그 표와 CSRF 로만 움직인다.

링크 주소의 상담 id(``c``)가 차례와 다르면 열지 않는다 — 다른 환경(스테이징 · 운영)의 같은 차례 번호로 잘못 들어온 링크가
엉뚱한 상담을 보이지 않게.

작은 창 접목 두 줄(설계서 2026-11-14-foms-graft 3.9 — 관리 칸 :mod:`.graft_settings`, 끄면 칸 자체가 없다): :func:`wam_graft` 가
그 차례의 근거 칩(셋까지 — 회사 지식 카드 · 주문 화면의 FOMS **절대 주소**: 채널톡이 거쳐 여는 창이라 상대 주소는 채널톡 쪽으로
풀린다)과 작은 창 줄 제안 하나를 읽기만 한다.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy import select

from foms.persistence.graft.models import ErpActionProposal
from foms.persistence.main.models import CsAgentTurn
from foms.services.ai_staff.registry import proposer
from foms.services.brain.usage_events import refs_of
from foms.services.cs_agent.case_memory import EDIT_REASONS
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader
from foms.services.cs_agent.drafting_read import freshness, memo_draft, read_lines
from foms.services.cs_agent.edit_detail import MAX_DETAIL, switches
from foms.services.cs_agent.edit_photos import MAX_BYTES as PHOTO_MAX_BYTES, MAX_PHOTOS
from foms.services.cs_agent.graft_settings import actions_on, evidence_on
from foms.services.cs_agent.graft_step import AGENT, SOURCE_KIND, brain_labels, order_label
from foms.services.cs_agent.memo import memo_allowed
from foms.services.cs_agent.report import desk_link
from foms.services.cs_agent.send import BASE_URL_ENV, SEND_BRAND
from foms.services.cs_agent.send_auth import issue_send_token
from foms.services.cs_agent.send_flow import MAX_NOTE, MAX_REWRITES, MAX_TEXT, MESSAGES, switch_on, turn_status
from foms.services.cs_agent.send_record import SEND_SENDING, SEND_UNKNOWN_STATE
from foms.services.cs_agent.settings import read_settings
from foms.services.erp_actions.preview import check as action_check
from foms.services.erp_actions.registry import ACTIONS, KIND_MASKED_TEXT, STATUS_OPEN
from foms.services.erp_ontology.read import order_id_of
from models import Order

logger = logging.getLogger(__name__)

__all__ = ["EDIT_REASON_LABELS", "MAX_CHIPS", "STATUS_LABELS", "screen_view", "wam_graft", "wam_view"]

#: 작은 창 근거 칩 상한(설계서 3.9 — 셋까지).
MAX_CHIPS = 3

#: 고친 까닭(설계서 17.2 — 틀린 사실 · 약속 · 말투 · 빠짐 · 기타). 코드는 :data:`.case_memory.EDIT_REASONS` 순서.
EDIT_REASON_LABELS: dict[str, str] = dict(zip(EDIT_REASONS, ("틀린 사실", "약속", "말투", "빠짐", "기타")))
STATUS_LABELS = {"sent": "손님께 보냈어요", "discarded": "버린 초안이에요", "superseded": "지난 초안이에요(손님이 더 썼어요)",
                 "staff_replied": "직원이 먼저 답했어요", "checking": "보냈는지 확인하고 있어요"}


def _status_text(row: Any) -> Optional[str]:
    """지금 할 수 없는 까닭 글(할 수 있으면 ``None``)."""
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return STATUS_LABELS["checking"]
    if row.send_state == "sent" or row.outcome == "as_is" or row.outcome == "edited":
        return STATUS_LABELS["sent"]
    if row.outcome == "discarded":
        return STATUS_LABELS["discarded"]
    if row.outcome is not None:
        return MESSAGES["already"]
    if row.state != "posted" or not row.memo_message_id:
        return STATUS_LABELS.get(row.state, MESSAGES["not_open"])
    return None


def _detail_view(session: Any) -> Optional[dict[str, Any]]:
    """'왜 고쳤나요(자세히) · 사진' 칸 재료(설계서 17.6.1 (a)) — 칸이 꺼졌으면 ``None``(화면에 칸이 없다). DB 는 읽기만 한다."""
    on = switches(session)
    session.rollback()
    if not on.detail:
        return None
    return {"photos": on.photos, "max_detail": MAX_DETAIL, "max_photos": MAX_PHOTOS, "max_photo_bytes": PHOTO_MAX_BYTES}


def _open(session: Any, turn_id: int, chat_hint: Any) -> Optional[tuple[Any, dict[str, Any]]]:
    """차례 줄 + 화면 기본 재료(보낼 글 · 표 없음) — 차례가 없거나 상담 id 가 다르면 ``None``. DB 는 읽기만 한다."""
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    session.rollback()
    if row is None or not isinstance(chat_hint, str) or chat_hint != row.chat_id:
        return None
    status = turn_status(row)
    blocked = _status_text(row)
    if blocked is None and (row.brand != SEND_BRAND or not memo_allowed(row.chat_id)):
        blocked = MESSAGES["not_allowed"]
    if blocked is None and not switch_on(session):
        blocked = MESSAGES["switch_off"]
    session.rollback()
    return row, {
        "turn_id": row.id, "desk_url": desk_link(row.brand, row.chat_id), "status": status, "blocked": blocked,
        "draft": None, "fresh_note": None, "token": None, "checking": status["send_state"] in (SEND_SENDING,
                                                                                               SEND_UNKNOWN_STATE),
        "edit_reasons": list(EDIT_REASON_LABELS.items()), "rewrite_left": max(0, MAX_REWRITES - status["rewrite_count"]),
        "max_text": MAX_TEXT, "max_note": MAX_NOTE, "detail": None,
    }


def _with_draft(view: dict[str, Any], row: Any, reader: Any) -> dict[str, Any]:
    """그 상담 메모를 다시 읽어 '손님께 보낼 답'을 싣는다(읽기 실패면 막음 글 · 표 없음). 새 손님 글이 있으면 알림 글."""
    try:
        lines = read_lines(reader if reader is not None else OpenApiReader(), row.brand, row.chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 보내기 화면] 상담 글 읽기 실패 turn=%s status=%s", row.id, exc.status)
        view["blocked"], view["token"] = MESSAGES["read_failed"], None
        return view
    memo = next((line for line in lines if line.meta.message_id == row.memo_message_id and line.meta.is_private), None)
    view["draft"] = memo_draft(memo.text) if memo is not None else None
    stale = freshness(lines, row.last_user_message_id)
    if stale:
        view["fresh_note"] = MESSAGES["new_message"]
    return view


def screen_view(session: Any, turn_id: int, user: Any, *, chat_hint: Any, secret_key: Any, now: datetime.datetime,
                reader: Any = None) -> Optional[dict[str, Any]]:
    """화면 재료 — 차례가 없거나 링크의 상담 id 가 다르면 ``None``(404). DB 는 읽기만 한다(읽기 트랜잭션은 닫는다).

    Returns:
        ``{"turn_id", "desk_url", "status": {...}, "blocked": 까닭 글 | None, "draft": 보낼 글 | None, "fresh_note",
        "token", "edit_reasons", "rewrite_left", "max_text", "max_note", "detail"}`` — 상담 글은 보낼 초안(직원이 보낼 글)만
        싣는다. ``detail`` 은 '왜 고쳤나요(자세히) · 사진' 칸 재료(꺼졌으면 ``None``).
    """
    opened = _open(session, turn_id, chat_hint)
    if opened is None:
        return None
    row, view = opened
    if view["checking"] or view["blocked"] is None:
        view["token"] = issue_send_token(secret_key, turn_id=row.id, user_id=int(user.id), memo_id=row.memo_message_id)
    if view["blocked"] is not None:
        return view
    view["detail"] = _detail_view(session)
    return _with_draft(view, row, reader)


def wam_view(session: Any, turn_id: int, *, chat_hint: Any, reader: Any = None) -> Optional[dict[str, Any]]:
    """채널톡 작은 창 [수정하기] 재료(설계서 17.2.2) — :func:`screen_view` 와 같되 표 · 자세한 이유 칸이 없다(부른 사람은 앱
    함수 서명이 정한다). 차례가 없거나 작은 창이 받은 상담 id 가 다르면 ``None``."""
    opened = _open(session, turn_id, chat_hint)
    if opened is None:
        return None
    row, view = opened
    return view if view["blocked"] is not None else _with_draft(view, row, reader)


# ── 작은 창 접목 두 줄(읽기만) ───────────────────────────────────────────
def _foms_url(path: str) -> Optional[str]:
    """FOMS 절대 주소(env :data:`.send.BASE_URL_ENV`, https 만 — 아니면 ``None``: 칩은 글만 보인다)."""
    base = (os.environ.get(BASE_URL_ENV) or "").strip().rstrip("/")
    return base + path if base.startswith("https://") else None


def _evidence_chips(session: Any, turn_id: int) -> list[dict[str, Any]]:
    """그 차례에 남긴 근거 → 칩 ``[{"kind", "label", "href"}]`` 셋까지 — 회사 지식(모두 보기 범위만) 먼저, 주문은 한 자리를 둔다."""
    keys = refs_of(session, SOURCE_KIND, str(turn_id))
    order_ids = [order_id for key in keys if (order_id := order_id_of(key)) is not None]
    labels = brain_labels(session, [key for key in keys if order_id_of(key) is None])
    orders = [order for order in (session.get(Order, order_id) for order_id in order_ids[:1]) if order is not None]
    chips = [{"kind": "brain", "label": label, "href": _foms_url("/brain/items/" + quote(key, safe="/"))}
             for key, label in labels.items()][:MAX_CHIPS - len(orders)]
    return chips + [{"kind": "order", "label": order_label(order), "href": _foms_url(f"/erp/orders/{order.id}")}
                    for order in orders]


def _inline_text(row: Any) -> str:
    """작은 창 줄 글 — 주문 번호 + 넣을 글(가림 검사를 지난 값)."""
    spec = ACTIONS[row.action]
    value = next((str((row.params or {}).get(p.name) or "") for p in spec.params if p.kind == KIND_MASKED_TEXT), "")
    return f'주문 #{row.order_id} "{value}"' if value else f"주문 #{row.order_id}"


def _inline_action(session: Any, turn_id: int) -> Optional[dict[str, Any]]:
    """그 차례에서 상담 AI 가 만든 작은 창 줄 제안(열림 · 막는 조건 없음) 하나 ``{"id", "label", "text"}`` — 없으면 ``None``."""
    inline = [name for name, spec in ACTIONS.items() if spec.wam_inline]
    row = session.execute(select(ErpActionProposal).where(
        ErpActionProposal.source_kind == SOURCE_KIND, ErpActionProposal.source_ref == str(turn_id),
        ErpActionProposal.proposed_by == proposer(AGENT), ErpActionProposal.status == STATUS_OPEN,
        ErpActionProposal.action.in_(inline)).order_by(ErpActionProposal.id.desc()).limit(1)).scalars().first()
    order = session.get(Order, row.order_id) if row is not None and row.order_id is not None else None
    if order is None or action_check(row.action, order, row.params or {}):
        return None
    return {"id": row.id, "label": ACTIONS[row.action].label, "text": _inline_text(row)}


def wam_graft(session: Any, turn_id: int) -> dict[str, Any]:
    """작은 창 접목 두 줄 재료 — 켜진 관리 칸의 칸만 싣는다(둘 다 끔이면 빈 dict — 함수 답이 지금과 같다). DB 는 읽기만.

    Args:
        session: DB 세션(읽기 트랜잭션은 닫는다).
        turn_id: 차례 번호(부르는 쪽이 그 상담의 차례인지 이미 봤다).

    Returns:
        ``{"evidence": [칩 셋까지]}`` · ``{"action": None | {"id", "label", "text"}}`` 가운데 켜진 것.
    """
    cfg = read_settings(session, log=False)
    out: dict[str, Any] = {}
    if evidence_on(cfg):
        out["evidence"] = _evidence_chips(session, turn_id)
    if actions_on(cfg):
        out["action"] = _inline_action(session, turn_id)
    session.rollback()
    return out
