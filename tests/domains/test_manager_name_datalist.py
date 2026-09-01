"""담당자 입력 칸 후보 목록(datalist) 계약.

주문 담당자는 자유 입력이라 표기가 조금만 달라도 안내 문자의 담당자 연락처가 대표번호로
떨어진다. 후보 목록을 띄우되 값 자체는 제약하지 않는다(목록에 없는 사람도 직접 입력).
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import context_processors as cp
from models import Order, User


@pytest.fixture
def form_client(client):
    """주문 추가·수정 화면을 열 수 있는 사용자로 로그인."""
    user = User(
        username="mgr_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="담당 관리자",
    )
    db_session.add(user)
    db_session.commit()
    client.post(
        "/login",
        data={"username": "mgr_admin", "password": "admin"},
        follow_redirects=True,
    )
    return client


def _stub_settings(monkeypatch, managers):
    monkeypatch.setattr(
        cp, "load_erp_shipment_settings", lambda: {"measurement_manager": managers}
    )


def test_options_follow_sort_order_and_dedupe(monkeypatch):
    _stub_settings(monkeypatch, [
        {"name": "한용희", "phone": "010-1111-1111", "sort_order": 7},
        {"name": "김의종", "phone": "010-2222-2222", "sort_order": 1},
        {"name": "한용희", "phone": "010-3333-3333", "sort_order": 9},
        {"name": "  ", "phone": "010-4444-4444", "sort_order": 2},
    ])
    assert cp.manager_name_options() == ["김의종", "한용희"]


def test_options_empty_when_settings_unreadable(monkeypatch):
    def _boom():
        raise RuntimeError("설정 조회 실패")

    monkeypatch.setattr(cp, "load_erp_shipment_settings", _boom)
    assert cp.manager_name_options() == []


def test_add_order_form_offers_candidates(form_client, monkeypatch):
    _stub_settings(monkeypatch, [{"name": "백재현", "phone": "010-5555-5555",
                                  "sort_order": 6}])
    body = form_client.get("/add").get_data(as_text=True)
    assert 'list="manager_name_options"' in body
    assert 'id="manager_name_options"' in body
    assert '<option value="백재현"></option>' in body


def test_edit_order_form_offers_candidates(form_client, monkeypatch):
    _stub_settings(monkeypatch, [{"name": "정다슬", "phone": "010-6666-6666",
                                  "sort_order": 4}])
    order = Order(
        received_date="2026-09-01",
        customer_name="담당자 후보",
        phone="010-0000-0000",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=True,
        manager_name="목록에 없는 사람",
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    body = form_client.get(f"/edit/{order.id}").get_data(as_text=True)
    assert 'list="manager_name_options"' in body
    assert '<option value="정다슬"></option>' in body
    # datalist 는 값을 제약하지 않는다 — 목록 밖 이름도 그대로 칠 수 있어야 한다.
    assert 'id="erp-manager"' in body
    # 한 화면에 후보 목록이 두 벌 렌더되면 id 가 겹친다(ERP·비ERP 폼은 배타적이어야 한다).
    assert body.count('id="manager_name_options"') == 1


def test_legacy_edit_form_offers_candidates(form_client, monkeypatch):
    """비ERP 주문 편집 폼(`manager_name` 입력)에도 같은 후보가 붙는다."""
    _stub_settings(monkeypatch, [{"name": "강민경", "phone": "010-7777-7777",
                                  "sort_order": 5}])
    order = Order(
        received_date="2026-09-01",
        customer_name="구형 주문",
        phone="010-0000-0001",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=False,
        manager_name="목록에 없는 사람",
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    body = form_client.get(f"/edit/{order.id}").get_data(as_text=True)
    assert 'id="manager_name"' in body
    assert 'list="manager_name_options"' in body
    assert '<option value="강민경"></option>' in body
    assert 'value="목록에 없는 사람"' in body
    assert body.count('id="manager_name_options"') == 1


def test_mobile_erp_form_offers_candidates(form_client, monkeypatch):
    """모바일 ERP 폼도 후보를 띄운다 — 담당자 칸은 input 이라야 `list` 가 먹는다.

    모바일 코호트는 PC·모바일 두 표면을 함께 렌더하고 인라인 스크립트가 한쪽을 지운다.
    그래서 후보 목록 id 는 표면마다 달라야 한다(지워지기 전까지 id 가 겹친다).
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _stub_settings(monkeypatch, [{"name": "안중훈", "phone": "010-8888-8888",
                                  "sort_order": 3}])
    order = Order(
        received_date="2026-09-01",
        customer_name="모바일 후보",
        phone="010-0000-0002",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    user = db_session.query(User).filter_by(username="mgr_admin").first()
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    body = form_client.get(f"/edit/{order.id}").get_data(as_text=True)
    assert 'id="erp-order-form-mobile"' in body
    assert 'list="manager_name_options_mobile"' in body
    assert body.count('id="manager_name_options_mobile"') == 1
    assert body.count('id="manager_name_options"') == 1
    # 담당자 칸은 input 이라야 후보가 뜬다. 시공 담당자는 여러 명을 줄로 적으므로 textarea 유지.
    assert 'id="erp-construction-workers"' in body
