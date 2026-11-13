"""능력 질문(Competency Questions) — 온톨로지 시험지(설계서 2026-11-12 온톨로지 2.5 · 부록 A · 사장님 D184).

지난 상담의 가린 질문을 묶어 일반화한 질문만 둔다(원문 · 예시 · 개수는 저장소 밖 학습 폴더). 질문마다 영역 · 주된 답 근거 ·
답에 필요한 물건 종류(자주 쓰인 앞 넷) · 연결 종류(앞 셋). ``erp:`` 는 회사 지식 표가 아니라 ERP 를 읽기만 하는 운영 물건
(설계서 5.5 — 승인 대기)이다. 온톨로지 탭(:mod:`.ontology_view`)이 이 목록으로 "답 재료가 있나"를 센다.

**연결 요구 고침(2026-11-13 · 사장님 D204 — 설계서 2026-11-13 빈 재료 채우기 3절 F)**: ``part_of`` 는 그림 조각 종류(도면 층) →
제품 라인만, ``uses`` 는 상담 · 도면 층 항목 → 공통 바탕만 이을 수 있다(:data:`.constants.ALLOWED_LINKS`). 그런데 '구성 · 포함'을 묻는
상담 질문이 ``part_of`` 를, 계산기로 답하는 질문이 ``uses`` 를 요구해 상담 층에서는 그 질문의 뜻으로 채울 길이 없었다. 지금 틀의
말로 고쳤다 — '기본 포함'은 옵션의 값 방식 칸(``price_kind``), '구성'은 ``applies_to``. 시험지를 몰래 쉽게 만들지 않게 고치기 전
요구를 :data:`LINKS_BEFORE_D204` 에 그대로 남긴다(바뀐 것은 이 두 연결뿐 — 시험이 강제).
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["CQ", "CQS", "D204_DROPPED", "ERP_NEEDS", "LINKS_BEFORE_D204"]

#: D204 가 질문 요구에서 뺀 연결 — 상담 질문의 뜻으로는 채울 길이 없는 둘.
D204_DROPPED: frozenset[str] = frozenset({"part_of", "uses"})
#: D204 고치기 전 연결 요구(질문 번호 → 연결 종류). 지금 요구는 아래 :data:`CQS`.
LINKS_BEFORE_D204: dict[str, tuple[str, ...]] = {
    "E01": ("applies_to", "value_from", "uses"), "E03": ("applies_to", "requires", "part_of"),
    "E05": ("part_of", "applies_to", "broader"), "E06": ("applies_to", "part_of", "excludes"),
    "E13": ("broader", "part_of"), "O02": ("part_of", "applies_to", "value_from"),
    "O05": ("applies_to", "part_of", "value_from"), "O08": ("applies_to", "part_of", "value_from"),
    "P02": ("value_from", "applies_to", "uses"), "P03": ("at_step", "requires", "part_of"),
    "P05": ("at_step", "requires", "part_of"), "A04": ("part_of",),
}

#: ERP 운영 물건(아직 없음 — 설계서 5.5).
ERP_NEEDS: dict[str, str] = {"erp:order": "주문(ERP)", "erp:schedule": "일정(ERP)"}


class CQ(NamedTuple):
    """능력 질문 하나."""

    cq_id: str
    domain: str
    question: str
    basis: str
    needs: tuple[str, ...]
    links: tuple[str, ...]


CQS: tuple[CQ, ...] = (
    CQ("E01", "견적·제품", "<제품>을 <치수>·<구성>으로 하면 견적이 얼마인가요?",
       "calculator", ("product_line", "spec", "option", "price_rule"), ("applies_to", "value_from")),
    CQ("E02", "견적·제품", "<사진·도면·참고 이미지>처럼 만들면 견적이 얼마이고 제작이 되나요?",
       "photo", ("product_line", "option", "build_rule", "price_rule"), ("applies_to", "requires", "value_from")),
    CQ("E03", "견적·제품", "여러 공간·여러 제품·여러 현장을 한꺼번에 견적·주문할 수 있나요?",
       "calculator", ("price_rule", "policy", "process_step", "product_line"), ("applies_to", "requires")),
    CQ("E04", "견적·제품", "<구성·옵션·자재>를 바꾸거나 빼면 금액이 어떻게 달라지나요?",
       "calculator", ("option", "price_rule", "product_line", "erp:order"), ("applies_to", "value_from", "excludes")),
    CQ("E05", "견적·제품", "제가 받은 견적서의 <항목>이 무슨 뜻이고 맞나요, 견적은 언제 받나요?",
       "order_data", ("term", "erp:order", "product_line", "price_rule"), ("applies_to", "broader")),
    CQ("E06", "견적·제품", "견적가에 시공비·VAT·운임·부속이 포함인가요?",
       "rule", ("price_rule", "policy", "term", "option"), ("applies_to", "excludes")),
    CQ("E07", "견적·제품", "견적을 받으려면 무엇을 보내야 하나요, 실측 없이 대략 견적이 되나요?",
       "rule", ("process_step", "policy", "term", "product_line"), ("at_step", "requires", "value_from")),
    CQ("E08", "견적·제품", "가격은 어떤 단위(자·통·30cm·1cm)로 산정되고 <치수>면 몇 통·몇 도어인가요?",
       "rule", ("price_rule", "term", "build_rule", "product_line"), ("applies_to", "value_from")),
    CQ("E09", "견적·제품", "할인·이벤트·공동구매·리뷰 적립이 있나요, 가격이 바뀌었나요?",
       "rule", ("policy", "price_rule", "fact", "owner_decision"), ("applies_to", "excludes")),
    CQ("E10", "견적·제품", "시공 사례·샘플·쇼룸을 볼 수 있나요?",
       "rule", ("fact", "product_line", "process_step", "option"), ("applies_to", "at_step")),
    CQ("E11", "견적·제품", "<다른 품목·다른 공정>도 만들거나 해 주나요?",
       "rule", ("fact", "policy", "product_line"), ("excludes", "broader", "applies_to")),
    CQ("E12", "견적·제품", "기존 가구를 리폼·도어 교체·개조할 수 있나요?",
       "rule", ("build_rule", "policy", "product_line", "situation"), ("excludes", "requires", "applies_to")),
    CQ("E13", "견적·제품", "<제품 A>와 <제품 B>는 무엇이 다른가요?",
       "rule", ("product_line", "option", "term"), ("broader", "applies_to")),
    CQ("E14", "견적·제품", "우리 공간에는 어떤 구성·배치가 좋을까요(추천)?",
       "human_judgment", ("option", "build_rule", "owner_decision", "situation"), ("applies_to", "excludes", "requires")),
    CQ("O01", "옵션·규격", "<옵션>을 더하면 추가 비용이 얼마이고 목록은 어디서 보나요?",
       "calculator", ("option", "price_rule", "product_line", "build_rule"), ("applies_to", "value_from", "requires")),
    CQ("O02", "옵션·규격", "기본 견적·기본 구성에 무엇이 포함되나요?",
       "rule", ("option", "product_line", "price_rule", "spec"), ("applies_to", "value_from")),
    CQ("O03", "옵션·규격", "<제품>을 원하는 크기·내부 구성·특수 구성으로 맞춤 제작할 수 있나요?",
       "rule", ("build_rule", "option", "spec", "product_line"), ("applies_to", "requires", "excludes")),
    CQ("O04", "옵션·규격", "<문 방식>과 <옵션·형태>를 같이 할 수 있나요?",
       "rule", ("build_rule", "option", "product_line", "price_rule"), ("excludes", "requires", "applies_to")),
    CQ("O05", "옵션·규격", "ㄱ자·ㄷ자 코너는 어떻게 구성되고 활용되나요?",
       "rule", ("build_rule", "spec", "product_line", "option"), ("applies_to", "value_from")),
    CQ("O06", "옵션·규격", "<천장 단내림·스프링클러·보·커튼박스> 같은 공간 조건에서도 설치되나요?",
       "photo", ("build_rule", "situation", "price_rule", "spec"), ("applies_to", "requires", "excludes")),
    CQ("O07", "옵션·규격", "천장 높이 <치수>에서 무몰딩이 되나요, 몰딩·마감판 폭은?",
       "rule", ("build_rule", "spec", "term", "option"), ("applies_to", "requires", "excludes")),
    CQ("O08", "옵션·규격", "<제품>의 사양(두께·깊이·높이·자재 등급·경첩)은 어떻게 되나요?",
       "rule", ("spec", "product_line", "term", "fact"), ("applies_to", "value_from")),
    CQ("O09", "옵션·규격", "표준보다 작거나 큰 <치수>도 제작되고 추가 비용이 있나요?",
       "rule", ("spec", "build_rule", "price_rule", "product_line"), ("applies_to", "value_from", "excludes")),
    CQ("O10", "옵션·규격", "색상·자재·손잡이는 무엇을 고를 수 있나요?",
       "rule", ("option", "process_step", "product_line", "spec"), ("applies_to", "at_step", "broader")),
    CQ("O11", "옵션·규격", "제 가구의 색상(자재 회사·번호)은 무엇이었나요?",
       "order_data", ("option", "fact", "erp:order"), ("value_from",)),
    CQ("O12", "옵션·규격", "콘센트·조명·스위치를 넣거나 옮길 수 있나요?",
       "rule", ("build_rule", "option", "price_rule", "situation"), ("requires", "applies_to")),
    CQ("O13", "옵션·규격", "치수는 어디서부터 어떻게 재서 알려 드리나요?",
       "rule", ("process_step", "spec"), ("at_step", "requires")),
    CQ("P01", "주문·결제", "주문·실측 예약은 어디서 어떤 순서로 하나요?",
       "rule", ("process_step", "policy", "term", "product_line"), ("at_step", "requires", "applies_to")),
    CQ("P02", "주문·결제", "스토어에서 <치수>면 어떤 단위 상품을 몇 개 주문하나요?",
       "calculator", ("price_rule", "process_step", "option", "build_rule"), ("value_from", "applies_to")),
    CQ("P03", "주문·결제", "예약금을 넣고 정보를 보냈는데 접수됐나요?",
       "order_data", ("erp:order", "erp:schedule", "process_step", "policy"), ("at_step", "requires")),
    CQ("P04", "주문·결제", "결제 수단·계좌·카드·현금영수증은 어떻게 되나요?",
       "rule", ("policy", "price_rule", "process_step", "term"), ("applies_to", "at_step")),
    CQ("P05", "주문·결제", "예약금·잔금은 언제 내고 예약금은 잔금에서 빠지나요?",
       "rule", ("policy", "process_step", "term"), ("at_step", "requires")),
    CQ("P06", "주문·결제", "예약 뒤 실측 때 구성·옵션을 바꾸거나 정해도 되나요?",
       "rule", ("policy", "process_step", "option"), ("at_step", "applies_to")),
    CQ("P07", "주문·결제", "실측 뒤 금액이 바뀌면 차액은 어떻게 하나요?",
       "rule", ("policy", "process_step", "price_rule", "erp:order"), ("at_step", "value_from")),
    CQ("P08", "주문·결제", "취소하면 환불되나요, 실측비가 드나요?",
       "rule", ("policy", "price_rule", "process_step", "erp:order"), ("applies_to", "at_step")),
    CQ("P09", "주문·결제", "제 주문 정보·결제 상태를 확인하거나 바꿀 수 있나요?",
       "order_data", ("erp:order",), ("applies_to",)),
    CQ("S01", "일정·실측·시공", "<날짜>에 실측·시공이 되나요, 가장 빠른 날은요? 이 날로 잡아 주세요",
       "order_data", ("erp:schedule", "process_step", "policy", "erp:order"), ("at_step", "requires")),
    CQ("S02", "일정·실측·시공", "잡힌 실측·시공 일정을 바꾸거나 확인할 수 있나요?",
       "order_data", ("erp:schedule", "policy", "erp:order", "process_step"), ("at_step", "requires")),
    CQ("S03", "일정·실측·시공", "제 일정·담당자는 어떻게 되고 제 요청이 전달되나요?",
       "order_data", ("erp:schedule", "erp:order", "fact"), ("at_step",)),
    CQ("S04", "일정·실측·시공", "실측 뒤 도면·견적은 언제 받나요, 시안을 미리 볼 수 있나요?",
       "order_data", ("process_step", "policy", "erp:order", "erp:schedule"), ("at_step",)),
    CQ("S05", "일정·실측·시공", "실측부터 설치까지, 시공 당일은 얼마나 걸리나요?",
       "rule", ("process_step", "product_line", "policy", "erp:schedule"), ("at_step", "applies_to")),
    CQ("S06", "일정·실측·시공", "주말·공휴일·저녁에도 되나요, 기사는 몇 시에 오나요?",
       "rule", ("policy", "erp:schedule", "product_line", "fact"), ("applies_to", "at_step")),
    CQ("S07", "일정·실측·시공", "다른 공사(도배·마루·입주청소)와 어떤 순서로 하나요?",
       "rule", ("process_step", "situation", "build_rule", "policy"), ("at_step", "requires")),
    CQ("S08", "일정·실측·시공", "시공 당일 무엇을 준비하나요?",
       "rule", ("policy", "process_step", "situation"), ("at_step", "requires")),
    CQ("S09", "일정·실측·시공", "실측 방문이 꼭 필요하고 비용이 있나요, 자가 실측이 되나요?",
       "rule", ("policy", "process_step", "price_rule", "situation"), ("requires", "at_step", "applies_to")),
    CQ("S10", "일정·실측·시공", "기존 가구 철거·폐기도 해 주나요, 비용은요?",
       "rule", ("price_rule", "policy", "build_rule", "situation"), ("applies_to", "requires", "excludes")),
    CQ("S11", "일정·실측·시공", "이사할 때 옮겨 다시 설치할 수 있나요?",
       "rule", ("policy", "build_rule", "process_step", "price_rule"), ("applies_to", "requires", "at_step")),
    CQ("S12", "일정·실측·시공", "도면을 고칠 수 있고 몇 번까지 되나요?",
       "rule", ("process_step", "erp:order", "policy", "build_rule"), ("at_step", "requires", "excludes")),
    CQ("S13", "일정·실측·시공", "실측 오차가 생기면 누가 부담하나요?",
       "rule", ("policy", "build_rule"), ("applies_to",)),
    CQ("S14", "일정·실측·시공", "우리 집 구조에서 설치가 되는지 봐 주실 수 있나요?",
       "human_judgment", ("situation", "build_rule", "owner_decision"), ("requires",)),
    CQ("D01", "배송", "<지역>도 실측·시공을 오나요, 출장비·권역비는요?",
       "rule", ("policy", "price_rule", "fact", "situation"), ("applies_to", "value_from")),
    CQ("D02", "배송", "엘리베이터·계단·사다리차 같은 운반 조건은 어떻게 되나요?",
       "human_judgment", ("situation", "policy", "build_rule", "price_rule"), ("requires", "applies_to")),
    CQ("D03", "배송", "설치 없이 택배로 받을 수 있나요?",
       "rule", ("policy", "price_rule"), ("applies_to",)),
    CQ("A01", "AS·하자", "AS를 신청했는데 언제 오나요, 약속한 처리는 됐나요?",
       "order_data", ("erp:order", "erp:schedule", "process_step", "policy"), ("at_step", "requires", "applies_to")),
    CQ("A02", "AS·하자", "설치 뒤 <부위>가 이상한데 고쳐 주나요?",
       "photo", ("policy", "erp:order", "situation", "process_step"), ("applies_to", "requires", "at_step")),
    CQ("A03", "AS·하자", "AS 보증 기간·범위·출장비는 어떻게 되나요?",
       "rule", ("policy", "spec"), ("applies_to",)),
    CQ("A04", "AS·하자", "부자재를 따로 살 수 있나요?",
       "order_data", ("product_line", "option", "erp:order"), ("applies_to",)),
    CQ("X01", "정책·기타", "전화·카톡 같은 상담 창구와 영업시간은요?",
       "rule", ("policy", "fact"), ("applies_to",)),
    CQ("X02", "정책·기타", "제조사 직영인가요, 매장은 어디인가요?",
       "rule", ("fact", "policy"), ("applies_to",)),
    CQ("X03", "정책·기타", "인테리어 업체가 의뢰하면 어떻게 진행하나요?",
       "rule", ("process_step", "policy", "situation"), ("at_step",)),
    CQ("X04", "정책·기타", "담당자 응대가 불만인데 어떻게 처리되나요?",
       "human_judgment", ("policy", "erp:order", "owner_decision"), ("applies_to",)),
)
