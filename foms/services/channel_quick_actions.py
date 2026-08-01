"""
ChannelTalk quick actions service (Phase D).
- 읽기 전용 Quick Action: 명령어 처리 및 WAM 데이터 조회
- 주문 요약, 일정 요약, 담당 요약, 첨부파일 목록 조회 지원
"""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from foms.persistence.main.db import get_db
from foms.persistence.main.models import Order, OrderAttachment
from foms.services.channel_identity import get_user_by_manager_id
from foms.services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "RECEIVED": "접수",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
    "CS": "CS",
    "COMPLETED": "완료",
    "AS": "AS",
}

__all__ = [
    "STATUS_MAP",
    "parse_foms_command",
    "process_foms_command",
    "get_order_summary_for_wam",
    "get_order_attachments_for_wam",
]


def parse_foms_command(text: str) -> tuple[str, str]:
    """Parse a quick action command such as '주문 1234'."""
    parts = str(text).strip().split()
    if len(parts) >= 2:
        cmd_type = parts[0]
        order_num = parts[1]
        return cmd_type, order_num
    return "", ""


#: 사용 가능한 quick action 명령어(주문/일정/담당). 그 외는 사용법 안내.
_ORDER_COMMANDS = ("주문", "일정", "담당")

_USAGE_TEXT = (
    "[안내] 사용 가능한 명령어:\n"
    "- /foms 주문 {번호}\n"
    "- /foms 일정 {번호}\n"
    "- /foms 담당 {번호}"
)

#: 모든 deny/nonexistent 를 구분 없이 덮는 단일 no-data 문구.
#: 권한 거부·미매핑·비활성·DB 오류·미존재 주문을 서로 구별하지 않는다(존재 여부 미노출).
#: PII·raw exception·order id 를 절대 담지 않는다.
_NO_DATA_TEXT = "요청하신 정보를 조회할 수 없습니다. FOMS 계정 연동과 주문 조회 권한을 확인해주세요."


def _text_result(text: str) -> dict[str, Any]:
    """Channel Function domain result 봉투(``{"result": {"type":"text",...}}``)."""
    return {"result": {"type": "text", "text": text}}


def _no_data_result() -> dict[str, Any]:
    """존재 여부·PII 를 노출하지 않는 단일 no-data 도메인 결과(모든 deny 공통)."""
    return _text_result(_NO_DATA_TEXT)


def _load_readable_order(user: Any, order_num: str) -> Order | None:
    """resolve 된 User 가 canonical read scope 로 조회 가능한 active Order 를 로드한다.

    ``user`` 가 없거나(미인증/미매핑/비활성/DB 오류로 resolve 실패) read scope 가 없거나
    주문이 없으면 ``None``(deny) 을 반환한다. read scope 는 PII 를 만지기 **전에** 적용하며,
    DB fault 는 삼키지 않고 서버 로그에만 남긴다(호출자에게 raw exception 미노출).
    """
    if user is None:
        return None
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == int(order_num), Order.active_filter()).first()
    except Exception as e:  # DB fault → deny(존재 여부·raw exception 미노출)
        logger.error("[QuickAction] readable-order load failed: %s", e)
        return None
    if order is None or not user_can_read_order(user, order):
        return None
    return order


def _format_order_summary(order: Order) -> str:
    status_kr = STATUS_MAP.get(order.status, order.status)
    return (
        f"📦 주문 #{order.id} 요약\n"
        f"- 고객명: {order.customer_name or '-'}\n"
        f"- 연락처: {order.phone or '-'}\n"
        f"- 주소: {order.address or '-'}\n"
        f"- 현재 상태: {status_kr}\n"
        f"- 수주 제품: {order.product or '-'}"
    )


def _format_order_schedule(order: Order) -> str:
    sd = order.structured_data or {}
    sched = sd.get("schedule", {})
    recv = order.received_date or "-"
    measure = sched.get("measurement", {}).get("date", order.measurement_date or "-")
    const = sched.get("construction", {}).get("date", order.scheduled_date or "-")
    return (
        f"📅 주문 #{order.id} 일정 정보\n"
        f"- 접수일: {recv}\n"
        f"- 실측일: {measure}\n"
        f"- 시공일: {const}"
    )


def _format_order_manager(order: Order) -> str:
    sd = order.structured_data or {}
    shipment = sd.get("shipment", {})
    draw_managers = shipment.get("drawing_managers", [])
    draw_mgr_str = ", ".join(draw_managers) if draw_managers else shipment.get("drawing_manager", "-")
    const_workers = shipment.get("construction_workers", [])
    const_wkr_str = ", ".join(const_workers) if const_workers else "-"
    return (
        f"👤 주문 #{order.id} 담당자 정보\n"
        f"- 담당 매니저: {order.manager_name or '-'}\n"
        f"- 도면 담당자: {draw_mgr_str}\n"
        f"- 시공 담당자: {const_wkr_str}"
    )


_COMMAND_FORMATTERS = {
    "주문": _format_order_summary,
    "일정": _format_order_schedule,
    "담당": _format_order_manager,
}


def process_foms_command(text: str, manager_id: str | None = None) -> dict[str, Any]:
    """ChannelTalk ``/foms`` quick action 명령을 처리한다(read-only).

    PII(customer/phone/address/schedule/assignee) 를 만지기 전에 (1) manager id 를
    canonical active User 로 resolve 하고 (2) 일반 Order detail 과 동일한 read scope 를
    적용한다. manager id 누락은 allow 가 아니다(fail-open 제거). deny·미매핑·비활성·DB
    오류·미존재 주문은 모두 동일한 no-data 결과(PII 0, 존재 여부 미노출)를 반환하며, Order
    row/version/receipt 를 변경하지 않는다. 명령 형식 오류만 PII 없는 사용법 안내를 준다.

    Args:
        text: quick action 명령 문자열(예: ``"주문 1234"``).
        manager_id: ChannelTalk caller manager id(transport adapter 제공). ``None``/
            unmapped/비활성은 deny.

    Returns:
        Channel Function domain result(``{"result": {"type": "text", "text": ...}}``).
    """
    cmd_type, order_num = parse_foms_command(text)

    # 명령 형식 오류(PII·주문 데이터 없음) → 사용법 안내(pre-auth 허용).
    if cmd_type not in _ORDER_COMMANDS or not order_num.isdigit():
        return _text_result(_USAGE_TEXT)

    # 권한: manager id → canonical active User + Order read scope(PII 조회 전 적용).
    user = get_user_by_manager_id(manager_id) if manager_id else None
    order = _load_readable_order(user, order_num)
    if order is None:
        return _no_data_result()

    return _text_result(_COMMAND_FORMATTERS[cmd_type](order))


def get_order_summary_for_wam(order_id: int) -> dict[str, Any] | None:
    """Return a read-only summary payload for the WAM view."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return None

    sd = _ensure_dict(order.structured_data)
    display_order = order
    if is_erp_order_record(order) and sd:
        display_order = deepcopy(order)
        apply_erp_display_fields(display_order)

    if is_erp_order_record(order):
        status_kr = _erp_get_stage(order, sd)
    else:
        status_kr = STATUS_MAP.get(display_order.status, display_order.status)

    return {
        "order_id": display_order.id,
        "customer_name": display_order.customer_name,
        "phone": display_order.phone,
        "address": display_order.address,
        "status_kr": status_kr,
        "product": display_order.product,
        "measurement_date": display_order.measurement_date or "-",
        "construction_date": display_order.scheduled_date or "-",
        "manager_name": display_order.manager_name or "-",
    }


def get_order_attachments_for_wam(order_id: int) -> list[dict[str, Any]]:
    """Return attachment metadata with presigned URLs for the WAM view."""
    db = get_db()
    attachments = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).order_by(OrderAttachment.id.desc()).all()  # perf-ok: single-order attachments

    storage = get_storage()
    files: list[dict[str, Any]] = []
    for att in attachments:
        if att.storage_key:
            url = storage.get_download_url(att.storage_key, expires_in=3600)
            if url:
                files.append(
                    {
                        "id": att.id,
                        "name": att.filename,
                        "type": att.file_type,
                        "url": url,
                        "category": att.category,
                    }
                )
    return files
