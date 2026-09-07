"""네이버 붙이기 후보 **쌍 판정** — 판정과 문구 계약 (2026-09-07 운영 사고).

전부 취소된 집을 놓고 고르는데 화면이 후보 주문 쪽만 보고
`살아 있음 · 추가결제 신호` 라고 권했다(고객 이광헌, 집 ``2026090658033751`` 6건 전부
``CANCEL_DONE`` × 후보 주문 #5168 의 수집분 전부 ``PAYED``). 지금 집이 옛 결제이므로
실제 관계는 **재결제**다 — 판정 축에 "지금 집"이 없었던 것이 근본 원인이다.

렌더·버튼 강조·표 전수 대조는 ``test_naver_candidate_pair_render`` 가 본다.
픽스처는 ``naver_candidate_pair_helpers`` 한 벌을 공유한다.
"""

from __future__ import annotations

import pytest  # noqa: F401  (파라미터 테스트가 쓴다)

from tests.services.integrations.naver_candidate_pair_helpers import (  # noqa: F401
    ADDON_TEXT,
    REPAY_TEXT,
    TRIAGE_PATH,
    _attach_buttons,
    _button_relation,
    _candidate_row,
    _link,
    _login,
    _order,
    _pane,
    _reconcile_plans,
    _seek,
    _seek_buttons,
    _uid,
    workbench_on,
)

# --------------------------------------------------------------------------- #
# 1. 운영 사고 재현 — 지금 집이 전부 취소면 후보 쪽이 살아 있어도 재결제다
# --------------------------------------------------------------------------- #

def test_all_canceled_current_household_recommends_repay(app):
    """지금 집 ``all_done`` × 후보 주문 ``alive`` → ``REPAY``. 칩은 그대로 `살아 있음`.

    운영 실데이터 그대로다(이광헌 / 지금 집 ``2026090658033751`` 전부 ``CANCEL_DONE`` ×
    후보 주문 **#5168** 의 수집분 ``2026090758601671`` 전부 ``PAYED``). 예전 판정은 후보 쪽만
    봐서 `추가결제 신호` 를 권했다.

    **칩과 신호는 다른 축**이라는 것도 여기서 못박는다 — ``naver_claim_code`` 는 여전히
    ``alive`` 여야 한다(후보 쪽의 사실은 바뀌지 않았다).
    """
    tel = "010-3380-7500"
    order_id = _order(tel=tel)
    # 후보 주문 #5168 자리 — 살아 있는 집(클레임 없음) 2건.
    _link(order_no="N-PAIR-1-CAND", tel=tel, amount=1_022_900, order_id=order_id)
    _link(order_no="N-PAIR-1-CAND", tel=tel, amount=587_880, order_id=order_id)
    # 지금 집 — 전부 취소 확정, 아직 안 붙음.
    current = _link(order_no="N-PAIR-1-CUR", tel=tel, amount=1_191_900, claim="CANCEL_DONE")
    _link(order_no="N-PAIR-1-CUR", tel=tel, amount=170_000, claim="CANCEL_DONE")

    row = _candidate_row(current, order_id)

    assert row["current_claim_code"] == "all_done", "지금 집이 판정 축에 없다"
    assert row["naver_claim_code"] == "alive", "후보 쪽의 사실(칩)까지 바뀌면 안 된다"
    assert row["recommended_relation"] == "REPAY", "권고 축이 쌍 판정을 안 읽는다"


# --------------------------------------------------------------------------- #
# 2. 음성 대조군 — 화면이 실제로 따라오는가 (렌더 결과)
# --------------------------------------------------------------------------- #

def test_pane_prints_the_repay_signal_and_never_the_addon_one(client, workbench_on):
    """같은 상황의 pane 본문에 `재결제 신호` 가 있고 `추가결제 신호` 는 **없다**.

    dict 만 보면 판정만 고치고 템플릿이 옛 축(``naver_claim_code``)으로 남아 있어도
    green 이 된다 — 그때 담당자 화면은 여전히 `추가결제 신호` 다. 그래서 본문을 본다.
    """
    _login(client)
    tel = "010-3380-7501"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-2-CAND", tel=tel, amount=1_610_780, order_id=order_id)
    current = _link(order_no="N-PAIR-2-CUR", tel=tel, amount=1_191_900, claim="CANCEL_DONE")

    body = _pane(client, link_id=int(current.id))

    assert f"#{order_id}" in body, "후보 표에 그 주문이 없다 — 전제가 깨졌다"
    assert REPAY_TEXT in body, "지금 집이 옛 결제인데 재결제 신호를 안 적는다"
    assert ADDON_TEXT not in body, "후보 쪽만 보고 추가결제를 권한다(2026-09-07 운영 사고)"
    # 칩은 후보 쪽의 사실 그대로다 — 신호가 재결제라고 칩까지 죽은 낱말로 바꾸면
    # 담당자가 후보 주문의 수집분이 취소된 것으로 읽는다.
    assert "wb-cand__claim--alive" in body, "칩이 후보 쪽의 사실을 버렸다"
    # 눈이 가는 쪽도 권고를 따라간다(관계 오선택 → deposit_guidance → 고객 청구액).
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    highlighted = [btn for btn in buttons if "btn-outline-primary" in btn]
    assert len(highlighted) == 1 and 'data-relation="REPAY"' in highlighted[0], \
        "권장 관계(재결제)가 강조색이 아니다"


# --------------------------------------------------------------------------- #
# 3~4. 회귀 아님 — 옛 동작 두 칸은 그대로다
# --------------------------------------------------------------------------- #

def test_both_households_alive_stays_addon(client, workbench_on):
    """지금 집 ``alive`` × 후보 주문 ``alive`` → ``ADDON`` (기존 동작 유지).

    쌍 판정이 들어왔다고 차액 결제까지 재결제로 뒤집히면 예약금이 '바꾸기'로 갈려
    고객이 낸 예약금이 화면에서 사라진다.
    """
    _login(client)
    tel = "010-3380-7502"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-3-CAND", tel=tel, amount=1_191_900, order_id=order_id)
    current = _link(order_no="N-PAIR-3-CUR", tel=tel, amount=17_880)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "alive"
    assert row["naver_claim_code"] == "alive"
    assert row["recommended_relation"] == "ADDON"
    assert ADDON_TEXT in body
    assert REPAY_TEXT not in body, "둘 다 살아 있는데 재결제를 권한다"


def test_canceled_candidate_still_repays_when_current_lives(client, workbench_on):
    """지금 집 ``alive`` × 후보 주문 ``all_done`` → ``REPAY`` (기존 동작 유지).

    이 칸은 쌍 판정 이전에도 재결제였다. 새 표가 옛 칸을 밟지 않았다는 음성 대조군이다.
    """
    _login(client)
    tel = "010-3380-7503"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-4-CAND", tel=tel, amount=1_191_900, claim="CANCEL_DONE",
          order_id=order_id)
    current = _link(order_no="N-PAIR-4-CUR", tel=tel, amount=1_610_780)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "alive"
    assert row["naver_claim_code"] == "all_done"
    assert row["recommended_relation"] == "REPAY"
    assert REPAY_TEXT in body
    assert ADDON_TEXT not in body


# --------------------------------------------------------------------------- #
# 5. 권하지 않음 — 사람이 봐야 하는 칸은 신호 줄 자체가 없다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tel, current_claims, expected_code", [
    ("010-3380-7511", ("CANCEL_DONE", ""), "partial"),
    ("010-3380-7512", ("CANCEL_REQUEST", "CANCEL_REQUEST"), "all_pending"),
])
def test_partial_or_pending_current_recommends_nothing(client, workbench_on,
                                                       tel, current_claims, expected_code):
    """지금 집이 ``partial``·``all_pending`` 이면 권고는 빈 문자열이다.

    일부만 취소됐거나 네이버가 아직 확정하지 않은 집이라 사람이 봐야 한다. 화면은
    **신호 줄을 아예 내지 않고** 버튼도 어느 쪽도 강조하지 않는다 — 강조가 곧 권고다.
    """
    _login(client)
    order_id = _order(tel=tel)
    _link(order_no=f"N-PAIR-5-CAND-{expected_code}", tel=tel, amount=1_191_900,
          order_id=order_id)
    current = None
    for index, claim in enumerate(current_claims):
        link = _link(order_no=f"N-PAIR-5-CUR-{expected_code}", tel=tel,
                     amount=500_000 + index, claim=claim)
        current = current or link

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == expected_code, "지금 집 집계가 전제와 다르다"
    assert row["recommended_relation"] == "", "사람이 봐야 하는 칸인데 권고가 나왔다"
    assert REPAY_TEXT not in body and ADDON_TEXT not in body, "신호 줄이 남아 있다"
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    assert not [btn for btn in buttons if "btn-outline-primary" in btn], \
        "아무 쪽도 권하지 않는데 한쪽이 강조색이다"


# --------------------------------------------------------------------------- #
# 6. 카브아웃 — 후보에 네이버 집이 아예 없으면 권하지 않는다
# --------------------------------------------------------------------------- #

def test_candidate_without_a_naver_household_recommends_nothing(client, workbench_on):
    """후보가 ERP 수기 주문(``naver_link_count == 0``)이면 지금 집이 무엇이든 권고는 없다.

    없는 집에 재결제를 권하면 ``deposit_guidance`` 가 '바꾸기'로 갈려 고객 청구액을
    건드린다. 화면은 `네이버 수집분 없음` 한 줄만 낸다(지금과 같다).
    """
    _login(client)
    tel = "010-3380-7520"
    order_id = _order(tel=tel)
    current = _link(order_no="N-PAIR-6-CUR", tel=tel, amount=800_000, claim="CANCEL_DONE")

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "all_done"
    assert row["naver_link_count"] == 0
    assert row["naver_claim_code"] == ""
    assert row["recommended_relation"] == ""
    assert "네이버 수집분 없음" in body
    assert REPAY_TEXT not in body and ADDON_TEXT not in body


