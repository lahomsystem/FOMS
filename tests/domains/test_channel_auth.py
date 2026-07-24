"""CHANNEL-AUTH-01: Channel quick action 권한·PII 봉쇄 계약 테스트 (red→green).

P1-8: ``process_foms_command`` 이 manager id 누락 시 fail-open 하고, active mapping 만
확인한 뒤 canonical Order read scope 없이 customer/phone/address/schedule/assignee PII 를
반환하던 결함을 봉쇄한다.

검증 대상(§3.2 P1-8 / §5.2 CHANNEL-AUTH-01):

* manager id 누락/unmapped/inactive mapping/inactive user/DB fault → 모두 **deny**.
  단일 no-data domain result, PII 0, 존재 여부 미노출(order id 미노출).
* resolve 된 active User 도 Order read scope 가 없으면 deny (PII 0). read scope 는 PII
  조회 **전에** 적용된다.
* read scope 가 있으면 정상 detail(요약/일정/담당) 을 반환하되 Order row/receipt 변화 0
  (read-only).
* fail-open 제거: manager id 누락은 allow 가 아니다(= no-data, PII 아님).
* 모든 deny variant 는 **서로 구분 불가**(동일 no-data result).
"""

from __future__ import annotations

import itertools
import json

import pytest

from db import db_session
from models import ChannelManagerLink, Order, User
from foms.services.channel_quick_actions import process_foms_command

ORDER_CMD = "주문"      # 주문
SCHEDULE_CMD = "일정"   # 일정
MANAGER_CMD = "담당"    # 담당

# PII 감시 sentinel — deny/no-data 결과에 아래 값이 하나라도 새면 실패.
_CUSTOMER = "PII_CUSTOMER_SENTINEL"
_PHONE = "010-7777-7777"
_ADDRESS = "SENTINEL_ADDRESS_RD_9"
_MANAGER = "SENTINEL_MANAGER_NAME"
_PRODUCT = "SENTINEL_PRODUCT_X"
_PII_VALUES = (_CUSTOMER, _PHONE, _ADDRESS, _MANAGER, _PRODUCT)

_counter = itertools.count(1)


def _make_user(*, is_active: bool = True, role: str = "STAFF") -> User:
    n = next(_counter)
    user = User(
        username=f"chan-mgr-user-{n}",
        password="x",
        role=role,
        name=f"user-{n}",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _link(manager_id: str, user: User, *, is_active: bool = True) -> ChannelManagerLink:
    link = ChannelManagerLink(
        channel_manager_id=manager_id,
        user_id=user.id,
        is_active=is_active,
    )
    db_session.add(link)
    db_session.commit()
    return link


def _make_order() -> Order:
    order = Order(
        received_date="2026-03-26",
        customer_name=_CUSTOMER,
        phone=_PHONE,
        address=_ADDRESS,
        product=_PRODUCT,
        status="RECEIVED",
        manager_name=_MANAGER,
        structured_data={
            "schedule": {
                "measurement": {"date": "2026-03-28"},
                "construction": {"date": "2026-04-01"},
            },
            "shipment": {
                "drawing_managers": [_MANAGER],
                "construction_workers": [_MANAGER],
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _dump(result) -> str:
    return json.dumps(result, ensure_ascii=False)


def _assert_no_pii(result, order_id: int | None = None) -> None:
    blob = _dump(result)
    for value in _PII_VALUES:
        assert value not in blob, f"PII leak: {value!r} in {blob!r}"
    if order_id is not None:
        # 존재 여부 미노출: order id 가 결과에 나타나면 존재/부재를 구분시킨다.
        assert str(order_id) not in blob, f"order id leak: {order_id} in {blob!r}"


# --------------------------------------------------------------------------
# fail-open 제거 + deny 계열이 모두 동일 no-data 결과
# --------------------------------------------------------------------------
def test_missing_manager_id_is_denied_not_fail_open(app):
    """manager id 누락 + 유효 주문 명령 → PII 아님(no-data). fail-open 제거."""
    with app.app_context():
        order = _make_order()
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id=None)
        _assert_no_pii(res, order.id)


def test_unmapped_manager_id_denies(app):
    with app.app_context():
        order = _make_order()
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="no-such-manager")
        _assert_no_pii(res, order.id)


def test_inactive_mapping_denies(app):
    with app.app_context():
        order = _make_order()
        user = _make_user()
        _link("mgr-inactive-map", user, is_active=False)
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-inactive-map")
        _assert_no_pii(res, order.id)


def test_inactive_user_denies(app):
    """active mapping 이지만 User 가 비활성 → deny (active User resolve)."""
    with app.app_context():
        order = _make_order()
        user = _make_user(is_active=False)
        _link("mgr-inactive-user", user, is_active=True)
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-inactive-user")
        _assert_no_pii(res, order.id)


def test_db_fault_on_resolve_denies(app, monkeypatch):
    """resolve 단계 DB fault → deny, raw exception 미노출."""
    class _RaisingSession:
        def query(self, *a, **k):
            raise RuntimeError("boom-resolve")

        def close(self):
            pass

    with app.app_context():
        order = _make_order()
        monkeypatch.setattr(
            "foms.services.channel_identity.db_session", lambda: _RaisingSession()
        )
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-any")
        _assert_no_pii(res, order.id)
        assert "boom-resolve" not in _dump(res)


def test_db_fault_on_order_load_denies(app, monkeypatch):
    """read 단계 DB fault → deny, raw exception 미노출."""
    with app.app_context():
        order = _make_order()
        user = _make_user()
        _link("mgr-dbfault", user)

        def _boom():
            raise RuntimeError("boom-load")

        monkeypatch.setattr("foms.services.channel_quick_actions.get_db", _boom)
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-dbfault")
        _assert_no_pii(res, order.id)
        assert "boom-load" not in _dump(res)


def test_resolved_user_without_read_scope_denies(app, monkeypatch):
    """resolve 된 active User 라도 read scope 없으면 deny·PII 0 (scope 는 PII 前 적용)."""
    with app.app_context():
        order = _make_order()
        user = _make_user()
        _link("mgr-noscope", user)
        monkeypatch.setattr(
            "foms.services.channel_quick_actions.user_can_read_order",
            lambda u, o=None: False,
        )
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-noscope")
        _assert_no_pii(res, order.id)


def test_nonexistent_order_indistinguishable_from_deny(app):
    """존재하지 않는 주문 == deny 와 동일 no-data 결과(존재 여부 미노출)."""
    with app.app_context():
        user = _make_user()
        _link("mgr-exists", user)
        nonexistent = process_foms_command(f"{ORDER_CMD} 99999", manager_id="mgr-exists")
        unmapped = process_foms_command(f"{ORDER_CMD} 99999", manager_id="no-such")
        _assert_no_pii(nonexistent)
        assert nonexistent == unmapped  # indistinguishable


def test_all_deny_variants_are_identical(app):
    """missing/unmapped/inactive-map/inactive-user 모든 deny 는 동일 결과."""
    with app.app_context():
        order = _make_order()

        inactive_user = _make_user(is_active=False)
        _link("mgr-iu", inactive_user, is_active=True)
        active_user = _make_user()
        _link("mgr-imap", active_user, is_active=False)

        cmd = f"{ORDER_CMD} {order.id}"
        results = [
            process_foms_command(cmd, manager_id=None),
            process_foms_command(cmd, manager_id="unmapped-xyz"),
            process_foms_command(cmd, manager_id="mgr-iu"),
            process_foms_command(cmd, manager_id="mgr-imap"),
        ]
        for r in results:
            _assert_no_pii(r, order.id)
        assert all(r == results[0] for r in results)


# --------------------------------------------------------------------------
# 정상 read scope → detail 반환 + read-only
# --------------------------------------------------------------------------
def test_resolved_user_with_read_scope_returns_detail(app):
    """active User + read scope → 요약 detail(PII) 반환."""
    with app.app_context():
        order = _make_order()
        user = _make_user()
        _link("mgr-ok", user)
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id="mgr-ok")
        blob = _dump(res)
        assert _CUSTOMER in blob
        assert _PRODUCT in blob


def test_read_is_read_only_no_mutation(app):
    """detail 조회는 Order row/개수를 바꾸지 않는다(read-only, receipt 0)."""
    with app.app_context():
        order = _make_order()
        oid = order.id
        user = _make_user()
        _link("mgr-ro", user)

        before_count = db_session.query(Order).count()
        before_name = order.customer_name
        before_status = order.status

        for cmd in (ORDER_CMD, SCHEDULE_CMD, MANAGER_CMD):
            process_foms_command(f"{cmd} {oid}", manager_id="mgr-ro")

        db_session.expire_all()
        after = db_session.get(Order, oid)
        assert db_session.query(Order).count() == before_count
        assert after.customer_name == before_name
        assert after.status == before_status


def test_schedule_and_manager_commands_are_also_gated(app):
    """일정/담당 명령도 manager 누락 시 no-data·PII 0 (전 command 게이트)."""
    with app.app_context():
        order = _make_order()
        for cmd in (SCHEDULE_CMD, MANAGER_CMD):
            res = process_foms_command(f"{cmd} {order.id}", manager_id=None)
            _assert_no_pii(res, order.id)
