"""NAVER-INGEST-01 잔여: 수집 주문 표시 계약 — 대시보드 '담당 미지정' + 상세 '네이버 수집'.

고정하는 계약:

* 보류함(``naver_unassigned``)이 아직 owner 인 **수집 주문만** '담당 미지정' 대상이다.
* 실제 영업사원이 owner 면 대상이 아니다(배정하면 뱃지가 사라진다).
* 수집 주문이 아닌 일반 주문은 owner 가 누구든 대상이 아니다.
* 수집 주문이 페이지에 없으면 **쿼리를 아예 내지 않는다**(대시보드 hot path 비용 0).
* DTO 는 그 집합을 ``is_unassigned_intake`` 로 실어 템플릿에 넘긴다.
* 주문 상세(PC·모바일 탭)는 ``structured_data['source']`` 로 '네이버 수집' 표식을 띄우고,
  템플릿 리터럴은 ``SOURCE_MARKER`` 와 같아야 한다(어긋나면 조용히 안 뜬다).
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.constants import (
    OWNER_USERNAME,
    SOURCE_MARKER,
)
from foms.services.orders.dashboard_read_model import compute_unassigned_intake_order_ids
from models import Order, OrderAssignment, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"badge-{_SEQ[0]}"


def _user(username: str, name: str) -> User:
    user = User(username=username, password="pw-not-committed", name=name,
                role="STAFF", team="SALES", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(sd: dict, *, owner: User | None) -> Order:
    """표시용 주문 1건 + (있으면) active SALES 배정 1행.

    배정 교체는 SQLite 레인에서 partial unique 가 전체 unique 로 굳어 실패한다
    (원장 T10 레인 함정) — 그래서 각 주문은 처음부터 최종 owner 로 만든다.
    """
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-13",
                  status="RECEIVED", is_erp_order=True, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    if owner is not None:
        db_session.add(OrderAssignment(order_id=order.id, domain="SALES", user_id=owner.id,
                                       source="INITIAL_OWNER", active=True,
                                       assigned_by_user_id=owner.id))
        db_session.commit()
    return order


def _naver_sd() -> dict:
    return {"source": SOURCE_MARKER, "parties": {"customer": {"name": "테스트고객"}}}


def test_intake_order_still_owned_by_holding_account_is_flagged(app):
    """보류함이 owner 인 수집 주문은 뱃지 대상이다."""
    holding = _user(OWNER_USERNAME, "미배정")
    order = _order(_naver_sd(), owner=holding)

    ids = compute_unassigned_intake_order_ids(db_session, [order], {order.id: _naver_sd()})

    assert ids == {order.id}


def test_intake_order_assigned_to_real_person_is_not_flagged(app):
    """실제 담당자가 owner 면 뱃지가 사라진다."""
    _user(OWNER_USERNAME, "미배정")
    sales = _user(_uid(), "박영업")
    order = _order(_naver_sd(), owner=sales)

    ids = compute_unassigned_intake_order_ids(db_session, [order], {order.id: _naver_sd()})

    assert ids == set()


def test_plain_order_is_never_flagged_even_if_holding_account_owns_it(app):
    """수집 주문이 아니면 대상이 아니다 — 뱃지는 채널 수집분 전용 표시다."""
    holding = _user(OWNER_USERNAME, "미배정")
    order = _order({"parties": {"customer": {"name": "테스트고객"}}}, owner=holding)

    ids = compute_unassigned_intake_order_ids(db_session, [order], {order.id: {}})

    assert ids == set()


def test_missing_holding_account_is_not_an_error(app):
    """T0 계정이 아직 없는 환경(운영 미반영)에서도 대시보드가 죽지 않는다."""
    order = _order(_naver_sd(), owner=None)

    assert compute_unassigned_intake_order_ids(db_session, [order], {order.id: _naver_sd()}) == set()


def test_page_without_intake_orders_issues_no_query(app):
    """수집 주문 0건이면 쿼리조차 내지 않는다(대시보드 hot path)."""
    class _ExplodingSession:
        def query(self, *args, **kwargs):  # pragma: no cover - 호출되면 실패다
            raise AssertionError("수집 주문이 없으면 쿼리를 내면 안 된다")

    order = _order({"parties": {}}, owner=None)

    assert compute_unassigned_intake_order_ids(_ExplodingSession(), [order], {order.id: {}}) == set()


def test_dto_carries_the_flag_to_the_template(app):
    """DTO 가 집합을 행 플래그로 옮긴다(템플릿이 읽는 자리)."""
    from foms.services.orders.dashboard_dto import build_orders_row_dtos

    holding = _user(OWNER_USERNAME, "미배정")
    flagged = _order(_naver_sd(), owner=holding)
    plain = _order({"parties": {}}, owner=None)
    page_sds = {flagged.id: _naver_sd(), plain.id: {}}

    rows = build_orders_row_dtos([flagged, plain], page_sds, {}, {}, None,
                                 unassigned_intake_ids={flagged.id})

    by_id = {r["id"]: r for r in rows}
    assert by_id[flagged.id]["is_unassigned_intake"] is True
    assert by_id[plain.id]["is_unassigned_intake"] is False


def test_dashboard_html_shows_the_badge_instead_of_the_holding_account_name(client):
    """실제 대시보드 응답 HTML 에 뱃지가 나온다(템플릿 배선까지 고정).

    DTO 플래그만 검사하면 템플릿에서 안 읽어도 green 이라, 라우트를 실제로 렌더한다.
    """
    from werkzeug.security import generate_password_hash

    admin = User(username="badge_admin", password=generate_password_hash("admin"),
                 role="ADMIN", team="CS", name="뱃지 관리자", is_active=True)
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["username"] = admin.username
        sess["role"] = admin.role

    holding = _user(OWNER_USERNAME, "미배정")
    _order(_naver_sd(), owner=holding)

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert "담당 미지정" in html
    # 보류함 계정 이름이 담당자처럼 보이면 안 된다.
    assert "미배정</strong>" not in html


def _login_admin(client, username: str):
    from werkzeug.security import generate_password_hash

    admin = User(username=username, password=generate_password_hash("admin"),
                 role="ADMIN", team="CS", name="뱃지 관리자", is_active=True)
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["username"] = admin.username
        sess["role"] = admin.role
    return admin


def test_order_detail_shows_naver_intake_badge(client):
    """수집 주문 상세에는 '네이버 수집' 표식이 뜬다."""
    _login_admin(client, "detail_badge_admin")
    order = _order(_naver_sd(), owner=None)

    html = client.get(f"/edit/{order.id}").get_data(as_text=True)

    assert 'data-erp-order-source="NAVER_SMARTSTORE"' in html
    assert "네이버 수집" in html


def test_plain_order_detail_has_no_intake_badge(client):
    """손으로 받은 주문에는 표식이 없다(오표시 방지)."""
    _login_admin(client, "detail_plain_admin")
    order = _order({"parties": {}}, owner=None)

    html = client.get(f"/edit/{order.id}").get_data(as_text=True)

    assert 'data-erp-order-source="NAVER_SMARTSTORE"' not in html


def test_templates_use_the_canonical_source_marker():
    """템플릿 리터럴이 상수와 어긋나면 표식이 조용히 안 뜬다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "templates" / "orders" / "partials"
    for name in ("erp_order_tab.html", "erp_order_tab_mobile.html"):
        text = (root / name).read_text(encoding="utf-8")
        assert f"'{SOURCE_MARKER}'" in text, f"{name} 의 source 비교 리터럴이 상수와 다르다"
        assert f'data-erp-order-source="{SOURCE_MARKER}"' in text


def test_dto_default_keeps_existing_callers_unflagged(app):
    """인자를 안 주면 뱃지 없음 — 기존 호출자 동작 보존."""
    from foms.services.orders.dashboard_dto import build_orders_row_dtos

    order = _order(_naver_sd(), owner=None)

    rows = build_orders_row_dtos([order], {order.id: _naver_sd()}, {}, {}, None)

    assert rows[0]["is_unassigned_intake"] is False
