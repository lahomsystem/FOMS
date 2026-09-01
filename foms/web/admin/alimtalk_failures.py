"""관리자 화면 — 손님에게 못 간 안내(알림톡·문자) 목록 (2026-09-01 사용자 요청).

FOMS 안에 "무엇이 손님에게 안 나갔는가"를 사람이 볼 화면이 하나도 없었다. 실패는
``order_events`` 와 ``domain_side_effect_outbox`` 에 남지만 개발자가 DB·CLI 를 쳐야만
보였다. 이 화면은 **읽기 전용**이다 — 재발송 버튼은 두지 않는다(사용자 지시). 다시
보내는 일은 주문 화면의 기존 버튼이 한다.

조회축은 ``order_events`` 한 테이블이다. ``event_type``·``created_at`` 둘 다 인덱스가
있어(``models.OrderEvent``) 관리자 cold path 로 충분하다. 기간 창을 항상 건다.

**핵심 함정 — ``in_flight`` 는 실패가 아니다.** 자동 경로는 Solapi 를 부르기 *전에*
``ALIMTALK_FAILED(error='in_flight')`` 앵커를 만들고, 성공하면 그 행을 ``ALIMTALK_SENT``
로 승격한다(``kakao_alimtalk._reserve_dedupe``). 공유 발송도 같은 선점 패턴이라
``status='in_flight'`` 로 시작한다(``foms/api/share.py``). 그대로 세면 **지금 잘 나가고
있는 건이 실패로 뜬다** — 두 축 모두 진행 중을 제외한다.

두 번째 함정 — **재시도 중과 최종 실패는 다르다.** 자동 실측 안내는 워커가 10회·약 43분
재시도하는데 그 사이 이벤트는 실패 상태로 남아 있다. 재시도 중인 건을 "실패"로 보여주면
직원이 수동으로 또 눌러 손님이 두 통 받는다. outbox 상태를 함께 읽어 갈라 보여준다.
공유 발송은 요청 스레드 동기(``sync_only``)라 재시도가 없다 — 항상 최종이다.
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import render_template, request

from db import get_db
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required
from models import DomainSideEffectOutbox, Order, OrderEvent, User

# 페이지당 행 수 — 관리자 cold path 라 페이지네이션으로 충분하다(감사 화면과 같은 값).
_PER_PAGE = 50

# 기간 창 기본·상한(일). 창 없이 열면 order_events 전체를 훑는다 — 상한을 코드로 건다.
_DEFAULT_DAYS = 14
_MAX_DAYS = 90

# 실측 예약 안내 이벤트(자동·수동 공통). 실패 축은 payload.error 다.
_MEASURE_FAILED = "ALIMTALK_FAILED"
# 공유 링크 발송 이벤트. 실패 축은 payload.status == 'failed' 다(선점 시 'in_flight').
_SHARE_TYPES = ("SHARE_ALIMTALK", "SHARE_SMS")

# 발송 전 선점 표식 — 실패가 아니라 "진행 중"이다.
_IN_FLIGHT = "in_flight"

# outbox 가 아직 재시도할 수 있는 상태. 그 외(DEAD·DONE·행 없음)는 더 안 나간다.
_RETRYING_STATUSES = frozenset({"PENDING", "PROCESSING"})

# 사유 코드 → 사람 문구. 화면 3곳(erp-alimtalk-send.js·tablet-measure-form.js·erp-share.js)
# 의 맵과 미러 관계다 — 문구를 고칠 땐 네 곳을 같이 본다.
_REASON_LABELS = {
    "order_not_found": "주문을 찾을 수 없습니다",
    "not_configured": "알림톡 서버 설정이 없습니다",
    "not_eligible": "실측 일정이 확정되지 않았습니다",
    "no_valid_phone": "고객 휴대폰 번호가 올바르지 않습니다",
    "brand_profile_missing": "이 발주사의 알림톡 발신프로필이 아직 등록되지 않았습니다",
    "auth": "알림톡 인증 정보가 올바르지 않습니다",
    "balance": "알림톡 잔액이 부족합니다",
    "template_mismatch": "승인된 템플릿과 본문이 일치하지 않습니다",
    "invalid_phone": "수신 번호가 올바르지 않습니다",
    "length_exceeded": "본문이 1,000자를 넘었습니다",
    "network": "전송 중 네트워크 오류가 발생했습니다",
    "unknown": "알 수 없는 오류입니다",
}

# 안내 종류 표기. 공유는 payload.kind 가 무엇을 보냈는지 말한다.
_SHARE_KIND_LABELS = {
    "drawing": "도면 공유",
    "estimate": "계약서 공유",
    "bundle": "도면+계약서 공유",
}


def _payload(event: OrderEvent) -> dict[str, Any]:
    """이벤트 payload 를 dict 로 정규화한다(None·비 dict 방어).

    Args:
        event: 대상 이벤트.

    Returns:
        payload dict(없으면 빈 dict).
    """
    payload = event.payload
    return payload if isinstance(payload, dict) else {}


def _is_failure(event: OrderEvent) -> bool:
    """이 이벤트가 '손님에게 못 갔다'를 뜻하는가.

    진행 중 선점 표식은 제외한다 — 이걸 빼먹으면 정상 발송 건이 실패로 보인다.

    Args:
        event: 판정할 이벤트.

    Returns:
        실패로 세어야 하면 True.
    """
    payload = _payload(event)
    if event.event_type == _MEASURE_FAILED:
        error = payload.get("error")
        return bool(error) and error != _IN_FLIGHT
    if event.event_type in _SHARE_TYPES:
        return payload.get("status") == "failed"
    return False


def _kind_label(event: OrderEvent) -> str:
    """무슨 안내였는지 사람 말로.

    Args:
        event: 대상 이벤트.

    Returns:
        표시 문구.
    """
    if event.event_type == _MEASURE_FAILED:
        return "실측 예약 안내"
    kind = str(_payload(event).get("kind") or "")
    base = _SHARE_KIND_LABELS.get(kind, "공유 링크")
    return f"{base} (문자)" if event.event_type == "SHARE_SMS" else base


def _reason_label(event: OrderEvent) -> str:
    """실패 사유를 사람 말로. 모르는 코드는 코드 그대로 보여준다(숨기지 않는다).

    Args:
        event: 대상 이벤트.

    Returns:
        사유 문구.
    """
    code = str(_payload(event).get("error") or "").strip()
    if not code:
        return "사유가 기록되지 않았습니다"
    return _REASON_LABELS.get(code, code)


def _source_label(event: OrderEvent) -> str:
    """자동으로 나간 것인지 사람이 누른 것인지.

    Args:
        event: 대상 이벤트.

    Returns:
        ``'자동'`` 또는 ``'수동'``.
    """
    if event.event_type in _SHARE_TYPES:
        return "수동"
    payload = _payload(event)
    if payload.get("manual") or event.created_by_user_id:
        return "수동"
    return "자동"


def _retry_state(event: OrderEvent, outbox_by_key: dict[str, str]) -> str:
    """지금도 다시 시도하는 중인지, 더는 안 나가는지.

    공유 발송은 요청 스레드 동기라 재시도가 없다 — 언제나 최종이다.

    Args:
        event: 대상 이벤트.
        outbox_by_key: 멱등키 → outbox 상태 map.

    Returns:
        ``'다시 시도 중'`` 또는 ``'최종 실패'``.
    """
    if event.event_type in _SHARE_TYPES:
        return "최종 실패"
    key = str(_payload(event).get("dedupe_key") or "")
    status = outbox_by_key.get(key)
    return "다시 시도 중" if status in _RETRYING_STATUSES else "최종 실패"


def _outbox_status_by_key(db: Any, events: list[OrderEvent]) -> dict[str, str]:
    """실측 안내 이벤트들의 멱등키 → outbox 상태 map(N+1 금지 — 배치 1회).

    Args:
        db: 세션.
        events: 이 페이지에 그릴 이벤트들.

    Returns:
        ``{provider_idempotency_key: status}``.
    """
    keys = {
        str(_payload(e).get("dedupe_key") or "")
        for e in events
        if e.event_type == _MEASURE_FAILED
    }
    keys.discard("")
    if not keys:
        return {}
    rows = (
        db.query(
            DomainSideEffectOutbox.provider_idempotency_key,
            DomainSideEffectOutbox.status,
        )
        .filter(
            DomainSideEffectOutbox.effect_type == "ALIMTALK_SEND",
            DomainSideEffectOutbox.provider_idempotency_key.in_(sorted(keys)),
        )
        .all()  # perf-ok: 페이지당 최대 _PER_PAGE 개 키
    )
    return {key: status for key, status in rows if key}


def _orders_by_id(db: Any, events: list[OrderEvent]) -> dict[int, Order]:
    """이벤트가 가리키는 주문을 한 번에 읽는다(N+1 금지).

    Args:
        db: 세션.
        events: 이 페이지에 그릴 이벤트들.

    Returns:
        ``{order_id: Order}``.
    """
    order_ids = {int(e.order_id) for e in events if e.order_id}
    if not order_ids:
        return {}
    rows = db.query(Order).filter(Order.id.in_(sorted(order_ids))).all()  # perf-ok
    return {int(row.id): row for row in rows}


def _customer_phone(order: Order | None) -> str:
    """받는 번호. 가리지 않는다(관리자 전용 화면 — 사용자 지시).

    Args:
        order: 대상 주문(없을 수 있다 — 감사 원장은 주문보다 오래 산다).

    Returns:
        전화번호 문자열(없으면 ``'-'``).
    """
    if order is None:
        return "-"
    structured = order.structured_data if isinstance(order.structured_data, dict) else {}
    parties = structured.get("parties") if isinstance(structured.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    return str(customer.get("phone") or order.phone or "-").strip() or "-"


def _row(
    event: OrderEvent,
    orders: dict[int, Order],
    outbox_by_key: dict[str, str],
    user_map: dict[int, User],
) -> dict[str, Any]:
    """화면이 그대로 그릴 한 줄.

    Args:
        event: 대상 이벤트.
        orders: 배치 조회한 주문 map.
        outbox_by_key: 멱등키 → outbox 상태 map.
        user_map: 행위자 id → User map.

    Returns:
        템플릿용 dict.
    """
    order = orders.get(int(event.order_id)) if event.order_id else None
    actor = user_map.get(event.created_by_user_id) if event.created_by_user_id else None
    return {
        "event_id": int(event.id),
        "when": format_datetime_kst(event.created_at, "%Y-%m-%d %H:%M") or "-",
        "kind": _kind_label(event),
        "order_id": int(event.order_id) if event.order_id else None,
        "customer_name": (order.customer_name if order is not None else None) or "(삭제된 주문)",
        "phone": _customer_phone(order),
        "reason": _reason_label(event),
        "source": _source_label(event),
        "state": _retry_state(event, outbox_by_key),
        "actor": (actor.name or actor.username) if actor is not None else "",
    }


@admin_bp.route("/admin/alimtalk-failures")
@login_required
@role_required(["ADMIN"])
def alimtalk_failures():
    """손님에게 못 간 안내 목록 (관리자 전용, 읽기 전용).

    Returns:
        ``admin/alimtalk_failures.html`` 렌더 결과.
    """
    db = get_db()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    days = request.args.get("days", _DEFAULT_DAYS, type=int) or _DEFAULT_DAYS
    days = max(1, min(days, _MAX_DAYS))
    kind = (request.args.get("kind") or "all").strip()

    since = now_utc_naive() - datetime.timedelta(days=days)
    wanted = {
        "measure": [_MEASURE_FAILED],
        "share": list(_SHARE_TYPES),
    }.get(kind, [_MEASURE_FAILED, *_SHARE_TYPES])

    # 실패 판정은 payload 안(JSONB)이라 파이썬이 한다 — 인덱스 없는 JSONB 술어를 SQL 에
    # 넣지 않는다(성능 가드). 대신 인덱스가 있는 event_type·created_at 으로 먼저 좁히고,
    # 진행 중 표식이 섞여 있으니 페이지 크기보다 넉넉히 읽어 거른 뒤 자른다.
    scan_limit = _PER_PAGE * page + _PER_PAGE * 4
    candidates = (
        db.query(OrderEvent)
        .filter(OrderEvent.event_type.in_(wanted), OrderEvent.created_at >= since)
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .limit(scan_limit)
        .all()  # perf-ok: event_type·created_at 인덱스 + 기간 창 + 상한
    )
    failures = [event for event in candidates if _is_failure(event)]
    total = len(failures)
    events = failures[(page - 1) * _PER_PAGE: page * _PER_PAGE]

    orders = _orders_by_id(db, events)
    outbox_by_key = _outbox_status_by_key(db, events)
    actor_ids = {e.created_by_user_id for e in events if e.created_by_user_id}
    user_map = (
        {int(u.id): u for u in db.query(User).filter(User.id.in_(sorted(actor_ids))).all()}
        if actor_ids else {}
    )

    return render_template(
        "admin/alimtalk_failures.html",
        rows=[_row(e, orders, outbox_by_key, user_map) for e in events],
        page=page,
        total=total,
        total_pages=max((total + _PER_PAGE - 1) // _PER_PAGE, 1),
        days=days,
        kind=kind,
        max_days=_MAX_DAYS,
        # 상한까지 읽었으면 그 뒤가 더 있을 수 있다 — 화면이 "이게 전부"라고 말하지 않게 한다.
        truncated=len(candidates) >= scan_limit,
    )
