"""좌표 없는 주문(지오코딩 후보) 선별 술어 SSOT.

지오코딩 후보를 고르는 곳이 두 군데 있다.

* ``tools/ops/backfill_geocode_missing.py`` — 운영자가 손으로 도는 일회성 백필 CLI.
* ``scripts/maintenance/run_geocode_sweep.py`` — worker 컨테이너에서 도는 주기 스윕 루프.

둘이 술어를 각자 들고 있으면 "백필은 잡는데 스윕은 안 잡는" 계열이 조용히 생긴다.
그래서 조건식을 이 모듈 한 곳에만 둔다(로직 2벌 금지).

공통 술어
    활성 주문(soft-delete·ERP draft 제외) + ``lat``/``lng`` 중 하나라도 NULL +
    ``address`` 가 NULL/``''``/``'-'`` 가 아님.

상태(``geocode_status``)별 판정은 호출자가 고른다 — :func:`build_missing_geocode_query`
의 ``include_failed`` / ``pending_retry_before`` / ``failed_retry_before`` 참조.
백오프 간격의 정본은 :mod:`foms.services.geocode_retry` 다(파이썬 술어와 같은 값).

``geocode_status='address_error'`` 는 **어떤 옵션으로도 대상이 되지 않는다** — 카카오가
"그런 주소 없음"이라고 답한 건이라 다시 불러도 같은 답이 온다. 사람이 주소를 고치면
write 경로가 ``pending`` 으로 되돌려 자동으로 후보에 복귀한다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

__all__ = ["build_missing_geocode_query"]


def build_missing_geocode_query(
    session: Any,
    *,
    include_failed: bool = False,
    pending_retry_before: Optional[datetime.datetime] = None,
    failed_retry_before: Optional[datetime.datetime] = None,
):
    """좌표 없는 주문 쿼리를 만든다(정렬·limit 은 호출자 몫).

    Args:
        session: SQLAlchemy 세션.
        include_failed: True 면 ``geocode_status='failed'`` 건을 **나이 제한 없이** 전부
            대상에 넣는다(운영자가 손으로 도는 백필 CLI ``--include-failed``).
            일상 재시도는 이 스위치가 아니라 ``failed_retry_before`` 로 한다.
        failed_retry_before: None 이 아니면 ``geocode_status='failed'`` 건 중 마지막 시도가
            이 시각보다 오래된 것(시각 NULL 포함)을 대상에 넣는다.

            ``failed`` 를 통째로 빼두던 시절의 결함(2026-09-01): 일시적 네트워크 사고로
            ``failed`` 가 된 주문 11건이 주소는 멀쩡한데도 사람이 손대기 전까지 영원히
            제외됐다. 사유가 분명한 주소 오류는 이제 ``address_error`` 로 따로 표시되므로,
            남은 ``failed`` 는 사유 불명이고 하루 1회 다시 시도할 값어치가 있다.
        pending_retry_before: None 이 아니면 ``geocode_status='pending'`` 건 중
            **마지막 시도 시각이 이 시각보다 오래된 것**(또는 시각이 NULL 인 것)을
            대상에 넣는다. None 이면 ``pending`` 은 통째로 제외한다.

            ``pending`` 을 나이로 자르는 이유:
            ``foms/services/order_geocode.py`` 의
            ``reset_order_geocode_on_address_change`` 는 주소 수정 시 ``pending`` 만
            찍고 ``geocoded_at`` 은 건드리지 않는다. 예약이 실패하면(SIDEFX 워커 부재)
            재큐 술어가 ``pending`` 을 건너뛰므로 영구 고착된다. 그래서 오래된
            ``pending`` 은 다시 집어야 하고, 시각이 NULL(=시각 불명)이면 "오래된 것"으로
            간주해 반드시 포함해야 고착 건이 풀린다. 반대로 방금 예약한 건까지 다시
            집으면 큐가 중복 잡으로 부푸니, 최근 것은 제외한다.

    Returns:
        :class:`~models.Order` 를 돌려주는 SQLAlchemy Query.
    """
    from sqlalchemy import and_, or_

    from models import Order

    # ``geocode_status`` 별 대상 조건. NULL(=한 번도 시도 안 함)은 항상 대상.
    status_terms = [Order.geocode_status.is_(None)]
    if pending_retry_before is not None:
        status_terms.append(
            and_(
                Order.geocode_status == 'pending',
                or_(
                    Order.geocoded_at.is_(None),
                    Order.geocoded_at < pending_retry_before,
                ),
            )
        )
    if include_failed:
        status_terms.append(Order.geocode_status == 'failed')
    elif failed_retry_before is not None:
        status_terms.append(
            and_(
                Order.geocode_status == 'failed',
                or_(
                    Order.geocoded_at.is_(None),
                    Order.geocoded_at < failed_retry_before,
                ),
            )
        )

    return session.query(Order).filter(
        Order.active_filter(),
        or_(Order.lat.is_(None), Order.lng.is_(None)),
        Order.address.isnot(None),
        Order.address != '',
        Order.address != '-',
        or_(*status_terms),
    )
