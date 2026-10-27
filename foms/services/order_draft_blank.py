"""마법사 초안 "빈 내용" 판정 (2026-10-26 설계서
docs/plans/2026-10-26-wizard-empty-draft-cleanup-spec.md §6).

마법사를 열었다 닫기만 해도 떠날 때 저장이 나가 아무것도 안 적힌 초안 행이 생겼다(운영 10-19
이후 약 3할, 홈 "작성 중" 띠에 "이름 아직 없음" 카드로 7일 동안 선다). 행을 만들 가치가 있는지는
"이름이 있나" 가 아니라 **값이 하나라도 있나** 로 본다 — 사진만·주소만 적은 초안도 진짜 작업이다.

판정이 틀릴 때는 **저장하는 쪽으로** 틀리게 짠다: 모르는 칸도 값이 있으면 값이고, 값으로 치지 않는
화면 기본값은 아래 네 가지뿐이다(늘리지 않는다).
"""

from __future__ import annotations

from typing import Any

__all__ = ["is_blank_draft_data"]

#: 1단계 발주사 숨은 기본값(``templates/orders/wizard/step1_basic.html``).
_DEFAULT_ORDERER = "라홈"
#: 2단계 제품 카드 글자 칸 기본값(``templates/orders/wizard/step2_products.html``).
_DEFAULT_ITEM_TEXT = "상담"
_ITEM_TEXT_DEFAULT_KEYS = frozenset({"internal", "color", "handle", "option_detail", "misc"})


def _is_zero_amount(value: Any) -> bool:
    """계약금 칸 기본값(빈 칸·"0"·"0원")인가. 숫자 아닌 글자가 섞이면 값으로 친다."""
    text = str(value if value is not None else "").replace(",", "").replace("원", "").strip()
    return text == "" or (text.isdigit() and int(text) == 0)


def _has_value(value: Any) -> bool:
    """기본값 예외 없이 값이 있는가(문자열 1자 이상·true·0 아닌 숫자·값 있는 하위 항목)."""
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_value(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_value(v) for v in value)
    return True  # 모르는 모양은 값으로 친다(저장하는 쪽으로 틀린다)


def _item_has_value(item: Any) -> bool:
    """제품 카드 1장에 값이 있는가. 글자 칸 기본값 "상담" 은 값이 아니다."""
    if not isinstance(item, dict):
        return _has_value(item)
    for key, value in item.items():
        if key in _ITEM_TEXT_DEFAULT_KEYS and isinstance(value, str) \
                and value.strip() == _DEFAULT_ITEM_TEXT:
            continue
        if _has_value(value):
            return True
    return False


def is_blank_draft_data(data: Any, *, today_kst: str) -> bool:
    """초안 ``payload.data`` 에 저장할 값이 하나도 없는가.

    Args:
        data: 마법사가 보낸 ``payload.data``.
        today_kst: 오늘 날짜 ``YYYY-MM-DD``(KST). 접수일 기본값 비교용.

    Returns:
        값이 하나도 없으면 True. 기본값(발주사 "라홈"·접수일 오늘·제품 글자 칸 "상담"·계약금 0)은
        값으로 치지 않는다.
    """
    if not isinstance(data, dict):
        return not _has_value(data)
    for key, value in data.items():
        if key == "orderer" and isinstance(value, str) and value.strip() == _DEFAULT_ORDERER:
            continue
        if key == "received_date" and isinstance(value, str) and value.strip() == today_kst:
            continue
        if key == "deposit" and _is_zero_amount(value):
            continue
        if key == "items" and isinstance(value, list):
            if any(_item_has_value(item) for item in value):
                return False
            continue
        if _has_value(value):
            return False
    return True
