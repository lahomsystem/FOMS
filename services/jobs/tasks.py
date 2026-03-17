"""
RQ Worker 태스크 정의.
worker 프로세스에서 실행되며, Flask 앱 컨텍스트 없이 동작.
"""
import os
import sys
import logging

logger = logging.getLogger(__name__)

# 프로젝트 루트를 path에 추가 (worker 단독 실행 시)
if os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def create_thumbnail_for_attachment(attachment_id, storage_key):
    """
    주문 첨부 파일 썸네일 생성 (worker 전용).
    RQ job으로 enqueue되어 별도 worker 프로세스에서 실행됨.
    """
    if not attachment_id or not storage_key:
        return
    try:
        from services.storage import get_storage
        from db import db_session
        from models import OrderAttachment

        storage = get_storage()
        result = storage.generate_thumbnail_from_storage_key(storage_key)
        if not result.get('success'):
            return
        thumbnail_key = result.get('thumbnail_key')
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
        from foms_address_converter import FOMSAddressConverter
        from services.geocode_helpers import extract_address_from_order, compute_address_hash

        db = db_session()
        try:
            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                return

            address = extract_address_from_order(order)
            if not address:
                order.lat = None
                order.lng = None
                order.geocode_status = 'failed'
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
                order.geocode_status = 'success'
            else:
                order.lat = None
                order.lng = None
                order.geocode_status = 'failed'

            db.commit()
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] geocode_order_address error: {e}", exc_info=True)
        raise


def push_order_to_channeltalk(order_id, event_type="update"):
    """
    채널톡 그룹 메시지 푸시 (worker 전용).

    주문의 현재 상태를 채널톡 해당 팀 그룹으로 전송.
    단계에 맞는 카테고리의 이미지(최근 5장)를 Presigned URL로 첨부.

    Args:
        order_id: Order.id
        event_type: "new" / "update" / "save"
    """
    if not order_id:
        return
    try:
        from services.channel_client import (
            is_configured,
            format_order_message,
            get_target_group_id,
            get_attachment_category_for_status,
            send_group_message,
        )

        if not is_configured():
            logger.info("[채널톡] 환경변수 미설정 - 푸시 건너뜀")
            return

        from db import db_session
        from models import Order, OrderAttachment
        from services.storage import get_storage

        db = db_session()
        try:
            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                return

            sd = order.structured_data or {}
            schedule = sd.get("schedule", {})

            plain_text = format_order_message(
                customer_name=order.customer_name,
                status=order.status,
                address=order.address,
                order_id=order.id,
                schedule=schedule,
                event_type=event_type,
            )

            # 단계에 맞는 이미지 첨부 (최근 5장, Presigned URL)
            img_category = get_attachment_category_for_status(order.status)
            files = []
            if img_category:
                storage = get_storage()
                attachments = (
                    db.query(OrderAttachment)
                    .filter(
                        OrderAttachment.order_id == order.id,
                        OrderAttachment.category == img_category,
                        OrderAttachment.file_type == "image",
                    )
                    .order_by(OrderAttachment.id.desc())
                    .limit(5)
                    .all()
                )
                for att in attachments:
                    if att.storage_key:
                        url = storage.get_download_url(att.storage_key, expires_in=3600)
                        if url:
                            files.append({
                                "fileName": att.filename or "image.jpg",
                                "url": url,
                                "mime": "image/jpeg",
                            })

            group_id = get_target_group_id(order.status)
            result = send_group_message(
                group_id=group_id,
                plain_text=plain_text,
                files=files,
            )
            if not result.get('success'):
                raise RuntimeError(f"채널톡 전송 실패 (order_id={order_id}, group={group_id})")
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] push_order_to_channeltalk error: {e}", exc_info=True)
        raise
