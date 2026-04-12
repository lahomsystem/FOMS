/**
 * WDCalculator coupon/shipping recalculation listener wiring.
 * Host keeps totals math and mutable estimate state.
 */
var WdCalculatorCouponShippingWiring = window.WdCalculatorCouponShippingWiring || {};

(function (ns) {
    var defaultCouponValue = 11000;
    var getEstimates = function () {
        return [];
    };
    var calculateEstimate = function () {};
    var calculateTotalEstimates = function () {};
    var getCouponValue = function () {
        return defaultCouponValue;
    };

    function configure(opts) {
        if (opts && typeof opts.defaultCouponValue === "number") {
            defaultCouponValue = opts.defaultCouponValue;
        }
        if (opts && typeof opts.getEstimates === "function") {
            getEstimates = opts.getEstimates;
        }
        if (opts && typeof opts.calculateEstimate === "function") {
            calculateEstimate = opts.calculateEstimate;
        }
        if (opts && typeof opts.calculateTotalEstimates === "function") {
            calculateTotalEstimates = opts.calculateTotalEstimates;
        }
        if (opts && typeof opts.getCouponValue === "function") {
            getCouponValue = opts.getCouponValue;
        }
    }

    function shouldRecalculateTotals() {
        return (getEstimates() || []).length > 0;
    }

    function bindShippingCostInput() {
        var shippingCostInputField = document.getElementById("shippingCost");
        if (shippingCostInputField) {
            shippingCostInputField.addEventListener("input", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            shippingCostInputField.addEventListener("change", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            console.log("배송비 입력 필드 이벤트 리스너 등록 완료");
        }
    }

    function bindShippingIncludedCheckbox() {
        var shippingIncludedCheckbox = document.getElementById("shippingIncluded");
        if (shippingIncludedCheckbox) {
            shippingIncludedCheckbox.addEventListener("change", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            console.log("배송비 포함 여부 체크박스 이벤트 리스너 등록 완료");
        }
    }

    function bindCouponInput() {
        var couponInputField = document.getElementById("globalCouponValue");
        if (couponInputField) {
            if (!couponInputField.value || couponInputField.value === "0") {
                couponInputField.value = defaultCouponValue;
                console.log("쿠폰 입력 필드 초기값 설정:", defaultCouponValue);
            }

            couponInputField.addEventListener("input", function () {
                var newValue = this.value;
                console.log("쿠폰 값 변경됨 (input):", newValue);
                setTimeout(function () {
                    var currentValue = getCouponValue();
                    console.log("재계산 실행 - 쿠폰 값:", currentValue);
                    calculateEstimate();
                    if (shouldRecalculateTotals()) {
                        calculateTotalEstimates();
                    }
                }, 100);
            });

            couponInputField.addEventListener("change", function () {
                var newValue = this.value;
                console.log("쿠폰 값 확정됨 (change):", newValue);
                var currentValue = getCouponValue();
                console.log("재계산 실행 - 쿠폰 값:", currentValue);
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });

            couponInputField.addEventListener("blur", function () {
                var newValue = this.value;
                console.log("쿠폰 입력 필드 포커스 아웃 (blur):", newValue);
                var currentValue = getCouponValue();
                console.log("재계산 실행 - 쿠폰 값:", currentValue);
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });

            console.log("쿠폰 입력 필드 이벤트 리스너 등록 완료, 현재 값:", couponInputField.value);

            setTimeout(function () {
                console.log("초기 로드 후 계산 실행");
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            }, 500);
        } else {
            console.error("쿠폰 입력 필드를 찾을 수 없습니다!");
        }
    }

    function initCouponShippingWiring() {
        bindShippingCostInput();
        bindShippingIncludedCheckbox();
        bindCouponInput();
    }

    ns.configure = configure;
    ns.initCouponShippingWiring = initCouponShippingWiring;
})(WdCalculatorCouponShippingWiring);

window.WdCalculatorCouponShippingWiring = WdCalculatorCouponShippingWiring;
