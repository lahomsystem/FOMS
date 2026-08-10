"""AS 채널톡 PUSH 본문 조립 (서버 SSOT).

AS PUSH 본문은 두 화면에서 발사된다 — ERP 주문수정 탭과 AS 대시보드 첨부 모달.
AS 대시보드에는 주문 폼 DOM 이 없으므로 본문을 클라이언트가 만들 수 없고, 화면마다
다른 조립기를 두면 같은 주문이 화면에 따라 다른 문구로 나가는 드리프트가 난다.
그래서 조립은 저장된 주문(Order + structured_data) 기준으로 서버가 단독 수행한다.

포맷(요청 사양 그대로)::

    고객명 : 홍길동
    발주사 : 숨고
    시공일 : 8월 14일
    주  소 : 경남 창원시 ...
    연락처 : 010-0000-0000

    내용 : (AS 모달에서 접수한 최신 내용)
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["build_as_push_text", "format_schedule_date_korean"]

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DEFAULT_ORDERER = "라홈"
_NO_CONSTRUCTION_DATE = "상담"


def format_schedule_date_korean(value: Any) -> str:
    """ISO 날짜를 변환 텍스트와 같은 한글 표기로 바꾼다.

    콤마로 이어진 다중 일정도 각 항목을 개별 변환한다(예: ``2026-08-14,2026-08-15``
    → ``8월 14일, 8월 15일``). ISO 형태가 아니면 원문을 그대로 돌려준다 —
    사용자가 직접 적은 자유 문구(예: ``미정``)를 지우지 않기 위해서다.

    Args:
        value: ``YYYY-MM-DD`` 또는 콤마로 이어진 날짜 문자열.

    Returns:
        ``8월 14일`` 형태의 표시 문자열(빈 입력이면 빈 문자열).
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts: list[str] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        match = _ISO_DATE_RE.match(token)
        parts.append(f"{int(match.group(2))}월 {int(match.group(3))}일" if match else token)
    return ", ".join(parts) if parts else raw


def _append_line(text: str, label: str, value: Any) -> str:
    """``label : value`` 한 줄을 덧붙인다(값이 비면 줄 자체를 생략).

    여러 줄 값은 첫 줄만 라벨을 달고 나머지는 이어 붙인다 — ERP 변환 텍스트
    (``erpAppendConversionTextLine``)와 같은 규칙이라 두 경로의 표기가 어긋나지 않는다.

    Args:
        text: 지금까지 조립된 본문.
        label: 줄 라벨(예: ``고객명``).
        value: 표시 값.

    Returns:
        줄이 덧붙은 본문.
    """
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return text
    lines = normalized.split("\n")
    out = f"{text}{label} : {lines[0].strip()}\n"
    for line in lines[1:]:
        stripped = line.strip()
        if stripped:
            out += f"{stripped}\n"
    return out


def _dict_at(container: Any, *keys: str) -> dict:
    """중첩 dict 를 안전하게 따라간다(중간이 dict 가 아니면 빈 dict)."""
    node = container if isinstance(container, dict) else {}
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return {}
    return node


def build_as_push_text(order: Any) -> str:
    """저장된 주문으로 AS PUSH 본문을 조립한다.

    값은 ``structured_data`` 를 우선하고, 비어 있으면 평면 컬럼(Order.customer_name 등)
    으로 폴백한다 — 구버전/부분 저장 주문에서도 식별 정보가 비지 않게 하기 위해서다.
    본문의 핵심인 AS 접수 내용은 ``structured_data.shipment.as_content`` 하나만 본다
    (append-only ``as_log`` 는 이력 화면 소관이며, PUSH 는 최신 접수 내용만 보낸다).

    Args:
        order: 대상 ``Order`` (structured_data 포함).

    Returns:
        전송 본문. **AS 접수 내용이 없으면 빈 문자열** — 호출자는 이를 전송 거부
        신호로 쓴다(내용 없는 AS 알림은 받는 쪽에 무의미하므로).
    """
    sd = order.structured_data if isinstance(getattr(order, "structured_data", None), dict) else {}

    as_content = str(_dict_at(sd, "shipment").get("as_content") or "").strip()
    if not as_content:
        return ""

    parties = _dict_at(sd, "parties")
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    orderer = parties.get("orderer") if isinstance(parties.get("orderer"), dict) else {}
    site = _dict_at(sd, "site")
    construction = _dict_at(sd, "schedule", "construction")

    customer_name = str(customer.get("name") or "").strip() or (getattr(order, "customer_name", "") or "")
    orderer_name = str(orderer.get("name") or "").strip() or _DEFAULT_ORDERER
    phone = str(customer.get("phone") or "").strip() or (getattr(order, "phone", "") or "")
    address = (
        str(site.get("address_full") or site.get("address_main") or "").strip()
        or (getattr(order, "address", "") or "")
    )
    construction_date = (
        str(construction.get("date") or "").strip()
        or str(getattr(order, "erp_construction_date", "") or "").strip()
    )
    construction_label = format_schedule_date_korean(construction_date) or _NO_CONSTRUCTION_DATE

    text = ""
    text = _append_line(text, "고객명", customer_name)
    text = _append_line(text, "발주사", orderer_name)
    text = _append_line(text, "시공일", construction_label)
    text = _append_line(text, "주  소", address)
    text = _append_line(text, "연락처", phone)
    if text:
        text += "\n"
    text = _append_line(text, "내용", as_content)
    return text.strip()
