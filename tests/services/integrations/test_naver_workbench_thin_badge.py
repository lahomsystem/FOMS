"""nav 뱃지 얇게 읽기 — **모집단이 아니라 문서의 두께만** 바뀐다는 계약.

뱃지는 모든 페이지 렌더에 실린다. 2026-08-24 실측으로 3.3KB ``raw_snapshot`` 본문이
행 조회 비용의 약 80% 였다(게이트 ON 콜드 113ms). 그래서 뱃지 경로는 판정에 필요한 경로만
담은 축소 문서를 읽는다(``_snapshot_projection``).

**여기서 지키는 것**: 뱃지용 함수를 따로 만들지 않았다는 사실. `display=False` 는 같은
`_work_groups` 를 같은 술어·같은 병합·같은 캡으로 돌린다. 그러니 집 키 목록·필터 숫자·
`truncated` 가 두 모드에서 같아야 한다 — 계약 §2.4(뱃지 == 탭 숫자 == 칩 '전체')의 증명이
바로 이 동치다. 이 저장소는 모집단이 두 벌이 되어 nav 67·탭 45, nav 140·필터 43 으로
어긋난 적이 있다.

(SQLite 레인에서는 투영이 `raw_snapshot` 통째로 폴백한다 — 여기서 재는 것은 `display`
배선이 모집단을 건드리지 않는다는 사실이고, 투영 자체의 충실성은 PG 레인이 맡는다:
``tests/postgres/test_naver_workbench_thin_badge_pg.py``.)
"""
from __future__ import annotations

import datetime
from typing import Any

from models import ExternalOrderLink

#: 큐에서 빠진(확인 완료) 링크의 확인 시각.
_REVIEWED_AT = datetime.datetime(2026, 8, 24, 0, 0, 0)

#: 두 모드가 반드시 같아야 하는 집 필드 — **어떤 술어라도 읽는 값**은 전부 여기 있다.
#: 표시 전용(제품명·고객명·금액·다음 할 일)은 얇은 경로에서 비므로 제외한다.
POPULATION_FIELDS = (
    "key", "count", "extra_count", "place_pending", "place_pending_count",
    "claim_blocking", "canceled", "relation", "close_now", "locked", "can_pick",
    "in_queue", "dispatched", "dispatched_any", "dispatched_count",
    "dispatch_pending_count",
    "promotable_count", "household_count", "household_place_pending",
)


def _snapshot(*, order_no: str, po_id: str, name: str, tel: str, addr: str,
              detail: str = "101호", place: str = "NOT_YET",
              claim: str | None = None, amount: int = 100000) -> dict[str, Any]:
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
          claim: str | None = None, reviewed_at=None,
          triage_state: dict | None = None) -> ExternalOrderLink:
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

    확인 대기 집 · 형제 2건짜리 집 · **분할배송**(같은 주문번호·다른 주소) ·
    취소·반품 집 · 우리가 취소한 집 · 큐 밖 발주확인 전 집 · 이미 발주확인 끝난 형제.
    """
    _link(db, external_id="20260824000001", order_no="N-A", name="가집",
          tel="010-1000-0001", addr="서울 A로 1")
    # 같은 집(형제 2건)
    _link(db, external_id="20260824000002", order_no="N-B", name="나집",
          tel="010-1000-0002", addr="서울 B로 2")
    _link(db, external_id="20260824000003", order_no="N-B", name="나집",
          tel="010-1000-0002", addr="서울 B로 2")
    # 분할배송 — 주문번호가 같아도 주소가 다르면 다른 집이다
    _link(db, external_id="20260824000004", order_no="N-C", name="다집",
          tel="010-1000-0003", addr="서울 C로 3", detail="201호")
    _link(db, external_id="20260824000005", order_no="N-C", name="다집",
          tel="010-1000-0003", addr="서울 C로 3", detail="202호")
    # 취소·반품 집(원본 claimStatus)
    _link(db, external_id="20260824000006", order_no="N-D", name="라집",
          tel="010-1000-0004", addr="서울 D로 4", claim="CANCEL_REQUEST")
    # 우리가 취소한 집(triage_state 표식)
    _link(db, external_id="20260824000007", order_no="N-E", name="마집",
          tel="010-1000-0005", addr="서울 E로 5",
          triage_state={"fulfillment": {"canceled_at": "2026-08-24T00:00:00"}})
    # 큐에서 빠졌지만(확인 완료) 아직 발주확인 전인 집
    _link(db, external_id="20260824000008", order_no="N-F", name="바집",
          tel="010-1000-0006", addr="서울 F로 6", status="LINKED",
          reviewed_at=_REVIEWED_AT)
    # 이미 발주확인이 끝난 형제(취소·반품) — 집 전체를 잠가야 하는 자리
    _link(db, external_id="20260824000009", order_no="N-G", name="사집",
          tel="010-1000-0007", addr="서울 G로 7")
    _link(db, external_id="20260824000010", order_no="N-G", name="사집",
          tel="010-1000-0007", addr="서울 G로 7", place="OK", claim="RETURN_REQUEST",
          reviewed_at=_REVIEWED_AT)
    # 발송처리가 나간 형제가 섞인 집
    _link(db, external_id="20260824000011", order_no="N-H", name="아집",
          tel="010-1000-0008", addr="서울 H로 8",
          triage_state={"fulfillment": {"dispatched_at": "2026-08-24T00:00:00"}})


def test_thin_and_rich_agree_on_population(app):
    """얇은 문서로 읽어도 **집 목록·잠금·선택 가능 여부가 한 글자도 다르지 않다**."""
    from db import db_session
    from foms.web.admin.naver_ingest import _filter_counts, _work_groups

    _seed_mixed(db_session)

    rich, rich_truncated = _work_groups(db_session, display=True)
    thin, thin_truncated = _work_groups(db_session, display=False)

    assert [g["key"] for g in rich] == [g["key"] for g in thin]
    assert rich_truncated == thin_truncated
    assert _filter_counts(rich) == _filter_counts(thin)
    for left, right in zip(rich, thin):
        assert ({name: left[name] for name in POPULATION_FIELDS}
                == {name: right[name] for name in POPULATION_FIELDS})


def test_badge_equals_work_tab_count(app):
    """nav 뱃지 == 처리 탭 숫자 == 손댈 수 있는 집 (계약 §2.4, 2026-08-24 개정).

    2026-08-24 개정 전에는 목록 길이(칩 '전체')와도 같았다. 지금은 취소·반품 집이
    숫자에서 빠지고 스트립의 '손대지 않음'이 그 차이를 말한다.
    """
    from db import db_session
    from foms.services.integrations.naver_commerce.triage_count import (
        _workbench_group_count,
    )
    from foms.web.admin.naver_ingest import (
        _actionable_count,
        _filter_counts,
        _work_groups,
    )

    _seed_mixed(db_session)

    groups, _truncated = _work_groups(db_session, display=True)
    counts = _filter_counts(groups)
    assert _workbench_group_count(db_session) == _actionable_count(groups)
    assert _actionable_count(groups) + counts["claim"] == len(groups) == counts["all"]


def test_thin_path_does_not_load_orders(app, monkeypatch):
    """얇은 경로는 표시용 주문 조회를 **아예 내지 않는다**(고객명은 안 쓰므로)."""
    from db import db_session
    from foms.web.admin import naver_ingest

    _seed_mixed(db_session)
    calls: list[int] = []
    original = naver_ingest._orders_by_id
    monkeypatch.setattr(naver_ingest, "_orders_by_id",
                        lambda db, links: (calls.append(len(links)), original(db, links))[1])

    naver_ingest._work_groups(db_session, display=False)
    assert calls == []

    naver_ingest._work_groups(db_session, display=True)
    assert calls, "표시 경로는 주문을 읽어야 한다(고객명·다음 할 일)"
