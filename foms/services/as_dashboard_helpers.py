"""ERP AS 대시보드 탭/카운트 조건 헬퍼 (Batch 5 AS 구조-추출, 동작 보존).

AS 미완료/완료 탭 SQL 조건 + 다중 케이스 집계(_count_cases)를 분리한다.
라우트와 (향후) AS read-model이 공유한다. 원본은 `foms/web/cs/as_dashboard.py`
모듈 함수였고 verbatim 이전한다. Order 컬럼 기반 조건이라 sqlalchemy + Order만 의존.
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from sqlalchemy import or_, and_, func, case

from models import Order


def _erp_as_incomplete_filter(query):
    """AS 미완료 탭 공통 필터."""
    return query.filter(_erp_as_incomplete_condition())


def _erp_as_completed_condition():
    """AS 완료 탭 공통 조건."""
    return and_(
        Order.status == 'AS_COMPLETED',
        Order.as_completed_date.isnot(None),
        Order.as_completed_date != ''
    )


def _count_cases(query, *definitions):
    """여러 조건의 집계를 한 번에 계산한다."""
    columns = [
        func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
        for name, condition in definitions
    ]
    row = query.with_entities(*columns).one()
    return {
        name: int(getattr(row, name) or 0)
        for name, _condition in definitions
    }


def _erp_as_incomplete_condition():
    """AS 미완료 탭 공통 조건."""
    return or_(
        Order.status == 'AS',
        Order.status == 'AS_RECEIVED',
        and_(
            Order.status == 'AS_COMPLETED',
            or_(
                Order.as_completed_date.is_(None),
                Order.as_completed_date == ''
            )
        )
    )
