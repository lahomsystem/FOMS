"""처리 목록 모집단 계약 — 수집이 깨진 링크는 불가역 호출 대상이 아니다.

v2 에서 `_place_groups` 는 '발주확인 전' **탭 전용**이라 `FAILED`/`PENDING_REVIEW` 가
섞여도 처리 큐·nav 뱃지에는 안 들어갔다. v3 가 두 목록을 합치면서 그 건들이
"처리할 집"으로 세어지고 **벌크 발주확인 후보로 체크박스가 열렸다**(2026-08-23 발견).
발주확인은 네이버로 나가는 불가역 호출이라 원본이 불완전한 건을 대상에 올리지 않는다.
"""
from __future__ import annotations

import pytest

from models import ExternalOrderLink


def _link(db, *, external_id: str, status: str, name: str) -> ExternalOrderLink:
    """발주확인 전 상태의 수집 링크 한 건을 만든다."""
    row = ExternalOrderLink(
        channel="NAVER",
        external_id=external_id,
        external_order_no=external_id[:-2],
        sync_status=status,
        place_order_status="NOT_YET",
        raw_snapshot={
            "order": {"orderId": external_id[:-2], "ordererName": name},
            "productOrder": {
                "productOrderId": external_id,
                "productName": f"{name} 상품",
                "quantity": 1,
                "totalPaymentAmount": 10000,
                "productOrderStatus": "PAYED",
                "placeOrderStatus": "NOT_YET",
                "shippingAddress": {"name": name, "tel1": "010-0000-0000",
                                    "baseAddress": "서울시 어딘가", "detailedAddress": "101호"},
            },
        },
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("broken_status", ["FAILED", "PENDING_REVIEW"])
def test_broken_collections_never_enter_the_work_list(app, broken_status):
    """수집 실패·보류 건은 처리 목록에도 뱃지에도 들어가지 않는다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _link(db_session, external_id="20260823000011", status="COLLECTED", name="정상수집")
    _link(db_session, external_id="20260823000021", status=broken_status, name="깨진수집")

    groups, _truncated = _work_groups(db_session)
    names = [g["customer_name"] for g in groups]

    assert "정상수집" in names
    assert "깨진수집" not in names, (
        f"{broken_status} 수집분이 처리 목록에 올라왔다 — 벌크 발주확인 후보가 된다"
    )


def test_badge_counts_the_same_population_as_the_list(app):
    """nav 뱃지는 목록과 같은 수여야 한다 — 깨진 수집분을 세면 다시 어긋난다.

    기대값을 **직접 박는다**. `len(_work_groups(...))` 끼리 비교하면 구현을 통째로
    바꿔도 통과하는 동어반복이라 어떤 회귀도 못 잡는다(2026-08-23 리뷰).
    """
    from db import db_session
    from foms.services.integrations.naver_commerce.triage_count import (
        compute_triage_pending_count,
    )
    from foms.web.admin.naver_ingest import _work_groups

    _link(db_session, external_id="20260823000031", status="COLLECTED", name="정상수집")
    _link(db_session, external_id="20260823000041", status="FAILED", name="실패수집")

    # 정상 1집만 세어야 한다 — 실패 수집분은 목록에도 뱃지에도 없다.
    assert compute_triage_pending_count(db_session, workbench=True) == 1
    groups, _truncated = _work_groups(db_session)
    assert [g["customer_name"] for g in groups] == ["정상수집"]


def test_badge_survives_a_broken_snapshot(app):
    """뱃지 계산이 터져도 페이지는 살아야 한다 — 뱃지는 부가 정보다(리뷰 M1).

    워크벤치 경로는 순수 COUNT 가 아니라 화면 목록 로직 전부를 돈다. 원본 하나가
    예상 밖 모양이면 SQL 예외가 아닌 것이 새어 nav 렌더하는 **모든 페이지**가 죽는다.
    """
    from db import db_session
    from foms.services.integrations.naver_commerce import triage_count as tc

    def boom(_db):
        raise TypeError("깨진 스냅샷")

    original = tc._workbench_group_count
    tc._workbench_group_count = boom
    try:
        assert tc.compute_triage_pending_count(db_session, workbench=True) == 0
    finally:
        tc._workbench_group_count = original


def test_sibling_claim_locks_the_row_even_when_it_came_from_the_queue(app):
    """확인 끝난 형제의 취소가 큐 출신 집에도 반영돼야 한다 (리뷰 H1).

    v2 는 체크박스가 '발주확인 전' 목록 루프 안에만 있어 구조적으로 안전했다. v3 가 두
    목록을 합치면서 **원천 1(확인 큐) 출신 집이 형제 클레임 검사를 건너뛰었고**, 잠겨야 할
    집에 체크박스가 열려 벌크 발주확인 후보가 됐다. 그러면 목록은 "보내도 된다"고 하고
    상세는 "취소·반품이라 닫혀 있다"고 하는, 한 화면 안의 모순이 된다.
    """
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    # 형제 A: 확인 대기 + 발주확인 전 → 큐(원천 1)에 뜬다.
    a = _link(db_session, external_id="20260823000051", status="COLLECTED", name="형제집")
    # 형제 B: 같은 집인데 확인 완료 + 발주확인 완료 + 네이버 취소요청 → 큐에도 place 에도 없다.
    b = _link(db_session, external_id="20260823000052", status="LINKED", name="형제집")
    b.external_order_no = a.external_order_no
    b.raw_snapshot = dict(a.raw_snapshot)
    po = dict(b.raw_snapshot["productOrder"])
    po["productOrderId"] = "20260823000052"
    po["placeOrderStatus"] = "OK"
    po["claimType"] = "CANCEL"
    po["claimStatus"] = "CANCEL_REQUEST"
    b.raw_snapshot = dict(b.raw_snapshot, productOrder=po)
    b.place_order_status = "OK"
    from datetime import datetime
    b.reviewed_at = datetime(2026, 8, 23, 0, 0, 0)
    db_session.commit()

    groups, _truncated = _work_groups(db_session)
    house = [g for g in groups if g["customer_name"] == "형제집"]
    assert house, "집이 목록에서 사라지면 안 된다 — 잠긴 줄로 남아야 한다"
    assert house[0]["claim_blocking"] is True, (
        "형제 취소가 반영되지 않았다 — 체크박스가 열려 벌크 발주확인 대상이 된다"
    )


def test_bulk_restates_the_household_the_worker_will_touch(app):
    """벌크 재진술 건수 == 워커가 처리할 상품주문 수 (리뷰 H2).

    `count` 는 확인 대기로 좁혀진 화면 모집단 크기고, 워커 `_links_of_group` 은
    `reviewed_at` 과 무관하게 집 전체를 처리한다. 그 차이가 모달 문장에 그대로 나오면
    "1건 보냅니다"라고 읽고 3건이 나간다.
    """
    from datetime import datetime

    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    a = _link(db_session, external_id="20260823000061", status="COLLECTED", name="큰집")
    for suffix in ("62", "63"):
        sib = _link(db_session, external_id=f"202608230000{suffix}",
                    status="LINKED", name="큰집")
        sib.external_order_no = a.external_order_no
        po = dict(a.raw_snapshot["productOrder"])
        po["productOrderId"] = f"202608230000{suffix}"
        sib.raw_snapshot = dict(a.raw_snapshot, productOrder=po)
        sib.reviewed_at = datetime(2026, 8, 23, 0, 0, 0)
    db_session.commit()

    groups, _truncated = _work_groups(db_session)
    house = [g for g in groups if g["customer_name"] == "큰집"][0]

    assert house["count"] == 1, "전제: 화면 모집단은 1건만 본다"
    assert house["household_count"] == 3, (
        "벌크가 재진술할 수가 워커가 처리할 수와 다르다"
    )
