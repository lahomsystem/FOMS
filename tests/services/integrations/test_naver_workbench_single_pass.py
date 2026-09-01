"""nav 뱃지 중복 순회 제거 — **읽는 횟수만** 줄었고 판정은 한 글자도 안 바뀌었다는 계약.

2026-08-24 스테이징 구간 실측(실브라우저 콜드 8회)에서 뱃지 콜드 155.5ms 의 내역이
드러났다: 형제를 세 벌로 조회·파싱하는 데 74.0ms(48%), 두 원천 링크를 따로 읽는 데
56.0ms(36%). 그래서 형제는 색인 한 벌(``_SiblingIndex``)로, 원천은 OR 술어 한 벌
(``_work_source_links``)로 읽는다.

**여기서 지키는 것**: 옛 경로(형제 3벌 + 원천 2벌)와 새 경로의 결과가 완전히 같다는 사실.
모집단이 갈리면 계약 §2.4(뱃지 == 탭 숫자 == 칩 '전체')가 깨진다 — 이 저장소는 그걸로
nav 67·탭 45, nav 140·필터 43 을 겪었다. 옛 경로는 선택 인자를 주지 않았을 때의 분기로
그대로 살아 있어 이 비교가 가능하다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from models import ExternalOrderLink

_REVIEWED_AT = datetime.datetime(2026, 8, 24, 0, 0, 0)

#: 두 경로가 반드시 같아야 하는 집 필드.
POPULATION_FIELDS = (
    "key", "count", "extra_count", "place_pending", "place_pending_count",
    "claim_blocking", "canceled", "relation", "close_now", "locked", "can_pick",
    "in_queue", "dispatched", "dispatched_any", "dispatched_count",
    "dispatch_pending_count",
    "promotable_count", "household_count", "household_place_pending",
)


def _snapshot(*, order_no: str, po_id: str, name: str, tel: str, addr: str,
              detail: str = "101호", place: str = "NOT_YET",
              claim: Optional[str] = None, amount: int = 100000) -> dict[str, Any]:
    """네이버 상품주문 상세 1건(중첩 형태)."""
    product_order: dict[str, Any] = {
        "productOrderId": po_id,
        "productName": f"{name} 상품",
        "quantity": 1,
        "totalPaymentAmount": amount,
        "productOrderStatus": "PAYED",
        "placeOrderStatus": place,
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": addr, "detailedAddress": detail},
    }
    if claim:
        product_order["claimStatus"] = claim
    return {"order": {"orderId": order_no, "ordererName": name}, "productOrder": product_order}


def _link(db, *, external_id: str, order_no: str, name: str, tel: str, addr: str,
          detail: str = "101호", status: str = "COLLECTED", place: str = "NOT_YET",
          claim: Optional[str] = None, reviewed_at=None,
          triage_state: Optional[dict] = None) -> ExternalOrderLink:
    """수집 링크 1건을 심는다."""
    row = ExternalOrderLink(
        channel="NAVER",
        external_id=external_id,
        external_order_no=order_no,
        sync_status=status,
        place_order_status=place,
        reviewed_at=reviewed_at,
        triage_state=triage_state,
        raw_snapshot=_snapshot(order_no=order_no, po_id=external_id, name=name, tel=tel,
                               addr=addr, detail=detail, place=place, claim=claim),
    )
    db.add(row)
    db.commit()
    return row


def _seed_mixed(db) -> None:
    """모든 판정 갈래가 한 번씩 걸리는 모집단.

    확인 대기 집 · 형제 2건 집 · 분할배송(같은 주문번호·다른 주소) · 취소·반품 집 ·
    우리가 취소한 집 · 큐 밖 발주확인 전 집 · 이미 발주확인 끝난 취소 형제 ·
    발송처리가 나간 형제 · **큐에도 있고 발주확인 전에도 있는 집**(병합이 걸리는 자리).
    """
    _link(db, external_id="20260824100001", order_no="M-A", name="가집",
          tel="010-2000-0001", addr="서울 A로 1")
    _link(db, external_id="20260824100002", order_no="M-B", name="나집",
          tel="010-2000-0002", addr="서울 B로 2")
    _link(db, external_id="20260824100003", order_no="M-B", name="나집",
          tel="010-2000-0002", addr="서울 B로 2")
    _link(db, external_id="20260824100004", order_no="M-C", name="다집",
          tel="010-2000-0003", addr="서울 C로 3", detail="201호")
    _link(db, external_id="20260824100005", order_no="M-C", name="다집",
          tel="010-2000-0003", addr="서울 C로 3", detail="202호")
    _link(db, external_id="20260824100006", order_no="M-D", name="라집",
          tel="010-2000-0004", addr="서울 D로 4", claim="CANCEL_REQUEST")
    _link(db, external_id="20260824100007", order_no="M-E", name="마집",
          tel="010-2000-0005", addr="서울 E로 5",
          triage_state={"fulfillment": {"canceled_at": "2026-08-24T00:00:00"}})
    # 큐에서 빠졌지만 아직 발주확인 전 — 원천 2 에서만 오는 집
    _link(db, external_id="20260824100008", order_no="M-F", name="바집",
          tel="010-2000-0006", addr="서울 F로 6", status="LINKED",
          reviewed_at=_REVIEWED_AT)
    # 이미 발주확인이 끝난 형제가 취소·반품 — 집 전체를 잠가야 하는 자리
    _link(db, external_id="20260824100009", order_no="M-G", name="사집",
          tel="010-2000-0007", addr="서울 G로 7")
    _link(db, external_id="20260824100010", order_no="M-G", name="사집",
          tel="010-2000-0007", addr="서울 G로 7", place="OK", claim="RETURN_REQUEST",
          reviewed_at=_REVIEWED_AT)
    _link(db, external_id="20260824100011", order_no="M-H", name="아집",
          tel="010-2000-0008", addr="서울 H로 8",
          triage_state={"fulfillment": {"dispatched_at": "2026-08-24T00:00:00"}})
    # 같은 집이 큐(미확인)와 발주확인 전(확인 완료 형제) 양쪽에 걸린다 — 병합 경로
    _link(db, external_id="20260824100012", order_no="M-I", name="자집",
          tel="010-2000-0009", addr="서울 I로 9")
    _link(db, external_id="20260824100013", order_no="M-I", name="자집",
          tel="010-2000-0009", addr="서울 I로 9", status="LINKED",
          reviewed_at=_REVIEWED_AT)
    # 발주확인이 끝났고 확인도 끝난 집 — 어느 원천에도 안 들어와야 한다
    _link(db, external_id="20260824100014", order_no="M-J", name="차집",
          tel="010-2000-0010", addr="서울 J로 10", status="LINKED", place="OK",
          reviewed_at=_REVIEWED_AT)


def _legacy_work_groups(db, *, display: bool) -> tuple[list[dict[str, Any]], bool]:
    """수술 **전** 경로 — 원천 2벌 + 형제 3벌. 선택 인자를 안 주면 그대로 살아 있다."""
    from foms.web.admin.naver_ingest import (
        WORK_GROUP_LIMIT,
        _attach_household_counts,
        _attach_row_flags,
        _group_queue,
        _mark_sibling_claims,
        _orders_by_id,
        _place_groups,
        _queue_links,
        _sort_groups,
    )

    pending, truncated = _queue_links(db, display=display)
    queue = _group_queue(pending, _orders_by_id(db, pending) if display else {},
                         truncated=truncated, limit=WORK_GROUP_LIMIT + 1)
    place_groups, place_truncated = _place_groups(db, display=display)

    merged: dict[Any, dict[str, Any]] = {}
    order_of_key: list[Any] = []
    for group in queue:
        merged[group["key"]] = dict(group, in_queue=True)
        order_of_key.append(group["key"])
    for group in place_groups:
        seen = merged.get(group["key"])
        if seen is not None:
            seen["place_pending"] = bool(seen["place_pending"] or group["place_pending"])
            continue
        merged[group["key"]] = dict(group, in_queue=False)
        order_of_key.append(group["key"])
    groups = [merged[key] for key in order_of_key]
    _mark_sibling_claims(db, pending, groups, display=display)
    _attach_household_counts(db, groups, display=display)
    _attach_row_flags(groups)
    # 정렬은 캡보다 먼저 — 본체와 같은 순서로 둔다(정렬 자체는 이 수술의 대상이 아니다).
    _sort_groups(groups, "new")
    capped = len(groups) > WORK_GROUP_LIMIT
    if capped:
        groups = groups[:WORK_GROUP_LIMIT]
    return groups, bool(truncated or place_truncated or capped)


def _assert_same(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> None:
    """두 집 목록이 순서까지 같은지 — 판정에 쓰이는 필드 전부."""
    assert [g["key"] for g in left] == [g["key"] for g in right]
    for a, b in zip(left, right):
        assert ({name: a[name] for name in POPULATION_FIELDS}
                == {name: b[name] for name in POPULATION_FIELDS})


def test_single_pass_matches_legacy_three_pass(app):
    """형제 1벌·원천 1벌이 옛 3벌·2벌과 **완전히 같은 목록**을 만든다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _filter_counts, _work_groups

    _seed_mixed(db_session)

    legacy, legacy_truncated = _legacy_work_groups(db_session, display=False)
    fresh, fresh_truncated = _work_groups(db_session, display=False)

    _assert_same(legacy, fresh)
    assert legacy_truncated == fresh_truncated
    assert _filter_counts(legacy) == _filter_counts(fresh)


def test_single_pass_matches_legacy_in_display_mode(app):
    """표시 모드에서도 같다 — 얇은 경로만 고치고 화면을 흘리는 일이 없도록."""
    from db import db_session
    from foms.web.admin.naver_ingest import _filter_counts, _work_groups

    _seed_mixed(db_session)

    legacy, _ = _legacy_work_groups(db_session, display=True)
    fresh, _ = _work_groups(db_session, display=True)

    _assert_same(legacy, fresh)
    assert _filter_counts(legacy) == _filter_counts(fresh)


def test_python_place_pending_matches_sql_clause(app):
    """``_row_place_pending`` 은 ``_place_pending_clause`` 와 **같은 행**을 고른다.

    한 번 읽은 행을 파이썬에서 가르는 이상, 두 술어가 갈리면 '발주확인 전' 칩 숫자가
    목록과 어긋난다. 갈래를 직접 맞춰 본다.
    """
    from db import db_session
    from foms.web.admin.naver_ingest import _place_pending_clause, _row_place_pending

    _seed_mixed(db_session)

    sql_ids = {row.id for row in db_session.query(ExternalOrderLink).filter(
        ExternalOrderLink.channel == "NAVER", _place_pending_clause()).all()}
    all_rows = db_session.query(ExternalOrderLink).filter(
        ExternalOrderLink.channel == "NAVER").all()
    python_ids = {row.id for row in all_rows if _row_place_pending(row)}

    assert sql_ids == python_ids


def test_sibling_index_covers_legacy_claim_keys(app):
    """색인의 ``confirmed_claim_blocked`` 가 옛 ``_claim_blocked_group_keys`` 를 덮는다."""
    from db import db_session
    from foms.web.admin.naver_ingest import (
        _build_sibling_index,
        _claim_blocked_group_keys,
        _queue_links,
        _source_order_nos,
        _work_source_links,
    )

    _seed_mixed(db_session)

    pending, _ = _queue_links(db_session, display=False)
    legacy = _claim_blocked_group_keys(db_session, pending, display=False)
    source, _ = _work_source_links(db_session, display=False)
    index = _build_sibling_index(db_session, _source_order_nos(source), display=False)

    # 색인은 두 원천 합집합으로 만들어 옛 경로보다 넓게 읽지만, 목록에 오르는 집키에
    # 대해서는 같은 판정을 준다 — 그 집의 주문번호가 이미 기준 집합에 있기 때문이다.
    assert legacy
    assert legacy <= index.confirmed_claim_blocked


def test_badge_path_reads_links_table_twice(app):
    """뱃지 한 번에 링크 표 조회는 **2회**(원천 합집합 + 형제 색인)뿐이다.

    옛 경로는 원천 2 + 형제 3 + 대표 링크 1 = 6회였다. 조회 횟수가 다시 늘면 이 계약이
    빨개진다 — 성능 회귀를 사람 눈이 아니라 코드가 지킨다.
    """
    from sqlalchemy import event

    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_mixed(db_session)

    seen: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        text = " ".join(statement.split()).lower()
        if text.startswith("select") and "external_order_links" in text:
            seen.append(text)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", _count)
    try:
        _work_groups(db_session, display=False)
    finally:
        event.remove(bind, "before_cursor_execute", _count)

    assert len(seen) == 2, seen
