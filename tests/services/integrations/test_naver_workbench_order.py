"""처리 목록의 순서 — 중간에서 시간이 되감기면 안 된다 (2026-08-24 감사).

목록은 두 원천을 합친 것이다: 확인 큐(최신순)와 '발주확인 전' 집(최신순).
:func:`_work_groups` 는 큐 키 뒤에 발주확인 전 키를 **이어 붙이기만** 했다. 그래서
접수시각이 아래로 내려가다가 목록 중간에서 다시 최신으로 튀었다 — 담당자는 목록이
시간순이라고 믿고 훑는데 그 믿음이 중간에서 깨진다.

**왜 이게 나쁜가**: 발송기한을 넘기면 네이버가 자동으로 취소할 수 있다. 기한이 임박한
집은 정의상 오래 전에 수집된 집인데, 순서가 두 덩어리로 갈라지면 "아래로 갈수록 오래된
집"이라는 유일한 단서가 무너진다.
"""
from __future__ import annotations

import datetime

from models import ExternalOrderLink


def _link(db, *, external_id: str, order_no: str, name: str, tel: str,
          created_at: datetime.datetime, reviewed_at=None,
          place: str = "NOT_YET") -> ExternalOrderLink:
    """수집 링크 1건. ``reviewed_at`` 을 주면 큐에서 빠져 '발주확인 전' 원천으로만 들어온다."""
    row = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="COLLECTED" if reviewed_at is None else "LINKED",
        place_order_status=place, reviewed_at=reviewed_at, created_at=created_at,
        raw_snapshot={
            "order": {"orderId": order_no},
            "productOrder": {
                "productOrderId": external_id, "productName": f"{name} 상품",
                "totalPaymentAmount": 100000, "placeOrderStatus": place,
                "shippingAddress": {"name": name, "tel1": tel,
                                    "baseAddress": f"서울 {name}로 1",
                                    "detailedAddress": "101호"},
            },
        },
    )
    db.add(row)
    db.commit()
    return row


def _seed_interleaved(db) -> None:
    """큐 집과 큐 밖 집의 접수시각을 **엇갈리게** 심는다.

    시각 순서: 08-20(큐밖) · 08-21(큐) · 08-22(큐밖) · 08-23(큐).
    이어 붙이기만 하면 큐 두 개가 먼저 오고(23·21) 큐 밖 두 개가 뒤에 온다(22·20) —
    21 다음에 22 가 나오면서 시간이 되감긴다.
    """
    reviewed = datetime.datetime(2026, 8, 24, 0, 0, 0)
    _link(db, external_id="20260820000001", order_no="N-ORD-20", name="이십일",
          tel="010-4000-0020", created_at=datetime.datetime(2026, 8, 20, 9, 0),
          reviewed_at=reviewed)
    _link(db, external_id="20260821000001", order_no="N-ORD-21", name="이십이",
          tel="010-4000-0021", created_at=datetime.datetime(2026, 8, 21, 9, 0))
    _link(db, external_id="20260822000001", order_no="N-ORD-22", name="이십삼",
          tel="010-4000-0022", created_at=datetime.datetime(2026, 8, 22, 9, 0),
          reviewed_at=reviewed)
    _link(db, external_id="20260823000001", order_no="N-ORD-23", name="이십사",
          tel="010-4000-0023", created_at=datetime.datetime(2026, 8, 23, 9, 0))


def test_list_never_rewinds_in_time(app):
    """목록의 접수시각이 위에서 아래로 **단조 감소**한다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_interleaved(db_session)
    groups, _truncated = _work_groups(db_session)

    stamps = [group["created_sort"] for group in groups]
    assert stamps == sorted(stamps, reverse=True), (
        f"목록 중간에서 시간이 되감긴다: {[group['created_at'] for group in groups]}"
    )


def test_order_is_the_same_in_the_badge_path(app):
    """얇은 읽기 경로도 같은 순서를 낸다(모드가 갈리면 캡이 서로 다른 집을 자른다)."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_interleaved(db_session)
    rich, _ = _work_groups(db_session, display=True)
    thin, _ = _work_groups(db_session, display=False)

    assert [group["key"] for group in rich] == [group["key"] for group in thin]


def _seed_due(db) -> None:
    """발송기한이 다른 집 3개 + 기한 없는 집 1개."""
    def _with_due(external_id, order_no, name, tel, created, due):
        row = _link(db, external_id=external_id, order_no=order_no, name=name,
                    tel=tel, created_at=created)
        snap = dict(row.raw_snapshot)
        product_order = dict(snap["productOrder"])
        if due:
            product_order["shippingDueDate"] = due
        snap["productOrder"] = product_order
        row.raw_snapshot = snap
        db.commit()

    _with_due("20260810000001", "N-DUE-A", "느긋", "010-5000-0001",
              datetime.datetime(2026, 8, 23, 9, 0), "2026-09-30T00:00:00.0+09:00")
    _with_due("20260810000002", "N-DUE-B", "급함", "010-5000-0002",
              datetime.datetime(2026, 8, 22, 9, 0), "2026-09-01T00:00:00.0+09:00")
    _with_due("20260810000003", "N-DUE-C", "중간", "010-5000-0003",
              datetime.datetime(2026, 8, 21, 9, 0), "2026-09-15T00:00:00.0+09:00")
    _with_due("20260810000004", "N-DUE-D", "기한없음", "010-5000-0004",
              datetime.datetime(2026, 8, 20, 9, 0), None)


def test_due_sort_puts_the_nearest_deadline_first(app):
    """발송기한 임박순 — 기한을 넘기면 네이버가 자동 취소할 수 있다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_due(db_session)
    groups, _truncated = _work_groups(db_session, sort="due")

    assert [group["customer_name"] for group in groups][:3] == ["급함", "중간", "느긋"]


def test_due_sort_puts_missing_deadlines_last(app):
    """기한이 없는 집이 '제일 급한 집'으로 맨 앞에 오면 안 된다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_due(db_session)
    groups, _truncated = _work_groups(db_session, sort="due")

    assert groups[-1]["customer_name"] == "기한없음"


def test_unknown_sort_falls_back_to_received_order(app):
    """모르는 정렬값은 조용히 접수순으로 떨어진다(주소를 손으로 고쳐도 목록이 안 빈다)."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _seed_interleaved(db_session)
    groups, _truncated = _work_groups(db_session, sort="드롭테이블")

    stamps = [group["created_sort"] for group in groups]
    assert stamps == sorted(stamps, reverse=True)


def test_sort_does_not_change_the_population(app):
    """정렬은 **모집단을 바꾸지 않는다** — 숫자가 정렬에 따라 달라지면 계약 위반이다."""
    from db import db_session
    from foms.web.admin.naver_ingest import (
        _actionable_count,
        _filter_counts,
        _work_groups,
    )

    _seed_due(db_session)
    by_new, trunc_new = _work_groups(db_session, sort="new")
    by_due, trunc_due = _work_groups(db_session, sort="due")

    assert sorted(g["key"] for g in by_new) == sorted(g["key"] for g in by_due)
    assert _filter_counts(by_new) == _filter_counts(by_due)
    assert _actionable_count(by_new) == _actionable_count(by_due)
    assert trunc_new == trunc_due


def test_due_sort_pushes_locked_households_to_the_bottom(app):
    """임박순은 **손댈 수 있는 집**부터다 — 취소·반품이 상단을 차지하면 정렬이 거짓말이다.

    2026-08-24 스테이징 실화면에서 임박순 상단 6줄 중 4줄이 '손대지 않음'이었다.
    담당자는 "급한 것부터"를 보려고 누른 것이지 손댈 수 없는 집을 보려는 게 아니다.
    """
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    # 기한이 제일 가까운 집을 **취소 요청**으로 만든다 — 정렬만 보면 맨 위여야 하는 집.
    locked = _link(db_session, external_id="20260811000001", order_no="N-LOCK",
                   name="취소급함", tel="010-6000-0001",
                   created_at=datetime.datetime(2026, 8, 23, 9, 0))
    snap = dict(locked.raw_snapshot)
    product_order = dict(snap["productOrder"])
    product_order["shippingDueDate"] = "2026-08-25T00:00:00.0+09:00"
    product_order["claimStatus"] = "CANCEL_REQUEST"
    snap["productOrder"] = product_order
    locked.raw_snapshot = snap
    db_session.commit()
    _seed_due(db_session)

    groups, _truncated = _work_groups(db_session, sort="due")

    assert groups[0]["customer_name"] == "급함", "손댈 수 있는 집이 먼저 와야 한다"
    assert groups[-1]["customer_name"] == "취소급함", "잠긴 집은 기한과 무관하게 맨 뒤다"
