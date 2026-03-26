"""
ChannelTalk Dispatch Service (Phase A)
- 정책(channel_policy)과 클라이언트(channel_client)를 잇는 중간 레이어
- 향후 Outbox 처리 및 Payload 생성을 담당
"""
import logging
from typing import Dict, Any, List, Optional
import requests

from services.channel_client import send_group_message
from services.channel_policy import get_routing_group_id, build_message_template, apply_attachment_policy

logger = logging.getLogger(__name__)

def dispatch_channel_push(delivery_id: int):
    """
    ChannelDeliveryLog를 기반으로 메시지를 조립하고 전송한다.
    의존성: 
    - db 세션을 직접 열어 상태를 확인하고 변경.
    """
    from db import db_session
    from models import Order, OrderAttachment, ChannelDeliveryLog
    from services.storage import get_storage
    from services.channel_delivery import mark_delivery_status, mark_api_failed, mark_api_rejected, mark_token_rate_limited
    
    session = db_session()
    try:
        log = session.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == delivery_id).first()
        if not log:
            logger.warning(f"[ChannelDispatch] Delivery log {delivery_id} not found")
            return
            
        if log.status != 'pending':
            logger.info(f"[ChannelDispatch] Delivery log {delivery_id} is not pending (status: {log.status})")
            return
            
        order = session.query(Order).filter(Order.id == log.order_id).first()
        if not order:
            mark_delivery_status(session, log.id, 'ignored_stale', 'Order deleted')
            session.commit()
            return
            
        if log.source_version and order.channel_source_seq and log.source_version < order.channel_source_seq:
            mark_delivery_status(session, log.id, 'ignored_stale', f'Stale event (log_v={log.source_version} < order_v={order.channel_source_seq})')
            session.commit()
            return
            
        parts = log.event_key.split('_')
        current_event_type = parts[2] if len(parts) >= 3 else 'update'
        
        sd = order.structured_data or {}
        data = {
            'order_id': order.id,
            'customer_name': order.customer_name,
            'address': order.address,
            'measurement_date': (sd.get('schedule') or {}).get('measurement', {}).get('date', '-'),
            'reason': '상태 변경 발생',
            'status': order.status
        }
        
        # 파일 수집 (정책에 따라 category 식별)
        from services.channel_client import get_attachment_category_for_status
        img_category = get_attachment_category_for_status(order.status)
        files = []
        if img_category:
            storage = get_storage()
            attachments = session.query(OrderAttachment).filter(
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
        
        # 1. 대상 그룹 결정
        group_id = get_routing_group_id(current_event_type, data)
        if not group_id:
            logger.warning("[ChannelDispatch] 라우팅 그룹 없음: %s", current_event_type)
            mark_api_failed(session, log.id, 'No routing group')
            session.commit()
            return
            
        # 2. 메시지 템플릿 생성
        plain_text = build_message_template(current_event_type, data)
        
        # 3. 첨부파일 정책 적용
        files = apply_attachment_policy(files)
        
        try:
            result = send_group_message(
                group_id=group_id,
                plain_text=plain_text,
                files=files,
                bot_name="FOMS",
                raise_on_error=True
            )
            mark_delivery_status(session, log.id, 'sent', message_id=result.get('message_id'))
            session.commit()
        except requests.exceptions.HTTPError as e:
            resp = e.response
            if resp is not None:
                if resp.status_code == 429:
                    mark_token_rate_limited(session, log.id, str(e))
                elif 400 <= resp.status_code < 500:
                    mark_api_rejected(session, log.id, str(e))
                else:
                    mark_api_failed(session, log.id, str(e))
            else:
                mark_api_failed(session, log.id, str(e))
            session.commit()
            raise # Let worker retry or handle
        except Exception as e:
            mark_api_failed(session, log.id, str(e))
            session.commit()
            raise
            
    except Exception as e:
        logger.error(f"[ChannelDispatch] Error in dispatch_channel_push for log {delivery_id}: {e}", exc_info=True)
        raise
    finally:
        session.close()

def dispatch_order_event(event_type: str, data: Dict[str, Any], raise_on_error: bool = False) -> dict:
    """
    주문 이벤트를 받아 템플릿과 라우팅 정책을 적용하여 ChannelTalk로 전송(또는 Outbox 기록)한다.
    
    Args:
        event_type: 이벤트 종류 ('manual', 'measurement_completed' 등)
        data: 전송에 필요한 데이터 페이로드
        raise_on_error: 클라이언트 레벨 예외를 상위로 던질지 여부
        
    Returns:
        {"success": bool, "message_id": str | None}
    """
    try:
        # 1. 대상 그룹 결정
        group_id = get_routing_group_id(event_type, data)
        if not group_id:
            logger.warning("[ChannelDispatch] 라우팅 그룹 없음: %s", event_type)
            return {"success": False, "message_id": None}
            
        # 2. 메시지 템플릿 생성
        plain_text = build_message_template(event_type, data)
        
        # 3. 첨부파일 정책 적용
        files = data.get('files', [])
        files = apply_attachment_policy(files)
        
        # 4. 클라이언트 전송 (향후 CT-A-02 로직에서 Outbox DB에 먼저 넣고 백그라운드로 처리됨)
        result = send_group_message(
            group_id=group_id,
            plain_text=plain_text,
            files=files,
            bot_name="FOMS",
            raise_on_error=raise_on_error
        )
        
        return result
        
    except Exception as e:
        logger.error("[ChannelDispatch] Dispatch 실패: %s", e, exc_info=True)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
