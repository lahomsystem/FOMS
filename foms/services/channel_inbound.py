"""
ChannelTalk Inbound Service (Phase E)
- 웹훅 수신, Dedupe/Creation Key 생성, 로그 저장 (CT-E-01)
- 텍스트 파싱 규칙 적용 및 마스킹 (CT-E-02)
- 실제 주문/태스크 생성 연동 (CT-E-03)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from foms.persistence.main.db import db_session, get_db
from foms.persistence.main.models import ChannelInboundEventLog, Order
from foms.services.datetime_kst import get_today_kst
from foms.services.jobs.queue import enqueue_channeltalk_inbound

__all__ = [
    "generate_payload_hash",
    "extract_keys",
    "receive_webhook",
    "parse_order_text",
    "process_inbound_job",
]

logger = logging.getLogger(__name__)


def generate_payload_hash(payload: dict) -> str:
    """Payload 전체 해시 (SHA-256)"""
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def extract_keys(payload: dict) -> Tuple[Optional[str], str, Optional[str]]:
    """
    payload에서 provider_event_id, dedupe_key, creation_key 추출 (CT-E-01)
    """
    # 1. provider_event_id 확인 (보통 채널톡 웹훅에는 event_id나 id가 최상위에 있을 수 있음)
    provider_event_id = payload.get("id") or payload.get("eventId")

    entity = payload.get("entity", {})
    ref = payload.get("ref", {})

    # Stable message key: chat_id + message_id 또는 유사한 조합
    stable_id = None
    if entity and entity.get("id"):
        stable_id = f"{payload.get('type', 'unknown')}_{entity.get('id')}"

    # Dedupe key 결정 로직
    if provider_event_id:
        dedupe_key = f"evt_{provider_event_id}"
    elif stable_id:
        dedupe_key = f"msg_{stable_id}"
    else:
        # Fallback: replay-window hash (생성용으로는 금지됨)
        payload_hash = generate_payload_hash(payload)
        dedupe_key = f"hash_{payload_hash}"

    # Creation key 결정 로직 (Dedupe와 유사하나 Hash fallback은 None으로 처리)
    if provider_event_id:
        creation_key = f"crt_{provider_event_id}"
    elif stable_id:
        creation_key = f"crt_{stable_id}"
    else:
        creation_key = None

    return provider_event_id, dedupe_key, creation_key


def receive_webhook(payload: dict) -> Tuple[int, Dict[str, Any]]:
    """
    Webhook 수신 및 Receipt Log 저장, Enqueue 처리 (CT-E-01, CT-E-05)
    반환: (HTTP_STATUS_CODE, Response_JSON)
    """
    db = get_db()

    # 1. Key 추출
    provider_event_id, dedupe_key, creation_key = extract_keys(payload)
    payload_hash = generate_payload_hash(payload)

    # 2. 중복 검사 (Dedupe)
    existing_log = db.query(ChannelInboundEventLog).filter_by(dedupe_key=dedupe_key).first()
    if existing_log:
        terminal_statuses = [
            "worker_processing",
            "created",
            "parse_failed",
            "rejected_signature",
            "rejected_replay",
            "rejected_group",
            "ignored_duplicate",
        ]
        if existing_log.status in terminal_statuses:
            return 200, {"status": "duplicate_ignored"}

        # received 또는 queue_enqueue_failed 상태면 재 enqueue 시도
        if enqueue_channeltalk_inbound(existing_log.id):
            return 200, {"status": "re_enqueued"}
        return 503, {"error": "queue_unavailable"}

    # 3. 그룹 화이트리스트 검사 (CT-E-01)
    allowed_groups_str = os.environ.get("CHANNEL_ALLOWED_GROUP_IDS", "")
    allowed_groups = [g.strip() for g in allowed_groups_str.split(",")] if allowed_groups_str else []

    entity = payload.get("entity", {})
    chat_id = entity.get("chatId") or entity.get("channelId") or str(payload.get("ref", {}).get("id", ""))

    # 테스트 환경이나 화이트리스트가 비어있으면 통과 (단, 실 운영에서는 엄격히 설정)
    if allowed_groups and chat_id and chat_id not in allowed_groups:
        log = ChannelInboundEventLog(
            provider_event_id=provider_event_id,
            dedupe_key=dedupe_key,
            creation_key=creation_key,
            payload_hash=payload_hash,
            raw_payload=payload,
            chat_type=payload.get("type"),
            source_chat_id=chat_id,
            status="rejected_group",
        )
        db.add(log)
        db.commit()
        # 거부된 그룹은 200으로 처리하여 Provider 재시도 방지 (설정 문제이므로)
        return 200, {"status": "rejected_group"}

    # 4. Inbound Log 생성 (Receipt Persist)
    log = ChannelInboundEventLog(
        provider_event_id=provider_event_id,
        dedupe_key=dedupe_key,
        creation_key=creation_key,
        payload_hash=payload_hash,
        raw_payload=payload,
        chat_type=payload.get("type"),
        source_chat_id=chat_id,
        status="received",
    )
    db.add(log)
    db.commit()

    # 5. Async Enqueue
    if enqueue_channeltalk_inbound(log.id):
        return 200, {"status": "received", "log_id": log.id}

    # Enqueue 실패 시 상태 업데이트
    log.status = "queue_enqueue_failed"
    db.commit()
    return 503, {"error": "queue_unavailable"}


def parse_order_text(text: str) -> Tuple[bool, Dict[str, Any], list[str], Dict[str, Any]]:
    """
    텍스트 파싱 로직 (CT-E-02)
    반환: (성공여부, 파싱된데이터, 누락된필드목록)
    """
    data = {}
    missing = []

    # 정규식 패턴 (고객명, 연락처, 주소, 수주제품)
    name_match = re.search(r"고객명\s*[:\-]?\s*(.+)", text)
    phone_match = re.search(r"연락처\s*[:\-]?\s*([0-9\-\.]+)", text)
    addr_match = re.search(r"주소\s*[:\-]?\s*(.+)", text)
    product_match = re.search(r"수주제품\s*[:\-]?\s*(.+)", text)

    if name_match:
        data["customer_name"] = name_match.group(1).strip()
    else:
        missing.append("고객명")

    if phone_match:
        data["phone"] = phone_match.group(1).strip()
    else:
        missing.append("연락처")

    if addr_match:
        data["address"] = addr_match.group(1).strip()
    else:
        missing.append("주소")

    if product_match:
        data["product"] = product_match.group(1).strip()

    # PII 마스킹 (저장용)
    masked_data = {}
    for k, v in data.items():
        if k == "customer_name" and len(v) >= 2:
            masked_data[k] = v[0] + "*" * (len(v) - 1)
        elif k == "phone" and len(v) >= 10:
            parts = v.split("-")
            if len(parts) == 3:
                masked_data[k] = f"{parts[0]}-****-{parts[2]}"
            else:
                masked_data[k] = v[:3] + "****" + v[-4:]
        else:
            masked_data[k] = v

    success = len(missing) == 0
    return success, data, missing, masked_data


def process_inbound_job(log_id: int):
    """
    Worker에서 실행되는 실제 처리 로직 (CT-E-03)
    """
    db = db_session
    log = db.query(ChannelInboundEventLog).get(log_id)
    if not log:
        logger.error(f"[Inbound] Log {log_id} not found.")
        return

    if log.status not in ["received", "queue_enqueue_failed"]:
        logger.warning(f"[Inbound] Log {log_id} is already in terminal state: {log.status}")
        return

    log.status = "worker_processing"
    db.commit()

    try:
        payload = log.raw_payload or {}
        # UserChat / Message 텍스트 추출 (채널톡 웹훅 스키마에 따라 변동 가능)
        entity = payload.get("entity", {})
        text = entity.get("plainText") or entity.get("message") or ""

        if not text:
            # 텍스트가 없는 이벤트는 무시
            log.status = "ignored_duplicate"  # 의미상 ignored
            log.error_reason = "No text content to parse."
            log.processed_at = datetime.now()
            db.commit()
            return

        # 1. 파싱
        success, parsed_data, missing, masked_data = parse_order_text(text)
        log.parsed_result = masked_data

        if not success:
            log.status = "parse_failed"
            log.error_reason = f"Missing fields: {', '.join(missing)}"
            log.processed_at = datetime.now()
            db.commit()

            # TODO: 채널톡 API를 통해 실패 안내 Quick Reply 전송 (channel_client 활용)
            return

        # 2. 생성 모드 판단
        create_enabled = os.environ.get("CHANNEL_INBOUND_CREATE_ENABLED", "false").lower() == "true"

        if not create_enabled or not log.creation_key:
            log.status = "dry_run_completed"
            log.processed_at = datetime.now()
            db.commit()
            return

        # 3. Order 생성
        new_order = Order(
            received_date=get_today_kst().strftime("%Y-%m-%d"),
            customer_name=parsed_data.get("customer_name"),
            phone=parsed_data.get("phone"),
            address=parsed_data.get("address"),
            product=parsed_data.get("product", "-"),
            status="RECEIVED",
            is_erp_order=True,
        )
        db.add(new_order)
        db.commit()  # ID 획득

        log.created_order_id = new_order.id
        log.created_order_ref = f"ORD-{new_order.id}"
        log.status = "created"
        log.processed_at = datetime.now()
        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"[Inbound] Error processing log {log_id}: {e}", exc_info=True)
        log.status = "worker_processing_failed"
        log.error_reason = str(e)
        log.processed_at = datetime.now()
        db.commit()
