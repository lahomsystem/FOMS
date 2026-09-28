"""실측 모바일 카드의 현장 메모 — 실측 가기 전에 꼭 볼 특이사항 5종을 한 번에 모은다.

출처(저장 위치):
- 주소·연락처·실측 특이사항: ERP 편집 ``structured_data['notes']`` 의 ``address_note`` ·
  ``phone_note`` · ``measurement_note``. 마법사·옛 주문은 ``notes`` 가 **문자열**이라
  dict 일 때만 읽는다(channel_measure_message._notes_map 과 같은 규칙).
- 비고: ``Order.notes`` 컬럼(마법사 비고칸·ERP 편집 비고가 같이 쓴다).
- 고객 요청: 네이버 주문 배송메모 ``structured_data['naver']['shipping_memo']``.

추가 조회는 없다 — 이미 읽은 주문 행만 쓴다.
"""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_site_memo(order: Any) -> dict[str, Any]:
    """카드 행에 합칠 키: ``site_memo``(5종 문자열) 와 ``site_memo_count``(빈 칸 제외 개수)."""
    sd = getattr(order, "structured_data", None) or {}
    notes = sd.get("notes") if isinstance(sd, dict) else None
    notes = notes if isinstance(notes, dict) else {}
    naver = sd.get("naver") if isinstance(sd, dict) else None
    naver = naver if isinstance(naver, dict) else {}
    memo = {
        "address": _text(notes.get("address_note")),
        "phone": _text(notes.get("phone_note")),
        "measure": _text(notes.get("measurement_note")),
        "notes": _text(getattr(order, "notes", None)),
        "request": _text(naver.get("shipping_memo")),
    }
    return {"site_memo": memo, "site_memo_count": sum(1 for v in memo.values() if v)}
