"""네이버 붙이기 후보 **쌍 판정** — 렌더·버튼 강조·표 전수 대조.

판정 자체와 문구는 ``test_naver_candidate_pair_signal`` 이 본다. 이 파일은 그 판정이
**화면까지 따라왔는가**를 렌더 결과로 확인하고(문구와 버튼 강조가 같은 키를 읽는가),
표의 모든 칸을 한 번씩 견주며, 휴지통 주문의 노출·차단을 못박는다.
픽스처는 ``naver_candidate_pair_helpers`` 한 벌을 공유한다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.order_candidates import (
    recommended_relation,
    search_orders_for_attach,
)
from models import Order

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
# 7. 문구와 버튼 강조는 **같은 키**를 읽는다
# --------------------------------------------------------------------------- #

#: 신호 문구 → 그 문구가 뜰 때 강조돼야 하는 버튼의 관계.
SIGNAL_TEXT_BY_RELATION = {"REPAY": REPAY_TEXT, "ADDON": ADDON_TEXT}


@pytest.mark.parametrize("current_claim, candidate_claim, expected", [
    ("CANCEL_DONE", "", "REPAY"),             # all_done x alive
    ("CANCEL_DONE", "CANCEL_DONE", "REPAY"),  # all_done x all_done
    ("", "", "ADDON"),                        # alive x alive
    ("", "CANCEL_DONE", "REPAY"),             # alive x all_done
    ("CANCEL_REQUEST", "", ""),               # all_pending x alive - 권하지 않음
])
def test_signal_text_and_button_highlight_read_the_same_key(
        client, workbench_on, current_claim, candidate_claim, expected):
    """②열 문구와 오른쪽 버튼 강조가 **한 판정**에서 나온다 — 렌더 결과로 본다.

    예전에는 payload 에 값이 똑같은 키가 둘 있었다(``relation_signal_code`` 는 문구가,
    ``recommended_relation`` 은 버튼이 읽었다). 이름이 둘이면 **한쪽만 고치는 경로**가
    열린다 — 표는 `재결제 신호` 라고 적어 놓고 강조된 버튼은 추가결제였던 2026-09-04
    결함이 바로 그 모양이다. 키를 하나로 줄였으니, 화면 두 층이 실제로 같은 답을 내는지
    를 dict 가 아니라 **본문**으로 못박는다.
    """
    _login(client)
    tel = f"010-3383-{_uid()}"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-7-CAND", tel=tel, amount=900_000, claim=candidate_claim,
          order_id=order_id)
    current = _link(order_no="N-PAIR-7-CUR", tel=tel, amount=1_000_000, claim=current_claim)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["recommended_relation"] == expected, "쌍 판정이 표와 다르다"
    assert "relation_signal_code" not in row,         "값이 같은 키에 이름을 둘 두면 한쪽만 고치는 경로가 다시 열린다"

    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    highlighted = [btn for btn in buttons if "btn-outline-primary" in btn]
    for relation, text in SIGNAL_TEXT_BY_RELATION.items():
        printed = text in body
        emphasized = any(f'data-relation="{relation}"' in btn for btn in highlighted)
        assert printed == emphasized,             f"{relation}: 문구({printed})와 버튼 강조({emphasized})가 갈렸다"
        assert printed == (relation == expected),             f"{relation}: 화면이 권고({expected!r})와 다른 말을 한다"


# --------------------------------------------------------------------------- #
# 8. 검색 경로도 같은 규칙이다
# --------------------------------------------------------------------------- #

def test_search_path_carries_the_same_pair_rule(client, workbench_on):
    """``search_orders_for_attach`` 행에도 쌍 판정이 같은 규칙으로 실린다.

    검색은 후보 0건일 때의 유일한 붙이기 경로다. 여기만 옛 축으로 남으면 자동 매칭이
    못 잡는 조합(가족 대리결제·시공지 변경·번호 변경) — 즉 **재결제가 가장 많은 자리** —
    에서 화면이 그대로 추가결제를 권한다.
    """
    _login(client)
    tel = "010-3382-7000"
    name = f"검색쌍판정{_uid()}"
    order_id = _order(tel=tel, name=name)
    _link(order_no="N-PAIR-8-CAND", tel=tel, amount=1_610_780, order_id=order_id, name=name)
    current = _link(order_no="N-PAIR-8-CUR", tel=tel, amount=1_191_900,
                    claim="CANCEL_DONE", name=name)

    result = search_orders_for_attach(db_session, current, query=name)
    row = next(item for item in result["rows"] if item["order_id"] == order_id)

    assert row["current_claim_code"] == "all_done"
    assert row["naver_claim_code"] == "alive", "칩은 후보 쪽의 사실 그대로다"
    assert row["recommended_relation"] == "REPAY"

    body = _seek(client, link_id=int(current.id), query=name)

    assert REPAY_TEXT in body
    assert ADDON_TEXT not in body, "검색 경로가 옛 축으로 남았다"
    repay_at = body.find('data-relation="REPAY"')
    addon_at = body.find('data-relation="ADDON"')
    assert repay_at > 0 and addon_at > 0, "붙이기 버튼이 없다"
    assert repay_at < addon_at, "재결제 신호인데 추가결제 버튼이 먼저 나온다"
    repay_btn = body[body.rfind("<button", 0, repay_at):repay_at]
    assert "btn-outline-primary" in repay_btn, "권장 관계가 강조색이 아니다"


# --------------------------------------------------------------------------- #
# 9. 표 자체의 전수 확인 — 어느 칸도 우연히 REPAY 가 되지 않게
# --------------------------------------------------------------------------- #

#: 판정 표를 손으로 옮긴 것이다(줄 = 지금 집, 칸 = **후보 주문**). 구현이 아니라 **계약**을
#: 적은 것이므로, 여기와 구현이 갈리면 구현을 고친다. 빈 문자열 키는 셀 것이 아예 없는
#: 쪽이다(후보 ``link_count == 0`` 또는 지금 집을 못 읽음) — 못 읽었다고 재결제를 권하지
#: 않는다.
#:
#: ``all_done`` 줄에서 ``partial``·``all_pending``·``all_mixed`` 칸이 비어 있는 이유:
#: 지금 집이 옛 결제라도 후보 쪽이 확정 전이거나 일부만 취소됐으면 **실행 축**
#: (``repay_reconcile.run_gate``)이 막거나 사람이 봐야 하는 칸이다. 권고 축과 실행 축이
#: 같은 칸에서 어긋나면 화면이 자기 말을 안 지킨다(10절이 렌더로 못박는다).
DECISION_GRID = {
    "": {"": "", "alive": "", "partial": "", "all_done": "",
         "all_pending": "", "all_mixed": ""},
    "alive": {"": "", "alive": "ADDON", "partial": "", "all_done": "REPAY",
              "all_pending": "", "all_mixed": ""},
    "partial": {"": "", "alive": "", "partial": "", "all_done": "",
                "all_pending": "", "all_mixed": ""},
    "all_done": {"": "", "alive": "REPAY", "partial": "", "all_done": "REPAY",
                 "all_pending": "", "all_mixed": ""},
    "all_pending": {"": "", "alive": "", "partial": "", "all_done": "",
                    "all_pending": "", "all_mixed": ""},
    "all_mixed": {"": "", "alive": "", "partial": "", "all_done": "",
                  "all_pending": "", "all_mixed": ""},
}


@pytest.mark.parametrize("current_code", sorted(DECISION_GRID))
def test_recommended_relation_matches_the_decision_table(current_code):
    """지금 집 코드 한 줄을 후보 코드 6칸과 **한 칸씩** 대조한다.

    ``claim_aggregate_code`` 가 내는 5종에 '수집분 없음'(빈 문자열)까지 넣어 6×6 = 36칸을
    전수로 본다. 표에 없는 칸이 우연히 REPAY 로 떨어지면 그 칸에서 예약금 안내가
    '바꾸기'로 갈린다.
    """
    actual = {candidate_code: recommended_relation(current_claim_code=current_code,
                                                   candidate_claim_code=candidate_code)
              for candidate_code in DECISION_GRID}

    assert actual == DECISION_GRID[current_code]


# --------------------------------------------------------------------------- #
# 10. 실행이 막히거나 사람이 봐야 하는 칸은 **권하지도 않는다** (렌더 계약 3칸)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("candidate_claims, expected_code, can_run", [
    (("CANCEL_REQUEST", "CANCEL_REQUEST"), "all_pending", False),
    (("CANCEL_DONE", "CANCEL_REQUEST"), "all_mixed", False),
    (("CANCEL_DONE", ""), "partial", True),
])
def test_all_done_current_never_recommends_an_unsettled_candidate(
        client, workbench_on, candidate_claims, expected_code, can_run):
    """지금 집 ``all_done`` × 후보 ``all_pending``/``all_mixed``/``partial`` → 권고 없음.

    지금 집이 옛 결제라는 것만으로 재결제를 권하면 **권고 축과 실행 축이 같은 칸에서
    어긋난다**. 확정 전 칸은 ``repay_reconcile.run_gate`` 가 실행 자체를 막으므로, 화면은
    ②열 한 칸 안에서 `네이버가 아직 확정하지 않았습니다`(칩 층)와 `재결제 신호`(신호 층)
    를 동시에 적고, 강조된 버튼이 여는 정리 계획의 `정리 실행` 은 애초에 눌리지 않는다.
    더 나쁜 쪽은 검색 경로의 붙이기 라우트다 — 거기엔 ``run_gate`` 가 없어 화면이 권한
    재결제가 그대로 실행된다. 그래서 이 세 칸은 **권고 자체를 내지 않는다**.

    ``partial`` 은 실행이 막히지는 않는다(``can_run`` 이 True 다). 그래도 권하지 않는
    이유는 다르다 — 후보 축은 집이 아니라 **주문 단위 집계**라, 재결제가 이미 한 번 붙은
    주문은 옛 수집분과 새 수집분이 섞여 ``partial`` 로 나온다. 사람이 봐야 하는 칸이다.
    """
    _login(client)
    tel = "010-3384-7000"
    name = f"막힌칸{_uid()}"
    order_id = _order(tel=tel, name=name)
    for index, claim in enumerate(candidate_claims):
        _link(order_no="N-PAIR-10-CAND", tel=tel, amount=900_000 + index, claim=claim,
              order_id=order_id, name=name)
    current = _link(order_no="N-PAIR-10-CUR", tel=tel, amount=1_191_900,
                    claim="CANCEL_DONE", name=name)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "all_done", "지금 집 전제가 깨졌다"
    assert row["naver_claim_code"] == expected_code, "후보 쪽 집계 전제가 깨졌다"
    assert row["recommended_relation"] == ""

    # (a) 두 신호 문구 어느 쪽도 화면에 없다.
    assert REPAY_TEXT not in body, "실행이 막히거나 사람이 봐야 하는 칸에 재결제를 권한다"
    assert ADDON_TEXT not in body

    # (b) 어느 버튼도 강조되지 않는다 — 강조가 곧 권고다.
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    assert not [btn for btn in buttons if "btn-outline-primary" in btn],         "아무 쪽도 권하지 않는데 한쪽이 강조색이다"

    # (c) 확정 전 칸은 실행 축도 막혀 있다(템플릿이 `정리 실행` 을 disabled 로 만드는 값).
    assert _reconcile_plans(current, order_id)["REPAY"]["can_run"] is can_run,         "실행 축 전제가 깨졌다 — 권고 축을 이 값과 견주는 것이 이 테스트의 뜻이다"

    # 검색 경로도 같은 3칸을 본다. 여기엔 실행 관문이 아예 없어 화면이 곧 실행이다.
    seek_row = next(item for item in
                    search_orders_for_attach(db_session, current, query=name)["rows"]
                    if item["order_id"] == order_id)
    assert seek_row["recommended_relation"] == ""

    seek_body = _seek(client, link_id=int(current.id), query=name)

    assert REPAY_TEXT not in seek_body, "검색 경로가 막힌 칸에 재결제를 권한다"
    assert ADDON_TEXT not in seek_body
    seek_buttons = _seek_buttons(seek_body)
    assert [_button_relation(btn) for btn in seek_buttons] == ["ADDON", "REPAY"],         "권고가 없으면 버튼 순서는 기본값 그대로다"
    assert not [btn for btn in seek_buttons if "btn-outline-primary" in btn],         "권고가 없는데 검색 경로가 한쪽을 강조한다"

# --------------------------------------------------------------------------- #
# 6. 휴지통 주문 (2026-09-07) — 목록에는 내고, 붙이기는 닫는다
#
# 이광헌 사고에서 이번 집의 진짜 짝(#5163)은 휴지통이라 후보 표에서 통째로 빠졌다.
# 담당자 화면에는 새 주문 하나만 남았고, 그게 "기존 주문 전부"로 읽혔다.
# --------------------------------------------------------------------------- #

def test_pane_shows_trashed_candidate_and_closes_its_attach_buttons(client, workbench_on):
    """휴지통 주문은 표에 나오되 `휴지통` 이라 말하고, 붙이기 버튼은 없다.

    버튼을 열어 두면 서버(:func:`promotion.attach_link_to_order`)가 거절하면서
    "붙일 주문을 찾을 수 없습니다"라는 엉뚱한 말을 돌려준다 — 화면이 먼저 이유를 말한다.
    """
    _login(client)
    tel = "010-7788-0001"
    trashed_id = _order(tel=tel, name="휴지통고객")
    trashed = db_session.get(Order, trashed_id)
    trashed.deleted_at = now_utc_naive()
    db_session.commit()
    current = _link(order_no="N-TRASH-CUR", tel=tel, amount=1_093_100,
                    claim="CANCEL_DONE", name="휴지통고객")

    body = _pane(client, link_id=current.id)

    assert f"#{trashed_id}" in body, "휴지통 주문이 후보 표에서 통째로 빠졌다"
    assert "휴지통" in body
    assert f'data-order-id="{trashed_id}"' not in body, "휴지통 주문에 붙이기 버튼이 열렸다"
    assert "되살린 뒤에 붙이세요" in body


def test_live_candidate_still_gets_its_attach_buttons(client, workbench_on):
    """음성 대조군 — 살아 있는 후보는 버튼이 그대로 있다(전부 닫아 버리면 안 된다)."""
    _login(client)
    tel = "010-7788-0002"
    live_id = _order(tel=tel, name="살아있는고객")
    current = _link(order_no="N-TRASH-LIVE", tel=tel, amount=500_000, name="살아있는고객")

    body = _pane(client, link_id=current.id)

    assert f'data-order-id="{live_id}"' in body
    assert "되살린 뒤에 붙이세요" not in body


def test_trashed_candidate_deposit_hint_does_not_move_refunded_money(client, workbench_on):
    """전부 취소된 집을 재결제로 정리해도 **환불된 금액**을 예약금으로 권하지 않는다."""
    _login(client)
    tel = "010-7788-0003"
    order_id = _order(tel=tel, name="환불안내고객")
    _link(order_no="N-DEP-OLD", tel=tel, amount=900_000, order_id=order_id,
          name="환불안내고객")
    current = _link(order_no="N-DEP-CUR", tel=tel, amount=1_093_100,
                    claim="CANCEL_DONE", name="환불안내고객")

    plans = _reconcile_plans(current, order_id)

    assert plans["REPAY"]["deposit"]["verb"] == "그대로"
    assert "1,093,100" not in plans["REPAY"]["deposit"]["sentence"]

