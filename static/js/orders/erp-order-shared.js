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
var ORDER_ID = 0;
var ERP_ORDER_ENABLED = false;

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

var erpBuildTotals =
    window.erpBuildTotals ||
    function erpBuildTotals(itemsTotal, depositAmount) {
        var total = erpCoerceAmount(itemsTotal);
        var deposit = erpCoerceAmount(depositAmount);
        var balance = Math.max(0, total - deposit);
        return {
            items_total: total,
            deposit_amount: deposit,
            balance_amount: balance,
            final_amount: balance,
        };
    };
window.erpBuildTotals = erpBuildTotals;

var _erpNormalizePaymentData =
    window._erpNormalizePaymentData ||
    function _erpNormalizePaymentData(sd) {
        if (!sd) sd = {};
        var pay = sd.payment || {};
        var depositAmount = erpResolveDepositAmount(sd);

        return {
            deposit: Math.max(0, depositAmount),
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
        icon.src = _erpPaymentIconSrc(type, false);
        btn.title = "미확인 - 클릭하여 확인 완료 처리";
    };
window._erpUpdatePaymentConfirmUI = _erpUpdatePaymentConfirmUI;

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

var syncWorkflowStageByOrderer =
    window.syncWorkflowStageByOrderer ||
    function syncWorkflowStageByOrderer() {
        var orderer = (typeof getOrdererValue === "function" ? getOrdererValue() : "").trim();
        if (orderer === "라홈") return;
        var stageEl = document.getElementById("erp-workflow-stage");
        if (stageEl && stageEl.querySelector('option[value="MEASURE"]')) {
            stageEl.value = "MEASURE";
        }
    };
window.syncWorkflowStageByOrderer = syncWorkflowStageByOrderer;

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

        var res = await fetch(erpGetDraftEndpoint(), { method: "POST" });
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

async function erpEnsureFinalizedOrderForAction(actionText) {
    if (!ERP_ORDER_ENABLED) return 0;

    let targetId = erpResolveCurrentOrderId();
    if (targetId > 0 && !erpIsDraftBackedOrder()) return targetId;

    const label = actionText || '작업';
    erpSetStatus(`${label} 진행을 위해 주문을 저장 중...`);
    const saveRes = await erpSaveStructured({ redirect: false });
    if (!saveRes || !saveRes.success) {
        const message = (saveRes && saveRes.message) || `${label} 진행을 위해 주문 저장이 필요합니다.`;
        erpSetStatus(message, true);
        return 0;
    }

    targetId = erpResolveCurrentOrderId();
    if (targetId > 0) {
        erpSetOrderId(targetId);
        return targetId;
    }

    erpSetStatus(`${label} 진행을 위한 주문 ID를 확보할 수 없습니다.`, true);
    return 0;
}
window.erpEnsureFinalizedOrderForAction = erpEnsureFinalizedOrderForAction;

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

var erpFormatDepositDisplay =
    window.erpFormatDepositDisplay ||
    function erpFormatDepositDisplay(num) {
        if (num == null || !Number.isFinite(num) || num < 0) return "0원";
        return num === 0 ? "0원" : num.toLocaleString("ko-KR") + "원";
    };
window.erpFormatDepositDisplay = erpFormatDepositDisplay;


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

function erpRecalcItemsTotal() {
    const itemsWrap = document.getElementById('erp-items');
    const totalEl = document.getElementById('erp-items-total');
    const remainingSection = document.getElementById('erp-remaining-section');
    if (!itemsWrap || !totalEl) return;
    let sum = 0;
    itemsWrap.querySelectorAll('[data-erp="price"]').forEach(inp => {
        const digits = String(inp.value || '').replace(/[^0-9]/g, '');
        if (digits) sum += parseInt(digits, 10);
    });
    totalEl.textContent = erpFormatMoneyKRW(sum);
    if (remainingSection) {
        remainingSection.style.display = (sum === 0 || !Number.isFinite(sum)) ? 'none' : 'flex';
    }
    erpCalculateRemaining();
}

function erpCalculateRemaining() {
    const totalEl = document.getElementById('erp-items-total');
    const remainingEl = document.getElementById('erp-remaining-amount');
    if (!totalEl || !remainingEl) return;
    const totalAmount = erpCoerceAmount(totalEl.textContent);
    const totals = erpBuildTotals(totalAmount, erpParseDepositValue());
    remainingEl.textContent = totals.final_amount > 0 ? erpFormatMoneyKRW(totals.final_amount) : '0원';
}

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
            hintEl.textContent = name ? `${name} 실측 이미지` : `항목 ${idx + 1} 실측 이미지`;
        }
    });
}

function erpNewItemRow(item = {}) {
    const row = document.createElement('div');
    row.className = 'border rounded p-2 mb-2 erp-item-row';
    row.dataset.itemIndex = '-1';

    const defaultConsult = (v) => {
        const s = String(v ?? '').trim();
        return s ? s : '상담';
    };

    const productName = String(item.product_name || '').trim();
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
    const specRowsHtml = specRows.map((sr, idx) => {
        const w = escapeHtml(String((sr.spec_width ?? sr.w ?? '')).trim());
        const d = escapeHtml(String((sr.spec_depth ?? sr.d ?? '')).trim());
        const h = escapeHtml(String((sr.spec_height ?? sr.h ?? '')).trim());
        const showDel = specRows.length > 1 ? '' : ' style="display:none;"';
        return `<div class="erp-spec-row d-flex flex-wrap gap-2 align-items-end mb-1">
<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">W(폭)</label><input class="form-control form-control-sm" data-erp="spec_width" data-spec-row placeholder="폭" value="${w}" lang="ko"></div>
<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">D(깊이)</label><input class="form-control form-control-sm" data-erp="spec_depth" data-spec-row placeholder="깊이" value="${d}" lang="ko"></div>
<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">H(높이)</label><input class="form-control form-control-sm" data-erp="spec_height" data-spec-row placeholder="높이" value="${h}" lang="ko"></div>
<button type="button" class="btn btn-sm btn-outline-secondary erp-remove-spec-row-btn"${showDel}><i class="fas fa-minus"></i></button>
</div>`;
    }).join('');
    const internal = defaultConsult(item.internal);
    // 색상: 신규(빈 값)은 '상담' 기본. 저장된 값이 있으면 그대로 로드.
    // 이전 버그로 ' (SK)' suffix가 중복 저장된 레거시 데이터 자동 정리
    let _colorRaw = String(item.color ?? '').trim();
    _colorRaw = _colorRaw.replace(/(\s+\(SK\))+$/g, '').trim();
    const color = _colorRaw || '상담';
    const optionDetail = defaultConsult(item.option_detail);
    const handle = defaultConsult(item.handle);
    const misc = defaultConsult(item.misc);
    const price = String(item.price ?? '').trim();
    const extraInput = String(item.extra_input ?? '').trim();

    row.innerHTML = `
<div class="d-flex justify-content-between align-items-center mb-2">
<div class="fw-bold small erp-item-title">항목</div>
<button type="button" class="btn btn-sm btn-outline-danger erp-remove-item-btn">
    <i class="fas fa-times"></i>
</button>
</div>
<div class="row g-2">
<div class="col-12">
    <label class="form-label mb-1 small text-primary">제품명</label>
    <input class="form-control form-control-sm" data-erp="product_name" value="${escapeHtml(productName)}" lang="ko">
</div>
<div class="col-12">
    <label class="form-label mb-1 small text-primary">규격 (폭·깊이·높이)</label>
    <div class="erp-spec-rows">${specRowsHtml}</div>
    <button type="button" class="btn btn-sm btn-outline-primary mt-1 erp-add-spec-row-btn"><i class="fas fa-plus"></i> 규격 1행 추가</button>
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">내부</label>
    <input class="form-control form-control-sm" data-erp="internal" value="${escapeHtml(internal)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">색상</label>
    <input class="form-control form-control-sm" data-erp="color" value="${escapeHtml(color)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">옵션</label>
    <input class="form-control form-control-sm" data-erp="option_detail" value="${escapeHtml(optionDetail)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">손잡이</label>
    <input class="form-control form-control-sm" data-erp="handle" value="${escapeHtml(handle)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">기타 / 설치위치</label>
    <input class="form-control form-control-sm" data-erp="misc" value="${escapeHtml(misc)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">항목 금액(원)</label>
    <input class="form-control form-control-sm" data-erp="price" inputmode="numeric" value="${escapeHtml(price)}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">항목 실측일</label>
    <input type="text" class="form-control form-control-sm erp-item-date-multiple" data-erp="measurement_date" placeholder="여러 날짜 가능" value="${escapeHtml(String(item.measurement_date || '').trim())}" lang="ko">
</div>
<div class="col-md-6">
    <label class="form-label mb-1 small text-primary">항목 시공일</label>
    <input type="text" class="form-control form-control-sm erp-item-date-multiple" data-erp="construction_date" placeholder="여러 날짜 가능" value="${escapeHtml(String(item.construction_date || '').trim())}" lang="ko">
</div>
<div class="col-12">
    <label class="form-label mb-1 small text-primary">추가 입력</label>
    <textarea class="form-control form-control-sm" data-erp="extra_input" rows="3"
        placeholder="추가 내용을 입력하세요 (여러 줄 가능)" lang="ko">${escapeHtml(extraInput)}</textarea>
</div>
<div class="col-12">
    <div class="border rounded p-2 bg-light">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
            <div class="small fw-semibold text-muted erp-item-attachment-hint">항목 실측 이미지</div>
            <div class="d-flex gap-1">
                <input type="file" class="d-none erp-item-attachments-input" accept="image/*" multiple onchange="erpUploadItemAttachmentsPromptless(this)">
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="this.previousElementSibling.click()">
                    <i class="fas fa-image"></i> 즉시 추가
                </button>
            </div>
        </div>
        <div class="d-flex flex-wrap gap-1 mt-2 erp-item-attachments-gallery">
            <div class="small text-muted">연결된 실측 이미지가 없습니다.</div>
        </div>
    </div>
</div>
</div>
`;

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
        const div = document.createElement('div');
        div.className = 'erp-spec-row d-flex flex-wrap gap-2 align-items-end mb-1';
        div.innerHTML = `<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">W(폭)</label><input class="form-control form-control-sm" data-erp="spec_width" data-spec-row placeholder="폭" value="" lang="ko"></div>
<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">D(깊이)</label><input class="form-control form-control-sm" data-erp="spec_depth" data-spec-row placeholder="깊이" value="" lang="ko"></div>
<div class="col-md-3 col-4"><label class="form-label mb-0 small text-muted">H(높이)</label><input class="form-control form-control-sm" data-erp="spec_height" data-spec-row placeholder="높이" value="" lang="ko"></div>
<button type="button" class="btn btn-sm btn-outline-secondary erp-remove-spec-row-btn"><i class="fas fa-minus"></i></button>`;
        div.querySelector('.erp-remove-spec-row-btn').addEventListener('click', () => {
            div.remove();
            updateSpecRowRemoveVisibility();
        });
        container.appendChild(div);
        updateSpecRowRemoveVisibility();
    });
    row.querySelectorAll('.erp-remove-spec-row-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            this.closest('.erp-spec-row')?.remove();
            updateSpecRowRemoveVisibility();
        });
    });

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
        if (removedIndex >= 0 && typeof erpReindexMeasurementAttachmentsAfterItemRemoval === 'function') {
            await erpReindexMeasurementAttachmentsAfterItemRemoval(removedIndex);
        }
        row.remove();
        erpRefreshItemRowIndices();
        erpRecalcItemsTotal();
        if (typeof erpRenderAttachments === 'function') {
            erpRenderAttachments();
        }
    });
    row.addEventListener('input', (e) => {
        erpRecalcItemsTotal();
        if (e.target && e.target.dataset && e.target.dataset.erp === 'product_name') {
            erpRefreshItemRowIndices();
            if (typeof erpRenderAttachments === 'function') {
                erpRenderAttachments();
            }
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

    const sd = data.structured_data || {};
    const receivedDateEl = document.getElementById('erp-received-date');
    const receivedTimeEl = document.getElementById('erp-received-time');
    if (receivedDateEl) receivedDateEl.value = data.received_date || '';
    if (receivedTimeEl) receivedTimeEl.value = data.received_time || '';
    document.getElementById('erp-customer-name').value = sd?.parties?.customer?.name || '';
    document.getElementById('erp-customer-phone').value = sd?.parties?.customer?.phone || '';
    try {
        const erpManualPhone = document.getElementById('erp-manual-phone-input');
        if (!erpManualPhone || !erpManualPhone.checked) {
            document.getElementById('erp-customer-phone').value =
                formatPhoneAuto(document.getElementById('erp-customer-phone').value);
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
    document.getElementById('erp-workflow-stage').value = sd?.workflow?.stage || '';
    const erpNotesEl = document.getElementById('erp-notes');
    if (erpNotesEl) erpNotesEl.value = data.notes || '';
    document.getElementById('erp-urgent-flag').checked = !!sd?.flags?.urgent;
    document.getElementById('erp-urgent-reason').value = sd?.flags?.urgent_reason || '';
    const selfMeasEl = document.getElementById('erp-self-measurement');
    if (selfMeasEl) selfMeasEl.checked = !!data.is_self_measurement;
    // 주소 로드: 주소+상세주소는 한 필드(erp-address)에 함께 표기
    const site = sd?.site || {};
    const addressFull = site.address_full || site.address_main || '';
    const addressDetail = site.address_detail || '';
    document.getElementById('erp-address').value = addressDetail ? `${addressFull} ${addressDetail}`.trim() : addressFull;
    document.getElementById('erp-address-note').value = sd?.notes?.address_note || '';
    const measurementDateVal = sd?.schedule?.measurement?.date || '';
    document.getElementById('erp-measurement-date').value = measurementDateVal;
    if (window._erpMeasurementDatePicker && measurementDateVal) {
        const dates = measurementDateVal.split(',').map(s => s.trim()).filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
        if (dates.length) window._erpMeasurementDatePicker.setDate(dates);
    }
    const measurementTime = sd?.schedule?.measurement?.time || '';
    const erpMeasurementTimeSelect = document.getElementById('erp-measurement-time-select');
    const erpMeasurementTimeInput = document.getElementById('erp-measurement-time');
    if (erpMeasurementTimeSelect) {
        if (measurementTime === '오전' || measurementTime === '오후' || measurementTime === '종일') {
            erpMeasurementTimeSelect.value = measurementTime;
            if (erpMeasurementTimeInput) {
                erpMeasurementTimeInput.value = '';
                erpMeasurementTimeInput.style.display = 'none';
            }
        } else {
            erpMeasurementTimeSelect.value = '__direct__';
            if (erpMeasurementTimeInput) {
                erpMeasurementTimeInput.value = measurementTime || '';
                erpMeasurementTimeInput.style.display = 'block';
            }
        }
    }
    document.getElementById('erp-measurement-note').value = sd?.notes?.measurement_note || '';
    const constructionDateVal = sd?.schedule?.construction?.date || '';
    document.getElementById('erp-construction-date').value = constructionDateVal;
    if (window._erpConstructionDatePicker && constructionDateVal) {
        const dates = constructionDateVal.split(',').map(s => s.trim()).filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
        if (dates.length) window._erpConstructionDatePicker.setDate(dates);
    }
    const constructionTime = sd?.schedule?.construction?.time || '';
    const erpConstructionTimeSelect = document.getElementById('erp-construction-time-select');
    const erpConstructionTimeInput = document.getElementById('erp-construction-time');
    if (erpConstructionTimeSelect) {
        if (constructionTime === '오전' || constructionTime === '오후' || constructionTime === '종일') {
            erpConstructionTimeSelect.value = constructionTime;
            if (erpConstructionTimeInput) {
                erpConstructionTimeInput.value = '';
                erpConstructionTimeInput.style.display = 'none';
            }
        } else {
            erpConstructionTimeSelect.value = '__direct__';
            if (erpConstructionTimeInput) {
                erpConstructionTimeInput.value = constructionTime || '';
                erpConstructionTimeInput.style.display = 'block';
            }
        }
    }

    const itemsWrap = document.getElementById('erp-items');
    itemsWrap.innerHTML = '';
    const items = Array.isArray(sd.items) ? sd.items : [];
    if (items.length === 0) {
        itemsWrap.appendChild(erpNewItemRow({}));
    } else {
        items.forEach(it => itemsWrap.appendChild(erpNewItemRow(it)));
    }
    erpRefreshItemRowIndices();

    erpSetStatus(`불러오기 완료 (confidence: ${data.structured_confidence || sd.confidence || '-'})`);
    const paymentData = _erpNormalizePaymentData(sd);
    sd.payment = paymentData;
    window.__erpLastStructuredData = sd;
    window.__erpStructuredLoadSucceeded = true;
    erpRecalcItemsTotal();
    const depositEl = document.getElementById('erp-deposit-amount');
    if (depositEl) {
        depositEl.value = erpFormatDepositDisplay(paymentData.deposit);
    }
    erpCalculateRemaining();
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
}

function erpCollectStructured() {
    const itemsWrap = document.getElementById('erp-items');
    const items = [];
    let itemsTotal = 0;
    itemsWrap.querySelectorAll('.erp-item-row').forEach(row => {
        const obj = {};
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
            specRows.push({ spec_width: w, spec_depth: d, spec_height: h });
        });
        if (specRows.length > 0) {
            obj.spec_rows = specRows;
            const first = specRows[0];
            obj.spec_width = first.spec_width;
            obj.spec_depth = first.spec_depth;
            obj.spec_height = first.spec_height;
            const specParts = [first.spec_width, first.spec_depth, first.spec_height].filter(Boolean);
            obj.spec = specParts.join('x');
        } else {
            obj.spec_rows = [];
            obj.spec_width = '';
            obj.spec_depth = '';
            obj.spec_height = '';
            obj.spec = '';
        }
        if (obj.price) {
            const digits = String(obj.price).replace(/[^0-9]/g, '');
            obj.price = digits ? parseInt(digits, 10) : obj.price;
            if (typeof obj.price === 'number' && Number.isFinite(obj.price)) {
                itemsTotal += obj.price;
            }
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
    const totals = erpBuildTotals(itemsTotal, depositAmount);

    // PUT /structured 는 본문 전체로 JSONB를 교체함. 폼에 없는 최상위 키는 서버 스냅샷에서 유지 (AS as_content 등)
    const prevSd = (window.__erpLastStructuredData && typeof window.__erpLastStructuredData === 'object')
        ? window.__erpLastStructuredData
        : {};
    const preservedTopLevelKeys = ['shipment', 'assignments', 'quests', 'meta'];

    const structured = {
        entity_type: 'order_structured',
        schema_version: 1,
        confidence: null,
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
            measurement_note: getVal('erp-measurement-note')
        },
        workflow: { stage: getVal('erp-workflow-stage') },
        flags: {
            urgent: getCheck('erp-urgent-flag'),
            urgent_reason: getVal('erp-urgent-reason')
        },
        payment: (function () {
            const prev = window.__erpLastStructuredData ? _erpNormalizePaymentData(window.__erpLastStructuredData) : _erpNormalizePaymentData({});
            return {
                deposit: totals.deposit_amount,
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

    return structured;
}

/**
 * ERP Order 구조화 데이터 저장.
 * @param {Object} opts - 옵션
 * @param {boolean} [opts.redirect=true] - 저장 성공 후 리다이렉트 여부 (푸쉬 전 자동 저장 시 false)
 * @returns {Promise<{success: boolean, message?: string}>}
 */
async function erpSaveStructured(opts = {}) {
    const doRedirect = opts.redirect !== false;
    if (!ERP_ORDER_ENABLED) return { success: false, message: 'ERP Order 비활성' };

    // 필수 입력값 검증 (사용자 직접 저장 시에만 적용, 자동 저장 예외)
    if (opts._skipValidation !== true) {
        const missing = [];
        const nameVal = (document.getElementById('erp-customer-name')?.value || '').trim();
        const phoneVal = (document.getElementById('erp-customer-phone')?.value || '').trim();
        const addrVal = (document.getElementById('erp-address')?.value || '').trim();

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
            alert(`다음 필수 항목을 입력해주세요:\n\n• ${missing.join('\n• ')}`);
            // 첫 번째 누락 필드에 포커스
            if (!nameVal) document.getElementById('erp-customer-name')?.focus();
            else if (!phoneVal) document.getElementById('erp-customer-phone')?.focus();
            else if (!addrVal) document.getElementById('erp-address')?.focus();
            else {
                const firstItem = document.querySelector('#erp-items .erp-item-row [data-erp="product_name"]');
                firstItem?.focus();
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

    erpSetStatus('저장 중...');

    try {
        const structured_data = erpCollectStructured();

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
            window.__erpAsReceivePreviousStage = prevStage;
            window.__erpAsReceiveTargetId = targetId;
            window.__erpAsReceiveSubmitted = false;
            const modalEl = document.getElementById('asReceiveModal');
            if (modalEl) {
                const contentEl = document.getElementById('as-receive-content');
                const filesEl = document.getElementById('as-receive-files');
                const previewEl = document.getElementById('as-receive-preview');
                if (contentEl) contentEl.value = (window.__erpLastStructuredData?.shipment?.as_content || '').trim();
                if (filesEl) filesEl.value = '';
                if (previewEl) previewEl.innerHTML = '';
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            }
            erpSetStatus('AS 접수 내용을 입력해주세요.');
            return { success: false, message: 'AS 접수 단계로 변경 시 내용 입력 후 접수를 완료해주세요.' };
        }

        const receivedDateEl = document.getElementById('erp-received-date');
        const receivedTimeEl = document.getElementById('erp-received-time');
        const received_date = receivedDateEl ? (receivedDateEl.value || '').trim() : '';
        const received_time = receivedTimeEl ? (receivedTimeEl.value || '').trim() : '';
        const notesVal = (typeof getVal === 'function' ? getVal('erp-notes') : (document.getElementById('erp-notes')?.value || '')).trim();

        const res = await fetch(`/api/orders/${targetId}/structured`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                structured_data,
                raw_order_text: '',
                structured_schema_version: 1,
                structured_confidence: structured_data.confidence,
                received_date: received_date || undefined,
                received_time: received_time || undefined,
                notes: notesVal || undefined,
                is_self_measurement: document.getElementById('erp-self-measurement')?.checked === true
            })
        });
        const data = await res.json();
        if (!data.success) {
            erpSetStatus(data.message || '저장 실패', true);
            return { success: false, message: data.message || '저장 실패' };
        }
        erpSetStatus(doRedirect ? '저장 완료! 이동합니다...' : '저장 완료');
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
            if (isErpOrderDraftMode()) {
                window.location.href = '/erp/dashboard';
            } else {
                const referrerInput = document.querySelector('input[name="referrer"]');
                let targetUrl = referrerInput ? referrerInput.value : document.referrer;
                if (!targetUrl || targetUrl.includes(window.location.pathname)) targetUrl = '/erp/dashboard';
                window.location.href = targetUrl;
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

window.erpTogglePayment = async function(btn, pType) {
    if (_paymentTogglePending) return;
    
    let targetId = erpResolveCurrentOrderId();
    if (targetId <= 0 || erpIsDraftBackedOrder()) {
        targetId = await erpEnsureFinalizedOrderForAction('결제 확인');
        if (!targetId) return;
    }

    _paymentTogglePending = true;
    const isConfirmedNow = btn.dataset.confirmed === '1';
    const targetConfirmed = !isConfirmedNow;
    
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
            const p = _erpNormalizePaymentData({ payment: data.payment });
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
        erpPhoneInput.value = formatPhoneAuto(erpPhoneInput.value);
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

    // ERP Order: 실측시간 직접 입력 처리
    const erpMeasurementTimeSelect = document.getElementById('erp-measurement-time-select');
    const erpMeasurementTimeInput = document.getElementById('erp-measurement-time');
    if (erpMeasurementTimeSelect && erpMeasurementTimeInput) {
        erpMeasurementTimeSelect.addEventListener('change', function () {
            if (this.value === '__direct__') {
                erpMeasurementTimeInput.style.display = 'block';
            } else {
                erpMeasurementTimeInput.style.display = 'none';
                erpMeasurementTimeInput.value = '';
            }
        });
    }

    const erpConstructionTimeSelect = document.getElementById('erp-construction-time-select');
    const erpConstructionTimeInput = document.getElementById('erp-construction-time');
    if (erpConstructionTimeSelect && erpConstructionTimeInput) {
        erpConstructionTimeSelect.addEventListener('change', function () {
            if (this.value === '__direct__') {
                erpConstructionTimeInput.style.display = 'block';
            } else {
                erpConstructionTimeInput.style.display = 'none';
                erpConstructionTimeInput.value = '';
            }
        });
    }

    // 기본 항목 1개
    const itemsWrap = document.getElementById('erp-items');
    if (itemsWrap && itemsWrap.children.length === 0) {
        itemsWrap.appendChild(erpNewItemRow({}));
        erpRefreshItemRowIndices();
        erpRecalcItemsTotal();
    }

    document.getElementById('erp-add-item-btn')?.addEventListener('click', function () {
        document.getElementById('erp-items')?.appendChild(erpNewItemRow({}));
        erpRefreshItemRowIndices();
        erpRecalcItemsTotal();
        if (typeof erpRenderAttachments === 'function') {
            erpRenderAttachments();
        }
    });
    document.getElementById('erp-save-btn')?.addEventListener('click', erpSaveStructured);
    document.getElementById('erp-load-btn')?.addEventListener('click', erpLoadStructured);

    // AS 접수 모달: 파일 미리보기, 10MB 경고, 제출, 취소 시 롤백
    (function initAsReceiveModal() {
        const modalEl = document.getElementById('asReceiveModal');
        const contentEl = document.getElementById('as-receive-content');
        const filesEl = document.getElementById('as-receive-files');
        const previewEl = document.getElementById('as-receive-preview');
        const submitBtn = document.getElementById('as-receive-submit-btn');
        const AS_VIDEO_SIZE_WARN = 10 * 1024 * 1024; // 10MB

        if (filesEl && previewEl) {
            filesEl.addEventListener('change', function () {
                previewEl.innerHTML = '';
                const files = Array.from(this.files || []);
                files.forEach(function (f) {
                    const isVideo = (f.type || '').startsWith('video/');
                    if (isVideo && f.size > AS_VIDEO_SIZE_WARN) {
                        const warn = document.createElement('div');
                        warn.className = 'small text-warning';
                        warn.textContent = f.name + ' (10MB 초과, 업로드 지연 가능)';
                        previewEl.appendChild(warn);
                    }
                    const span = document.createElement('span');
                    span.className = 'badge bg-secondary';
                    span.textContent = f.name;
                    previewEl.appendChild(span);
                });
            });
        }

        if (modalEl) {
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
                    contentEl?.focus();
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

                try {
                    const regRes = await fetch(`/api/orders/${targetId}/as/register`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ as_content: content })
                    });
                    const regData = await regRes.json();
                    if (!regData.success) {
                        throw new Error(regData.message || 'AS 접수 등록 실패');
                    }

                    const files = filesEl?.files ? Array.from(filesEl.files) : [];
                    if (files.length > 0) {
                        const folder = `orders/${targetId}/attachments`;
                        const category = 'as';
                        let sessionMap = {};
                        try {
                            const bRes = await fetch('/api/upload/session/batch', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    files: files.map(function (f) { return { filename: f.name, size: f.size }; }),
                                    folder: folder,
                                    category: category
                                })
                            });
                            const bData = await bRes.json();
                            if (bData.success && bData.sessions) {
                                bData.sessions.forEach(function (s) {
                                    s.success = true;
                                    sessionMap[s.filename] = s;
                                });
                            }
                        } catch (e) { }

                        const CONCURRENCY = 10;
                        for (let start = 0; start < files.length; start += CONCURRENCY) {
                            const chunk = files.slice(start, start + CONCURRENCY);
                            await Promise.all(chunk.map(function (f) {
                                const sess = sessionMap[f.name];
                                return (typeof erpDoDirectUploadOne === 'function')
                                    ? erpDoDirectUploadOne(f, category, null, sess)
                                    : Promise.resolve({ success: false });
                            }));
                        }
                    }

                    window.__erpAsReceiveSubmitted = true;
                    bootstrap.Modal.getInstance(modalEl)?.hide();
                    erpSetStatus('AS 접수 완료. 대시보드로 이동합니다...');
                    window.location.href = '/erp/dashboard?stage=AS%EC%B2%98%EB%A6%AC';
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
    const erpDepositInput = document.getElementById('erp-deposit-amount');
    if (erpDepositInput) {
        erpDepositInput.addEventListener('input', function () {
            const raw = (this.value || '').replace(/[^0-9]/g, '');
            const num = raw ? parseInt(raw, 10) : 0;
            const formatted = erpFormatDepositDisplay(num);
            if (this.value !== formatted) this.value = formatted;
            erpCalculateRemaining();
        });
        erpDepositInput.addEventListener('change', function () {
            const num = erpParseDepositValue();
            this.value = erpFormatDepositDisplay(num);
            erpCalculateRemaining();
        });
    }


    // add_order(draft) 모드에선 tab 오픈 시 draft 생성 후 로드, edit_order에선 즉시 로드
    if (!isErpOrderDraftMode()) {
        erpLoadStructured();
    } else {
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
                const hh = String(now.getHours()).padStart(2, '0');
                const mi = String(now.getMinutes()).padStart(2, '0');
                rTime.value = `${hh}:${mi}`;
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
        erpAttachmentsSetStatus('이미지 연결이 변경되었습니다.');
        await erpLoadAttachments();
    } catch (e) {
        console.error(e);
        erpAttachmentsSetStatus(String(e?.message || e), true);
    }
}

async function erpReindexMeasurementAttachmentsAfterItemRemoval(removedIndex) {
    if (!ORDER_ID || removedIndex < 0) return;
    const list = (__erpAttachments || []).filter((a) => erpNormalizeAttachmentCategory(a.category) === 'measurement');
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
    if (!await erpEnsureFinalizedOrderForAction('제품 이미지 업로드')) {
        return;
    }
    if (!Array.isArray(files) || !files.length) {
        erpAttachmentsSetStatus('업로드할 이미지를 선택하세요.', true);
        return;
    }

    // --- Optimistic UI Start ---
    // 1. UI에 회색 스켈레톤/로딩 카드 먼저 렌더링
    const row = erpGetItemRows()[itemIndex];
    const galleryWrap = row ? row.querySelector('.erp-item-attachments-gallery') : null;
    if (galleryWrap) {
        // "연결된 실측 이미지가 없습니다." 텍스트 제거
        const emptyText = galleryWrap.querySelector('.text-muted');
        if (emptyText && emptyText.textContent.includes('없습니다')) emptyText.remove();

        files.forEach((f, fi) => {
            const uniqueId = 'opt-ul-' + Date.now() + '-' + fi;
            f._optId = uniqueId; // 파일 객체에 임시 ID 부여
            const name = escapeHtml(f.name);
            let previewUrl = '';
            try { previewUrl = URL.createObjectURL(f); } catch (e) { }

            const placeholderHtml = `
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

    erpAttachmentsSetStatus(`제품 항목 ${itemIndex + 1} 이미지 등록 중... (${files.length}개)`);
    const progressWrap = document.getElementById('erp-attachments-progress');
    const progressBar = document.getElementById('erp-attachments-progress-bar');
    if (progressWrap) progressWrap.classList.remove('d-none');
    const totalFiles = files.length;
    let ok = 0;
    if (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD) {
        let sessionMap = {};
        try {
            const bRes = await fetch('/api/upload/session/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: files.map(f => ({ filename: f.name, size: f.size })),
                    folder: `orders/${ORDER_ID}/measurement`,
                    category: 'measurement'
                })
            });
            const bData = await bRes.json();
            if (bData.success && bData.sessions) {
                for (let s of bData.sessions) s.success = true;
                for (let s of bData.sessions) sessionMap[s.filename] = s;
            }
        } catch (e) { }

        const CONCURRENCY = 10;
        for (let start = 0; start < files.length; start += CONCURRENCY) {
            const chunk = files.slice(start, start + CONCURRENCY);
            const results = await Promise.all(chunk.map(function (f) { return erpDoDirectUploadOne(f, 'measurement', itemIndex, sessionMap[f.name]); }));
            for (let i = 0; i < results.length; i++) {
                if (results[i] && results[i].success) ok += 1;
                else if (results[i]) console.warn('item upload failed', results[i]);
            }
            if (progressBar) {
                const done = Math.min(start + chunk.length, totalFiles);
                const p = Math.round((done / totalFiles) * 100);
                progressBar.style.width = p + '%';
                progressBar.textContent = p + '%';

                // Update optimistic cards
                chunk.forEach(f => {
                    const el = document.getElementById(f._optId);
                    if (el) {
                        const pctSpan = el.querySelector('.opt-pct');
                        if (pctSpan) pctSpan.textContent = '완료';
                    }
                });
            }
        }
    } else {
        for (let i = 0; i < files.length; i++) {
            const f = files[i];
            const fd = new FormData();
            fd.append('file', f);
            fd.append('category', 'measurement');
            fd.append('item_index', String(itemIndex));
            if (typeof uploadWithProgress !== 'undefined') {
                const data = await uploadWithProgress(`/api/orders/${ORDER_ID}/attachments`, fd, {
                    onProgress: (p) => {
                        if (progressBar) {
                            const totalPercent = Math.round(((i + p / 100) / totalFiles) * 100);
                            progressBar.style.width = totalPercent + '%';
                            progressBar.textContent = totalPercent + '%';
                        }
                    }
                });
                if (data.success) ok += 1;
                else console.warn('item upload failed', data);
            } else {
                const res = await fetch(`/api/orders/${ORDER_ID}/attachments`, { method: 'POST', body: fd });
                const data = await res.json();
                if (data.success) ok += 1;
                else console.warn('item upload failed', data);
            }
        }
    }
    if (progressWrap) progressWrap.classList.add('d-none');
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
    erpAttachmentsSetStatus(`제품 항목 ${itemIndex + 1} 신속 등록 완료: ${ok}/${files.length}`);
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

function erpRenderItemAttachmentPanels() {
    const rows = erpGetItemRows();
    const measurementItems = (__erpAttachments || []).filter((a) => erpNormalizeAttachmentCategory(a.category) === 'measurement');
    rows.forEach((row, idx) => {
        const wrap = row.querySelector('.erp-item-attachments-gallery');
        if (!wrap) return;
        const linked = measurementItems.filter((a) => erpParseAttachmentItemIndex(a.item_index) === idx);
        if (!linked.length) {
            wrap.innerHTML = '<div class="small text-muted">연결된 실측 이미지가 없습니다.</div>';
            return;
        }
        wrap.innerHTML = linked.map((a) => {
            const thumb = a.thumbnail_view_url || a.view_url || '';
            const name = escapeHtml(a.filename || '');
            return `
<div class="border rounded bg-white p-1 d-flex align-items-center gap-1" style="max-width: 200px;">
<img src="${thumb}" alt="${name}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;cursor:zoom-in;"
    onclick="erpOpenAttachmentPreview('${a.id}')">
<div class="small text-truncate flex-grow-1" style="max-width: 80px;" title="${name}">${name}</div>
<div class="d-flex gap-1">
    <button type="button" class="btn btn-sm btn-outline-secondary" title="공통으로 이동"
        onclick="erpLinkAttachmentToItem('${a.id}', '')">
        <i class="fas fa-unlink"></i>
    </button>
    <button type="button" class="btn btn-sm btn-outline-danger" title="삭제(공통 첨부에서도 제거)"
        onclick="erpDeleteAttachment('${a.id}')">
        <i class="fas fa-trash"></i>
    </button>
</div>
</div>`;
        }).join('');
    });
}

function erpRenderAttachments() {
    const wrap = document.getElementById('erp-attachments-gallery');
    if (!wrap) return;
    const items = Array.isArray(__erpAttachments) ? __erpAttachments : [];
    if (!items.length) {
        wrap.innerHTML = `<div class="col-12">
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

    const renderCard = (a) => {
        const name = escapeHtml(a.filename || '');
        const type = a.file_type || 'file';
        const thumb = a.thumbnail_view_url || a.view_url;
        const viewUrl = a.view_url || '#';
        const downloadUrl = a.download_url || '#';
        const category = erpNormalizeAttachmentCategory(a.category);

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
        ${category === 'measurement' ? `
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
                <button class="btn btn-outline-danger" type="button" title="삭제"
                    onclick="erpDeleteAttachment('${a.id}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    </div>
</div>
</div>
`;
    };

    const order = ['measurement', 'drawing', 'construction', 'as'];
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
    } catch (e) {
        console.error(e);
        erpAttachmentsSetStatus(String(e?.message || e), true);
    }
}

function erpOpenAttachmentPreview(attachmentId) {
    const targetId = Number(attachmentId);
    const a = (__erpAttachments || []).find(x => Number(x.id) === targetId);
    if (!a) return;
    const modalEl = document.getElementById('erpAttachmentPreviewModal');
    const body = document.getElementById('erp-attachment-preview-body');
    const dl = document.getElementById('erp-attachment-preview-download');
    if (!modalEl || !body || !dl) return;

    const viewUrl = a.view_url || '#';
    const downloadUrl = a.download_url || '#';
    dl.href = downloadUrl;

    if (a.file_type === 'video') {
        body.innerHTML = `
<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">
<video src="${viewUrl}" controls autoplay style="width:100%;height:100%;"></video>
</div>
<div class="small text-muted mt-2">${escapeHtml(a.filename || '')}</div>
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
<img src="${viewUrl}" alt="${escapeHtml(a.filename || '')}" class="img-fluid rounded"
style="background:#fff; padding:4px;">
<div class="small text-muted mt-2">${escapeHtml(a.filename || '')}</div>
`;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    var storageKey = a.storage_key || (a.download_url && String(a.download_url).replace(/^\/api\/files\/download\//, ''));
    if (storageKey) {
        var presignedPath = storageKey.split('/').map(function (s) { return encodeURIComponent(s); }).join('/');
        fetch('/api/files/presigned-urls/' + presignedPath)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                if (data.download_url) {
                    dl.href = data.download_url;
                    var downloadLink = body.querySelector('a.btn-primary') || body.querySelector('a[href*="download"]');
                    if (downloadLink) downloadLink.href = data.download_url;
                }
                if (data.view_url) {
                    var img = body.querySelector('img');
                    if (img) img.src = data.view_url;
                    var video = body.querySelector('video');
                    if (video) video.src = data.view_url;
                }
            })
            .catch(function () { });
    }
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

async function erpUploadSelectedAttachments() {
    if (!ERP_ORDER_ENABLED) return;
    const input = document.getElementById('erp-attachments-input');
    if (!input || !input.files || input.files.length === 0) {
        erpAttachmentsSetStatus('업로드할 파일을 선택하세요.', true);
        return;
    }
    const files = Array.from(input.files);
    if (!await erpEnsureFinalizedOrderForAction('첨부 업로드')) {
        return;
    }
    const categoryEl = document.getElementById('erp-attachments-category');
    const category = erpNormalizeAttachmentCategory(categoryEl ? categoryEl.value : 'measurement');
    // --- Optimistic UI Start ---
    const galleryWrap = document.getElementById('erp-attachments-gallery');
    if (galleryWrap) {
        files.forEach((f, fi) => {
            const uniqueId = 'opt-ul-gen-' + Date.now() + '-' + fi;
            f._optId = uniqueId;
            const name = escapeHtml(f.name);
            let previewUrl = '';
            try { previewUrl = URL.createObjectURL(f); } catch (e) { }

            const placeholderHtml = `
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

    erpAttachmentsSetStatus(`업로드 중... (${files.length}개)`);

    const progressWrap = document.getElementById('erp-attachments-progress');
    const progressBar = document.getElementById('erp-attachments-progress-bar');
    if (progressWrap) progressWrap.classList.remove('d-none');
    const totalFiles = files.length;

    let ok = 0;
    if (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD) {
        let sessionMap = {};
        try {
            const folder = `orders/${ORDER_ID}/${category || 'attachments'}`;
            const bRes = await fetch('/api/upload/session/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: files.map(f => ({ filename: f.name, size: f.size })),
                    folder: folder,
                    category: category
                })
            });
            const bData = await bRes.json();
            if (bData.success && bData.sessions) {
                for (let s of bData.sessions) s.success = true;
                for (let s of bData.sessions) sessionMap[s.filename] = s;
            }
        } catch (e) { }

        const CONCURRENCY = 10;
        for (let start = 0; start < files.length; start += CONCURRENCY) {
            const chunk = files.slice(start, start + CONCURRENCY);
            const results = await Promise.all(chunk.map(function (f) { return erpDoDirectUploadOne(f, category, null, sessionMap[f.name]); }));
            for (let i = 0; i < results.length; i++) {
                if (results[i] && results[i].success) ok += 1;
                else if (results[i]) console.warn('upload failed', results[i]);
            }
            if (progressBar) {
                const done = Math.min(start + chunk.length, totalFiles);
                const p = Math.round((done / totalFiles) * 100);
                progressBar.style.width = p + '%';
                progressBar.textContent = p + '%';

                // Update optimistic cards
                chunk.forEach(f => {
                    const el = document.getElementById(f._optId);
                    if (el) {
                        const pctSpan = el.querySelector('.opt-pct');
                        if (pctSpan) pctSpan.textContent = '완료';
                    }
                });
            }
        }
    } else {
        for (let i = 0; i < files.length; i++) {
            const f = files[i];
            const fd = new FormData();
            fd.append('file', f);
            fd.append('category', category);
            if (typeof uploadWithProgress !== 'undefined') {
                const data = await uploadWithProgress(`/api/orders/${ORDER_ID}/attachments`, fd, {
                    onProgress: (p) => {
                        if (progressBar) {
                            const totalPercent = Math.round(((i + p / 100) / totalFiles) * 100);
                            progressBar.style.width = totalPercent + '%';
                            progressBar.textContent = totalPercent + '%';
                        }
                    }
                });
                if (data.success) ok += 1;
                else console.warn('upload failed', data);
            } else {
                const res = await fetch(`/api/orders/${ORDER_ID}/attachments`, { method: 'POST', body: fd });
                const data = await res.json();
                if (data.success) ok += 1;
                else console.warn('upload failed', data);
            }
        }
    }

    if (progressWrap) progressWrap.classList.add('d-none');
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }

    input.value = '';
    erpAttachmentsSetStatus(`업로드 완료: ${ok}/${files.length}`);
    await erpLoadAttachments();
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
function erpGenerateConversionText() {
    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? (el.value || '').trim() : '';
    };

    const formatDateToKorean = (dateStr) => {
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
    };

    let measurementDate = getVal('erp-measurement-date');
    measurementDate = formatDateToKorean(measurementDate);

    // 시간: select가 직접입력이면 input 값 사용
    let measurementTime = '';
    const timeSelect = document.getElementById('erp-measurement-time-select');
    if (timeSelect) {
        if (timeSelect.value === '__direct__') {
            measurementTime = getVal('erp-measurement-time');
        } else {
            measurementTime = timeSelect.value;
        }
    }

    const customerName = getVal('erp-customer-name');
    let orderer = typeof getOrdererValue === 'function' ? getOrdererValue() : getVal('erp-orderer');
    if (!orderer) orderer = '라홈'; // Default

    let constructionDate = getVal('erp-construction-date');
    if (!constructionDate) constructionDate = '상담'; // Default
    else constructionDate = formatDateToKorean(constructionDate);

    let constructionTime = '';
    const constructionTimeSelect = document.getElementById('erp-construction-time-select');
    if (constructionTimeSelect) {
        if (constructionTimeSelect.value === '__direct__') {
            constructionTime = getVal('erp-construction-time');
        } else {
            constructionTime = constructionTimeSelect.value;
        }
    }

    const address = getVal('erp-address');
    const phone = getVal('erp-customer-phone');

    // Header
    let text = `실측일 : ${measurementDate}\n`;
    text += `시   간 : ${measurementTime}\n`;
    text += `\n`;
    text += `고객명 : ${customerName}\n`;
    text += `발주사 : ${orderer}\n`;
    text += `시공일 : ${constructionDate}\n`;
    text += `시공시간 : ${constructionTime}\n`;
    text += `주  소 : ${address}\n`;
    text += `연락처 : ${phone}\n`;
    text += `\n`;

    // Items
    const rows = erpGetItemRows();
    const itemCount = rows.length;
    const allExtraInputs = [];

    rows.forEach((row, index) => {
        const getRowVal = (key) => {
            const el = row.querySelector(`[data-erp="${key}"]`);
            return el ? (el.value || '').trim() : '';
        };

        const extraInput = getRowVal('extra_input');
        if (extraInput) allExtraInputs.push(extraInput);

        const pName = getRowVal('product_name');
        // Spec: 다중 행 수집 (W합/표시용은 출고 대시보드에서 처리)
        const specParts = [];
        row.querySelectorAll('.erp-spec-row').forEach(sr => {
            const w = (sr.querySelector('[data-erp="spec_width"]')?.value ?? '').trim();
            const d = (sr.querySelector('[data-erp="spec_depth"]')?.value ?? '').trim();
            const h = (sr.querySelector('[data-erp="spec_height"]')?.value ?? '').trim();
            const one = [w, d, h].filter(Boolean).join('*');
            if (one) specParts.push(one);
        });
        const spec = specParts.length ? specParts.join(', ') : '';

        let internal = getRowVal('internal');
        if (!internal) internal = '상담';

        let color = getRowVal('color');
        // if (!color) color = '(SK)'; // (SK) 표시 안 되게 임시 주석 처리

        let option = getRowVal('option_detail');
        if (!option) option = '상담';

        let handle = getRowVal('handle');

        let misc = getRowVal('misc');
        if (!misc) misc = '상담';

        if (itemCount >= 2) {
            text += `${index + 1}.\n`;
        }

        text += `제품명 : ${pName}\n`;
        text += `규 격 : ${spec}\n`;
        text += `내 부 : ${internal}\n`;
        text += `색 상 : ${color}\n`;
        text += `옵 션 : ${option}\n`;
        text += `손잡이 : ${handle}\n`;
        text += `기 타 : ${misc}\n`;
        text += `\n`;
    });

    // 추가 입력 (기타 <-> 선결제금액 사이)
    if (allExtraInputs.length > 0) {
        const extraBlock = allExtraInputs.join('\n');
        text += `추가 입력 : ${extraBlock}\n`;
        text += `\n`;
    }

    // Footer: 예약금(선금) 값이 있으면 잔금을 함께 표시, 없으면 기존 선결제금액 표시
    const depositEl = document.getElementById('erp-deposit-amount');
    const depositVal = depositEl ? (depositEl.value || '').trim() : '';
    const totalText = document.getElementById('erp-items-total')?.textContent || '0원';
    const depositAmount = erpCoerceAmount(depositVal);
    if (depositAmount > 0) {
        const balanceText = erpFormatMoneyKRW(Math.max(0, erpCoerceAmount(totalText) - depositAmount));
        text += `예약금 : ${erpFormatMoneyKRW(depositAmount)}\n`;
        text += `잔금 : ${balanceText}`;
    } else {
        text += `선결제금액 : ${totalText}`;
    }

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
            html += '<div class="measurement-item-header d-flex align-items-center justify-content-between gap-1 w-100 flex-nowrap" role="button">';
            html += '<span class="measurement-panel-date">' + escapeHtml(item.date) + '</span>';
            html += '<span class="measurement-panel-day">(' + escapeHtml(item.day_label) + ')</span>';
            html += badges.join('');
            html += '<span class="badge badge-count ms-auto">' + item.count + '</span>';
            html += '</div>';
            
            if (item.cases && item.cases.length > 0) {
                html += '<div class="measurement-cases-list d-none mt-2 pt-2 border-top">';
                item.cases.forEach(function(c) {
                    const t = escapeHtml(c.time || '');
                    const n = escapeHtml(c.customer_name || '이름없음');
                    const a = escapeHtml(c.address || '-');
                    const timeBadge = t ? `<span class="badge bg-secondary me-1" style="font-size:0.7rem;">${t}</span>` : `<span class="badge bg-light text-secondary border me-1" style="font-size:0.7rem;">시간미정</span>`;
                    html += `<div class="small mb-1 text-muted"><div class="fw-semibold text-dark d-flex align-items-center">${timeBadge} ${n}</div><div style="padding-left:0.5rem; font-size:0.8rem; line-height:1.2;">- ${a}</div></div>`;
                });
                html += '</div>';
            }
            
            html += '</div>';
        });
        panel.innerHTML = html;
        panel.classList.add('measurement-panel-list');
        panel.querySelectorAll('.measurement-panel-item').forEach(function (el) {
            const header = el.querySelector('.measurement-item-header');
            if (header) {
                header.addEventListener('click', function (e) {
                    const dateStr = el.dataset.date;
                    if (!dateStr) return;
                    
                    // 날짜 스타일 토글 여부는 주소 목록을 토글하는 것으로 대체, 
                    // 하지만 시각적으로 어느 것을 눌렀는지 표시하기 위해 active 상태 토글 추가
                    if (el.classList.contains('is-selected')) {
                        el.classList.remove('is-selected');
                    } else {
                        panel.querySelectorAll('.measurement-panel-item').forEach(function (x) { x.classList.remove('is-selected'); });
                        el.classList.add('is-selected');
                    }
                    
                    const casesList = el.querySelector('.measurement-cases-list');
                    if (casesList) {
                        casesList.classList.toggle('d-none');
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

    // 실패/예외 경로에서도 surface가 영구 hidden으로 남지 않도록 최후 failsafe.
    var _erpReadyFailsafeId = window.setTimeout(_erpMarkSurfaceReady, 3000);

    function initErpMainDatePickers() {
        const mEl = document.getElementById('erp-measurement-date');
        const cEl = document.getElementById('erp-construction-date');
        if (typeof flatpickr !== 'function') return;
        const opts = { mode: 'multiple', dateFormat: 'Y-m-d', locale: 'ko', allowInput: true };
        if (mEl && !mEl._flatpickr) {
            window._erpMeasurementDatePicker = flatpickr(mEl, opts);
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
    }
    window.erpInitFlatpickrForItemRow = function (row) {
        if (typeof flatpickr !== 'function') return;
        (row.querySelectorAll('.erp-item-date-multiple') || []).forEach(function (el) {
            if (el._flatpickr) return;
            flatpickr(el, { mode: 'multiple', dateFormat: 'Y-m-d', locale: 'ko', allowInput: true });
        });
    };

    document.getElementById('erp-attachments-upload-btn')?.addEventListener('click', erpUploadSelectedAttachments);
    document.getElementById('erp-gen-text-btn')?.addEventListener('click', erpGenerateConversionText);
    document.getElementById('erp-copy-text-btn')?.addEventListener('click', erpCopyToClipboard);

    document.getElementById('erp-channeltalk-push-btn')?.addEventListener('click', async function() {
        const btn = this;

        if (typeof erpGenerateConversionText === 'function') {
            erpGenerateConversionText();
        }
        const text = (document.getElementById('erp-conversion-text')?.value || '').trim();
        if (!text) {
            alert('변환할 내용이 없습니다. 주문 정보를 입력해주세요.');
            return;
        }

        let orderId = (typeof ORDER_ID !== 'undefined' && ORDER_ID > 0) ? ORDER_ID : 0;
        if (!orderId || erpIsDraftBackedOrder()) {
            const saveRes = await erpSaveStructured({ redirect: false });
            if (!saveRes.success) {
                alert(saveRes.message || '저장 실패. 푸쉬를 위해 저장이 필요합니다.');
                return;
            }
            orderId = (typeof ORDER_ID !== 'undefined' && ORDER_ID > 0) ? ORDER_ID : 0;
        }
        if (!orderId) {
            alert('주문 ID를 확보할 수 없습니다.');
            return;
        }

        btn.disabled = true;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 전송중...';

        try {
            const resp = await fetch('/api/channel/push-manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order_id: orderId, text }),
            });
            const data = await resp.json();

            if (data.success) {
                btn.innerHTML = '<i class="fas fa-check"></i> 전송완료';
                btn.classList.replace('btn-primary', 'btn-success');
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                    btn.classList.replace('btn-success', 'btn-primary');
                    btn.disabled = false;
                }, 3000);
            } else {
                const errMsg = data.error || '알 수 없는 오류';
                alert(`채널톡 전송 실패:\n${errMsg}`);
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        } catch (e) {
            alert(`네트워크 오류: ${e.message}`);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    });

    initErpMainDatePickers();

    loadMeasurementPanel();
    if (!window.__fomsErpMeasurementIntervalId) {
        window.__fomsErpMeasurementIntervalId = window.setInterval(loadMeasurementPanel, 30000);
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
        if (isErpOrderDraftMode() && (!ORDER_ID || ORDER_ID <= 0)) {
            const now = new Date();
            const localDateStr = [
                now.getFullYear(),
                String(now.getMonth() + 1).padStart(2, '0'),
                String(now.getDate()).padStart(2, '0')
            ].join('-');
            const localTimeStr = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');

            const rd = document.getElementById('erp-received-date');
            const rt = document.getElementById('erp-received-time');
            if (rd) rd.value = localDateStr;
            if (rt) rt.value = localTimeStr;
            const stageEl = document.getElementById('erp-workflow-stage');
            if (stageEl && !stageEl.value) stageEl.value = 'RECEIVED';
            syncWorkflowStageByOrderer();
        }
        if (ORDER_ID && ORDER_ID > 0) {
            // 탭 전환 시에는 이미 부트스트랩을 소비했을 수 있으므로 서버 최신 상태를 재조회한다.
            await erpLoadStructured();
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

        __erpQuest = data.quest;
        erpRenderQuest();

        if (data.all_approved) {
            if (data.auto_transitioned && data.next_stage) {
                const nextStageLabel = erpLabel(ERP_STAGE_LABELS, data.next_stage, data.next_stage);
                erpSetQuestStatus(`✅ 모든 팀 승인 완료! 다음 단계(${nextStageLabel})로 자동 전환되었습니다.`);
                setTimeout(() => {
                    erpLoadQuest(); // 새 Quest 로드
                    erpLoadStructured(); // structured_data도 새로고침
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
