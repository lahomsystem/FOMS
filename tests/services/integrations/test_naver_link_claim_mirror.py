"""NVMIRROR-01 클레임 축 사본 컬럼 계약 (2026-09-13).

사본은 **정본이 아니다** — 정본은 ``raw_snapshot`` 이고 사본은 TOAST 를 안 읽으려고 두는
필터·집계용 복사다. 그래서 지켜야 할 것이 셋이다.

1. 사본으로 판정한 결과가 스냅샷으로 판정한 결과와 **같다**.
2. ``NULL``(아직 계산 안 함)과 ``''``(계산했고 값 없음)이 갈린다 — 이 구분이 무너지면
   백필 뒤에도 클레임 없는 행 전부가 스냅샷을 다시 읽는다(운영 489행 중 370행).
3. 갱신 자리(수집 2곳·클레임 스윕)가 **빠짐없이** 사본을 쓴다 — 한 곳을 빼먹으면 사본이
   조용히 낡고, 낡은 사본은 폴백조차 하지 않는다(그게 NULL 과 다른 점이다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from foms.services.integrations.naver_commerce.ghost_orders import _fold_link, _new_bucket
from foms.services.integrations.naver_commerce.link_mirror import (
    MIRROR_COLUMNS,
    apply_claim_mirror,
    claim_mirror_values,
    snapshot_from_mirror,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: 판정 경로를 한 번씩 태우는 모양들.
SHAPES: dict[str, dict[str, Any]] = {
    "정상": {"order": {"orderId": "M-1"},
             "productOrder": {"productOrderId": "PM-1", "totalPaymentAmount": 100000,
                              "productOrderStatus": "DELIVERED"}},
    "취소확정": {"order": {"orderId": "M-2"},
               "productOrder": {"productOrderId": "PM-2", "claimStatus": "CANCEL_DONE",
                                "claimType": "CANCEL", "totalPaymentAmount": 250000,
                                "productOrderStatus": "CANCELED"}},
    "취소요청": {"order": {"orderId": "M-3"},
               "productOrder": {"productOrderId": "PM-3", "claimStatus": "CANCEL_REQUEST",
                                "claimType": "CANCEL", "totalPaymentAmount": 70000}},
    "최상위-반품확정": {"order": {"orderId": "M-4"},
                  "productOrder": {"productOrderId": "PM-4", "totalPaymentAmount": 310000},
                  "return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN"}},
    "cancel-블록": {"order": {"orderId": "M-5"},
                 "productOrder": {"productOrderId": "PM-5", "totalPaymentAmount": 40000},
                 "cancel": {"claimStatus": "CANCEL_DONE", "claimType": "CANCEL"}},
    "currentClaim": {"order": {"orderId": "M-6"},
                     "productOrder": {"productOrderId": "PM-6", "totalPaymentAmount": 55000},
                     "currentClaim": {"cancel": {"claimStatus": "RETURN_DONE",
                                                 "claimType": "RETURN"}}},
    "주문단위-클레임": {"order": {"orderId": "M-7", "claimStatus": "CANCEL_DONE"},
                  "productOrder": {"productOrderId": "PM-7", "totalPaymentAmount": 12000}},
    "평평한응답": {"productOrderId": "PM-8", "claimStatus": "CANCEL_REQUEST",
              "claimType": "CANCEL", "productOrderStatus": "PAYED",
              "totalPaymentAmount": 70000},
    "빈원본": {},
}


class _Link:
    """사본 컬럼만 가진 최소 대역 객체(ORM 없이 얹기 규약을 본다)."""

    def __init__(self) -> None:
        for name in MIRROR_COLUMNS:
            setattr(self, name, None)


def test_mirror_folds_the_same_as_the_snapshot() -> None:
    """사본을 되돌린 문서로 접은 결과가 스냅샷으로 접은 결과와 같다."""
    for name, snapshot in SHAPES.items():
        values = claim_mirror_values(snapshot)
        restored = snapshot_from_mirror(claim_status=values["claim_status"],
                                        claim_type=values["claim_type"],
                                        payment_amount=values["payment_amount"])
        thick, thin = _new_bucket(), _new_bucket()
        _fold_link(thick, snapshot=snapshot, order_no="2026000001", link_id=1)
        _fold_link(thin, snapshot=restored, order_no="2026000001", link_id=1)
        assert thick == thin, f"{name} 의 판정이 사본에서 갈린다"


def test_computed_empty_is_not_null() -> None:
    """클레임 없는 정상 건은 ``''``·``0`` 이다 — NULL 이면 영원히 폴백한다."""
    values = claim_mirror_values(SHAPES["정상"])
    assert values["claim_status"] == ""
    assert values["claim_type"] == ""
    assert values["payment_amount"] == 100000
    assert values["product_order_status"] == "DELIVERED"


def test_unknown_input_is_null() -> None:
    """문서가 아니면 전부 NULL 이다 — 읽는 쪽이 스냅샷으로 폴백해야 한다."""
    assert claim_mirror_values(None) == {name: None for name in MIRROR_COLUMNS}
    assert claim_mirror_values("문서 아님") == {name: None for name in MIRROR_COLUMNS}


def test_flat_response_amount_matches_the_snapshot_reader() -> None:
    """평평한 응답의 금액은 **0** 이다 — ``_fold_link`` 가 중첩 블록만 보기 때문이다.

    여기서 최상위로 폴백하면 사본이 스냅샷보다 큰 합계를 낸다(동치가 먼저다).
    """
    assert claim_mirror_values(SHAPES["평평한응답"])["payment_amount"] == 0
    # 상태는 평평한 자리에서도 읽는다 — 다시 읽기 판정이 그렇게 읽어 왔다.
    assert claim_mirror_values(SHAPES["평평한응답"])["product_order_status"] == "PAYED"


def test_apply_does_not_overwrite_with_unknown() -> None:
    """값을 못 뽑으면 기존 사본을 지우지 않는다 — 옛 사본이 "모름" 보다 정확하다."""
    link = _Link()
    apply_claim_mirror(link, SHAPES["취소확정"])
    assert link.claim_status == "CANCEL_DONE"
    apply_claim_mirror(link, "문서 아님")
    assert link.claim_status == "CANCEL_DONE", "모름이 옛 사본을 덮었다"


def test_every_write_site_updates_the_mirror() -> None:
    """수집 2곳·클레임 스윕이 사본을 쓴다(한 곳을 빼먹으면 사본이 조용히 낡는다)."""
    ingest = (_REPO_ROOT / "foms/services/integrations/naver_commerce/ingest.py").read_text(
        encoding="utf-8")
    sweep = (_REPO_ROOT / "foms/services/integrations/naver_commerce/claim_watch.py").read_text(
        encoding="utf-8")
    assert ingest.count("claim_mirror_values(detail)") >= 2, "수집 두 자리 중 하나가 빠졌다"
    assert "apply_claim_mirror(link, detail)" in sweep, "클레임 스윕이 사본을 안 쓴다"


def test_readers_do_not_touch_the_snapshot_on_the_hot_path() -> None:
    """뜨거운 경로가 사본을 읽는다 — 스냅샷 경로는 **NULL 행 폴백에만** 남는다."""
    ghost = (_REPO_ROOT
             / "foms/services/integrations/naver_commerce/ghost_orders.py").read_text(
        encoding="utf-8")
    sweep = (_REPO_ROOT
             / "foms/services/integrations/naver_commerce/claim_watch.py").read_text(
        encoding="utf-8")
    # 유령 스캔의 첫 조회에 사본 컬럼이 있고, 투영은 폴백 분기 안에만 남아야 한다.
    assert "ExternalOrderLink.claim_status" in ghost
    assert "stale_ids" in ghost and "_ghost_snapshot_projection(session)" in ghost
    assert "ExternalOrderLink.product_order_status" in sweep
    assert "stale_ids" in sweep


def test_shapes_cover_both_verdicts() -> None:
    """음성 대조군 — 모양에 클레임 있는 것과 없는 것이 둘 다 있어야 한다."""
    statuses = {claim_mirror_values(s)["claim_status"] for s in SHAPES.values()}
    assert "" in statuses, "클레임 없는 모양이 없다"
    assert any(status for status in statuses), "클레임 있는 모양이 없다"
