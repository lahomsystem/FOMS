/**
 * WDCalculator coupon input reading and final-price display styling helpers.
 * Depends on giant host script to configure the current default coupon value.
 */
var WdCalculatorCouponDisplayHelpers = window.WdCalculatorCouponDisplayHelpers || {};

(function (ns) {
    var defaultCouponValue = 11000;

    /**
     * @param {{ defaultCouponValue?: number }} opts
     */
    function configure(opts) {
        if (!opts) return;
        if (typeof opts.defaultCouponValue === "number" && !isNaN(opts.defaultCouponValue)) {
            defaultCouponValue = opts.defaultCouponValue;
        }
    }

    function getCouponValue() {
        var couponInput = document.getElementById("globalCouponValue");
        if (!couponInput) {
            console.warn("쿠폰 입력 필드를 찾을 수 없습니다. 기본값 사용:", defaultCouponValue);
            return defaultCouponValue;
        }
        var value = couponInput.value;
        if (!value || value === "") {
            return defaultCouponValue;
        }
        var numValue = parseInt(value, 10);
        if (isNaN(numValue) || numValue < 0) {
            console.warn("잘못된 쿠폰 값:", value, "기본값 사용:", defaultCouponValue);
            return defaultCouponValue;
        }
        return numValue;
    }

    function applyFinalPriceStyle(element) {
        if (!element) return;
        element.style.fontSize = "2.4rem";
        element.style.fontWeight = "900";
        element.style.color = "#0d6efd";
        element.style.lineHeight = "1.1";
        element.className = "final-price-display mb-2";
    }

    function applyCouponDiscountStyle(element, hasDiscount) {
        if (!element) return;
        if (hasDiscount) {
            element.style.color = "#dc3545";
            element.style.fontWeight = "700";
            element.className = "coupon-discount";
            return;
        }
        element.style.color = "#6c757d";
        element.style.fontWeight = "400";
        element.className = "text-muted";
    }

    ns.configure = configure;
    ns.getCouponValue = getCouponValue;
    ns.applyFinalPriceStyle = applyFinalPriceStyle;
    ns.applyCouponDiscountStyle = applyCouponDiscountStyle;
})(WdCalculatorCouponDisplayHelpers);

window.WdCalculatorCouponDisplayHelpers = WdCalculatorCouponDisplayHelpers;
