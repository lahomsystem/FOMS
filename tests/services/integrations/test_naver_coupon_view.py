"""주문 화면 예약금 옆 네이버 쿠폰 표시 값 (2026-11-24 사장님 요구).

못박는 것:

1. 색 뜻 — 우리가 낸 몫이 있으면 ``ours``, 네이버가 전부 냈으면 ``naver``, 모르면 ``unknown``.
2. 쿠폰을 안 쓴 주문은 ``None`` — 화면에 아무것도 안 생긴다.
3. 원본을 못 읽었으면 "안 썼다"가 아니라 모름이다.
4. 화면 조각(자리 · 스크립트)이 PC · 모바일 두 틀에 다 있다.
"""
import pathlib

from foms.services.integrations.naver_commerce.coupon_view import build_coupon_view
from foms.services.integrations.naver_commerce.mapping import build_payment_info

_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _coupons(*rows):
    detail = {"order": {"orderId": "N-1"},
              "productOrder": {"productOrderId": "PO-1", "appliedCoupons": list(rows)}}
    return build_payment_info(detail)["coupons"]


def test_naver_paid_coupon_is_naver_tone():
    view = build_coupon_view(_coupons(
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 11000, "naverBurdenRatio": 100},
    ), known=True)

    assert view["tone"] == "naver"
    assert view["line"] == "쿠폰 11,000원 · 네이버가 냄"
    assert view["rows"] == [{"label": "상품 할인 쿠폰", "amount": "-11,000원", "who": "네이버가 전부 냄"}]
    assert view["total"] == "-11,000원"
    assert view["ours"] == "0원"


def test_our_share_makes_ours_tone():
    view = build_coupon_view(_coupons(
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 10000, "naverBurdenRatio": 100},
        {"couponClassCode": "NMP_PRD_DUP_DCNT", "couponDiscountAmount": 1000, "naverBurdenRatio": 0},
    ), known=True)

    assert view["tone"] == "ours"
    assert view["line"] == "쿠폰 2장 11,000원 · 우리 몫 1,000원"
    assert view["rows"][1]["who"] == "우리가 전부 냄"
    assert view["ours"] == "1,000원"


def test_split_ratio_says_both_sides():
    view = build_coupon_view(_coupons(
        {"couponClassCode": "X_NEW", "couponDiscountAmount": 10000, "naverBurdenRatio": 30},
    ), known=True)

    assert view["tone"] == "ours"
    assert view["rows"][0] == {"label": "쿠폰", "amount": "-10,000원", "who": "네이버 30% · 우리 7,000원"}


def test_missing_ratio_is_unknown_not_naver():
    """부담 비율이 없으면 '네이버가 냄'이라고 말하지 않는다."""
    view = build_coupon_view(_coupons(
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 9000},
    ), known=True)

    assert view["tone"] == "unknown"
    assert view["line"] == "쿠폰 9,000원 · 누가 냈는지 모름"
    assert "모르는 쿠폰" in view["ours"]


def test_no_coupon_shows_nothing_but_unread_source_says_unknown():
    assert build_coupon_view([], known=True) is None

    view = build_coupon_view([], known=False)
    assert view["tone"] == "unknown"
    assert view["rows"] == []
    assert view["note"]


def test_dock_row_source_carries_coupons_and_unknown_for_broken_snapshot():
    """도크 행 원본 — 읽은 행은 낱장을 싣고, 못 읽은 행은 모름(키가 빠져 죽지 않는다)."""
    from types import SimpleNamespace

    from foms.services.integrations.naver_commerce.dock import _row_source

    broken = _row_source(SimpleNamespace(id=1, raw_snapshot=None))
    assert broken["coupon_known"] is False
    assert broken["coupons"] == []
    assert broken["coupon_count"] == 0

    good = _row_source(SimpleNamespace(id=2, raw_snapshot={
        "order": {"orderId": "N-1"},
        "productOrder": {"productOrderId": "PO-1", "productName": "붙박이장",
                         "appliedCoupons": [{"couponClassCode": "NMP_PRD_DCNT",
                                             "couponDiscountAmount": 11000,
                                             "naverBurdenRatio": 100}]},
    }))
    assert good["coupon_known"] is True
    assert good["coupons"][0]["discount_amount"] == 11000


def test_screen_slots_exist_on_pc_and_mobile_and_script_is_loaded():
    for rel in ("templates/orders/partials/erp_order_tab.html",
                "templates/orders/partials/erp_order_tab_mobile.html"):
        markup = (_ROOT / rel).read_text(encoding="utf-8")
        for node_id in ("erp-coupon-icon", "erp-coupon-line", "erp-coupon-box"):
            assert f'id="{node_id}"' in markup, (rel, node_id)
            # 처음엔 숨김 — 쿠폰을 쓴 주문에서만 스크립트가 연다.
        assert markup.count(" hidden></") >= 3

    loader = (_ROOT / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    assert "asset_url('js/orders/erp-naver-coupon.js')" in loader
    assert "asset_url('css/orders/erp-naver-coupon.css')" in loader

    script = (_ROOT / "static/js/orders/erp-naver-coupon.js").read_text(encoding="utf-8")
    assert "payload.coupon_view" in script
    # 내역은 눌렀을 때만 — 처음 그릴 때 닫아 둔다.
    assert "setOpen(false);" in script
