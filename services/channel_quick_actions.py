"""
ChannelTalk Quick Actions Service (Phase D)
- 읽기 전용 Quick Action: 명령어 처리 및 WAM 데이터 조회
- 주문 요약, 일정 요약, 담당 요약, 첨부파일 목록 조회 지원
"""
from copy import deepcopy
import logging
from typing import Dict, Any, Tuple
from models import Order, OrderAttachment
from services.storage import get_storage
from db import get_db
from services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields

logger = logging.getLogger(__name__)

STATUS_MAP = {
    'RECEIVED': '접수',
    'MEASURE': '실측',
    'DRAWING': '도면',
    'CONFIRM': '컨펌',
    'PRODUCTION': '생산',
    'CONSTRUCTION': '시공',
    'CS': 'CS',
    'COMPLETED': '완료',
    'AS': 'AS'
}

def parse_foms_command(text: str) -> Tuple[str, str]:
    """
    명령어 파싱 헬퍼. '주문 1234', '일정 1234' 등을 분석.
    반환: (명령분류, 주문번호 문자열)
    """
    parts = str(text).strip().split()
    if len(parts) >= 2:
        cmd_type = parts[0]
        order_num = parts[1]
        return cmd_type, order_num
    return "", ""

def get_order_summary_text(order_id: str) -> str:
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return f"[오류] 존재하지 않는 주문 번호이거나 조회 권한이 없습니다. (#{order_id})"
        
        status_kr = STATUS_MAP.get(order.status, order.status)
        return (
            f"📦 주문 #{order.id} 요약\n"
            f"- 고객명: {order.customer_name or '-'}\n"
            f"- 연락처: {order.phone or '-'}\n"
            f"- 주소: {order.address or '-'}\n"
            f"- 현재 상태: {status_kr}\n"
            f"- 수주 제품: {order.product or '-'}"
        )
    except Exception as e:
        logger.error("[QuickAction] get_order_summary error: %s", e)
        return "[오류] 주문 정보를 불러오는 중 서버 오류가 발생했습니다."

def get_order_schedule_text(order_id: str) -> str:
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return f"[오류] 존재하지 않는 주문 번호이거나 조회 권한이 없습니다. (#{order_id})"
            
        sd = order.structured_data or {}
        sched = sd.get('schedule', {})
        recv = order.received_date or '-'
        measure = sched.get('measurement', {}).get('date', order.measurement_date or '-')
        const = sched.get('construction', {}).get('date', order.scheduled_date or '-')
        
        return (
            f"📅 주문 #{order.id} 일정 정보\n"
            f"- 접수일: {recv}\n"
            f"- 실측일: {measure}\n"
            f"- 시공일: {const}"
        )
    except Exception as e:
        logger.error("[QuickAction] get_order_schedule error: %s", e)
        return "[오류] 일정 정보를 불러오는 중 서버 오류가 발생했습니다."

def get_order_manager_text(order_id: str) -> str:
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return f"[오류] 존재하지 않는 주문 번호이거나 조회 권한이 없습니다. (#{order_id})"
            
        sd = order.structured_data or {}
        shipment = sd.get('shipment', {})
        draw_managers = shipment.get('drawing_managers', [])
        draw_mgr_str = ", ".join(draw_managers) if draw_managers else shipment.get('drawing_manager', '-')
        
        const_workers = shipment.get('construction_workers', [])
        const_wkr_str = ", ".join(const_workers) if const_workers else '-'
        
        return (
            f"👤 주문 #{order.id} 담당자 정보\n"
            f"- 담당 매니저: {order.manager_name or '-'}\n"
            f"- 도면 담당자: {draw_mgr_str}\n"
            f"- 시공 담당자: {const_wkr_str}"
        )
    except Exception as e:
        logger.error("[QuickAction] get_order_manager error: %s", e)
        return "[오류] 담당자 정보를 불러오는 중 서버 오류가 발생했습니다."

def process_foms_command(text: str, manager_id: str = None) -> Dict[str, Any]:
    """
    ChannelTalk Command (/foms) 파싱 및 응답 반환
    """
    if manager_id:
        from services.channel_identity import is_action_allowed_for_manager
        if not is_action_allowed_for_manager(manager_id, 'read_order'):
            return {
                "type": "text",
                "text": "❌ 권한이 없습니다. FOMS 계정 연동을 확인해주세요."
            }

    cmd_type, order_num = parse_foms_command(text)
    
    if not cmd_type or not order_num.isdigit():
        return {
            "result": {
                "type": "text",
                "text": "[안내] 사용 가능한 명령어:\n- /foms 주문 {번호}\n- /foms 일정 {번호}\n- /foms 담당 {번호}"
            }
        }
        
    if cmd_type == '주문':
        resp_text = get_order_summary_text(order_num)
    elif cmd_type == '일정':
        resp_text = get_order_schedule_text(order_num)
    elif cmd_type == '담당':
        resp_text = get_order_manager_text(order_num)
    else:
        resp_text = "[안내] 사용 가능한 명령어:\n- /foms 주문 {번호}\n- /foms 일정 {번호}\n- /foms 담당 {번호}"
        
    return {
        "result": {
            "type": "text",
            "text": resp_text
        }
    }

def get_order_summary_for_wam(order_id: int) -> dict:
    """WAM용 주문 요약 데이터 (Read-Only)"""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return None
        
    sd = _ensure_dict(order.structured_data)
    display_order = order
    if getattr(order, 'is_erp_beta', False) and sd:
        display_order = deepcopy(order)
        apply_erp_display_fields(display_order)

    if getattr(order, 'is_erp_beta', False):
        status_kr = _erp_get_stage(order, sd)
    else:
        status_kr = STATUS_MAP.get(display_order.status, display_order.status)
    
    return {
        'order_id': display_order.id,
        'customer_name': display_order.customer_name,
        'phone': display_order.phone,
        'address': display_order.address,
        'status_kr': status_kr,
        'product': display_order.product,
        'measurement_date': display_order.measurement_date or '-',
        'construction_date': display_order.scheduled_date or '-',
        'manager_name': display_order.manager_name or '-'
    }

def get_order_attachments_for_wam(order_id: int) -> list:
    """WAM용 첨부파일 URL 데이터"""
    db = get_db()
    attachments = db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id
    ).order_by(OrderAttachment.id.desc()).all()
    
    storage = get_storage()
    files = []
    for att in attachments:
        if att.storage_key:
            # WAM용 링크는 1시간 유효 Presigned URL 제공
            url = storage.get_download_url(att.storage_key, expires_in=3600)
            if url:
                files.append({
                    'id': att.id,
                    'name': att.filename,
                    'type': att.file_type,
                    'url': url,
                    'category': att.category
                })
    return files
