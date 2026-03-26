"""
ChannelTalk Dispatch Service (Phase A)
- 정책(channel_policy)과 클라이언트(channel_client)를 잇는 중간 레이어
- 향후 Outbox 처리 및 Payload 생성을 담당
"""
import logging
from typing import Dict, Any, List

from services.channel_client import send_group_message
from services.channel_policy import get_routing_group_id, build_message_template, apply_attachment_policy

logger = logging.getLogger(__name__)

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
