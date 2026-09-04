var _erpBoolConfirmed =
    window._erpBoolConfirmed ||
    function _erpBoolConfirmed(v) {
        if (v === true || v === 1) return true;
        if (v === false || v === 0 || v == null) return false;
        if (typeof v === "string") {
            var s = v.trim().toLowerCase();
            return s === "true" || s === "1" || s === "yes" || s === "on";
        }
        return false;
    };
window._erpBoolConfirmed = _erpBoolConfirmed;

/** edit_order / add_order runtime state; fragment/full-page both sync from DOM config. */
var ORDER_ID = parseInt(String(window.ORDER_ID || "0"), 10) || 0;
window.ORDER_ID = ORDER_ID;
var ERP_ORDER_ENABLED =
    typeof window.ERP_ORDER_ENABLED !== "undefined"
        ? _erpBoolConfirmed(window.ERP_ORDER_ENABLED)
        : false;
window.ERP_ORDER_ENABLED = ERP_ORDER_ENABLED;

var _erpPaymentIconSrc =
    window._erpPaymentIconSrc ||
    function _erpPaymentIconSrc(type, isConfirmed) {
        var urls = window.__ERP_PAYMENT_ICON_URLS;
        if (
            urls &&
            urls.depositConfirmed &&
            urls.depositUnconfirmed &&
            urls.balanceConfirmed &&
            urls.balanceUnconfirmed
        ) {
            if (type === "deposit") {
                return isConfirmed ? urls.depositConfirmed : urls.depositUnconfirmed;
            }
            return isConfirmed ? urls.balanceConfirmed : urls.balanceUnconfirmed;
        }
        var base = "/static/images/";
        if (type === "deposit") {
            return isConfirmed ? base + "pay-coin.png" : base + "pay-coin-gray.png";
        }
        return isConfirmed ? base + "pay-bill.png" : base + "pay-bill-gray.png";
    };
window._erpPaymentIconSrc = _erpPaymentIconSrc;

/** 라홈 표준 예약금(이 금액들은 미확인 시 회색 동전 유지). */
var ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS =
    window.ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS ||
    Object.freeze([50000, 100000, 200000, 300000, 400000]);
window.ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS = ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS;

/**
 * 발주사 라홈 + 표준 제외 양의 예약금 → 황금 동전 표시 여부.
 * 확정(deposit_confirmed)과 무관한 시각 힌트만 담당.
 */
var _erpShouldShowLahomDepositGold =
    window._erpShouldShowLahomDepositGold ||
    function _erpShouldShowLahomDepositGold(amount) {
        var orderer =
            typeof getOrdererValue === "function" ? getOrdererValue() : "";
        if (orderer !== "라홈") return false;
        var n = erpCoerceAmount(amount);
        if (n <= 0) return false;
        return ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS.indexOf(n) === -1;
    };
window._erpShouldShowLahomDepositGold = _erpShouldShowLahomDepositGold;

var erpCoerceAmount =
    window.erpCoerceAmount ||
    function erpCoerceAmount(value) {
        if (value == null) return 0;
        if (typeof value === "object") {
            return erpCoerceAmount(value.amount || value.raw || 0);
        }
        if (typeof value === "number") {
            return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
        }
        var digits = String(value || "").replace(/[^0-9]/g, "");
        return digits ? parseInt(digits, 10) : 0;
    };
window.erpCoerceAmount = erpCoerceAmount;

var erpResolveDepositAmount =
    window.erpResolveDepositAmount ||
    function erpResolveDepositAmount(sd) {
        sd = sd || {};
        var modernPayment = sd.payment || {};
        var legacyPayments = sd.payments || {};
        var modernDeposit = erpCoerceAmount(modernPayment.deposit);
        if (modernDeposit > 0) return modernDeposit;
        return erpCoerceAmount(legacyPayments.deposit);
    };
window.erpResolveDepositAmount = erpResolveDepositAmount;

var erpResolveDiscountAmount =
    window.erpResolveDiscountAmount ||
    function erpResolveDiscountAmount(sd) {
        sd = sd || {};
        var modernPayment = sd.payment || {};
        var totals = sd.totals || {};
        var modernDiscount = erpCoerceAmount(modernPayment.discount);
        if (modernDiscount > 0) return modernDiscount;
        return erpCoerceAmount(totals.discount_amount);
    };
window.erpResolveDiscountAmount = erpResolveDiscountAmount;

var erpResolveCashReceipt =
    window.erpResolveCashReceipt ||
    function erpResolveCashReceipt(sd) {
        sd = sd || {};
        var modernPayment = sd.payment || {};
        if (Object.prototype.hasOwnProperty.call(modernPayment, 'cash_receipt')) {
            return String(modernPayment.cash_receipt || '').trim();
        }
        var legacyPayments = sd.payments || {};
        var legacyEntry = legacyPayments.cash_receipt;
        if (legacyEntry && typeof legacyEntry === 'object') {
            return String(legacyEntry.value || legacyEntry.raw || '').trim();
        }
        return String(legacyEntry || '').trim();
    };
window.erpResolveCashReceipt = erpResolveCashReceipt;

var erpResolveBalanceNote =
    window.erpResolveBalanceNote ||
    function erpResolveBalanceNote(sd) {
        sd = sd || {};
        var modernPayment = sd.payment || {};
        if (Object.prototype.hasOwnProperty.call(modernPayment, 'balance_note')) {
            return String(modernPayment.balance_note || '').trim();
        }
        return '';
    };
window.erpResolveBalanceNote = erpResolveBalanceNote;

var erpResolveFreeInputText =
    window.erpResolveFreeInputText ||
    function erpResolveFreeInputText(sd) {
        sd = sd || {};
        var modernPayment = sd.payment || {};
        if (Object.prototype.hasOwnProperty.call(modernPayment, 'free_input')) {
            return String(modernPayment.free_input || '').trim();
        }
        var legacyPayments = sd.payments || {};
        var legacyEntry = legacyPayments.free_input;
        if (legacyEntry && typeof legacyEntry === 'object') {
            return String(legacyEntry.value || legacyEntry.raw || '').trim();
        }
        return String(legacyEntry || '').trim();
    };
window.erpResolveFreeInputText = erpResolveFreeInputText;

var erpSumFreeInputAmountFromText =
    window.erpSumFreeInputAmountFromText ||
    function erpSumFreeInputAmountFromText(text) {
        var raw = String(text || "").trim();
        if (!raw) return 0;
        var sum = 0;
        var lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
        for (var i = 0; i < lines.length; i += 1) {
            var trimmed = String(lines[i] || "").trim();
            if (!trimmed) continue;
            var amountPart = trimmed;
            var colonMatch = trimmed.match(/^[^:：]+[:：]\s*(.+)$/);
            if (colonMatch) {
                amountPart = colonMatch[1].trim();
            }
            var n = erpCoerceAmount(amountPart);
            if (n > 0) sum += n;
        }
        return sum;
    };
window.erpSumFreeInputAmountFromText = erpSumFreeInputAmountFromText;

var erpParseFreeInputAmount =
    window.erpParseFreeInputAmount ||
    function erpParseFreeInputAmount() {
        return erpParseFreeInputAmountFromField();
    };
window.erpParseFreeInputAmount = erpParseFreeInputAmount;

var erpBuildTotals =
    window.erpBuildTotals ||
    function erpBuildTotals(itemsTotal, depositAmount, discountAmount, freeInputAmount) {
        var itemsSubtotal = erpCoerceAmount(itemsTotal);
        var freeInput = erpCoerceAmount(freeInputAmount);
        var total = itemsSubtotal + freeInput;
        var deposit = erpCoerceAmount(depositAmount);
        var discount = erpCoerceAmount(discountAmount);
        var balance = Math.max(0, total - deposit - discount);
        var shippingPrice = Math.max(0, total - discount); // total = itemsSubtotal + freeInput
        return {
            items_total: itemsSubtotal,
            free_input_amount: freeInput,
            contract_total: total,
            deposit_amount: deposit,
            discount_amount: discount,
            balance_amount: balance,
            final_amount: balance,
            shipping_price: shippingPrice,
        };
    };
window.erpBuildTotals = erpBuildTotals;

var _erpNormalizePaymentData =
    window._erpNormalizePaymentData ||
    function _erpNormalizePaymentData(sd) {
        if (!sd) sd = {};
        var pay = sd.payment || {};
        var depositAmount = erpResolveDepositAmount(sd);
        var discountAmount = erpResolveDiscountAmount(sd);

        return {
            deposit: Math.max(0, depositAmount),
            discount: Math.max(0, discountAmount),
            free_input: erpResolveFreeInputText(sd),
            cash_receipt: erpResolveCashReceipt(sd),
            balance_note: erpResolveBalanceNote(sd),
            deposit_confirmed: _erpBoolConfirmed(pay.deposit_confirmed),
            deposit_confirmed_at: pay.deposit_confirmed_at || null,
            deposit_confirmed_by: pay.deposit_confirmed_by || null,
            deposit_confirmed_by_user_id: pay.deposit_confirmed_by_user_id || null,
            balance_confirmed: _erpBoolConfirmed(pay.balance_confirmed),
            balance_confirmed_at: pay.balance_confirmed_at || null,
            balance_confirmed_by: pay.balance_confirmed_by || null,
            balance_confirmed_by_user_id: pay.balance_confirmed_by_user_id || null,
        };
    };
window._erpNormalizePaymentData = _erpNormalizePaymentData;

var _erpUpdatePaymentConfirmUI =
    window._erpUpdatePaymentConfirmUI ||
    function _erpUpdatePaymentConfirmUI(type, paymentData) {
        var btn = document.querySelector(
            '.erp-payment-confirm-btn[data-payment-type="' + type + '"]'
        );
        if (!btn) return;
        var icon = btn.querySelector("img.erp-custom-payment-icon");
        if (!icon) return;

        var raw = type === "deposit" ? paymentData.deposit_confirmed : paymentData.balance_confirmed;
        var isConfirmed = _erpBoolConfirmed(raw);
        btn.dataset.confirmed = isConfirmed ? "1" : "0";

        if (isConfirmed) {
            icon.classList.add("erp-custom-payment-confirmed");
            icon.classList.remove("erp-custom-payment-unconfirmed");
            icon.classList.remove("erp-custom-payment-lahom-hint");
            icon.src = _erpPaymentIconSrc(type, true);
            var byName =
                type === "deposit"
                    ? paymentData.deposit_confirmed_by
                    : paymentData.balance_confirmed_by;
            var at =
                type === "deposit"
                    ? paymentData.deposit_confirmed_at
                    : paymentData.balance_confirmed_at;
            btn.title =
                "확인됨 (" +
                byName +
                " / " +
                (at ? at.substring(0, 16).replace("T", " ") : "-") +
                ") - 클릭하여 취소";
            return;
        }

        icon.classList.add("erp-custom-payment-unconfirmed");
        icon.classList.remove("erp-custom-payment-confirmed");
        // 라홈 비표준 예약금: 미확인이어도 황금 동전(pay-coin.png) 표시. 확정 상태는 그대로.
        var useGoldSrc = false;
        if (type === "deposit") {
            var depositEl = document.getElementById("erp-deposit-amount");
            useGoldSrc = _erpShouldShowLahomDepositGold(
                depositEl ? depositEl.value : 0
            );
        }
        if (useGoldSrc) {
            icon.classList.add("erp-custom-payment-lahom-hint");
        } else {
            icon.classList.remove("erp-custom-payment-lahom-hint");
        }
        icon.src = _erpPaymentIconSrc(type, useGoldSrc);
        btn.title = useGoldSrc
            ? "라홈 비표준 예약금 - 미확인 (클릭하여 확인 완료 처리)"
            : "미확인 - 클릭하여 확인 완료 처리";
    };
window._erpUpdatePaymentConfirmUI = _erpUpdatePaymentConfirmUI;

/** DOM 예약금/발주사 기준 예약금 동전 아이콘만 재동기화(확정 API 무호출). */
var _erpRefreshDepositCoinVisual =
    window._erpRefreshDepositCoinVisual ||
    function _erpRefreshDepositCoinVisual() {
        var btn = document.querySelector(
            '.erp-payment-confirm-btn[data-payment-type="deposit"]'
        );
        if (!btn) return;
        var pay =
            (window.__erpLastStructuredData &&
                window.__erpLastStructuredData.payment) ||
            {};
        _erpUpdatePaymentConfirmUI("deposit", {
            deposit_confirmed: btn.dataset.confirmed === "1",
            deposit_confirmed_by: pay.deposit_confirmed_by,
            deposit_confirmed_at: pay.deposit_confirmed_at,
        });
    };
window._erpRefreshDepositCoinVisual = _erpRefreshDepositCoinVisual;

var escapeHtml =
    window.escapeHtml ||
    function escapeHtml(text) {
        if (!text) return "";
        var div = document.createElement("div");
        div.textContent = String(text);
        return div.innerHTML;
    };
window.escapeHtml = escapeHtml;

var formatPhoneAuto =
    window.formatPhoneAuto ||
    function formatPhoneAuto(value) {
        var digits = String(value || "").replace(/[^0-9]/g, "");
        if (digits.length === 11) {
            return (
                digits.slice(0, 3) +
                "-" +
                digits.slice(3, 7) +
                "-" +
                digits.slice(7, 11)
            );
        }
        if (digits.length === 10) {
            return (
                digits.slice(0, 3) +
                "-" +
                digits.slice(3, 6) +
                "-" +
                digits.slice(6, 10)
            );
        }
        return value || "";
    };
window.formatPhoneAuto = formatPhoneAuto;

var getOrdererValue =
    window.getOrdererValue ||
    function getOrdererValue() {
        var direct = document.getElementById("erp-orderer-direct");
        var selectEl = document.getElementById("erp-orderer-select");
        var inputEl = document.getElementById("erp-orderer");
        if (direct && direct.checked && inputEl) return (inputEl.value || "").trim();
        if (selectEl) return (selectEl.value || "").trim();
        return inputEl && inputEl.value ? inputEl.value.trim() : "";
    };
window.getOrdererValue = getOrdererValue;

var erpNormalizeConstructionWorkers =
    window.erpNormalizeConstructionWorkers ||
    function erpNormalizeConstructionWorkers(value) {
        var rawValues;
        if (Array.isArray(value)) {
            rawValues = value;
        } else {
            rawValues = String(value || "").replace(/\n/g, ",").split(",");
        }
        var workers = [];
        rawValues.forEach(function (item) {
            var rawName = item;
            if (item && typeof item === "object") {
                rawName = item.name || item.text || item.value || "";
            }
            var name = String(rawName || "").trim();
            if (name && workers.indexOf(name) === -1) workers.push(name);
        });
        return workers;
    };
window.erpNormalizeConstructionWorkers = erpNormalizeConstructionWorkers;

var erpFormatConstructionWorkers =
    window.erpFormatConstructionWorkers ||
    function erpFormatConstructionWorkers(value) {
        return erpNormalizeConstructionWorkers(value).join("\n");
    };
window.erpFormatConstructionWorkers = erpFormatConstructionWorkers;

/**
 * 주소와 상세주소를 편집용 한 칸 문자열로 합친다 (ADDR-DUP-01).
 *
 * FOMS 정본 형태는 address_full 이 이미 상세주소를 품고 address_detail 은 빈 값이지만,
 * 외부 수집분·옛 문서에는 둘 다 들어 있는 행이 있다. 그대로 이어 붙이면 같은 동·호수가
 * 두 번 붙고, 저장 시 그 문자열이 주소로 굳는다(2026-08-14 운영 실측:
 * "… 103동 605호 103동 605호"). full 이 이미 detail 로 끝나면 붙이지 않는다.
 *
 * @param {string} full 전체 주소(address_full 또는 address_main).
 * @param {string} detail 상세주소(address_detail).
 * @returns {string} 편집 칸에 넣을 주소 문자열.
 */
function erpJoinSiteAddress(full, detail) {
    var base = (full || '').trim();
    var extra = (detail || '').trim();
    if (!extra) return base;
    if (!base) return extra;
    return base.endsWith(extra) ? base : (base + ' ' + extra);
}
window.erpJoinSiteAddress = erpJoinSiteAddress;

function erpConstructionWorkersEqual(left, right) {
    var a = erpNormalizeConstructionWorkers(left);
    var b = erpNormalizeConstructionWorkers(right);
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i += 1) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

function erpConfirmConstructionWorkerOverwrite() {
    var inputEl = document.getElementById("erp-construction-workers");
    if (!inputEl) return true;

    var previousWorkers = erpNormalizeConstructionWorkers(
        window.__erpLastStructuredData?.shipment?.construction_workers
    );
    var nextWorkers = erpNormalizeConstructionWorkers(inputEl.value);
    if (!previousWorkers.length || erpConstructionWorkersEqual(previousWorkers, nextWorkers)) {
        inputEl.value = erpFormatConstructionWorkers(nextWorkers);
        return true;
    }

    var nextLabel = nextWorkers.length ? nextWorkers.join("\n") : "공란";
    var confirmed = window.confirm(
        "현재 출고 대시보드 시공자: " +
        previousWorkers.join(", ") +
        ". " +
        nextLabel +
        "(으)로 변경하시겠습니까?"
    );
    if (confirmed) {
        inputEl.value = erpFormatConstructionWorkers(nextWorkers);
        return true;
    }

    inputEl.value = erpFormatConstructionWorkers(previousWorkers);
    if (typeof erpSetStatus === "function") {
        erpSetStatus("시공 담당자 변경이 취소되었습니다.", true);
    }
    return false;
}

var toggleOrdererUI =
    window.toggleOrdererUI ||
    function toggleOrdererUI() {
        var direct = document.getElementById("erp-orderer-direct");
        var selectEl = document.getElementById("erp-orderer-select");
        var inputEl = document.getElementById("erp-orderer");
        if (!direct || !selectEl || !inputEl) return;
        if (direct.checked) {
            selectEl.classList.add("d-none");
            inputEl.classList.remove("d-none");
            return;
        }
        selectEl.classList.remove("d-none");
        inputEl.classList.add("d-none");
    };
window.toggleOrdererUI = toggleOrdererUI;

var erpRefreshSpecCalcForOrderer =
    window.erpRefreshSpecCalcForOrderer ||
    function erpRefreshSpecCalcForOrderer() {
        if (window.ErpSpecCalc && typeof window.ErpSpecCalc.refreshForOrderer === "function") {
            window.ErpSpecCalc.refreshForOrderer(document);
        }
    };
window.erpRefreshSpecCalcForOrderer = erpRefreshSpecCalcForOrderer;

function erpGetRegionalConstructionType() {
    const selectEl = document.getElementById('erp-regional-construction-type');
    return (selectEl?.value || '').trim();
}

function erpSyncRegionalConstructionTypeVisibility(options = {}) {
    const regionalEl = document.getElementById('erp-regional-order');
    const fieldEl = document.getElementById('erp-regional-construction-type-field');
    const selectEl = document.getElementById('erp-regional-construction-type');
    if (!regionalEl || !fieldEl || !selectEl) return;

    if (regionalEl.checked) {
        fieldEl.classList.remove('d-none');
        // ORDER-FLAG-01: 지방주문 체크박스를 못 만지는 사용자는 구분도 못 바꾼다(서버도 무시한다).
        selectEl.disabled = !!regionalEl.disabled;
        return;
    }

    fieldEl.classList.add('d-none');
    selectEl.disabled = true;
    if (options.clear !== false) {
        selectEl.value = '';
    }
}

var syncWorkflowStageByOrderer =
    window.syncWorkflowStageByOrderer ||
    function syncWorkflowStageByOrderer() {
        erpRefreshSpecCalcForOrderer();
        if (typeof _erpRefreshDepositCoinVisual === "function") {
            _erpRefreshDepositCoinVisual();
        }
        var orderer = (typeof getOrdererValue === "function" ? getOrdererValue() : "").trim();
        if (orderer === "라홈") return;
        var stageEl = document.getElementById("erp-workflow-stage");
        if (stageEl && stageEl.querySelector('option[value="MEASURE"]')) {
            stageEl.value = "MEASURE";
        }
    };
window.syncWorkflowStageByOrderer = syncWorkflowStageByOrderer;

/**
 * AS 가 진행 중이면 '본공정 단계' select 맨 앞에 저장되지 않는 표시 옵션을 끼운다.
 *
 * AS 축(as_lifecycle)과 본공정 stage 는 직교한다(STATE-AS-01). 그래서 AS 접수해도
 * 드롭다운은 계속 '실측'을 보여줬고, 사용자는 저장이 안 된 것으로 읽었다. 값을 실제로
 * AS_RECEIVED 로 바꾸면 AS 종료 후 되돌릴 근거가 없어 도면·생산·시공 큐에서 주문이
 * 영구 이탈한다(2026-09-04 운영 실측 62건). 그래서 표시만 바꾸고 저장값은 본공정 그대로 둔다.
 *
 * @param {boolean} [force] AS 접수 직후처럼 data 속성 갱신 전에도 켜야 할 때 true.
 */
function erpApplyAsStageDisplay(force) {
    var stageEl = document.getElementById('erp-workflow-stage');
    if (!stageEl) return;
    var existing = stageEl.querySelector('option[data-erp-as-display]');
    if (existing) existing.remove();
    stageEl.removeAttribute('title');
    var active = force === true || (stageEl.dataset.erpAsActive || '') === '1';
    if (!active) return;
    var asLabel = (stageEl.dataset.erpAsLabel || '').trim() || '접수';
    var current = stageEl.selectedIndex >= 0 ? stageEl.options[stageEl.selectedIndex] : null;
    var mainLabel = current ? (current.textContent || '').replace(/^[A-H]\.\s*/, '').trim() : '';
    if (mainLabel === '-') mainLabel = '';  // 빈 선택 placeholder 는 본공정이 아니다
    var opt = document.createElement('option');
    opt.value = '';
    opt.disabled = true;
    opt.setAttribute('data-erp-as-display', '1');
    // '접수'/'처리' 는 진행 중이라 '중' 을 붙이고, '완료' 는 끝난 상태라 안 붙인다
    // ('AS 완료 중' 은 뜻이 어긋난다).
    var asPhrase = asLabel === '완료' ? 'AS 완료' : ('AS ' + asLabel + ' 중');
    // select 실측 폭이 163px(가용 129px)라 '본공정: X' 를 붙이면 195px 로 잘린다
    // (2026-09-04 스테이징 실측). 보이는 글자는 짧게 두고 본공정은 title 로 넘긴다.
    // 레거시로 stage 가 AS_* 인 주문은 그 값이 옵션 목록에 없어 선택이 비어 있다 -
    // 없는 본공정을 지어내지 않는다.
    opt.textContent = asPhrase;
    var tip = mainLabel ? (asPhrase + ' · 본공정: ' + mainLabel) : asPhrase;
    opt.title = tip;
    stageEl.title = tip;
    stageEl.insertBefore(opt, stageEl.firstChild);
    stageEl.selectedIndex = 0;
}
window.erpApplyAsStageDisplay = erpApplyAsStageDisplay;

var syncWorkflowStageByMeasurementDate =
    window.syncWorkflowStageByMeasurementDate ||
    function syncWorkflowStageByMeasurementDate() {
        var measurementDateEl = document.getElementById("erp-measurement-date");
        var stageEl = document.getElementById("erp-workflow-stage");
        if (!measurementDateEl || !stageEl) return;
        var hasMeasurementDate = (measurementDateEl.value || "").trim() !== "";
        var current = String(stageEl.value || "").trim();
        var orderer = (typeof getOrdererValue === "function" ? getOrdererValue() : "").trim();
        var isLahomLike = !orderer || orderer === "라홈";
        // 서버 자동 전진/복귀와 동일: RECEIVED↔MEASURE 1칸만. 도면 이후는 유지.
        if (hasMeasurementDate && (!current || current === "RECEIVED") &&
                stageEl.querySelector('option[value="MEASURE"]')) {
            stageEl.value = "MEASURE";
        } else if (!hasMeasurementDate && current === "MEASURE" && isLahomLike &&
                stageEl.querySelector('option[value="RECEIVED"]')) {
            stageEl.value = "RECEIVED";
        }
        if (window.FOMS_STAGE_OVERRIDE &&
                typeof window.FOMS_STAGE_OVERRIDE.noteCurrentStage === "function") {
            window.FOMS_STAGE_OVERRIDE.noteCurrentStage(stageEl.value);
        }
    };
window.syncWorkflowStageByMeasurementDate = syncWorkflowStageByMeasurementDate;

var adjustTextareaHeight =
    window.adjustTextareaHeight ||
    function adjustTextareaHeight(textarea) {
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = textarea.scrollHeight + "px";
    };
window.adjustTextareaHeight = adjustTextareaHeight;

var erpGetDraftEndpoint =
    window.erpGetDraftEndpoint ||
    function erpGetDraftEndpoint() {
        return window.__ERP_DRAFT_ENDPOINT || "/api/orders/erp/draft";
    };
window.erpGetDraftEndpoint = erpGetDraftEndpoint;

var erpGetDraftRequestToken =
    window.erpGetDraftRequestToken ||
    function erpGetDraftRequestToken() {
        if (!window.__ERP_DRAFT_REQUEST_TOKEN) {
            if (window.crypto && typeof window.crypto.randomUUID === "function") {
                window.__ERP_DRAFT_REQUEST_TOKEN = window.crypto.randomUUID();
            } else {
                window.__ERP_DRAFT_REQUEST_TOKEN =
                    String(Date.now()) + "-" + String(Math.random()).slice(2);
            }
        }
        return window.__ERP_DRAFT_REQUEST_TOKEN;
    };
window.erpGetDraftRequestToken = erpGetDraftRequestToken;

var erpSetDraftBanner =
    window.erpSetDraftBanner ||
    function erpSetDraftBanner(orderId) {
        var banner = document.getElementById("erp-draft-banner");
        var idEl = document.getElementById("erp-draft-order-id");
        var link = document.getElementById("erp-draft-edit-link");
        if (idEl) idEl.textContent = String(orderId || "-");
        if (link && orderId) {
            link.href = "/edit/" + orderId;
            link.style.display = "";
        }
        if (banner) banner.style.display = orderId ? "" : "none";
    };
window.erpSetDraftBanner = erpSetDraftBanner;

var erpSetOrderId =
    window.erpSetOrderId ||
    function erpSetOrderId(newId) {
        try {
            var oldOrderId = ORDER_ID;
            ORDER_ID = parseInt(String(newId || "0"), 10) || 0;
            if (oldOrderId !== ORDER_ID) {
                var fileInput = document.getElementById("erp-attachments-input");
                if (fileInput) {
                    fileInput.value = "";
                }
            }
        } catch (e) {}

        var host =
            document.querySelector(".card[data-erp-order-id]") ||
            document.querySelector("[data-erp-order-id]");
        if (host) {
            host.setAttribute("data-erp-order-id", String(ORDER_ID));
        }
        erpSetDraftBanner(ORDER_ID);
    };
window.erpSetOrderId = erpSetOrderId;

var erpEnsureDraftOrderId =
    window.erpEnsureDraftOrderId ||
    async function erpEnsureDraftOrderId() {
        if (!ERP_ORDER_ENABLED) return 0;
        if (!isErpOrderDraftMode()) return ORDER_ID || 0;
        if (ORDER_ID && ORDER_ID > 0) return ORDER_ID;

        var res = await fetch(erpGetDraftEndpoint(), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ draft_token: erpGetDraftRequestToken() }),
        });
        var data = await res.json();
        if (!data || !data.success) {
            throw new Error(
                data && data.message ? data.message : "Draft 생성 실패 (HTTP " + res.status + ")"
            );
        }
        erpSetOrderId(data.order_id);

        if (!window.__erpDraftUnloadBound) {
            window.__erpDraftUnloadBound = true;
            window.addEventListener("beforeunload", function (e) {
                if (isErpOrderDraftMode() && ORDER_ID && ORDER_ID > 0) {
                    e.preventDefault();
                    e.returnValue =
                        "작성 중인 주문이 저장되지 않았습니다. 페이지를 떠나시겠습니까?";
                }
            });
        }

        return ORDER_ID;
    };
window.erpEnsureDraftOrderId = erpEnsureDraftOrderId;

var erpRequireOrderIdOrWarn =
    window.erpRequireOrderIdOrWarn ||
    async function erpRequireOrderIdOrWarn(contextText) {
        var prefix = contextText || "";
        try {
            var id = await erpEnsureDraftOrderId();
            if (!id) {
                erpSetStatus(prefix + " 주문번호 생성 실패", true);
                return 0;
            }
            return id;
        } catch (e) {
            console.error(e);
            erpSetStatus(prefix + " " + String((e && e.message) || e), true);
            return 0;
        }
    };
window.erpRequireOrderIdOrWarn = erpRequireOrderIdOrWarn;

function erpResolveCurrentOrderId() {
    let targetId = parseInt(String(ORDER_ID || '0'), 10) || 0;
    if (targetId > 0) return targetId;

    const cardEl =
        document.querySelector('.card[data-erp-order-id]') ||
        document.querySelector('.card[data-order-id]');
    if (!cardEl) return 0;

    const idVal = cardEl.dataset.erpOrderId || cardEl.dataset.orderId || '0';
    return parseInt(String(idVal), 10) || 0;
}
window.erpResolveCurrentOrderId = erpResolveCurrentOrderId;

function erpIsDraftBackedOrder() {
    const metaDraft = window.__erpLastStructuredData &&
        window.__erpLastStructuredData.meta &&
        window.__erpLastStructuredData.meta.draft === true;
    return isErpOrderDraftMode() || !!metaDraft;
}
window.erpIsDraftBackedOrder = erpIsDraftBackedOrder;

function erpCanUsePersistedOrderAction(actionText) {
    if (!ERP_ORDER_ENABLED) return false;
    const targetId = erpResolveCurrentOrderId();
    if (targetId > 0 && !erpIsDraftBackedOrder()) return true;

    const label = actionText || '이 작업은';
    const message = `${label} 주문 저장 후 사용할 수 있습니다.`;
    erpSetStatus(message, true);
    alert(message);
    return false;
}
window.erpCanUsePersistedOrderAction = erpCanUsePersistedOrderAction;

function erpToggleLocalPaymentState(pType, targetConfirmed) {
    const previousPayment = window.__erpLastStructuredData && window.__erpLastStructuredData.payment
        ? window.__erpLastStructuredData.payment
        : {};
    const nextPayment = _erpNormalizePaymentData({ payment: previousPayment });

    if (pType === 'deposit') {
        nextPayment.deposit_confirmed = targetConfirmed;
        nextPayment.deposit_confirmed_at = targetConfirmed ? new Date().toISOString() : null;
        nextPayment.deposit_confirmed_by = targetConfirmed ? '저장 전' : null;
        nextPayment.deposit_confirmed_by_user_id = null;
    } else {
        nextPayment.balance_confirmed = targetConfirmed;
        nextPayment.balance_confirmed_at = targetConfirmed ? new Date().toISOString() : null;
        nextPayment.balance_confirmed_by = targetConfirmed ? '저장 전' : null;
        nextPayment.balance_confirmed_by_user_id = null;
    }

    if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
        window.__erpLastStructuredData = {};
    }
    window.__erpLastStructuredData.payment = nextPayment;
    _erpUpdatePaymentConfirmUI(pType, nextPayment);
    erpSetStatus('결제 확인 상태가 저장 전 임시 반영되었습니다. 최종 저장 버튼을 누르면 저장됩니다.');
}
window.erpToggleLocalPaymentState = erpToggleLocalPaymentState;

var erpSetStatus =
    window.erpSetStatus ||
    function erpSetStatus(text, isError) {
        var el = document.getElementById("erp-status-text");
        if (!el) return;
        el.textContent = text || "";
        el.style.color = isError ? "#b02a37" : "#6c757d";
    };
window.erpSetStatus = erpSetStatus;

var erpFormatMoneyKRW =
    window.erpFormatMoneyKRW ||
    function erpFormatMoneyKRW(num) {
        var n = Number(num);
        if (!Number.isFinite(n)) return "0원";
        return Math.round(n).toLocaleString("ko-KR") + "원";
    };
window.erpFormatMoneyKRW = erpFormatMoneyKRW;

var erpParseDepositValue =
    window.erpParseDepositValue ||
    function erpParseDepositValue() {
        var el = document.getElementById("erp-deposit-amount");
        if (!el) return 0;
        return erpCoerceAmount(el.value);
    };
window.erpParseDepositValue = erpParseDepositValue;

var erpParseDiscountValue =
    window.erpParseDiscountValue ||
    function erpParseDiscountValue() {
        var el = document.getElementById("erp-discount-amount");
        if (!el) return 0;
        return erpCoerceAmount(el.value);
    };
window.erpParseDiscountValue = erpParseDiscountValue;

var erpParseFreeInputLabelText =
    window.erpParseFreeInputLabelText ||
    function erpParseFreeInputLabelText() {
        var el = document.getElementById("erp-free-input-text");
        if (!el) return "";
        return String(el.value || "").trim();
    };
window.erpParseFreeInputLabelText = erpParseFreeInputLabelText;

var erpParseFreeInputAmountFromField =
    window.erpParseFreeInputAmountFromField ||
    function erpParseFreeInputAmountFromField() {
        var el = document.getElementById("erp-free-input-amount");
        if (!el) return 0;
        return erpCoerceAmount(el.value);
    };
window.erpParseFreeInputAmountFromField = erpParseFreeInputAmountFromField;

var erpSplitFreeInputForForm =
    window.erpSplitFreeInputForForm ||
    function erpSplitFreeInputForForm(stored) {
        var raw = String(stored || "").trim();
        if (!raw) return { text: "", amount: 0 };
        var lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
        var first = "";
        for (var i = 0; i < lines.length; i += 1) {
            var line = String(lines[i] || "").trim();
            if (line) {
                first = line;
                break;
            }
        }
        if (!first) return { text: "", amount: 0 };
        var colonMatch = first.match(/^(.+?)[:：]\s*(.+)$/);
        if (colonMatch) {
            return {
                text: colonMatch[1].trim(),
                amount: erpCoerceAmount(colonMatch[2]),
            };
        }
        var asAmount = erpCoerceAmount(first);
        if (asAmount > 0 && String(first).replace(/[^0-9]/g, "").length >= String(asAmount).length) {
            return { text: "", amount: asAmount };
        }
        return { text: first, amount: 0 };
    };
window.erpSplitFreeInputForForm = erpSplitFreeInputForForm;

var erpBuildFreeInputStoredValue =
    window.erpBuildFreeInputStoredValue ||
    function erpBuildFreeInputStoredValue() {
        var label = erpParseFreeInputLabelText();
        var amount = erpParseFreeInputAmountFromField();
        if (!label && amount <= 0) return "";
        if (!label) return erpFormatDepositDisplay(amount);
        if (amount <= 0) return label;
        return label + " : " + Math.round(amount).toLocaleString("ko-KR");
    };
window.erpBuildFreeInputStoredValue = erpBuildFreeInputStoredValue;

/** 변환/PUSH용: `항목 : 120,000` → `항목 : 120,000원` (저장값은 원 미포함 유지). */
var erpFormatFreeInputForConversion =
    window.erpFormatFreeInputForConversion ||
    function erpFormatFreeInputForConversion(value) {
        var raw = String(value ?? '').trim();
        if (!raw) return '';
        return raw
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .split('\n')
            .map(erpFormatFreeInputForConversionLine)
            .filter(function (line) {
                return !!line;
            })
            .join('\n');
    };
window.erpFormatFreeInputForConversion = erpFormatFreeInputForConversion;

function erpFormatFreeInputForConversionLine(line) {
    var trimmed = String(line || '').trim();
    if (!trimmed) return '';
    var colonMatch = trimmed.match(/^(.+?)[:：]\s*(.+)$/);
    if (colonMatch) {
        var label = colonMatch[1].trim();
        var amountPart = colonMatch[2].trim();
        if (/원$/.test(amountPart)) {
            return label + ' : ' + amountPart;
        }
        var amount = erpCoerceAmount(amountPart);
        if (amount > 0) {
            return label + ' : ' + erpFormatMoneyKRW(amount);
        }
        return trimmed;
    }
    if (/원$/.test(trimmed)) {
        return trimmed;
    }
    var asAmount = erpCoerceAmount(trimmed);
    if (asAmount > 0) {
        return erpFormatMoneyKRW(asAmount);
    }
    return trimmed;
}

var erpParseFreeInputText =
    window.erpParseFreeInputText ||
    function erpParseFreeInputText() {
        return erpBuildFreeInputStoredValue();
    };
window.erpParseFreeInputText = erpParseFreeInputText;

var erpFormatDepositDisplay =
    window.erpFormatDepositDisplay ||
    function erpFormatDepositDisplay(num) {
        if (num == null || !Number.isFinite(num) || num < 0) return "0원";
        return num === 0 ? "0원" : num.toLocaleString("ko-KR") + "원";
    };
window.erpFormatDepositDisplay = erpFormatDepositDisplay;

/** 금액 input 공통: 입력 시 천단위 쉼표 + '원' suffix, backspace는 suffix 앞 숫자부터 삭제. */
var erpBindAmountInput =
    window.erpBindAmountInput ||
    function erpBindAmountInput(inputEl, parseFn, onRecalc) {
        if (!inputEl || inputEl.dataset.erpAmountBound === '1') return;
        inputEl.dataset.erpAmountBound = '1';
        const recalc = typeof onRecalc === 'function' ? onRecalc : erpCalculateRemaining;

        // iOS Safari 는 값 재대입 직후 caret 을 끝('원' 뒤)으로 되돌리는 경우가 있어
        // 다음 프레임에 한 번 더 확인해 바로잡는다.
        function applyAmountCaret(el, pos) {
            if (!el || typeof el.setSelectionRange !== 'function') return;
            try {
                el.setSelectionRange(pos, pos);
            } catch (_e) {
                return; /* 포커스 밖 — 복원 실패는 무해 */
            }
            if (typeof window.requestAnimationFrame !== 'function') return;
            window.requestAnimationFrame(function () {
                if (document.activeElement !== el || el.selectionStart === pos) return;
                try {
                    el.setSelectionRange(pos, pos);
                } catch (_e2) {
                    /* 무해 */
                }
            });
        }
        function setAmountCaretBeforeSuffix(el) {
            if (!el || typeof el.setSelectionRange !== 'function' || !String(el.value || '').endsWith('원')) return;
            applyAmountCaret(el, Math.max(0, String(el.value || '').length - 1));
        }
        // 재포맷 후 caret 을 '끝에서부터의 오프셋'으로 보존한다(중간 자릿수 수정 시 끝으로
        // 튀지 않게). 하한 1 이라 접미사 '원' 뒤로는 가지 않는다.
        function restoreAmountCaret(el, prevValue, prevCaret, formatted) {
            const caret = prevCaret == null ? prevValue.length : prevCaret;
            const fromEnd = Math.max(1, prevValue.length - caret);
            applyAmountCaret(el, Math.max(0, formatted.length - fromEnd));
        }
        function deleteErpAmountDigitBeforeSuffix(el) {
            const value = String(el.value || '');
            const start = el.selectionStart;
            const end = el.selectionEnd;
            if (!value.endsWith('원') || start == null || end == null || start !== end || start !== value.length) {
                return false;
            }
            const raw = value.replace(/[^0-9]/g, '');
            if (!raw) return false;
            const nextRaw = raw.slice(0, -1);
            el.value = nextRaw ? erpFormatDepositDisplay(parseInt(nextRaw, 10)) : '';
            setAmountCaretBeforeSuffix(el);
            recalc();
            return true;
        }
        inputEl.addEventListener('keydown', function (event) {
            if (event.key !== 'Backspace') return;
            if (deleteErpAmountDigitBeforeSuffix(this)) event.preventDefault();
        });
        inputEl.addEventListener('beforeinput', function (event) {
            if (event.inputType !== 'deleteContentBackward') return;
            if (deleteErpAmountDigitBeforeSuffix(this)) event.preventDefault();
        });
        inputEl.addEventListener('input', function () {
            const prevValue = String(this.value || '');
            const prevCaret = this.selectionStart;
            const raw = prevValue.replace(/[^0-9]/g, '');
            if (!raw) {
                if (this.value !== '') this.value = '';
                recalc();
                return;
            }
            const num = parseInt(raw, 10);
            const formatted = erpFormatDepositDisplay(num);
            if (this.value !== formatted) this.value = formatted;
            restoreAmountCaret(this, prevValue, prevCaret, formatted);
            recalc();
        });
        inputEl.addEventListener('change', function () {
            const num = typeof parseFn === 'function' ? parseFn() : erpCoerceAmount(this.value);
            this.value = erpFormatDepositDisplay(num);
            recalc();
        });
    };
window.erpBindAmountInput = erpBindAmountInput;


// --- ERP Order shared-form island (moved from templates/partials/erp_order_js.html, W5-B8) ---
// ============================================================
// ERP Order JS (shared): edit_order + add_order
//
// Required globals:
// - ERP_ORDER_ENABLED (boolean)
// - ORDER_ID (number; in add_order should be "let", in edit_order can be const)
// - USE_DIRECT_UPLOAD (boolean): true면 session→PUT→complete 플로우 사용
// - window.__ERP_ORDER_DRAFT_MODE (boolean): true on add_order, false on edit_order
// - window.__ERP_DRAFT_ENDPOINT (string): optional, default '/api/orders/erp/draft'
// ============================================================

// Shared-form island logic (runs after helper block above in this file).
let _paymentTogglePending = false;

var erpSumItemsSubtotal =
    window.erpSumItemsSubtotal ||
    function erpSumItemsSubtotal(scope) {
        var root = scope || document.getElementById('erp-items');
        if (!root) return 0;
        var sum = 0;
        root.querySelectorAll('[data-erp="price"]').forEach(function (inp) {
            var digits = String(inp.value || '').replace(/[^0-9]/g, '');
            if (digits) sum += parseInt(digits, 10);
        });
        return sum;
    };
window.erpSumItemsSubtotal = erpSumItemsSubtotal;

function erpRecalcItemsTotal() {
    const itemsWrap = document.getElementById('erp-items');
    const totalEl = document.getElementById('erp-items-total');
    const discountSection = document.getElementById('erp-discount-section');
    const remainingSection = document.getElementById('erp-remaining-section');
    const freeInputSection = document.getElementById('erp-free-input-section');
    const cashReceiptSection = document.getElementById('erp-cash-receipt-section');
    const balanceNoteToggleRow = document.getElementById('erp-balance-note-toggle-row');
    const balanceNoteSection = document.getElementById('erp-balance-note-section');
    if (!itemsWrap || !totalEl) return;
    const sum = erpSumItemsSubtotal(itemsWrap);
    const totals = erpBuildTotals(sum, erpParseDepositValue(), erpParseDiscountValue(), erpParseFreeInputAmount());
    totalEl.textContent = erpFormatMoneyKRW(totals.shipping_price);
    totalEl.dataset.itemsSubtotal = String(sum);
    if (window.ErpItemsMasterDetail?.syncRailTotal) {
        window.ErpItemsMasterDetail.syncRailTotal();
    }
    const showAmountRows = sum > 0 && Number.isFinite(sum);
    if (discountSection) {
        discountSection.style.display = showAmountRows ? '' : 'none';
    }
    if (remainingSection) {
        remainingSection.style.display = showAmountRows ? '' : 'none';
    }
    if (freeInputSection) {
        freeInputSection.style.display = showAmountRows ? '' : 'none';
    }
    if (cashReceiptSection) {
        cashReceiptSection.style.display = showAmountRows ? '' : 'none';
    }
    if (balanceNoteToggleRow) {
        balanceNoteToggleRow.hidden = !showAmountRows;
    }
    if (balanceNoteSection) {
        if (!showAmountRows) {
            balanceNoteSection.hidden = true;
        } else {
            balanceNoteSection.hidden = !erpIsBalanceNoteSectionOpen();
        }
    }
    erpUpdateBalanceNoteToggleUi();
    erpCalculateRemaining();
}

function erpIsBalanceNoteSectionOpen() {
    const section = document.getElementById('erp-balance-note-section');
    if (!section) return false;
    return section.dataset.erpOpen === '1';
}

function erpSetBalanceNoteSectionOpen(open, opts) {
    opts = opts || {};
    const section = document.getElementById('erp-balance-note-section');
    if (!section) return;
    section.dataset.erpOpen = open ? '1' : '0';
    section.hidden = !open;
    if (!open && opts.clearValue !== false) {
        const noteEl = document.getElementById('erp-balance-note');
        if (noteEl) noteEl.value = '';
    }
    erpUpdateBalanceNoteToggleUi();
}

function erpUpdateBalanceNoteToggleUi() {
    const toggleBtn = document.getElementById('erp-balance-note-toggle');
    if (!toggleBtn) return;
    const open = erpIsBalanceNoteSectionOpen();
    toggleBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggleBtn.textContent = open ? '−' : '+';
    toggleBtn.title = open ? '잔금 메모 삭제' : '잔금 메모 추가';
    toggleBtn.setAttribute('aria-label', toggleBtn.title);
}

function erpToggleBalanceNoteSection() {
    if (erpIsBalanceNoteSectionOpen()) {
        erpSetBalanceNoteSectionOpen(false, { clearValue: true });
        return;
    }
    erpSetBalanceNoteSectionOpen(true, { clearValue: false });
    const noteEl = document.getElementById('erp-balance-note');
    if (noteEl && typeof noteEl.focus === 'function') {
        noteEl.focus();
    }
}
window.erpToggleBalanceNoteSection = erpToggleBalanceNoteSection;

function erpCalculateRemaining() {
    const totalEl = document.getElementById('erp-items-total');
    const remainingEl = document.getElementById('erp-remaining-amount');
    if (!totalEl || !remainingEl) return;
    const itemsSubtotal = erpSumItemsSubtotal();
    const totals = erpBuildTotals(
        itemsSubtotal,
        erpParseDepositValue(),
        erpParseDiscountValue(),
        erpParseFreeInputAmount()
    );
    totalEl.textContent = erpFormatMoneyKRW(totals.shipping_price);
    totalEl.dataset.itemsSubtotal = String(itemsSubtotal);
    if (window.ErpItemsMasterDetail?.syncRailTotal) {
        window.ErpItemsMasterDetail.syncRailTotal();
    }
    remainingEl.textContent = totals.final_amount > 0 ? erpFormatMoneyKRW(totals.final_amount) : '0원';
}

/** 항목 금액 `[data-erp="price"]` — PC·모바일 동일 천단위 쉼표 포맷. */
var erpBindPriceInput =
    window.erpBindPriceInput ||
    function erpBindPriceInput(inputEl) {
        if (!inputEl) return;
        erpBindAmountInput(
            inputEl,
            function () {
                return erpCoerceAmount(inputEl.value);
            },
            erpRecalcItemsTotal
        );
    };
window.erpBindPriceInput = erpBindPriceInput;

var erpBindAllPriceInputs =
    window.erpBindAllPriceInputs ||
    function erpBindAllPriceInputs(scope) {
        const root = scope || document;
        root.querySelectorAll('[data-erp="price"]').forEach(function (inp) {
            erpBindPriceInput(inp);
        });
    };
window.erpBindAllPriceInputs = erpBindAllPriceInputs;

function erpGetItemRows() {
    const wrap = document.getElementById('erp-items');
    if (!wrap) return [];
    return Array.from(wrap.querySelectorAll('.erp-item-row'));
}

function erpGetItemIndexFromRow(rowEl) {
    if (!rowEl) return -1;
    const n = Number(rowEl.dataset.itemIndex);
    return Number.isInteger(n) && n >= 0 ? n : -1;
}

function erpGetItemNameByIndex(index) {
    if (!Number.isInteger(index) || index < 0) return '';
    const row = erpGetItemRows().find((r) => erpGetItemIndexFromRow(r) === index);
    if (!row) return '';
    const nameEl = row.querySelector('[data-erp="product_name"]');
    return String(nameEl?.value || '').trim();
}

function erpRefreshItemRowIndices() {
    const rows = erpGetItemRows();
    rows.forEach((row, idx) => {
        row.dataset.itemIndex = String(idx);
        const titleEl = row.querySelector('.erp-item-title');
        if (titleEl) {
            titleEl.textContent = `항목 ${idx + 1}`;
        }
        const hintEl = row.querySelector('.erp-item-attachment-hint');
        if (hintEl) {
            const name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
            hintEl.textContent = erpItemAttachmentHintText(name, idx);
        }
        erpUpdateItemSummary(row);
    });
    if (window.ErpItemsMasterDetail?.isActive?.()) {
        window.ErpItemsMasterDetail.refresh();
    }
}

// 모바일 항목 카드 접힘 시 한 줄 요약(제품명 · W×D×H · 금액)을 헤더에 반영.
// 데스크톱 행에는 요약 span이 없으므로 no-op.
function erpUpdateItemSummary(row) {
    if (!row) return;
    const specEl = row.querySelector('.erp-item-summary-spec');
    const amtEl = row.querySelector('.erp-item-summary-amount');
    if (!specEl && !amtEl) return;
    const name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
    const firstSpec = row.querySelector('.erp-spec-row');
    let specText = '';
    if (firstSpec) {
        const w = String(firstSpec.querySelector('[data-erp="spec_width"]')?.value || '').trim();
        const d = String(firstSpec.querySelector('[data-erp="spec_depth"]')?.value || '').trim();
        const h = String(firstSpec.querySelector('[data-erp="spec_height"]')?.value || '').trim();
        specText = [w, d, h].filter(Boolean).join('×');
    }
    if (specEl) {
        specEl.textContent = [name, specText].filter(Boolean).join(' · ') || '내용 없음';
    }
    if (amtEl) {
        const digits = String(row.querySelector('[data-erp="price"]')?.value || '').replace(/[^0-9]/g, '');
        amtEl.textContent = digits ? erpFormatMoneyKRW(parseInt(digits, 10)) : '';
    }
}

// 모바일 항목 아코디언: 한 번에 한 항목만 펼친다.
function erpToggleItemRow(row, forceOpen) {
    if (!row) return;
    const wrap = document.getElementById('erp-items');
    const open = typeof forceOpen === 'boolean' ? forceOpen : !row.classList.contains('is-open');
    if (open && wrap) {
        wrap.querySelectorAll('.erp-item-row.is-open').forEach((other) => {
            if (other !== row) {
                other.classList.remove('is-open');
                other.querySelector('.erp-item-head-toggle')?.setAttribute('aria-expanded', 'false');
            }
        });
    }
    row.classList.toggle('is-open', open);
    row.querySelector('.erp-item-head-toggle')?.setAttribute('aria-expanded', String(open));
    if (open) erpUpdateItemSummary(row);
}

// 렌더 직후 첫 항목만 펼친다(모바일). 데스크톱은 토글이 없어 no-op.
function erpOpenFirstItemRow() {
    const rows = erpGetItemRows();
    if (!rows.length) return;
    if (window.ErpItemsMasterDetail?.isActive?.()) {
        window.ErpItemsMasterDetail.selectItem(0);
        return;
    }
    rows.forEach((r, i) => {
        if (r.querySelector('.erp-item-head-toggle')) erpToggleItemRow(r, i === 0);
    });
}

function erpResolveAutosizeMinHeight(el) {
    const fromDataset = el.dataset.erpMinHeight ? Number(el.dataset.erpMinHeight) : 0;
    if (typeof erpIsMobileFormContext === 'function' && erpIsMobileFormContext() && el.classList.contains('erp-flex-textarea')) {
        return Math.max(fromDataset, 40);
    }
    return fromDataset;
}

function erpAutosizeTextarea(el) {
    if (!el || el.tagName !== 'TEXTAREA') return;
    const isMobile = typeof erpIsMobileFormContext === 'function' && erpIsMobileFormContext();
    if (isMobile && el.classList.contains('erp-flex-textarea')) {
        const minH = erpResolveAutosizeMinHeight(el);
        const value = String(el.value ?? '');
        const isBlank = value.length === 0 || (value.trim().length === 0 && !value.includes('\n'));
        if (isBlank) {
            el.style.height = minH > 0 ? `${minH}px` : 'auto';
            return;
        }
        el.style.height = '0';
        el.style.height = `${Math.max(el.scrollHeight, minH || 0)}px`;
        return;
    }
    const minH = el.dataset.erpMinHeight ? Number(el.dataset.erpMinHeight) : 0;
    el.style.height = '0';
    el.style.height = `${Math.max(el.scrollHeight, minH)}px`;
}

function erpBindAutosizeTextareas(root) {
    const scope = root || document;
    scope.querySelectorAll('textarea.erp-autosize-textarea').forEach((el) => {
        if (el.dataset.erpAutosizeBound !== '1') {
            el.dataset.erpAutosizeBound = '1';
            el.addEventListener('input', () => erpAutosizeTextarea(el));
            el.addEventListener('change', () => erpAutosizeTextarea(el));
        }
        window.requestAnimationFrame
            ? window.requestAnimationFrame(() => erpAutosizeTextarea(el))
            : erpAutosizeTextarea(el);
    });
}

function erpIsMobileFormContext() {
    return !!document.querySelector('.erp-order-mobile-form');
}

function erpItemAttachmentHintText(productName, itemIndex) {
    if (erpIsMobileFormContext()) {
        return productName ? `${productName} 사진/동영상` : `항목 ${itemIndex + 1} 사진/동영상`;
    }
    return productName ? `${productName} 실측 이미지` : `항목 ${itemIndex + 1} 실측 이미지`;
}

function erpItemAttachmentEmptyText() {
    return erpIsMobileFormContext() ? '연결된 사진/동영상이 없습니다.' : '연결된 실측 이미지가 없습니다.';
}

function erpMobileFlexibleControl(name, label, value, options = {}) {
    const escapedValue = escapeHtml(value);
    const rows = options.rows || 1;
    const minHeight = options.minHeight || (options.isMobileForm ? 40 : 28);
    const placeholder = options.placeholder || '';
    const inputClass = options.isMobileForm
        ? 'foms-textarea erp-autosize-textarea erp-flex-textarea'
        : `${options.inputClass || 'form-control form-control-sm'} erp-autosize-textarea erp-flex-textarea`;
    const placeholderAttr = placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : '';
    return `<textarea class="${inputClass}" data-erp="${name}" rows="${rows}" data-erp-min-height="${minHeight}"${placeholderAttr} lang="ko">${escapedValue}</textarea>`;
}

/** PC Master-Detail: Fiori compact 제품 속성 property sheet (목업 1:1). */
function erpDesktopPresetSheetRow(label, field, value, textareaClass) {
    const v = escapeHtml(value);
    return `<div class="erp-preset-row">
<span class="erp-preset-row__label">${label}</span>
<div class="erp-preset-row__value">
<textarea class="${textareaClass} erp-autosize-textarea erp-flex-textarea" data-erp="${field}" rows="1" data-erp-min-height="32" lang="ko">${v}</textarea>
</div>
</div>`;
}

function erpBuildDesktopPresetSheet(internal, color, optionDetail, handle, misc, textareaClass) {
    return `<div class="col-12">
<div class="erp-preset-sheet" aria-label="제품 속성">
<div class="erp-preset-sheet__head">제품 속성</div>
<div class="erp-preset-sheet__body">
${erpDesktopPresetSheetRow('내부', 'internal', internal, textareaClass)}
${erpDesktopPresetSheetRow('색상', 'color', color, textareaClass)}
${erpDesktopPresetSheetRow('옵션', 'option_detail', optionDetail, textareaClass)}
${erpDesktopPresetSheetRow('손잡이', 'handle', handle, textareaClass)}
${erpDesktopPresetSheetRow('기타·설치', 'misc', misc, textareaClass)}
</div>
</div>
</div>`;
}

function erpNewItemRow(item = {}) {
    const row = document.createElement('div');
    row.className = 'border rounded p-2 mb-2 erp-item-row';
    row.dataset.itemIndex = '-1';
    // ORDER-ITEM-UID: 서버가 발급한 품목 식별자를 행에 실어 저장 때 되돌려 보낸다.
    // 이게 없으면 서버는 위치로 추측할 수밖에 없어 중간 삽입이 "여러 품목 변경"으로 기록된다.
    if (item && item.uid) row.dataset.itemUid = String(item.uid);

    const defaultConsult = (v) => {
        const s = String(v ?? '').trim();
        return s ? s : '상담';
    };
    const isMobileForm = erpIsMobileFormContext();
    const inputClass = isMobileForm ? 'foms-input' : 'form-control form-control-sm';
    const tabularInputClass = isMobileForm ? 'foms-input foms-tabular' : 'form-control form-control-sm';
    const textareaClass = isMobileForm ? 'foms-textarea' : 'form-control form-control-sm';
    const itemScheduleFieldClass = isMobileForm ? 'col-md-6 d-none erp-mobile-rare-field' : 'col-md-6';
    const productName = String(item.product_name ?? '');
    const itemAttachmentAccept = isMobileForm ? 'image/*,video/*' : 'image/*';
    const itemAttachmentAriaLabel = isMobileForm
        ? '제품 항목 사진 및 동영상 업로드 영역. 이미지를 붙여넣으면 이 항목에 바로 업로드됩니다.'
        : '제품 항목 실측 이미지 업로드 영역. 이미지를 붙여넣으면 이 항목에 바로 업로드됩니다.';
    const itemAttachmentHint = erpItemAttachmentHintText(productName, 0).replace('항목 1', '항목');
    const itemAttachmentEmpty = erpItemAttachmentEmptyText();
    const itemAttachmentPasteHint = isMobileForm
        ? ''
        : '<div class="small text-muted mt-1">이 박스를 클릭 후 Ctrl+V로 캡처 이미지를 항목에 바로 업로드할 수 있습니다.</div>';
    // 규격 행 목록: spec_rows 우선, 없으면 단일 spec_width/spec_depth/spec_height 또는 spec 파싱
    let specRows = Array.isArray(item.spec_rows) ? item.spec_rows : [];
    if (specRows.length === 0) {
        let specWidth = String(item.spec_width || '').trim();
        let specDepth = String(item.spec_depth || '').trim();
        let specHeight = String(item.spec_height || '').trim();
        if (!specWidth && !specDepth && !specHeight && item.spec) {
            const specStr = String(item.spec || '').trim();
            const parts = specStr.split(/[xX*×]/).map(s => s.trim());
            if (parts.length >= 3) {
                specWidth = parts[0];
                specDepth = parts[1];
                specHeight = parts[2];
            } else if (parts.length === 2) {
                specWidth = parts[0];
                specDepth = parts[1];
            } else if (parts.length === 1) {
                specWidth = parts[0];
            }
        }
        specRows = [{ spec_width: specWidth, spec_depth: specDepth, spec_height: specHeight }];
    }
    // 규격 입력은 구조화 W/D/H 행이 SSOT. W(가로)는 복합 표기(총합·괄호·가산)를 그대로 받고
    // 저장 시 spec(원문)으로 파생 보존된다(출고 W/300은 백엔드 eval_spec_width_mm 기준).
    const buildSpecRowHtml = (sr, showDel) => {
        const w = escapeHtml(String((sr.spec_width ?? sr.w ?? '')).trim());
        const d = escapeHtml(String((sr.spec_depth ?? sr.d ?? '')).trim());
        const h = escapeHtml(String((sr.spec_height ?? sr.h ?? '')).trim());
        const delStyle = showDel ? '' : ' style="display:none;"';
        const wPlaceholder = isMobileForm
            ? '예: 5700(2402+…) 또는 2352+…'
            : '예: 5700(2402+1864+1638) 또는 2352+2100+2860';
        const specMinH = isMobileForm ? 40 : 28;
        const specWField = isMobileForm
            ? `<textarea class="${tabularInputClass} erp-autosize-textarea erp-flex-textarea" data-erp="spec_width" data-spec-row rows="1" data-erp-min-height="${specMinH}" placeholder="${wPlaceholder}" lang="ko">${w}</textarea>`
            : `<input class="${tabularInputClass}" data-erp="spec_width" data-spec-row placeholder="${wPlaceholder}" value="${w}" lang="ko">`;
        const specDField = isMobileForm
            ? `<textarea class="${tabularInputClass} erp-autosize-textarea erp-flex-textarea" data-erp="spec_depth" data-spec-row rows="1" data-erp-min-height="${specMinH}" placeholder="깊이" lang="ko">${d}</textarea>`
            : `<input class="${tabularInputClass}" data-erp="spec_depth" data-spec-row placeholder="깊이" value="${d}" lang="ko">`;
        const specHField = isMobileForm
            ? `<textarea class="${tabularInputClass} erp-autosize-textarea erp-flex-textarea" data-erp="spec_height" data-spec-row rows="1" data-erp-min-height="${specMinH}" placeholder="높이" lang="ko">${h}</textarea>`
            : `<input class="${tabularInputClass}" data-erp="spec_height" data-spec-row placeholder="높이" value="${h}" lang="ko">`;
        return `<div class="erp-spec-row d-flex flex-wrap gap-2 align-items-end mb-1">
<div class="col-12 erp-spec-w-col"><label class="form-label mb-0 small text-muted">W(가로·총폭)</label>${specWField}</div>
<div class="col erp-spec-d-col"><label class="form-label mb-0 small text-muted">D(깊이)</label>${specDField}</div>
<div class="col erp-spec-h-col"><label class="form-label mb-0 small text-muted">H(높이)</label>${specHField}</div>
<button type="button" class="btn btn-sm btn-outline-secondary erp-remove-spec-row-btn"${delStyle}><i class="fas fa-minus"></i></button>
</div>`;
    };
    const specRowsHtml = specRows.map((sr) => buildSpecRowHtml(sr, specRows.length > 1)).join('');
    // 복합 규격 안내(간단) — W*D*H 붙여넣기 자동 분해 + W 복합 폭은 콤마 합산.
    const specExamplesHintHtml = isMobileForm ? `
    <div class="field__hint erp-mobile-spec-hint">W*D*H 붙여넣으면 자동 분해 · 복합 폭은 콤마로 (예: 5700,4512,2300)</div>` : '';
    const internal = defaultConsult(item.internal);
    // 색상: 신규(빈 값)은 '상담' 기본. 저장된 값이 있으면 그대로 로드.
    // 이전 버그로 ' (SK)' suffix가 중복 저장된 레거시 데이터 자동 정리
    let _colorRaw = String(item.color ?? '').trim();
    _colorRaw = _colorRaw.replace(/(\s+\(SK\))+$/g, '').trim();
    const color = _colorRaw || '상담';
    const optionDetail = defaultConsult(item.option_detail);
    const handle = defaultConsult(item.handle);
    const misc = defaultConsult(item.misc);
    const priceAmount = erpCoerceAmount(item.price);
    const price = priceAmount > 0 ? erpFormatDepositDisplay(priceAmount) : '';
    const extraInput = String(item.extra_input ?? '');
    const colorFieldHtml = `
<div class="col-md-6 erp-mobile-full-row">
    <label class="form-label mb-1 small text-primary">색상</label>
    ${erpMobileFlexibleControl('color', '색상', color, { isMobileForm, inputClass, placeholder: '상담' })}
</div>`;
    const optionFieldHtml = `
<div class="col-md-6 erp-mobile-full-row">
    <label class="form-label mb-1 small text-primary">옵션</label>
    ${erpMobileFlexibleControl('option_detail', '옵션', optionDetail, { isMobileForm, inputClass, placeholder: '상담' })}
</div>`;
    const handleFieldHtml = `
<div class="col-md-6 erp-mobile-full-row">
    <label class="form-label mb-1 small text-primary">손잡이</label>
    ${erpMobileFlexibleControl('handle', '손잡이', handle, { isMobileForm, inputClass, placeholder: '상담' })}
</div>`;
    const attributeFieldsHtml = isMobileForm
        ? `${colorFieldHtml}${handleFieldHtml}${optionFieldHtml}`
        : `${colorFieldHtml}${optionFieldHtml}${handleFieldHtml}`;
    const presetFieldsHtml = isMobileForm
        ? `<div class="col-md-6 erp-mobile-full-row">
    <label class="form-label mb-1 small text-primary">내부</label>
    ${erpMobileFlexibleControl('internal', '내부', internal, { isMobileForm, inputClass, placeholder: '상담' })}
</div>
${attributeFieldsHtml}
<div class="col-md-6 erp-mobile-full-row">
    <label class="form-label mb-1 small text-primary">기타 / 설치위치</label>
    ${erpMobileFlexibleControl('misc', '기타 / 설치위치', misc, { isMobileForm, inputClass, placeholder: '상담' })}
</div>`
        : erpBuildDesktopPresetSheet(internal, color, optionDetail, handle, misc, textareaClass);
    const fieldLabelClass = isMobileForm ? 'form-label mb-1 small text-primary' : 'form-label mb-1 small erp-field-label';
    const priceFieldClass = isMobileForm ? 'col-md-6 erp-mobile-full-row' : 'col-12 erp-mobile-full-row';
    // 데스크톱: 기존 항상-펼침 헤더 유지.
    const itemHeadHtml = isMobileForm
        ? `<div class="erp-item-head">
<button type="button" class="erp-item-head-toggle" aria-expanded="false">
    <span class="erp-item-head-chevron" aria-hidden="true"><i class="fas fa-chevron-right"></i></span>
    <span class="fw-bold small erp-item-title">항목</span>
    <span class="erp-item-summary" aria-hidden="true"><span class="erp-item-summary-spec"></span><span class="erp-item-summary-amount"></span></span>
</button>
<button type="button" class="btn btn-sm btn-outline-danger erp-remove-item-btn">
    <i class="fas fa-times"></i>
</button>
</div>`
        : `<div class="d-flex justify-content-between align-items-center mb-2">
<div class="fw-bold small erp-item-title">항목</div>
<button type="button" class="btn btn-sm btn-outline-danger erp-remove-item-btn">
    <i class="fas fa-times"></i>
</button>
</div>`;
    const productMinH = isMobileForm ? 40 : 28;
    const extraInputRows = isMobileForm ? 1 : 2;
    const extraInputMinH = isMobileForm ? 40 : 72;
    const extraInputLargeClass = isMobileForm ? '' : ' erp-flex-textarea--large';
    const productNameFieldHtml = isMobileForm
        ? `<textarea class="${textareaClass} erp-autosize-textarea erp-flex-textarea" data-erp="product_name" rows="1" data-erp-min-height="${productMinH}" lang="ko">${escapeHtml(productName)}</textarea>`
        : `<input class="${inputClass}" data-erp="product_name" value="${escapeHtml(productName)}" lang="ko">`;
    const itemFieldsHtml = `
<div class="row g-2">
<div class="col-12">
    <label class="${fieldLabelClass}">제품명</label>
    ${productNameFieldHtml}
</div>
<div class="col-12">
    <label class="${fieldLabelClass}">규격 (W × D × H)</label>
    ${specExamplesHintHtml}
    <div class="erp-spec-rows">${specRowsHtml}</div>
    <button type="button" class="btn btn-sm btn-outline-primary mt-1 erp-add-spec-row-btn"><i class="fas fa-plus"></i> 규격 1행 추가</button>
</div>
${presetFieldsHtml}
<div class="${priceFieldClass}">
    <label class="form-label mb-1 small text-primary">항목 금액(원)</label>
    <input class="${tabularInputClass}" data-erp="price" inputmode="numeric" value="${escapeHtml(price)}" lang="ko">
</div>
<div class="${itemScheduleFieldClass}">
    <label class="form-label mb-1 small text-primary">항목 실측일</label>
    <input type="text" class="${tabularInputClass} erp-item-date-multiple" data-erp="measurement_date" placeholder="여러 날짜 가능" value="${escapeHtml(String(item.measurement_date || '').trim())}" lang="ko">
</div>
<div class="${itemScheduleFieldClass}">
    <label class="form-label mb-1 small text-primary">항목 시공일</label>
    <input type="text" class="${tabularInputClass} erp-item-date-multiple" data-erp="construction_date" placeholder="여러 날짜 가능" value="${escapeHtml(String(item.construction_date || '').trim())}" lang="ko">
</div>
<div class="col-12">
    <label class="form-label mb-1 small text-primary">추가 입력</label>
    <textarea class="${textareaClass} erp-autosize-textarea erp-flex-textarea${extraInputLargeClass}" data-erp="extra_input" rows="${extraInputRows}" data-erp-min-height="${extraInputMinH}"
        placeholder="추가 내용을 입력하세요 (여러 줄 가능)" lang="ko">${escapeHtml(extraInput)}</textarea>
</div>
<div class="col-12">
    <div class="border rounded p-2 bg-light" data-erp-attachment-paste-zone="item" tabindex="0"
        aria-label="${itemAttachmentAriaLabel}">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
            <div class="small fw-semibold text-muted erp-item-attachment-hint">${itemAttachmentHint}</div>
            <div class="d-flex gap-1">
                <input type="file" class="d-none erp-item-attachments-input" accept="${itemAttachmentAccept}" multiple data-foms-no-capture onchange="erpUploadItemAttachmentsPromptless(this)">
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="this.previousElementSibling.click()">
                    <i class="fas fa-image"></i> 즉시 추가
                </button>
            </div>
        </div>
        ${itemAttachmentPasteHint}
        <div class="d-flex flex-wrap gap-1 mt-2 erp-item-attachments-gallery">
            <div class="small text-muted">${itemAttachmentEmpty}</div>
        </div>
    </div>
</div>
</div>
`;
    row.innerHTML = isMobileForm
        ? `${itemHeadHtml}<div class="erp-item-collapse">${itemFieldsHtml}</div>`
        : `${itemHeadHtml}${itemFieldsHtml}`;
    erpBindAutosizeTextareas(row);

    // W(가로) 칸에 'W*D*H' 복합 규격을 붙여넣으면 곱(*,×) 기준으로 W/D/H에 자동 분해한다.
    function bindSpecWidthPasteSplit(scope) {
        if (!scope) return;
        scope.querySelectorAll('[data-erp="spec_width"]').forEach((wInput) => {
            if (wInput.dataset.erpSpecPasteBound === '1') return;
            wInput.dataset.erpSpecPasteBound = '1';
            wInput.addEventListener('paste', function (e) {
                const raw = (e.clipboardData?.getData('text/plain') || '').trim();
                if (!/[*×]/.test(raw)) return;
                const parts = raw.split(/[*×]/).map((s) => s.trim());
                if (parts.length < 2 || !parts[0]) return;
                e.preventDefault();
                const specRow = this.closest('.erp-spec-row');
                const setVal = (sel, v) => {
                    const el = specRow?.querySelector(sel);
                    if (el && v != null && v !== '') el.value = v;
                };
                setVal('[data-erp="spec_width"]', parts[0]);
                setVal('[data-erp="spec_depth"]', parts[1]);
                if (parts.length >= 3) setVal('[data-erp="spec_height"]', parts[2]);
                this.dispatchEvent(new Event('input', { bubbles: true }));
            });
        });
    }

    function updateSpecRowRemoveVisibility() {
        const container = row.querySelector('.erp-spec-rows');
        if (!container) return;
        const rows = container.querySelectorAll('.erp-spec-row');
        container.querySelectorAll('.erp-remove-spec-row-btn').forEach((btn, i) => {
            btn.style.display = rows.length > 1 ? '' : 'none';
        });
    }
    row.querySelector('.erp-add-spec-row-btn')?.addEventListener('click', () => {
        const container = row.querySelector('.erp-spec-rows');
        if (!container) return;
        const template = document.createElement('div');
        template.innerHTML = buildSpecRowHtml({}, true);
        const div = template.firstElementChild;
        if (!div) return;
        div.querySelector('.erp-remove-spec-row-btn').addEventListener('click', () => {
            div.remove();
            updateSpecRowRemoveVisibility();
        });
        bindSpecWidthPasteSplit(div);
        container.appendChild(div);
        updateSpecRowRemoveVisibility();
    });
    row.querySelectorAll('.erp-remove-spec-row-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            this.closest('.erp-spec-row')?.remove();
            updateSpecRowRemoveVisibility();
        });
    });
    bindSpecWidthPasteSplit(row);
    erpBindPriceInput(row.querySelector('[data-erp="price"]'));

    row.querySelector('[data-erp="extra_input"]')?.addEventListener('paste', (e) => {
        const raw = e.clipboardData?.getData('text/plain') || '';
        let cleaned = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        cleaned = cleaned.replace(/[\ufeff\u200b\u200c\u200d]/g, '');

        const newlineRuns = cleaned.match(/\n+/g) || [];
        const isChannelTalkPlainText =
            newlineRuns.length > 0 &&
            newlineRuns.every((run) => run.length === 2);

        if (!isChannelTalkPlainText || raw === cleaned) {
            return;
        }

        cleaned = cleaned.replace(/\n\n/g, '\n');

        e.preventDefault();
        const ta = e.currentTarget;
        const start = ta.selectionStart ?? ta.value.length;
        const end = ta.selectionEnd ?? ta.value.length;
        ta.value = ta.value.slice(0, start) + cleaned + ta.value.slice(end);
        ta.selectionStart = ta.selectionEnd = start + cleaned.length;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    });

    row.querySelector('.erp-remove-item-btn')?.addEventListener('click', async () => {
        const removedIndex = erpGetItemIndexFromRow(row);
        if (removedIndex >= 0 && typeof erpReindexItemLinkedAttachmentsAfterItemRemoval === 'function') {
            await erpReindexItemLinkedAttachmentsAfterItemRemoval(removedIndex);
        }
        row.remove();
        erpRefreshItemRowIndices();
        erpRecalcItemsTotal();
        if (window.ErpItemsMasterDetail?.afterRemove) {
            window.ErpItemsMasterDetail.afterRemove(removedIndex);
        }
        if (typeof erpRenderAttachments === 'function') {
            erpRenderAttachments();
        }
    });
    // 모바일 아코디언 헤더 토글
    row.querySelector('.erp-item-head-toggle')?.addEventListener('click', () => {
        erpToggleItemRow(row);
    });
    row.addEventListener('input', (e) => {
        erpRecalcItemsTotal();
        erpUpdateItemSummary(row);
        if (e.target && e.target.dataset && e.target.dataset.erp === 'product_name') {
            erpRefreshItemRowIndices();
            if (typeof erpRenderAttachments === 'function') {
                erpRenderAttachments();
            }
        } else if (window.ErpItemsMasterDetail?.isActive?.()) {
            window.ErpItemsMasterDetail.refresh();
        }
    });
    // Event listener removed as it's now handled by inline onchange="erpUploadItemAttachmentsPromptless(this)"

    setTimeout(() => {
        erpRefreshItemRowIndices();
        if (typeof erpRenderItemAttachmentPanels === 'function') {
            erpRenderItemAttachmentPanels();
        }
    }, 0);
    setTimeout(erpRecalcItemsTotal, 0);
    if (typeof window.erpInitFlatpickrForItemRow === 'function') {
        window.erpInitFlatpickrForItemRow(row);
    }
    // 현장 스펙 즉시견적(플래그 게이트): 드롭다운 부착·라이브 계산. off면 no-op.
    if (window.ERP_SPEC_PICKER_ENABLED && window.ErpSpecCalc) {
        try { window.ErpSpecCalc.enhanceItemRow(row, item); } catch (e) { console.warn('[erp-spec-calc] enhance 실패', e); }
    }
    return row;
}

function _erpConsumeBootstrap() {
    // 서버 렌더 시점 주입된 인라인 JSON 부트스트랩을 1회만 소비한다.
    // (동일 페이로드를 반복 적용하지 않도록 파싱 후 즉시 엘리먼트 제거)
    if (typeof document === 'undefined') return null;
    const el = document.getElementById('erp-order-bootstrap');
    if (!el) return null;
    try {
        const text = el.textContent || '';
        el.parentNode && el.parentNode.removeChild(el);
        if (!text.trim()) return null;
        const payload = JSON.parse(text);
        if (!payload || payload.success === false) return null;
        return payload;
    } catch (_e) {
        try { el.parentNode && el.parentNode.removeChild(el); } catch (_e2) { }
        return null;
    }
}

const ERP_RECEIVED_TIME_DIRECT_VALUE = '__direct__';

function erpFormatHalfHourTime(date) {
    const d = date instanceof Date ? new Date(date.getTime()) : new Date();
    let hours = d.getHours();
    const minutes = d.getMinutes();
    let roundedMinutes = 0;
    if (minutes >= 15 && minutes < 45) {
        roundedMinutes = 30;
    } else if (minutes >= 45) {
        hours = (hours + 1) % 24;
    }
    return String(hours).padStart(2, '0') + ':' + String(roundedMinutes).padStart(2, '0');
}

function erpEnsureReceivedTimeOptions() {
    const select = document.getElementById('erp-received-time-select');
    if (!select || select.dataset.erpTimeOptionsBuilt === '1') return select;
    const directOption = select.querySelector(`option[value="${ERP_RECEIVED_TIME_DIRECT_VALUE}"]`);
    if (!select.querySelector('option[value="00:00"]')) {
        for (let hour = 0; hour < 24; hour += 1) {
            for (let minute = 0; minute < 60; minute += 30) {
                const value = String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                select.insertBefore(option, directOption || null);
            }
        }
    }
    select.dataset.erpTimeOptionsBuilt = '1';
    return select;
}

function erpSetReceivedTimeControlValue(value) {
    const select = erpEnsureReceivedTimeOptions();
    const input = document.getElementById('erp-received-time');
    const normalized = String(value || '').trim();
    if (input) input.value = normalized;
    if (!select) return;

    const hasPreset = normalized
        ? Array.from(select.options || []).some(function (opt) { return opt.value === normalized; })
        : false;
    if (!normalized) {
        select.value = '';
        select.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        input?.classList.add('d-none');
        return;
    }
    if (hasPreset) {
        select.value = normalized;
        select.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        input?.classList.add('d-none');
        return;
    }
    select.value = ERP_RECEIVED_TIME_DIRECT_VALUE;
    select.closest('.erp-mobile-time-inline')?.classList.add('is-direct');
    input?.classList.remove('d-none');
}

function erpBindReceivedTimeControl() {
    const select = erpEnsureReceivedTimeOptions();
    const input = document.getElementById('erp-received-time');
    if (!select || !input || select.dataset.erpBound === '1') return;
    select.dataset.erpBound = '1';
    select.addEventListener('change', function () {
        if (this.value === ERP_RECEIVED_TIME_DIRECT_VALUE) {
            this.closest('.erp-mobile-time-inline')?.classList.add('is-direct');
            input.classList.remove('d-none');
            erpFocusWithoutScroll(input);
            return;
        }
        this.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        input.value = this.value || '';
        input.classList.add('d-none');
    });
    input.addEventListener('input', function () {
        if (!input.classList.contains('d-none')) {
            select.value = ERP_RECEIVED_TIME_DIRECT_VALUE;
        }
    });
    erpSetReceivedTimeControlValue(input.value || '');
}

function erpSetScheduleTimeControlValue(selectId, inputId, value) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    if (!select || !input) return;
    const normalized = String(value || '').trim();
    const isPreset = normalized === '오전' || normalized === '오후' || normalized === '종일';
    if (!normalized) {
        select.value = '';
        input.value = '';
        input.classList.add('d-none');
        select.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        return;
    }
    if (isPreset) {
        select.value = normalized;
        input.value = '';
        input.classList.add('d-none');
        select.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        return;
    }
    select.value = ERP_RECEIVED_TIME_DIRECT_VALUE;
    input.value = normalized;
    input.classList.remove('d-none');
    select.closest('.erp-mobile-time-inline')?.classList.add('is-direct');
    erpAutosizeTextarea(input);
}

function erpBindScheduleTimeControl(selectId, inputId) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    if (!select || !input || select.dataset.erpBound === '1') return;
    select.dataset.erpBound = '1';
    select.addEventListener('change', function () {
        if (this.value === ERP_RECEIVED_TIME_DIRECT_VALUE) {
            this.closest('.erp-mobile-time-inline')?.classList.add('is-direct');
            input.classList.remove('d-none');
            erpFocusWithoutScroll(input);
            return;
        }
        this.closest('.erp-mobile-time-inline')?.classList.remove('is-direct');
        input.value = '';
        input.classList.add('d-none');
    });
}

function erpReadScheduleTimeValue(selectId, inputId) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    if (!select) return '';
    if (select.value === ERP_RECEIVED_TIME_DIRECT_VALUE) {
        return input ? String(input.value || '').trim() : '';
    }
    return String(select.value || '').trim();
}

function erpSyncUrgentReasonVisibility(options = {}) {
    const urgent = document.getElementById('erp-urgent-flag');
    const field = document.getElementById('erp-urgent-reason-field');
    const input = document.getElementById('erp-urgent-reason');
    if (!urgent || !field || !input) return;
    if (urgent.checked) {
        field.classList.remove('d-none');
        return;
    }
    field.classList.add('d-none');
    if (options.clear !== false) input.value = '';
}

function erpBindUrgentReasonControl() {
    const urgent = document.getElementById('erp-urgent-flag');
    if (!urgent || urgent.dataset.erpUrgentBound === '1') return;
    urgent.dataset.erpUrgentBound = '1';
    urgent.addEventListener('change', function () {
        erpSyncUrgentReasonVisibility({ clear: true });
    });
    erpSyncUrgentReasonVisibility({ clear: !urgent.checked });
}

async function erpLoadStructured(bootstrapData, options) {
    if (!ERP_ORDER_ENABLED) return;
    if (!ORDER_ID) return;
    const opts = options && typeof options === 'object' ? options : {};
    const deferAttachments = opts.deferAttachments === true;

    // 주문이 변경될 때 파일 input 초기화 (이전 주문의 파일이 남아있지 않도록)
    const fileInput = document.getElementById('erp-attachments-input');
    if (fileInput) {
        fileInput.value = '';
    }

    window.__erpStructuredLoadSucceeded = false;
    let data = bootstrapData || null;
    if (!data) {
        erpSetStatus('불러오는 중...');
        const res = await fetch(`/api/orders/${ORDER_ID}/structured`);
        data = await res.json();
    }
    if (!data || !data.success) {
        erpSetStatus((data && data.message) || '불러오기 실패', true);
        return;
    }

    // DATA-01 낙관 잠금 토큰. 저장·단계 override 가 If-Match 로 되돌려 보내는 SSOT
    // (erp-stage-override.js 와 공유). 숫자가 아니면 null — 구버전 서버(필드 없음)에서는
    // If-Match 를 생략해 기존 동작을 유지한다(graceful degradation).
    window.__erpLastMutationVersion =
        typeof data.mutation_version === 'number' ? data.mutation_version : null;

    erpApplyAttachmentPermissionsFromBootstrap(data);

    const sd = data.structured_data || {};
    const receivedDateEl = document.getElementById('erp-received-date');
    const receivedTimeEl = document.getElementById('erp-received-time');
    if (receivedDateEl) receivedDateEl.value = data.received_date || '';
    if (receivedTimeEl) receivedTimeEl.value = data.received_time || '';
    erpSetReceivedTimeControlValue(data.received_time || '');
    document.getElementById('erp-customer-name').value = sd?.parties?.customer?.name || '';
    document.getElementById('erp-customer-phone').value = sd?.parties?.customer?.phone || '';
    try {
        const erpManualPhone = document.getElementById('erp-manual-phone-input');
        const erpPhoneEl = document.getElementById('erp-customer-phone');
        if ((!erpManualPhone || !erpManualPhone.checked) && erpPhoneEl && !/\n/.test(erpPhoneEl.value || '')) {
            erpPhoneEl.value = formatPhoneAuto(erpPhoneEl.value);
        }
    } catch (e) { }
    document.getElementById('erp-phone-note').value = sd?.notes?.phone_note || '';
    (function () {
        const ordererName = (sd?.parties?.orderer?.name || '').trim();
        const selectEl = document.getElementById('erp-orderer-select');
        const inputEl = document.getElementById('erp-orderer');
        const directCb = document.getElementById('erp-orderer-direct');
        if (ordererName === '라홈' || ordererName === '하우드') {
            if (selectEl) selectEl.value = ordererName;
            if (directCb) directCb.checked = false;
            if (inputEl) inputEl.value = '';
        } else {
            if (inputEl) inputEl.value = ordererName;
            if (directCb) directCb.checked = true;
        }
        toggleOrdererUI();
    })();
    document.getElementById('erp-manager').value = sd?.parties?.manager?.name || '';
    const erpConstructionWorkersEl = document.getElementById('erp-construction-workers');
    if (erpConstructionWorkersEl) {
        erpConstructionWorkersEl.value = erpFormatConstructionWorkers(sd?.shipment?.construction_workers || []);
    }
    document.getElementById('erp-workflow-stage').value = sd?.workflow?.stage || '';
    erpApplyAsStageDisplay();
    // 단계 강제 변경 가드의 base = **서버에 저장된** 단계. 아래 발주사/실측일 동기화가
    // select 를 미리 앞당겨 놓아도 override 요청은 저장값 기준으로 나가야 한다.
    if (window.FOMS_STAGE_OVERRIDE &&
            typeof window.FOMS_STAGE_OVERRIDE.noteServerStage === 'function') {
        window.FOMS_STAGE_OVERRIDE.noteServerStage(sd?.workflow?.stage || '');
    }
    const erpNotesEl = document.getElementById('erp-notes');
    if (erpNotesEl) erpNotesEl.value = data.notes || '';
    document.getElementById('erp-urgent-flag').checked = !!sd?.flags?.urgent;
    document.getElementById('erp-urgent-reason').value = sd?.flags?.urgent_reason || '';
    const factory2El = document.getElementById('erp-factory2');
    if (factory2El) factory2El.checked = !!sd?.flags?.factory2;
    erpSyncUrgentReasonVisibility({ clear: !sd?.flags?.urgent });
    const selfMeasEl = document.getElementById('erp-self-measurement');
    if (selfMeasEl) selfMeasEl.checked = !!data.is_self_measurement;
    const regionalEl = document.getElementById('erp-regional-order');
    if (regionalEl) regionalEl.checked = !!data.is_regional;
    // 지방주문 AS 재상차 모달 prefill용 flat 컬럼값 보관(structured_data에 없어 GET 응답에서 전달).
    window.__erpShippingScheduledDate = data.shipping_scheduled_date || '';
    // AS 건(cycle) 투영 — 재접수 모달의 모드·제목·지난 건 요약 정본(서버 as_cycle_view SSOT).
    // structured_data 가 아니라 payload 루트라 여기서 따로 보관한다. 부트스트랩과
    // GET /structured 가 같은 shape 라 첫 페인트와 새로고침 후 모달이 갈리지 않는다.
    window.__erpAsCycle = (data.as_cycle && typeof data.as_cycle === 'object') ? data.as_cycle : null;
    const regionalConstructionTypeEl = document.getElementById('erp-regional-construction-type');
    if (regionalConstructionTypeEl) {
        regionalConstructionTypeEl.value = data.construction_type || '';
    }
    erpSyncRegionalConstructionTypeVisibility({ clear: !data.is_regional });
    // 주소 로드: 주소+상세주소는 한 필드(erp-address)에 함께 표기
    const site = sd?.site || {};
    const addressFull = site.address_full || site.address_main || '';
    const addressDetail = site.address_detail || '';
    document.getElementById('erp-address').value = erpJoinSiteAddress(addressFull, addressDetail);
    document.getElementById('erp-address-note').value = sd?.notes?.address_note || '';
    const measurementDateVal = sd?.schedule?.measurement?.date || '';
    document.getElementById('erp-measurement-date').value = measurementDateVal;
    if (window._erpMeasurementDatePicker && measurementDateVal) {
        const dates = measurementDateVal.split(',').map(s => s.trim()).filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
        if (dates.length) window._erpMeasurementDatePicker.setDate(dates);
    }
    const measurementTime = sd?.schedule?.measurement?.time || '';
    erpSetScheduleTimeControlValue('erp-measurement-time-select', 'erp-measurement-time', measurementTime);
    document.getElementById('erp-measurement-note').value = sd?.notes?.measurement_note || '';
    const constructionDateVal = sd?.schedule?.construction?.date || '';
    document.getElementById('erp-construction-date').value = constructionDateVal;
    if (window._erpConstructionDatePicker && constructionDateVal) {
        const dates = constructionDateVal.split(',').map(s => s.trim()).filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
        if (dates.length) window._erpConstructionDatePicker.setDate(dates);
    }
    const constructionTime = sd?.schedule?.construction?.time || '';
    erpSetScheduleTimeControlValue('erp-construction-time-select', 'erp-construction-time', constructionTime);
    document.getElementById('erp-construction-note').value = sd?.notes?.construction_note || '';

    const itemsWrap = document.getElementById('erp-items');
    itemsWrap.innerHTML = '';
    const items = Array.isArray(sd.items) ? sd.items : [];
    if (items.length === 0) {
        itemsWrap.appendChild(erpNewItemRow({}));
    } else {
        items.forEach(it => itemsWrap.appendChild(erpNewItemRow(it)));
    }
    erpRefreshItemRowIndices();
    erpOpenFirstItemRow();

    erpSetStatus(`불러오기 완료 (confidence: ${data.structured_confidence || sd.confidence || '-'})`);
    const paymentData = _erpNormalizePaymentData(sd);
    sd.payment = paymentData;
    window.__erpLastStructuredData = sd;
    window.__erpStructuredLoadSucceeded = true;
    // 구조화 데이터가 도착했다는 신호. 이 데이터만 읽고 그리는 화면 조각(알림톡 발송 흔적
    // 칩 등)이 로드 순서에 상관없이 다시 그릴 수 있게 한다.
    document.dispatchEvent(new CustomEvent('foms:erp-structured-loaded'));
    erpRecalcItemsTotal();
    const depositEl = document.getElementById('erp-deposit-amount');
    if (depositEl) {
        depositEl.value = erpFormatDepositDisplay(paymentData.deposit);
    }
    const discountEl = document.getElementById('erp-discount-amount');
    if (discountEl) {
        discountEl.value = erpFormatDepositDisplay(paymentData.discount);
    }
    const freeInputParts = erpSplitFreeInputForForm(paymentData.free_input);
    const freeInputTextEl = document.getElementById('erp-free-input-text');
    if (freeInputTextEl) {
        freeInputTextEl.value = freeInputParts.text;
    }
    const freeInputEl = document.getElementById('erp-free-input-amount');
    if (freeInputEl) {
        freeInputEl.value = freeInputParts.amount > 0
            ? erpFormatDepositDisplay(freeInputParts.amount)
            : '';
    }
    const cashReceiptEl = document.getElementById('erp-cash-receipt');
    if (cashReceiptEl) {
        cashReceiptEl.value = paymentData.cash_receipt || '';
    }
    const balanceNoteEl = document.getElementById('erp-balance-note');
    if (balanceNoteEl) {
        balanceNoteEl.value = paymentData.balance_note || '';
        erpSetBalanceNoteSectionOpen(!!paymentData.balance_note, { clearValue: false });
    }
    erpRecalcItemsTotal();
    _erpUpdatePaymentConfirmUI('deposit', paymentData);
    _erpUpdatePaymentConfirmUI('balance', paymentData);

    // 첨부는 편집 본문(first paint)과 별개의 부가 패널이다.
    // 초기 active ERP 탭에서는 구조화 필드만 먼저 채운 뒤 surface를 공개하고,
    // 첨부/Quest는 후속 비동기로 붙여 흰 화면 체류 시간을 줄인다.
    if (!deferAttachments && typeof erpLoadAttachments === 'function') {
        await erpLoadAttachments();
    }
    if (typeof erpRenderItemAttachmentPanels === 'function') {
        erpRenderItemAttachmentPanels();
    }
    erpBindAutosizeTextareas(document.getElementById('erp-order') || document);
    // as_cycle 이 채워진 뒤라야 재접수 모달이 옳은 모드로 열린다 — 로드 끝에서 1회 소비.
    erpMaybeOpenAsReintakeFromUrl();
}

function erpCollectStructured() {
    const itemsWrap = document.getElementById('erp-items');
    const items = [];
    let itemsTotal = 0;
    itemsWrap.querySelectorAll('.erp-item-row').forEach(row => {
        const obj = {};
        // ORDER-ITEM-UID: 렌더 때 실어둔 식별자를 그대로 돌려보낸다(서버가 이 값의 진위를
        // 검증한다 — 이 주문에 없던 uid 는 서버가 버리고 새로 발급한다).
        if (row.dataset.itemUid) obj.uid = row.dataset.itemUid;
        row.querySelectorAll('[data-erp]').forEach(inp => {
            if (inp.closest('.erp-spec-row')) return;
            obj[inp.dataset.erp] = inp.value;
        });
        // 규격 다중 행 수집
        const specRows = [];
        row.querySelectorAll('.erp-spec-row').forEach(sr => {
            const w = String(sr.querySelector('[data-erp="spec_width"]')?.value ?? '').trim();
            const d = String(sr.querySelector('[data-erp="spec_depth"]')?.value ?? '').trim();
            const h = String(sr.querySelector('[data-erp="spec_height"]')?.value ?? '').trim();
            if (w || d || h) {
                specRows.push({ spec_width: w, spec_depth: d, spec_height: h });
            }
        });
        const rawSpecEl = row.querySelector('[data-erp="spec"]');
        const rawSpec = String(obj.spec || '').trim();
        const rawSpecWasDerived = rawSpecEl?.dataset?.erpSpecDerived === '1';
        if (specRows.length > 0) {
            obj.spec_rows = specRows;
            const first = specRows[0];
            obj.spec_width = first.spec_width;
            obj.spec_depth = first.spec_depth;
            obj.spec_height = first.spec_height;
            const specLines = specRows.map(function (sr) {
                return [sr.spec_width, sr.spec_depth, sr.spec_height].filter(Boolean).join('x');
            }).filter(Boolean);
            obj.spec = rawSpec && !rawSpecWasDerived ? rawSpec : (specLines.join(', ') || rawSpec);
        } else {
            obj.spec_rows = [];
            obj.spec_width = '';
            obj.spec_depth = '';
            obj.spec_height = '';
            obj.spec = rawSpec;
        }
        if (obj.price) {
            const digits = String(obj.price).replace(/[^0-9]/g, '');
            obj.price = digits ? parseInt(digits, 10) : obj.price;
            if (typeof obj.price === 'number' && Number.isFinite(obj.price)) {
                itemsTotal += obj.price;
            }
        }
        // 현장 스펙 즉시견적(플래그 게이트): 계산 활성 항목의 pricing 스냅샷 첨부. off면 no-op.
        if (window.ERP_SPEC_PICKER_ENABLED && window.ErpSpecCalc) {
            try { window.ErpSpecCalc.collectPricing(row, obj); } catch (e) { console.warn('[erp-spec-calc] collect 실패', e); }
        }
        items.push(obj);
    });

    // 안전하게 값 가져오는 헬퍼 함수
    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? (el.value || '') : '';
    };

    const getCheck = (id) => {
        const el = document.getElementById(id);
        return el ? !!el.checked : false;
    };
    const depositAmount = erpCoerceAmount(getVal('erp-deposit-amount'));
    const discountAmount = erpCoerceAmount(getVal('erp-discount-amount'));
    const freeInputAmount = erpParseFreeInputAmount();
    const totals = erpBuildTotals(itemsTotal, depositAmount, discountAmount, freeInputAmount);

    // PUT /structured 는 본문 전체로 JSONB를 교체함. 폼에 없는 최상위 키는 서버 스냅샷에서 유지 (AS as_content 등)
    const prevSd = (window.__erpLastStructuredData && typeof window.__erpLastStructuredData === 'object')
        ? window.__erpLastStructuredData
        : {};
    const preservedTopLevelKeys = [
        'shipment',
        'assignments',
        'quests',
        'meta',
        'drawing',
        'blueprint',
        'drawing_status',
        'drawing_transferred',
        'drawing_confirmed_at',
        'drawing_confirmed_by',
        'drawing_current_files',
        'drawing_transfer_history',
        'last_drawing_transfer',
        'drawing_assignees',
        'estimate_preview',
        'channeltalk_push',
        'channeltalk_push_drawing',
        'channeltalk_push_estimate',
        'channeltalk_push_as',
        'channeltalk_push_measure_room',
    ];

    // DATA-01: provenance(schema_version/confidence)는 서버 소유다. 폼은 전송하지 않는다
    // (서버가 old-wins 로 보존). totals 도 서버가 재계산하지만, 편집 폼 표시용으로만 담는다.
    const structured = {
        entity_type: 'order_structured',
        totals,
        parties: {
            customer: {
                name: getVal('erp-customer-name'),
                phone: getVal('erp-customer-phone')
            },
            orderer: { name: typeof getOrdererValue === 'function' ? getOrdererValue() : getVal('erp-orderer') },
            manager: { name: getVal('erp-manager') }
        },
        site: (function () {
            const full = getVal('erp-address').trim();
            return { address_main: full, address_detail: '', address_full: full };
        })(),
        schedule: {
            measurement: (function () {
                const timeSelect = document.getElementById('erp-measurement-time-select');
                const timeInput = document.getElementById('erp-measurement-time');
                let timeValue = '';
                if (timeSelect) {
                    if (timeSelect.value === '__direct__') {
                        timeValue = timeInput ? timeInput.value : '';
                    } else {
                        timeValue = timeSelect ? timeSelect.value : '';
                    }
                }
                return { date: getVal('erp-measurement-date'), time: timeValue };
            })(),
            construction: (function () {
                const timeSelect = document.getElementById('erp-construction-time-select');
                const timeInput = document.getElementById('erp-construction-time');
                let timeValue = '';
                if (timeSelect) {
                    if (timeSelect.value === '__direct__') {
                        timeValue = timeInput ? timeInput.value : '';
                    } else {
                        timeValue = timeSelect.value;
                    }
                }
                return { raw: '', date: getVal('erp-construction-date'), time: timeValue };
            })()
        },
        notes: {
            phone_note: getVal('erp-phone-note'),
            address_note: getVal('erp-address-note'),
            measurement_note: getVal('erp-measurement-note'),
            construction_note: getVal('erp-construction-note')
        },
        workflow: (function () {
            const prevWorkflow = (prevSd.workflow && typeof prevSd.workflow === 'object' && !Array.isArray(prevSd.workflow))
                ? prevSd.workflow
                : {};
            let workflow = {};
            try {
                workflow = JSON.parse(JSON.stringify(prevWorkflow));
            } catch (e) {
                workflow = Object.assign({}, prevWorkflow);
            }
            // 폼 hidden stage 가 서버보다 뒤처진 값이면 역행(도면→실측) 사고. 앞선 단계 유지.
            var formStage = getVal('erp-workflow-stage');
            var prevStage = String(prevWorkflow.stage || '').trim();
            var rank = {
                RECEIVED: 0, '주문접수': 0,
                MEASURE: 1, '실측': 1,
                DRAWING: 2, '도면': 2,
                CONFIRM: 3, '고객컨펌': 3,
                PRODUCTION: 4, '생산': 4,
                CONSTRUCTION: 5, '시공': 5,
                CS: 6, COMPLETED: 7, '완료': 7
            };
            var formRank = Object.prototype.hasOwnProperty.call(rank, formStage) ? rank[formStage] : -1;
            var prevRank = Object.prototype.hasOwnProperty.call(rank, prevStage) ? rank[prevStage] : -1;
            // 알려진 단계끼리: 인접 전진(+1)만 허용. 역행·스킵은 서버 단계 유지(override API).
            if (formRank >= 0 && prevRank >= 0) {
                if (formRank === prevRank + 1 || formStage === prevStage) {
                    workflow.stage = formStage || prevStage;
                } else {
                    workflow.stage = prevStage;
                }
            } else {
                workflow.stage = formStage || prevStage;
            }
            return workflow;
        })(),
        flags: {
            urgent: getCheck('erp-urgent-flag'),
            urgent_reason: getVal('erp-urgent-reason'),
            factory2: getCheck('erp-factory2')
        },
        payment: (function () {
            const prev = window.__erpLastStructuredData ? _erpNormalizePaymentData(window.__erpLastStructuredData) : _erpNormalizePaymentData({});
            return {
                deposit: totals.deposit_amount,
                discount: totals.discount_amount,
                free_input: erpBuildFreeInputStoredValue(),
                cash_receipt: String(getVal('erp-cash-receipt') || ''),
                balance_note: String(getVal('erp-balance-note') || '').trim(),
                deposit_confirmed: _erpBoolConfirmed(prev.deposit_confirmed),
                deposit_confirmed_at: prev.deposit_confirmed_at || null,
                deposit_confirmed_by: prev.deposit_confirmed_by || null,
                deposit_confirmed_by_user_id: prev.deposit_confirmed_by_user_id || null,
                balance_confirmed: _erpBoolConfirmed(prev.balance_confirmed),
                balance_confirmed_at: prev.balance_confirmed_at || null,
                balance_confirmed_by: prev.balance_confirmed_by || null,
                balance_confirmed_by_user_id: prev.balance_confirmed_by_user_id || null
            };
        })(),
        items
    };

    preservedTopLevelKeys.forEach(function (key) {
        if (!Object.prototype.hasOwnProperty.call(prevSd, key) || prevSd[key] == null) {
            return;
        }
        try {
            structured[key] = JSON.parse(JSON.stringify(prevSd[key]));
        } catch (e) {
            structured[key] = prevSd[key];
        }
    });

    const constructionWorkersEl = document.getElementById('erp-construction-workers');
    if (constructionWorkersEl) {
        if (!structured.shipment || typeof structured.shipment !== 'object' || Array.isArray(structured.shipment)) {
            structured.shipment = {};
        }
        structured.shipment.construction_workers = erpNormalizeConstructionWorkers(
            constructionWorkersEl.value
        );
    }

    return structured;
}

/**
 * ERP Order 구조화 데이터 저장.
 * @param {Object} opts - 옵션
 * @param {boolean} [opts.redirect=true] - 저장 성공 후 리다이렉트 여부
 * @returns {Promise<{success: boolean, message?: string}>}
 */
async function erpSaveStructured(opts = {}) {
    if (opts && typeof opts.preventDefault === 'function') {
        opts.preventDefault();
        if (typeof opts.stopPropagation === 'function') opts.stopPropagation();
        opts = {};
    }
    if (!ERP_ORDER_ENABLED) return { success: false, message: 'ERP Order 비활성' };
    if (_erpSaveStructuredInFlight) {
        erpSetStatus('저장 중...');
        return _erpSaveStructuredInFlight;
    }

    erpSetStatus('저장 중...');
    erpSetSaveButtonBusy(true);
    _erpSaveStructuredInFlight = erpSaveStructuredOnce(opts);
    try {
        return await _erpSaveStructuredInFlight;
    } finally {
        _erpSaveStructuredInFlight = null;
        erpSetSaveButtonBusy(false);
    }
}

let _erpSaveStructuredInFlight = null;

function erpSetSaveButtonBusy(isBusy) {
    const btn = document.getElementById('erp-save-btn');
    if (!btn) return;

    if (isBusy) {
        if (!btn.dataset.erpOriginalHtml) {
            btn.dataset.erpOriginalHtml = btn.innerHTML;
        }
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>저장 중...';
        return;
    }

    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    if (btn.dataset.erpOriginalHtml) {
        btn.innerHTML = btn.dataset.erpOriginalHtml;
        delete btn.dataset.erpOriginalHtml;
    }
}

function erpFocusWithoutScroll(el) {
    if (!el || typeof el.focus !== 'function') return;
    try {
        el.focus({ preventScroll: true });
    } catch (e) {
        el.focus();
    }
}

function erpAppendFocusOrderParam(targetUrl, orderId) {
    // 저장 복귀를 방금 저장한 행으로 정렬(focus_order 딥링크 재사용: 스크롤+하이라이트).
    // 대시보드 복귀가 그리드(erp-grid-scroll-wrap) 스크롤을 0으로 되돌려
    // "저장 누르면 스크롤 업" 으로 보이던 문제의 근본 수정 — px 위치 복원 대신
    // 행 기준 복귀라 저장 후 재정렬·필터 상태에도 안전하다.
    if (!orderId || orderId <= 0) return targetUrl;
    try {
        const u = new URL(targetUrl, window.location.origin);
        if (u.origin !== window.location.origin) return targetUrl;
        // focus_order 소비자가 배선된 복귀처만 부여(주문·실측 대시보드).
        if (u.pathname !== '/erp/dashboard' && u.pathname !== '/erp/measurement') return targetUrl;
        u.searchParams.set('focus_order', String(orderId));
        return u.pathname + u.search + u.hash;
    } catch (e) {
        return targetUrl;
    }
}

function erpNavigateAfterStructuredSave(targetUrl) {
    if (!targetUrl) {
        window.location.href = '/erp/dashboard';
        return;
    }

    let target;
    try {
        target = new URL(targetUrl, window.location.origin);
    } catch (e) {
        window.location.href = targetUrl;
        return;
    }

    try {
        const ref = document.referrer ? new URL(document.referrer) : null;
        if (
            ref &&
            ref.origin === window.location.origin &&
            target.origin === window.location.origin &&
            ref.pathname === target.pathname &&
            ref.search === target.search &&
            ref.hash === target.hash &&
            target.pathname !== window.location.pathname &&
            window.history &&
            window.history.length > 1
        ) {
            try {
                sessionStorage.setItem('foms:reload-order-list-after-erp-save', target.href);
            } catch (e) {
                // sessionStorage may be unavailable in hardened browser modes.
            }
            window.history.back();
            return;
        }
    } catch (e) {
        // Fall through to normal navigation when referrer parsing is unavailable.
    }

    window.location.href = target.href;
}

/**
 * AS 접수 모달이 열릴 세 모드 중 하나를 고른다.
 *
 * 판정은 서버 payload(``as_cycle.cycle_status``)로만 한다. 화면이 ``order.status`` 같은
 * 상태 문자열을 따로 해석하면 서버 분기(as_orders.py:565-573 — 열린 건이면 기록 갱신,
 * 아니면 새 건 발급)와 어긋나 "새 건인 줄 알았는데 갱신됐다"가 난다.
 *
 * @param {{reregister: boolean}} options - 호출자가 준 힌트(payload 가 건을 못 찾을 때만 쓰인다).
 * @returns {{mode: string, cycleNo: number, lastClosed: (Object|null)}}
 *   mode 는 'new'(최초 접수) · 'edit'(열린 건 접수 수정) · 'reintake'(완료 뒤 새 건),
 *   cycleNo 는 이번 모달이 다루는 건의 순번, lastClosed 는 지난 종결 건 요약.
 */
function erpResolveAsReceiveMode(options = {}) {
    const cycle = window.__erpAsCycle || null;
    const status = String((cycle && cycle.cycle_status) || 'NONE');
    const lastClosed = (cycle && cycle.last_closed_cycle && typeof cycle.last_closed_cycle === 'object')
        ? cycle.last_closed_cycle
        : null;
    if (status === 'RECEIVED' || status === 'IN_PROGRESS') {
        return { mode: 'edit', cycleNo: Number((cycle && cycle.cycle_no) || 0), lastClosed: lastClosed };
    }
    if (status === 'COMPLETED' || lastClosed) {
        return { mode: 'reintake', cycleNo: Number((lastClosed && lastClosed.ordinal) || 0) + 1, lastClosed: lastClosed };
    }
    // as_lifecycle 이 없는 레거시 AS 주문: payload 로는 못 가른다 — 버튼이 준 힌트로 간다.
    return options.reregister === true
        ? { mode: 'edit', cycleNo: 0, lastClosed: null }
        : { mode: 'new', cycleNo: 1, lastClosed: null };
}

/**
 * 이번 접수에서 비용 판정을 다시 시드할 수 있는가(= 세그먼트를 열어도 되는가).
 *
 * 서버는 ``reseed_billing = new_cycle and _prior_cycle_billing_sealed(sd)`` 로만 재시드한다
 * (as_orders.py). 봉인이 없는 레거시 주문에서 화면만 열면 사용자가 고른 값이 조용히 버려져
 * "골랐는데 저장 안 됨"이 된다 — 그래서 봉인 여부(billing_text)까지 같이 본다.
 *
 * @returns {boolean} 세그먼트를 열어도 되면 true.
 */
function erpAsReceiveCanReseedBilling() {
    if (window.__erpAsReceiveMode !== 'reintake') return false;
    const lastClosed = window.__erpAsCycle && window.__erpAsCycle.last_closed_cycle;
    return !!(lastClosed && lastClosed.billing_text);
}

/**
 * 접수 모달 안의 조건부 블록 하나를 켜고 끈다.
 *
 * @param {string} id - 대상 엘리먼트 id.
 * @param {boolean} show - 보일지 여부.
 * @returns {void}
 */
function erpToggleAsReceiveBlock(id, show) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('d-none', !show);
}

/**
 * '지난 AS 요약' 접힘 블록을 채운다 — 값이 없는 줄은 통째로 숨긴다(추정 금지).
 *
 * 완료일·비용은 cycle 봉인분(B2/B3)이 있는 건만 진짜 값이다. 없는 걸 '-' 로 채우면
 * 화면이 "기록이 있는데 비었다"고 거짓말한다.
 *
 * 증상·처리(목업 4-C)도 같은 규약이다 — 증상은 그 건 접수 원문 발췌(``symptom_text``),
 * 처리는 그 건 as_log 의 최대 회차(``max_round``)다. 건 표식이 없던 옛 기록에는 회차
 * 스탬프가 없어 0 으로 오므로 그 줄은 안 낸다.
 *
 * @param {Object|null} summary - as_cycle_view.cycle_summary shape 또는 null.
 * @returns {void}
 */
function erpRenderAsReceivePrevCycle(summary) {
    const wrap = document.getElementById('as-receive-prev-wrap');
    if (!wrap) return;
    wrap.open = false;
    if (!summary) { wrap.classList.add('d-none'); return; }
    const unknown = summary.history_unknown === true;
    const ordinal = Number(summary.ordinal || 0);
    const maxRound = Number(summary.max_round || 0);
    const rows = {
        ordinal: unknown ? '이력 시작 전' : (ordinal > 0 ? `${ordinal}번째 AS` : ''),
        received: unknown ? '접수일 불명' : String(summary.received_date || ''),
        completed: String(summary.completed_date || ''),
        symptom: String(summary.symptom_text || ''),
        billing: String(summary.billing_text || ''),
        rounds: maxRound > 0
            ? `${maxRound}차까지 갔어요${maxRound > 1 ? ` — "이번엔 못 끝냈다" 판정이 ${maxRound - 1}번 있었다는 뜻` : ''}`
            : '',
    };
    Object.keys(rows).forEach(function (key) {
        const row = wrap.querySelector(`[data-prev-row="${key}"]`);
        const valEl = wrap.querySelector(`[data-prev-val="${key}"]`);
        if (valEl) valEl.textContent = rows[key];
        if (row) row.classList.toggle('d-none', !rows[key]);
    });
    const label = document.getElementById('as-receive-prev-summary');
    if (label) {
        label.textContent = (unknown || ordinal <= 0)
            ? '지난 AS 요약 보기'
            : `지난 AS 요약 보기 (${ordinal}번째 AS)`;
    }
    wrap.classList.remove('d-none');
}

/**
 * 모드에 맞춰 접수 모달의 조건부 UI 를 전부 다시 그린다(오픈마다 재평가).
 *
 * @param {string} mode - 'new' | 'edit' | 'reintake'.
 * @param {Object|null} lastClosed - 지난 종결 건 요약(as_cycle.last_closed_cycle).
 * @returns {void}
 */
function erpApplyAsReceiveMode(mode, lastClosed) {
    const isReintake = mode === 'reintake';
    erpToggleAsReceiveBlock('as-receive-same-cycle-note', mode === 'edit');
    erpToggleAsReceiveBlock('as-receive-hard-warn', isReintake);
    erpToggleAsReceiveBlock('as-receive-prefill-tools', isReintake);
    erpToggleAsReceiveBlock('as-receive-recurrence-wrap', isReintake && !!lastClosed);
    erpToggleAsReceiveBlock('as-receive-clear-content', false);
    erpToggleAsReceiveBlock('as-receive-load-hint', false);
    const recurEl = document.getElementById('as-receive-recurrence');
    if (recurEl) recurEl.checked = false;
    erpRenderAsReceivePrevCycle(isReintake ? lastClosed : null);
    if (!isReintake) return;
    // 새 건은 지난 건 판정·금액을 물려받지 않는다 — 기본값(무상 추정)에서 다시 고른다.
    document.querySelectorAll('input[name="as-receive-billing"]').forEach(function (r) {
        r.checked = (r.value === 'free');
    });
    const amountEl = document.getElementById('as-receive-amount');
    if (amountEl) amountEl.value = '';
}

/**
 * URL 의 ``as_reintake=1`` 딥링크를 1회 소비해 AS 재접수 모달을 자동으로 연다.
 *
 * AS 대시보드 완료 탭의 '재접수' 버튼이 이 링크로 들어온다. 모드는 URL 이 아니라
 * ``as_cycle`` payload 가 정한다 — 링크를 눌러 오는 사이 다른 사람이 그 건을 다시 열었다면
 * 화면이 "새 건"이라고 거짓말하면 안 된다. 파라미터는 연 직후 지워 새로고침 재오픈을 막는다.
 *
 * @returns {boolean} 모달을 열었으면 true.
 */
function erpMaybeOpenAsReintakeFromUrl() {
    let params;
    try {
        params = new URLSearchParams(window.location.search || '');
    } catch (e) {
        return false;
    }
    if (params.get('as_reintake') !== '1') return false;
    params.delete('as_reintake');
    const qs = params.toString();
    try {
        window.history.replaceState(
            null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash || ''}`);
    } catch (e) {
        // history 접근이 막힌 브라우저 모드에서도 모달 자체는 열어야 한다.
    }
    const previousStage = (window.__erpLastStructuredData?.workflow?.stage || '').trim();
    return erpOpenAsReceiveModal(erpResolveCurrentOrderId(), previousStage);
}

/**
 * Open the shared AS reception modal without mutating the main workflow stage.
 * Active AS corrections reuse the same endpoint, which preserves the cycle and history.
 */
function erpOpenAsReceiveModal(targetId, previousStage, options = {}) {
    const modalEl = document.getElementById('asReceiveModal');
    if (!modalEl || !targetId || targetId <= 0) return false;

    window.__erpAsReceivePreviousStage = (previousStage || '').trim();
    window.__erpAsReceiveTargetId = targetId;
    window.__erpAsReceiveSubmitted = false;

    const contentEl = document.getElementById('as-receive-content');
    const filesEl = document.getElementById('as-receive-files');
    const previewEl = document.getElementById('as-receive-preview');
    const titleEl = document.getElementById('asReceiveModalLabel');
    const submitBtn = document.getElementById('as-receive-submit-btn');
    const isReregister = options.reregister === true;
    // 모드 정본은 서버 payload 다(erpResolveAsReceiveMode). isReregister 는 payload 가
    // 건을 못 찾는 레거시 주문에서만 갈림길이 된다.
    const modeInfo = erpResolveAsReceiveMode({ reregister: isReregister });
    const mode = modeInfo.mode;
    const isReintake = mode === 'reintake';
    const isEdit = mode === 'edit';
    window.__erpAsReceiveMode = mode;

    if (contentEl) {
        // D4: 새 건은 지난 증상을 절대 미리 채우지 않는다 — 채워 두면 그게 이번 건의
        // 접수 원문으로 굳어 "저번 증상으로 새 AS 가 열린" 기록이 남는다.
        if (contentEl.dataset.defaultPlaceholder === undefined) {
            contentEl.dataset.defaultPlaceholder = contentEl.placeholder || '';
        }
        contentEl.value = isReintake
            ? ''
            : (window.__erpLastStructuredData?.shipment?.as_content || '').trim();
        contentEl.placeholder = isReintake
            ? '이번에 생긴 문제를 적어주세요'
            : contentEl.dataset.defaultPlaceholder;
    }
    if (filesEl) filesEl.value = '';
    window.__erpAsReceiveClipboardFiles = [];
    if (previewEl && previewEl._asOrder) previewEl._asOrder.clear();
    else if (previewEl) previewEl.innerHTML = '';
    if (titleEl) {
        // 건 배지는 2번째부터만 붙인다(1번째 AS 는 소음 — as_cycle_view 표시 규약).
        const badge = modeInfo.cycleNo >= 2
            ? ` <span class="foms-as-cycle-badge">${modeInfo.cycleNo}번째 AS</span>`
            : '';
        titleEl.innerHTML = isReintake
            ? `<i class="fas fa-redo text-primary"></i> ${modeInfo.cycleNo}번째 AS 접수${badge}`
            : '<i class="fas fa-exclamation-circle text-warning"></i> '
                + (isEdit ? `AS 접수 수정${badge}` : 'AS 접수');
    }
    if (submitBtn) {
        submitBtn.innerHTML = isReintake
            ? `<i class="fas fa-redo"></i> ${modeInfo.cycleNo}번째 AS 접수하기`
            : '<i class="fas fa-check"></i> '
                + (isEdit ? '수정 내용 저장' : 'AS 접수 확인');
    }
    erpApplyAsReceiveMode(mode, modeInfo.lastClosed);

    const shipWrapEl = document.getElementById('as-receive-shipping-wrap');
    const shipDateEl = document.getElementById('as-receive-shipping-date');
    const isRegionalNow = document.getElementById('erp-regional-order')?.checked === true;
    if (shipWrapEl) shipWrapEl.classList.toggle('d-none', !isRegionalNow);
    if (shipDateEl) {
        shipDateEl.value = isRegionalNow ? (window.__erpShippingScheduledDate || '') : '';
    }

    bootstrap.Modal.getOrCreateInstance(modalEl).show();
    return true;
}

async function erpSaveStructuredOnce(opts = {}) {
    const doRedirect = opts.redirect !== false;
    const redirectUrlOverride = typeof opts.redirectUrl === 'string' ? opts.redirectUrl.trim() : '';

    // 필수 입력값 검증 (사용자 직접 저장 시에만 적용, 자동 저장 예외)
    if (opts._skipValidation !== true) {
        const missing = [];
        const nameVal = (document.getElementById('erp-customer-name')?.value || '').trim();
        const phoneVal = (document.getElementById('erp-customer-phone')?.value || '').trim();
        const addrVal = (document.getElementById('erp-address')?.value || '').trim();
        // 지방주문 체크 시 구분(하우드/협력사)은 서버가 400으로 강제하는 필수값 —
        // 여기서 안 잡으면 alert 없이 저장만 조용히 막힌다.
        const regionalChecked = document.getElementById('erp-regional-order')?.checked === true;
        const regionalTypeMissing = regionalChecked && !erpGetRegionalConstructionType();

        if (regionalTypeMissing) missing.push('지방주문 구분 (하우드/협력사)');
        if (!nameVal) missing.push('고객명');
        if (!phoneVal) missing.push('전화번호');
        if (!addrVal) missing.push('주소');

        // 제품 항목 중 품명이 1개 이상 있는지 확인
        const itemRows = document.querySelectorAll('#erp-items .erp-item-row');
        const hasProductName = Array.from(itemRows).some(row => {
            const nameInput = row.querySelector('[data-erp="product_name"]');
            return nameInput && nameInput.value.trim() !== '';
        });
        if (!hasProductName) missing.push('제품명 (최소 1개)');

        if (missing.length > 0) {
            // 래퍼가 먼저 찍은 '저장 중...'이 남지 않게 실패 사유로 교체
            erpSetStatus(`필수 항목 미입력: ${missing.join(', ')}`, true);
            alert(`다음 필수 항목을 입력해주세요:\n\n• ${missing.join('\n• ')}`);
            // 첫 번째 누락 필드에 포커스 (폼 상단 순서)
            if (regionalTypeMissing) erpFocusWithoutScroll(document.getElementById('erp-regional-construction-type'));
            else if (!nameVal) erpFocusWithoutScroll(document.getElementById('erp-customer-name'));
            else if (!phoneVal) erpFocusWithoutScroll(document.getElementById('erp-customer-phone'));
            else if (!addrVal) erpFocusWithoutScroll(document.getElementById('erp-address'));
            else {
                const firstItem = document.querySelector('#erp-items .erp-item-row [data-erp="product_name"]');
                erpFocusWithoutScroll(firstItem);
            }
            return { success: false, message: '필수 항목 미입력' };
        }
    }

    if (_paymentTogglePending) {
        await new Promise(resolve => {
            const deadline = Date.now() + 3000; // 최대 3초 대기
            const iv = setInterval(() => {
                if (!_paymentTogglePending || Date.now() >= deadline) {
                    clearInterval(iv);
                    resolve();
                }
            }, 50);
        });
    }

    // ORDER_ID 안전하게 확보
    let targetId = erpResolveCurrentOrderId();

    // 신규 주문(draft) 모드: ID가 0이면 반드시 draft 생성
    if (isErpOrderDraftMode() && targetId <= 0) {
        const id = await erpRequireOrderIdOrWarn('저장:');
        if (!id) return { success: false, message: '주문번호 생성 실패' };
        targetId = parseInt(String(id), 10) || 0;
    }

    if (targetId <= 0) {
        erpSetStatus('주문 ID를 찾을 수 없습니다.', true);
        return { success: false, message: '주문 ID를 찾을 수 없습니다.' };
    }

    if (!erpConfirmConstructionWorkerOverwrite()) {
        return { success: false, message: '시공 담당자 변경이 취소되었습니다.' };
    }

    erpSetStatus('저장 중...');
    // 저장 시작을 자동저장 모듈에 먼저 알린다. 저장(PUT)이 승격한 draft 를 뒤늦은
    // 자동저장(디바운스 타이머·beforeunload beacon)이 다시 draft 로 되돌려 주문이
    // 대시보드에서 사라지는 사고를 막는다(서버 행 잠금과 2중 방어).
    try { document.dispatchEvent(new Event('erp:order-saving')); } catch (_e) {}

    try {
        const structured_data = erpCollectStructured();
        const isRegionalOrder = document.getElementById('erp-regional-order')?.checked === true;
        const regionalConstructionType = isRegionalOrder ? erpGetRegionalConstructionType() : '';
        // _skipValidation(자동 저장) 경로 방어선 — 서버 400 왕복 전 차단.
        // 사용자 저장은 위 필수값 검증(alert)이 먼저 잡는다. 맨 .focus()는
        // 뷰포트를 폼 상단으로 튕겨 "저장 누르면 스크롤만 올라간다" 증상을 만들었다.
        if (isRegionalOrder && !regionalConstructionType) {
            erpSetStatus('지방주문 구분(하우드/협력사)을 선택해주세요.', true);
            erpFocusWithoutScroll(document.getElementById('erp-regional-construction-type'));
            return { success: false, message: '지방주문 구분을 선택해주세요.' };
        }

        // AS접수: 다른 단계 → AS접수로 "전환"한 직후에만 모달·저장 중단. 이미 서버에 AS접수면 일반 PUT 허용.
        const nextStage = (structured_data?.workflow?.stage || '').trim();
        const prevStage = (window.__erpLastStructuredData?.workflow?.stage || '').trim();
        const transitioningIntoAsReceived =
            nextStage === 'AS_RECEIVED' && prevStage !== 'AS_RECEIVED';
        if (transitioningIntoAsReceived) {
            const needServerSnapshot =
                !isErpOrderDraftMode() && targetId > 0;
            if (needServerSnapshot && !window.__erpStructuredLoadSucceeded) {
                erpSetStatus('먼저 주문 정보를 불러온 뒤 저장해주세요.', true);
                return { success: false, message: '주문 정보를 불러온 뒤 다시 시도해주세요.' };
            }
            // redirect: false(채널톡 자동 저장 등)에서도 모달을 띄워 저장 실패만 나오는 상황 방지
            erpOpenAsReceiveModal(targetId, prevStage);
            erpSetStatus('AS 접수 내용을 입력해주세요.');
            return { success: false, message: 'AS 접수 단계로 변경 시 내용 입력 후 접수를 완료해주세요.' };
        }

        const receivedDateEl = document.getElementById('erp-received-date');
        const receivedTimeEl = document.getElementById('erp-received-time');
        const received_date = receivedDateEl ? (receivedDateEl.value || '').trim() : '';
        const received_time = receivedTimeEl ? (receivedTimeEl.value || '').trim() : '';
        // 비고: 빈 문자열도 반드시 전송해야 한다. `notes: x || undefined`는 JSON.stringify 시 키가
        // 빠져 서버가 column을 갱신하지 않아(이전 값 유지) 삭제·변경이 반영되지 않는 버그가 난다.
        const notesVal = (document.getElementById('erp-notes')?.value ?? '').trim();

        // DATA-01 낙관 잠금: 로드/저장이 받은 mutation_version 을 If-Match 로 되돌려 보내
        // 동시 편집의 lost update(items 배열 통째 교체)를 서버에서 막는다.
        // opts.force 는 사용자가 409 후 "덮어쓰기"를 고른 재시도 → 의도적으로 생략한다.
        const saveHeaders = { 'Content-Type': 'application/json' };
        if (opts.force !== true && typeof window.__erpLastMutationVersion === 'number') {
            saveHeaders['If-Match'] = String(window.__erpLastMutationVersion);
        }

        const res = await fetch(`/api/orders/${targetId}/structured`, {
            method: 'PUT',
            headers: saveHeaders,
            body: JSON.stringify({
                // DATA-01: provenance(raw_order_text/schema_version/confidence)는 전송하지 않는다.
                // 서버가 원본 파싱 provenance 를 보존한다(client overwrite 금지).
                structured_data,
                received_date: received_date || undefined,
                received_time: received_time || undefined,
                notes: notesVal,
                is_self_measurement: document.getElementById('erp-self-measurement')?.checked === true,
                is_regional: isRegionalOrder,
                construction_type: regionalConstructionType
            })
        });
        const data = await res.json();
        // 409(VERSION_CONFLICT): 데이터 보존이 최우선 — 여기서 절대 erpLoadStructured()나
        // 폼 리셋을 호출하지 않는다(사용자가 입력한 내용이 화면에 그대로 남아야 한다).
        if (res.status === 409 && opts.force !== true) {
            const wantsOverwrite = confirm(
                '다른 사용자가 이 주문을 먼저 수정했습니다.\n' +
                '내 입력으로 덮어쓸까요?\n\n' +
                '(취소하면 저장하지 않고 입력한 내용을 그대로 둡니다)'
            );
            if (!wantsOverwrite) {
                erpSetStatus('저장하지 않았습니다. 입력한 내용은 그대로 남아 있습니다.', true);
                return { success: false, message: '다른 사용자의 수정과 충돌해 저장하지 않았습니다.' };
            }
            // 덮어쓰기 재시도는 1회뿐 — force 호출에서 또 409 가 나면 아래 실패 경로로 간다.
            return await erpSaveStructuredOnce({ ...opts, force: true });
        }
        if (!data.success) {
            erpSetStatus(data.message || '저장 실패', true);
            return { success: false, message: data.message || '저장 실패' };
        }
        // 다음 저장이 stale 토큰으로 나가 무조건 409 가 되는 것을 막는다.
        window.__erpLastMutationVersion =
            typeof data.mutation_version === 'number' ? data.mutation_version : null;
        // 저장 성공 = 폼 단계가 서버 단계가 됨. 강제 변경 가드 base 를 함께 옮긴다.
        if (window.FOMS_STAGE_OVERRIDE &&
                typeof window.FOMS_STAGE_OVERRIDE.noteServerStage === 'function') {
            var _savedStageEl = document.getElementById('erp-workflow-stage');
            if (_savedStageEl) window.FOMS_STAGE_OVERRIDE.noteServerStage(_savedStageEl.value);
        }
        erpSetStatus(doRedirect ? '저장 완료! 이동합니다...' : '저장 완료');
        // 명시 저장(승격) 성공 → 자동저장 모듈이 로컬/세션 draft 흔적을 정리하도록 알림.
        try { document.dispatchEvent(new Event('erp:order-saved')); } catch (_e) {}
        // ORDER-REASON-00: 금액·일정·단계가 바뀐 저장이면 서버가 표시해서 보낸다. 판정은
        // 서버에만 있고, 화면은 저장이 끝난 뒤 사유를 받는다(저장을 막지 않는다).
        // **이동 전에 기다린다** — 저장 성공 직후 대시보드로 넘어가면 시트가 뜨자마자
        // 사라진다(2026-08-13 스테이징 QA 에서 실제로 그랬다).
        if (data.change_reason_required === true && data.change_set) {
            const reasonDetail = { orderId: targetId, changeSet: data.change_set, mode: 'full' };
            try {
                if (window.FomsChangeReason && typeof window.FomsChangeReason.prompt === 'function') {
                    await window.FomsChangeReason.prompt(reasonDetail);
                } else {
                    document.dispatchEvent(new CustomEvent('foms:change-reason-required', {
                        detail: reasonDetail
                    }));
                }
            } catch (_e) {}
        }
        // 저장 성공 후 Draft 모드 해제 → beforeunload 경고 비활성
        const wasDraftMode = isErpOrderDraftMode();
        if (wasDraftMode) {
            setErpOrderDraftMode(false);
        }
        if (structured_data && typeof structured_data === 'object') {
            if (!structured_data.meta || typeof structured_data.meta !== 'object') {
                structured_data.meta = {};
            }
            if (wasDraftMode || data.draft_cleared) {
                structured_data.meta.draft = false;
            }
            window.__erpLastStructuredData = structured_data;
        }
        if (typeof window.erpInvalidateEstimateCache === 'function') {
            window.erpInvalidateEstimateCache();
        }
        if (doRedirect) {
            if (redirectUrlOverride) {
                window.location.href = redirectUrlOverride;
            } else if (isErpOrderDraftMode()) {
                window.location.href = erpAppendFocusOrderParam('/erp/dashboard', targetId);
            } else {
                const referrerInput = document.querySelector('input[name="referrer"]');
                let targetUrl = referrerInput ? referrerInput.value : document.referrer;
                if (!targetUrl || targetUrl.includes(window.location.pathname)) targetUrl = '/erp/dashboard';
                erpNavigateAfterStructuredSave(erpAppendFocusOrderParam(targetUrl, targetId));
            }
        }
        return { success: true };
    } catch (e) {
        console.error(e);
        erpSetStatus(`저장 실패: ${String(e?.message || e)}`, true);
        return { success: false, message: String(e?.message || e) };
    }
}



document.addEventListener('DOMContentLoaded', function () {
    if (typeof syncErpOrderGlobalsFromDom === 'function') {
        syncErpOrderGlobalsFromDom();
    }
    if (!ERP_ORDER_ENABLED) return;
    erpBindReceivedTimeControl();
    erpBindScheduleTimeControl('erp-measurement-time-select', 'erp-measurement-time');
    erpBindScheduleTimeControl('erp-construction-time-select', 'erp-construction-time');
    erpBindUrgentReasonControl();
    erpBindAutosizeTextareas(document);

window.erpTogglePayment = async function(btn, pType) {
    if (_paymentTogglePending) return;
    
    let targetId = erpResolveCurrentOrderId();
    const isConfirmedNow = btn.dataset.confirmed === '1';
    const targetConfirmed = !isConfirmedNow;

    if (targetId <= 0 || erpIsDraftBackedOrder()) {
        erpToggleLocalPaymentState(pType, targetConfirmed);
        return;
    }

    _paymentTogglePending = true;
    
    // ================= Optimistic UI Update ================= //
    const originalPaymentData = window.__erpLastStructuredData && window.__erpLastStructuredData.payment 
        ? { ...window.__erpLastStructuredData.payment } 
        : _erpNormalizePaymentData({});
    
    const optimisticPaymentData = { ...originalPaymentData };
    if (pType === 'deposit') {
        optimisticPaymentData.deposit_confirmed = targetConfirmed;
        optimisticPaymentData.deposit_confirmed_by = '처리 중...';
        optimisticPaymentData.deposit_confirmed_at = new Date().toISOString();
    } else {
        optimisticPaymentData.balance_confirmed = targetConfirmed;
        optimisticPaymentData.balance_confirmed_by = '처리 중...';
        optimisticPaymentData.balance_confirmed_at = new Date().toISOString();
    }
    
    if (!window.__erpLastStructuredData) window.__erpLastStructuredData = {};
    window.__erpLastStructuredData.payment = optimisticPaymentData;
    _erpUpdatePaymentConfirmUI(pType, optimisticPaymentData);
    // ======================================================= //
    
    try {
        const res = await fetch(`/api/orders/${targetId}/payment-confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: pType,
                confirmed: targetConfirmed
            })
        });
        const data = await res.json();
        if (data.success && data.payment) {
            const p = _erpNormalizePaymentData({
                payment: Object.assign({}, originalPaymentData, data.payment),
            });
            window.__erpLastStructuredData.payment = p;
            _erpUpdatePaymentConfirmUI(pType, p);
        } else {
            alert(data.message || '상태 변경에 실패했습니다.');
            throw new Error(data.message || '상태 변경 처리 실패');
        }
    } catch (err) {
        console.error(err);
        // Rollback on error
        window.__erpLastStructuredData.payment = originalPaymentData;
        _erpUpdatePaymentConfirmUI(pType, originalPaymentData);
    } finally {
        _paymentTogglePending = false;
    }
};

    // ERP Order: 발주사 드롭다운 + 직접입력 토글
    document.getElementById('erp-orderer-direct')?.addEventListener('change', function () {
        toggleOrdererUI();
        syncWorkflowStageByOrderer();
    });
    toggleOrdererUI();
    document.getElementById('erp-orderer-select')?.addEventListener('change', syncWorkflowStageByOrderer);
    document.getElementById('erp-orderer')?.addEventListener('input', syncWorkflowStageByOrderer);
    document.getElementById('erp-orderer')?.addEventListener('change', syncWorkflowStageByOrderer);
    syncWorkflowStageByOrderer();

    // ORDER-FLAG-01: 라홈시스템·지방주문은 견적 공급자·지방 대시보드 모집단을 가르는 값이라
    // 켤 때와 끌 때 모두 확인한다. document 캡처에 두는 이유는 순서다 — 자동저장(pane 캡처)과
    // 아래 change 핸들러보다 먼저 잡아야 '취소'가 값 변경으로 새어나가지 않는다.
    if (!window.__fomsOrderFlagConfirmBound) {
        window.__fomsOrderFlagConfirmBound = true;
        const ORDER_FLAG_CONFIRM_LABELS = {
            'erp-factory2': '라홈시스템',
            'erp-regional-order': '지방주문',
        };
        document.addEventListener('change', function (event) {
            const target = event.target;
            if (!target || target.type !== 'checkbox') return;
            const label = ORDER_FLAG_CONFIRM_LABELS[target.id];
            if (!label) return;
            const nextChecked = !!target.checked;
            const question = nextChecked
                ? `'${label}'을(를) 켤까요?`
                : `'${label}'을(를) 끌까요?`;
            if (window.confirm(question)) return;
            // 취소: 체크 상태를 되돌리고 이벤트를 여기서 끊는다. 되돌린 상태가 곧 원래
            // 상태이므로 아래 동기화 핸들러들을 굳이 태울 필요가 없다.
            target.checked = !nextChecked;
            event.stopPropagation();
        }, true);
    }

    document.getElementById('erp-factory2')?.addEventListener('change', function () {
        if (typeof window.erpInvalidateEstimateCache === 'function') {
            window.erpInvalidateEstimateCache();
        }
        if (typeof window.erpApplyEstimateFactory2Variant === 'function') {
            window.erpApplyEstimateFactory2Variant(!!this.checked);
        }
    });

    // ERP Order: 지방주문이면 대시보드 필터용 하우드/협력사 구분을 반드시 받는다.
    document.getElementById('erp-regional-order')?.addEventListener('change', function () {
        erpSyncRegionalConstructionTypeVisibility({ clear: !this.checked });
    });
    erpSyncRegionalConstructionTypeVisibility({ clear: false });

    // ERP Order: 주소 입력 (통합 - 찾기 버튼으로 주소 검색 또는 직접 입력 가능)
    const addrInput = document.getElementById('erp-address');

    // ERP Order: 주소 검색 모달 (선택 후 '입력' 버튼으로 한꺼번에 적용)
    const addrModalEl = document.getElementById('erpAddressSearchModal');
    const addrModal = addrModalEl ? new bootstrap.Modal(addrModalEl) : null;
    const addrModalQuery = document.getElementById('erp-address-modal-query');
    const addrModalSearchBtn = document.getElementById('erp-address-modal-search-btn');
    const addrModalStatus = document.getElementById('erp-address-modal-status');
    const addrModalResults = document.getElementById('erp-address-modal-results');
    const addrModalApplyBtn = document.getElementById('erp-address-modal-apply-btn');
    const openSearchBtn = document.getElementById('erp-address-search-btn');

    let selectedModalAddress = '';

    async function doAddressSearch(query) {
        if (!query || !query.trim()) return;
        selectedModalAddress = '';
        if (addrModalStatus) addrModalStatus.textContent = '검색 중...';
        if (addrModalResults) addrModalResults.innerHTML = '';
        try {
            const qs = new URLSearchParams({ q: query.trim(), size: '10' });
            const res = await fetch(`/api/address/search?${qs.toString()}`);
            const data = await res.json();
            if (!data.success) {
                if (addrModalStatus) addrModalStatus.textContent = data.message || '검색 실패';
                return;
            }
            const results = data.results || [];
            if (addrModalStatus) addrModalStatus.textContent = `${results.length}건 검색됨. 주소를 선택한 뒤 상세주소 입력 후 '입력' 버튼을 누르세요.`;
            results.forEach(r => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'list-group-item list-group-item-action';
                const base = r.road_address_name || r.address_name || '-';
                const main = r.building_name ? `${base}, ${r.building_name}` : base;
                const sub = [r.building_name, r.region_3depth_name].filter(Boolean).join(' · ');
                item.innerHTML = `<div class="fw-semibold">${escapeHtml(main)}</div>${sub ? `<div class="small text-muted">
${escapeHtml(sub)}</div>` : ''}`;
                item.addEventListener('click', () => {
                    selectedModalAddress = main;
                    addrModalResults.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
                    item.classList.add('active');
                });
                addrModalResults.appendChild(item);
            });
        } catch (e) {
            if (addrModalStatus) addrModalStatus.textContent = `검색 실패: ${String(e?.message || e)}`;
        }
    }

    if (addrModalApplyBtn) {
        addrModalApplyBtn.addEventListener('click', () => {
            const detailEl = document.getElementById('erp-address-modal-detail');
            const detail = detailEl ? (detailEl.value || '').trim() : '';
            const full = selectedModalAddress ? (detail ? `${selectedModalAddress} ${detail}` : selectedModalAddress) : detail;
            if (addrInput) addrInput.value = full;
            if (addrModal) addrModal.hide();
        });
    }

    if (openSearchBtn && addrModal) {
        openSearchBtn.addEventListener('click', () => {
            selectedModalAddress = '';
            if (addrModalQuery) addrModalQuery.value = addrInput?.value || '';
            if (addrModalStatus) addrModalStatus.textContent = '';
            if (addrModalResults) addrModalResults.innerHTML = '';
            const detailEl = document.getElementById('erp-address-modal-detail');
            if (detailEl) detailEl.value = '';
            addrModal.show();
            setTimeout(() => addrModalQuery?.focus(), 200);
        });
    }

    if (addrModalEl) {
        addrModalEl.addEventListener('hidden.bs.modal', () => { selectedModalAddress = ''; });
    }

    if (addrModalSearchBtn) {
        addrModalSearchBtn.addEventListener('click', () => doAddressSearch(addrModalQuery?.value || ''));
    }
    if (addrModalQuery) {
        addrModalQuery.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                doAddressSearch(addrModalQuery.value);
            }
        });
    }

    // ERP Order: 연락처 자동 포맷 처리
    const erpManualPhone = document.getElementById('erp-manual-phone-input');
    const erpPhoneInput = document.getElementById('erp-customer-phone');
    function applyErpPhoneFormat() {
        if (!erpPhoneInput) return;
        if (erpManualPhone && erpManualPhone.checked) return;
        const raw = erpPhoneInput.value || '';
        if (/\n/.test(raw)) return;
        erpPhoneInput.value = formatPhoneAuto(raw);
    }
    if (erpPhoneInput) {
        erpPhoneInput.addEventListener('input', applyErpPhoneFormat);
        erpPhoneInput.addEventListener('blur', applyErpPhoneFormat);
        erpPhoneInput.addEventListener('change', applyErpPhoneFormat);
    }
    if (erpManualPhone) {
        erpManualPhone.addEventListener('change', function () {
            if (!this.checked) applyErpPhoneFormat();
        });
    }

    // 기본 항목 1개
    const itemsWrap = document.getElementById('erp-items');
    if (itemsWrap && itemsWrap.children.length === 0) {
        itemsWrap.appendChild(erpNewItemRow({}));
        erpRefreshItemRowIndices();
        erpOpenFirstItemRow();
        erpRecalcItemsTotal();
    }
    window.ErpItemsMasterDetail?.init?.();

    document.getElementById('erp-add-item-btn')?.addEventListener('click', function () {
        const wrap = document.getElementById('erp-items');
        if (!wrap) return;
        const newRow = erpNewItemRow({});
        wrap.appendChild(newRow);
        erpRefreshItemRowIndices();
        if (window.ErpItemsMasterDetail?.isActive?.()) {
            window.ErpItemsMasterDetail.selectItem(erpGetItemRows().length - 1);
        } else {
            erpToggleItemRow(newRow, true);
            newRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        erpRecalcItemsTotal();
        if (typeof erpRenderAttachments === 'function') {
            erpRenderAttachments();
        }
    });
    // 저장 버튼은 포커스를 뺏지 않는다(마우스 pointerdown 기본동작 차단).
    // 텍스트 입력(한글 IME)에 포커스를 둔 채 아래로 스크롤해 저장을 누르면
    // mousedown→blur→IME 커밋이 화면 밖 입력칸으로 네이티브 캐럿 스크롤을
    // 일으키고(부트스트랩 :root smooth 로 애니메이션), 버튼이 커서 밑에서
    // 이동해 click 이 무산되던 사고("저장 누르면 스크롤만 올라가고 저장 안 됨,
    // 재클릭은 됨")의 근본 수정. 터치는 제외 — pointerdown preventDefault 가
    // 모바일에서 click 합성을 막을 수 있다.
    document.getElementById('erp-save-btn')?.addEventListener('pointerdown', function (e) {
        if (e.pointerType === 'mouse') e.preventDefault();
    });
    document.getElementById('erp-save-btn')?.addEventListener('click', erpSaveStructured);
    document.getElementById('erp-load-btn')?.addEventListener('click', () => erpLoadStructured());

    // 모바일 섹션 이동 칩: 탭하면 해당 섹션으로 스크롤 + 접힌 섹션 펼침.
    // fragment 재실행 대비 singleton guard(중복 바인딩 차단).
    (function initErpMobileSecNav() {
        const nav = document.getElementById('erp-mobile-secnav');
        if (!nav || nav.dataset.erpSecnavBound === '1') return;
        nav.dataset.erpSecnavBound = '1';
        let scrollGen = 0;

        function scrollSecToView(target, gen) {
            const form = target.closest('.erp-order-mobile-form');
            const scroller = document.scrollingElement;
            if (!form || !scroller) return;

            form.style.removeProperty('--erp-mobile-secnav-tail');
            requestAnimationFrame(() => {
                if (gen !== scrollGen) return;
                const stickyTop = Number.parseFloat(window.getComputedStyle(nav).top) || 0;
                const viewportTargetTop = stickyTop + nav.getBoundingClientRect().height + 8;
                const targetTop = window.scrollY + target.getBoundingClientRect().top;
                const top = Math.max(0, targetTop - viewportTargetTop);
                const tail = Math.max(0, top - (scroller.scrollHeight - window.innerHeight));
                if (tail) form.style.setProperty('--erp-mobile-secnav-tail', `${Math.ceil(tail)}px`);

                requestAnimationFrame(() => {
                    if (gen === scrollGen) window.scrollTo({ top, behavior: 'auto' });
                });
            });
        }

        function expandThenScroll(target, toggle, gen) {
            const bodySel = toggle.getAttribute('data-bs-target');
            const body = bodySel ? document.querySelector(bodySel) : null;
            if (!body) {
                toggle.click();
                if (gen === scrollGen) scrollSecToView(target, gen);
                return;
            }
            // Expand first, then measure after Bootstrap finishes its height transition.
            body.addEventListener('shown.bs.collapse', () => {
                if (gen === scrollGen) scrollSecToView(target, gen);
            }, { once: true });
            toggle.click();
        }

        nav.addEventListener('click', (e) => {
            const chip = e.target.closest('.erp-mobile-secnav-chip');
            if (!chip) return;
            const target = chip.dataset.erpSecnavTarget && document.getElementById(chip.dataset.erpSecnavTarget);
            if (!target) return;
            nav.querySelectorAll('.erp-mobile-secnav-chip').forEach((c) => c.classList.toggle('is-active', c === chip));
            const gen = ++scrollGen;
            const collapsedToggle = target.querySelector('.erp-mobile-collapse-toggle[aria-expanded="false"]');
            if (collapsedToggle) expandThenScroll(target, collapsedToggle, gen);
            else scrollSecToView(target, gen);
        });
    })();

    // AS 접수 모달: 파일 미리보기, 10MB 경고, 제출, 취소 시 롤백
    (function initAsReceiveModal() {
        const modalEl = document.getElementById('asReceiveModal');
        const contentEl = document.getElementById('as-receive-content');
        const filesEl = document.getElementById('as-receive-files');
        const previewEl = document.getElementById('as-receive-preview');
        const submitBtn = document.getElementById('as-receive-submit-btn');
        const amountWrap = document.getElementById('as-receive-amount-wrap');
        const amountEl = document.getElementById('as-receive-amount');
        const sinceBadge = document.getElementById('as-receive-since-badge');
        const lockedNote = document.getElementById('as-receive-billing-locked-note');
        const billingRadios = () => Array.from(document.querySelectorAll('input[name="as-receive-billing"]'));

        function selectedBillingType() {
            const checked = billingRadios().find((r) => r.checked);
            return checked ? checked.value : 'free';
        }

        function syncBillingUi() {
            if (amountWrap) amountWrap.classList.toggle('d-none', selectedBillingType() !== 'paid');
        }
        billingRadios().forEach((r) => r.addEventListener('change', syncBillingUi));

        // 모바일 v2 코호트 페이지(edit_order_body.html)는 PC·모바일 파티얼을 모두 렌더한 뒤
        // 인라인 스크립트로 한쪽을 remove 한다. 두 벌의 라디오는 <form> 조상이 없어 같은
        // name이 문서 전체로 스코프되고, 파싱 중 두 번째 checked가 첫 번째의 checkedness를
        // 지운다 → 데스크톱에서 모바일 블록이 제거되면 남은 PC 세그먼트가 "선택 0개"가 된다
        // (defaultChecked:true / checked:false). 저장값은 selectedBillingType()의 'free'
        // 폴백으로 정확하지만 화면에는 기본값이 안 보인다. 그래서 살아남은 쪽을 보정한다.
        // 템플릿의 checked 속성을 지우는 방식은 반대 코호트에서 같은 버그를 만든다.
        function ensureBillingSelection() {
            const radios = billingRadios();
            if (!radios.length || radios.some((r) => r.checked)) return;
            (radios.find((r) => r.value === 'free') || radios[0]).checked = true;
        }
        ensureBillingSelection();

        // 재접수(지방 재상차 등)는 서버가 billing 페이로드를 무시하고 기존 판정을 보존한다
        // (foms/api/cs/as_orders.py: as_billing이 dict면 시드 건너뜀). 그래서 세그먼트를
        // 열어두면 "골랐는데 저장 안 됨"이 된다 — 기존값으로 고정하고 잠근다.
        // 예외 = 완료 뒤 **새 건**(reintake): 지난 건 판정이 cycle.billing_snapshot 에
        // 봉인돼 있어 서버가 이번 선택으로 재시드한다. 그때만 잠금을 푼다
        // (erpAsReceiveCanReseedBilling 이 서버 조건과 같은 술어를 쓴다).
        function applyExistingBillingLock() {
            const existing = window.__erpLastStructuredData?.shipment?.as_billing;
            const locked = !!existing && typeof existing === 'object' && !Array.isArray(existing)
                && !erpAsReceiveCanReseedBilling();
            const radios = billingRadios();
            if (locked) {
                const type = String(existing.type || 'free');
                radios.forEach((r) => { r.checked = (r.value === type); r.disabled = true; });
                if (amountEl) {
                    amountEl.value = (existing.amount === null || existing.amount === undefined)
                        ? ''
                        : String(existing.amount);
                    amountEl.disabled = true;
                }
            } else {
                radios.forEach((r) => { r.disabled = false; });
                if (amountEl) amountEl.disabled = false;
            }
            if (lockedNote) lockedNote.classList.toggle('d-none', !locked);
        }

        function refreshSinceBadge() {
            if (!sinceBadge) return;
            // 시공일(#erp-construction-date)은 "2026-03-13, 2026-03-14"처럼 여러 날짜가
            // 들어가는 text input이라 new Date(raw) 직접 파싱은 NaN이 난다. ISO 문자열은
            // 사전순=시간순이므로 정렬 후 마지막(가장 늦은 시공일)을 기준으로 잡는다.
            const raw = (document.getElementById('erp-construction-date')?.value || '').trim();
            const found = raw.match(/\d{4}-\d{2}-\d{2}/g);
            if (!found || !found.length) { sinceBadge.classList.add('d-none'); return; }
            const base = new Date(`${found.slice().sort().pop()}T00:00:00`);
            if (Number.isNaN(base.getTime())) { sinceBadge.classList.add('d-none'); return; }
            const months = Math.max(0, Math.floor((Date.now() - base.getTime()) / (1000 * 60 * 60 * 24 * 30.44)));
            sinceBadge.textContent = `시공 후 ${months}개월 경과`;
            sinceBadge.classList.remove('d-none');
        }

        if (filesEl && previewEl) {
            filesEl.addEventListener('change', function () {
                window.__erpAsReceiveClipboardFiles = [];
                const files = Array.from(this.files || []);
                erpRenderAsReceiveFilePreview(files);
            });
        }

        // 새 건은 빈 칸으로 연다(D4). 지난 증상은 버튼을 누른 사람만 가져가고,
        // '지우기'로 언제든 빈 칸으로 되돌린다 — 실수로 지난 내용이 남는 걸 막는다.
        const loadPrevBtn = document.getElementById('as-receive-load-prev');
        const clearContentBtn = document.getElementById('as-receive-clear-content');
        const loadHint = document.getElementById('as-receive-load-hint');
        if (loadPrevBtn && contentEl) {
            loadPrevBtn.addEventListener('click', function () {
                contentEl.value = (window.__erpLastStructuredData?.shipment?.as_content || '').trim();
                if (clearContentBtn) clearContentBtn.classList.remove('d-none');
                if (loadHint) loadHint.classList.remove('d-none');
                erpFocusWithoutScroll(contentEl);
            });
        }
        if (clearContentBtn && contentEl) {
            clearContentBtn.addEventListener('click', function () {
                contentEl.value = '';
                clearContentBtn.classList.add('d-none');
                if (loadHint) loadHint.classList.add('d-none');
                erpFocusWithoutScroll(contentEl);
            });
        }

        document.querySelectorAll('[data-erp-as-reregister-open]').forEach(function (button) {
            if (button.dataset.erpAsReregisterBound === '1') return;
            button.dataset.erpAsReregisterBound = '1';
            button.addEventListener('click', function () {
                if (!window.__erpStructuredLoadSucceeded) {
                    alert('주문 정보를 불러온 뒤 다시 시도해주세요.');
                    return;
                }
                const targetId = parseInt(button.dataset.orderId || '', 10)
                    || erpResolveCurrentOrderId();
                const previousStage =
                    (window.__erpLastStructuredData?.workflow?.stage || '').trim();
                if (!erpOpenAsReceiveModal(targetId, previousStage, { reregister: true })) {
                    alert('AS 접수 수정 화면을 열 수 없습니다.');
                    return;
                }
                erpSetStatus('수정할 AS 접수 내용을 확인해주세요.');
            });
        });

        if (modalEl) {
            // 오픈마다 재평가(상차일 wrap과 동일 원칙): 판정 잠금 → 세그먼트 → 경과 배지 순.
            modalEl.addEventListener('shown.bs.modal', function () {
                applyExistingBillingLock();
                syncBillingUi();
                refreshSinceBadge();
            });
            modalEl.addEventListener('hidden.bs.modal', function () {
                if (window.__erpAsReceiveSubmitted !== true) {
                    const stageEl = document.getElementById('erp-workflow-stage');
                    const prev = (window.__erpAsReceivePreviousStage || '').trim();
                    if (stageEl && prev) stageEl.value = prev;
                }
                window.__erpAsReceiveSubmitted = false;
            });
        }

        if (submitBtn) {
            submitBtn.addEventListener('click', async function () {
                const content = (contentEl?.value || '').trim();
                if (!content) {
                    alert('AS 내용을 입력해주세요.');
                    erpFocusWithoutScroll(contentEl);
                    return;
                }
                const targetId = window.__erpAsReceiveTargetId;
                if (!targetId || targetId <= 0) {
                    alert('주문 ID를 찾을 수 없습니다.');
                    return;
                }
                submitBtn.disabled = true;
                const origHtml = submitBtn.innerHTML;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> 처리 중...';

                // 지방주문 + 상차일 입력 시 AS 등록 payload에 포함(정본 경로에서 원자적 저장).
                const regPayload = { as_content: content };
                // 최초 접수의 무상/유상 "추정". 확정·전환은 POST /as/billing 소관이며,
                // 재접수 시에는 서버가 이 두 필드를 무시하고 기존 판정을 보존한다.
                const billingType = selectedBillingType();
                regPayload.billing_type = billingType;
                if (billingType === 'paid') {
                    const amt = parseInt(amountEl?.value || '', 10);
                    if (!Number.isNaN(amt) && amt >= 0) regPayload.amount = amt;
                }
                // 재발 표식은 새 건 core 에만 붙는다 — 열린 건 재접수(같은 건 갱신)에서는
                // 체크박스 자체가 숨겨져 있고 서버도 recurrence 를 봉인하지 않는다.
                const recurEl = document.getElementById('as-receive-recurrence');
                if (recurEl && recurEl.checked && window.__erpAsReceiveMode === 'reintake') {
                    regPayload.recurrence = true;
                }
                const shipDateEl = document.getElementById('as-receive-shipping-date');
                const isRegionalNow = document.getElementById('erp-regional-order')?.checked === true;
                const shipDateVal = (shipDateEl?.value || '').trim();
                if (isRegionalNow && shipDateVal) {
                    regPayload.shipping_scheduled_date = shipDateVal;
                }

                try {
                    const regRes = await fetch(`/api/orders/${targetId}/as/register`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(regPayload)
                    });
                    const regData = await regRes.json();
                    if (!regData.success) {
                        throw new Error(regData.message || 'AS 접수 등록 실패');
                    }
                    if (typeof regData.mutation_version === 'number') {
                        window.__erpLastMutationVersion = regData.mutation_version;
                    }
                    if (isRegionalNow && shipDateVal) {
                        window.__erpShippingScheduledDate = shipDateVal;
                    }

                    const previewCtl = document.getElementById('as-receive-preview')
                        && document.getElementById('as-receive-preview')._asOrder;
                    const fallbackFiles = Array.isArray(window.__erpAsReceiveClipboardFiles)
                        ? window.__erpAsReceiveClipboardFiles
                        : [];
                    const nativeFiles = filesEl?.files ? Array.from(filesEl.files) : [];
                    const files = previewCtl
                        ? previewCtl.getFiles()
                        : (fallbackFiles.length ? fallbackFiles : nativeFiles);
                    // AS-FRESH-01: 접수 첨부를 접수 기록에 결합한다. 무편집 재접수는 서버가
                    // 직전 동일 본문 항목 id 를 돌려주므로 그 파일도 고아가 되지 않는다.
                    const receptionLogId = regData.reception_log_id || '';
                    if (files.length > 0) {
                        if (typeof window.fomsUploadOrderAttachmentsBatch === 'function') {
                            await window.fomsUploadOrderAttachmentsBatch({
                                orderId: targetId,
                                files: files,
                                folder: `orders/${targetId}/attachments`,
                                category: 'as',
                                asLogId: receptionLogId || null,
                                sortOrders: files.map(function (_file, index) { return index; }),
                                useDirectUpload: (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD),
                                onPrepareProgress: function (info) {
                                    erpSetStatus(`이미지 최적화 중... (${info.done}/${info.total})`);
                                },
                                onUploadProgress: function (info) {
                                    erpSetStatus(`AS 첨부 업로드 중... (${Math.round(info.done)}/${info.total})`);
                                }
                            });
                        } else {
                            let uploaded = 0;
                            for (let i = 0; i < files.length; i += 1) {
                                const fd = new FormData();
                                fd.append('file', files[i]);
                                fd.append('category', 'as');
                                if (receptionLogId) fd.append('as_log_id', receptionLogId);
                                fd.append('sort_order', String(i));
                                const res = await fetch(`/api/orders/${targetId}/attachments`, { method: 'POST', body: fd });
                                const data = await res.json();
                                if (data && data.success) uploaded += 1;
                                erpSetStatus(`AS 첨부 업로드 중... (${uploaded}/${files.length})`);
                            }
                            if (uploaded !== files.length) {
                                throw new Error('일부 AS 첨부 업로드에 실패했습니다.');
                            }
                        }
                    }

                    window.__erpAsReceiveSubmitted = true;
                    if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
                        window.__erpLastStructuredData = {};
                    }
                    if (!window.__erpLastStructuredData.workflow || typeof window.__erpLastStructuredData.workflow !== 'object') {
                        window.__erpLastStructuredData.workflow = {};
                    }
                    // workflow.stage 는 건드리지 않는다 - AS 축은 본공정 stage 와
                    // 직교하고(STATE-AS-01), 서버 _pin_form_stage_to_server 가 폐기한다.
                    erpApplyAsStageDisplay(true);
                    if (!window.__erpLastStructuredData.shipment || typeof window.__erpLastStructuredData.shipment !== 'object') {
                        window.__erpLastStructuredData.shipment = {};
                    }
                    window.__erpLastStructuredData.shipment.as_content = content;

                    bootstrap.Modal.getInstance(modalEl)?.hide();
                    erpSetStatus('AS 접수 저장 중...');

                    const saveResult = await erpSaveStructured({
                        redirect: true,
                        redirectUrl: '/erp/as',
                    });
                    if (!saveResult || saveResult.success !== true) {
                        window.location.href = '/erp/as';
                    }
                } catch (e) {
                    console.error(e);
                    alert(e?.message || 'AS 접수 처리 중 오류가 발생했습니다.');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = origHtml;
                }
            });
        }
    })();
    erpBindAmountInput(
        document.getElementById('erp-deposit-amount'),
        erpParseDepositValue,
        function () {
            erpCalculateRemaining();
            if (typeof _erpRefreshDepositCoinVisual === 'function') {
                _erpRefreshDepositCoinVisual();
            }
        }
    );
    erpBindAmountInput(document.getElementById('erp-discount-amount'), erpParseDiscountValue);
    erpBindAmountInput(document.getElementById('erp-free-input-amount'), erpParseFreeInputAmountFromField);
    erpBindAllPriceInputs(document.getElementById('erp-items'));

    (function bindErpFreeInputTextField() {
        const freeInputTextEl = document.getElementById('erp-free-input-text');
        if (!freeInputTextEl || freeInputTextEl.dataset.erpFreeInputTextBound === '1') return;
        freeInputTextEl.dataset.erpFreeInputTextBound = '1';
        freeInputTextEl.addEventListener('input', erpCalculateRemaining);
        freeInputTextEl.addEventListener('change', erpCalculateRemaining);
    })();

    (function bindErpBalanceNoteControls() {
        if (window.__ERP_BALANCE_NOTE_BOUND) return;
        window.__ERP_BALANCE_NOTE_BOUND = true;
        const toggleBtn = document.getElementById('erp-balance-note-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                erpToggleBalanceNoteSection();
            });
        }
    })();


    // 초기 structured/첨부 로드는 fomsMountErpOrderSurface가 담당한다.
    // (여기서 erpLoadStructured를 또 호출하면 edit 화면에서 이중 fetch·DOM 주입이 발생해
    // 모바일 크롬이 STATUS_BREAKPOINT로 다운될 수 있다.)
    if (isErpOrderDraftMode()) {
        // [자동 완성 함수]
        function fillErpDateTime() {
            const rDate = document.getElementById('erp-received-date');
            const rTime = document.getElementById('erp-received-time');
            if (rDate && !rDate.value) {
                const now = new Date();
                const yyyy = now.getFullYear();
                const mm = String(now.getMonth() + 1).padStart(2, '0');
                const dd = String(now.getDate()).padStart(2, '0');
                rDate.value = `${yyyy}-${mm}-${dd}`;
            }
            if (rTime && !rTime.value) {
                const now = new Date();
                const timeValue = erpFormatHalfHourTime(now);
                rTime.value = timeValue;
                erpSetReceivedTimeControlValue(timeValue);
            }
        }

        // 1. 처음 로드 시 시도
        fillErpDateTime();

        // 2. 탭 전환 시 시도
        const erpTabBtn = document.getElementById('erp-order-tab');
        if (erpTabBtn) {
            erpTabBtn.addEventListener('shown.bs.tab', fillErpDateTime);
        }
    }
});

// ============================================
// ERP Order: Attachments (photo/video)
// ============================================
let __erpAttachments = [];
const ERP_ATTACHMENT_CATEGORY_LABELS = {
    measurement: '실측',
    drawing: '도면',
    construction: '시공',
    as: 'AS'
};

function erpNormalizeAttachmentCategory(category) {
    const c = String(category || '').trim().toLowerCase();
    if (c === 'drawing' || c === 'construction' || c === 'as') return c;
    return 'measurement';
}

function erpAttachmentSupportsItemLink(attachmentOrCategory) {
    const category = typeof attachmentOrCategory === 'object' && attachmentOrCategory
        ? attachmentOrCategory.category
        : attachmentOrCategory;
    const normalized = erpNormalizeAttachmentCategory(category);
    return normalized === 'measurement' || normalized === 'drawing';
}

function erpAttachmentsSetStatus(text, isError = false) {
    const el = document.getElementById('erp-attachments-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('text-danger', !!isError);
    el.classList.toggle('text-muted', !isError);
}

function erpParseAttachmentItemIndex(rawValue) {
    if (rawValue === null || rawValue === undefined || rawValue === '') return null;
    const n = Number(rawValue);
    if (!Number.isInteger(n) || n < 0) return null;
    return n;
}

function erpBuildAttachmentItemOptions(selectedIndex) {
    const rows = erpGetItemRows();
    const selected = erpParseAttachmentItemIndex(selectedIndex);
    const options = [`<option value="" ${selected === null ? 'selected' : ''}>공통(제품 미연결)</option>`];
    rows.forEach((row, idx) => {
        const name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
        const label = name ? `항목 ${idx + 1} - ${name}` : `항목 ${idx + 1}`;
        options.push(`<option value="${idx}" ${selected === idx ? 'selected' : ''}>${escapeHtml(label)}</option>`);
    });
    return options.join('');
}

function erpGetAttachmentById(attachmentId) {
    const targetId = Number(attachmentId);
    return (__erpAttachments || []).find(x => Number(x.id) === targetId) || null;
}

async function erpPatchAttachmentItemIndex(attachmentId, itemIndex) {
    const body = { item_index: itemIndex === null ? null : Number(itemIndex) };
    const res = await fetch(`/api/orders/${ORDER_ID}/attachments/${attachmentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.success) {
        throw new Error(data.message || '첨부 연결 변경 실패');
    }
    return data.attachment || null;
}

async function erpLinkAttachmentToItem(attachmentId, itemIndexValue) {
    try {
        const itemIndex = (itemIndexValue === '' || itemIndexValue === null || itemIndexValue === undefined)
            ? null
            : erpParseAttachmentItemIndex(itemIndexValue);
        if (itemIndexValue !== '' && itemIndex === null) {
            throw new Error('유효한 항목을 선택하세요.');
        }
        await erpPatchAttachmentItemIndex(attachmentId, itemIndex);
        erpAttachmentsSetStatus('첨부 연결이 변경되었습니다.');
        await erpLoadAttachments();
    } catch (e) {
        console.error(e);
        erpAttachmentsSetStatus(String(e?.message || e), true);
    }
}

function erpIsMobileAttachmentLayout() {
    return erpIsMobileFormContext();
}

function erpBuildAttachmentMediaTile(a) {
    const name = escapeHtml(a.filename || '');
    const type = a.file_type || 'file';
    const thumb = a.thumbnail_view_url || a.view_url || '';
    const viewUrl = a.view_url || thumb || '#';
    const isMobileLayout = erpIsMobileAttachmentLayout();
    const gridImageSrc =
        type === 'image' && isMobileLayout
            ? (a.view_url || a.thumbnail_view_url || '')
            : (a.thumbnail_view_url || a.view_url || '');

    if (type === 'video') {
        return `
<div class="erp-attachment-tile__media erp-attachment-tile__media--video">
    ${thumb ? `<img src="${thumb}" alt="${name}">` : `<video src="${viewUrl}" muted playsinline preload="metadata"></video>`}
    <span class="erp-attachment-tile__type"><i class="fas fa-video"></i></span>
</div>`;
    }
    if (type === 'image') {
        return `
<div class="erp-attachment-tile__media">
    <img src="${gridImageSrc || viewUrl}" alt="${name}" loading="lazy" decoding="async">
</div>`;
    }
    return `
<div class="erp-attachment-tile__media erp-attachment-tile__media--file">
    <i class="fas fa-file-alt"></i>
</div>`;
}

function erpBuildAttachmentTile(a, options = {}) {
    const name = escapeHtml(a.filename || '첨부');
    const itemIndex = erpParseAttachmentItemIndex(a.item_index);
    const badge = options.showItemBadge && itemIndex !== null ? `<span class="erp-attachment-tile__badge">항목 ${itemIndex + 1}</span>` : '';
    return `
<button type="button" class="erp-attachment-tile" data-erp-attachment-id="${escapeHtml(String(a.id))}"
    title="${name}" onclick="erpOpenAttachmentPreview('${a.id}')">
    ${erpBuildAttachmentMediaTile(a)}
    <span class="erp-attachment-tile__name">${name}</span>
    ${badge}
</button>`;
}

function erpApplyAttachmentPermissionsFromBootstrap(data) {
    const perms = data && data.attachment_permissions;
    if (!perms || typeof perms !== 'object') {
        window.__erpAttachmentPermissions = null;
        return;
    }
    window.__erpAttachmentPermissions = {
        currentUserId: perms.current_user_id != null ? parseInt(String(perms.current_user_id), 10) : null,
        isAdmin: !!perms.is_admin,
        isOrderManager: !!perms.is_order_manager,
    };
}

function erpCanDeleteAttachment(attachment) {
    if (!attachment) return false;
    if (typeof attachment.can_delete === 'boolean') return attachment.can_delete;
    const perms = window.__erpAttachmentPermissions;
    if (!perms) return false;
    if (perms.isAdmin || perms.isOrderManager) return true;
    const uid = perms.currentUserId;
    const attUid = attachment.user_id != null ? parseInt(String(attachment.user_id), 10) : null;
    return uid != null && attUid != null && uid === attUid;
}

function erpSyncAttachmentPreviewActions(attachment) {
    const a = attachment || null;
    const select = document.getElementById('erp-attachment-preview-item-select');
    const unlinkBtn = document.getElementById('erp-attachment-preview-unlink');
    const deleteBtn = document.getElementById('erp-attachment-preview-delete');
    if (!select && !unlinkBtn && !deleteBtn) return;

    const canLinkToItem = !!(a && erpAttachmentSupportsItemLink(a));
    const linkedIndex = a ? erpParseAttachmentItemIndex(a.item_index) : null;

    if (select) {
        select.classList.toggle('d-none', !canLinkToItem);
        select.disabled = !canLinkToItem;
        if (canLinkToItem) {
            select.innerHTML = erpBuildAttachmentItemOptions(a.item_index);
            select.onchange = async function () {
                await erpLinkAttachmentToItem(a.id, this.value);
                const fresh = erpGetAttachmentById(a.id) || Object.assign({}, a, { item_index: this.value || null });
                erpSyncAttachmentPreviewActions(fresh);
            };
        } else {
            select.innerHTML = '';
            select.onchange = null;
        }
    }

    if (unlinkBtn) {
        unlinkBtn.classList.toggle('d-none', !canLinkToItem || linkedIndex === null);
        unlinkBtn.onclick = (!canLinkToItem || linkedIndex === null) ? null : async function () {
            await erpLinkAttachmentToItem(a.id, '');
            const fresh = erpGetAttachmentById(a.id) || Object.assign({}, a, { item_index: null });
            erpSyncAttachmentPreviewActions(fresh);
        };
    }

    if (deleteBtn) {
        const canDelete = erpCanDeleteAttachment(a);
        deleteBtn.classList.toggle('d-none', !a || !canDelete);
        deleteBtn.onclick = (!a || !canDelete) ? null : async function () {
            await erpDeleteAttachment(a.id);
            if (!erpGetAttachmentById(a.id)) {
                const modalEl = document.getElementById('erpAttachmentPreviewModal');
                if (modalEl && window.bootstrap) {
                    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                }
            }
        };
    }
}

async function erpReindexItemLinkedAttachmentsAfterItemRemoval(removedIndex) {
    if (!ORDER_ID || removedIndex < 0) return;
    const list = (__erpAttachments || []).filter((a) => erpAttachmentSupportsItemLink(a));
    const updates = [];
    list.forEach((a) => {
        const idx = erpParseAttachmentItemIndex(a.item_index);
        if (idx === null) return;
        if (idx === removedIndex) updates.push({ id: a.id, itemIndex: null });
        else if (idx > removedIndex) updates.push({ id: a.id, itemIndex: idx - 1 });
    });
    if (!updates.length) return;
    erpAttachmentsSetStatus('항목 삭제로 이미지 연결을 조정 중입니다...');
    for (const u of updates) {
        await erpPatchAttachmentItemIndex(u.id, u.itemIndex);
    }
    await erpLoadAttachments();
}

async function erpUploadItemAttachments(itemIndex, files) {
    if (!ERP_ORDER_ENABLED) return;
    if (!Number.isInteger(itemIndex) || itemIndex < 0) {
        erpAttachmentsSetStatus('유효한 제품 항목을 찾지 못했습니다.', true);
        return;
    }
    const targetId = await erpRequireOrderIdOrWarn('제품 첨부 업로드:');
    if (!targetId) {
        return;
    }
    if (!Array.isArray(files) || !files.length) {
        erpAttachmentsSetStatus('업로드할 파일을 선택하세요.', true);
        return;
    }

    // --- Optimistic UI Start ---
    // 1. UI에 회색 스켈레톤/로딩 카드 먼저 렌더링
    const row = erpGetItemRows()[itemIndex];
    const galleryWrap = row ? row.querySelector('.erp-item-attachments-gallery') : null;
    if (galleryWrap) {
        // 빈 상태 텍스트 제거
        const emptyText = galleryWrap.querySelector('.text-muted');
        if (emptyText && emptyText.textContent.includes('없습니다')) emptyText.remove();

        files.forEach((f, fi) => {
            const uniqueId = 'opt-ul-' + Date.now() + '-' + fi;
            f._optId = uniqueId; // 파일 객체에 임시 ID 부여
            const name = escapeHtml(f.name);
            let previewUrl = '';
            try { previewUrl = URL.createObjectURL(f); } catch (e) { }

            const isMobilePlaceholder = erpIsMobileAttachmentLayout();
            const isVideo = String(f.type || '').startsWith('video/');
            const placeholderHtml = isMobilePlaceholder ? `
<div id="${uniqueId}" class="erp-attachment-tile erp-attachment-tile--pending opacity-75">
    <div class="erp-attachment-tile__media ${isVideo ? 'erp-attachment-tile__media--video' : ''}">
        ${isVideo
                    ? `<i class="fas fa-video"></i><span class="erp-attachment-tile__type"><i class="fas fa-spinner fa-spin"></i></span>`
                    : `<img src="${previewUrl}" alt="${name}" style="filter:grayscale(100%);">`}
    </div>
    <span class="erp-attachment-tile__name">${name}</span>
    <span class="erp-attachment-tile__badge opt-pct">0%</span>
</div>` : `
<div id="${uniqueId}" class="border rounded bg-light p-1 d-flex align-items-center gap-1 opacity-75" style="max-width: 200px;">
<div class="position-relative">
    <img src="${previewUrl}" class="rounded" style="width:40px;height:40px;object-fit:cover;filter:grayscale(100%);">
    <div class="spinner-border spinner-border-sm text-primary position-absolute" style="top:50%;left:50%;margin-top:-0.5rem;margin-left:-0.5rem;" role="status"></div>
</div>
<div class="small text-truncate flex-grow-1" style="max-width: 80px;" title="${name}">${name}</div>
<div class="small text-primary fw-bold pe-2 opt-pct">0%</div>
</div>`;
            galleryWrap.insertAdjacentHTML('beforeend', placeholderHtml);
        });
    }
    // --- Optimistic UI End ---

    erpAttachmentsSetStatus(`제품 항목 ${itemIndex + 1} 첨부 등록 중... (${files.length}개)`);
    const progressWrap = document.getElementById('erp-attachments-progress');
    const progressBar = document.getElementById('erp-attachments-progress-bar');
    if (progressWrap) progressWrap.classList.remove('d-none');
    const totalFiles = files.length;
    let ok = 0;
    const uploadResult = await window.fomsUploadOrderAttachmentsBatch({
        orderId: ORDER_ID,
        files: files,
        folder: `orders/${ORDER_ID}/measurement`,
        category: 'measurement',
        itemIndex: itemIndex,
        useDirectUpload: (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD),
        onPrepareProgress: function (info) {
            erpAttachmentsSetStatus(`이미지 최적화 중... (${info.done}/${info.total})`);
        },
        onUploadProgress: function (info) {
            if (progressBar) {
                const p = Math.round((info.done / totalFiles) * 100);
                progressBar.style.width = p + '%';
                progressBar.textContent = p + '%';
            }
        },
        onFileDone: function (info) {
            const el = document.getElementById(info.entry.originalFile._optId);
            if (el) {
                const pctSpan = el.querySelector('.opt-pct');
                if (pctSpan) pctSpan.textContent = info.result && info.result.success ? '완료' : '실패';
            }
        }
    });
    ok = uploadResult.ok;
    if (progressWrap) progressWrap.classList.add('d-none');
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
    erpAttachmentsSetStatus(`제품 항목 ${itemIndex + 1} 첨부 등록 완료: ${ok}/${files.length}`);
    await erpLoadAttachments();
}

async function erpUploadItemAttachmentsPromptless(inputElement) {
    if (!inputElement || !inputElement.files || inputElement.files.length === 0) return;
    const row = inputElement.closest('.erp-item-row');
    if (!row) return;
    // 행 인덱스 계산
    const rows = Array.from(document.querySelectorAll('.erp-item-row'));
    const itemIndex = rows.indexOf(row);
    if (itemIndex < 0) return;

    await erpUploadItemAttachments(itemIndex, Array.from(inputElement.files));
    inputElement.value = ''; // Reset input to allow triggering change event again with same files
}

function erpExpandMobileAttachmentSections() {
    if (!erpIsMobileFormContext()) return;
    const items = Array.isArray(__erpAttachments) ? __erpAttachments : [];
    if (!items.length) return;

    const collapseIds = [
        'erp-mobile-collapse-attachments-body',
    ];
    collapseIds.forEach((bodyId) => {
        const body = document.getElementById(bodyId);
        if (!body || body.classList.contains('show')) return;
        if (typeof window.bootstrap !== 'undefined' && window.bootstrap.Collapse) {
            window.bootstrap.Collapse.getOrCreateInstance(body, { toggle: false }).show();
            return;
        }
        body.classList.add('show');
        const toggle = document.querySelector(`[data-bs-target="#${bodyId}"]`);
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
            const icon = toggle.querySelector('i');
            if (icon) {
                icon.classList.remove('fa-chevron-right');
                icon.classList.add('fa-chevron-down');
            }
        }
    });
}

function erpItemAttachmentLinksForRow(measurementItems, idx, rowCount) {
    const linked = measurementItems.filter((a) => erpParseAttachmentItemIndex(a.item_index) === idx);
    if (linked.length || rowCount !== 1 || idx !== 0) {
        return linked;
    }
    // 단일 제품 행: item_index 미지정(공통) 실측 첨부도 항목 갤러리에 노출
    return measurementItems.filter((a) => erpParseAttachmentItemIndex(a.item_index) === null);
}

function erpRenderItemAttachmentPanels() {
    const rows = erpGetItemRows();
    const measurementItems = (__erpAttachments || []).filter((a) => erpNormalizeAttachmentCategory(a.category) === 'measurement');
    const isMobileLayout = erpIsMobileAttachmentLayout();
    rows.forEach((row, idx) => {
        const wrap = row.querySelector('.erp-item-attachments-gallery');
        if (!wrap) return;
        wrap.classList.toggle('erp-attachment-tile-grid', isMobileLayout);
        const linked = erpItemAttachmentLinksForRow(measurementItems, idx, rows.length);
        if (!linked.length) {
            wrap.innerHTML = `<div class="small text-muted${isMobileLayout ? ' erp-attachment-empty' : ''}">${erpItemAttachmentEmptyText()}</div>`;
            return;
        }
        wrap.innerHTML = linked.map((a) => {
            if (isMobileLayout) {
                return erpBuildAttachmentTile(a, { showItemBadge: false });
            }
            const thumb = a.thumbnail_view_url || a.view_url || '';
            const name = escapeHtml(a.filename || '');
            const type = a.file_type || 'file';
            const mediaHtml = type === 'video'
                ? `<button type="button" class="btn btn-light border p-0" style="width:40px;height:40px;"
    title="${name}" onclick="erpOpenAttachmentPreview('${a.id}')"><i class="fas fa-video"></i></button>`
                : type === 'image'
                    ? `<img src="${thumb}" alt="${name}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;cursor:zoom-in;"
    onclick="erpOpenAttachmentPreview('${a.id}')">`
                    : `<button type="button" class="btn btn-light border p-0" style="width:40px;height:40px;"
    title="${name}" onclick="erpOpenAttachmentPreview('${a.id}')"><i class="fas fa-file-alt"></i></button>`;
            return `
<div class="border rounded bg-white p-1 d-flex align-items-center gap-1" style="max-width: 200px;">
${mediaHtml}
<div class="small text-truncate flex-grow-1" style="max-width: 80px;" title="${name}">${name}</div>
<div class="d-flex gap-1">
    <button type="button" class="btn btn-sm btn-outline-secondary" title="공통으로 이동"
        onclick="erpLinkAttachmentToItem('${a.id}', '')">
        <i class="fas fa-unlink"></i>
    </button>
    ${erpCanDeleteAttachment(a) ? `
    <button type="button" class="btn btn-sm btn-outline-danger" title="삭제(공통 첨부에서도 제거)"
        onclick="erpDeleteAttachment('${a.id}')">
        <i class="fas fa-trash"></i>
    </button>` : ''}
</div>
</div>`;
        }).join('');
    });
}

function erpRenderAttachments() {
    const wrap = document.getElementById('erp-attachments-gallery');
    if (!wrap) return;
    const items = Array.isArray(__erpAttachments) ? __erpAttachments : [];
    const isMobileLayout = erpIsMobileAttachmentLayout();
    wrap.classList.toggle('erp-attachment-tile-grid', isMobileLayout);
    if (!items.length) {
        wrap.innerHTML = `<div class="col-12 erp-attachment-empty">
<div class="small text-muted">첨부된 파일이 없습니다.</div>
</div>`;
        erpRenderItemAttachmentPanels();
        return;
    }

    const grouped = { measurement: [], drawing: [], construction: [], as: [] };
    items.forEach((a) => {
        const key = erpNormalizeAttachmentCategory(a.category);
        grouped[key].push(Object.assign({}, a, { category: key }));
    });

    const order = ['measurement', 'drawing', 'construction', 'as'];

    if (isMobileLayout) {
        const sections = order
            .map((key) => ({ key, list: grouped[key] || [] }))
            .filter((section) => section.list.length > 0);
        if (!sections.length) {
            wrap.innerHTML = `<div class="erp-attachment-empty small text-muted">첨부된 파일이 없습니다.</div>`;
            erpRenderItemAttachmentPanels();
            return;
        }
        wrap.innerHTML = sections.map(({ key, list }) => {
            const label = ERP_ATTACHMENT_CATEGORY_LABELS[key] || key;
            return `
<div class="erp-attachment-group-header">
    <div class="fw-semibold">${label}</div>
    <span class="badge bg-primary">${list.length}</span>
</div>
${list.map((a) => erpBuildAttachmentTile(a, { showItemBadge: erpAttachmentSupportsItemLink(a) })).join('')}
`;
        }).join('');
        erpRenderItemAttachmentPanels();
        return;
    }

    const renderCard = (a) => {
        const name = escapeHtml(a.filename || '');
        const type = a.file_type || 'file';
        const thumb = a.thumbnail_view_url || a.view_url;
        const viewUrl = a.view_url || '#';
        const downloadUrl = a.download_url || '#';

        const mediaHtml = (type === 'video')
            ? `<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">
<video src="${viewUrl}" controls preload="metadata" style="width:100%;height:100%;"></video>
</div>`
            : (type === 'image')
                ? `<img src="${thumb}" alt="${name}" class="img-fluid rounded"
style="max-height: 220px; cursor: zoom-in; background:#fff; padding:4px;"
onclick="erpOpenAttachmentPreview('${a.id}')">`
                : `<div class="border rounded d-flex flex-column align-items-center justify-content-center bg-light"
style="height: 220px;">
<i class="fas fa-file-alt text-secondary mb-2" style="font-size: 2rem;"></i>
<div class="small text-muted text-center px-2">문서 파일</div>
</div>`;

        return `
<div class="col-md-4 col-sm-6 col-12">
<div class="card h-100">
    <div class="card-body p-2">
        ${mediaHtml}
        ${erpAttachmentSupportsItemLink(a) ? `
        <div class="mt-2">
            <label class="form-label mb-1 small text-muted">제품 연결</label>
            <select class="form-select form-select-sm" onchange="erpLinkAttachmentToItem('${a.id}', this.value)">
                ${erpBuildAttachmentItemOptions(a.item_index)}
            </select>
        </div>
        ` : ''}
        <div class="d-flex justify-content-between align-items-center mt-2">
            <div class="small text-truncate" title="${name}" style="max-width: 70%;">${name}</div>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-secondary" type="button" title="미리보기"
                    onclick="erpOpenAttachmentPreview('${a.id}')">
                    <i class="fas fa-eye"></i>
                </button>
                <a class="btn btn-outline-primary" href="${downloadUrl}" title="다운로드" target="_blank"
                    rel="noopener">
                    <i class="fas fa-download"></i>
                </a>
                ${erpCanDeleteAttachment(a) ? `
                <button class="btn btn-outline-danger" type="button" title="삭제"
                    onclick="erpDeleteAttachment('${a.id}')">
                    <i class="fas fa-trash"></i>
                </button>` : ''}
            </div>
        </div>
    </div>
</div>
</div>
`;
    };

    wrap.innerHTML = order.map((key) => {
        const list = grouped[key] || [];
        const label = ERP_ATTACHMENT_CATEGORY_LABELS[key] || key;
        if (!list.length) {
            return `
<div class="col-12">
<div class="d-flex justify-content-between align-items-center mb-1 mt-2">
    <div class="fw-semibold">${label}</div>
    <span class="badge bg-light text-dark">0</span>
</div>
<div class="small text-muted border rounded p-2 bg-light">첨부된 파일이 없습니다.</div>
</div>
`;
        }
        return `
<div class="col-12">
<div class="d-flex justify-content-between align-items-center mb-1 mt-2">
    <div class="fw-semibold">${label}</div>
    <span class="badge bg-primary">${list.length}</span>
</div>
</div>
${list.map(renderCard).join('')}
`;
    }).join('');
    erpRenderItemAttachmentPanels();
}

async function erpLoadAttachments() {
    if (!ERP_ORDER_ENABLED) return;
    if (!ORDER_ID) return;
    try {
        // 파일 input 초기화 (이전 주문의 파일이 남아있지 않도록)
        const fileInput = document.getElementById('erp-attachments-input');
        if (fileInput) {
            fileInput.value = '';
        }

        const res = await fetch(`/api/orders/${ORDER_ID}/attachments`);
        const data = await res.json();
        if (!data.success) throw new Error(data.message || '첨부 목록 조회 실패');
        __erpAttachments = data.attachments || [];
        erpRenderAttachments();
        erpExpandMobileAttachmentSections();
    } catch (e) {
        console.error(e);
        erpAttachmentsSetStatus(String(e?.message || e), true);
    }
}

function erpReleaseAttachmentPreviewModalFocus(modalEl) {
    if (!modalEl) return;
    var active = document.activeElement;
    if (active && (modalEl === active || modalEl.contains(active))) {
        if (typeof active.blur === 'function') active.blur();
    }
    if (modalEl === document.activeElement && typeof modalEl.blur === 'function') {
        modalEl.blur();
    }
}

function erpRestoreAttachmentPreviewModalFocus(modalEl) {
    if (!modalEl) return;
    var target = modalEl._fomsPreviewReturnFocus || modalEl._erpPreviewReturnFocus;
    modalEl._fomsPreviewReturnFocus = null;
    modalEl._erpPreviewReturnFocus = null;
    if (!target || typeof target.focus !== 'function' || !document.contains(target)) return;
    if (target === modalEl || modalEl.contains(target)) return;
    try {
        target.focus({ preventScroll: true });
    } catch (err) {
        try { target.focus(); } catch (ignored) { /* noop */ }
    }
}

function erpEnsureAttachmentPreviewModalZoomReset() {
    var modalEl = document.getElementById('erpAttachmentPreviewModal');
    if (!modalEl || typeof window.fomsBindAttachmentPreviewModalZoomReset !== 'function') return;
    window.fomsBindAttachmentPreviewModalZoomReset(modalEl, 'erp-attachment-preview-body', {
        saveFocusOnShow: true,
        releaseFocusOnHide: function () {
            erpReleaseAttachmentPreviewModalFocus(modalEl);
        },
        restoreFocusOnHidden: function () {
            erpRestoreAttachmentPreviewModalFocus(modalEl);
        }
    });
}

function erpResetAttachmentPreviewZoom(img) {
    if (typeof window.fomsResetAttachmentPreviewZoom === 'function') {
        window.fomsResetAttachmentPreviewZoom(img);
    }
}

function erpApplyAttachmentPreviewZoom(img) {
    if (typeof window.fomsApplyAttachmentPreviewZoom === 'function') {
        window.fomsApplyAttachmentPreviewZoom(img);
    }
}

function erpBindAttachmentPreviewImageZoom(bodyEl) {
    if (typeof window.fomsBindAttachmentPreviewImageZoom !== 'function') return;
    window.fomsBindAttachmentPreviewImageZoom(bodyEl, {
        ensureModalReset: erpEnsureAttachmentPreviewModalZoomReset
    });
}

function erpOpenAttachmentPreview(attachmentId) {
    const targetId = Number(attachmentId);
    const a = (__erpAttachments || []).find(x => Number(x.id) === targetId);
    if (!a) return;
    const modalEl = document.getElementById('erpAttachmentPreviewModal');
    const body = document.getElementById('erp-attachment-preview-body');
    const dl = document.getElementById('erp-attachment-preview-download');
    if (!modalEl || !body || !dl) return;

    const storageKey = a.storage_key || (a.download_url && String(a.download_url).replace(/^\/api\/files\/download\//, ''));
    const storagePath = storageKey ? storageKey.split('/').map(function (s) { return encodeURIComponent(s); }).join('/') : '';
    function isSignedStorageUrl(url) {
        return /(?:^|\/\/|[.])r2\.cloudflarestorage\.com/i.test(url || '') ||
            /(?:[?&](?:X-Amz-Signature|Signature)=)/i.test(url || '');
    }
    const stableViewUrl = storagePath ? `/api/files/view/${storagePath}` : '#';
    const stableDownloadUrl = storagePath ? `/api/files/download/${storagePath}` : '#';
    const viewUrl = isSignedStorageUrl(a.view_url) ? stableViewUrl : (a.view_url || stableViewUrl);
    const downloadUrl = isSignedStorageUrl(a.download_url) ? stableDownloadUrl : (a.download_url || stableDownloadUrl);
    dl.href = downloadUrl;
    erpSyncAttachmentPreviewActions(a);

    if (a.file_type === 'video') {
        body.innerHTML = `
<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">
<video src="${viewUrl}" controls autoplay style="width:100%;height:100%;"></video>
</div>
<div class="small text-muted mt-2 erp-attachment-preview-caption">${escapeHtml(a.filename || '')}</div>
`;
    } else if (a.file_type === 'file') {
        body.innerHTML = `
<div class="d-flex flex-column align-items-center justify-content-center text-center p-4" style="min-height: 280px;">
<i class="fas fa-file-alt text-secondary mb-3" style="font-size: 3rem;"></i>
<div class="fw-semibold mb-2">${escapeHtml(a.filename || '파일')}</div>
<div class="small text-muted mb-3">문서 파일은 미리보기를 지원하지 않습니다.</div>
<a class="btn btn-primary" href="${downloadUrl}" target="_blank" rel="noopener">
    <i class="fas fa-download"></i> 다운로드
</a>
</div>
`;
    } else {
        body.innerHTML = `
<img src="${viewUrl}" alt="${escapeHtml(a.filename || '')}" class="img-fluid rounded erp-attachment-preview-img" draggable="false">
<div class="small text-muted mt-2 erp-attachment-preview-caption">${escapeHtml(a.filename || '')}</div>
`;
        erpBindAttachmentPreviewImageZoom(body);
    }

    erpEnsureAttachmentPreviewModalZoomReset();

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    // Keep preview media on stable app routes; direct R2 signed URLs expire in long-lived modals.
}

async function erpDoDirectUploadOne(originalFile, category, itemIndex, preFetchedSess) {
    let file = originalFile;
    if (typeof window.compressImageFile === 'function') {
        try { file = await window.compressImageFile(originalFile, { quality: 0.8 }); } catch (e) { console.warn('Compression failed', e); }
    }

    let sess = preFetchedSess;
    if (!sess || !sess.success || !sess.upload_url) {
        const folder = `orders/${ORDER_ID}/${category || 'attachments'}`;
        const sessRes = await fetch('/api/upload/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, size: file.size, folder: folder })
        });
        sess = await sessRes.json();

        if (!sessRes.ok || !sess.success || !sess.upload_url) {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('category', category || 'measurement');
            if (itemIndex != null) fd.append('item_index', String(itemIndex));
            const res = await fetch(`/api/orders/${ORDER_ID}/attachments`, { method: 'POST', body: fd });
            const data = await res.json();
            return data.success ? { success: true, attachment: data.attachment } : data;
        }
    }
    const fallbackForm = async () => {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('category', category || 'measurement');
        if (itemIndex != null) fd.append('item_index', String(itemIndex));
        const res = await fetch(`/api/orders/${ORDER_ID}/attachments`, { method: 'POST', body: fd });
        const d = await res.json();
        return d.success ? { success: true, attachment: d.attachment } : d;
    };
    let putRes;
    try {
        putRes = await fetch(sess.upload_url, {
            method: 'PUT',
            headers: { 'Content-Type': file.type || 'application/octet-stream' },
            body: file
        });
    } catch (_) {
        return fallbackForm();
    }
    if (!putRes.ok) {
        return fallbackForm();
    }
    const completeRes = await fetch(`/api/orders/${ORDER_ID}/attachments/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            key: sess.key,
            filename: file.name,
            category: category,
            item_index: itemIndex == null ? null : itemIndex,
            size: file.size
        })
    });
    return await completeRes.json();
}

function erpResolveCommonAttachmentInput(source) {
    if (source && source.tagName === 'INPUT') {
        return source;
    }
    const shouldUseGalleryInput = !!(
        source &&
        source.getAttribute &&
        source.getAttribute('data-erp-common-attachment-gallery-trigger') === '1'
    );
    const galleryInput = shouldUseGalleryInput
        ? document.getElementById('erp-attachments-gallery-input')
        : null;
    return galleryInput || document.getElementById('erp-attachments-input');
}

function erpOpenCommonAttachmentPicker(input) {
    if (!input || typeof input.click !== 'function') return false;
    input.setAttribute('multiple', '');
    input.multiple = true;
    input.click();
    return true;
}

async function erpUploadSelectedAttachments(source) {
    if (!ERP_ORDER_ENABLED) return;
    const input = erpResolveCommonAttachmentInput(source);
    if (!input || !input.files || input.files.length === 0) {
        if (erpOpenCommonAttachmentPicker(input)) {
            return;
        }
        erpAttachmentsSetStatus('업로드할 파일을 선택하세요.', true);
        return;
    }
    const files = Array.from(input.files);
    await erpUploadCommonAttachmentFiles(files);
    input.value = '';
}

async function erpUploadCommonAttachmentFiles(files, options = {}) {
    if (!ERP_ORDER_ENABLED) return;
    if (!Array.isArray(files) || files.length === 0) {
        erpAttachmentsSetStatus('업로드할 파일을 선택하세요.', true);
        return;
    }
    const targetId = await erpRequireOrderIdOrWarn('첨부 업로드:');
    if (!targetId) {
        return;
    }
    const categoryEl = document.getElementById('erp-attachments-category');
    const category = erpNormalizeAttachmentCategory(categoryEl ? categoryEl.value : 'measurement');
    const statusVerb = options.statusVerb || '업로드';
    const doneVerb = options.doneVerb || '업로드 완료';

    let asLogId = null;
    let sortOrders = null;
    if (category === 'as') {
        if (typeof window.fomsEnsureAsUploadAnchor !== 'function') {
            erpAttachmentsSetStatus('AS 첨부 위치를 준비하지 못했습니다.', true);
            return;
        }
        try {
            const anchor = await window.fomsEnsureAsUploadAnchor(targetId);
            asLogId = anchor.asLogId;
            sortOrders = files.map(function (_file, index) { return anchor.nextSort + index; });
        } catch (err) {
            erpAttachmentsSetStatus(String((err && err.message) || err || 'AS 첨부 위치를 만들지 못했습니다.'), true);
            return;
        }
    }

    // --- Optimistic UI Start ---
    const galleryWrap = document.getElementById('erp-attachments-gallery');
    if (galleryWrap) {
        files.forEach((f, fi) => {
            const uniqueId = 'opt-ul-gen-' + Date.now() + '-' + fi;
            f._optId = uniqueId;
            const name = escapeHtml(f.name);
            let previewUrl = '';
            try { previewUrl = URL.createObjectURL(f); } catch (e) { }

            const isMobilePlaceholder = erpIsMobileAttachmentLayout();
            const isVideo = String(f.type || '').startsWith('video/');
            const placeholderHtml = isMobilePlaceholder ? `
<div id="${uniqueId}" class="erp-attachment-tile erp-attachment-tile--pending opacity-75">
    <div class="erp-attachment-tile__media ${isVideo ? 'erp-attachment-tile__media--video' : ''}">
        ${isVideo
                    ? `<i class="fas fa-video"></i><span class="erp-attachment-tile__type"><i class="fas fa-spinner fa-spin"></i></span>`
                    : `<img src="${previewUrl}" alt="${name}" style="filter:grayscale(80%);">`}
    </div>
    <span class="erp-attachment-tile__name">${name}</span>
    <span class="erp-attachment-tile__badge opt-pct">0%</span>
</div>` : `
<div id="${uniqueId}" class="col-md-4 col-sm-6 col-12 opacity-75">
<div class="card h-100 bg-light border-dashed">
    <div class="card-body p-2 d-flex flex-column align-items-center justify-content-center position-relative">
        <img src="${previewUrl}" class="rounded mb-2" style="width:100%;height:180px;object-fit:cover;filter:grayscale(80%);">
        <div class="spinner-border text-primary position-absolute" style="top:50%;left:50%;margin-top:-1rem;margin-left:-1rem;" role="status"></div>
        <div class="small text-truncate w-100 text-center" title="${name}">${name}</div>
        <div class="small text-primary fw-bold mt-1 opt-pct">0%</div>
    </div>
</div>
</div>`;
            // 상단에 임시 요소 추가 (append 대신 prepend에 가깝게 하려면)
            galleryWrap.insertAdjacentHTML('afterbegin', placeholderHtml);
        });
    }
    // --- Optimistic UI End ---

    erpAttachmentsSetStatus(`${statusVerb} 중... (${files.length}개)`);

    const progressWrap = document.getElementById('erp-attachments-progress');
    const progressBar = document.getElementById('erp-attachments-progress-bar');
    if (progressWrap) progressWrap.classList.remove('d-none');
    const totalFiles = files.length;

    let ok = 0;
    const uploadResult = await window.fomsUploadOrderAttachmentsBatch({
        orderId: ORDER_ID,
        files: files,
        folder: `orders/${ORDER_ID}/${category || 'attachments'}`,
        category: category,
        asLogId: asLogId,
        sortOrders: sortOrders,
        useDirectUpload: (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD),
        onPrepareProgress: function (info) {
            erpAttachmentsSetStatus(`이미지 최적화 중... (${info.done}/${info.total})`);
        },
        onUploadProgress: function (info) {
            if (progressBar) {
                const p = Math.round((info.done / totalFiles) * 100);
                progressBar.style.width = p + '%';
                progressBar.textContent = p + '%';
            }
        },
        onFileDone: function (info) {
            const el = document.getElementById(info.entry.originalFile._optId);
            if (el) {
                const pctSpan = el.querySelector('.opt-pct');
                if (pctSpan) pctSpan.textContent = info.result && info.result.success ? '완료' : '실패';
            }
        }
    });
    ok = uploadResult.ok;

    if (progressWrap) progressWrap.classList.add('d-none');
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }

    erpAttachmentsSetStatus(`${doneVerb}: ${ok}/${files.length}`);
    await erpLoadAttachments();
}

function erpBuildClipboardImageFilename(file, index) {
    const now = new Date();
    const stamp = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, '0'),
        String(now.getDate()).padStart(2, '0')
    ].join('') + '-' + [
        String(now.getHours()).padStart(2, '0'),
        String(now.getMinutes()).padStart(2, '0'),
        String(now.getSeconds()).padStart(2, '0')
    ].join('');
    const mime = String(file?.type || '').toLowerCase();
    const ext = mime === 'image/jpeg' ? 'jpg'
        : mime === 'image/webp' ? 'webp'
            : mime === 'image/gif' ? 'gif'
                : 'png';
    const suffix = index > 0 ? '-' + (index + 1) : '';
    return `capture-${stamp}${suffix}.${ext}`;
}

function erpGetClipboardImageFiles(event) {
    const items = event && event.clipboardData && event.clipboardData.items;
    if (!items || !items.length) return [];
    const files = [];
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (!item || item.kind !== 'file' || !String(item.type || '').startsWith('image/')) {
            continue;
        }
        const rawFile = item.getAsFile();
        if (!rawFile) continue;
        const type = rawFile.type || item.type || 'image/png';
        const name = erpBuildClipboardImageFilename({ type }, files.length);
        try {
            files.push(new File([rawFile], name, { type: type, lastModified: Date.now() }));
        } catch (_) {
            files.push(rawFile);
        }
    }
    return files;
}

function erpFindAttachmentPasteZone(target) {
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest('[data-erp-attachment-paste-zone]');
}

function erpSetAttachmentPasteZoneActive(zone, isActive) {
    if (!zone) return;
    zone.classList.toggle('border-primary', !!isActive);
    zone.classList.toggle('shadow-sm', !!isActive);
    zone.style.borderColor = isActive ? '#0d6efd' : '';
    zone.style.boxShadow = isActive ? '0 0 0 0.2rem rgba(13,110,253,0.18)' : '';
    zone.style.backgroundColor = isActive ? '#eef6ff' : '';
}

function erpAsReceiveOrderCtl() {
    const previewEl = document.getElementById('as-receive-preview');
    if (!previewEl || !window.fomsAsAttachmentOrder) return null;
    if (!previewEl._asOrder) {
        previewEl._asOrder = window.fomsAsAttachmentOrder.mount(previewEl, {
            onChange: function (files) {
                const filesEl = document.getElementById('as-receive-files');
                erpSetFileInputFiles(filesEl, files);
                window.__erpAsReceiveClipboardFiles = files.slice();
            }
        });
    }
    return previewEl._asOrder;
}

function erpRemoveAsReceiveFile(idx) {
    const ctl = erpAsReceiveOrderCtl();
    if (ctl) {
        const files = ctl.getFiles();
        files.splice(idx, 1);
        ctl.setFiles(files);
        return;
    }
    const filesEl = document.getElementById('as-receive-files');
    if (!filesEl) return;
    const files = Array.from(filesEl.files || []);
    files.splice(idx, 1);
    erpSetFileInputFiles(filesEl, files);
    erpRenderAsReceiveFilePreview(files);
}

function erpRenderAsReceiveFilePreview(files) {
    const ctl = erpAsReceiveOrderCtl();
    if (ctl) {
        ctl.setFiles(Array.isArray(files) ? files : []);
        return;
    }
    const previewEl = document.getElementById('as-receive-preview');
    if (!previewEl) return;
    const AS_VIDEO_SIZE_WARN = 10 * 1024 * 1024;
    (previewEl._objectUrls || []).forEach(function (u) { try { URL.revokeObjectURL(u); } catch (_) {} });
    previewEl._objectUrls = [];
    previewEl.innerHTML = '';
    (Array.isArray(files) ? files : []).forEach(function (f, idx) {
        const isImage = (f.type || '').startsWith('image/');
        const isVideo = (f.type || '').startsWith('video/');
        const isSizeWarn = isVideo && f.size > AS_VIDEO_SIZE_WARN;
        let thumbHtml = '';
        if (isImage) {
            const objUrl = URL.createObjectURL(f);
            previewEl._objectUrls.push(objUrl);
            thumbHtml = `<img src="${objUrl}" class="img-fluid rounded as-attach-order-fallback-img" alt="">`;
        } else if (isVideo) {
            thumbHtml = `<div class="d-flex align-items-center justify-content-center bg-dark rounded as-attach-order-fallback-box">
                <i class="fas fa-video text-white"></i></div>`;
        } else {
            thumbHtml = `<div class="d-flex align-items-center justify-content-center bg-light rounded as-attach-order-fallback-box">
                <i class="fas fa-file text-secondary"></i></div>`;
        }
        const col = document.createElement('div');
        col.className = 'col-6 col-sm-4 col-md-3';
        col.innerHTML = `<div class="card h-100">
            <div class="card-body p-2">
                ${thumbHtml}
                ${isSizeWarn ? '<div class="small text-warning mt-1">10MB 초과 - 지연 가능</div>' : ''}
                <div class="d-flex justify-content-between align-items-center mt-1">
                    <div class="small text-truncate" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
                    <button type="button" class="btn btn-outline-danger btn-sm py-0 px-1" data-idx="${idx}" title="삭제">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div></div>`;
        col.querySelector('[data-idx]').addEventListener('click', function () {
            erpRemoveAsReceiveFile(parseInt(this.getAttribute('data-idx'), 10));
        });
        previewEl.appendChild(col);
    });
}

function erpSetFileInputFiles(input, files) {
    if (!input || typeof DataTransfer !== 'function') return false;
    const dt = new DataTransfer();
    (Array.isArray(files) ? files : []).forEach(function (file) {
        dt.items.add(file);
    });
    input.files = dt.files;
    return true;
}

window.erpAppendAsReceiveFiles = erpAppendAsReceiveFiles;

function erpAppendAsReceiveFiles(files) {
    const ctl = erpAsReceiveOrderCtl();
    if (ctl) {
        ctl.addFiles(files || []);
        return;
    }
    const filesEl = document.getElementById('as-receive-files');
    if (!filesEl) {
        erpAttachmentsSetStatus('AS 첨부 입력 영역을 찾지 못했습니다.', true);
        return;
    }
    const mergedFiles = Array.from(filesEl.files || []).concat(files || []);
    if (erpSetFileInputFiles(filesEl, mergedFiles)) {
        window.__erpAsReceiveClipboardFiles = [];
        filesEl.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
        window.__erpAsReceiveClipboardFiles = mergedFiles;
        erpRenderAsReceiveFilePreview(mergedFiles);
    }
}

async function erpHandleAttachmentPaste(event) {
    const zone = erpFindAttachmentPasteZone(event.target) || erpFindAttachmentPasteZone(document.activeElement);
    if (!zone) return;
    const files = erpGetClipboardImageFiles(event);
    if (!files.length) return;
    event.preventDefault();
    if (zone.getAttribute('data-erp-attachment-paste-zone') === 'item') {
        const row = zone.closest('.erp-item-row');
        const rows = Array.from(document.querySelectorAll('.erp-item-row'));
        const itemIndex = row ? rows.indexOf(row) : -1;
        if (itemIndex < 0) {
            erpAttachmentsSetStatus('붙여넣을 제품 항목을 찾지 못했습니다.', true);
            return;
        }
        await erpUploadItemAttachments(itemIndex, files);
        return;
    }
    if (zone.getAttribute('data-erp-attachment-paste-zone') === 'as-receive') {
        erpAppendAsReceiveFiles(files);
        return;
    }
    await erpUploadCommonAttachmentFiles(files, {
        statusVerb: '붙여넣은 이미지 업로드',
        doneVerb: '붙여넣은 이미지 업로드 완료'
    });
}

// =====================================================
// AS접수 모달 클립보드 이미지 붙여넣기 (전면 재설계)
// =====================================================
// 설계 원칙
//   1) #asReceiveModal은 #erp-order DOM 바깥(sibling) → root paste 핸들러 불가
//   2) paste는 DOM 조상 체인을 따라 버블링 → focus가 modal 안에 있어야 modal 리스너 발화
//   3) document 레벨 paste 금지(테스트 계약: scoped only)
//
// 4중 focus 안전망 — focus를 zone에 공격적으로 강제하여 paste 수신 보장
//   [A] shown.bs.modal           → zone.focus()
//   [B] fileInput.mousedown      → preventDefault (포커스 이탈 차단)
//   [C] fileInput.click          → setTimeout으로 다이얼로그 종료 후 zone 재포커스
//   [D] modal.click (비입력)     → zone 재포커스 (백드롭/빈영역 클릭 대응)
//
// paste 흐름
//   Ctrl+V → focus한 element(보장: zone 또는 modal 내부)에서 paste fire
//   → modal로 버블링 → 핸들러가 image item 추출 → erpAppendAsReceiveFiles
//   textarea/text input에 focus한 경우는 early return → 일반 텍스트 붙여넣기 정상 동작
function erpBindAsReceiveModalPaste() {
    const modal = document.getElementById('asReceiveModal');
    if (!modal || modal._erpAsReceivePasteBound) return;
    modal._erpAsReceivePasteBound = true;

    const zone = modal.querySelector('[data-erp-attachment-paste-zone="as-receive"]');
    const fileInput = modal.querySelector('#as-receive-files');
    if (!zone) return;

    const focusZone = function () {
        if (!modal.classList.contains('show')) return;
        try { zone.focus({ preventScroll: true }); } catch (_) { zone.focus(); }
    };

    // [A] 모달 열림 → zone 자동 포커스
    modal.addEventListener('shown.bs.modal', focusZone);

    // [B][C] 파일 인풋 포커스 이탈 차단 + 다이얼로그 종료 후 zone 복귀
    if (fileInput) {
        fileInput.addEventListener('mousedown', function (e) { e.preventDefault(); });
        fileInput.addEventListener('click', function () {
            setTimeout(focusZone, 250);
        });
    }

    // [D] 모달 빈 영역 클릭 → zone 재포커스 (입력 요소는 제외)
    modal.addEventListener('click', function (event) {
        const tgt = event.target;
        if (!tgt) return;
        if (tgt.closest('textarea,input,button,a,select,[data-bs-dismiss],[role="button"]')) return;
        focusZone();
    });

    // Modal-scoped paste 리스너 (document 레벨 아님 → 테스트 계약 충족)
    modal.addEventListener('paste', function (event) {
        const ae = document.activeElement;
        if (ae) {
            const tag = ae.tagName;
            const type = (ae.type || '').toLowerCase();
            // 텍스트 입력 영역에서는 일반 텍스트 붙여넣기 허용
            if (tag === 'TEXTAREA' || (tag === 'INPUT' && type !== 'file')) return;
        }
        const files = erpGetClipboardImageFiles(event);
        if (!files.length) return;
        event.preventDefault();
        event.stopPropagation();
        erpAppendAsReceiveFiles(files);
        erpSetAttachmentPasteZoneActive(zone, true);
        setTimeout(function () { erpSetAttachmentPasteZoneActive(zone, false); }, 800);
    });

    // Zone 포커스 시각 피드백
    zone.addEventListener('focus', function () { erpSetAttachmentPasteZoneActive(zone, true); });
    zone.addEventListener('blur', function () { erpSetAttachmentPasteZoneActive(zone, false); });
}

function erpBindAttachmentPasteUpload() {
    const root = document.getElementById('erp-order');
    if (!root || root._erpPasteUploadBound) return;
    root._erpPasteUploadBound = true;
    root.addEventListener('paste', erpHandleAttachmentPaste);
    root.addEventListener('click', function (event) {
        const zone = erpFindAttachmentPasteZone(event.target);
        if (!zone || (event.target && event.target.closest('button,a,input,select,textarea'))) return;
        try { zone.focus({ preventScroll: true }); } catch (_) { zone.focus(); }
    });
    root.addEventListener('focusin', function (event) {
        const zone = erpFindAttachmentPasteZone(event.target);
        if (zone) erpSetAttachmentPasteZoneActive(zone, true);
    });
    root.addEventListener('focusout', function (event) {
        const zone = erpFindAttachmentPasteZone(event.target);
        if (zone) erpSetAttachmentPasteZoneActive(zone, false);
    });
    erpBindAsReceiveModalPaste();
}

async function erpDeleteAttachment(attachmentId) {
    if (!confirm('첨부파일을 삭제할까요?')) return;
    try {
        const res = await fetch(`/api/orders/${ORDER_ID}/attachments/${attachmentId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) throw new Error(data.message || '삭제 실패');
        erpAttachmentsSetStatus('삭제 완료');
        await erpLoadAttachments();
    } catch (e) {
        console.error(e);
        erpAttachmentsSetStatus(String(e?.message || e), true);
    }
}

// ============================================
// ERP Order: Text Conversion (기존주문 변환)
// ============================================
function erpHasConversionTextValue(value) {
    return String(value ?? '').trim().length > 0;
}

function erpAppendConversionTextLine(text, label, value) {
    const raw = String(value ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const trimmed = raw.trim();
    if (!trimmed) return text;
    if (!trimmed.includes('\n')) {
        return text + `${label} : ${trimmed}\n`;
    }
    const lines = trimmed.split('\n');
    let out = text + `${label} : ${(lines[0] || '').trim()}\n`;
    for (let i = 1; i < lines.length; i += 1) {
        const line = lines[i].trim();
        if (line) out += `${line}\n`;
    }
    return out;
}

function erpAppendConversionExtraInputLine(text, value) {
    const raw = String(value ?? '').trim();
    if (!raw) return text;
    const lines = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const first = (lines[0] || '').trim();
    if (!first) return text;
    let out = text + `추가 입력 : ${first}\n`;
    for (let i = 1; i < lines.length; i += 1) {
        const line = lines[i].trim();
        if (line) out += `${line}\n`;
    }
    return out;
}

function erpAppendConversionFreeInputBlock(text, value) {
    const formatted = erpFormatFreeInputForConversion(value);
    if (!formatted) return text;
    const withSuffix = formatted
        .split('\n')
        .map(function (line) { return line ? `${line}(총견적 포함)` : line; })
        .join('\n');
    return text + `${withSuffix}\n`;
}

function erpReadItemFieldValue(row, key) {
    if (!row || !key) return '';
    const el = row.querySelector(`:scope [data-erp="${key}"]`);
    return el ? String(el.value || '') : '';
}

function erpAppendConversionMoneyLine(text, label, amount, suffix) {
    const n = erpCoerceAmount(amount);
    if (n <= 0) return text;
    const tail = suffix ? String(suffix) : '';
    return text + `${label} : ${erpFormatMoneyKRW(n)}${tail}\n`;
}

var _erpIsBalancePaymentConfirmed =
    window._erpIsBalancePaymentConfirmed ||
    function _erpIsBalancePaymentConfirmed() {
        var btn = document.querySelector(
            '.erp-payment-confirm-btn[data-payment-type="balance"]'
        );
        if (btn) {
            if (btn.dataset.confirmed === '1') return true;
            var icon = btn.querySelector('img.erp-custom-payment-icon');
            if (icon && icon.classList.contains('erp-custom-payment-confirmed')) return true;
        }
        var pay = window.__erpLastStructuredData && window.__erpLastStructuredData.payment;
        return _erpBoolConfirmed(pay && pay.balance_confirmed);
    };
window._erpIsBalancePaymentConfirmed = _erpIsBalancePaymentConfirmed;

function erpSliceConversionTextForChannelPush(text) {
    const raw = String(text ?? '').trim();
    if (!raw) return '';
    // 라홈시스템(factory2) ★★는 채널톡에도 유지.
    // 실측일/시간 헤더만 제거 — 실측 특이사항·주소/연락처 특이사항은 유지.
    const hasFactory2Stars = raw.split('\n').some((line) => /^\s*★★\s*$/.test(line));
    const body = raw
        .split('\n')
        .filter((line) => !/^\s*★★\s*$/.test(line) && !/^\s*실측일\s*:/.test(line) && !/^\s*시\s*간\s*:/.test(line))
        .join('\n')
        .replace(/^\n+/, '')
        .trim();
    if (!hasFactory2Stars) return body;
    if (!body) return '★★';
    return `★★\n${body}`;
}

/**
 * ISO 날짜(YYYY-MM-DD, 콤마 다중 허용)를 변환/푸시 공통 한글 포맷으로 바꾼다.
 * 변환 텍스트와 AS PUSH 본문이 같은 표기(`8월 14일`)를 쓰도록 하는 SSOT.
 *
 * @param {string} dateStr 'YYYY-MM-DD' 또는 콤마로 이어진 다중 날짜
 * @returns {string} '8월 14일' 형태(파싱 실패 시 원문 그대로)
 */
function erpFormatConversionDateToKorean(dateStr) {
    if (!dateStr) return '';
    const single = (s) => {
        const t = String(s).trim();
        const match = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (match) {
            const m = parseInt(match[2], 10);
            const d = parseInt(match[3], 10);
            return `${m}월 ${d}일`;
        }
        return t || '';
    };
    const parts = String(dateStr).split(',').map(s => single(s)).filter(Boolean);
    return parts.length ? parts.join(', ') : dateStr;
}

function erpGenerateConversionText() {
    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? (el.value || '').trim() : '';
    };

    const formatDateToKorean = erpFormatConversionDateToKorean;

    let measurementDate = getVal('erp-measurement-date');
    measurementDate = formatDateToKorean(measurementDate);

    // 시간: select가 직접입력이면 input 값 사용
    const measurementTime = erpReadScheduleTimeValue('erp-measurement-time-select', 'erp-measurement-time');

    const customerName = getVal('erp-customer-name');
    let orderer = typeof getOrdererValue === 'function' ? getOrdererValue() : getVal('erp-orderer');
    if (!orderer) orderer = '라홈'; // Default

    let constructionDate = getVal('erp-construction-date');
    if (!constructionDate) constructionDate = '상담'; // Default
    else constructionDate = formatDateToKorean(constructionDate);

    const constructionTime = erpReadScheduleTimeValue('erp-construction-time-select', 'erp-construction-time');

    const address = getVal('erp-address');
    const phone = getVal('erp-customer-phone');
    const factory2Checked = !!document.getElementById('erp-factory2')?.checked;

    // Header + customer (값 없는 라인은 제외)
    // 라홈시스템(factory2) 체크 시 실측일 위에 ★★ 표기
    let text = '';
    if (factory2Checked) text += '★★\n';
    text = erpAppendConversionTextLine(text, '실측일', measurementDate);
    text = erpAppendConversionTextLine(text, '시   간', measurementTime);
    // 실측 특이사항 → 실측 블록(실측일/시간) 바로 아래
    text = erpAppendConversionTextLine(text, '실측 특이사항', getVal('erp-measurement-note'));
    if (text) text += '\n';
    text = erpAppendConversionTextLine(text, '고객명', customerName);
    text = erpAppendConversionTextLine(text, '발주사', orderer);
    text = erpAppendConversionTextLine(text, '시공일', constructionDate);
    // 시공 특이사항 → 시공일 바로 아래 (변환·채널톡 PUSH 공통 텍스트)
    text = erpAppendConversionTextLine(text, '시공 특이사항', getVal('erp-construction-note'));
    text = erpAppendConversionTextLine(text, '시공시간', constructionTime);
    text = erpAppendConversionTextLine(text, '주  소', address);
    // 주소 특이사항 → 주소 바로 아래
    text = erpAppendConversionTextLine(text, '주소 특이사항', getVal('erp-address-note'));
    text = erpAppendConversionTextLine(text, '연락처', phone);
    // 연락처 특이사항 → 연락처 바로 아래
    text = erpAppendConversionTextLine(text, '연락처 특이사항', getVal('erp-phone-note'));
    if (text && !text.endsWith('\n\n')) text += '\n';

    // Items
    const rows = erpGetItemRows();
    const itemCount = rows.length;
    let visibleItemIndex = 0;

    rows.forEach((row) => {
        const getRowVal = (key) => erpReadItemFieldValue(row, key);

        const extraInput = getRowVal('extra_input');

        const pName = getRowVal('product_name');
        // Spec: 다중 행 수집 (W합/표시용은 출고 대시보드에서 처리)
        const rawSpec = getRowVal('spec');
        const specParts = [];
        row.querySelectorAll('.erp-spec-row').forEach(sr => {
            const w = (sr.querySelector('[data-erp="spec_width"]')?.value ?? '').trim();
            const d = (sr.querySelector('[data-erp="spec_depth"]')?.value ?? '').trim();
            const h = (sr.querySelector('[data-erp="spec_height"]')?.value ?? '').trim();
            const one = [w, d, h].filter(Boolean).join('*');
            if (one) specParts.push(one);
        });
        const spec = rawSpec || (specParts.length ? specParts.join(', ') : '');

        const internal = getRowVal('internal');
        const color = getRowVal('color');
        const option = getRowVal('option_detail');
        const handle = getRowVal('handle');
        const misc = getRowVal('misc');
        const itemPrice = getRowVal('price');

        let itemText = '';
        itemText = erpAppendConversionTextLine(itemText, '제품명', pName);
        itemText = erpAppendConversionTextLine(itemText, '규 격', spec);
        itemText = erpAppendConversionTextLine(itemText, '내 부', internal);
        itemText = erpAppendConversionTextLine(itemText, '색 상', color);
        itemText = erpAppendConversionTextLine(itemText, '옵 션', option);
        itemText = erpAppendConversionTextLine(itemText, '손잡이', handle);
        itemText = erpAppendConversionTextLine(itemText, '기 타', misc);
        itemText = erpAppendConversionMoneyLine(itemText, '항목 견적', itemPrice);
        itemText = erpAppendConversionExtraInputLine(itemText, extraInput);
        if (!itemText) return;

        visibleItemIndex += 1;
        if (itemCount >= 2) {
            text += `${visibleItemIndex}.\n`;
        }
        text += itemText;
        text += '\n';
    });

    // Footer: 채널톡/발주방 공유용 고정 포맷 (담당자 + 출고가 + 예약금 + 배송 + 잔금)
    const manager = getVal('erp-manager');
    const itemsTotal = erpSumItemsSubtotal();
    const depositAmount = erpParseDepositValue();
    const discountAmount = erpParseDiscountValue();
    const totals = erpBuildTotals(itemsTotal, depositAmount, discountAmount, erpParseFreeInputAmount());
    const freeInputVal = erpParseFreeInputText();

    const footerStart = text.length;
    text = erpAppendConversionTextLine(text, '담당자', manager);
    if (text.length > footerStart) text += '\n';
    text = erpAppendConversionMoneyLine(text, '출고가', totals.shipping_price);
    text = erpAppendConversionMoneyLine(text, '예약금(선금)', totals.deposit_amount);
    text = erpAppendConversionFreeInputBlock(text, freeInputVal);
    const balanceSuffix = _erpIsBalancePaymentConfirmed() ? '(결제 완)' : '';
    text = erpAppendConversionMoneyLine(text, '잔금', totals.final_amount, balanceSuffix);
    const balanceNoteVal = getVal('erp-balance-note');
    text = erpAppendConversionTextLine(text, '잔금메모', balanceNoteVal);
    const cashReceiptVal = getVal('erp-cash-receipt');
    if (erpHasConversionTextValue(cashReceiptVal) && totals.final_amount > 0) {
        text += '\n';
    }
    text = erpAppendConversionTextLine(text, '현금영수증', cashReceiptVal);
    text = text.replace(/\n+$/, '');

    const textarea = document.getElementById('erp-conversion-text');
    if (textarea) {
        textarea.value = text;
        adjustTextareaHeight(textarea); // Auto-resize if helper exists
    }
}

function erpCopyToClipboard() {
    const textarea = document.getElementById('erp-conversion-text');
    if (!textarea || !textarea.value) return;

    textarea.select();
    textarea.setSelectionRange(0, 99999); // Mobile compatibility

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textarea.value).then(() => {
            alert('텍스트가 복사되었습니다.');
        }).catch(err => {
            console.error('Clipboard API 실패, execCommand 시도:', err);
            try {
                const successful = document.execCommand('copy');
                if (successful) alert('텍스트가 복사되었습니다.');
                else alert('복사에 실패했습니다. 수동으로 복사해주세요.');
            } catch (e) {
                alert('복사에 실패했습니다. 수동으로 복사해주세요.');
            }
        });
    } else {
        try {
            const successful = document.execCommand('copy');
            if (successful) alert('텍스트가 복사되었습니다.');
            else alert('복사에 실패했습니다. 수동으로 복사해주세요.');
        } catch (err) {
            console.error('Copy failed:', err);
            alert('복사에 실패했습니다. 수동으로 복사해주세요.');
        }
    }
}

// ============================================
// ERP Order: 실측 일정 미러링 패널 (14일, 30초 갱신, 클릭 시 실측일 입력)
// ============================================
function renderMeasurementSchedulerCountBadges(item) {
    const total = Number(item.count) || 0;
    const regional = Number(item.count_regional) || 0;
    const metro = Number(item.count_metro) || 0;
    return (
        '<span class="erp-scheduler-count-group" aria-label="실측 전체 ' + total + ', 지방 ' + regional + ', 수도권 ' + metro + '">' +
        '<span class="badge badge-count erp-scheduler-count erp-scheduler-count--total" title="전체">' + total + '</span>' +
        '<span class="badge badge-count erp-scheduler-count erp-scheduler-count--regional" title="지방">' + regional + '</span>' +
        '<span class="badge badge-count erp-scheduler-count erp-scheduler-count--metro" title="수도권">' + metro + '</span>' +
        '</span>'
    );
}
window.renderMeasurementSchedulerCountBadges = renderMeasurementSchedulerCountBadges;

/**
 * 실측 일정 패널의 날짜별 건 목록 모달을 생성(최초 1회)하고 반환한다.
 * 패널 카드 안에서 펼치면 컨테이너 폭에 눌려 읽기 어려워 body 직속 모달로 띄운다.
 * @returns {HTMLElement} 모달 루트 엘리먼트
 */
function getMeasurementDayModal() {
    let modal = document.getElementById('erp-measurement-day-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'erp-measurement-day-modal';
    modal.className = 'erp-measure-day-modal';
    modal.hidden = true;
    modal.innerHTML =
        '<div class="erp-measure-day-modal__backdrop" data-erp-measure-day-close="1"></div>' +
        '<div class="erp-measure-day-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="erp-measure-day-modal-title">' +
        '<div class="erp-measure-day-modal__header">' +
        '<div class="erp-measure-day-modal__title" id="erp-measure-day-modal-title"></div>' +
        '<button type="button" class="btn-close" aria-label="닫기" data-erp-measure-day-close="1"></button>' +
        '</div>' +
        '<div class="erp-measure-day-modal__body"></div>' +
        '</div>';
    document.body.appendChild(modal);
    modal.addEventListener('click', function (e) {
        // 빈 곳(백드롭) 또는 닫기 버튼 클릭 시 닫는다.
        if (e.target.closest('[data-erp-measure-day-close]')) closeMeasurementDayModal();
    });
    return modal;
}

/**
 * 실측 일정 모달을 닫는다.
 * @returns {void}
 */
function closeMeasurementDayModal() {
    const modal = document.getElementById('erp-measurement-day-modal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('erp-measure-day-modal-open');
    document.removeEventListener('keydown', handleMeasurementDayModalKeydown, true);
}
window.closeMeasurementDayModal = closeMeasurementDayModal;

/**
 * 모달 열림 중 ESC 키 처리.
 * @param {KeyboardEvent} e 키 이벤트
 * @returns {void}
 */
function handleMeasurementDayModalKeydown(e) {
    if (e.key === 'Escape' || e.key === 'Esc') {
        e.stopPropagation();
        closeMeasurementDayModal();
    }
}

/**
 * 실측 일정 모달을 화면 정중앙에 띄운다(주변은 블러 처리).
 * @param {{date: string, dayLabel: string, countsHtml: string, bodyHtml: string}} payload 표시 내용
 * @returns {void}
 */
function openMeasurementDayModal(payload) {
    const modal = getMeasurementDayModal();
    const title = modal.querySelector('.erp-measure-day-modal__title');
    const body = modal.querySelector('.erp-measure-day-modal__body');
    if (title) {
        title.innerHTML =
            '<span class="erp-measure-day-modal__date">' + escapeHtml(payload.date || '') + '</span>' +
            '<span class="erp-measure-day-modal__day">' + escapeHtml(payload.dayLabel || '') + '</span>' +
            (payload.countsHtml || '');
    }
    if (body) body.innerHTML = payload.bodyHtml || '';
    modal.hidden = false;
    document.body.classList.add('erp-measure-day-modal-open');
    document.addEventListener('keydown', handleMeasurementDayModalKeydown, true);
    const closeBtn = modal.querySelector('.btn-close');
    if (closeBtn) closeBtn.focus();
}
window.openMeasurementDayModal = openMeasurementDayModal;

async function loadMeasurementPanel() {
    const panel = document.getElementById('erp-order-measurement-panel');
    if (!panel) return;
    try {
        const url = '/api/erp/measurement/summary';
        const res = await fetch(url);
        const data = await res.json();
        if (!data || !data.success || !Array.isArray(data.panel_dates)) {
            panel.innerHTML = '<div class="small text-muted py-2">데이터를 불러올 수 없습니다.</div>';
            return;
        }
        let selectedDate = (panel.dataset.selectedDate || '').trim();
        if (!selectedDate && window._erpMeasurementDatePicker && window._erpMeasurementDatePicker.selectedDates && window._erpMeasurementDatePicker.selectedDates.length > 0) {
            const d = window._erpMeasurementDatePicker.selectedDates[0];
            selectedDate = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        }
        let html = '';
        data.panel_dates.forEach(function (item) {
            const klasses = ['measurement-panel-item', 'measurement-panel-item-oneline'];
            if (item.is_weekend) klasses.push('is-weekend');
            if (item.is_holiday) klasses.push('is-holiday');
            if (item.is_today) klasses.push('is-today');
            if (item.date === selectedDate) klasses.push('is-selected');
            const badges = [];
            if (item.is_holiday) badges.push('<span class="badge bg-danger">휴일</span>');
            else if (item.is_weekend) badges.push('<span class="badge bg-warning text-dark">주말</span>');
            html += '<div class="' + klasses.join(' ') + '" data-date="' + escapeHtml(item.date) + '">';
            html += '<div class="erp-scheduler-panel-row" role="button" tabindex="0">';
            html += '<span class="measurement-panel-date">' + escapeHtml(item.date) + '</span>';
            html += '<span class="measurement-panel-day">(' + escapeHtml(item.day_label) + ')</span>';
            html += badges.join('');
            html += renderMeasurementSchedulerCountBadges(item);
            html += '</div>';
            
            if (item.cases && item.cases.length > 0) {
                html += '<div class="measurement-cases-list d-none mt-2 pt-2 border-top">';
                // 서버가 지역(시/도·시군구) 묶음 → 방문시각 이른 순으로 내려준다.
                // 같은 지역 구간의 첫 건 앞에 지역 제목을 넣어 묶음이 눈에 보이게 한다.
                const regionCounts = {};
                const scopeCounts = {};
                item.cases.forEach(function (c) {
                    const key = c.region_label || '지역 미상';
                    regionCounts[key] = (regionCounts[key] || 0) + 1;
                    const scope = c.scope_label || '수도권';
                    scopeCounts[scope] = (scopeCounts[scope] || 0) + 1;
                });
                let lastRegion = null;
                let lastScope = null;
                item.cases.forEach(function(c) {
                    const scope = c.scope_label || '수도권';
                    if (scope !== lastScope) {
                        lastScope = scope;
                        // 권역 색점은 패널 건수 뱃지 범례(지방=주황, 수도권=초록)와 같은 규약.
                        const scopeMod = scope === '지방' ? 'regional' : 'metro';
                        html += '<div class="erp-measure-day-scope erp-measure-day-scope--' + scopeMod + '">' +
                            escapeHtml(scope) +
                            '<span class="erp-measure-day-scope__count">' + scopeCounts[scope] + '건</span></div>';
                    }
                    const region = c.region_label || '지역 미상';
                    if (region !== lastRegion) {
                        lastRegion = region;
                        html += '<div class="erp-measure-day-region">' + escapeHtml(region) +
                            '<span class="erp-measure-day-region__count">' + regionCounts[region] + '건</span></div>';
                    }
                    const t = escapeHtml(c.time || '');
                    const n = escapeHtml(c.customer_name || '이름없음');
                    const a = escapeHtml(c.address || '-');
                    const timeBadge = t
                        ? `<span class="erp-measure-day-time">${t}</span>`
                        : '<span class="erp-measure-day-time erp-measure-day-time--unknown">시간미정</span>';
                    // 시각 뱃지 폭이 문구마다 달라도 이름·주소 왼쪽선이 흔들리지 않도록
                    // 래퍼 없이 grid 셀 3개로 배치한다(CSS: auto 1fr 2행).
                    html += `<div class="erp-measure-day-case">${timeBadge}` +
                        `<span class="erp-measure-day-case__name">${n}</span>` +
                        `<span class="erp-measure-day-case__addr">${a}</span>` +
                        `</div>`;
                });
                html += '</div>';
            }
            
            html += '</div>';
        });
        panel.innerHTML = html;
        panel.classList.add('measurement-panel-list');
        panel.querySelectorAll('.measurement-panel-item').forEach(function (el) {
            const header = el.querySelector('.erp-scheduler-panel-row');
            if (header) {
                const openDay = function () {
                    const dateStr = el.dataset.date;
                    if (!dateStr) return;

                    // 어느 날짜를 눌렀는지 패널에서도 보이도록 선택 표시를 유지한다.
                    panel.querySelectorAll('.measurement-panel-item').forEach(function (x) { x.classList.remove('is-selected'); });
                    el.classList.add('is-selected');

                    // 목록은 카드 폭에 눌리지 않도록 화면 정중앙 모달로 띄운다.
                    const casesList = el.querySelector('.measurement-cases-list');
                    const dayEl = el.querySelector('.measurement-panel-day');
                    const countsEl = el.querySelector('.erp-scheduler-count-group');
                    openMeasurementDayModal({
                        date: dateStr,
                        dayLabel: dayEl ? dayEl.textContent.trim() : '',
                        countsHtml: countsEl ? countsEl.outerHTML : '',
                        bodyHtml: casesList
                            ? casesList.innerHTML
                            : '<div class="small text-muted py-2 text-center">해당 날짜에 실측 건이 없습니다.</div>'
                    });
                };
                header.addEventListener('click', openDay);
                header.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openDay();
                    }
                });
            }
        });
    } catch (e) {
        console.error('loadMeasurementPanel:', e);
        panel.innerHTML = '<div class="small text-danger py-2">로드 실패</div>';
    }
}
window.loadMeasurementPanel = loadMeasurementPanel;

/**
 * ERP shell and full-document paths now mount from the same DOM config contract.
 */
function getErpOrderConfigElement() {
    return (
        document.getElementById("erp-order-config") ||
        document.querySelector("#main-content #erp-order-config") ||
        document.querySelector("[data-erp-order-enabled]")
    );
}

function setErpOrderEnabled(nextEnabled) {
    ERP_ORDER_ENABLED = !!nextEnabled;
    window.ERP_ORDER_ENABLED = ERP_ORDER_ENABLED;
}

function isErpOrderDraftMode() {
    return !!window.__ERP_ORDER_DRAFT_MODE;
}
window.isErpOrderDraftMode = isErpOrderDraftMode;

function setErpOrderDraftMode(nextDraftMode) {
    const next = !!nextDraftMode;
    window.__ERP_ORDER_DRAFT_MODE = next;
}

function syncErpOrderGlobalsFromDom() {
    var config = getErpOrderConfigElement();
    if (!config) {
        return false;
    }
    var hostCard =
        config.closest(".card[data-order-id]") ||
        document.querySelector("#main-content .card[data-order-id]") ||
        document.querySelector(".card[data-order-id]");
    var orderIdRaw =
        config.getAttribute("data-order-id") ||
        config.getAttribute("data-erp-order-id") ||
        (hostCard ? hostCard.getAttribute("data-order-id") : "0");
    var enabledRaw =
        config.getAttribute("data-erp-order-enabled") ||
        (hostCard ? hostCard.getAttribute("data-erp-order-enabled") : null);
    var directUploadRaw = config.getAttribute("data-use-direct-upload");
    var draftModeRaw = config.getAttribute("data-erp-order-draft-mode");
    var oid = parseInt(String(orderIdRaw || "0"), 10) || 0;

    if (enabledRaw === "true" || enabledRaw === "false") {
        setErpOrderEnabled(enabledRaw === "true");
    }
    if (directUploadRaw === "true" || directUploadRaw === "false") {
        window.USE_DIRECT_UPLOAD = directUploadRaw === "true";
        try {
            USE_DIRECT_UPLOAD = window.USE_DIRECT_UPLOAD;
        } catch (e) {}
    }
    if (draftModeRaw === "true" || draftModeRaw === "false") {
        setErpOrderDraftMode(draftModeRaw === "true");
    }

    ORDER_ID = oid;
    window.ORDER_ID = ORDER_ID;
    return true;
}
window.syncErpOrderGlobalsFromDom = syncErpOrderGlobalsFromDom;
window.fomsErpSyncEditGlobalsFromDom = syncErpOrderGlobalsFromDom;

function _erpMarkSurfaceReady() {
    // 시각 cloak(`[data-erp-surface]:not([data-erp-ready])`) 해제 — 1회성 래치.
    // `#erp-order` 탭 pane이 정식 cloak 대상이며, 초기 부트스트랩 적용/비적용
    // 경로 모두에서 반드시 호출돼야 사용자가 빈 화면에 머무르지 않는다.
    var pane = document.getElementById("erp-order");
    if (pane && !pane.dataset.erpReady) {
        pane.dataset.erpReady = "1";
    }
}
window._fomsMarkErpSurfaceReady = _erpMarkSurfaceReady;

function _erpLoadDeferredSurfaceDecorations() {
    if (!ERP_ORDER_ENABLED || !ORDER_ID) {
        return;
    }
    if (typeof erpLoadQuest === 'function') {
        void erpLoadQuest();
    }
    if (typeof erpLoadAttachments === 'function') {
        void (async () => {
            await erpLoadAttachments();
            if (typeof erpRenderItemAttachmentPanels === 'function') {
                erpRenderItemAttachmentPanels();
            }
        })();
    }
}

function _erpYieldForFirstPaint() {
    return new Promise(function (resolve) {
        if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
            window.requestAnimationFrame(function () {
                window.requestAnimationFrame(resolve);
            });
            return;
        }
        window.setTimeout(resolve, 0);
    });
}

function fomsMountErpOrderSurface() {
    var config = getErpOrderConfigElement();
    if (!config) {
        _erpMarkSurfaceReady();
        return;
    }
    syncErpOrderGlobalsFromDom();
    if (!ERP_ORDER_ENABLED) {
        _erpMarkSurfaceReady();
        return;
    }

    var mountRoot = document.getElementById("erp-order") || config;
    if (mountRoot.dataset.erpOrderMounted === "1") {
        _erpMarkSurfaceReady();
        return;
    }
    mountRoot.dataset.erpOrderMounted = "1";
    if (typeof erpMountChannelPushResendModal === 'function') {
        erpMountChannelPushResendModal();
    }
    erpBindReceivedTimeControl();
    erpBindScheduleTimeControl('erp-measurement-time-select', 'erp-measurement-time');
    erpBindScheduleTimeControl('erp-construction-time-select', 'erp-construction-time');
    erpBindUrgentReasonControl();
    erpBindAutosizeTextareas(mountRoot);

    // 실패/예외 경로에서도 surface가 영구 hidden으로 남지 않도록 최후 failsafe.
    var _erpReadyFailsafeId = window.setTimeout(_erpMarkSurfaceReady, 3000);

    // 여러 날짜 선택(multiple) 달력은 자동으로 닫히지 않으므로, 빈 곳 클릭 없이
    // 한 번에 닫을 수 있도록 달력 하단에 '확인' 버튼을 주입한다.
    function erpAddFlatpickrDoneButton(instance) {
        if (!instance || !instance.calendarContainer) return;
        if (instance.calendarContainer.querySelector('.erp-fp-done-bar')) return;
        if (!document.getElementById('erp-fp-done-style')) {
            const st = document.createElement('style');
            st.id = 'erp-fp-done-style';
            st.textContent =
                '.flatpickr-calendar .erp-fp-done-bar{display:flex;justify-content:flex-end;' +
                'padding:6px;border-top:1px solid #e5e7eb;background:#fff;border-bottom-left-radius:5px;border-bottom-right-radius:5px;}' +
                '.flatpickr-calendar .erp-fp-done-btn{min-height:40px;padding:6px 18px;border:0;' +
                'border-radius:8px;background:#2563eb;color:#fff;font-weight:600;font-size:14px;cursor:pointer;}';
            document.head.appendChild(st);
        }
        const bar = document.createElement('div');
        bar.className = 'erp-fp-done-bar';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'erp-fp-done-btn';
        btn.innerHTML = '<i class="fas fa-check"></i> 확인';
        btn.addEventListener('click', function () { instance.close(); });
        bar.appendChild(btn);
        instance.calendarContainer.appendChild(bar);
    }

    function initErpMainDatePickers() {
        const mEl = document.getElementById('erp-measurement-date');
        const cEl = document.getElementById('erp-construction-date');
        if (typeof flatpickr !== 'function') return;
        const opts = {
            mode: 'multiple', dateFormat: 'Y-m-d', locale: 'ko', allowInput: true,
            onReady: function (selectedDates, dateStr, instance) {
                erpAddFlatpickrDoneButton(instance);
            }
        };
        if (mEl && !mEl._flatpickr) {
            window._erpMeasurementDatePicker = flatpickr(mEl, {
                ...opts,
                onChange: function () {
                    syncWorkflowStageByMeasurementDate();
                }
            });
        }
        if (cEl && !cEl._flatpickr) {
            window._erpConstructionDatePicker = flatpickr(cEl, opts);
        }
        var mOpen = document.getElementById('erp-measurement-date-open');
        var cOpen = document.getElementById('erp-construction-date-open');
        if (mOpen && window._erpMeasurementDatePicker && !mOpen._erpDateBound) {
            mOpen._erpDateBound = true;
            mOpen.addEventListener('click', function () { window._erpMeasurementDatePicker.open(); });
        }
        if (cOpen && window._erpConstructionDatePicker && !cOpen._erpDateBound) {
            cOpen._erpDateBound = true;
            cOpen.addEventListener('click', function () { window._erpConstructionDatePicker.open(); });
        }
        if (mEl && !mEl._erpStageSyncBound) {
            mEl._erpStageSyncBound = true;
            mEl.addEventListener('change', syncWorkflowStageByMeasurementDate);
            mEl.addEventListener('input', syncWorkflowStageByMeasurementDate);
        }
    }
    window.erpInitFlatpickrForItemRow = function (row) {
        if (typeof flatpickr !== 'function') return;
        (row.querySelectorAll('.erp-item-date-multiple') || []).forEach(function (el) {
            if (el._flatpickr) return;
            flatpickr(el, {
                mode: 'multiple', dateFormat: 'Y-m-d', locale: 'ko', allowInput: true,
                onReady: function (selectedDates, dateStr, instance) {
                    erpAddFlatpickrDoneButton(instance);
                }
            });
        });
    };

    document.getElementById('erp-attachments-upload-btn')?.addEventListener('click', function () {
        erpUploadSelectedAttachments(this);
    });
    document.getElementById('erp-attachments-input')?.addEventListener('change', function () {
        if (this.files && this.files.length > 0) {
            erpUploadSelectedAttachments(this);
        }
    });
    document.getElementById('erp-attachments-gallery-input')?.addEventListener('change', function () {
        if (this.files && this.files.length > 0) {
            erpUploadSelectedAttachments(this);
        }
    });
    erpBindAttachmentPasteUpload();
    document.getElementById('erp-gen-text-btn')?.addEventListener('click', erpGenerateConversionText);
    document.getElementById('erp-copy-text-btn')?.addEventListener('click', erpCopyToClipboard);

    document.getElementById('erp-channeltalk-push-btn')?.addEventListener('click', function() {
        return erpRunChannelPush(this, 'measurement');
    });
    document.getElementById('erp-channeltalk-push-drawing-btn')?.addEventListener('click', function() {
        return erpRunChannelPush(this, 'drawing');
    });
    document.getElementById('erp-channeltalk-push-as-btn')?.addEventListener('click', function() {
        return erpRunChannelPush(this, 'as');
    });
    document.getElementById('erp-channeltalk-push-measure-btn')?.addEventListener('click', function() {
        return erpRunChannelPush(this, 'measure_room');
    });

    // 모바일 하단 액션바는 폭이 좁아 PUSH 버튼 3개를 나란히 두면 정렬이 무너진다.
    // 대신 PUSH 버튼 하나로 종류 선택 시트를 띄우고, 고른 종류로 공용 핸들러를 실행한다.
    document.getElementById('erp-channeltalk-push-picker-btn')?.addEventListener('click', async function() {
        if (typeof erpPromptChannelPushKind !== 'function') return;
        const pushKind = await erpPromptChannelPushKind();
        if (!pushKind) return;
        return erpRunChannelPush(this, pushKind);
    });

    // 영발(measurement)/발주(drawing)/AS(as) PUSH 공용 핸들러.
    // pushKind에 따라 백엔드가 해당 분류 첨부만 골라 별도 채널톡 그룹으로 전송한다.
    // 재전송(prev push) 시 modal/sheet에서 change_note 입력 후 전송.
    // 서버 400(재전송 note 필수) 시 클라 상태 동기화 후 modal 1회 재시도(M1).
    async function erpRunChannelPush(btn, pushKind, resendRetryState) {
        const retryState = resendRetryState || { resendRecoveryUsed: false };

        // 푸시 본문은 저장 전 라이브 DOM에서 조립된다 — 미저장 변경이 있거나 아직
        // 승격되지 않은 draft 주문이면 "전송완료" 표시만 남고 DB엔 반영 안 되는 사고가 난다.
        // 그래서 되묻지 않고 여기서 먼저 저장(draft면 승격)한 뒤 푸시한다.
        // (저장 후 다시 들어와야 푸시되던 동선 제거 — 다른 PUSH 버튼과 동일 UX)
        // 재귀(resend note) 호출은 이미 저장을 마쳤으므로 다시 저장하지 않는다.
        if (!resendRetryState) {
            const _autosave = window.fomsErpAutosave;
            const _isDirty = !!(
                _autosave && typeof _autosave.isDirty === 'function' && _autosave.isDirty()
            );
            const _needsPersist =
                !(typeof ORDER_ID !== 'undefined' && ORDER_ID > 0) || erpIsDraftBackedOrder();
            if (_isDirty || _needsPersist) {
                erpSetStatus(
                    _isDirty
                        ? '저장되지 않은 변경이 있습니다. 저장 후 푸시합니다...'
                        : '푸시 전 주문을 저장합니다...'
                );
                // 필수값 검증(고객명·전화·주소·제품)은 그대로 통과해야 한다 —
                // 실패 시 저장 함수가 alert로 누락 항목을 알려주고 푸시는 중단된다.
                const saveResult = await erpSaveStructured({ redirect: false });
                if (saveResult?.success !== true) {
                    return;
                }
            }
        }

        // AS PUSH 본문은 서버가 저장된 주문으로 조립한다(SSOT) — AS 대시보드처럼 폼 DOM이
        // 없는 화면과 같은 문구를 보장하기 위해 여기서는 text를 만들지 않는다.
        let text = '';
        if (pushKind !== 'as') {
            if (typeof erpGenerateConversionText === 'function') {
                erpGenerateConversionText();
            }
            const rawConversionText = document.getElementById('erp-conversion-text')?.value || '';
            // 실측방(measure_room) PUSH 만 변환 텍스트를 그대로 보낸다 — 실측방은 실측일·
            // 시   간이 그대로 필요하다. 영발(measurement)·발주(drawing) 은 종전대로
            // 실측일/시간 헤더를 잘라낸다(영발방·발주방엔 실측 일정이 나가면 안 된다).
            text = pushKind === 'measure_room'
                ? String(rawConversionText).trim()
                : erpSliceConversionTextForChannelPush(rawConversionText);
            if (!text) {
                alert('변환할 내용이 없습니다. 주문 정보를 입력해주세요.');
                return;
            }
        }

        let orderId = (typeof ORDER_ID !== 'undefined' && ORDER_ID > 0) ? ORDER_ID : 0;
        if (!orderId || erpIsDraftBackedOrder()) {
            erpCanUsePersistedOrderAction('푸쉬는');
            return;
        }
        if (!orderId) {
            alert('주문 ID를 확보할 수 없습니다.');
            return;
        }

        let changeNote = retryState.changeNote || null;
        if (!changeNote && typeof erpHasPriorChannelPush === 'function' && erpHasPriorChannelPush(pushKind)) {
            changeNote = await erpPromptChannelPushResendNote(pushKind);
            if (!changeNote) {
                return;
            }
        }

        const activeClass = btn.classList.contains('erp-push-btn--drawing') ? 'erp-push-btn--drawing'
            : btn.classList.contains('btn-warning') ? 'btn-warning'
            : btn.classList.contains('btn-primary') ? 'btn-primary'
            : btn.classList.contains('erp-push-btn--measure-room') ? 'erp-push-btn--measure-room'
            : btn.classList.contains('btn-info') ? 'btn-info'
            : btn.classList.contains('foms-btn--warning') ? 'foms-btn--warning'
            : btn.classList.contains('foms-btn--primary') ? 'foms-btn--primary'
            : btn.classList.contains('erp-mobile-push-btn--pastel') ? 'erp-mobile-push-btn--pastel'
            : btn.classList.contains('foms-btn--secondary') ? 'foms-btn--secondary'
            : null;
        const successClass = btn.classList.contains('foms-btn') ? 'foms-btn--success' : 'btn-success';

        btn.disabled = true;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 전송중...';

        const payload = { order_id: orderId, text, push_kind: pushKind };
        if (changeNote) {
            payload.change_note = changeNote;
        }

        if (pushKind === 'as') {
            if (typeof window.fomsConfirmAndSendAsPush !== 'function') {
                alert('AS 전송 확인창을 불러오지 못했습니다.');
                btn.innerHTML = originalHtml;
                btn.disabled = false;
                return;
            }
            try {
                const result = await window.fomsConfirmAndSendAsPush({
                    orderId: orderId,
                    changeNote: changeNote,
                });
                if (!result || result.cancelled) {
                    btn.innerHTML = originalHtml;
                    btn.disabled = false;
                    return;
                }
                if (result.success) {
                    if (typeof erpMarkChannelPushSent === 'function') {
                        erpMarkChannelPushSent(pushKind);
                    }
                    btn.innerHTML = '<i class="fas fa-check"></i> 전송완료';
                    if (activeClass) btn.classList.replace(activeClass, successClass);
                    setTimeout(() => {
                        btn.innerHTML = originalHtml;
                        if (activeClass) btn.classList.replace(successClass, activeClass);
                        btn.disabled = false;
                    }, 3000);
                    return;
                }
                alert(`채널톡 전송 실패:\n${result.error || result.message || '알 수 없는 오류'}`);
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            } catch (e) {
                alert(`네트워크 오류: ${e.message}`);
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
            return;
        }

        try {
            const resp = await fetch('/api/channel/push-manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();

            if (data.success) {
                if (typeof erpMarkChannelPushSent === 'function') {
                    erpMarkChannelPushSent(pushKind);
                }
                btn.innerHTML = '<i class="fas fa-check"></i> 전송완료';
                if (activeClass) btn.classList.replace(activeClass, successClass);
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                    if (activeClass) btn.classList.replace(successClass, activeClass);
                    btn.disabled = false;
                }, 3000);
                return;
            }

            const errMsg = data.error || data.message || '알 수 없는 오류';
            if (
                !retryState.resendRecoveryUsed
                && typeof erpIsChannelPushResendNoteRequired === 'function'
                && erpIsChannelPushResendNoteRequired(errMsg)
            ) {
                if (typeof erpMarkChannelPushSent === 'function') {
                    erpMarkChannelPushSent(pushKind);
                }
                btn.innerHTML = originalHtml;
                btn.disabled = false;
                const recoveryNote = await erpPromptChannelPushResendNote(pushKind);
                if (!recoveryNote) {
                    return;
                }
                return erpRunChannelPush(btn, pushKind, {
                    resendRecoveryUsed: true,
                    changeNote: recoveryNote,
                });
            }

            alert(`채널톡 전송 실패:\n${errMsg}`);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        } catch (e) {
            alert(`네트워크 오류: ${e.message}`);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }

    initErpMainDatePickers();

    loadMeasurementPanel();
    if (!window.__fomsErpMeasurementIntervalId) {
        // 30초 폴링은 **화면이 보일 때만** 돈다. 숨겨진 탭에서도 돌면 서버가 같은 실측
        // 창을 계속 다시 계산한다 — 열려 있는 탭 수만큼 곱해지는 비용이라 사용자는
        // 아무것도 못 느끼는 채로 서버만 먹는다(2026-09-01 실측: 호출당 서버 263ms).
        // 패널이 사라지면(프래그먼트 스왑) 타이머 자체를 접는다.
        window.__fomsErpMeasurementIntervalId = window.setInterval(function () {
            if (!document.getElementById('erp-order-measurement-panel')) {
                window.clearInterval(window.__fomsErpMeasurementIntervalId);
                window.__fomsErpMeasurementIntervalId = null;
                return;
            }
            if (document.visibilityState === 'hidden') return;
            loadMeasurementPanel();
        }, 30000);
    }
    if (!window.__FOMS_ERP_MEASUREMENT_VISIBILITY_BOUND) {
        // 돌아오는 즉시 1회 갱신 — 숨은 동안 건너뛴 만큼을 여기서 메운다(다음 틱까지
        // 최대 30초 낡은 값을 보여주지 않는다).
        window.__FOMS_ERP_MEASUREMENT_VISIBILITY_BOUND = true;
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState !== 'visible') return;
            if (!document.getElementById('erp-order-measurement-panel')) return;
            loadMeasurementPanel();
        });
    }

    // 서버 렌더에서 주입된 부트스트랩 페이로드를 1회 소비해 초기 페인트의 fetch 왕복을 제거한다.
    const erpBootstrap = _erpConsumeBootstrap();

    var _erpWillRunInitialLoad = false;
    if (ORDER_ID && ORDER_ID > 0) {
        const erpTabBtn = document.getElementById('erp-order-tab');
        const erpPane = document.getElementById('erp-order');
        const erpTabAlreadyActive =
            (erpTabBtn && erpTabBtn.classList.contains('active')) ||
            (erpPane && (erpPane.classList.contains('active') || erpPane.classList.contains('show')));
        if (erpTabAlreadyActive) {
            _erpWillRunInitialLoad = true;
            void (async () => {
                try {
                    window.clearTimeout(_erpReadyFailsafeId);
                    _erpMarkSurfaceReady();
                    await _erpYieldForFirstPaint();
                    await erpLoadStructured(erpBootstrap || undefined, { deferAttachments: true });
                    _erpLoadDeferredSurfaceDecorations();
                } finally {
                    window.clearTimeout(_erpReadyFailsafeId);
                    _erpMarkSurfaceReady();
                }
            })();
        }
    }
    if (!_erpWillRunInitialLoad) {
        // 초기 비동기 로드가 없는 경로(기능 OFF·미저장 신규·비활성 탭)는
        // 즉시 cloak을 해제한다. 해당 탭을 나중에 활성화할 때는 shown.bs.tab 핸들러에서
        // 첫 데이터 로드 완료 후 다시 ready를 설정해 네트워크 지연 동안의 flash를 가린다.
        window.clearTimeout(_erpReadyFailsafeId);
        _erpMarkSurfaceReady();
    }

    document.getElementById('erp-order-tab')?.addEventListener('shown.bs.tab', async function () {
        initErpMainDatePickers();
        loadMeasurementPanel();
        const fileInput = document.getElementById('erp-attachments-input');
        if (fileInput) {
            fileInput.value = '';
        }
        erpBindAttachmentPasteUpload();
        if (isErpOrderDraftMode() && (!ORDER_ID || ORDER_ID <= 0)) {
            const now = new Date();
            const localDateStr = [
                now.getFullYear(),
                String(now.getMonth() + 1).padStart(2, '0'),
                String(now.getDate()).padStart(2, '0')
            ].join('-');
            const localTimeStr = erpFormatHalfHourTime(now);

            const rd = document.getElementById('erp-received-date');
            const rt = document.getElementById('erp-received-time');
            if (rd) rd.value = localDateStr;
            if (rt) {
                rt.value = localTimeStr;
                erpSetReceivedTimeControlValue(localTimeStr);
            }
            const stageEl = document.getElementById('erp-workflow-stage');
            if (stageEl && !stageEl.value) stageEl.value = 'RECEIVED';
            syncWorkflowStageByOrderer();
        }
        if (ORDER_ID && ORDER_ID > 0) {
            // 미저장 편집이 있으면 서버 재조회로 DOM(사용자 입력)을 덮어쓰지 않는다.
            // 계산기/견적서 탭 왕복 시 타이핑이 stale 서버 데이터로 파괴되던 버그 차단.
            // dirty가 아닐 때만 서버 최신 상태를 재조회(타 팀 갱신 반영 유지).
            var _autosave = window.fomsErpAutosave;
            var _erpDirty = _autosave && typeof _autosave.isDirty === 'function'
                ? _autosave.isDirty() : false;
            if (!_erpDirty) {
                await erpLoadStructured();
                if (_autosave && typeof _autosave.recaptureBaseline === 'function') {
                    _autosave.recaptureBaseline();
                }
            }
            erpLoadQuest();
            loadMeasurementPanel();
        }
    });
}

window.fomsMountErpOrderSurface = fomsMountErpOrderSurface;
window.fomsErpBootstrapErpBetaSurface = fomsMountErpOrderSurface;
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fomsMountErpOrderSurface);
} else {
    fomsMountErpOrderSurface();
}
if (!window.__erpOrderMainContentSwapListenerBound) {
    window.__erpOrderMainContentSwapListenerBound = true;
    document.addEventListener("foms:main-content-swapped", function () {
        if (typeof window.fomsMountErpOrderSurface === "function") {
            window.fomsMountErpOrderSurface();
        }
    });
}

// ============================================
// ERP Order: Quest System (단계별 명확한 퀘스트)
// ============================================
let __erpQuest = null;

const ERP_TEAM_LABELS = {
    CS: 'CS팀',
    LAHOME: '라홈팀',
    HAUDD: '하우드팀',
    SALES: '영업팀',
    MEASURE: '실측팀',
    DRAWING: '도면팀',
    PRODUCTION: '생산팀',
    CONSTRUCTION: '시공팀',
    SHIPMENT: '출고팀',
};

const ERP_QUEST_STATUS_LABELS = {
    OPEN: '오픈',
    IN_PROGRESS: '진행중',
    COMPLETED: '완료',
};

const ERP_STAGE_LABELS = {
    RECEIVED: 'A. 주문접수',
    MEASURE: 'C. 실측',
    DRAWING: 'D. 도면',
    CONFIRM: 'E. 고객컨펌',
    PRODUCTION: 'F. 생산',
    CONSTRUCTION: 'G. 시공',
    CS: 'H. CS',
    AS_RECEIVED: 'AS접수',
    AS_COMPLETED: 'AS완료',
    COMPLETED: '완료',
    AS: 'AS처리',
};

function erpLabel(map, code, fallback = '-') {
    if (!code) return fallback;
    return map[code] || code;
}

function erpSetQuestStatus(text, isError = false) {
    const el = document.getElementById('erp-quest-status-text');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('text-danger', !!isError);
    el.classList.toggle('text-muted', !isError);
}

function erpRenderQuest() {
    const quest = __erpQuest;
    const container = document.getElementById('erp-quest-container');
    if (!container) return;

    if (!quest) {
        container.innerHTML = '<div class="alert alert-secondary">현재 단계의 Quest가 없습니다. Quest는 자동으로 생성됩니다.</div>';
        return;
    }

    const titleEl = document.getElementById('erp-quest-title');
    const descEl = document.getElementById('erp-quest-description');
    const statusBadgeEl = document.getElementById('erp-quest-status-badge');
    const ownerTeamEl = document.getElementById('erp-quest-owner-team');
    const approvalsEl = document.getElementById('erp-quest-approvals');

    if (titleEl) titleEl.textContent = quest.title || '-';
    if (descEl) descEl.textContent = quest.description || '-';

    const status = quest.status || 'OPEN';
    const statusLabel = erpLabel(ERP_QUEST_STATUS_LABELS, status, status);
    if (statusBadgeEl) {
        let badgeClass = 'bg-secondary';
        if (status === 'COMPLETED') badgeClass = 'bg-success';
        else if (status === 'IN_PROGRESS') badgeClass = 'bg-primary';
        statusBadgeEl.className = `badge ${badgeClass}`;
        statusBadgeEl.textContent = statusLabel;
    }

    if (ownerTeamEl) {
        ownerTeamEl.textContent = erpLabel(ERP_TEAM_LABELS, quest.owner_team, quest.owner_team || '-');
    }

    // 팀별 승인 표시
    if (approvalsEl) {
        const teamApprovals = quest.team_approvals || {};
        const requiredTeams = Object.keys(teamApprovals);

        if (requiredTeams.length === 0) {
            approvalsEl.innerHTML = '<div class="text-muted small">승인 필요 팀이 없습니다.</div>';
        } else {
            approvalsEl.innerHTML = requiredTeams.map(team => {
                const approval = teamApprovals[team] || {};
                const isApproved = approval.approved === true;
                const approvedBy = escapeHtml(approval.approved_by_name || approval.approved_by || '-');
                const approvedAt = approval.approved_at ? new Date(approval.approved_at).toLocaleString('ko-KR') : '-';
                const teamLabel = escapeHtml(erpLabel(ERP_TEAM_LABELS, team, team));
                const teamEscaped = escapeHtml(team);

                return `
<div class="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
    <div>
        <div class="fw-bold">${teamLabel}</div>
        ${isApproved ? `<small class="text-success">승인 완료 (${approvedBy}, ${approvedAt})</small>` :
                        `<small class="text-muted">승인 대기</small>`}
    </div >
                        <div>
                            ${!isApproved ? `
        <button class="btn btn-sm btn-success" type="button" onclick="erpApproveQuestTeam('${teamEscaped}')">
            <i class="fas fa-check"></i> 승인
        </button>
        ` : `
        <span class="badge bg-success"><i class="fas fa-check-circle"></i> 승인됨</span>
        `}
                        </div>
</div >
                        `;
            }).join('');
        }
    }
}

async function erpLoadQuest() {
    if (!ERP_ORDER_ENABLED || !ORDER_ID) return;
    // 퀘스트 마크업이 없는 화면에서는 응답을 그릴 곳이 없다 — 헛요청을 보내지 않는다.
    // (템플릿에 #erp-quest-container 가 다시 붙으면 이 가드가 자동으로 풀린다.)
    if (!document.getElementById('erp-quest-container')) return;
    try {
        const res = await fetch(`/api/orders/${ORDER_ID}/quest`);
        const data = await res.json();
        if (!data.success) throw new Error(data.message || 'Quest 조회 실패');
        __erpQuest = data.quest;
        erpRenderQuest();

        // 자동 전환 알림
        if (data.auto_transitioned && data.next_stage) {
            const nextStageLabel = erpLabel(ERP_STAGE_LABELS, data.next_stage, data.next_stage);
            erpSetQuestStatus(`✅ 모든 팀 승인 완료! 다음 단계(${nextStageLabel})로 자동 전환되었습니다.`);
            setTimeout(() => {
                erpLoadQuest(); // 새 Quest 로드
            }, 1000);
        }
    } catch (e) {
        console.error(e);
        erpSetQuestStatus('Quest 조회 실패', true);
    }
}

async function erpApproveQuestTeam(team) {
    if (!ERP_ORDER_ENABLED || !ORDER_ID) return;
    if (!confirm(`${erpLabel(ERP_TEAM_LABELS, team, team)} 승인을 진행하시겠습니까?`)) return;

    erpSetQuestStatus('승인 처리 중...');
    try {
        const res = await fetch(`/api/orders/${ORDER_ID}/quest/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team })
        });
        const data = await res.json();
        if (!data.success) {
            erpSetQuestStatus(data.message || '승인 실패', true);
            return;
        }

        if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
            window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
        }

        __erpQuest = data.quest;
        erpRenderQuest();

        if (data.all_approved) {
            if (data.auto_transitioned && data.next_stage) {
                const nextStageLabel = erpLabel(ERP_STAGE_LABELS, data.next_stage, data.next_stage);
                erpSetQuestStatus(`✅ 모든 팀 승인 완료! 다음 단계(${nextStageLabel})로 자동 전환되었습니다.`);
                setTimeout(async () => {
                    erpLoadQuest(); // 새 Quest 로드(폼을 건드리지 않으므로 무조건)
                    // 미저장 편집이 있으면 서버 재조회로 DOM(사용자 입력)을 덮어쓰지 않는다.
                    // dirty가 아닐 때만 structured_data를 새로고침(탭 복귀 가드와 동일 패턴).
                    var _autosave = window.fomsErpAutosave;
                    var _erpDirty = _autosave && typeof _autosave.isDirty === 'function'
                        ? _autosave.isDirty() : false;
                    if (!_erpDirty) {
                        await erpLoadStructured();
                        if (_autosave && typeof _autosave.recaptureBaseline === 'function') {
                            _autosave.recaptureBaseline();
                        }
                    } else {
                        erpSetQuestStatus('미저장 입력이 있어 화면 새로고침을 건너뛰었습니다. 저장 후 새로고침하세요.', true);
                    }
                }, 1500);
            } else {
                erpSetQuestStatus('✅ 모든 팀 승인 완료!');
            }
        } else {
            const missingTeams = data.missing_teams.map(t => erpLabel(ERP_TEAM_LABELS, t, t)).join(', ');
            erpSetQuestStatus(`승인 완료. 남은 팀: ${missingTeams}`);
        }
    } catch (e) {
        console.error(e);
        erpSetQuestStatus('승인 처리 실패', true);
    }
}

async function erpUpdateQuestStatus() {
    if (!ERP_ORDER_ENABLED || !ORDER_ID) return;
    if (!__erpQuest) return;

    const currentStatus = __erpQuest.status || 'OPEN';
    const statuses = ['OPEN', 'IN_PROGRESS', 'COMPLETED'];
    const currentIndex = statuses.indexOf(currentStatus);
    const nextIndex = (currentIndex + 1) % statuses.length;
    const nextStatus = statuses[nextIndex];

    erpSetQuestStatus('상태 업데이트 중...');
    try {
        const res = await fetch(`/api/orders/${ORDER_ID}/quest/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: nextStatus })
        });
        const data = await res.json();
        if (!data.success) {
            erpSetQuestStatus(data.message || '상태 업데이트 실패', true);
            return;
        }

        __erpQuest = data.quest;
        erpRenderQuest();
        erpSetQuestStatus('상태 업데이트 완료');
    } catch (e) {
        console.error(e);
        erpSetQuestStatus('상태 업데이트 실패', true);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!ERP_ORDER_ENABLED) return;
    document.getElementById('erp-quest-status-btn')?.addEventListener('click', erpUpdateQuestStatus);
});
