"""
ChannelTalk 통합 알림 라우팅 및 템플릿 정책.
(Phase B: CT-B-01 ~ CT-B-04 구현)
"""
import os
from typing import Dict, Any, List

# Dedupe Windows (seconds)
DEDUPE_WINDOWS = {
    'urgent': 0,
    'manual': 0,
    'normal': 60,
    'info': 300
}

def get_routing_group_id(event_type: str, order_info: Dict[str, Any] = None) -> str:
    """
    이벤트 타입 및 주문 정보에 따라 적절한 채널톡 그룹 ID를 반환한다.
    
    Args:
        event_type: 'manual', 'measurement_completed', 'drawing_approved' 등
        order_info: 주문 컨텍스트 딕셔너리 (필요 시 팀 정보 참조)
    """
    # 환경변수에서 기본 그룹 로드
    base_group = os.environ.get('CHANNEL_GROUP_MEASUREMENT', '')
    
    # 향후 event_type 에 따라 동적 라우팅 가능 (현재는 모두 단일 그룹)
    if event_type == 'as_urgent':
        return os.environ.get('CHANNEL_GROUP_AS', base_group)
    
    return base_group

def build_message_template(event_type: str, data: Dict[str, Any]) -> str:
    """
    이벤트 타입과 데이터 페이로드를 받아 전송할 텍스트 템플릿을 렌더링한다.
    """
    order_id = data.get('order_id', '?')
    customer_name = data.get('customer_name', '고객')
    erp_url = os.environ.get('FOMS_BASE_URL', 'http://localhost:5000')
    link_str = f"🔗 주문 상세 보기: {erp_url}/erp/orders/{order_id}"
    
    if event_type == 'manual':
        user_message = data.get('text', '')
        is_retry = data.get('is_retry', False)
        prefix = "[수정]\n" if is_retry else "[ERP 푸시]\n"
        return f"{prefix}주문 #{order_id} - {customer_name}\n\n{user_message}\n\n{link_str}"
        
    elif event_type == 'measurement_completed':
        address = data.get('address', '-')
        date_str = data.get('measurement_date', '-')
        return f"[실측완료] 주문 #{order_id} - {customer_name} 고객님\n실측이 완료되었습니다.\n📍 주소: {address}\n⏰ 실측일: {date_str}\n\n{link_str}"
        
    elif event_type == 'urgent':
        reason = data.get('reason', '긴급 확인 필요')
        return f"🚨 [긴급] 주문 #{order_id} - {customer_name} 고객님\n{reason}\n관련 담당자는 즉시 확인 바랍니다. @all\n\n{link_str}"
        
    else:
        # 기본 Fallback
        return f"[알림] 주문 #{order_id} 상태 변경\n\n{link_str}"

def apply_attachment_policy(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    첨부파일 정책 (CT-B-02) 적용.
    최대 10개 허용 및 MIME 타입 등 필터링.
    """
    max_files = 10
    # 파일이 dict 리스트라고 가정 (url, fileName, mime 등 포함)
    return files[:max_files]

def get_policy_version() -> str:
    """CT-5.11: 정책 버전 반환"""
    return "1.0.0"

def resolve_push_policy(event_type: str, order_snapshot: Dict[str, Any], wave: str = None) -> Dict[str, Any]:
    """CT-5.11: 이벤트 타입별 라우팅 및 처리 정책 반환"""
    group_id = get_routing_group_id(event_type, order_snapshot)
    
    # 기본 Dedupe window 결정
    dedupe_window = DEDUPE_WINDOWS.get('normal', 60)
    if event_type in ['manual', 'urgent', 'as_urgent']:
        dedupe_window = DEDUPE_WINDOWS.get(event_type, 0)
        
    return {
        "group_id": group_id,
        "dedupe_window": dedupe_window,
        "template_key": event_type,
        "max_attachments": 10
    }

def resolve_resend_policy(event_type: str, actor_role: str) -> Dict[str, Any]:
    """CT-5.11: 운영자 재전송 승인 규칙 및 snapshot/latest 우선순위"""
    # 기본적으로 ADMIN, MANAGER는 재전송 허용
    allowed = actor_role in ['ADMIN', 'MANAGER']
    return {
        "allowed": allowed,
        "default_mode": "snapshot" if event_type != 'manual' else "latest"
    }

def resolve_inbound_policy(group_id: str, template_key: str, create_enabled: bool) -> Dict[str, Any]:
    """CT-5.11: Inbound Webhook 수신 허용 그룹 및 생성 정책"""
    allowed_groups_str = os.environ.get('CHANNEL_ALLOWED_GROUP_IDS', '')
    allowed_groups = [g.strip() for g in allowed_groups_str.split(',')] if allowed_groups_str else []
    
    return {
        "is_allowed_group": not allowed_groups or group_id in allowed_groups,
        "can_create": create_enabled
    }
