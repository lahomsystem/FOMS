"""도면방 채널톡 PUSH 본문 조립 (서버 SSOT).

도면방에는 **고객 이름 한 줄**만 나간다. 방을 보는 사람은 제작·시공이고 외부 협력사도
있어서, 발주방 본문에 실린 출고가·예약금·잔금 같은 금액이 이 방에 나가면 안 된다.
도면 자체가 규격·품목을 다 담고 있으므로 본문은 "어느 집 도면인가"만 말하면 된다.

조립기를 화면마다 두지 않고 서버가 단독으로 만든다 — 도면방 PUSH 는 워크벤치 상세와 도면
마법사 두 화면에서 발사되는데, 마법사에는 주문 폼 DOM(``#erp-*``)이 없어 클라이언트가 같은
본문을 만들 수 없다(:mod:`foms.services.channel_as_message` 선례와 같은 이유).
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_drawing_room_push_text"]


def build_drawing_room_push_text(order: Any) -> str:
    """도면방 PUSH 본문을 조립한다 — 고객 이름 한 줄.

    Args:
        order: 대상 주문.

    Returns:
        고객 이름. 이름이 비어 있으면 ``주문 #<id>``, 그것도 못 만들면 빈 문자열.
    """
    name = str(getattr(order, "customer_name", None) or "").strip()
    if name:
        return name
    order_id = getattr(order, "id", None)
    return f"주문 #{order_id}" if order_id else ""
