"""휴지통 미러 — canonical soft-delete 와 legacy ``status='DELETED'`` 를 한 tx 에 묶는다.

ADMIN-OVERRIDE-01 C3. 삭제 목표를 가진 경로가 여럿(일반 화면 대량 삭제, 강제 단계 변경의
``DELETED`` 목표)이라 삭제 1건분 동작을 이 한 곳에 모은다.

**왜 canonical ``deleted_at`` 만으로는 부족한가**: 휴지통 목록은 아직
``status == 'DELETED'`` 술어에 의존한다(``foms/web/orders/trash.py:311-314``).
:func:`~foms.services.orders.soft_delete.soft_delete_order` 는 ``deleted_at`` 만 세팅하고
``order.status`` 를 보존하므로, 그것만 부르면 주문이 삭제되고도 휴지통 목록에 보이지 않아
사용자가 복구할 길을 잃는다. 그래서 전이기 dual-write 로 ``original_status`` 보존 +
``status='DELETED'`` 미러를 함께 한다. 완전 canonical 화(휴지통 술어를 ``deleted_at`` 으로,
restore 를 :func:`~foms.services.orders.soft_delete.restore_order` 로)는 DELETE-TRASH-01 소관.

커밋은 호출부가 소유한다. 대시보드 캐시 무효화(:func:`invalidate_trash_caches`)는
**커밋 뒤에만** 부른다 — 커밋 전에 부르면 롤백된 삭제가 캐시만 날린다.

**계층 규율**: 이 모듈은 services 층이라 ``foms.web`` 을 import 하지 않는다(계층 래칫
``tests/contracts/runtime/test_layer_dependency_ratchet.py``). 접근 로그(``log_access``)는
web/api 층 소유이므로 호출부가 ``audit_sink`` 로 주입한다.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import current_app

from foms.services.audit_message_display import describe_field_change
# 심볼이 아니라 모듈을 import 한다: 호출 시점 attribute 조회여야 계약 테스트의
# ``patch("foms.services.common.dashboard_cache....")`` 가 이 경로에도 걸린다
# (tests/domains/test_delete_bulk.py::test_bulk_delete_invalidates_dashboard_caches).
from foms.services.common import dashboard_cache
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.soft_delete import soft_delete_order
from models import Order


def soft_delete_with_trash_mirror(
    db: Any,
    *,
    order_id: int,
    actor_user_id: Any,
    reason: Optional[str] = None,
    expected_version: Optional[int] = None,
    bulk: bool = False,
    audit_sink: Optional[Callable[..., Any]] = None,
) -> bool:
    """주문 1건을 soft-delete 하고 휴지통 미러(status/original_status)와 감사행을 남긴다.

    커밋하지 않는다. ``RevisionError`` 는 그대로 올려 보내 호출부가 전체 롤백을 결정한다.

    Args:
        db: 활성 DB 세션(commit 은 호출부 소유).
        order_id: 삭제 대상 order id.
        actor_user_id: 삭제 actor user id(event/receipt 소유자).
        reason: 삭제 사유(선택 — 강제 단계 변경의 관리자 사유가 여기로 들어온다).
        expected_version: If-Match ``mutation_version``(선택, 불일치면 ``RevisionError``).
        bulk: 감사 detail 의 일괄 플래그.
        audit_sink: 접근 로그 기록기(api/web 층의 ``foms.web.auth.log_access``). services
            층은 ``foms.web`` 을 import 할 수 없으므로 호출부가 주입한다. ``None`` 이면
            접근 로그를 남기지 않는다 — canonical ``ORDER_SOFT_DELETED`` OrderEvent 는
            :func:`~foms.services.orders.soft_delete.soft_delete_order` 가 이미 남긴다.

    Returns:
        이번 호출로 실제 삭제됐으면 True, 이미 삭제된 주문이면 False(멱등 no-op).
    """
    result = soft_delete_order(
        db,
        order_id=order_id,
        actor_user_id=actor_user_id,
        reason=reason,
        expected_version=expected_version,
    )
    deleted_now = result is not None  # None = 이미 삭제됨(멱등 no-op)

    # 전이기 dual-write: canonical deleted_at 과 함께 legacy status/original_status 를 같은
    # tx 에 미러(휴지통 호환). status 를 덮기 전 원상태를 original_status 로 보존한다.
    order = db.get(Order, order_id)
    if order is not None and getattr(order, "status", None) != "DELETED":
        order.original_status = order.status or "RECEIVED"
        order.status = "DELETED"
    # original_status 에 방금 보존한 값이 곧 '이전 상태'다(덮어쓰기 전 값).
    trash_context = order_audit_context(order)
    previous_status = getattr(order, "original_status", None)
    if audit_sink is not None:
        audit_sink(
            describe_field_change(
                order_id=order_id, field="status", before=previous_status,
                after="DELETED", has_before=True, **trash_context,
            ),
            actor_user_id,
            auto_commit=False,
            action="ORDER_SOFT_DELETED", target_type="order", target_id=order_id,
            detail={"field": "status", "before": previous_status, "after": "DELETED",
                    "bulk": bulk, **trash_context},
        )
    return deleted_now


def invalidate_trash_caches(source: str) -> None:
    """삭제 커밋 뒤 대시보드 read-slice 캐시를 무효화한다(예외는 warning 으로 삼킨다).

    무효화가 없으면 삭제한 주문이 실측 날짜별 집계 등에 최대 5분(TTL 300초) 잔존한다
    (2026-08-10 운영 사고). **커밋 뒤에만** 부른다.

    Args:
        source: 무효화 사유 문자열(호출 경로 이름).
    """
    try:
        dashboard_cache.invalidate_dashboard_caches_after_delete_transition(source)
    except Exception:
        current_app.logger.warning(
            "post delete dashboard cache invalidate failed", exc_info=True
        )


__all__ = ["invalidate_trash_caches", "soft_delete_with_trash_mirror"]
