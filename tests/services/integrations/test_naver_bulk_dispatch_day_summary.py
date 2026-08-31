"""NAVER-BULKDISPATCH-02 T1: 오늘 하루 **결과**를 세는 계약.

1회차 운영(2026-08-31)에서 버튼을 누르고 새로고침했더니 띠가 통째로 사라졌다. 동작은
정상이었지만 화면에서는 발송 여부를 알 수 없었다 — **"다 나갔다"와 "애초에 대상이
없었다"가 같은 모양(띠 사라짐)이었기 때문이다.** 되돌릴 수 없는 조작에서 그 둘이 구분되지
않으면 사람이 판매자센터를 다시 열게 되고, 이 기능이 없앤 일이 되살아난다.

그래서 이 파일이 가장 무겁게 재는 것은 **두 상태가 화면 값에서 갈리는가** 이고, 그 다음이
**판매자센터 수동 발송분을 '남음'으로 세지 않는가**(음성 대조군)이다.
"""

from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.integrations.naver_commerce.bulk_dispatch import (
    build_day_summary,
    build_preview,
    select_targets,
)
from models import ExternalOrderLink

from tests.services.integrations.test_naver_bulk_dispatch_select import (  # noqa: F401
    OTHER_DAY,
    TODAY,
    _fresh_db,
    _link_to,
    _measured_on,
    _naver_order,
    _order,
    _stamp_naver,
    _stamp_ours,
)
from tests.services.integrations.test_naver_workbench import _collected, _uid


def _mark_failure(link: ExternalOrderLink, *, action: str = "dispatch",
                  reason: str = "발송처리에 실패했습니다: 네이버 500") -> None:
    """워커가 남기는 실패 표식을 그대로 얹는다.

    Args:
        link: 대상 링크.
        action: 실패한 작업(``dispatch``/``confirm``).
        reason: 사유 문장.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = {**(state.get("fulfillment") or {}),
                            "last_error": reason,
                            "last_error_at": "2026-08-31T07:45:00",
                            "last_error_action": action}
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _one(rows: list[dict], link_id: int) -> dict:
    """그 링크가 대표인 줄 하나를 집어낸다.

    Args:
        rows: ``day_rows``.
        link_id: 찾을 대표 링크 id.

    Returns:
        줄 dict.
    """
    picked = [row for row in rows if row["link_id"] == link_id]
    assert len(picked) == 1, f"link {link_id} 의 줄이 하나가 아니다: {rows}"
    return picked[0]


# --------------------------------------------------------------------------- #
# 두 상태가 갈리는가 — 이 작업의 존재 이유
# --------------------------------------------------------------------------- #

def test_all_sent_day_says_done_not_empty():
    """전부 나간 날은 **띠가 뜨고 '완료'라고 말한다** — 사라지지 않는다."""
    _, link = _naver_order(order_no=f"N-DONE-{_uid()}")
    _stamp_ours(link)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["show"] is True, "다 나간 날에 띠가 사라지면 1회차 결함 그대로다"
    assert preview["state"] == "done"
    assert preview["count"] == 0, "보낼 대상은 0이 맞다 — 기존 키의 뜻은 안 바뀐다"
    assert preview["sent"] == 1
    assert preview["day_total"] == 1
    assert preview["last_sent_at"], "언제 나갔는지 말해야 한다"


def test_day_without_naver_orders_shows_nothing():
    """오늘 네이버 건이 아예 없으면 띠를 띄우지 않는다 — '완료'와 다른 사실이다."""
    order = _order(customer="박예약")
    _measured_on(order)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["show"] is False
    assert preview["state"] == "none"
    assert preview["day_total"] == 0


def test_pending_day_is_not_called_done():
    """아직 안 보낸 날은 ``pending`` 이다(완료와 섞이지 않는다)."""
    _naver_order(order_no=f"N-PEND-{_uid()}")
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["state"] == "pending"
    assert preview["sent"] == 0
    assert preview["count"] == 1 and preview["eligible"] == 1


def test_partial_day_says_partial():
    """일부만 나간 날은 보낸 수와 남은 수를 **함께** 말한다."""
    _, done = _naver_order(order_no=f"N-P1-{_uid()}", customer="김보냄")
    _stamp_ours(done)
    _naver_order(order_no=f"N-P2-{_uid()}", customer="이남음")
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["state"] == "partial"
    assert preview["day_total"] == 2
    assert preview["sent"] == 1
    assert preview["count"] == 1


# --------------------------------------------------------------------------- #
# 음성 대조군 — 판매자센터 수동 발송분
# --------------------------------------------------------------------------- #

def test_manual_seller_center_dispatch_counts_as_sent():
    """**판매자센터에서 사람이 보낸 집도 '발송됨'이다.**

    우리 표식만 세면 손으로 보낸 집이 영원히 "남음"으로 뜬다 — 화면 큐가 이미 그 실수를
    하고 있고, 그걸 상속하면 사람이 이미 끝난 일을 다시 누르게 된다.
    """
    _, link = _naver_order(order_no=f"N-MAN-{_uid()}")
    _stamp_naver(link)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["state"] == "done"
    assert preview["sent"] == 1
    row = _one(preview["day_rows"], link.id)
    assert row["state"] == "sent"
    assert row["sent_by_naver"] is True, "우리가 한 일과 사람이 한 일을 구별해 말해야 한다"
    assert row["sent_at"], "네이버 원본 시각을 그대로 읽어 보여준다"


def test_our_dispatch_is_not_labelled_as_manual():
    """우리가 보낸 집은 수동 발송으로 말하지 않는다(대조군의 반대편)."""
    _, link = _naver_order(order_no=f"N-OURS2-{_uid()}")
    _stamp_ours(link)
    row = _one(build_preview(db_session, on_date=TODAY)["day_rows"], link.id)
    assert row["state"] == "sent"
    assert row["sent_by_naver"] is False


# --------------------------------------------------------------------------- #
# 실패
# --------------------------------------------------------------------------- #

def test_dispatch_failure_is_reported_with_reason():
    """발송처리 실패는 사유와 함께 뜬다 — 재시도할 사람이 이유를 알아야 한다."""
    _, link = _naver_order(order_no=f"N-FAIL-{_uid()}")
    _mark_failure(link)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["failed"] == 1
    row = _one(preview["day_rows"], link.id)
    assert row["state"] == "failed"
    assert "네이버 500" in row["failure_reason"]


def test_confirm_failure_is_not_counted_as_dispatch_failure():
    """**발주확인 실패는 발송 실패가 아니다** — 작업 축을 안 보면 남의 실패를 뒤집어쓴다."""
    _, link = _naver_order(order_no=f"N-CFAIL-{_uid()}")
    _mark_failure(link, action="confirm", reason="발주확인에 실패했습니다")
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["failed"] == 0
    assert _one(preview["day_rows"], link.id)["failure_reason"] == ""


def test_sent_household_does_not_show_stale_failure():
    """**다 나간 집의 옛 실패 기록은 실패로 세지 않는다.**

    판매자센터 수동 발송분이 정확히 이 모양을 만든다 — 워커가 "네이버에 이미 발송 기록이
    있습니다"로 되돌려보내며 실패 표식을 남긴다. 그 집은 실제로 **발송된** 집이라,
    빨간 줄로 띄우면 화면이 "발송됐는데 실패했다"고 말하게 된다.
    """
    _, link = _naver_order(order_no=f"N-STALE-{_uid()}")
    _stamp_naver(link)
    _mark_failure(link, reason="네이버에 이미 발송 기록이 있습니다(2026-08-30 14:03)")
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["failed"] == 0
    assert preview["state"] == "done"
    assert _one(preview["day_rows"], link.id)["failure_reason"] == ""


# --------------------------------------------------------------------------- #
# 기존 계약이 안 깨졌는가
# --------------------------------------------------------------------------- #

def test_select_targets_still_excludes_sent_households():
    """실행 경로(:func:`select_targets`)는 이미 나간 집을 **여전히** 안 돌려준다."""
    _, sent = _naver_order(order_no=f"N-SEL1-{_uid()}", customer="김끝남")
    _stamp_ours(sent)
    _, left = _naver_order(order_no=f"N-SEL2-{_uid()}", customer="이남음")
    picked = select_targets(db_session, on_date=TODAY)
    assert [t.link_id for t in picked] == [left.id]


def test_day_summary_keeps_sent_household_that_select_drops():
    """같은 집을 요약은 들고 선별은 뺀다 — 두 함수의 뜻이 다르다는 계약."""
    _, link = _naver_order(order_no=f"N-BOTH-{_uid()}")
    _stamp_ours(link)
    assert [t.link_id for t in build_day_summary(db_session, on_date=TODAY)] == [link.id]
    assert select_targets(db_session, on_date=TODAY) == []


def test_rows_are_targets_only_and_day_rows_are_everything():
    """``rows`` 는 보낼 대상, ``day_rows`` 는 오늘 전체 — 두 화면이 이 뜻에 기대고 있다."""
    _, sent = _naver_order(order_no=f"N-KEY1-{_uid()}", customer="김끝남")
    _stamp_ours(sent)
    _, left = _naver_order(order_no=f"N-KEY2-{_uid()}", customer="이남음")
    preview = build_preview(db_session, on_date=TODAY)
    assert [row["link_id"] for row in preview["rows"]] == [left.id]
    assert sorted(row["link_id"] for row in preview["day_rows"]) == sorted([sent.id, left.id])


def test_other_day_is_not_counted_in_today_result():
    """다른 날 실측분은 오늘 결과에 안 섞인다(날짜 술어가 요약에서도 산다)."""
    _, link = _naver_order(order_no=f"N-DAY2-{_uid()}", date=OTHER_DAY)
    _stamp_ours(link)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["show"] is False and preview["day_total"] == 0


def test_blocked_household_state_is_blocked_not_failed():
    """막힌 집과 실패한 집은 다른 상태다 — 사람이 할 일이 다르다."""
    _, link = _naver_order(order_no=f"N-BLK-{_uid()}", place_status="")
    row = _one(build_preview(db_session, on_date=TODAY)["day_rows"], link.id)
    assert row["state"] == "blocked"
    assert "발주확인이 먼저" in row["reason"]


def test_household_with_one_sent_and_one_left_stays_a_target():
    """집 안에서 일부만 나갔으면 그 집은 **아직 대상**이다(남은 건만 센다)."""
    order = _order(customer="최반쪽")
    _measured_on(order)
    order_no = f"N-HALF-{_uid()}"
    first = _link_to(order, _collected(order_no=order_no, product="붙박이장",
                                       amount=500_000))
    second = _link_to(order, _collected(order_no=order_no, product="붙박이장",
                                        amount=500_000))
    _stamp_ours(first)
    preview = build_preview(db_session, on_date=TODAY)
    assert preview["count"] == 1 and preview["sent"] == 0
    row = preview["day_rows"][0]
    assert row["product_orders"] == 1, "남은 건만 '보낼 상품주문'으로 센다"
    assert row["sent_orders"] == 1
    targets = select_targets(db_session, on_date=TODAY)
    assert [t.pending_link_ids for t in targets] == [[second.id]]
