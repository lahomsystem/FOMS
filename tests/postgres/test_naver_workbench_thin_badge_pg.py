"""nav 뱃지 얇게 읽기 — **투영이 통째 스냅샷과 같은 판정을 낸다**는 증명 (PGTEST-00 lane).

``_snapshot_projection`` 은 판정에 필요한 경로만 담은 축소 문서를 SQL 이 조립하게 한다.
판정 함수를 두 벌로 만들지 않으려는 것이므로, 지켜야 할 것은 하나다:
**축소 문서로 부른 결과 == 통째 문서로 부른 결과.**

여기서 재는 것 세 가지:

1. 모양별 충실성 — 중첩/평평/``cancel``/``currentClaim``/빈 원본에서
   ``group_key``·``extract_claim``·``extract_place_status`` 가 같은 값을 낸다.
2. 실제로 얇은가 — 얇은 경로가 낸 SQL 어디에도 ``raw_snapshot`` **본문 컬럼**이 없다.
3. 모집단 동치 — 진짜 투영이 걸린 상태에서 ``display`` 두 모드의 집 목록이 같다
   (SQLite 레인은 투영이 폴백이라 이 축을 증명하지 못한다).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import datetime
import re

import pytest
from sqlalchemy import event, select

from models import ExternalOrderLink

#: 판정 3종이 읽는 모양을 한 번씩 태우는 원본들. ``id`` 는 사람이 읽는 이름표다.
SNAPSHOT_SHAPES = {
    "중첩-정상": {
        "order": {"orderId": "N-1"},
        "productOrder": {"productOrderId": "P-1", "placeOrderStatus": "NOT_YET",
                         "productName": "정상 상품", "totalPaymentAmount": 100000,
                         "shippingAddress": {"name": "홍길동", "tel1": "010-1111-1111",
                                             "baseAddress": "서울 A로 1",
                                             "detailedAddress": "101호"}},
    },
    "중첩-상품주문클레임": {
        "order": {"orderId": "N-2"},
        "productOrder": {"productOrderId": "P-2", "claimStatus": "CANCEL_REQUEST",
                         "claimType": "CANCEL", "placeOrderStatus": "OK",
                         "shippingAddress": {"tel1": "010-2222-2222",
                                             "baseAddress": "서울 B로 2",
                                             "detailedAddress": "202호"}},
    },
    "주문단위클레임": {
        "order": {"orderId": "N-3", "claimStatus": "RETURN_REQUEST",
                  "placeOrderStatus": "OK"},
        "productOrder": {"productOrderId": "P-3",
                         "shippingAddress": {"tel1": "010-3333-3333",
                                             "baseAddress": "서울 C로 3"}},
    },
    "cancel-블록": {
        "order": {"orderId": "N-4"},
        "productOrder": {"productOrderId": "P-4",
                         "shippingAddress": {"tel1": "010-4444-4444",
                                             "baseAddress": "서울 D로 4"}},
        "cancel": {"claimStatus": "CANCEL_DONE", "claimType": "CANCEL",
                   "cancelReason": "고객 변심", "claimRequestDate": "2026-08-24"},
    },
    "currentClaim-블록": {
        "order": {"orderId": "N-5"},
        "productOrder": {"productOrderId": "P-5",
                         "shippingAddress": {"tel1": "010-5555-5555",
                                             "baseAddress": "서울 E로 5"}},
        "currentClaim": {"cancel": {"claimStatus": "RETURN_DONE",
                                    "returnReason": "파손", "claimType": "RETURN"}},
    },
    "평평한응답": {
        "productOrderId": "P-6", "claimStatus": "CANCEL_REQUEST", "claimType": "CANCEL",
        "placeOrderStatus": "NOT_YET",
        "shippingAddress": {"tel1": "010-6666-6666", "baseAddress": "서울 F로 6",
                            "detailedAddress": "606호"},
    },
    # 2026-08-28 (R-7): 투영이 `return`·`exchange`·`delivery` 를 통째로 버려서, 이 모양은
    # 얇은 경로에서 "클레임 없음"으로 읽혔다(두꺼운 경로는 "반품 완료"). 배지 수 ≠ 목록이
    # 되는 바로 그 결함이고, top-level `return.claimStatus` 는 스테이징 실측 키다.
    "return-블록": {
        "order": {"orderId": "N-9"},
        "productOrder": {"productOrderId": "P-9",
                         "shippingAddress": {"tel1": "010-9999-9999",
                                             "baseAddress": "서울 I로 9"}},
        "return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN",
                   "returnReason": "PRODUCT_DEFECT", "claimRequestDate": "2026-08-26",
                   "returnCompletedDate": "2026-08-27T10:02:11.000+09:00",
                   "collectDeliveryMethod": "RETURN_INDIVIDUAL"},
        "delivery": {"sendDate": "2026-08-20T10:00:00.000+09:00"},
    },
    "exchange-블록": {
        "order": {"orderId": "N-10"},
        "productOrder": {"productOrderId": "P-10",
                         "shippingAddress": {"tel1": "010-1010-1010",
                                             "baseAddress": "서울 J로 10"}},
        "exchange": {"claimStatus": "EXCHANGE_REQUEST", "claimType": "EXCHANGE",
                     "claimRequestDate": "2026-08-26"},
    },
    "빈원본": {},
    "주소없음": {"order": {"orderId": "N-8"}, "productOrder": {"productOrderId": "P-8"}},
}


def _insert(session, external_id: str, snapshot: dict, **kwargs) -> ExternalOrderLink:
    """수집 링크 1건을 심는다(발주확인 전·확인 대기가 기본)."""
    row = ExternalOrderLink(
        channel="NAVER",
        external_id=external_id,
        external_order_no=str((snapshot.get("order") or {}).get("orderId") or ""),
        sync_status=kwargs.pop("sync_status", "COLLECTED"),
        place_order_status=kwargs.pop("place_order_status", "NOT_YET"),
        raw_snapshot=snapshot,
        **kwargs,
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.parametrize("shape_name", sorted(SNAPSHOT_SHAPES))
def test_projection_decides_the_same_as_the_full_snapshot(pg_session, shape_name):
    """축소 문서로 부른 판정 3종이 통째 문서와 **한 글자도 다르지 않다**."""
    from foms.services.integrations.naver_commerce.mapping import (
        extract_claim,
        extract_place_status,
        group_key,
    )
    from foms.web.admin.naver_ingest import _snapshot_projection

    full = SNAPSHOT_SHAPES[shape_name]
    row = _insert(pg_session, f"THIN-{shape_name}", full)

    projected = pg_session.execute(
        select(_snapshot_projection(pg_session)).where(ExternalOrderLink.id == row.id)
    ).scalar_one()

    assert group_key(projected) == group_key(full), "집 키가 갈리면 뱃지와 목록이 어긋난다"
    assert extract_claim(projected) == extract_claim(full)
    # 반품 축·발송 사실도 같아야 한다 — `is_return_pending` 이 둘 다 읽는다(R-7).
    from foms.services.integrations.naver_commerce.mapping import (
        extract_delivery, extract_return_axis,
    )
    assert extract_return_axis(projected) == extract_return_axis(full)
    assert extract_delivery(projected) == extract_delivery(full)
    assert (extract_place_status(projected)["confirmed"]
            == extract_place_status(full)["confirmed"])


def test_thin_path_never_selects_the_snapshot_body(pg_session, pg_engine):
    """얇은 경로가 낸 SQL 어디에도 ``raw_snapshot`` **본문 컬럼**이 없다.

    투영은 ``raw_snapshot -> '...'`` 로 조각만 읽으므로 걸리지 않는다. 걸리는 것은
    본문을 통째로 싣는 ``external_order_links.raw_snapshot AS ...`` 뿐이다.
    """
    from foms.web.admin.naver_ingest import _work_groups

    for index, (name, shape) in enumerate(sorted(SNAPSHOT_SHAPES.items())):
        _insert(pg_session, f"THINSQL-{index}", shape)
    pg_session.flush()

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        _work_groups(pg_session, display=False)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    body = re.compile(r"external_order_links\.raw_snapshot\s+AS", re.IGNORECASE)
    offenders = [sql for sql in seen if body.search(sql)]
    assert not offenders, f"얇은 경로가 스냅샷 본문을 실었다: {offenders[:1]}"
    assert any("jsonb_build_object" in sql for sql in seen), "투영이 아예 안 걸렸다"


def test_population_matches_across_modes_with_the_real_projection(pg_session):
    """진짜 투영이 걸린 상태에서 두 모드의 집 목록이 같다(계약 §2.4)."""
    from foms.web.admin.naver_ingest import _filter_counts, _work_groups

    reviewed = datetime.datetime(2026, 8, 24, 0, 0, 0)
    for index, (name, shape) in enumerate(sorted(SNAPSHOT_SHAPES.items())):
        _insert(pg_session, f"THINPOP-{index}", shape)
    # 큐 밖 발주확인 전 집 + 이미 발주확인이 끝난 취소 형제(집 전체를 잠그는 자리)
    _insert(pg_session, "THINPOP-OUT", SNAPSHOT_SHAPES["중첩-정상"],
            sync_status="LINKED", reviewed_at=reviewed)
    _insert(pg_session, "THINPOP-SIB", SNAPSHOT_SHAPES["중첩-상품주문클레임"],
            sync_status="LINKED", place_order_status="OK", reviewed_at=reviewed)
    pg_session.flush()

    rich, rich_truncated = _work_groups(pg_session, display=True)
    thin, thin_truncated = _work_groups(pg_session, display=False)

    assert [g["key"] for g in rich] == [g["key"] for g in thin]
    assert rich_truncated == thin_truncated
    assert _filter_counts(rich) == _filter_counts(thin)
    for left, right in zip(rich, thin):
        for field in ("place_pending", "claim_blocking", "canceled", "locked",
                      "can_pick", "count", "household_count", "household_place_pending",
                      "place_pending_count", "dispatched_count",
                      "dispatch_pending_count", "in_queue"):
            assert left[field] == right[field], f"{field} 가 모드에 따라 갈렸다"
