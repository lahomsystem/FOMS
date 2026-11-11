"""주문 금액 변경 이벤트(``PAYMENT_CHANGED``)의 before_flush SSOT.

왜 라우트별 emit 이 아니라 flush 훅인가: 금액(예약금·할인·자유입력·현금영수증·잔금 메모·
확인 토글)을 건드리는 쓰기 경로는 전체저장 PUT · 결제확인 토글 · 자동저장 · 스크립트/워커까지
흩어져 있고, 경로마다 emit 을 심으면 경로가 늘어날 때마다 무음 구멍이 다시 생긴다
(``order_date_sync`` 가 시공일에서 이미 겪은 실패). 모든 쓰기가 통과하는 유일 지점인
``Session.before_flush`` 한 곳에서만 기록한다.

**before(이전 값)는 DB 에서 읽는다.** ``flag_modified`` 는 attribute history 의 old 를
파괴하므로(SQLAlchemy 2.0.23 실증 — ``state._modified_event(is_userland=True)`` 가
committed_state 를 ``NO_VALUE`` 로 덮는다) ``get_history`` 기반 diff 는 정본 저장 패턴
(deepcopy → 재할당 → ``flag_modified``) 아래에서 항상 빈 old 를 준다. 대신 payment-dirty 주문
id 를 모아 flush **전** committed ``structured_data`` 를 배치 1회 SELECT 로 읽고, 그 값을
트랜잭션 origin 으로 ``Session.info`` 에 캐시한다(다중 flush 대비).

``order_date_sync`` 와 가드 로직(origin 기억·복귀 시 취소·재진입·rollback/commit 소거·actor
해석)이 동형이지만 **의도적으로 복제**한다 — 그 모듈은 동시 세션(출고 알림 플랜)이 소유 중이라
무접촉이 계약이다. 통합 리팩터는 해당 플랜 완료 후 별건.

캡처 제외: ``Order.shipping_fee``(이미 ``SHIPPING_FEE_CHANGED`` 로 감사됨 — 중복 금지),
``totals.*``(파생값이며 전체저장·생성 2곳에서만 재계산돼 stale).
"""

from __future__ import annotations

import logging
from typing import Any

from models import OrderEvent

logger = logging.getLogger(__name__)

__all__ = [
    "PAYMENT_CHANGED_EVENT",
    "PAYMENT_CHANGED_FIELDS",
    "register_payment_sync_listener",
]

#: 금액 변경 이벤트 타입(단일 타입 + payload ``field`` — 설계 결정 ①).
PAYMENT_CHANGED_EVENT = "PAYMENT_CHANGED"

#: diff 대상 payload ``field`` 값(트랜잭션당 field 별 정확히 1건).
PAYMENT_CHANGED_FIELDS: tuple[str, ...] = (
    "payment.deposit",
    "payment.discount",
    "payment.free_input",
    "payment.cash_receipt",
    "payment.balance_note",
    "payment.deposit_confirmed",
    "payment.balance_confirmed",
)

#: 자유입력 원문과 함께 기록할 파싱 합계 스냅샷 키(단독 diff 대상 아님).
_FREE_INPUT_AMOUNT_KEY = "payment.free_input_amount"

#: 재진입 가드 키(``Session.info``).
_PAYMENT_EVENT_GUARD = "foms_payment_event_in_flush"
#: 트랜잭션 origin 스냅샷 캐시 키(``Session.info``).
_PAYMENT_ORIGIN_STATE = "foms_payment_origin_state"
#: 트랜잭션 단위 pending 이벤트 맵 키(``Session.info``).
_PAYMENT_EVENT_STATE = "foms_payment_event_state"

#: 리스너 중복 등록 가드(``register_payment_sync_listener`` 는 멱등).
_LISTENERS_REGISTERED = False


# --------------------------------------------------------------------------- #
# 값 추출·정규화
# --------------------------------------------------------------------------- #
def _payment_text_value(sd: dict[str, Any], key: str) -> str:
    """``payment`` → 레거시 ``payments`` 폴백으로 문자열 결제 필드를 읽는다.

    레거시 ``payments`` 블록은 값이 ``{"value"/"raw": ...}`` dict 로 들어 있을 수 있어
    클라이언트 resolver(``erpResolveCashReceipt``)와 같은 규칙으로 푼다. 미존재·``None``·
    빈 문자열은 전부 ``""`` 로 동일시한다(허위 변경 차단).

    Args:
        sd: 주문 ``structured_data`` 딕셔너리.
        key: ``cash_receipt`` · ``balance_note`` 등 payment 하위 키.

    Returns:
        정규화된 문자열(없으면 빈 문자열).
    """
    modern = sd.get("payment")
    if isinstance(modern, dict) and key in modern:
        return str(modern.get(key) or "").strip()
    legacy = sd.get("payments")
    if isinstance(legacy, dict):
        entry = legacy.get(key)
        if isinstance(entry, dict):
            return str(entry.get("value") or entry.get("raw") or "").strip()
        if entry not in (None, ""):
            return str(entry).strip()
    return ""


def _payment_bool_value(sd: dict[str, Any], key: str) -> bool:
    """확인 토글(bool)을 ``payment`` → 레거시 ``payments`` 폴백으로 읽는다.

    클라이언트 ``_erpBoolConfirmed`` 와 동일 규칙: ``True``/``1``/``"true"``/``"1"``/
    ``"yes"``/``"on"`` 만 참, 그 외(미존재·``None``·빈 문자열 포함)는 거짓.

    Args:
        sd: 주문 ``structured_data`` 딕셔너리.
        key: ``deposit_confirmed`` · ``balance_confirmed``.

    Returns:
        정규화된 bool.
    """
    raw: Any = None
    for block_key in ("payment", "payments"):
        block = sd.get(block_key)
        if isinstance(block, dict) and key in block:
            raw = block.get(key)
            break
    if raw is True or raw == 1:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes", "on")
    return False


def _payment_snapshot(sd: Any) -> dict[str, Any]:
    """감사 대상 금액 필드의 정규화 스냅샷을 만든다.

    금액 3종은 **기존 서버 extractor 를 재사용**한다 — 레거시 ``payments`` 블록·
    ``totals`` 폴백 처리가 이미 그 안에 있어서, 여기서 다시 구현하면 표시 금액과 감사 금액이
    갈린다. 숫자는 ``int`` 로 강제하고 ``None``/미존재는 ``0`` 으로 동일시한다.

    Args:
        sd: 주문 ``structured_data``(dict 가 아니면 빈 dict 로 취급).

    Returns:
        ``{field: 정규화 값}`` 스냅샷(``_FREE_INPUT_AMOUNT_KEY`` 병기 포함).
    """
    # 함수 지역 import: estimate_service·erp_display 는 서로를 지역 import 하는 구조라
    # 모듈 최상위에서 끌어오면 순환 import 가 된다(erp_display 선례와 동일).
    from foms.services.erp_display import erp_deposit_amount_from_structured
    from foms.services.estimate_service import (
        _extract_discount_amount,
        _extract_free_input_amount,
        _extract_free_input_text,
    )

    data: dict[str, Any] = sd if isinstance(sd, dict) else {}
    return {
        "payment.deposit": int(erp_deposit_amount_from_structured(data) or 0),
        "payment.discount": int(_extract_discount_amount(data) or 0),
        "payment.free_input": _extract_free_input_text(data),
        _FREE_INPUT_AMOUNT_KEY: int(_extract_free_input_amount(data) or 0),
        "payment.cash_receipt": _payment_text_value(data, "cash_receipt"),
        "payment.balance_note": _payment_text_value(data, "balance_note"),
        "payment.deposit_confirmed": _payment_bool_value(data, "deposit_confirmed"),
        "payment.balance_confirmed": _payment_bool_value(data, "balance_confirmed"),
    }


def _is_draft_structured_data(sd: Any) -> bool:
    """``meta.draft`` 가 truthy 인 draft 주문 스냅샷인지 판정한다.

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        draft 면 True.
    """
    if not isinstance(sd, dict):
        return False
    meta = sd.get("meta")
    return bool(meta.get("draft")) if isinstance(meta, dict) else False


# --------------------------------------------------------------------------- #
# actor·세션 상태 (order_date_sync 동형 — 무접촉 복제)
# --------------------------------------------------------------------------- #
def _resolve_event_actor_and_source() -> tuple[int | None, str]:
    """이벤트 기록자(actor)와 쓰기 경로 힌트를 구한다.

    요청 컨텍스트가 있으면 세션 사용자 id 와 Flask endpoint 를, 없으면(부팅 백필·스크립트·
    워커) ``(None, "system")`` 을 돌려준다. 요청 밖 flush 에서 절대 예외를 던지지 않는다.

    Returns:
        ``(actor_user_id, source)`` — actor 는 미확인 시 ``None``.
    """
    try:
        from flask import has_request_context, request
        from flask import session as flask_session

        if not has_request_context():
            return None, "system"
        raw_user_id = flask_session.get("user_id")
        actor = int(raw_user_id) if str(raw_user_id or "").strip().isdigit() else None
        source = str(request.endpoint or request.path or "request")[:80]
        return actor, source
    except (RuntimeError, ImportError, ValueError, TypeError) as exc:
        logger.debug("[PaymentSync] actor resolve skipped outside request: %s", exc)
        return None, "system"


def _origin_state(session: Any) -> dict[int, dict[str, Any]]:
    """트랜잭션 최초(origin) payment 스냅샷 캐시를 얻는다.

    한 요청이 여러 번 flush 하면 2번째 flush 부터는 DB 에 이미 중간 값이 들어 있어 "이전 값"이
    중간 상태로 오염된다. 그래서 payment-dirty 를 처음 본 시점의 committed 값만 origin 으로
    고정하고 이후 flush 는 그 origin 과 비교한다. 커밋/롤백 시 비운다.

    Args:
        session: 현재 SQLAlchemy 세션.

    Returns:
        ``{order_id: {"draft": bool, "snapshot": dict}}``.
    """
    state = session.info.get(_PAYMENT_ORIGIN_STATE)
    if not isinstance(state, dict):
        state = {}
        session.info[_PAYMENT_ORIGIN_STATE] = state
    return state


def _pending_event_state(session: Any) -> dict[tuple[int, str], Any]:
    """트랜잭션 동안 ``(주문, field)`` 별 이벤트를 1건으로 합치기 위한 상태 맵.

    Args:
        session: 현재 SQLAlchemy 세션.

    Returns:
        ``{(order_id, field): OrderEvent}``.
    """
    state = session.info.get(_PAYMENT_EVENT_STATE)
    if not isinstance(state, dict):
        state = {}
        session.info[_PAYMENT_EVENT_STATE] = state
    return state


def _discard_pending_event(session: Any, event: Any) -> None:
    """값이 트랜잭션 origin 으로 되돌아왔을 때 이미 만든 이벤트를 취소한다.

    Args:
        session: 현재 SQLAlchemy 세션.
        event: 취소할 ``OrderEvent``(flush 전이면 expunge, 이미 INSERT 됐으면 delete).

    Returns:
        None.
    """
    from sqlalchemy import inspect as sa_inspect

    if sa_inspect(event).persistent:
        session.delete(event)
    else:
        session.expunge(event)


# --------------------------------------------------------------------------- #
# flush 파이프라인
# --------------------------------------------------------------------------- #
def _payment_dirty_orders(session: Any, order_cls: Any) -> list[Any]:
    """이번 flush 에서 ``structured_data`` 가 수정된 **기존** 주문만 고른다.

    생성(``session.new``)은 "이전 값"이 없으므로 대상이 아니다. ``structured_data`` 가
    깨끗한 주문은 배치 SELECT 자체를 유발하지 않는다(hot path 추가 쿼리 0).

    Args:
        session: 현재 flush 중인 세션.
        order_cls: ``Order`` 모델 클래스.

    Returns:
        payment diff 후보 주문 목록.
    """
    from sqlalchemy import inspect as sa_inspect

    candidates: list[Any] = []
    for obj in session.dirty:
        if not isinstance(obj, order_cls) or getattr(obj, "id", None) is None:
            continue
        if obj in session.new:
            continue
        if "structured_data" in sa_inspect(obj).unmodified:
            continue
        candidates.append(obj)
    return candidates


def _load_committed_structured_data(session: Any, order_ids: list[int]) -> dict[int, Any]:
    """flush 전 committed ``structured_data`` 를 **배치 1회** SELECT 로 읽는다.

    ``session.connection()`` 의 Core 실행이라 autoflush 로 이 훅에 재진입하지 않고, 같은
    트랜잭션 커넥션을 쓰므로 커넥션 풀 추가 checkout 도 없다.

    Args:
        session: 현재 flush 중인 세션.
        order_ids: 조회 대상 주문 id 목록.

    Returns:
        ``{order_id: structured_data}``(행이 없으면 키 없음).
    """
    if not order_ids:
        return {}
    from sqlalchemy import select

    from models import Order

    table = Order.__table__
    stmt = select(table.c.id, table.c.structured_data).where(table.c.id.in_(order_ids))
    rows = session.connection().execute(stmt).fetchall()
    return {int(row[0]): row[1] for row in rows}


def _event_payload(field: str, before: Any, after: Any, source: str, extra: dict | None) -> dict:
    """``PAYMENT_CHANGED`` payload 를 만든다.

    Args:
        field: :data:`PAYMENT_CHANGED_FIELDS` 중 하나.
        before: 트랜잭션 origin 값.
        after: 현재 값.
        source: 쓰기 경로 힌트(Flask endpoint 또는 ``"system"``).
        extra: 자유입력 파싱 합계 등 병기 키(없으면 None).

    Returns:
        payload 딕셔너리.
    """
    payload: dict[str, Any] = {
        "field": field,
        "from": before,
        "to": after,
        "source": source,
    }
    if extra:
        payload.update(extra)
    return payload


def _apply_field_change(
    session: Any,
    order_id: int,
    field: str,
    before: Any,
    after: Any,
    extra: dict | None = None,
) -> None:
    """field 1개의 변경을 pending 이벤트에 반영한다(생성·갱신·취소).

    같은 트랜잭션에서 이미 이벤트를 만들었으면 새로 추가하지 않고 ``to`` 만 갱신하고,
    값이 origin 으로 되돌아오면 이벤트를 취소한다(경로당 정확히 1건 · 허위 이벤트 0).

    Args:
        session: 현재 flush 중인 세션.
        order_id: 대상 주문 id.
        field: payload ``field`` 값.
        before: 트랜잭션 origin 값.
        after: 현재 값.
        extra: payload 병기 키.

    Returns:
        None.
    """
    state = _pending_event_state(session)
    key = (order_id, field)
    pending = state.get(key)

    if before == after:
        if pending is not None:
            _discard_pending_event(session, pending)
            state.pop(key, None)
        return

    actor_id, source = _resolve_event_actor_and_source()
    payload = _event_payload(field, before, after, source, extra)
    if pending is None:
        event = OrderEvent(
            order_id=order_id,
            event_type=PAYMENT_CHANGED_EVENT,
            payload=payload,
            created_by_user_id=actor_id,
        )
        session.add(event)
        state[key] = event
        return
    pending.payload = payload


def _diff_and_emit(session: Any, order_id: int, origin: dict[str, Any], current: dict[str, Any]) -> None:
    """origin ↔ 현재 스냅샷을 field 별로 비교해 이벤트를 반영한다.

    Args:
        session: 현재 flush 중인 세션.
        order_id: 대상 주문 id.
        origin: 트랜잭션 origin 스냅샷.
        current: 현재 스냅샷.

    Returns:
        None.
    """
    for field in PAYMENT_CHANGED_FIELDS:
        extra = None
        if field == "payment.free_input":
            # 원문 문자열이 정본 diff 축이고, 파싱 합계는 사람이 읽을 수 있게 병기한다
            # ("배송비 : 30,000" 처럼 텍스트만 봐서는 금액 변화를 알기 어렵다).
            extra = {
                "from_amount": origin[_FREE_INPUT_AMOUNT_KEY],
                "to_amount": current[_FREE_INPUT_AMOUNT_KEY],
            }
        _apply_field_change(session, order_id, field, origin[field], current[field], extra)


def _run_payment_sync_flush(session: Any, order_cls: Any) -> None:
    """flush 대상 주문의 금액 diff → ``PAYMENT_CHANGED`` emit 을 수행한다.

    Args:
        session: 현재 flush 중인 세션.
        order_cls: ``Order`` 모델 클래스(모듈 최상위 import 순환 회피용 주입).

    Returns:
        None.
    """
    # 재진입 가드: 이 훅 안의 delete/expunge 가 다시 flush 를 돌려도 같은 변경을 두 번
    # 기록하지 않는다.
    if session.info.get(_PAYMENT_EVENT_GUARD):
        return
    candidates = _payment_dirty_orders(session, order_cls)
    if not candidates:
        return

    origin_state = _origin_state(session)
    missing = [order.id for order in candidates if order.id not in origin_state]
    committed = _load_committed_structured_data(session, missing)
    for order_id in missing:
        sd = committed.get(order_id)
        origin_state[order_id] = {
            "draft": _is_draft_structured_data(sd),
            "snapshot": _payment_snapshot(sd),
        }

    session.info[_PAYMENT_EVENT_GUARD] = True
    try:
        for order in candidates:
            origin = origin_state[order.id]
            current_sd = getattr(order, "structured_data", None)
            # draft 자동저장은 노이즈다 — 승격 시점 값이 사실상 초기값이므로 억제한다.
            if origin["draft"] or _is_draft_structured_data(current_sd):
                continue
            _diff_and_emit(session, order.id, origin["snapshot"], _payment_snapshot(current_sd))
    finally:
        session.info[_PAYMENT_EVENT_GUARD] = False


def register_payment_sync_listener() -> None:
    """전역 ``Session`` 에 금액 변경 이벤트 리스너를 **1회** 등록한다.

    ``PAYMENT_CHANGED`` 의 유일한 emit 지점이다. 라우트/서비스별 emit 은 두지 않는다 —
    결제확인 토글 라우트가 편집 0줄로도 포착되는 것이 이 설계가 맞다는 신호다.

    Returns:
        None.
    """
    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return
    _LISTENERS_REGISTERED = True

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from models import Order

    @event.listens_for(Session, "before_flush")
    def _payment_before_flush(session, flush_context, instances):
        _run_payment_sync_flush(session, Order)

    @event.listens_for(Session, "after_soft_rollback")
    def _payment_after_soft_rollback(session, previous_transaction):
        # 롤백된 트랜잭션의 origin·이벤트 참조는 무효다 — 다음 트랜잭션으로 새어가면 안 된다.
        session.info.pop(_PAYMENT_ORIGIN_STATE, None)
        session.info.pop(_PAYMENT_EVENT_STATE, None)

    @event.listens_for(Session, "after_commit")
    def _payment_after_commit(session):
        session.info.pop(_PAYMENT_ORIGIN_STATE, None)
        session.info.pop(_PAYMENT_EVENT_STATE, None)
