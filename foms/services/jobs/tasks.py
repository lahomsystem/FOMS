"""
RQ Worker 태스크 정의.
worker 프로세스에서 실행되며, Flask 앱 컨텍스트 없이 동작.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 프로젝트 루트를 path에 추가 (worker 단독 실행 시)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_repo_root_str = str(_REPO_ROOT)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

__all__ = [
    "create_thumbnail_for_attachment",
    "geocode_order_address",
    "push_order_to_channeltalk",
    "process_channeltalk_inbound",
]


def create_thumbnail_for_attachment(attachment_id, storage_key):
    """
    주문 첨부 파일 썸네일 생성 (worker 전용).
    RQ job으로 enqueue되어 별도 worker 프로세스에서 실행됨.
    """
    if not attachment_id or not storage_key:
        return
    try:
        from foms.services.storage import get_storage
        from db import db_session
        from models import OrderAttachment

        storage = get_storage()
        result = storage.generate_thumbnail_from_storage_key(storage_key)
        if not result.get("success"):
            return
        thumbnail_key = result.get("thumbnail_key")
        if not thumbnail_key:
            return

        db = db_session()
        try:
            attachment = db.query(OrderAttachment).filter(OrderAttachment.id == int(attachment_id)).first()
            if attachment and not attachment.thumbnail_key:
                attachment.thumbnail_key = thumbnail_key
                db.commit()
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] create_thumbnail_for_attachment error: {e}", exc_info=True)
        raise


def geocode_order_address(order_id):
    """
    주문 주소 지오코딩 (Phase C).
    RQ job으로 enqueue되어 worker에서 실행.
    FOMSAddressConverter로 좌표 획득 후 Order.lat/lng/geocode_status/geocoded_at/address_hash 갱신.
    """
    import datetime

    if not order_id:
        return
    try:
        from db import db_session
        from models import Order
        from foms.services.common.address_converter import FOMSAddressConverter
        from foms.services.geocode_helpers import extract_address_from_order, compute_address_hash

        db = db_session()
        try:
            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                return

            address = extract_address_from_order(order)
            if not address:
                order.lat = None
                order.lng = None
                order.geocode_status = "failed"
                order.geocoded_at = datetime.datetime.now()
                db.commit()
                return

            new_hash = compute_address_hash(address)
            if order.address_hash == new_hash and order.lat is not None and order.lng is not None:
                return

            converter = FOMSAddressConverter()
            lat, lng, status = converter.convert_address(address)

            order.geocoded_at = datetime.datetime.now()
            order.address_hash = new_hash

            if lat is not None and lng is not None:
                order.lat = float(lat)
                order.lng = float(lng)
                order.geocode_status = "success"
            else:
                order.lat = None
                order.lng = None
                order.geocode_status = "failed"

            db.commit()
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] geocode_order_address error: {e}", exc_info=True)
        raise


def push_order_to_channeltalk(delivery_id: int):
    """
    채널톡 그룹 메시지 푸시 (worker 전용). Phase A: Outbox 패턴 지원
    """
    if not delivery_id:
        return
    try:
        from foms.services.channel_client import is_configured

        if not is_configured():
            logger.info("[채널톡] 환경변수 미설정 - 푸시 건너뜀")
            return

        from foms.services.channel_dispatch import dispatch_channel_push

        dispatch_channel_push(delivery_id)

    except Exception as e:
        logger.error(f"[RQ] push_order_to_channeltalk error for log {delivery_id}: {e}", exc_info=True)
        raise


def process_channeltalk_inbound(event_log_id: int):
    """
    채널톡 인바운드 웹훅 파싱 및 도메인 생성 (CT-E-03).
    RQ job으로 enqueue되어 worker에서 실행.
    """
    if not event_log_id:
        return

    try:
        from foms.services.channel_inbound import process_inbound_job

        process_inbound_job(event_log_id)
    except Exception as e:
        logger.error(f"[RQ] process_channeltalk_inbound error for log {event_log_id}: {e}", exc_info=True)
        raise
