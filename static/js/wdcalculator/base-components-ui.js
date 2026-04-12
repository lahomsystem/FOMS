/**
 * WDCalculator base-components UI: product select / manual pricing rows, additional fees.
 * Depends on shared.js (escapeHtml, computeAutoPrice1cmFrom30cm).
 * Call WdCalculatorBaseComponentsUI.configure({ getProducts, getCalculateEstimate }) from the host
 * after host state exists (products array, calculateEstimate).
 */
var WdCalculatorBaseComponentsUI = window.WdCalculatorBaseComponentsUI || {};

(function (ns) {
    var getProducts = function () {
        return [];
    };
    var getCalculateEstimate = function () {
        return function () {};
    };
    var documentRef = document;
    var liveInteractionsBound = false;

    /**
     * @param {{ getProducts?: () => Array<{id:number,name?:string}>, getCalculateEstimate?: () => function, documentRef?: Document }} opts
     */
    function configure(opts) {
        if (opts && typeof opts.getProducts === "function") {
            getProducts = opts.getProducts;
        }
        if (opts && typeof opts.getCalculateEstimate === "function") {
            getCalculateEstimate = opts.getCalculateEstimate;
        }
        if (opts && opts.documentRef) {
            documentRef = opts.documentRef;
        }
    }

    function triggerCalculateEstimate() {
        var fn = getCalculateEstimate();
        if (typeof fn === "function") {
            fn();
        }
    }

    function getProductsOptionsHtml() {
        var html = '<option value="">제품을 선택하세요</option>';
        var products = getProducts() || [];
        products.forEach(function (p) {
            if (!p) return;
            var optionValue = escapeHtml(String(p.id != null ? p.id : ""));
            html += '<option value="' + optionValue + '">' + escapeHtml(p.name || "") + "</option>";
        });
        return html;
    }

    function renderBaseComponentRow(component = {}) {
        var mode = component.mode || "select";
        var manualPricingType = (component.manualPricing && component.manualPricing.pricing_type) || "30cm";
        var widthMm = component.widthMm != null ? component.widthMm : "";
        var productId = component.productId != null ? component.productId : "";
        var price30 = (component.manualPricing && component.manualPricing.price_30cm) != null
            ? component.manualPricing.price_30cm
            : "";
        var price1 =
            (component.manualPricing && component.manualPricing.price_1cm) != null
                ? component.manualPricing.price_1cm
                : price30
                  ? computeAutoPrice1cmFrom30cm(price30)
                  : 0;
        var price1m = (component.manualPricing && component.manualPricing.price_1m) != null
            ? component.manualPricing.price_1m
            : "";
        var additionalFees =
            component.additionalFees ||
            (component.additionalFee ? [{ name: "", amount: component.additionalFee }] : []);

        return (
            '\n            <div class="card mb-2 border-light base-component-row" data-mode="' +
            mode +
            '">\n                <div class="card-body py-2">\n                    <!-- 첫 번째 행: 방식, 제품/직접입력, 가로, 삭제 -->\n                    <div class="row g-2 align-items-end">\n                        <!-- 방식 -->\n                        <div class="col-6 col-md-2">\n                            <label class="form-label small mb-1">방식</label>\n                            <div class="btn-group w-100" role="group">\n                                <button type="button" class="btn btn-sm ' +
            (mode === "select" ? "btn-info" : "btn-outline-info") +
            ' base-mode-btn" data-mode="select">선택</button>\n                                <button type="button" class="btn btn-sm ' +
            (mode === "manual" ? "btn-warning" : "btn-outline-warning") +
            ' base-mode-btn" data-mode="manual">직접</button>\n                            </div>\n                        </div>\n\n                        <!-- 선택/직접 상세 영역 (항상 같은 컬럼을 차지해서 남는 공간 제거) -->\n                        <div class="col-12 col-md-6 base-details-area">\n                            <!-- 제품(선택 모드) -->\n                            <div class="base-select-area" style="' +
            (mode === "manual" ? "display:none;" : "") +
            '">\n                                <label class="form-label small mb-1">제품</label>\n                                <select class="form-select form-select-sm base-product-select">\n                                    ' +
            getProductsOptionsHtml() +
            '\n                                </select>\n                            </div>\n\n                            <!-- 직접입력(직접 모드) -->\n                            <div class="base-manual-area" style="' +
            (mode === "manual" ? "" : "display:none;") +
            '">\n                                <div class="row g-2 align-items-end">\n                                    <div class="col-4">\n                                        <label class="form-label small mb-1">단가 방식</label>\n                                        <select class="form-select form-select-sm base-manual-pricing-type">\n                                            <option value="30cm" ' +
            (manualPricingType === "30cm" ? "selected" : "") +
            '>30cm/1cm</option>\n                                            <option value="1m" ' +
            (manualPricingType === "1m" ? "selected" : "") +
            '>1m</option>\n                                        </select>\n                                    </div>\n                                    <div class="col-5 base-manual-30cm-col" style="' +
            (manualPricingType === "1m" ? "display:none;" : "") +
            '">\n                                        <label class="form-label small mb-1">30cm(원)</label>\n                                        <input type="number" class="form-control form-control-sm base-manual-price30" min="0" step="1" placeholder="예: 187000" value="' +
            escapeHtml(String(price30)) +
            '">\n                                    </div>\n                                    <div class="col-3 base-manual-1cm-col" style="' +
            (manualPricingType === "1m" ? "display:none;" : "") +
            '">\n                                        <label class="form-label small mb-1">1cm(자동)</label>\n                                        <input type="number" class="form-control form-control-sm base-manual-price1" min="0" step="10" readonly value="' +
            escapeHtml(String(price1)) +
            '">\n                                    </div>\n                                    <div class="col-8 base-manual-1m-col" style="' +
            (manualPricingType === "1m" ? "" : "display:none;") +
            '">\n                                        <label class="form-label small mb-1">1m(원)</label>\n                                        <input type="number" class="form-control form-control-sm base-manual-price1m" min="0" step="1" placeholder="예: 330000" value="' +
            escapeHtml(String(price1m)) +
            '">\n                                    </div>\n                                </div>\n                                \n                            </div>\n                        </div>\n\n                        <!-- 가로 (직접: 마지막 / 선택: 제품 다음) -->\n                        <div class="col-6 col-md-3">\n                            <label class="form-label small mb-1">가로(mm)</label>\n                            <input type="number" class="form-control form-control-sm base-width-input" min="0" step="1" placeholder="예: 4470" value="' +
            escapeHtml(String(widthMm)) +
            '">\n                        </div>\n\n                        <!-- 삭제 -->\n                        <div class="col-6 col-md-1 text-end">\n                            <button type="button" class="btn btn-sm btn-outline-danger base-remove-btn" title="삭제">\n                                <i class="fas fa-times"></i>\n                            </button>\n                        </div>\n                    </div>\n                    \n                    <!-- 두 번째 행: 추가금 입력 (리스트 형태) -->\n                    <div class="mt-2">\n                        <label class="form-label small mb-2">추가금</label>\n                        <div class="base-additional-fees-list">\n                            ' +
            additionalFees
                .map(function (fee, idx) {
                    return (
                        '\n                                <div class="row g-2 align-items-end mb-2 base-additional-fee-item">\n                                    <div class="col-12 col-md-5">\n                                        <input type="text" class="form-control form-control-sm base-additional-fee-name" placeholder="제품명 입력" value="' +
                        escapeHtml(fee.name || "") +
                        '">\n                                    </div>\n                        <div class="col-12 col-md-4">\n                                        <input type="number" class="form-control form-control-sm base-additional-fee-amount" min="0" step="1" placeholder="금액 (원)" value="' +
                        escapeHtml(String(fee.amount || "")) +
                        '">\n                        </div>\n                                    <div class="col-12 col-md-3 text-end">\n                                        <button type="button" class="btn btn-sm btn-outline-danger base-remove-fee-btn" title="삭제">\n                                            <i class="fas fa-times"></i>\n                                        </button>\n                                    </div>\n                                </div>\n                            '
                    );
                })
                .join("") +
            '\n                        </div>\n                        <div class="mt-2">\n                            <button type="button" class="btn btn-sm btn-outline-primary base-add-fee-btn">\n                                <i class="fas fa-plus"></i> 추가금 추가\n                            </button>\n                        </div>\n                    </div>\n                </div>\n            </div>\n        '
        );
    }

    function ensureBaseComponentsUI(components = null) {
        var container = documentRef.getElementById("baseComponentsContainer");
        if (!container) return;
        container.innerHTML = "";
        var list =
            components && Array.isArray(components) && components.length
                ? components
                : [{ mode: "select" }];
        container.innerHTML = list
            .map(function (c) {
                return renderBaseComponentRow(c);
            })
            .join("");
        container.querySelectorAll(".base-component-row").forEach(function (rowEl, idx) {
            var comp = list[idx] || {};
            var sel = rowEl.querySelector(".base-product-select");
            if (sel && comp.productId) {
                sel.value = String(comp.productId);
            }
        });
        bindAdditionalFeeEvents();
    }

    function readBaseComponentsFromUI() {
        var container = documentRef.getElementById("baseComponentsContainer");
        if (!container) return [];
        var rows = Array.from(container.querySelectorAll(".base-component-row"));
        return rows.map(function (rowEl) {
            var mode = rowEl.dataset.mode || "select";
            var widthMm = Number(rowEl.querySelector(".base-width-input") && rowEl.querySelector(".base-width-input").value) || 0;
            var additionalFees = [];
            rowEl.querySelectorAll(".base-additional-fee-item").forEach(function (itemEl) {
                var name =
                    (itemEl.querySelector(".base-additional-fee-name") &&
                        itemEl.querySelector(".base-additional-fee-name").value &&
                        itemEl.querySelector(".base-additional-fee-name").value.trim()) ||
                    "";
                var amount =
                    Number(
                        itemEl.querySelector(".base-additional-fee-amount") &&
                            itemEl.querySelector(".base-additional-fee-amount").value
                    ) || 0;
                if (name || amount > 0) {
                    additionalFees.push({ name: name, amount: amount });
                }
            });
            if (mode === "manual") {
                var pricingType =
                    (rowEl.querySelector(".base-manual-pricing-type") &&
                        rowEl.querySelector(".base-manual-pricing-type").value) ||
                    "30cm";
                if (pricingType === "1m") {
                    var price1m =
                        Number(rowEl.querySelector(".base-manual-price1m") && rowEl.querySelector(".base-manual-price1m").value) ||
                        0;
                    return {
                        mode: mode,
                        widthMm: widthMm,
                        additionalFees: additionalFees,
                        manualPricing: { pricing_type: "1m", price_1m: price1m },
                    };
                }
                var price30 =
                    Number(rowEl.querySelector(".base-manual-price30") && rowEl.querySelector(".base-manual-price30").value) ||
                    0;
                var auto1 = computeAutoPrice1cmFrom30cm(price30);
                var price1El = rowEl.querySelector(".base-manual-price1");
                if (price1El) price1El.value = String(auto1);
                return {
                    mode: mode,
                    widthMm: widthMm,
                    additionalFees: additionalFees,
                    manualPricing: {
                        pricing_type: "30cm",
                        price_30cm: price30,
                        price_1cm: auto1,
                    },
                };
            }
            var productId =
                Number(rowEl.querySelector(".base-product-select") && rowEl.querySelector(".base-product-select").value) ||
                null;
            return { mode: mode, widthMm: widthMm, additionalFees: additionalFees, productId: productId };
        });
    }

    function bindAdditionalFeeEvents() {
        // Compatibility no-op: host script owns delegated fee input/remove handling.
    }

    function updateBaseProductSelectOptions() {
        var optionHtml = getProductsOptionsHtml();
        documentRef.querySelectorAll(".base-component-row .base-product-select").forEach(function (sel) {
            var prev = sel.value;
            sel.innerHTML = optionHtml;
            if (prev) sel.value = prev;
        });
    }

    function handleAddBaseComponentClick() {
        var container = documentRef.getElementById("baseComponentsContainer");
        if (!container) return;
        container.insertAdjacentHTML("beforeend", renderBaseComponentRow({ mode: "select" }));
        triggerCalculateEstimate();
    }

    function handleBaseComponentsContainerClick(e) {
        var rowEl = e.target.closest(".base-component-row");

        if (e.target.closest(".base-add-fee-btn")) {
            if (!rowEl) return;
            var feesList = rowEl.querySelector(".base-additional-fees-list");
            if (feesList) {
                var newItem = documentRef.createElement("div");
                newItem.className = "row g-2 align-items-end mb-2 base-additional-fee-item";
                newItem.innerHTML = `
                    <div class="col-12 col-md-5">
                        <input type="text" class="form-control form-control-sm base-additional-fee-name" placeholder="제품명 입력" value="">
                    </div>
                    <div class="col-12 col-md-4">
                        <input type="number" class="form-control form-control-sm base-additional-fee-amount" min="0" step="1" placeholder="금액 (원)" value="">
                    </div>
                    <div class="col-12 col-md-3 text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger base-remove-fee-btn" title="삭제">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
                feesList.appendChild(newItem);
                triggerCalculateEstimate();
            }
            return;
        }

        if (e.target.closest(".base-remove-fee-btn")) {
            var feeItem = e.target.closest(".base-additional-fee-item");
            if (feeItem) {
                feeItem.remove();
                triggerCalculateEstimate();
            }
            return;
        }

        if (!rowEl) return;

        var modeBtn = e.target.closest(".base-mode-btn");
        if (modeBtn) {
            var newMode = modeBtn.dataset.mode;
            rowEl.dataset.mode = newMode;
            var selectArea = rowEl.querySelector(".base-select-area");
            var manualArea = rowEl.querySelector(".base-manual-area");
            if (selectArea) selectArea.style.display = newMode === "manual" ? "none" : "";
            if (manualArea) manualArea.style.display = newMode === "manual" ? "" : "none";
            rowEl.querySelectorAll(".base-mode-btn").forEach(function (btn) {
                var mode = btn.dataset.mode;
                btn.classList.remove("btn-info", "btn-outline-info", "btn-warning", "btn-outline-warning");
                if (mode === "select") {
                    btn.classList.add(mode === newMode ? "btn-info" : "btn-outline-info");
                }
                if (mode === "manual") {
                    btn.classList.add(mode === newMode ? "btn-warning" : "btn-outline-warning");
                }
            });
            triggerCalculateEstimate();
            return;
        }

        var removeBtn = e.target.closest(".base-remove-btn");
        if (removeBtn) {
            var container = documentRef.getElementById("baseComponentsContainer");
            var rows = container ? container.querySelectorAll(".base-component-row") : [];
            if (rows.length <= 1) {
                return;
            }
            rowEl.remove();
            triggerCalculateEstimate();
        }
    }

    function handleBaseComponentsContainerInput(e) {
        var rowEl = e.target.closest(".base-component-row");
        if (!rowEl) return;
        if (e.target.classList.contains("base-manual-price30")) {
            var price30 = Number(e.target.value) || 0;
            var auto1 = computeAutoPrice1cmFrom30cm(price30);
            var price1El = rowEl.querySelector(".base-manual-price1");
            if (price1El) price1El.value = String(auto1);
        }
        triggerCalculateEstimate();
    }

    function handleBaseComponentsContainerChange(e) {
        var rowEl = e.target.closest(".base-component-row");
        if (!rowEl) return;
        if (e.target.classList.contains("base-manual-pricing-type")) {
            var pricingType = e.target.value || "30cm";
            var col30 = rowEl.querySelector(".base-manual-30cm-col");
            var col1 = rowEl.querySelector(".base-manual-1cm-col");
            var col1m = rowEl.querySelector(".base-manual-1m-col");
            if (pricingType === "1m") {
                if (col30) col30.style.display = "none";
                if (col1) col1.style.display = "none";
                if (col1m) col1m.style.display = "";
            } else {
                if (col30) col30.style.display = "";
                if (col1) col1.style.display = "";
                if (col1m) col1m.style.display = "none";
                var price30El = rowEl.querySelector(".base-manual-price30");
                var auto1 = computeAutoPrice1cmFrom30cm(Number(price30El && price30El.value) || 0);
                var price1El = rowEl.querySelector(".base-manual-price1");
                if (price1El) price1El.value = String(auto1);
            }
        }
        triggerCalculateEstimate();
    }

    function initBaseComponentsLiveInteractions() {
        if (liveInteractionsBound) return;
        var addBtn = documentRef.getElementById("addBaseComponentBtn");
        var container = documentRef.getElementById("baseComponentsContainer");
        if (addBtn) {
            addBtn.addEventListener("click", handleAddBaseComponentClick);
        }
        if (container) {
            container.addEventListener("click", handleBaseComponentsContainerClick);
            container.addEventListener("input", handleBaseComponentsContainerInput);
            container.addEventListener("change", handleBaseComponentsContainerChange);
        }
        liveInteractionsBound = true;
    }

    ns.configure = configure;
    ns.getProductsOptionsHtml = getProductsOptionsHtml;
    ns.renderBaseComponentRow = renderBaseComponentRow;
    ns.ensureBaseComponentsUI = ensureBaseComponentsUI;
    ns.readBaseComponentsFromUI = readBaseComponentsFromUI;
    ns.bindAdditionalFeeEvents = bindAdditionalFeeEvents;
    ns.updateBaseProductSelectOptions = updateBaseProductSelectOptions;
    ns.initBaseComponentsLiveInteractions = initBaseComponentsLiveInteractions;
    ns.handleAddBaseComponentClick = handleAddBaseComponentClick;
    ns.handleBaseComponentsContainerClick = handleBaseComponentsContainerClick;
    ns.handleBaseComponentsContainerInput = handleBaseComponentsContainerInput;
    ns.handleBaseComponentsContainerChange = handleBaseComponentsContainerChange;
})(WdCalculatorBaseComponentsUI);

window.WdCalculatorBaseComponentsUI = WdCalculatorBaseComponentsUI;
