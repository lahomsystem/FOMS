# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 부분 취소 뒤 남은 라인의 발주확인·발송(결정 5).

부분 취소 표식(``cancel_scope="partial"``)은 집을 잠그지 않고 **그 라인만** 대상에서 뺀다 —
household 표식이나 취소 실패가 남은 집은 그대로 잠긴다. 벌크 발송 pre-check
(``bulk_dispatch._blocking_reason``)가 같은 판정을 거울처럼 다시 하는지도 여기서 본다
(스펙 §11 결정 9).

서비스 계약(``plan_claim_scope``·``cancel_order``·``request_return``)은
``test_naver_partial_claim``, 큐·워커·라우트는 ``test_naver_partial_claim_routes``,
화면은 ``test_naver_partial_claim_ui`` 가 본다.
픽스처·헬퍼는 ``naver_partial_claim_helpers`` 한 벌을 공유한다.
"""
from __future__ import annotations

import copy

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink

from tests.services.integrations.naver_partial_claim_helpers import (
    _StubClient,
    _link,
    _links,
    _state,
)
from tests.services.integrations.test_naver_bulk_dispatch_select import (
    TODAY,
    _measured_on,
    _order,
)

# --------------------------------------------------------------------------- #
# 결정 5 — 부분 취소 뒤 남은 라인의 발주확인·발송
# --------------------------------------------------------------------------- #

def test_partial_cancel_leaves_the_rest_dispatchable(app):
    """부분 취소 표식(``cancel_scope="partial"``)은 집을 잠그지 않고 **그 라인만 대상에서 뺀다**.

    발송처리(M+A1 집, A1 취소 → M 만 발송)와 발주확인(M2+A4 집, A4 취소 → M2 만 발주확인)
    둘 다 — ``_cancel_guard`` 가 제외 목록을 돌려주는 계약 §1.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, confirm_place_order, dispatch_order,
    )

    main = _link("PO-PC-D5-M", order_no="N-PC-D5", addon=False)
    _link("PO-PC-D5-A1", order_no="N-PC-D5", addon=True)
    main2 = _link("PO-PC-D5C-M", order_no="N-PC-D5C", addon=False, place="NOT_YET")
    _link("PO-PC-D5C-A4", order_no="N-PC-D5C", addon=True, place="NOT_YET")
    client = _StubClient()

    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5-A1"])
    db_session.commit()
    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-D5-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-D5-M"]

    cancel_order(db_session, client, link_id=main2, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5C-A4"])
    db_session.commit()
    confirmed = confirm_place_order(db_session, client, link_id=main2)
    db_session.commit()

    assert confirmed["confirmed"] == ["PO-PC-D5C-M"]
    assert client.confirm_calls[-1] == ["PO-PC-D5C-M"]


def test_partial_cancel_survives_the_next_refresh(app):
    """다음 수집이 A1 스냅샷을 ``CANCEL_DONE`` 으로 바꿔도 남은 본품 발송은 열려 있다.

    집 단위 ``_claim_guard`` 가 partial 표식 라인을 판정에서 빼 주지 않으면, 우리가 낸
    부분 취소가 재수집 뒤 형제 클레임으로 읽혀 집 전체를 다시 잠근다(결정 5 의 두 번째 절반).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, dispatch_order,
    )

    main = _link("PO-PC-RF-M", order_no="N-PC-RF", addon=False)
    a1 = _link("PO-PC-RF-A1", order_no="N-PC-RF", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-RF-A1"])
    db_session.commit()

    row = db_session.get(ExternalOrderLink, a1)
    snapshot = copy.deepcopy(row.raw_snapshot)
    snapshot["productOrder"]["claimStatus"] = "CANCEL_DONE"
    snapshot["productOrder"]["claimType"] = "CANCEL"
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()

    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-RF-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-RF-M"]


def test_household_cancel_still_blocks_dispatch(app):
    """★ 음성 대조군(test_naver_cancel.py:325 거울) — 집 전체 취소 뒤 발송처리는 여전히 거절.

    결정 5 는 partial 표식만 연다. household(또는 옛 키 없는) 표식은 오늘처럼 집을 잠근다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-HB-M", order_no="N-PC-HB", addon=False)
    _link("PO-PC-HB-A1", order_no="N-PC-HB", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=main)
    assert client.dispatch_calls == []


def test_a_failed_cancel_line_still_blocks_dispatch(app):
    """취소 **실패**가 남은 라인(``last_error_action == "cancel"``)이 있으면 집 전체 차단(결정 5 단서)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-FL-M", order_no="N-PC-FL", addon=False)
    _link("PO-PC-FL-A1", order_no="N-PC-FL", addon=True)
    client = _StubClient(fail_ids={"PO-PC-FL-A1"})

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-FL-A1"])
    db_session.commit()

    with pytest.raises(FulfillmentError) as err:
        dispatch_order(db_session, client, link_id=main)
    assert "취소" in str(err.value)
    assert client.dispatch_calls == []


# --------------------------------------------------------------------------- #
# 벌크 발송 pre-check — `_cancel_guard` 거울 (결정 5, 스펙 §11 결정 9)
# --------------------------------------------------------------------------- #

def test_bulk_blocking_reason_mirrors_the_cancel_guard(app):
    """``bulk_dispatch._blocking_reason`` 은 순수 함수다 — 네이버 0회, ``_StubClient`` 조차 없다.

    partial 표식 + 재수집 ``CANCEL_DONE`` 형제 집은 ``""``(보낼 수 있다), household 표식 집은
    '취소한 주문입니다', 취소 실패가 남은(``last_error_action == "cancel"``) 집은
    '취소가 실패한 상품주문이 있습니다' — ``fulfillment._cancel_guard`` 와 같은 갈래·순서.
    """
    from foms.services.integrations.naver_commerce.bulk_dispatch import _blocking_reason

    open_main = _link("PO-PC-BK-M", order_no="N-PC-BK", addon=False)
    _link("PO-PC-BK-A1", order_no="N-PC-BK", addon=True, canceled=True,
          cancel_scope="partial", claim="CANCEL_DONE", claim_type="CANCEL")
    lock_main = _link("PO-PC-BKH-M", order_no="N-PC-BKH", addon=False)
    _link("PO-PC-BKH-A1", order_no="N-PC-BKH", addon=True, canceled=True,
          cancel_scope="household")
    fail_main = _link("PO-PC-BKF-M", order_no="N-PC-BKF", addon=False)
    fail_a1 = _link("PO-PC-BKF-A1", order_no="N-PC-BKF", addon=True)
    row = db_session.get(ExternalOrderLink, fail_a1)
    row.triage_state = {"fulfillment": {"last_error": "상품 주문 상태 확인 필요",
                                        "last_error_action": "cancel"}}
    flag_modified(row, "triage_state")
    db_session.commit()

    assert _blocking_reason(_links(open_main)) == ""
    assert _blocking_reason(_links(lock_main)).startswith("취소한 주문입니다")
    assert "1건" in _blocking_reason(_links(lock_main))
    assert _blocking_reason(_links(fail_main)).startswith("취소가 실패한 상품주문이 있습니다")


# --------------------------------------------------------------------------- #
# 구매자가 낸 부분 클레임 — 나머지는 발송한다 (2026-09-14)
#
# 2026-09-11 은 **우리가 취소한 행**에만 라인 스코프를 열어 뒀다. 구매자가 네이버에서
# 직접 낸 부분 클레임은 그대로 집 전체를 잠가, 판매자센터에서는 보낼 수 있는 남은
# 상품주문을 우리 화면에서만 영영 못 보냈다(#5245 이지학 — 발주확인 5/5 · 일부 취소 1건).
# --------------------------------------------------------------------------- #

def _claimed_pair(tag: str, *, place: str = "OK") -> tuple[int, str, str]:
    """본품 M + **구매자가 낸** 취소 확정 추가구성 A1 로 이루어진 집 하나.

    Args:
        tag: 집을 구분할 꼬리표(외부 id 에 들어간다).
        place: 두 행의 발주확인 상태.

    Returns:
        ``(기준 링크 id, 본품 외부 id, 클레임 행 외부 id)``.
    """
    order_no = f"N-PCB-{tag}"
    main = _link(f"{order_no}-M", order_no=order_no, addon=False, place=place)
    _link(f"{order_no}-A1", order_no=order_no, addon=True, place=place,
          claim="CANCEL_DONE", claim_type="CANCEL")
    return main, f"{order_no}-M", f"{order_no}-A1"


def _fully_claimed(tag: str) -> tuple[int, int]:
    """집의 **모든** 상품주문에 구매자 클레임이 걸린 집(음성 대조군용).

    Args:
        tag: 집을 구분할 꼬리표.

    Returns:
        ``(본품 링크 id, 추가구성 링크 id)``.
    """
    order_no = f"N-PCB-{tag}"
    main = _link(f"{order_no}-M", order_no=order_no, addon=False,
                 claim="CANCEL_DONE", claim_type="CANCEL")
    addon = _link(f"{order_no}-A1", order_no=order_no, addon=True,
                  claim="CANCEL_DONE", claim_type="CANCEL")
    return main, addon


def _day_row(link_id: int) -> dict:
    """그 집의 **화면 줄**(``build_preview`` 의 ``day_rows``) 하나."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    rows = [row for row in build_preview(db_session, on_date=TODAY)["day_rows"]
            if row["link_id"] == int(link_id)]
    assert len(rows) == 1, f"link {link_id} 의 화면 줄이 하나가 아니다: {rows}"
    return rows[0]


def _attach_to_a_measured_order(link_ids: list[int], *, customer: str) -> None:
    """그 링크들을 **오늘 실측** 주문에 붙인다 — 벌크 발송 띠의 모집단 조건."""
    order = _order(customer=customer)
    _measured_on(order)
    for link_id in link_ids:
        db_session.get(ExternalOrderLink, int(link_id)).order_id = int(order.id)
    db_session.commit()


def test_dispatch_payload_carries_only_the_unclaimed_product_order(app):
    """★ 이 작업의 안전 전부 — 클레임 걸린 상품주문 id 는 payload 에 **한 건도** 없다.

    발송처리는 불가역이다(구매자에게 '배송 시작'으로 보이고 정산 시계를 돌린다).
    그래서 반환값이 아니라 **네이버로 나간 payload** 를 직접 연다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    main, main_id, claimed_id = _claimed_pair("PAYLOAD")
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    sent = [str(row["productOrderId"]) for row in client.dispatch_calls[-1]]
    assert sent == [main_id]
    assert claimed_id not in sent, "클레임이 걸린 상품주문이 네이버 payload 에 실렸다"
    assert result["dispatched"] == [main_id]
    assert claimed_id in result["claim_skipped"], "몇 건을 뺐는지 화면이 말할 근거가 없다"


def test_the_skipped_key_keeps_its_list_of_str_shape(app):
    """``skipped`` 의 **모양은 안 바뀐다** — 워커와 기존 테스트가 그 모양을 읽는다."""
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    main, _main_id, claimed_id = _claimed_pair("SHAPE")
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert isinstance(result["skipped"], list)
    assert all(isinstance(pid, str) for pid in result["skipped"]), \
        "dict 로 바꾸면 워커(jobs/tasks.py)와 기존 테스트가 조용히 깨진다"
    assert claimed_id in result["skipped"]


def test_place_confirm_still_comes_first_for_the_remaining_rows(app):
    """남은 본품이 발주확인 전이면 여전히 막힌다 — 관문이 사라진 것이 아니다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, dispatch_order,
    )

    main, _main_id, _claimed_id = _claimed_pair("PLACE", place="NOT_YET")
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        dispatch_order(db_session, client, link_id=main)

    assert str(err.value).startswith("발주확인이 먼저입니다")
    assert client.dispatch_calls == []


def test_a_claimed_row_never_blocks_on_its_own_place_confirm(app):
    """클레임 행의 발주확인은 **영영 안 된다** — 그 행을 기다리면 집이 영원히 안 열린다."""
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    order_no = "N-PCB-WAIT"
    main = _link(f"{order_no}-M", order_no=order_no, addon=False, place="OK")
    _link(f"{order_no}-A1", order_no=order_no, addon=True, place="NOT_YET",
          claim="CANCEL_DONE", claim_type="CANCEL")
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert result["dispatched"] == [f"{order_no}-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == [f"{order_no}-M"]


def test_a_fully_claimed_household_is_still_refused(app):
    """★ 음성 대조군 — 집 전부가 클레임이면 오늘과 **같은 문구·같은 실패 표식**으로 거절한다.

    새 문장을 만들면 ``_mark_failures`` 표식이 사라져 워크벤치 실패 띠가 침묵한다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, dispatch_order,
    )

    main, addon = _fully_claimed("ALLCLAIM")
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert str(err.value).startswith("취소·반품·교환이 걸린 주문입니다")
    assert client.dispatch_calls == [], "집 전부가 클레임인데 네이버로 호출이 나갔다"
    assert _state(main)["last_error"], "실패 띠가 침묵한다"
    assert _state(addon)["last_error"]


def test_close_now_is_still_counted_over_the_whole_household(app):
    """``close_now`` 는 집 **전체**로 센다 — 클레임 행을 빼고 다시 세면 뜻이 바뀐다.

    집 전체가 추가결제(``ADDON``)면 발주확인 없이 닫는다. 클레임 행이 섞여도 그 판정은
    흔들리지 않아야 한다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    order_no = "N-PCB-ADDON"
    main = _link(f"{order_no}-M", order_no=order_no, addon=False, place="NOT_YET")
    addon = _link(f"{order_no}-A1", order_no=order_no, addon=True, place="NOT_YET",
                  claim="CANCEL_DONE", claim_type="CANCEL")
    for link_id in (main, addon):
        db_session.get(ExternalOrderLink, link_id).relation = "ADDON"
    db_session.commit()
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert result["dispatched"] == [f"{order_no}-M"], "추가결제 집인데 발주확인을 기다렸다"


def test_bulk_blocking_reason_opens_for_a_partly_claimed_household(app):
    """거울 — 남은 행이 있으면 빈 문자열, 집 **전부**가 클레임일 때만 사유를 낸다."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import _blocking_reason

    open_main, _main_id, _claimed_id = _claimed_pair("MIRROR")
    lock_main, _addon = _fully_claimed("MIRRORALL")

    assert _blocking_reason(_links(open_main)) == "", \
        "남은 상품주문이 있는데 집이 통째로 잠겼다(#5245)"
    assert _blocking_reason(_links(lock_main)) == \
        "취소·반품·교환이 걸린 주문입니다 — 판매자센터에서 처리하세요."


def test_household_locks_are_untouched_by_the_claim_change(app):
    """집 단위 취소 표식·취소 실패 잔존은 **여전히** 각자의 문구로 집을 잠근다(결정 5 불변)."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import _blocking_reason

    lock_main = _link("PO-PCB-HH-M", order_no="N-PCB-HH", addon=False)
    _link("PO-PCB-HH-A1", order_no="N-PCB-HH", addon=True, canceled=True,
          cancel_scope="household")
    fail_main = _link("PO-PCB-FL-M", order_no="N-PCB-FL", addon=False)
    fail_a1 = _link("PO-PCB-FL-A1", order_no="N-PCB-FL", addon=True)
    row = db_session.get(ExternalOrderLink, fail_a1)
    row.triage_state = {"fulfillment": {"last_error": "상품 주문 상태 확인 필요",
                                        "last_error_action": "cancel"}}
    flag_modified(row, "triage_state")
    db_session.commit()

    assert _blocking_reason(_links(lock_main)).startswith("취소한 주문입니다")
    assert _blocking_reason(_links(fail_main)).startswith("취소가 실패한 상품주문이 있습니다")


def test_the_screen_says_the_same_count_the_server_sends(app):
    """화면 재진술 == 서버 처리 건수 — 조용히 빼면 두 화면이 다른 수를 말한다."""
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    main, _main_id, _claimed_id = _claimed_pair("DAY")
    _attach_to_a_measured_order([row.id for row in _links(main)], customer="이지학")

    row = _day_row(main)

    assert row["claim_excluded"] == 1, "몇 건을 빼고 보내는지 화면이 말하지 않는다"
    assert row["eligible"] is True, "남은 상품주문이 있는데 띠가 보낼 수 없다고 말한다"

    client = _StubClient()
    result = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert row["sendable_orders"] == len(result["dispatched"])


def test_a_fully_claimed_household_is_not_eligible_on_the_screen(app):
    """★ 음성 대조군 — 집 전부가 클레임이면 띠도 사유와 함께 닫혀 있다."""
    main, addon = _fully_claimed("DAYALL")
    _attach_to_a_measured_order([main, addon], customer="전부취소")

    row = _day_row(main)

    assert row["eligible"] is False
    assert row["reason"], "보낼 수 없다면서 사유가 비었다"
