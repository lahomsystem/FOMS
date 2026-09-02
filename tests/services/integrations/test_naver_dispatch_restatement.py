"""발송처리 — **보낼 것이 0건인 집에 버튼이 열려 있던 자리** (2026-09-02).

`a077c72a`(모달 재진술을 `dispatch_pending_count` 로 통일)와 `7b06c966`(부분 발송 안내줄도
두 신호로)이 **말**을 고쳤다. 남은 것은 **버튼**이다.

`can_dispatch` 의 잠금 신호 두 개는 이 집을 못 막는다:

* `naver_sent_at` 은 pane 이 연 **상품주문 1건**의 원본만 본다(집 단위로 세려면 형제 원본을
  읽어야 하는데 pane 컨텍스트에 그 값이 없다 — 템플릿 주석이 그 한계를 적어 뒀다).
* `dispatched` 는 **우리가 다 보냈나**로 남긴다(2026-09-02 상류 판단 — 두 신호로 바꾸면
  판매자센터가 보낸 집이 '발송처리 완료' 배지로 덮이고 잠금 사유가 사라진다).

그래서 집 전체가 판매자센터에서 나갔고 연 건만 우리 표식을 가진 집에서는 버튼이 열린 채였다.
안내줄은 이미 "더 보낼 상품주문이 없습니다"라고 적는데 그 옆 버튼이 눌리고, 모달은
**"0건을 네이버에 발송처리로 보냅니다"** 라고 말한다 — 화면이 자기 자신과 모순되고, 눌러도
서버가 `FulfillmentError` 로 되돌린다. 옮길 형제가 0건이면 주문 만들기 버튼을 안 여는
(`can_create`) 규율과 같은 자리다.

말(문장)을 재는 계약은 `test_naver_dispatch_duplicate_block.py` §③ 에 있다 — 여기서 겹쳐
재지 않는다. 두 벌이면 한쪽만 고쳐도 초록이 된다.
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import is_dispatch_pending
from models import ExternalOrderLink

from tests.services.integrations.test_naver_dispatch_duplicate_block import (
    _mark_dispatched,
    _naver_sent,
    _pane_html,
)
from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _pane,
    _uid,
    workbench_on,
)
from tests.services.integrations.test_naver_workbench_v3_followup import _sibling

#: 모달 ① 재진술 문장의 꼬리 — 숫자만 갈아 끼워 찾는다.
SENDS = "건을 네이버에 발송처리로 보냅니다"


def _house_of_three(order_no: str) -> tuple[ExternalOrderLink, ExternalOrderLink,
                                            ExternalOrderLink]:
    """상품주문 3건짜리 집 하나(대표 + 형제 2)."""
    lead = _collected(order_no=order_no, product="붙박이장 본품", amount=1000000)
    return lead, _sibling(lead, product="구성 A", amount=2000), \
        _sibling(lead, product="구성 B", amount=3000)


def test_button_closes_when_the_opened_product_order_looks_clean(client, workbench_on):
    """**잠금의 사각** — 연 건은 우리 표식뿐이고 형제가 전부 판매자센터에서 나간 집.

    `naver_sent_at` 이 비어 있고(연 건에는 네이버 기록이 없다) `dispatched` 도 False 다
    (우리 표식은 3건 중 1건뿐). 두 잠금이 다 열어 주는 유일한 조합이고, 보낼 것은 0건이다.
    """
    _login(client)
    lead, sib_a, sib_b = _house_of_three("N-RS-SIBONLY")
    _naver_sent(sib_a)
    _naver_sent(sib_b)
    _mark_dispatched(lead)

    pane = _pane_html(client, lead.id)

    assert 'id="wb-dispatch-confirm"' not in pane, "보낼 것이 0건인데 발송 모달이 남았다"
    assert SENDS not in pane, "0건 집에서 재진술 문장이 렌더됐다"
    # 화면이 이미 하는 말과 버튼이 같은 편에 서야 한다.
    assert "더 보낼 상품주문이 없습니다" in pane, pane[:0]


def test_button_closes_when_the_whole_house_left_the_seller_center(client, workbench_on):
    """연 건에도 네이버 기록이 있는 집(기준선) — 옛 잠금으로도 닫히던 자리다.

    위 시험과 짝이다. 이쪽이 초록인데 위가 빨강이면, 잠금이 **연 1건만 보고 있다**는 뜻이다.
    """
    _login(client)
    lead, sib_a, sib_b = _house_of_three("N-RS-ALLNAVER")
    _naver_sent(sib_a)
    _naver_sent(sib_b)
    _naver_sent(lead, send_date="2026-08-25T15:00:00.000+09:00")

    pane = _pane_html(client, lead.id)

    assert 'id="wb-dispatch-confirm"' not in pane, "보낼 것이 0건인데 발송 모달이 남았다"
    assert SENDS not in pane, "0건 집에서 재진술 문장이 렌더됐다"


def test_a_clean_household_keeps_its_button(client, workbench_on):
    """**음성 대조군** — 아무 기록도 없는 집은 버튼이 그대로 열린다.

    잠그는 쪽만 재면 "전부 잠그기"도 초록이 된다. 가드가 과하면 정상 집까지 막혀 사람이
    판매자센터로 도망가고, 그 순간 이 화면은 존재 이유를 잃는다.
    """
    _login(client)
    lead, _sib_a, _sib_b = _house_of_three("N-RS-OPEN")

    pane = _pane_html(client, lead.id)

    assert 'id="wb-dispatch-confirm"' in pane, "정상 집에서 발송 모달이 사라졌다"
    assert f"3{SENDS}" in pane, "정상 집의 재진술이 줄었다"


def test_partial_household_still_opens_for_the_rest(client, workbench_on):
    """**음성 대조군 2** — 남은 건이 있으면(부분 발송) 버튼은 계속 열린다.

    0건 가드가 "하나라도 나갔으면 닫기"로 잘못 넓어지면, 부분 발송 집의 남은 상품주문이
    영영 못 나간다. 그 집이야말로 이 버튼이 필요한 자리다.
    """
    _login(client)
    lead, sib_a, _sib_b = _house_of_three("N-RS-PART")
    _naver_sent(sib_a)

    pane = _pane_html(client, lead.id)

    assert 'id="wb-dispatch-confirm"' in pane, "남은 건이 있는데 발송 모달이 사라졌다"
    assert f"2{SENDS}" in pane, "남은 건수 재진술이 흔들렸다"


def test_predicate_answers_for_each_signal(client, workbench_on):
    """술어를 **신호별로** 한 번씩 — 화면과 서버가 같은 함수를 부르는 것이 이 축의 근거다.

    함수가 신호 하나를 잃으면 두 소비처가 **함께** 틀린다. 소비처마다 재는 계약은 그 사실을
    못 잡는다(둘 다 같은 방향으로 틀리기 때문이다).
    """
    _login(client)
    lead, sib_a, sib_b = _house_of_three("N-RS-PRED")
    _naver_sent(sib_a)
    _mark_dispatched(sib_b)

    db_session.expire_all()
    assert is_dispatch_pending(db_session.get(ExternalOrderLink, int(lead.id))) is True
    assert is_dispatch_pending(db_session.get(ExternalOrderLink, int(sib_a.id))) is False
    assert is_dispatch_pending(db_session.get(ExternalOrderLink, int(sib_b.id))) is False
