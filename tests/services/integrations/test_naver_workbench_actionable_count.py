"""스트립·탭 배지·nav 뱃지는 **손댈 수 있는 집**만 센다 (계약 §2.4, 2026-08-24 개정).

취소·반품 집은 목록에 남지만 어떤 액션도 되지 않는다(체크박스도 disabled). 그런데
"처리할 집 N집"과 nav 뱃지가 그 집까지 세어서, 담당자가 매일 아침 보는 업무량이 실제
처리 대상보다 컸다 — 2026-08-24 스테이징 실측으로 확인 큐 **72집 중 13집(18%)**이 그랬다.

목록에서 지우지는 않는다. STAFF 는 이력 탭이 없어 '취소·반품' 칩이 유일한 조회 창구이고
그 칩의 모집단도 이 목록이다. 지우면 다시 찾을 자리가 사라진다(절대 규칙 3·4).

그래서 숫자만 쪼갠다. 여기서 지키는 산수는 하나다:

    actionable_count + locked_count == group_count == filter_counts["all"]
    locked_count == filter_counts["claim"]

이 등식이 깨지면 화면이 "두 말"을 하기 시작한다.
"""
from __future__ import annotations

import datetime

from models import ExternalOrderLink

_REVIEWED_AT = datetime.datetime(2026, 8, 24, 0, 0, 0)


def _link(db, *, external_id: str, order_no: str, name: str, tel: str,
          claim: str | None = None, triage_state: dict | None = None) -> ExternalOrderLink:
    """확인 대기 수집 링크 1건(집 하나 = 링크 하나)."""
    product_order = {
        "productOrderId": external_id,
        "productName": f"{name} 상품",
        "totalPaymentAmount": 100000,
        "placeOrderStatus": "NOT_YET",
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": f"서울 {name}로 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    row = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="COLLECTED", place_order_status="NOT_YET", triage_state=triage_state,
        raw_snapshot={"order": {"orderId": order_no}, "productOrder": product_order},
    )
    db.add(row)
    db.commit()
    return row


def _seed(db) -> None:
    """손댈 수 있는 집 3 + 손댈 수 없는 집 2(원본 클레임 1 · 우리가 낸 취소 1)."""
    for index in range(3):
        _link(db, external_id=f"2026082490000{index}", order_no=f"N-OK-{index}",
              name=f"정상{index}", tel=f"010-3000-000{index}")
    _link(db, external_id="20260824900010", order_no="N-CLAIM", name="취소요청",
          tel="010-3000-0010", claim="CANCEL_REQUEST")
    _link(db, external_id="20260824900011", order_no="N-OURS", name="우리취소",
          tel="010-3000-0011",
          triage_state={"fulfillment": {"canceled_at": "2026-08-24T00:00:00"}})


def test_actionable_plus_locked_equals_the_list(app):
    """쪼갠 두 수의 합이 목록 길이·칩 '전체'와 정확히 같다."""
    from db import db_session
    from foms.web.admin.naver_ingest import (
        _actionable_count,
        _filter_counts,
        _work_groups,
    )

    _seed(db_session)
    groups, _truncated = _work_groups(db_session)
    counts = _filter_counts(groups)
    actionable = _actionable_count(groups)
    locked = len(groups) - actionable

    assert actionable == 3
    assert locked == 2
    assert actionable + locked == len(groups) == counts["all"]
    assert locked == counts["claim"], "'손대지 않음'과 취소·반품 칩의 모집단은 하나다"


def test_nav_badge_says_the_same_number_as_the_tab(app):
    """nav 뱃지 == 스트립 == 탭 배지 (계약 §2.4)."""
    from db import db_session
    from foms.services.integrations.naver_commerce.triage_count import (
        _workbench_group_count,
    )
    from foms.web.admin.naver_ingest import _actionable_count, _work_groups

    _seed(db_session)
    groups, _truncated = _work_groups(db_session)

    assert _workbench_group_count(db_session) == _actionable_count(groups) == 3


def test_locked_households_stay_in_the_list(app):
    """숫자에서 빠져도 **목록에는 남는다** — STAFF 가 다시 찾을 자리다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _group_matches_filter, _work_groups

    _seed(db_session)
    groups, _truncated = _work_groups(db_session)

    locked = [g for g in groups if _group_matches_filter(g, "claim")]
    assert len(locked) == 2, "잠긴 집이 목록에서 사라졌다 — 다시 찾을 자리가 없어진다"
    assert all(group["locked"] for group in locked)
    assert not any(group["can_pick"] for group in locked)


def test_thin_badge_path_agrees_with_the_screen(app):
    """뱃지의 얇은 읽기 경로도 같은 수를 낸다(모드가 갈리면 계약이 깨진다)."""
    from db import db_session
    from foms.web.admin.naver_ingest import _actionable_count, _work_groups

    _seed(db_session)
    rich, _ = _work_groups(db_session, display=True)
    thin, _ = _work_groups(db_session, display=False)

    assert _actionable_count(rich) == _actionable_count(thin) == 3
