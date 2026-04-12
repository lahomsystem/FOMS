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

var _erpNormalizePaymentData =
    window._erpNormalizePaymentData ||
    function _erpNormalizePaymentData(sd) {
        if (!sd) sd = {};
        var pay = sd.payment || {};

        var depositAmount = Number(pay.deposit) || 0;
        if (!depositAmount && sd.payments && sd.payments.deposit && sd.payments.deposit.amount) {
            depositAmount = Number(sd.payments.deposit.amount) || 0;
        }

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
        if (!ERP_BETA_ENABLED) return 0;
        if (!window.__ERP_BETA_DRAFT_MODE) return ORDER_ID || 0;
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
                if (window.__ERP_BETA_DRAFT_MODE && ORDER_ID && ORDER_ID > 0) {
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
        var digits = String(el.value || "").replace(/[^0-9]/g, "");
        return digits ? parseInt(digits, 10) : 0;
    };
window.erpParseDepositValue = erpParseDepositValue;

var erpFormatDepositDisplay =
    window.erpFormatDepositDisplay ||
    function erpFormatDepositDisplay(num) {
        if (num == null || !Number.isFinite(num) || num < 0) return "0원";
        return num === 0 ? "0원" : num.toLocaleString("ko-KR") + "원";
    };
window.erpFormatDepositDisplay = erpFormatDepositDisplay;
