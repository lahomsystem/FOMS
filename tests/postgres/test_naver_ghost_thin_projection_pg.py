"""유령 스캔 축소 스냅샷 — **투영이 통째 스냅샷과 같은 띠를 낸다**는 증명 (PGTEST-00 lane).

`find_ghost_orders` 는 주문에 붙은 링크를 전부 읽는다. 운영 실측(2026-09-13)에서 그 전량이
1,958KB·조회 788ms 였고, 판정이 읽는 경로만 남기면 290KB·167ms 다. SQLite 레인에서는 투영이
폴백(원본 컬럼)이라 **이 축을 증명하지 못한다** — 그래서 PG 레인에 둔다.

여기서 재는 것 셋:

1. 모양별 충실성 — 얇은 문서로 접은 버킷이 통째 문서와 같다.
2. 실제로 얇은가 — 유령 스캔이 낸 SQL 에 ``raw_snapshot`` **본문 컬럼**이 없다.
3. 띠 동치 — 같은 데이터에서 유령 목록(수·주문 id·금액)이 그대로다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import event, select

from models import ExternalOrderLink, Order

#: 판정 경로를 한 번씩 태우는 모양. 금액을 다 다르게 두어 합계가 갈리면 드러나게 한다.
GHOST_SHAPES = {
    "정상": {
        "order": {"orderId": "GP-1"},
        "productOrder": {"productOrderId": "PP-1", "totalPaymentAmount": 100000,
                         "productName": "버리는 표시 값",
                         "shippingAddress": {"baseAddress": "서울 A로 1"}},
    },
    "취소확정": {
        "order": {"orderId": "GP-2"},
        "productOrder": {"productOrderId": "PP-2", "claimStatus": "CANCEL_DONE",
                         "claimType": "CANCEL", "totalPaymentAmount": 250000},
    },
    "취소요청": {
        "order": {"orderId": "GP-3"},
        "productOrder": {"productOrderId": "PP-3", "claimStatus": "CANCEL_REQUEST",
                         "claimType": "CANCEL", "totalPaymentAmount": 70000},
    },
    "최상위-반품확정": {
        "order": {"orderId": "GP-4"},
        "productOrder": {"productOrderId": "PP-4", "totalPaymentAmount": 310000},
        "return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN",
                   "returnCompletedDate": "2026-09-01T10:00:00.000+09:00"},
    },
    "cancel-블록": {
        "order": {"orderId": "GP-5"},
        "productOrder": {"productOrderId": "PP-5", "totalPaymentAmount": 40000},
        "cancel": {"claimStatus": "CANCEL_DONE", "claimType": "CANCEL"},
    },
    "currentClaim": {
        "order": {"orderId": "GP-6"},
        "productOrder": {"productOrderId": "PP-6", "totalPaymentAmount": 55000},
        "currentClaim": {"cancel": {"claimStatus": "RETURN_DONE", "claimType": "RETURN"}},
    },
    "주문단위-클레임": {
        "order": {"orderId": "GP-7", "claimStatus": "CANCEL_DONE"},
        "productOrder": {"productOrderId": "PP-7", "totalPaymentAmount": 12000},
    },
    "빈원본": {},
}


def _order(session, name: str) -> Order:
    row = Order(customer_name=name, phone="010-0000-0000", address="서울",
                product="테스트", status="RECEIVED", received_date="2026-09-01")
    session.add(row)
    session.flush()
    return row


def _link(session, order_id, external_id: str, snapshot: dict) -> ExternalOrderLink:
    row = ExternalOrderLink(
        channel="NAVER",
        external_id=external_id,
        external_order_no=str((snapshot.get("order") or {}).get("orderId") or ""),
        sync_status="LINKED",
        place_order_status="NOT_YET",
        raw_snapshot=snapshot,
        order_id=order_id,
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.parametrize("shape_name", sorted(GHOST_SHAPES))
def test_projection_folds_the_same_as_the_full_snapshot(pg_session, shape_name):
    """축소 문서로 접은 버킷이 통째 문서와 한 글자도 다르지 않다."""
    from foms.services.integrations.naver_commerce.ghost_orders import (
        _fold_link,
        _ghost_snapshot_projection,
        _new_bucket,
    )

    full = GHOST_SHAPES[shape_name]
    order = _order(pg_session, f"투영-{shape_name}")
    row = _link(pg_session, order.id, f"GHOSTTHIN-{shape_name}", full)

    projected = pg_session.execute(
        select(_ghost_snapshot_projection(pg_session))
        .where(ExternalOrderLink.id == row.id)
    ).scalar_one()

    thick, thin = _new_bucket(), _new_bucket()
    _fold_link(thick, snapshot=full, order_no="2026000001", link_id=row.id)
    _fold_link(thin, snapshot=projected, order_no="2026000001", link_id=row.id)
    assert thick == thin


def test_ghost_scan_never_selects_the_snapshot_body(pg_session, pg_engine):
    """유령 스캔이 낸 SQL 에 ``raw_snapshot`` 본문 컬럼이 없다.

    투영은 ``raw_snapshot -> '...'`` 로 조각만 읽으므로 걸리지 않는다. 걸리는 것은
    본문을 통째로 싣는 ``external_order_links.raw_snapshot AS ...`` 뿐이다.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders

    order = _order(pg_session, "얇은-SQL")
    for index, (name, shape) in enumerate(sorted(GHOST_SHAPES.items())):
        _link(pg_session, order.id, f"GHOSTSQL-{index}", shape)
    pg_session.flush()

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        find_ghost_orders(pg_session)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    body = re.compile(r"external_order_links\.raw_snapshot\s+AS", re.IGNORECASE)
    offenders = [sql for sql in seen if body.search(sql)]
    assert not offenders, f"유령 스캔이 스냅샷 본문을 실었다: {offenders[:1]}"
    assert any("jsonb_build_object" in sql for sql in seen), "투영이 아예 안 걸렸다"


def test_ghost_band_lists_the_same_orders_and_amounts(pg_session):
    """띠 내용이 그대로다 — 전부 취소된 주문만, 금액 합까지 같다."""
    from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders

    # 유령: 붙은 링크가 전부 확정 취소·반품
    ghost = _order(pg_session, "유령-전부취소")
    _link(pg_session, ghost.id, "GHOSTBAND-A1", GHOST_SHAPES["취소확정"])
    _link(pg_session, ghost.id, "GHOSTBAND-A2", GHOST_SHAPES["최상위-반품확정"])
    # 유령 아님: 한 건이 살아 있다(부분 취소)
    alive = _order(pg_session, "정상-부분취소")
    _link(pg_session, alive.id, "GHOSTBAND-B1", GHOST_SHAPES["취소확정"])
    _link(pg_session, alive.id, "GHOSTBAND-B2", GHOST_SHAPES["정상"])
    pg_session.flush()

    result = find_ghost_orders(pg_session)
    ids = [row["order_id"] for row in result["rows"]]

    assert ghost.id in ids, "전부 취소된 주문이 띠에서 빠졌다"
    assert alive.id not in ids, "부분 취소 주문이 유령으로 잡혔다"
    row = next(r for r in result["rows"] if r["order_id"] == ghost.id)
    assert row["naver_amount_total"] == 250000 + 310000, "금액 합이 갈렸다"
    assert row["naver_link_count"] == 2


def test_mirror_columns_keep_the_snapshot_untouched(pg_session, pg_engine):
    """사본이 채워진 행만 있으면 유령 스캔이 ``raw_snapshot`` 을 **한 번도** 안 읽는다.

    §13 의 투영은 "덜 읽는다" 였고 NVMIRROR-01 은 "안 읽는다" 다. 그 차이를 여기서 잠근다.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders
    from foms.services.integrations.naver_commerce.link_mirror import apply_claim_mirror

    order = _order(pg_session, "사본-채운행")
    for index, (name, shape) in enumerate(sorted(GHOST_SHAPES.items())):
        row = _link(pg_session, order.id, f"GHOSTMIRROR-{index}", shape)
        apply_claim_mirror(row, shape)
    pg_session.flush()

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        find_ghost_orders(pg_session)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    touched = [sql for sql in seen if "raw_snapshot" in sql.lower()]
    assert not touched, f"사본이 있는데도 스냅샷을 읽었다: {touched[:1]}"


def test_stale_rows_still_fall_back_to_the_snapshot(pg_session, pg_engine):
    """사본이 NULL 인 행(백필 전)은 스냅샷으로 폴백한다 — 그 행만, 답은 그대로.

    음성 대조군이다: 위 테스트가 "안 읽는다" 를 증명하므로, 여기서 "필요하면 읽는다" 까지
    보여야 폴백이 살아 있는지 알 수 있다.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders

    ghost = _order(pg_session, "백필전-전부취소")
    # 사본을 **채우지 않는다**(NULL) — 옛 행과 같은 상태.
    _link(pg_session, ghost.id, "GHOSTSTALE-1", GHOST_SHAPES["취소확정"])
    _link(pg_session, ghost.id, "GHOSTSTALE-2", GHOST_SHAPES["최상위-반품확정"])
    pg_session.flush()

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        result = find_ghost_orders(pg_session)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    ids = [row["order_id"] for row in result["rows"]]
    assert ghost.id in ids, "백필 전 행이 띠에서 빠졌다 — 폴백이 죽었다"
    row = next(r for r in result["rows"] if r["order_id"] == ghost.id)
    assert row["naver_amount_total"] == 250000 + 310000
    assert any("jsonb_build_object" in sql for sql in seen), "폴백이 투영을 안 썼다"
