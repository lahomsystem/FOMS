"""관리 패널 '바꿔 묻기 대응(온톨로지)' 칸 묶음 — 손님이 같은 뜻을 다른 말로 물어도 AI 가 답하게(사장님 11-11 '온톨로지화해야 다양한
변형에 대응').

운영 7일(11-11 무렵) '모름' 넘김 94건 가운데 69건을 직원이 바로 답했고, 보내기 전 검사의 '승인 안 된 숫자' 막힘이 67건이었다.
까닭 셋(:mod:`.ontology` 모듈 설명)마다 칸이 하나씩이고 처음 값은 모두 **끔**이다(끄면 예전 그대로).

- 숫자 같은 값: 숫자 검사가 같은 값을 알아본다(2주 = 2주일 = 14일 · 350mm = 35cm) · 손님이 말한 치수 · 개수는 되풀이해도 된다
  (금액 · 기간 · 날짜는 손님 글에서 가져오지 않는다 — D164).
- 다른 말 · 용어 · 규격 싣기: 회사 지식 표의 다른 이름과 지식 문서에 없는 용어 · 규격 · 절차 · 제품 라인 · 옵션 항목을 AI 에게 보여
  준다(그 글의 숫자도 승인 값).
- 같은 뜻이면 답하기: 지시문 8번을 '낱말이 달라도 뜻이 같으면 그 항목으로 답하고, 정말 없을 때만 넘긴다'로 바꾼다.
- 주문 확인해 답하기(설계서 2026-11-12 온톨로지 5.6 · D189 · D190): 손님 주문 자료가 있어야 답하는 문의일 때만 본인이 확인된
  ERP 주문 하나의 단계 · 날짜를 초안 재료에 싣는다(:mod:`.order_step`). 이 칸은 세 칸 묶음(:class:`OntoFlags`) 밖이다.
- 물건 찾아 따라가기(설계서 온톨로지 5절 · 5.0 · D196): 손님 글의 제품 · 옵션을 이름표로 찾아 걸린 규칙 id 를 차례 칸에
  싣는다(:mod:`.onto_find` · :mod:`.onto_block`). 다시 돌려 보기 뒤에 켜기를 묻는다.
- 뜻으로도 물건 찾기(D197 ②): 위 칸이 이름표로 아무것도 못 찾으면 가린 손님 글을 Voyage AI 벡터로 가까운 제품 · 옵션에
  잇는다(:mod:`.onto_meaning`). 가린 상담 글이 바깥으로 나가므로 처리방침 국외 이전 고침 · Voyage 학습 안 쓰기 뒤에 켠다.
- 뜻으로도 비슷한 상담 찾기(D197 ③): 지난 상담 고르기에 뜻이 가까운 사례를 섞는다(:mod:`.case_meaning`). 같은 조건.
:mod:`.settings` 가 이 모듈을 부르므로 여기서는 칸 꼴(:mod:`.settings_field`)만 가져온다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foms.services.cs_agent.settings_field import KIND_BOOL, Field

__all__ = [
    "GROUP_ONTO", "ONTO_CASES_FIELD", "ONTO_FIELDS", "ONTO_GRAPH_FIELD", "ONTO_LABELS_FIELD", "ONTO_MEANING_FIELD", "ONTO_NUMBERS_FIELD", "ONTO_OFF",
    "ONTO_ORDER_FIELD", "ONTO_PROMPT_FIELD", "OntoFlags", "onto_flags", "onto_graph_on", "onto_meaning_on", "order_lookup_on",
]

GROUP_ONTO = "바꿔 묻기 대응(온톨로지)"
ONTO_NUMBERS_FIELD = "onto_numbers_enabled"
ONTO_LABELS_FIELD = "onto_labels_enabled"
ONTO_PROMPT_FIELD = "onto_prompt_enabled"
ONTO_ORDER_FIELD = "onto_order_enabled"
ONTO_GRAPH_FIELD = "onto_graph_enabled"
ONTO_MEANING_FIELD = "onto_meaning_enabled"
ONTO_CASES_FIELD = "case_meaning_enabled"

ONTO_FIELDS: tuple[Field, ...] = (
    Field(ONTO_NUMBERS_FIELD, "숫자 같은 값 알아보기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 보내기 전 숫자 검사가 같은 값을 알아봐요(2주 = 2주일 = 14일, 350mm = 35cm). 손님이 말한 치수 · 개수는 "
               "초안이 되풀이해도 돼요. 금액 · 기간 · 날짜는 지금처럼 회사 지식에 있는 것만 써요"),
    Field(ONTO_LABELS_FIELD, "다른 말 · 용어 · 규격 싣기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 회사 지식 항목의 '다른 이름'과 용어 · 규격 · 절차 · 제품 라인 · 옵션 항목(보기 범위 모두 · 반영된 것)을 AI 가 "
               "같이 봐요. 손님이 다른 말로 물어도 같은 항목을 찾기 쉬워져요"),
    Field(ONTO_PROMPT_FIELD, "같은 뜻이면 답하기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 AI 지시문이 '낱말 · 단위 · 맞춤법이 달라도 뜻이 같으면 그 항목으로 답하고, 회사 지식에 정말 없을 때만 "
               "직원에게 넘긴다'로 바뀌어요. 끄면 예전처럼 '확실하지 않으면 넘긴다'예요"),
    Field(ONTO_ORDER_FIELD, "주문 확인해 답하기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 손님이 일정 · 접수 · 도면 · AS 처럼 그 손님 주문을 봐야 답할 것을 물을 때만, 본인이 확인된 주문 하나의 단계 · "
               "날짜를 ERP 에서 읽어 초안에 써요. 확인이 안 되면 성함과 휴대폰 번호를 한 번 묻고(톡톡은 묻지 않고 넘겨요), "
               "일정 바꾸기는 AI 가 하지 않고 담당자에게 넘겨요. 금액 · 주소 · 전화는 AI 에게 주지 않아요"),
    Field(ONTO_GRAPH_FIELD, "물건 찾아 따라가기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 손님 글에 나온 제품 · 옵션을 회사 지식 표에서 이름(다른 이름 포함)으로 찾아, 그 물건에 걸린 정책 · 가격 규칙 · "
               "규격을 AI 가 같이 봐요. 금액은 싣지 않아요. 다시 돌려 보기로 나아진 걸 확인한 뒤 켜요"),
    Field(ONTO_MEANING_FIELD, "뜻으로도 물건 찾기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 '물건 찾아 따라가기'가 이름으로 아무것도 못 찾았을 때, 개인정보를 가린 손님 글을 Voyage AI 로 보내 뜻이 "
               "가까운 제품 · 옵션을 찾아요. 켜기 전에 개인정보 처리방침의 '국외 이전'에 Voyage AI(가린 상담 글)를 올리고 Voyage "
               "에서 '학습에 쓰지 않기'를 켜야 해요. 회사 지식 물어보기 설정의 '의미 찾기'와 그 하루 돈 상한도 켜져 있어야 해요"),
    Field(ONTO_CASES_FIELD, "뜻으로도 비슷한 상담 찾기", KIND_BOOL, False, GROUP_ONTO,
          help="켜면 AI 가 참고할 지난 상담을 고를 때 글자가 비슷한 것에 더해, 개인정보를 가린 손님 글을 Voyage AI 로 보내 뜻이 "
               "가까운 지난 상담도 같이 골라요. 회사 지식 물어보기 설정의 '의미 찾기' · 하루 돈 상한 · '상담 사례 벡터'가 켜져 "
               "있고 지난 상담 벡터를 채운 뒤에 효과가 있어요"),
)


@dataclass(frozen=True)
class OntoFlags:
    """세 칸의 지금 값."""

    numbers: bool = False
    labels: bool = False
    prompt: bool = False

    @property
    def any(self) -> bool:
        return self.numbers or self.labels or self.prompt


ONTO_OFF = OntoFlags()


def onto_flags(cfg: Any) -> OntoFlags:
    """설정 → 세 칸(참일 때만 켬)."""
    return OntoFlags(numbers=cfg.get(ONTO_NUMBERS_FIELD) is True, labels=cfg.get(ONTO_LABELS_FIELD) is True,
                     prompt=cfg.get(ONTO_PROMPT_FIELD) is True)


def order_lookup_on(cfg: Any) -> bool:
    """'주문 확인해 답하기' 칸이 켜졌나(참일 때만)."""
    return cfg.get(ONTO_ORDER_FIELD) is True


def onto_graph_on(cfg: Any) -> bool:
    """'물건 찾아 따라가기' 칸이 켜졌나(참일 때만)."""
    return cfg.get(ONTO_GRAPH_FIELD) is True


def onto_meaning_on(cfg: Any) -> bool:
    """'뜻으로도 물건 찾기' 칸이 켜졌나(참일 때만)."""
    return cfg.get(ONTO_MEANING_FIELD) is True
