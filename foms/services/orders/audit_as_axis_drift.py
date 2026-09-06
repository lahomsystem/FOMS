"""AS 축 투영(``as_axis_status``) 드리프트 집계 — 읽기 전용 정본.

AS-AXIS-01 은 AS 대시보드 술어를 파생 사본 ``orders.status`` 에서 투영 컬럼
``as_axis_status`` 로 옮겼다(2026-08-14 사고 원인 제거). 투영은
:func:`~foms.services.orders.state_axes.derive_as_axis_status` 가 정본이고
``sync_erp_flat_columns`` 호출 규약이 컬럼을 맞춘다 — 규약을 안 거치는 새 write 경로가
생기면 컬럼과 유도값이 갈린다. 이 모듈이 그 간극을 센다.

집계 정본은 :func:`audit_session` **하나뿐**이다. 두 소비자가 이쪽을 향한다:

* CLI ``tools/ops/audit_as_axis_drift.py`` — DSN 으로 엔진을 여는 껍데기
* admin 조회 :mod:`foms.api.ops_drift` — 앱 요청 세션을 그대로 넘긴다

집계가 ``tools/`` 에 살면 웹 런타임이 개발·운영 도구 트리에 묶인다(검토 보고서 R8 이
지적한 패턴). 그래서 서비스 계층에 둔다 — 의존 방향은 tools → foms 한 쪽이다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from foms.services.orders.state_axes import derive_as_axis_status
from models import Order

AS_LEGACY_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")

# 요약에 싣는 불일치 표본 상한(전체 건수는 ``mismatch`` 가 그대로 센다 — 표본만 자른다).
SAMPLE_LIMIT = 20


def _drift_candidate_query() -> Select:
    """드리프트가 가능한 주문만 고르는 후보 쿼리(전체 테이블 스캔 회피).

    Returns:
        AS 축 컬럼이 채워졌거나 AS 흔적(legacy status·접수일·완료일)이 있는 주문 select.
        AS 이력이 전혀 없고 컬럼도 NULL 인 주문은 유도값도 NULL 이라 정의상 일치한다.
    """
    return select(Order).where(
        (Order.as_axis_status.isnot(None))
        | (Order.status.in_(AS_LEGACY_STATUSES))
        | ((Order.as_received_date.isnot(None)) & (Order.as_received_date != ""))
        | ((Order.as_completed_date.isnot(None)) & (Order.as_completed_date != ""))
    )


def audit_session(session: Session) -> dict[str, Any]:
    """열린 세션으로 드리프트를 집계한다(쓰기 없음).

    Args:
        session: 읽기 전용으로만 쓰는 SQLAlchemy Session. ``scoped_session`` 프록시도
            같은 인터페이스라 그대로 받는다(앱 요청 세션 재사용).

    Returns:
        ``{'checked', 'mismatch', 'missing_projection', 'legacy_only', 'samples'}``.
        **드리프트 총건수는 ``mismatch``** 하나다 — ``missing_projection``(유도값은 있는데
        컬럼 NULL)과 ``legacy_only``(legacy status 는 AS 인데 컬럼 NULL)는 둘 다 "유도값 ≠
        컬럼값" 이므로 ``mismatch`` 의 부분집합이고, 더하면 같은 행을 두세 번 센다.
        ``samples`` 는 불일치 앞 ``SAMPLE_LIMIT`` 건의 진단용 사본이다(총계 아님).
    """
    checked = 0
    mismatch: list[dict[str, Any]] = []
    missing: list[int] = []
    legacy_only: list[int] = []
    for order in session.scalars(_drift_candidate_query()).all():
        if order.deleted_at is not None:
            continue
        checked += 1
        derived = derive_as_axis_status(order)
        if derived != order.as_axis_status:
            mismatch.append({
                "order_id": int(order.id), "column": order.as_axis_status,
                "derived": derived, "status": order.status,
            })
        if derived is not None and order.as_axis_status is None:
            missing.append(int(order.id))
        if order.status in AS_LEGACY_STATUSES and order.as_axis_status is None:
            legacy_only.append(int(order.id))
    return {
        "checked": checked,
        "mismatch": len(mismatch),
        "missing_projection": len(missing),
        "legacy_only": len(legacy_only),
        "samples": mismatch[:SAMPLE_LIMIT],
    }
