import pytest
import os
from unittest.mock import patch
from services.channel_inbound import extract_keys, parse_order_text, receive_webhook, process_inbound_job
from models import ChannelInboundEventLog, Order
from db import db_session

def test_extract_keys():
    # 1. provider_event_id provided
    payload1 = {
        "eventId": "evt-123",
        "type": "userChat",
        "entity": {"id": "chat-456"}
    }
    evt_id, dedupe, creation = extract_keys(payload1)
    assert evt_id == "evt-123"
    assert dedupe == "evt_evt-123"
    assert creation == "crt_evt-123"
    
    # 2. stable message key
    payload2 = {
        "type": "userChat",
        "entity": {"id": "chat-789"}
    }
    evt_id, dedupe, creation = extract_keys(payload2)
    assert evt_id is None
    assert dedupe == "msg_userChat_chat-789"
    assert creation == "crt_userChat_chat-789"
    
    # 3. fallback hash
    payload3 = {
        "type": "unknown_event",
        "random_data": 123
    }
    evt_id, dedupe, creation = extract_keys(payload3)
    assert evt_id is None
    assert dedupe.startswith("hash_")
    assert creation is None

def test_parse_order_text():
    valid_text = """
    [신규 주문 접수]
    고객명: 홍길동
    연락처: 010-1234-5678
    주소: 서울시 강남구 테헤란로 123
    수주제품: 가죽소파 3인용
    """
    success, data, missing, masked = parse_order_text(valid_text)
    assert success is True
    assert data['customer_name'] == '홍길동'
    assert data['phone'] == '010-1234-5678'
    assert masked['customer_name'] == '홍**'
    assert masked['phone'] == '010-****-5678'
    
    invalid_text = """
    [주문]
    고객명: 김철수
    수주제품: 침대
    """
    success, data, missing, masked = parse_order_text(invalid_text)
    assert success is False
    assert '연락처' in missing
    assert '주소' in missing

@patch('services.channel_inbound.enqueue_channeltalk_inbound')
def test_receive_webhook_success(mock_enqueue, app):
    mock_enqueue.return_value = True
    payload = {
        "eventId": "evt-webhook-1",
        "type": "userChat",
        "entity": {"id": "chat-1", "chatId": "group-1"}
    }
    
    with app.app_context():
        status_code, response = receive_webhook(payload)
        
        assert status_code == 200
        assert response['status'] == 'received'
        
        log = db_session.query(ChannelInboundEventLog).filter_by(dedupe_key="evt_evt-webhook-1").first()
        assert log is not None
        assert log.status == 'received'
        assert log.source_chat_id == 'group-1'

@patch('services.channel_inbound.enqueue_channeltalk_inbound')
def test_receive_webhook_duplicate(mock_enqueue, app):
    mock_enqueue.return_value = True
    payload = {
        "eventId": "evt-webhook-2",
        "type": "userChat"
    }
    
    with app.app_context():
        # First call
        receive_webhook(payload)
        log = db_session.query(ChannelInboundEventLog).filter_by(dedupe_key="evt_evt-webhook-2").first()
        log.status = 'created' # terminal state
        db_session.commit()
        
        # Second call
        status_code, response = receive_webhook(payload)
        assert status_code == 200
        assert response['status'] == 'duplicate_ignored'

@patch('services.channel_inbound.enqueue_channeltalk_inbound')
def test_process_inbound_job_dry_run(mock_enqueue, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_INBOUND_CREATE_ENABLED", "false")
    
    with app.app_context():
        log = ChannelInboundEventLog(
            dedupe_key="test-job-1",
            creation_key="crt-job-1",
            payload_hash="hash",
            status="received",
            raw_payload={
                "entity": {
                    "plainText": "고객명: 테스트\n연락처: 010-1111-2222\n주소: 서울시\n수주제품: 소파"
                }
            }
        )
        db_session.add(log)
        db_session.commit()
        
        process_inbound_job(log.id)
        
        db_session.refresh(log)
        assert log.status == 'dry_run_completed'
        assert log.created_order_id is None
        assert log.parsed_result['customer_name'] == '테**'

@patch('services.channel_inbound.enqueue_channeltalk_inbound')
def test_process_inbound_job_create_enabled(mock_enqueue, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_INBOUND_CREATE_ENABLED", "true")
    
    with app.app_context():
        log = ChannelInboundEventLog(
            dedupe_key="test-job-2",
            creation_key="crt-job-2",
            payload_hash="hash",
            status="received",
            raw_payload={
                "entity": {
                    "plainText": "고객명: 실제고객\n연락처: 010-9999-8888\n주소: 부산시\n수주제품: 식탁"
                }
            }
        )
        db_session.add(log)
        db_session.commit()
        
        process_inbound_job(log.id)
        
        db_session.refresh(log)
        assert log.status == 'created'
        assert log.created_order_id is not None
        
        order = db_session.query(Order).get(log.created_order_id)
        assert order.customer_name == "실제고객"
        assert order.address == "부산시"
        assert order.is_erp_beta is True
