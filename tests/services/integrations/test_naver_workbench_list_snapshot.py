"""처리 목록 축소 스냅샷(성능 원장 P2-2 ④) — **읽는 양만** 줄었고 목록은 그대로라는 계약.

처리 탭(``_work_groups(display=True)``)은 링크 행을 ``raw_snapshot`` 째 읽었다 — 2026-10-02
스테이징 1,241행에 출력 5.5MB. 이제는 :data:`naver_list_snapshot.LIST_SNAPSHOT_SPEC` 이
남기는 경로만 싣는다. 이 투영이 미뤄졌던 까닭은 하나였다: **어떤 소비자가 읽는 필드를 조용히
떨어뜨릴 위험.** 그래서 여기서 지키는 것은 둘이다.

1. 목록 경로 전체를 **통째 원본 + 경로 추적기**로 돌려, 읽힌 자리가 전부 투영 안에 있다
   (새 함수가 투영 밖 경로를 읽기 시작하면 이 테스트가 빨개진다). 속성도 같은 방식으로 —
   목록 행(:class:`ListLink`)에 없는 속성을 읽으면 빨개진다.
2. 같은 입력에서 투영 행으로 만든 목록 == 통째 원본으로 만든 목록(함수별·목록 전체).

둘 다 음성 대조군을 붙인다 — 경로 하나(``productOrder.productName``)를 뺀 투영으로 같은 측정을
돌리면 잡아내야 한다. SQLite 레인은 투영을 파이썬 정본(:func:`project_list_snapshot`)으로
하고, SQL 투영이 그 정본과 키 순서까지 같다는 증명은 PG 레인이 맡는다.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import fulfillment as F
from foms.services.integrations.naver_commerce import mapping as M
from foms.services.integrations.naver_commerce import promotion as P
from foms.web.admin import naver_ingest as ingest
from foms.web.admin import naver_list_snapshot as nls
from tests.services.integrations.naver_list_snapshot_helpers import (
    SHAPES,
    seed_shapes,
    spec_without,
    traced,
    uncovered_reads,
)

#: 음성 대조군이 빼는 경로 — 목록 제목 줄이 읽는 제품명.
DROPPED = ("productOrder", "productName")

#: 목록 행의 칸(추적 중에는 ``nls.ListLink`` 가 기록 대역으로 바뀌므로 미리 잡아 둔다).
LIST_ROW_FIELDS = frozenset(nls.ListLink.__slots__)

#: 행 1건을 받는 목록 소비자 전부(``_group_queue``·형제 색인이 부르는 것).
ROW_CONSUMERS = {
    "household_key": F.household_key, "is_place_pending": F.is_place_pending,
    "is_dispatch_pending": F.is_dispatch_pending, "is_partial_canceled": F.is_partial_canceled,
    "is_purchase_decided": F.is_purchase_decided, "is_return_pending": F.is_return_pending,
    "return_sendable": F.return_sendable, "cancel_sendable": F.cancel_sendable,
    "is_return_rejectable": F.is_return_rejectable,
    "is_cancel_approvable": F.is_cancel_approvable,
    "is_return_approvable": F.is_return_approvable,
    "_naver_dispatched_at": F._naver_dispatched_at, "_is_addon_link": F._is_addon_link,
    "is_promotable": P.is_promotable,
    "summarize_snapshot": lambda row: P.summarize_snapshot(row.raw_snapshot),
    "extract_claim": lambda row: M.extract_claim(row.raw_snapshot or {}),
    "extract_claim_holdback": lambda row: M.extract_claim_holdback(row.raw_snapshot or {}),
    "_place_view": ingest._place_view, "_link_payment_amount": ingest._link_payment_amount,
    "_canceled_ours": ingest._canceled_ours,
}


def _row(snapshot: Any, attrs: dict[str, Any], *, list_row: bool, spec=None) -> Any:
    """표본 하나를 행으로 — 통째(SimpleNamespace) 또는 목록 행(투영)."""
    values = {"id": 1, "external_id": "LS-ROW", "external_order_no": "LS", "order_id": None,
              "sync_status": "COLLECTED", "place_order_status": "NOT_YET", "relation": None,
              "group_key": None, "created_at": None, "triage_state": None, "reviewed_at": None,
              "product_order_status": "PAYED"}
    values.update(copy.deepcopy(attrs))
    snap = copy.deepcopy(snapshot)
    if not list_row:
        return SimpleNamespace(**values, raw_snapshot=snap)
    return nls.ListLink(*[values[c.key] for c in nls.LIST_COLUMNS],
                        nls.project_list_snapshot(snap, spec))


def _trace_list_path(monkeypatch) -> tuple[set, set]:
    """목록 경로를 **통째 원본 + 추적기**로 돌려 읽힌 경로·속성을 모은다."""
    ops: set = set()
    attrs: set = set()

    class _RecordingRow(nls.ListLink):
        __slots__ = ()

        def __getattribute__(self, name):
            if not name.startswith("__"):
                attrs.add(name)
            return object.__getattribute__(self, name)

    monkeypatch.setattr(nls, "ListLink", _RecordingRow)
    monkeypatch.setattr(nls, "project_list_snapshot",
                        lambda raw, spec=None: traced(copy.deepcopy(raw), (), ops))
    seed_shapes(db_session, commit=True)
    for sort in ingest.WORKBENCH_SORTS:
        groups, _ = ingest._work_groups(db_session, display=True, sort=sort)
    # 형제 색인을 안 줬을 때의 옛 갈래도 목록 행을 받는다 — 같은 추적에 태운다.
    links = ingest._fetch_links(db_session, ingest.ExternalOrderLink.channel == "NAVER",
                                display=True)
    ingest._place_groups(db_session, display=True)
    ingest._attach_household_counts(db_session, [dict(g) for g in groups], display=True)
    ingest._claim_blocked_group_keys(db_session, links, display=True)
    return ops, attrs


def test_list_path_reads_only_projected_paths(app, monkeypatch):
    """목록 경로가 읽는 자리는 전부 투영 안에 있고, 속성은 전부 목록 행에 있다."""
    ops, attrs = _trace_list_path(monkeypatch)

    # 추적기가 실제로 돌았다는 증거(빈 기록끼리 통과하는 거짓 초록을 막는다).
    assert (DROPPED, "get") in ops
    assert (("productOrder", "shippingAddress", "tel1"), "get") in ops
    assert (("productOrder", "appliedCoupons"), "iter") in ops
    assert (("order", "delivery"), "get") in ops, "주문 쪽 발송 폴백까지 탔어야 한다"
    assert (("shippingAddress",), "get") in ops, "최상위 배송지 폴백까지 탔어야 한다"

    missing = uncovered_reads(ops, nls.LIST_SNAPSHOT_SPEC)
    assert not missing, f"투영 밖 경로를 읽는다 — LIST_SNAPSHOT_SPEC 에 더하라: {sorted(missing)}"
    assert attrs <= LIST_ROW_FIELDS, sorted(attrs - LIST_ROW_FIELDS)
    # 구매확정 판정은 사본 컬럼을 getattr 기본값으로 읽는다 — 빠지면 예외 없이 갈린다.
    assert "product_order_status" in attrs


def test_coverage_check_catches_a_dropped_path_negative_control(app, monkeypatch):
    """음성 대조군 — 경로 하나를 뺀 투영이면 같은 측정이 그 경로를 짚는다."""
    ops, _attrs = _trace_list_path(monkeypatch)

    missing = uncovered_reads(ops, spec_without(nls.LIST_SNAPSHOT_SPEC, DROPPED))

    assert (DROPPED, "get") in missing
    # 통째 마디(쿠폰 목록)를 잘게 자르면 반복 접근이 걸린다.
    sliced = spec_without(nls.LIST_SNAPSHOT_SPEC, ("productOrder", "appliedCoupons"))
    sliced["productOrder"]["appliedCoupons"] = {"couponDiscountAmount": None}
    assert (("productOrder", "appliedCoupons"), "iter") in uncovered_reads(ops, sliced)


@pytest.mark.parametrize("label", sorted(SHAPES))
def test_each_consumer_answers_the_same_on_the_projection(label):
    """모양마다·소비자마다 투영 행의 답 == 통째 원본의 답."""
    snapshot, attrs = SHAPES[label]
    full = _row(snapshot, attrs, list_row=False)
    thin = _row(snapshot, attrs, list_row=True)

    for name, consumer in ROW_CONSUMERS.items():
        assert consumer(thin) == consumer(full), f"{label}: {name} 가 갈렸다"


def test_consumer_check_catches_a_dropped_path_negative_control():
    """음성 대조군 — 제품명을 뺀 투영이면 목록 요약이 갈린다."""
    snapshot, attrs = SHAPES["중첩-정상"]
    full = _row(snapshot, attrs, list_row=False)
    broken = _row(snapshot, attrs, list_row=True,
                  spec=spec_without(nls.LIST_SNAPSHOT_SPEC, DROPPED))

    assert P.summarize_snapshot(broken.raw_snapshot) != P.summarize_snapshot(full.raw_snapshot)


def test_work_groups_match_the_full_snapshot(app, monkeypatch):
    """목록 전체(정렬 둘 다) — 투영 행으로 만든 집 목록 == 통째 원본으로 만든 집 목록."""
    seed_shapes(db_session, commit=True)
    real = nls.project_list_snapshot

    projected = {sort: ingest._work_groups(db_session, display=True, sort=sort)
                 for sort in ingest.WORKBENCH_SORTS}
    monkeypatch.setattr(nls, "project_list_snapshot", lambda raw, spec=None: raw)
    full = {sort: ingest._work_groups(db_session, display=True, sort=sort)
            for sort in ingest.WORKBENCH_SORTS}

    assert projected == full
    assert any(group["product"] for group in full["new"][0]), "빈 목록끼리 같다는 거짓 통과"
    # 음성 대조군 — 제품명을 뺀 투영이면 같은 비교가 갈린다.
    monkeypatch.setattr(nls, "project_list_snapshot",
                        lambda raw, spec=None: real(raw, spec_without(nls.LIST_SNAPSHOT_SPEC,
                                                                     DROPPED)))
    assert ingest._work_groups(db_session, display=True)[0] != full["new"][0]


def test_list_spec_keeps_every_claim_block_whole():
    """클레임 블록은 mapping 의 블록 이름에서 파생하고 **통째로** 남긴다(R-7 재발 방지)."""
    for key in (*M.CLAIM_BLOCK_KEYS, *M.RETURN_BLOCK_KEYS, "currentClaim", "beforeClaim",
                "delivery"):
        assert key in nls.LIST_SNAPSHOT_SPEC and nls.LIST_SNAPSHOT_SPEC[key] is None, key


def test_projection_keeps_shape_exactly():
    """남긴 키는 있을 때만 싣고(null 로 채우지 않는다), dict 아닌 자리·키 순서는 그대로."""
    raw = {"productOrder": "깨짐", "order": None, "completedClaims": [1],
           "delivery": {"sendDate": "x"}, "claimStatus": None}

    out = nls.project_list_snapshot(raw)

    assert out == {"productOrder": "깨짐", "order": None, "delivery": {"sendDate": "x"},
                   "claimStatus": None}
    assert list(out) == ["productOrder", "order", "delivery", "claimStatus"]
    assert "productName" not in nls.project_list_snapshot({"productOrder": {}})["productOrder"]
    for odd in (None, [], "문자", 5):
        assert nls.project_list_snapshot(odd) == odd
