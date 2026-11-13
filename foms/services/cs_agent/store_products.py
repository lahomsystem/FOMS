"""스토어 상품 → 계산기 제품 정해 둔 짝(사장님 11-13 확인) — 톡톡 '상품 문의' 줄(:mod:`.drafting_read`)의 상품 이름으로 견적 계산
제품을 짐작 없이 정한다(:mod:`.quote_step`).

- **짝이 계산기 제품 id**: 견적 뽑기에는 상품 문의 줄을 빼고 넘긴다(모델이 상품 이름으로 다른 제품을 짐작하지 않게). 손님 글이
  다른 제품을 말한 공간은 그대로 두고, 제품이 빈 공간만 이 id 로 채운다. 공간이 하나도 없으면 이 제품 공간 하나를 만든다.
- **짝이 ``None``**(계산기에 없는 상품 — 사장님 '계산 없이 직원에게'): 손님 글이 다른 제품을 말하지 않았으면 초안 없이 직원에게
  (:data:`HUMAN_STORE_PRODUCT`).
- **화장대가 든 상품**(:data:`STORE_OPTIONS` — 사장님 11-13 '01타입 견적가 포함이 기본, 손님께 01타입 기본으로 안내'): 채운
  공간에 화장대 TYPE01 하나를 더하고(누드 거울은 화장대 값에 들어 있다), 두뇌 재료에 안내 한 줄(:data:`VANITY_LINE`) · 검사
  허용 글(:data:`VANITY_ALLOWED` — 초안의 '01타입'이 숫자 검사에 막히지 않게)을 붙인다. 계산기에 그 옵션이 없으면 짝을 쓰지
  않는다(화장대가 빠진 금액이 나가지 않게).
- **표에 없는 상품**(새 상품 · 이름이 바뀐 상품 · 옵션 상품): 예전 그대로 — 뽑기가 상품 문의 줄을 보고 고른다.

이름은 지난 라홈 상담의 톡톡 상품 문의 줄 그대로(빈칸은 하나로 접어 맞춘다). 상품 번호는 싣지 않는다 — 짝은 이름으로만 찾는다.
계산기에 그 id 가 없으면(제품을 지웠으면) 짝을 쓰지 않는다.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Sequence

from foms.services.cs_agent.brain_prompt import ROLE_STORE
from foms.services.cs_agent.quote_brain import QuoteAsk, QuoteSpace, option_ids

__all__ = ["HUMAN_STORE_PRODUCT", "STORE_OPTIONS", "STORE_PRODUCTS", "VANITY_ALLOWED", "VANITY_LINE", "StoreChoice",
           "apply_choice", "store_choice", "with_guide", "without_store"]

#: 사람에게 넘기는 까닭 코드 — 계산기에 없는 스토어 상품의 견적 문의(차례 기록 ``error_code``).
HUMAN_STORE_PRODUCT = "quote_store_product"

_MOLDING_PUSH, _NO_MOLDING_PUSH, _BOTTEGA, _LED_SLIDING = 2, 5, 7, 24
_FRIDGE_NEW, _FRIDGE_REFORM, _HABAN, _MONTA_U, _MONTA_L = 13, 26, 10, 11, 12
_LIRA, _LINDA, _IRIS, _MONET, _ARA_ONE, _ARA_WOOD_ONE = 15, 16, 29, 30, 33, 35

#: 스토어 상품 이름 → 계산기 라홈 제품 id(``None`` = 계산기에 없음 · 직원에게). 사장님 11-13: 이름에 '무몰딩'이 없는 로라는
#: 몰딩(푸쉬), 아라 · 아라 우드는 원도어, 다른 슬라이딩 · 여닫이 스윙 시리즈는 계산 없이 직원에게. 짝을 정하지 못한
#: 여섯(라운드 냉장고장 · 제나 책장 · 큐브 벙커침대 · 루미 도장 · 카보 키친 · 노바 LED)도 직원에게(틀린 금액을 막는 쪽).
STORE_PRODUCTS: dict[str, Optional[int]] = {
    "라홈 무몰딩 붙박이장 로라 시리즈 30cm 푸쉬타입 친환경 E0": _NO_MOLDING_PUSH,
    "라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 180cm": _NO_MOLDING_PUSH,
    "라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 150cm": _NO_MOLDING_PUSH,
    "라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 240cm": _NO_MOLDING_PUSH,
    "라홈 로라 무몰딩 붙박이장 안방 여닫이 30cm 푸쉬타입 친환경 E0": _NO_MOLDING_PUSH,
    "라홈 로라 붙박이장 안방 여닫이 푸쉬타입 30cm": _MOLDING_PUSH,
    "라홈 보테가 붙박이장 작은방 안방 슬라이딩 미닫이 30cm": _BOTTEGA,
    "라홈 보테가 붙박이장 작은방 슬라이딩 240cm": _BOTTEGA,
    "라홈 보테가 붙박이장 작은방 슬라이딩 240cm 수납": _BOTTEGA,
    "라홈 보테가 붙박이장 작은방 슬라이딩 240cm 옷장": _BOTTEGA,
    "라홈 이모션 LED 슬라이딩 붙박이장 30cm": _LED_SLIDING,
    "라홈 빌트인 키친핏 냉장고장 리폼 홈카페장 맞춤 제작 시공": _FRIDGE_REFORM,
    "라홈 빌트인 키친핏 냉장고장 1800mm 이하 신규제작 홈카페장 맞춤 제작 시공": _FRIDGE_NEW,
    "라홈 하반 빌트인 침대 안방 무몰딩 붙박이장 30cm 친환경 E0": _HABAN,
    "몬타 ㄱ자 코너 커스텀 붙박이장 드레스룸 친환경 E0": _MONTA_L,
    "몬타 ㄷ자 코너 커스텀 붙박이장 드레스룸 친환경 E0": _MONTA_U,
    "리라 TV 월플렉스 거실 티비장 장식장 친환경 E0": _LIRA,
    "라홈 린다 TV 월플렉스 거실 붙박이장 30cm": _LINDA,
    "라홈 이리스 도장 친환경 무광 붙박이장 30cm": _IRIS,
    "라홈 자녀방 커스텀 책상 책장 가구 친환경 E0": _MONET,
    "라홈 모네 자녀방 커스텀 책상 책장 가구 친환경 E0": _MONET,
    "라홈 무몰딩 붙박이장 아라 시리즈 30cm 친환경 E0": _ARA_ONE,
    "라홈 무몰딩 붙박이장 아라 시리즈 30cm 푸쉬타입 친환경 E0": _ARA_ONE,
    "라홈 무몰딩 붙박이장 아라 우드 투톤 시리즈 30cm 푸쉬타입 친환경 E0": _ARA_WOOD_ONE,
    **dict.fromkeys((
        "라홈 소프트 1000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 체르티 1000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 체르티 3000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 그라시아 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 바흐 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 루나 3000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 루나 4000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 수피아 2000 붙박이장 안방 작은방 슬라이딩 240cm",
        "라홈 심플 붙박이장 여닫이 스윙 안방 작은방 240cm",
        "라홈 카이엔 1000 붙박이장 여닫이 스윙 안방 작은방 240cm",
        "라홈 카이엔 2000 붙박이장 여닫이 스윙 안방 작은방 240cm",
        "라홈 모카 붙박이장 여닫이 스윙 안방 작은방 240cm",
        # 아래 여섯은 계산기에 맞는 제품을 정하지 못했다(사장님 11-13 '고르기 없음') — 틀린 금액이 나가지 않게 직원에게.
        "라홈 라운드 냉장고장 빌트인 홈카페 키친핏 프리스탠딩 E0",
        "라홈 제나 커스텀 책장 도어형 매거진 서재 인테리어",
        "라홈 큐브 벙커침대 아이방 맞춤 수납 계단형 붙박이장 침대프레임 E0",
        "라홈 루미 도장 친환경 무광 붙박이장 30cm",
        "라홈 카보 키친 싱크대 부엌 주방 상하부장 E0",
        "라홈 노바 LED 조명 시스템장 드레스룸 시스템옷장 맞춤제작 30cm",
    ), None),
    # 화장대가 든 상품 — 제품은 위 규칙대로(무몰딩 말이 없는 로라 = 몰딩(푸쉬)), 화장대는 STORE_OPTIONS 로 더한다.
    "라홈 로라 붙박이장 무몰딩 화장대 작은방 여닫이 150cm 푸쉬타입 친환경 E0": _NO_MOLDING_PUSH,
    "라홈 로라 붙박이장 화장대 포함 누드 거울 작은방 여닫이 150cm 푸쉬타입 친환경 E0": _MOLDING_PUSH,
    "라홈 보테가 붙박이장 작은방 슬라이딩 화장대 포함 누드거울 240cm 친환경 E0": _BOTTEGA,
}

#: 화장대 TYPE01 하나(계산기 옵션 id ``카테고리id:옵션id`` — 화장대 > TYPE01).
_VANITY_TYPE01: tuple[tuple[str, int], ...] = (("1:1", 1),)
#: 스토어 상품 이름 → 채운 공간에 더할 계산기 옵션(사장님 11-13 — 01타입이 견적가 포함 기본, 누드 거울은 화장대 값에 들어 있음).
STORE_OPTIONS: dict[str, tuple[tuple[str, int], ...]] = {
    "라홈 로라 붙박이장 무몰딩 화장대 작은방 여닫이 150cm 푸쉬타입 친환경 E0": _VANITY_TYPE01,
    "라홈 로라 붙박이장 화장대 포함 누드 거울 작은방 여닫이 150cm 푸쉬타입 친환경 E0": _VANITY_TYPE01,
    "라홈 보테가 붙박이장 작은방 슬라이딩 화장대 포함 누드거울 240cm 친환경 E0": _VANITY_TYPE01,
}
#: 화장대 상품 두뇌 재료 한 줄(금액 없음) · 숫자 검사 허용 글.
VANITY_LINE = ("스토어 상품에 화장대가 들어 있다 — 견적에 화장대 01타입(TYPE01)을 기본으로 넣었다(누드 거울은 화장대 값에 들어 "
               "있다). 손님께 화장대는 01타입 기본으로 안내드린다고 쓴다.")
VANITY_ALLOWED = "화장대 01타입(TYPE01)"


@dataclasses.dataclass(frozen=True)
class StoreChoice:
    """정해 둔 짝 — 상품 이름 · 계산기 제품 id(계산기 목록의 값 그대로, ``None`` = 계산기에 없음 · 직원에게) · 더할 옵션 ·
    두뇌 재료 줄 · 검사 허용 글."""

    name: str
    product_id: Any
    options: tuple[tuple[str, int], ...] = ()
    lines: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()


def _norm(name: str) -> str:
    return " ".join(str(name).split())


_BY_NAME = {_norm(name): product_id for name, product_id in STORE_PRODUCTS.items()}
_OPTIONS_BY_NAME = {_norm(name): options for name, options in STORE_OPTIONS.items()}


def store_choice(messages: Sequence[tuple[str, str]], catalog: Any) -> Optional[StoreChoice]:
    """상담 글의 마지막 상품 문의 줄 → 정해 둔 짝. 표에 없거나, 짝 id · 더할 옵션이 계산기에 없으면 ``None``(예전 그대로)."""
    name = next((text for role, text in reversed(list(messages)) if role == ROLE_STORE), None)
    if name is None or _norm(name) not in _BY_NAME:
        return None
    key = _norm(name)
    wanted = _BY_NAME[key]
    if wanted is None:
        return StoreChoice(key, None)
    found = next((p.get("id") for p in catalog.products_of() if str(p.get("id")) == str(wanted)), None)
    options = _OPTIONS_BY_NAME.get(key, ())
    if found is None or not {ref for ref, _ in options} <= set(option_ids(catalog)):
        return None  # 제품이나 옵션을 지웠으면 짝을 쓰지 않는다(빠진 금액이 나가지 않게)
    guide = (VANITY_LINE,) if options else ()
    return StoreChoice(key, found, options, guide, (VANITY_ALLOWED,) if options else ())  # id 는 계산기 목록 그대로


def with_guide(step: Any, choice: Optional[StoreChoice]) -> Any:
    """견적 결과에 짝의 두뇌 재료 줄 · 허용 글을 붙인다(사람에게 넘기는 결과 · 짝 줄이 없으면 그대로)."""
    if choice is None or not choice.lines or step.human is not None:
        return step
    return dataclasses.replace(step, lines=(*step.lines, *choice.lines), allowed=(*step.allowed, *choice.allowed))


def without_store(messages: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """상품 문의 줄을 뺀 상담 글(뽑기가 상품 이름으로 짐작하지 않게 — 짝이 있을 때만 부른다)."""
    return tuple((role, text) for role, text in messages if role != ROLE_STORE)


def apply_choice(ask: QuoteAsk, choice: StoreChoice) -> tuple[QuoteAsk, bool]:
    """뽑은 견적 재료에 짝을 넣는다 → (고친 재료, 직원에게 넘기나).

    손님 글이 제품을 말한 공간은 그대로다. 짝이 ``None`` 이면 제품을 말한 공간이 하나도 없을 때만 직원에게 넘긴다.
    """
    named = any(space.product_ids for space in ask.spaces)
    if choice.product_id is None:
        return ask, not named

    def filled(space: QuoteSpace) -> QuoteSpace:
        have = {ref for ref, _ in space.options}
        extra = tuple(option for option in choice.options if option[0] not in have)
        return dataclasses.replace(space, product_ids=(choice.product_id,), options=(*space.options, *extra))

    spaces = tuple(space if space.product_ids else filled(space) for space in ask.spaces)
    if not spaces:
        spaces = (filled(QuoteSpace(space="기타", product_ids=(), width_mm=0, width_max_mm=0, height_mm=0,
                                    door="unknown", handle="unknown")),)
    unknown = tuple(name for name in ask.unknown if name != "product")
    return dataclasses.replace(ask, spaces=spaces, unknown=unknown), False
