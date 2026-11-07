"""계산기 견적(WDCalculator) — 켜진 프리랜서의 "내 견적" 판정 (FCOMM-01 화면 묶음 · 계산기).

견적(:class:`wdcalculator_models.Estimate`)에는 만든 사람 칸이 없다. 그래서 "내 견적"은 견적이 이어진 주문
(``EstimateOrderMatch``)으로 정한다. "내 주문" 판정은 프리랜서 문지기와 같은 하나
(:func:`foms.services.auth.freelancer_orders.freelancer_can_access_order` — 연결 표)다.

* **이어진 주문이 있는 견적** — 읽기(열기 · 찾기 목록 · 주문에 잇기)는 그중 하나라도 내 주문이면 된다. 주문 화면
  견적 칸(``order-estimates``)이 이미 내 주문에 이은 견적을 모두 보여 주므로 그와 같다. 바꾸기 · 지우기는 **모두**
  내 주문이어야 한다 — 남의 주문에도 이어진 견적을 고치면 그 주문 견적까지 바뀐다.
* **어디에도 안 이은 견적** — 이 로그인(세션)에서 내가 만든 것만. 번호를 서명된 세션 쿠키에 사람 번호와 함께 둔다
  (최근 :data:`SESSION_CAP` 개). 다른 사람이 만든 안 이은 견적은 보이지 않는다. 로그아웃하면 안 이은 내 견적도
  안 보인다 — 내 주문에 이으면 계속 보인다. 감사 기록(누가 저장했나)은 근거로 쓰지 않는다: 담당에서 빠진 주문의
  견적을 한 번 고친 기록만으로 계속 열리게 된다.

없는 견적과 남의 견적은 같은 답(거짓)이다 — 존재 여부를 알리지 않는다. 계산기 DB 는 따로일 수 있어
(``WD_CALCULATOR_DATABASE_URL``) 주문 표와 SQL 로 잇지 않고 번호 묶음으로 거른다.

시험: tests/security/test_freelancer_screen_wdcalculator.py
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from flask import g, has_request_context, session

from db import get_db
from foms.services.auth.freelancer_lists import freelancer_mine_sql_filter, freelancer_order_ids
from foms.services.auth.freelancer_orders import freelancer_can_access_order
from foms.services.auth.freelancer_scope import FREELANCER_ORDER_NOT_FOUND_MSG, is_freelancer_user
from wdcalculator_models import EstimateOrderMatch

#: 남의 주문 · 없는 주문 — 문지기의 주문 404 와 같은 문구.
ORDER_NOT_FOUND_MSG = FREELANCER_ORDER_NOT_FOUND_MSG
#: 이 로그인에서 프리랜서가 만든 견적 번호 ``{"u": 사람 번호, "ids": [견적 번호, ...]}``.
SESSION_KEY = "fcomm_wdc_estimates"
#: 세션 쿠키에 두는 최근 견적 수.
SESSION_CAP = 50


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def current_freelancer() -> Any:
    """지금 요청의 로그인 사용자가 켜진 프리랜서면 그 사용자, 아니면 None(요청 밖도 None)."""
    if not has_request_context():
        return None
    user = getattr(g, "current_user", None)
    return user if is_freelancer_user(user) else None


def created_ids(user: Any) -> frozenset[int]:
    """이 로그인에서 ``user`` 가 만든 견적 번호(세션의 사람 번호가 다르면 빈 묶음)."""
    uid = _int_or_none(getattr(user, "id", None))
    data = session.get(SESSION_KEY)
    if uid is None or not isinstance(data, dict) or data.get("u") != uid:
        return frozenset()
    ids = data.get("ids")
    return frozenset(n for n in (_int_or_none(v) for v in (ids if isinstance(ids, list) else [])) if n)


def remember_created(user: Any, estimate_id: Any) -> None:
    """``user`` 가 방금 만든 견적 번호를 세션에 둔다(최근 :data:`SESSION_CAP` 개)."""
    uid = _int_or_none(getattr(user, "id", None))
    eid = _int_or_none(estimate_id)
    if uid is None or eid is None:
        return
    data = session.get(SESSION_KEY)
    ids = data.get("ids") if isinstance(data, dict) and data.get("u") == uid else None
    kept = [n for n in (ids if isinstance(ids, list) else []) if n != eid]
    session[SESSION_KEY] = {"u": uid, "ids": (kept + [eid])[-SESSION_CAP:]}


def _matched_order_ids(wd_db: Any, estimate_id: int) -> set[int]:
    rows = wd_db.query(EstimateOrderMatch.order_id).filter(  # perf-ok: one estimate's matches
        EstimateOrderMatch.estimate_id == estimate_id).all()
    return {int(row[0]) for row in rows if row[0] is not None}


def _owns(user: Any, order_ids: Iterable[int], *, every: bool) -> bool:
    db = get_db()
    checks = (freelancer_can_access_order(db, user, oid) for oid in order_ids)
    return all(checks) if every else any(checks)


def _allowed(wd_db: Any, user: Any, estimate_id: Any, *, every: bool) -> bool:
    eid = _int_or_none(estimate_id)
    if user is None or eid is None:
        return False
    matched = _matched_order_ids(wd_db, eid)
    if matched:
        return _owns(user, sorted(matched), every=every)
    return eid in created_ids(user)


def can_read_estimate(wd_db: Any, user: Any, estimate_id: Any) -> bool:
    """열기 · 주문에 잇기 — 이은 주문 중 하나라도 내 주문, 안 이었으면 이 로그인에서 내가 만든 것."""
    return _allowed(wd_db, user, estimate_id, every=False)


def can_write_estimate(wd_db: Any, user: Any, estimate_id: Any) -> bool:
    """고치기 · 지우기 — 이은 주문이 모두 내 주문, 안 이었으면 이 로그인에서 내가 만든 것."""
    return _allowed(wd_db, user, estimate_id, every=True)


def readable_estimate_ids(wd_db: Any, user: Any) -> frozenset[int]:
    """찾기 목록에 보일 견적 번호 — 내 주문에 이은 견적 + 이 로그인에서 만든 안 이은 견적(쿼리 최대 2번)."""
    own_orders = sorted(freelancer_order_ids(user))
    readable: set[int] = set()
    if own_orders:
        rows = wd_db.query(EstimateOrderMatch.estimate_id).filter(  # perf-ok: matches of my linked orders
            EstimateOrderMatch.order_id.in_(own_orders)).all()
        readable.update(int(row[0]) for row in rows if row[0] is not None)
    mine = sorted(created_ids(user))
    if mine:
        rows = wd_db.query(EstimateOrderMatch.estimate_id).filter(  # perf-ok: at most SESSION_CAP ids
            EstimateOrderMatch.estimate_id.in_(mine)).all()
        matched_elsewhere = {int(row[0]) for row in rows if row[0] is not None}
        readable.update(set(mine) - matched_elsewhere)
    return frozenset(readable)


def can_use_order(user: Any, order_id: Any) -> bool:
    """잇기 · 풀기 · 저장에 실린 주문 번호가 내 주문인가(없는 주문도 거짓)."""
    return freelancer_can_access_order(get_db(), user, order_id)


def own_order_filters(user: Any) -> list[Any]:
    """주문 찾기 SQL 에 더할 "내 주문만" 조건(목록 강제 거르기와 같은 연결 표 조건)."""
    return freelancer_mine_sql_filter(user)


__all__ = [
    "ORDER_NOT_FOUND_MSG",
    "SESSION_CAP",
    "SESSION_KEY",
    "can_read_estimate",
    "can_use_order",
    "can_write_estimate",
    "created_ids",
    "current_freelancer",
    "own_order_filters",
    "readable_estimate_ids",
    "remember_created",
]
