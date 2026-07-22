var syncWdCalculatorViewportLayout =
    window.syncWdCalculatorViewportLayout ||
    function syncWdCalculatorViewportLayout() {
        var container = document.querySelector(".wdcalculator-container");
        var shell = document.querySelector(".wdcalculator-shell");
        if (!container || !shell) return;

        if (window.innerWidth < 992) {
            container.style.removeProperty("--wdcalculator-shell-height");
            return;
        }

        var shellTop = shell.getBoundingClientRect().top;
        var bottomGap = 16;
        var availableHeight = Math.max(
            520,
            Math.floor(window.innerHeight - shellTop - bottomGap)
        );
        container.style.setProperty("--wdcalculator-shell-height", availableHeight + "px");
    };
window.syncWdCalculatorViewportLayout = syncWdCalculatorViewportLayout;

var requestWdCalculatorLayoutSync =
    window.requestWdCalculatorLayoutSync ||
    function requestWdCalculatorLayoutSync() {
        window.requestAnimationFrame(syncWdCalculatorViewportLayout);
    };
window.requestWdCalculatorLayoutSync = requestWdCalculatorLayoutSync;

var ceilToTens =
    window.ceilToTens ||
    function ceilToTens(value) {
        var v = Number(value) || 0;
        return Math.ceil(v / 10) * 10;
    };
window.ceilToTens = ceilToTens;

var computeAutoPrice1cmFrom30cm =
    window.computeAutoPrice1cmFrom30cm ||
    function computeAutoPrice1cmFrom30cm(price30) {
        return ceilToTens((Number(price30) || 0) / 30);
    };
window.computeAutoPrice1cmFrom30cm = computeAutoPrice1cmFrom30cm;

var generateEstimateId =
    window.generateEstimateId ||
    function generateEstimateId() {
        return "est_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
    };
window.generateEstimateId = generateEstimateId;

var isSameId =
    window.isSameId ||
    function isSameId(id1, id2) {
        return String(id1) === String(id2);
    };
window.isSameId = isSameId;

var normalizeId =
    window.normalizeId ||
    function normalizeId(id) {
        if (!id) return null;
        return String(id);
    };
window.normalizeId = normalizeId;

var formatPrice =
    window.formatPrice ||
    function formatPrice(value) {
        if (!value) return "";
        var numValue = value.toString().replace(/[^\d]/g, "");
        if (!numValue) return "";
        return parseInt(numValue, 10).toLocaleString("ko-KR");
    };
window.formatPrice = formatPrice;

var parsePrice =
    window.parsePrice ||
    function parsePrice(value) {
        if (!value) return 0;
        var numValue = value.toString().replace(/[^\d]/g, "");
        return parseFloat(numValue) || 0;
    };
window.parsePrice = parsePrice;

var escapeHtml =
    window.escapeHtml ||
    function escapeHtml(text) {
        if (!text) return "";
        var div = document.createElement("div");
        div.textContent = String(text);
        return div.innerHTML;
    };
window.escapeHtml = escapeHtml;

var formatNumber =
    window.formatNumber ||
    function formatNumber(num) {
        return Math.round(num).toLocaleString("ko-KR");
    };
window.formatNumber = formatNumber;

/**
 * 금액 문자열 → 숫자 (콤마·통화기호 내성). parsePrice 의 얇은 별칭 — NaN → 0.
 * W(mm) 입력에는 사용 금지: 콤마가 복합식 항 구분자(spec-width-eval `split(/[+,]/)`)로 예약됨.
 */
var wdcParseAmount =
    window.wdcParseAmount ||
    function wdcParseAmount(value) {
        return parsePrice(value);
    };
window.wdcParseAmount = wdcParseAmount;

/**
 * 금액 input 천단위 콤마 재포맷. caret 은 "끝에서부터의 오프셋" 보존(간단·검증 용이).
 * 빈값/'-'/비숫자 = formatPrice 가 strip — 크래시 없음. 값 불변이면 no-op(caret 미접촉).
 */
var wdcFormatAmountInput =
    window.wdcFormatAmountInput ||
    function wdcFormatAmountInput(inputEl) {
        if (!inputEl) return;
        var raw = String(inputEl.value == null ? "" : inputEl.value);
        var formatted = formatPrice(raw);
        if (formatted === raw) return;
        var caret = inputEl.selectionStart == null ? raw.length : inputEl.selectionStart;
        var fromEnd = raw.length - caret;
        inputEl.value = formatted;
        var pos = Math.max(0, formatted.length - fromEnd);
        try {
            inputEl.setSelectionRange(pos, pos);
        } catch (e) {
            /* 포커스 밖/미지원 타입 — caret 복원 실패는 무해 */
        }
    };
window.wdcFormatAmountInput = wdcFormatAmountInput;

/**
 * 금액 입력 천단위 콤마 자동포맷 — 문서 위임 리스너 1개(G4 싱글톤 가드).
 * 동적 생성 input(fee·옵션 행, 태블릿 v2 셀)도 위임이라 자동 커버.
 * W(mm) 입력(.base-width-input, .wdc2-win)은 의도적으로 제외(복합식 구분자 충돌).
 */
var WDC_AMOUNT_INPUT_SELECTOR = [
    ".base-manual-price30",
    ".base-manual-price1m",
    ".base-additional-fee-amount",
    "#globalCouponValue",
    "#shippingCost",
    "[data-option-price]",
    ".wdc2-dinput",
    ".wdc2-oamt",
    ".wdc2-subfee__amt",
    ".wdc2-directcell__amt",
    '.wdc2-psheet__in[inputmode="numeric"]',
].join(",");
window.WDC_AMOUNT_INPUT_SELECTOR = WDC_AMOUNT_INPUT_SELECTOR;

if (!window.__WDC_AMOUNT_COMMA_BOUND &&
    document.addEventListener && document.documentElement) {
    window.__WDC_AMOUNT_COMMA_BOUND = true;
    document.addEventListener("input", function (e) {
        var t = e.target;
        if (!t || typeof t.matches !== "function") return;
        if (e.isComposing === true) return;   // IME 조합 중 미개입
        if (!t.matches(WDC_AMOUNT_INPUT_SELECTOR)) return;
        wdcFormatAmountInput(t);
    });
}
