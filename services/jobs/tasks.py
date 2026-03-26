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
    채널톡 그룹 메시지 푸시 (worker 전용). Phase A: Outbox 패턴 지원
    
    1. ChannelDeliveryLog에서 상태가 'pending'인 이벤트 처리
    2. 데이터가 없으면 기존(Legacy) 방식으로 주문 상태 기반 전송 진행
    """
    if not order_id:
        return
    try:
        from services.channel_client import is_configured
        
        if not is_configured():
            logger.info("[채널톡] 환경변수 미설정 - 푸시 건너뜀")
            return

        from db import db_session
        from models import Order, OrderAttachment, ChannelDeliveryLog
        from services.storage import get_storage
        from services.channel_dispatch import dispatch_order_event
        from services.channel_delivery import mark_delivery_status

        db = db_session()
        try:
            # 1. CT-A-03: Outbox (Pending Delivery Log) 처리
            pending_logs = db.query(ChannelDeliveryLog).filter(
                ChannelDeliveryLog.order_id == int(order_id),
                ChannelDeliveryLog.status == 'pending'
            ).order_by(ChannelDeliveryLog.id.asc()).all()

            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                # 주문이 삭제된 경우 pending 로그를 무시 처리
                for log in pending_logs:
                    mark_delivery_status(db, log.id, 'ignored_stale', 'Order deleted')
                db.commit()
                return

            if pending_logs:
                for log in pending_logs:
                    try:
                        # CT-A-07: Stale 이벤트 방지 (source_version 검증)
                        if log.source_version and order.channel_source_seq and log.source_version < order.channel_source_seq:
                            mark_delivery_status(db, log.id, 'ignored_stale', f'Stale event (log_v={log.source_version} < order_v={order.channel_source_seq})')
                            continue
                            
                        # event_key 에서 이벤트 타입 유추 (예: order_123_update_4)
                        parts = log.event_key.split('_')
                        if len(parts) >= 3:
                            current_event_type = parts[2]
                        else:
                            current_event_type = event_type
                            
                        # 기본 데이터 페이로드 조립
                        sd = order.structured_data or {}
                        data = {
                            'order_id': order.id,
                            'customer_name': order.customer_name,
                            'address': order.address,
                            'measurement_date': (sd.get('schedule') or {}).get('measurement', {}).get('date', '-'),
                            'reason': '상태 변경 발생' # 긴급일 경우 텍스트 대체 필요
                        }
                        
                        # 첨부파일 처리
                        from services.channel_client import get_attachment_category_for_status
                        img_category = get_attachment_category_for_status(order.status)
                        files = []
                        if img_category:
                            storage = get_storage()
                            attachments = db.query(OrderAttachment).filter(
                                OrderAttachment.order_id == order.id,
                                OrderAttachment.category == img_category,
                                OrderAttachment.file_type == "image"
                            ).order_by(OrderAttachment.id.desc()).limit(5).all()
                            
                            for att in attachments:
                                if att.storage_key:
                                    url = storage.get_download_url(att.storage_key, expires_in=3600)
                                    if url:
                                        files.append({
                                            "fileName": att.filename or "image.jpg",
                                            "url": url,
                                            "mime": "image/jpeg"
                                        })
                        data['files'] = files
                        
                        # DispatchService로 위임
                        result = dispatch_order_event(
                            event_type=current_event_type,
                            data=data,
                            raise_on_error=True
                        )
                        
                        if result.get('success'):
                            mark_delivery_status(db, log.id, 'sent', message_id=result.get('message_id'))
                        else:
                            mark_delivery_status(db, log.id, 'api_failed', 'Unknown dispatch failure')
                            
                    except Exception as loop_e:
                        logger.error(f"[ChannelDelivery] Worker Error for log_id={log.id}: {loop_e}", exc_info=True)
                        mark_delivery_status(db, log.id, 'api_failed', str(loop_e))
                db.commit()
                return

            # 2. CT-A-03: Legacy Payload 호환 모드 (pending_logs가 없는 경우 기존 방식)
            from services.channel_client import format_order_message, get_target_group_id, get_attachment_category_for_status, send_group_message
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
