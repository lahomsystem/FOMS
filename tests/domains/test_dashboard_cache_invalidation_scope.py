"""Wave 2: 대시보드 캐시 무효화 티어 helper 단위 계약.

broad 무효화(invalidate_all_dashboard_slice_caches)가 모든 mutation마다 7 family를
전멸시키던 것을, 스테이지/도메인 단위로 좁힌 helper들의 반환 family 집합을 고정한다.
family 문자열 오타 = 무효화 누락 = stale 버그이므로, 상수/매핑 자체도 검증한다.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from foms.services.common import dashboard_cache as dc


def _capture_invalidated_families(fn):
    """helper 실행 중 invalidate_dashboard_family에 넘어간 family를 순서대로 수집."""
    seen: list[str] = []

    def _fake(fam: str) -> int:
        seen.append(fam)
        return 1

    with patch.object(dc, "invalidate_dashboard_family", side_effect=_fake):
        fn()
    return seen


# --- 상수 구성 계약 ---------------------------------------------------------


def test_all_dashboard_families_is_seven_canonical():
    assert dc.ALL_DASHBOARD_FAMILIES == (
        "orders",
        "measurement",
        "shipment",
        "construction",
        "history",
        "production",
        "drawing",
    )


def test_attachment_families_exclude_only_history():
    """첨부를 읽는 도메인만 포함하고 history만 빠진다(근거는 상수 docstring)."""
    assert dc.ATTACHMENT_DASHBOARD_FAMILIES == frozenset(
        {"orders", "measurement", "shipment", "construction", "production", "drawing"}
    )
    assert "history" not in dc.ATTACHMENT_DASHBOARD_FAMILIES
    # 첨부 family는 항상 전체 family의 부분집합이어야 한다(오타 방지).
    assert dc.ATTACHMENT_DASHBOARD_FAMILIES <= set(dc.ALL_DASHBOARD_FAMILIES)


# --- stage_code_to_dashboard_family 매핑 ------------------------------------


def test_stage_code_to_family_known_stages():
    assert dc.stage_code_to_dashboard_family("MEASURE") == "measurement"
    assert dc.stage_code_to_dashboard_family("DRAWING") == "drawing"
    assert dc.stage_code_to_dashboard_family("CONFIRM") == "production"
    assert dc.stage_code_to_dashboard_family("PRODUCTION") == "production"
    assert dc.stage_code_to_dashboard_family("CONSTRUCTION") == "construction"
    assert dc.stage_code_to_dashboard_family("CS") == "construction"
    assert dc.stage_code_to_dashboard_family("AS") == "construction"
    assert dc.stage_code_to_dashboard_family("AS_RECEIVED") == "construction"
    assert dc.stage_code_to_dashboard_family("AS_COMPLETED") == "history"
    assert dc.stage_code_to_dashboard_family("COMPLETED") == "history"


def test_stage_code_to_family_korean_legacy_stages():
    """운영 데이터의 한글 stage 값(production_read_model 이중 필터 근거) 매핑.

    미등록 한글 stage는 broad 폴백(None)이어야 한다 — 오매핑보다 broad가 안전.
    """
    assert dc.stage_code_to_dashboard_family("고객컨펌") == "production"
    assert dc.stage_code_to_dashboard_family("생산") == "production"
    assert dc.stage_code_to_dashboard_family("시공") == "construction"
    # 미등록 한글 stage → None(호출부 broad 폴백)
    assert dc.stage_code_to_dashboard_family("실측중") is None


def test_stage_code_to_family_is_case_insensitive():
    assert dc.stage_code_to_dashboard_family("measure") == "measurement"
    assert dc.stage_code_to_dashboard_family(" Drawing ") == "drawing"


def test_stage_code_to_family_unmapped_returns_none():
    # RECEIVED는 orders 탭에만 있으므로 도메인 family가 없다 → None(=broad 폴백 신호).
    assert dc.stage_code_to_dashboard_family("RECEIVED") is None
    assert dc.stage_code_to_dashboard_family("BOGUS") is None
    assert dc.stage_code_to_dashboard_family(None) is None
    assert dc.stage_code_to_dashboard_family("") is None


# --- invalidate_dashboard_families (배치, 중복 제거) -------------------------


def test_invalidate_families_dedupes_and_skips_blank():
    seen = _capture_invalidated_families(
        lambda: dc.invalidate_dashboard_families("orders", "orders", "", "drawing")
    )
    assert seen == ["orders", "drawing"]


# --- invalidate_order_dashboard_families ------------------------------------


def test_order_families_measure_stage_scopes_orders_plus_measurement():
    order = SimpleNamespace(erp_stage_code="MEASURE")
    seen = _capture_invalidated_families(
        lambda: dc.invalidate_order_dashboard_families(order)
    )
    assert set(seen) == {"orders", "measurement"}


def test_order_families_construction_stage_scopes_orders_plus_construction():
    order = SimpleNamespace(erp_stage_code="CONSTRUCTION")
    seen = _capture_invalidated_families(
        lambda: dc.invalidate_order_dashboard_families(order)
    )
    assert set(seen) == {"orders", "construction"}


def test_order_families_extra_shipment_added():
    order = SimpleNamespace(erp_stage_code="CONSTRUCTION")
    seen = _capture_invalidated_families(
        lambda: dc.invalidate_order_dashboard_families(
            order, extra=(dc.DASHBOARD_FAMILY_SHIPMENT,)
        )
    )
    assert set(seen) == {"orders", "construction", "shipment"}


def test_order_families_unmapped_stage_falls_back_to_broad():
    """RECEIVED/None 등 미매핑 stage는 stale 방지를 위해 전체 7 family 무효화."""
    for bad_stage in ("RECEIVED", None, "WEIRD"):
        order = SimpleNamespace(erp_stage_code=bad_stage)
        seen = _capture_invalidated_families(
            lambda: dc.invalidate_order_dashboard_families(order)
        )
        assert seen == list(dc.ALL_DASHBOARD_FAMILIES), bad_stage


def test_order_families_missing_attribute_falls_back_to_broad():
    """erp_stage_code 속성 자체가 없으면(=None) 안전하게 broad."""
    order = SimpleNamespace()  # no erp_stage_code
    seen = _capture_invalidated_families(
        lambda: dc.invalidate_order_dashboard_families(order)
    )
    assert seen == list(dc.ALL_DASHBOARD_FAMILIES)
