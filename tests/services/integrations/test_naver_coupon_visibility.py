"""쿠폰 사용 여부가 화면에 **사실로** 뜨는지 (2026-08-25 사용자 요구).

담당자가 금액을 볼 때 같이 나오는 질문이 "이거 쿠폰 썼나" 다. 지금까지 쿠폰 할인은
`할인` 합계에 녹아 들어가서 화면 어디서도 구분되지 않았다(워크벤치 v3 상세에는 할인
표시 자체가 없었다).

두 가지를 못박는다.

1. **안 쓴 집도 말한다.** 표시가 없으면 "쿠폰이 없다"인지 "화면이 모른다"인지 구분이 안 된다.
2. **판매자 부담분을 따로 낸다.** 네이버 실데이터에는 부담 주체가 다른 두 종류가 섞여 온다
   (`NMP_PRD_DCNT` = 네이버 100% 부담 · `NMP_PRD_DUP_DCNT` = 판매자 부담). 같은 "쿠폰 1만원"
   이라도 우리 정산액이 깎이는 건과 아닌 건이 갈린다.
"""
from foms.services.integrations.naver_commerce.mapping import build_payment_info
from foms.services.integrations.naver_commerce.promotion import summarize_snapshot


def _snapshot(coupons=None, card_promotion=None):
    """상품주문 상세 1건(쿠폰만 갈아 끼운다)."""
    product_order = {
        "productOrderId": "PO-COUPON-1",
        "productName": "붙박이장",
        "totalPaymentAmount": 100000,
        "productDiscountAmount": 5000,
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1"},
    }
    if coupons is not None:
        product_order["appliedCoupons"] = coupons
    if card_promotion is not None:
        product_order["appliedCardPromotion"] = card_promotion
    return {"order": {"orderId": "N-COUPON", "paymentMeans": "신용카드"},
            "productOrder": product_order}


def test_naver_burden_coupon_costs_us_nothing():
    """네이버 100% 부담 쿠폰의 판매자 부담분은 0 이다."""
    payment = build_payment_info(_snapshot(coupons=[
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 10000,
         "naverBurdenRatio": 100, "couponPublishNumber": "SS_1"},
    ]))

    row = payment["coupons"][0]
    assert row["discount_amount"] == 10000
    assert row["naver_burden_ratio"] == 100
    assert row["seller_burden_amount"] == 0, "네이버가 문 쿠폰을 우리 부담으로 셌다"
    assert row["publish_number"] == "SS_1"


def test_seller_burden_coupon_is_our_money():
    """판매자 부담(비율 0) 쿠폰은 할인액 전액이 우리 부담이다."""
    payment = build_payment_info(_snapshot(coupons=[
        {"couponClassCode": "NMP_PRD_DUP_DCNT", "couponDiscountAmount": 11000,
         "naverBurdenRatio": 0},
    ]))

    assert payment["coupons"][0]["seller_burden_amount"] == 11000


def test_unknown_burden_ratio_is_not_counted_as_free():
    """부담 비율이 없으면 **모름**이다 — 0 으로 세면 '우리 부담 없음'으로 읽힌다."""
    payment = build_payment_info(_snapshot(coupons=[
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 9000},
    ]))

    assert payment["coupons"][0]["seller_burden_amount"] is None

    facts = summarize_snapshot(_snapshot(coupons=[
        {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 9000},
    ]))
    assert facts["coupon_count"] == 1
    assert facts["coupon_discount"] == 9000
    # 모르는 값은 부담 합계에 넣지 않는다.
    assert facts["coupon_seller_burden"] == 0


def test_summary_says_zero_coupons_but_knows_it():
    """쿠폰이 없으면 0 장이되 **읽었다는 사실**(coupon_known)이 참이어야 한다."""
    facts = summarize_snapshot(_snapshot())

    assert facts["coupon_known"] is True
    assert facts["coupon_count"] == 0
    assert facts["coupon_discount"] == 0


def test_broken_snapshot_is_unknown_not_zero():
    """원본이 깨졌으면 '쿠폰 없음'이 아니라 모름이다 — 화면이 거짓말하면 안 된다."""
    facts = summarize_snapshot({"garbage": True})

    assert facts["coupon_known"] is False
    assert facts["coupon_count"] == 0


def test_card_promotion_is_carried_separately():
    """카드사 프로모션은 쿠폰과 다른 축이다 — 섞지 않고 따로 싣는다."""
    payment = build_payment_info(_snapshot(card_promotion={
        "promotionName": "멤버십데이 삼성카드 3% 할인 (최대 2만원)",
        "cardCompanyName": "삼성", "promotionApplyAmount": 2000,
    }))

    assert payment["card_promotion"]["card_company"] == "삼성"
    assert payment["card_promotion"]["apply_amount"] == 2000
    assert payment["coupons"] == [], "카드 프로모션을 쿠폰으로 셌다"


def test_pane_template_says_coupon_either_way():
    """상세 템플릿이 **쓴 집과 안 쓴 집 둘 다** 문장을 갖는다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    markup = (root / "templates/admin/partials/naver_workbench_pane.html").read_text(encoding="utf-8")

    assert "쿠폰 사용 안 함" in markup, "안 쓴 집이 침묵하면 '모름'과 구분이 안 된다"
    assert "장 사용" in markup
    assert "판매자 부담" in markup
    assert "원본을 읽지 못해 모름" in markup


def test_dock_js_says_coupon_either_way():
    """도크 JS 도 같은 규율 — 안 썼으면 '사용 안 함' 을 낸다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    source = (root / "static/js/orders/erp-naver-dock.js").read_text(encoding="utf-8")

    assert "'사용 안 함'" in source
    assert "전액 네이버 부담" in source
    assert "couponSellerBurden: payload.coupon_seller_burden || 0" in source
