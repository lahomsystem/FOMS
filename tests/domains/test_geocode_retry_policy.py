"""지오코딩 재시도 정책 계약 (GEO-RETRY-01 / GEO-FAILKIND-01).

2026-09-01 조사에서 드러난 구조: 일시적 실패도 ``failed`` 로 굳었고, ``failed`` 는 스윕
(``include_failed=False``)·범용 ERP 지도(``not stored_geocode_status``) 어디서도 다시
시도되지 않았다. 주소가 멀쩡한 11건이 사람이 손대기 전까지 좌표 없이 남은 이유다.

이 스위트가 고정하는 것:

1. 저장단이 일시 오류를 ``failed`` 로 굳히지 않는다(``pending`` 유지 → 백오프 재시도).
2. 주소 오류만 ``address_error`` 로 굳고, **그것만** 자동 재시도에서 빠진다.
3. 스윕 SQL 술어가 파이썬 술어와 같은 답을 낸다(백필과 스윕이 갈라지지 않는다).
4. 화면은 여전히 3상태만 본다(``address_error`` → ``failed`` 정규화).

각 축마다 음성 대조군을 함께 둔다 — "전부 재시도" 나 "전부 제외" 로 퇴화한 구현은
양성 케이스만으로는 잡히지 않는다.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.geocode_helpers import (
    GEOCODE_OUTCOME_FAILED,
    GEOCODE_OUTCOME_SUCCESS,
    GEOCODE_OUTCOME_TRANSIENT,
    apply_geocode_to_order,
    compute_address_hash,
)
from foms.services.geocode_retry import (
    FAILED_RETRY_INTERVAL,
    FAILURE_PERMANENT,
    FAILURE_TRANSIENT,
    PENDING_RETRY_INTERVAL,
    STATUS_ADDRESS_ERROR,
    canonicalize_status,
    should_retry_geocode,
)

_NOW = datetime.datetime(2026, 9, 1, 12, 0, 0)
_ADDRESS = "서울 강남구 테헤란로 1"


class _Converter:
    """실패 종류까지 돌려주는 변환기 대역."""

    def __init__(self, *, lat=None, lng=None, failure_kind=None):
        self._lat = lat
        self._lng = lng
        self._kind = failure_kind
        self.calls: list[str] = []

    def convert_address_with_reason(self, address):
        self.calls.append(address)
        return self._lat, self._lng, "fake", self._kind


def _order(**over):
    base = dict(
        id=1, address=_ADDRESS, lat=None, lng=None,
        geocode_status=None, geocoded_at=None, address_hash=None,
        is_erp_order=False, structured_data=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# 1. 저장단 — 일시 오류는 굳지 않는다
# --------------------------------------------------------------------------- #
def test_transient_failure_stays_pending() -> None:
    """일시 오류 → ``pending`` 유지. 좌표·해시를 건드리지 않는다."""
    order = _order()
    conv = _Converter(failure_kind=FAILURE_TRANSIENT)

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_TRANSIENT
    assert order.geocode_status == "pending"
    assert order.geocode_status != "failed"
    assert order.geocoded_at == _NOW, "시도 시각이 없으면 백오프가 걸리지 않는다"
    assert order.address_hash is None, "판정되지 않은 주소를 처리 완료로 표시하면 안 된다"


def test_permanent_failure_marks_address_error() -> None:
    """음성 대조군: 주소 오류는 ``address_error`` 로 굳는다."""
    order = _order(lat=1.0, lng=2.0)
    conv = _Converter(failure_kind=FAILURE_PERMANENT)

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_FAILED
    assert order.geocode_status == STATUS_ADDRESS_ERROR
    assert (order.lat, order.lng) == (None, None)
    assert order.address_hash == compute_address_hash(_ADDRESS)


def test_success_is_unaffected() -> None:
    """음성 대조군: 성공 경로는 그대로다."""
    order = _order()
    conv = _Converter(lat=37.5, lng=127.0)

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_SUCCESS
    assert order.geocode_status == "success"


def test_transient_does_not_wipe_existing_coordinates() -> None:
    """네트워크가 흔들렸다고 이미 가진 좌표를 지우지 않는다."""
    order = _order(lat=37.5, lng=127.0, address_hash="stale-hash")
    conv = _Converter(failure_kind=FAILURE_TRANSIENT)

    apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert (order.lat, order.lng) == (37.5, 127.0)


# --------------------------------------------------------------------------- #
# 2. 재시도 술어 — 무엇을 다시 부르고 무엇을 안 부르는가
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status, age, expected",
    [
        (None, None, True),                                        # 미시도
        ("pending", PENDING_RETRY_INTERVAL / 2, False),            # 방금 예약
        ("pending", PENDING_RETRY_INTERVAL * 2, True),             # 고착 pending
        ("failed", FAILED_RETRY_INTERVAL / 2, False),              # 백오프 중
        ("failed", FAILED_RETRY_INTERVAL * 2, True),               # 백오프 지남
        ("failed", None, True),                                    # 시각 불명 레거시
        ("address_error", FAILED_RETRY_INTERVAL * 100, False),     # 영구 — 나이 무관
        ("address_error", None, False),
    ],
)
def test_retry_predicate_matrix(status, age, expected) -> None:
    """상태 x 나이 전 조합. 양성·음성이 한 표에 있어야 퇴화 구현이 잡힌다."""
    stamp = None if age is None else _NOW - age
    order = _order(geocode_status=status, geocoded_at=stamp)
    assert should_retry_geocode(order, now=_NOW) is expected


# --------------------------------------------------------------------------- #
# 3. SQL 술어 — 스윕이 파이썬 술어와 같은 답을 내는가
# --------------------------------------------------------------------------- #
def test_sql_candidates_match_python_predicate(app) -> None:
    """같은 모집단에 두 술어를 돌려 결과 집합이 일치하는지 본다.

    ``address_error`` 는 SQL 에서도 빠져야 한다 — 파이썬만 고치고 SQL 을 두면 스윕이
    쿼터를 계속 태운다(로직 2벌이 갈라지는 전형).
    """
    from foms.services.geocode_candidates import build_missing_geocode_query
    from models import Order

    cases = [
        ("untried", None, None),
        ("fresh_pending", "pending", _NOW - PENDING_RETRY_INTERVAL / 2),
        ("stuck_pending", "pending", None),
        ("fresh_failed", "failed", _NOW - FAILED_RETRY_INTERVAL / 2),
        ("stale_failed", "failed", _NOW - FAILED_RETRY_INTERVAL * 2),
        ("legacy_failed", "failed", None),
        ("address_error", "address_error", None),
        ("old_address_error", "address_error", _NOW - FAILED_RETRY_INTERVAL * 10),
    ]
    created = []
    for label, status, stamp in cases:
        order = Order(
            customer_name=f"재시도술어-{label}",
            phone="010-0000-0000",
            address="서울 강남구 테헤란로 1",
            product="테스트",
            options="",
            received_date=datetime.date(2026, 9, 1),
            status="RECEIVED",
            geocode_status=status,
            geocoded_at=stamp,
        )
        db_session.add(order)
        created.append(order)
    db_session.commit()

    rows = build_missing_geocode_query(
        db_session,
        pending_retry_before=_NOW - PENDING_RETRY_INTERVAL,
        failed_retry_before=_NOW - FAILED_RETRY_INTERVAL,
    ).all()
    sql_ids = {o.id for o in rows} & {o.id for o in created}
    python_ids = {o.id for o in created if should_retry_geocode(o, now=_NOW)}

    assert sql_ids == python_ids
    assert {o.id for o in created if o.geocode_status == "address_error"} & sql_ids == set()
    assert len(python_ids) == 4, "양성 4건(untried·stuck_pending·stale_failed·legacy_failed)"


def test_sql_include_failed_still_ignores_address_error(app) -> None:
    """음성 대조군: 운영자가 ``--include-failed`` 로 돌려도 address_error 는 안 잡힌다."""
    from foms.services.geocode_candidates import build_missing_geocode_query
    from models import Order

    bad = Order(
        customer_name="재시도술어-강제포함",
        phone="010-0000-0000",
        address="검암ehd 597-4 엘리시움 2동 303호",
        product="테스트",
        options="",
        received_date=datetime.date(2026, 9, 1),
        status="RECEIVED",
        geocode_status="address_error",
    )
    db_session.add(bad)
    db_session.commit()

    rows = build_missing_geocode_query(db_session, include_failed=True).all()
    assert bad.id not in {o.id for o in rows}


# --------------------------------------------------------------------------- #
# 4. 화면 — 새 상태값이 배지를 깨지 않는다
# --------------------------------------------------------------------------- #
def test_canonicalize_folds_address_error_only() -> None:
    """``address_error`` 만 ``failed`` 로 접고 나머지는 그대로 둔다."""
    assert canonicalize_status("address_error") == "failed"
    assert canonicalize_status("failed") == "failed"
    assert canonicalize_status("pending") == "pending"
    assert canonicalize_status("success") == "success"
    assert canonicalize_status(None) is None


def test_map_snapshot_shows_address_error_as_failed() -> None:
    """실측 지도 스냅샷: 주소 오류 건은 기존 '주소 오류' 배지 상태로 나온다."""
    from foms.services.map_snapshot import _canonicalize_geocode_status

    order = _order(geocode_status="address_error")
    assert _canonicalize_geocode_status(order, None, None, True) == "failed"
