# -*- coding: utf-8 -*-
"""유령 주문 '재결제 예정' — 저장 규약과 판정 (2026-09-14).

왜 이 기능이 있나
-----------------
:func:`ghost_orders.find_repay_candidate_links` 는 **이미 네이버 큐에 들어온 집**만 짝으로
찾는다 — 아직 결제가 안 들어온 건은 구조적으로 늘 `없음` 이라, 시스템이 알 수 없는 사실을
사람이 표시해야 한다(#5158 김선미 취소 후 · #5136 이신혜 반품 후 재결제 예정). 표시가 없으면
담당자는 그 행을 매일 보면서 접지도 치우지도 못하고, 실수로 접으면 재결제가 들어왔을 때
붙일 주문이 휴지통에 있다.

이 파일이 못박는 것 다섯:

1. 저장 시각은 **KST 표시 문자열** ``YYYY-MM-DD HH:MM`` 이다 — ISO naive 로 두면 템플릿의
   ``format_datetime_kst`` 가 UTC 로 읽어 9시간이 밀린다.
2. 해제는 **키 삭제**다. 빈 dict 를 남기면 ``if sd.get(KEY)`` 한 비트가 거짓말을 한다.
3. 표시는 JSONB 규약을 타야 **실제로 남는다** — 커밋하고 다시 읽어 증명한다.
4. 표시가 있어도 **모집단에서 빼지 않는다**(사용자 결정 2026-09-14) — 띠에 남고 버튼만 잠긴다.
5. 판정 순서는 사람이 먼저 알아야 할 사실 순이다: 살아 있는 결제 → 확정 전 → 재결제 표시.

라우트·자동 해제는 :mod:`test_naver_ghost_repay_route`, 화면 문구·버튼은
:mod:`test_naver_ghost_repay_ui` 가 잰다.
"""
from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.ghost_orders import (
    REPAY_EXPECTED_BLOCK_TEXT,
    REPAY_EXPECTED_SD_KEY,
    _discard_verdict,
    clear_repay_expected,
    judge_order_discard,
    read_repay_expected,
    set_repay_expected,
)
from models import Order
from tests.services.integrations.naver_ghost_repay_helpers import (
    AT_SHAPE,
    _bucket_of,
    _ghost,
    _link,
    _order,
    _row,
)


# --------------------------------------------------------------------------- #
# 저장 규약 — 시각 모양 · 잘림 · 키 삭제 · 실제로 남는가
# --------------------------------------------------------------------------- #

def test_the_mark_round_trips_with_a_kst_display_stamp(app):
    """왕복 — ``at`` 은 KST 표시 문자열이고 ISO 의 ``T`` 가 없다(메모 잘림도 함께)."""
    order = _order(tel="010-7910-0001")

    mark = set_repay_expected(order, actor_user_id=58, actor_name="김담당",
                              note="고객이 재결제하겠다고 함")

    assert AT_SHAPE.match(mark["at"]), f"KST 표시 문자열이 아니다: {mark['at']}"
    assert "T" not in mark["at"], "ISO naive 로 두면 화면이 9시간 밀린 시각을 찍는다"
    assert mark["by"] == 58
    assert mark["by_name"] == "김담당"
    assert mark["note"] == "고객이 재결제하겠다고 함"
    assert read_repay_expected(order) == mark

    # 메모는 200자로 자른다 — 화면 한 줄에 들어가야 하고 JSONB 를 살찌우지 않는다.
    assert len(set_repay_expected(order, actor_user_id=58, note="가" * 260)["note"]) == 200


def test_clearing_twice_is_harmless(app):
    """지울 게 있으면 True, 없으면 False — 예외를 던지지 않는다(무해한 호출)."""
    order = _order(tel="010-7910-0003")
    set_repay_expected(order, actor_user_id=1)

    assert clear_repay_expected(order) is True
    assert clear_repay_expected(order) is False, "두 번째 호출이 True 를 냈다"
    assert read_repay_expected(order) is None


def test_clearing_deletes_the_key_not_just_the_value(app):
    """해제는 **키 삭제**다 — 빈 dict 를 남기면 한 비트 판독이 거짓말을 한다."""
    order = _order(tel="010-7910-0004")
    set_repay_expected(order, actor_user_id=1, note="재결제 예정")

    clear_repay_expected(order)

    assert REPAY_EXPECTED_SD_KEY not in (order.structured_data or {}), "키를 남겼다"


def test_the_mark_actually_survives_a_commit(app):
    """저장이 DB 에 남는다 — JSONB 규약(재대입 + ``flag_modified``)의 유일한 증명이다."""
    order = _order(tel="010-7910-0005")
    order_id = int(order.id)
    set_repay_expected(order, actor_user_id=7, actor_name="박담당", note="재결제 약속")

    db_session.commit()
    db_session.expire_all()

    again = read_repay_expected(db_session.get(Order, order_id))
    assert again is not None, "커밋했는데 표시가 안 남았다 — flag_modified 가 빠졌다"
    assert again["note"] == "재결제 약속"
    assert again["by_name"] == "박담당"


# --------------------------------------------------------------------------- #
# 띠 — 잠기되 사라지지 않는다 (+ 음성 대조군)
# --------------------------------------------------------------------------- #

def test_a_marked_row_locks_the_trash_and_stays_in_the_band(app):
    """표시된 행은 휴지통이 잠기고 사유를 말한다 — 그리고 **띠에 그대로 남는다**."""
    marked = _ghost(tel="010-7911-0001", order_no="N-RX-1", amount=3_067_000)
    _ghost(tel="010-7911-0002", order_no="N-RX-2", amount=1_369_000)  # 같은 띠의 이웃
    set_repay_expected(marked, actor_user_id=1, actor_name="김담당", note="재결제 예정")
    db_session.commit()

    row = _row(int(marked.id))

    assert isinstance(row["repay_expected"], dict), "표시가 행에 안 실렸다"
    assert row["repay_expected"]["note"] == "재결제 예정"
    assert row["can_discard"] is False, "표시했는데 휴지통이 열려 있다"
    assert row["discard_block"] == REPAY_EXPECTED_BLOCK_TEXT


def test_an_unmarked_ghost_in_the_same_band_stays_open(app):
    """★ 음성 대조군 — 같은 띠의 이웃 행은 표시도 잠금도 없다.

    모집단 **밖**에서 고르면 "원래 안 떴던 것"을 재게 된다 — 같은 조회에서 함께 꺼낸다.
    """
    marked = _ghost(tel="010-7911-0003", order_no="N-RX-3", amount=3_067_000)
    plain = _ghost(tel="010-7911-0004", order_no="N-RX-4", amount=1_369_000)
    set_repay_expected(marked, actor_user_id=1, actor_name="김담당")
    db_session.commit()

    row = _row(int(plain.id))

    assert row["repay_expected"] is None
    assert row["can_discard"] is True, "이웃 행까지 잠갔다"
    assert row["discard_block"] == ""


# --------------------------------------------------------------------------- #
# pane — 띠와 같은 세 값
# --------------------------------------------------------------------------- #

def test_the_pane_carries_the_same_three_values(app):
    """pane 판정에도 같은 세 값이 실린다 — 띠와 pane 이 갈리면 같은 주문을 다르게 말한다."""
    order = _ghost(tel="010-7912-0001", order_no="N-RX-5")
    set_repay_expected(order, actor_user_id=1, actor_name="김담당", note="재결제 예정")
    db_session.commit()

    view = judge_order_discard(db_session, int(order.id))

    assert isinstance(view["repay_expected"], dict)
    assert view["can_discard"] is False
    assert view["discard_block"] == REPAY_EXPECTED_BLOCK_TEXT


def test_the_blank_view_still_carries_the_repay_key(app):
    """블록을 안 그리는 경로도 키를 **고정값 None** 으로 들고 있다 — 모양이 갈리면
    pane 템플릿이 ``undefined`` 를 읽어 조용히 아무것도 안 그린다.
    """
    order = _order(tel="010-7912-0002")
    _link(order_no="N-RX-6", amount=900_000, tel="010-7912-0002", order_id=int(order.id))

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is False, "클레임이 없는데 블록이 그려졌다"
    assert "repay_expected" in view, "blank 반환에 키 자체가 없다"
    assert view["repay_expected"] is None


# --------------------------------------------------------------------------- #
# 판정 순서 — 사람이 먼저 알아야 할 사실이 이긴다
# --------------------------------------------------------------------------- #

def test_a_living_payment_beats_the_repay_sentence(app):
    """살아 있는 결제가 있으면 재결제 문장이 이기지 않는다(판정 순서 1).

    셈법은 운영과 같은 :func:`_fold_link` 다 — 버킷을 손으로 지어내지 않는다.
    """
    tel = "010-7913-0001"
    order = _order(tel=tel)
    _link(order_no="N-RX-7", amount=500_000, tel=tel, claim="CANCEL_DONE",
          order_id=int(order.id))
    _link(order_no="N-RX-7", amount=300_000, tel=tel, order_id=int(order.id))
    set_repay_expected(order, actor_user_id=1)
    db_session.commit()

    verdict = _discard_verdict(_bucket_of(int(order.id)), "RECEIVED", repay_expected=True)

    assert verdict["can_discard"] is False
    assert verdict["discard_block"] == "이 주문에는 아직 살아 있는 결제가 있습니다"


def test_an_unconfirmed_claim_beats_the_repay_sentence(app):
    """확정 전 취소가 재결제 문장을 이긴다(판정 순서 2) — 띠에서 실제로 그렇게 읽힌다."""
    order = _ghost(tel="010-7913-0002", order_no="N-RX-8", claim="CANCEL_REQUEST")
    set_repay_expected(order, actor_user_id=1)
    db_session.commit()

    row = _row(int(order.id))

    assert row["can_discard"] is False
    assert row["discard_block"] == "네이버가 아직 취소를 확정하지 않았습니다"
    assert row["repay_expected"] is not None, "사실 자체는 그대로 실려야 한다"


# --------------------------------------------------------------------------- #
# pane 버튼은 라우트와 같은 말을 한다 — in_ghost_band
# --------------------------------------------------------------------------- #

def test_the_pane_says_whether_the_route_would_take_this_order(app):
    """``in_ghost_band`` 는 라우트(:func:`find_ghost_orders`)와 **같은 술어**다.

    pane 이 ``link_count == canceled_count`` 를 손으로 다시 세면 판정 축이 두 벌이 되고,
    부분 취소 주문에서 버튼이 열려 누르면 `목록에 없습니다` 400 이 온다 — 눌러야만 알 수
    있는 죽은 버튼이다.
    """
    whole = _ghost(tel="010-7917-0001", order_no="N-RX-22")
    assert judge_order_discard(db_session, int(whole.id))["in_ghost_band"] is True

    # ★ 음성 대조군 — 살아 있는 결제가 섞인 주문은 블록은 그려지되 버튼은 안 연다.
    tel = "010-7917-0002"
    partial = _order(tel=tel)
    _link(order_no="N-RX-23", amount=500_000, tel=tel, claim="CANCEL_DONE",
          order_id=int(partial.id))
    _link(order_no="N-RX-23", amount=300_000, tel=tel, order_id=int(partial.id))
    view = judge_order_discard(db_session, int(partial.id))

    assert view["applicable"] is True, "클레임이 있으니 블록 자체는 그려진다"
    assert view["in_ghost_band"] is False, "띠 모집단 밖인데 버튼이 열린다"

    # 블록을 안 그리는 경로도 키를 고정값으로 들고 있어야 모양이 안 갈린다.
    plain = _order(tel="010-7917-0003")
    _link(order_no="N-RX-24", amount=100_000, tel="010-7917-0003", order_id=int(plain.id))
    blank = judge_order_discard(db_session, int(plain.id))

    assert blank["in_ghost_band"] is False
