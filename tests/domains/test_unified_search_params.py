from pathlib import Path

from db import db_session
from foms.services.request_utils import get_search_query_arg
from models import Order
from sqlalchemy.orm.attributes import flag_modified


def _add_erp_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-04-30",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 검색로 1",
        product="슬라이딩",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {
                "customer": {"name": customer_name},
                "manager": {"name": "기본 담당"},
            },
            "site": {"address_full": "서울시 테스트구 검색로 1"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_search_query_arg_uses_first_non_blank_alias(app):
    with app.test_request_context("/?q=&search=%EC%A0%95%EC%9E%AC%EA%B5%90"):
        assert get_search_query_arg("q", "search") == "정재교"


def test_order_list_accepts_q_alias_and_preserves_search_value(login):
    _add_erp_order("정재교 고객")

    response = login.get("/?q=정재교")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="order-search-input" name="search"' in body
    assert 'placeholder="전체 검색..."' in body
    assert 'value="정재교"' in body
    assert "정재교 고객" in body


def test_order_list_whole_search_ignores_active_status_tab(login):
    target = _add_erp_order("정재교 실측")
    target.status = "MEASURE"
    received = _add_erp_order("접수 고객")
    received.status = "RECEIVED"
    db_session.commit()

    response = login.get("/?status=RECEIVED&search=정재교")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="정재교"' in body
    assert "정재교 실측" in body
    assert "접수 고객" not in body
    assert 'name="status" value="RECEIVED"' not in body


def test_order_list_search_ignores_hidden_structured_item_memo(login):
    hidden = _add_erp_order("숨은메모 고객")
    hidden.structured_data["items"] = [
        {"product_name": "붙박이장", "extra_input": "견적가 이미지 참고 9547"}
    ]
    hidden.product = "붙박이장"
    flag_modified(hidden, "structured_data")

    visible = _add_erp_order("컬럼고객")
    visible.structured_data["parties"]["customer"]["name"] = "이미지 고객"
    visible.structured_data["items"] = [
        {"product_name": "슬라이딩"}
    ]
    visible.product = "슬라이딩"
    flag_modified(visible, "structured_data")
    db_session.commit()

    response = login.get("/?search=이미지")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이미지 고객" in body
    assert "숨은메모 고객" not in body


def test_order_list_phone_last4_search_does_not_match_hidden_structured_numbers(login):
    hidden = _add_erp_order("숨은번호 고객")
    hidden.structured_data["items"] = [
        {"product_name": "붙박이장", "extra_input": "내부 참고 번호 9547"}
    ]
    flag_modified(hidden, "structured_data")

    visible = _add_erp_order("전화번호 고객")
    visible.structured_data["parties"]["customer"]["phone"] = "010-1234-9547"
    flag_modified(visible, "structured_data")
    db_session.commit()

    response = login.get("/?search=9547")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "전화번호 고객" in body
    assert "숨은번호 고객" not in body


def test_order_list_searches_visible_structured_product_and_schedule(login):
    visible = _add_erp_order("표시필드 고객")
    visible.product = "레거시 제품"
    visible.measurement_date = ""
    visible.structured_data["items"] = [{"product_name": "구조화도어"}]
    visible.structured_data["schedule"] = {
        "measurement": {"date": "2026-06-17", "time": "오전"},
        "construction": {"date": "2026-06-20"},
    }
    flag_modified(visible, "structured_data")
    db_session.commit()

    product_response = login.get("/?search=구조화도어")
    date_response = login.get("/?search=2026-06-17")

    assert product_response.status_code == 200
    assert "표시필드 고객" in product_response.get_data(as_text=True)
    assert date_response.status_code == 200
    assert "표시필드 고객" in date_response.get_data(as_text=True)


def test_order_list_refreshes_bfcache_after_erp_save_back_navigation():
    """ERP 저장 후 history.back 시 목록이 stale하지 않도록 전역 레이아웃 스크립트가 갱신한다."""
    text = Path("templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )

    assert "foms:reload-order-list-after-erp-save" in text
    assert "window.addEventListener('pageshow'" in text
    assert "event.persisted" in text
    assert "window.location.reload();" in text
    assert "foms:restore-order-list-scroll" in text
    assert "window.scrollTo(0, scrollY);" in text


def test_erp_dashboard_accepts_search_alias_and_preserves_q_value(login):
    _add_erp_order("정재교 고객")

    response = login.get("/erp/dashboard?search=정재교")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="q" placeholder="전체 검색..." value="정재교"' in body
    assert "정재교 고객" in body


def test_erp_dashboard_whole_search_ignores_active_stage_pipeline(login):
    _add_erp_order("이은지 고객")

    response = login.get("/erp/dashboard?stage=AS처리&q=이은지")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="q" placeholder="전체 검색..." value="이은지"' in body
    assert "이은지 고객" in body
    assert 'value="AS처리" selected' not in body


def test_erp_dashboard_search_ignores_hidden_structured_item_memo(login):
    hidden = _add_erp_order("노출되면안됨 고객")
    hidden.structured_data["items"] = [
        {"product_name": "붙박이장", "extra_input": "견적가 이미지 참고"}
    ]
    hidden.product = "붙박이장"

    visible = _add_erp_order("이미지 고객")
    visible.structured_data["items"] = [
        {"product_name": "슬라이딩"}
    ]
    visible.product = "슬라이딩"
    db_session.commit()

    response = login.get("/erp/dashboard?q=이미지")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이미지 고객" in body
    assert "노출되면안됨 고객" not in body


def test_erp_search_placeholders_use_whole_search_label():
    template_paths = [
        "templates/orders/partials/dashboard_filters.html",
        "templates/orders/partials/dashboard_mobile_filters.html",
        "templates/orders/partials/history_dashboard_body.html",
        "templates/production/partials/filters.html",
        "templates/production/partials/mobile_filters.html",
        "templates/construction/partials/filters.html",
        "templates/construction/partials/mobile_filters.html",
        "templates/measurement/partials/dashboard_main.html",
        "templates/measurement/partials/mobile_filters.html",
        "templates/shipment/partials/dashboard_main.html",
        "templates/cs/partials/as_dashboard_body.html",
        "templates/cs/partials/as_mobile_controls.html",
        "templates/drawing/partials/workbench_dashboard_body.html",
    ]

    for path in template_paths:
        text = Path(path).read_text(encoding="utf-8")
        assert 'placeholder="전체 검색..."' in text, path
