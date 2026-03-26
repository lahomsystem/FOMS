import pytest
from services.channel_quick_actions import (
    parse_foms_command,
    process_foms_command,
    get_order_summary_for_wam,
    get_order_summary_text
)
from models import Order
from db import db_session

def test_parse_foms_command():
    cmd, param = parse_foms_command("주문 123")
    assert cmd == "주문"
    assert param == "123"
    
    cmd, param = parse_foms_command("일정 456")
    assert cmd == "일정"
    assert param == "456"
    
    cmd, param = parse_foms_command("잘못된입력")
    assert cmd == ""
    assert param == ""

def test_process_foms_command_invalid(app):
    with app.app_context():
        res = process_foms_command("이상한명령 123")
        assert "사용 가능한 명령어" in res["result"]["text"]
        
        res = process_foms_command("주문 abc")
        assert "사용 가능한 명령어" in res["result"]["text"]

def test_process_foms_command_order_not_found(app):
    with app.app_context():
        res = process_foms_command("주문 99999")
        assert "[오류]" in res["result"]["text"]
        assert "99999" in res["result"]["text"]

def test_process_foms_command_success(app):
    with app.app_context():
        order = Order(
            received_date="2026-03-26",
            customer_name="퀵액션고객",
            phone="010-9999-8888",
            address="서울시 강남구",
            status="RECEIVED",
            product="테스트소파"
        )
        db_session.add(order)
        db_session.commit()
        
        res = process_foms_command(f"주문 {order.id}")
        text = res["result"]["text"]
        assert "요약" in text
        assert "퀵액션고객" in text
        assert "테스트소파" in text
        
        # WAM 요약 테스트
        wam_data = get_order_summary_for_wam(order.id)
        assert wam_data is not None
        assert wam_data["customer_name"] == "퀵액션고객"
        assert wam_data["status_kr"] == "접수"
