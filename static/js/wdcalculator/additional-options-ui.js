/**
 * WDCalculator additional-options rows UI helpers.
 * Depends on shared.js (formatNumber, formatPrice, parsePrice, escapeHtml).
 */
var WdCalculatorAdditionalOptionsUI = window.WdCalculatorAdditionalOptionsUI || {};

(function (ns) {
    var getCategories = function () {
        return [];
    };
    var getCalculateEstimate = function () {
        return function () {};
    };

    /**
     * @param {{ getCategories?: () => Array, getCalculateEstimate?: () => function }} opts
     */
    function configure(opts) {
        if (opts && typeof opts.getCategories === "function") {
            getCategories = opts.getCategories;
        }
        if (opts && typeof opts.getCalculateEstimate === "function") {
            getCalculateEstimate = opts.getCalculateEstimate;
        }
    }

    function triggerCalculateEstimate() {
        var fn = getCalculateEstimate();
        if (typeof fn === "function") {
            fn();
        }
    }

    function getAllOptionsHtml() {
        var html = '<option value="">카테고리 > 옵션을 선택하세요</option>';
        var categories = getCategories() || [];
        categories.forEach(function (category) {
            if (!(category && Array.isArray(category.options) && category.options.length)) return;
            category.options.forEach(function (option) {
                if (!(option && option.name && option.price !== undefined)) return;
                html +=
                    '<option value="' +
                    category.name +
                    "|" +
                    option.name +
                    "|" +
                    option.price +
                    '">' +
                    category.name +
                    " > " +
                    option.name +
                    " (" +
                    formatNumber(option.price) +
                    "원)</option>";
            });
        });
        return html;
    }

    function setOptionMode(selectEl, nameInputEl, mode) {
        if (!selectEl || !nameInputEl) return;
        if (mode === "select") {
            selectEl.style.setProperty("display", "block", "important");
            selectEl.classList.remove("d-none");
            nameInputEl.style.setProperty("display", "none", "important");
            nameInputEl.classList.add("d-none");
            return;
        }
        selectEl.style.setProperty("display", "none", "important");
        selectEl.classList.add("d-none");
        nameInputEl.style.setProperty("display", "block", "important");
        nameInputEl.classList.remove("d-none");
    }

    function setToggleIcon(toggleBtn, mode) {
        if (!toggleBtn) return;
        toggleBtn.innerHTML =
            mode === "select"
                ? '<i class="fas fa-keyboard"></i>'
                : '<i class="fas fa-list"></i>';
    }

    function findMatchedValue(optionName) {
        if (!optionName) return "";
        var matchedValue = "";
        var categories = getCategories() || [];
        categories.some(function (category) {
            if (!(category && Array.isArray(category.options))) return false;
            var found = category.options.find(function (option) {
                return option && option.name === optionName && option.price !== undefined;
            });
            if (!found) return false;
            matchedValue = category.name + "|" + found.name + "|" + found.price;
            return true;
        });
        return matchedValue;
    }

    function renderAdditionalOptionRowHtml(optionId, optionName, optionPrice, optionQuantity) {
        return (
            '\n                <div class="additional-option-item" data-option-id="' +
            optionId +
            '">\n                    <div class="row gx-2 align-items-center">\n                        <div class="col-md-5">\n                            <label class="form-label small">카테고리 > 옵션 선택</label>\n                            <div class="d-flex gap-2 align-items-center">\n                                <button type="button" class="btn btn-sm btn-outline-secondary" data-toggle-direct-input title="직접입력">\n                                    <i class="fas fa-keyboard"></i>\n                                </button>\n                                <select class="form-select form-select-sm category-option-select flex-grow-1" data-category-option-select>\n                                    ' +
            getAllOptionsHtml() +
            '\n                                </select>\n                                <input type="text" class="form-control form-control-sm option-name-input flex-grow-1" placeholder="또는 옵션명 직접 입력 (예: 화장대 > 화장대A)" data-option-name value="' +
            escapeHtml(optionName || "") +
            '">\n                            </div>\n                        </div>\n                        <div class="col-md-3 price-col">\n                            <label class="form-label small">가격 (원)</label>\n                            <input type="text" class="form-control form-control-sm option-price-input" placeholder="가격을 입력하세요" data-option-price value="' +
            (optionPrice != null && optionPrice !== "" ? formatPrice(optionPrice) : "") +
            '" inputmode="numeric">\n                        </div>\n                        <div class="col-md-2 quantity-col">\n                            <label class="form-label small">수량</label>\n                            <input type="number" class="form-control form-control-sm option-quantity-input" placeholder="수량" min="1" step="1" value="' +
            Math.max(1, parseInt(optionQuantity, 10) || 1) +
            '" data-option-quantity>\n                        </div>\n                        <div class="col-md-2">\n                            <label class="form-label small" style="visibility: hidden;">작업</label>\n                            <button type="button" class="btn btn-sm btn-outline-danger remove-option-btn w-100" style="white-space: nowrap;">\n                                <i class="fas fa-times"></i> 삭제\n                            </button>\n                        </div>\n                    </div>\n                </div>\n            '
        );
    }

    function wireAdditionalOptionRow(item, opts) {
        if (!item) return null;
        var options = opts || {};
        var select = item.querySelector("[data-category-option-select]");
        var nameInput = item.querySelector("[data-option-name]");
        var priceInput = item.querySelector("[data-option-price]");
        var quantityInput = item.querySelector("[data-option-quantity]");
        var toggleBtn = item.querySelector("[data-toggle-direct-input]");
        var removeBtn = item.querySelector(".remove-option-btn");
        var matchedValue = options.matchedValue || "";
        var forceMode = options.forceMode || "";
        var initialMode = forceMode || (matchedValue ? "select" : "input");

        if (matchedValue && select) {
            select.value = matchedValue;
        } else if (select) {
            select.value = "";
        }
        setOptionMode(select, nameInput, initialMode);
        setTimeout(function () {
            setOptionMode(select, nameInput, initialMode);
        }, 0);
        setToggleIcon(toggleBtn, initialMode);

        if (select) {
            select.addEventListener("change", function () {
                if (this.value) {
                    var parts = this.value.split("|");
                    if (parts.length >= 3) {
                        nameInput.value = parts[0] + " > " + parts[1];
                        priceInput.value = formatPrice(parts[2]);
                        if (!quantityInput.value || quantityInput.value < 1) {
                            quantityInput.value = 1;
                        }
                    }
                    setOptionMode(select, nameInput, "select");
                    setToggleIcon(toggleBtn, "select");
                    triggerCalculateEstimate();
                    return;
                }
                nameInput.value = "";
                priceInput.value = "";
            });
        }

        if (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                var selectVisible = select.style.display !== "none";
                if (selectVisible) {
                    setOptionMode(select, nameInput, "input");
                    if (select) select.value = "";
                    nameInput.value = "";
                    priceInput.value = "";
                    setToggleIcon(toggleBtn, "input");
                } else {
                    setOptionMode(select, nameInput, "select");
                    nameInput.value = "";
                    priceInput.value = "";
                    setToggleIcon(toggleBtn, "select");
                }
                triggerCalculateEstimate();
            });
        }

        if (priceInput) {
            if (options.formatPriceOnInput) {
                priceInput.addEventListener("input", function () {
                    var cursorPosition = this.selectionStart;
                    var oldValue = this.value;
                    var formattedValue = formatPrice(this.value);
                    this.value = formattedValue;
                    var diff = formattedValue.length - oldValue.length;
                    var newPosition = Math.max(0, cursorPosition + diff);
                    if (typeof this.setSelectionRange === "function") {
                        this.setSelectionRange(newPosition, newPosition);
                    }
                    triggerCalculateEstimate();
                });
                priceInput.addEventListener("blur", function () {
                    if (this.value) {
                        this.value = formatPrice(this.value);
                    }
                });
            } else {
                priceInput.addEventListener("input", triggerCalculateEstimate);
            }
        }

        if (nameInput) {
            nameInput.addEventListener("input", triggerCalculateEstimate);
        }
        if (quantityInput) {
            quantityInput.addEventListener("input", triggerCalculateEstimate);
        }
        if (removeBtn) {
            removeBtn.addEventListener("click", function () {
                item.remove();
                triggerCalculateEstimate();
            });
        }

        return item;
    }

    function appendAdditionalOptionRow(container, opts) {
        if (!container) return null;
        var options = opts || {};
        var option = options.option || {};
        var optionId = options.optionId || Date.now();
        var matchedValue = options.matchedValue;
        if (matchedValue == null) {
            matchedValue = findMatchedValue(option.name || "");
        }

        container.insertAdjacentHTML(
            "beforeend",
            renderAdditionalOptionRowHtml(
                optionId,
                option.name || "",
                option.price != null ? Math.max(0, parseFloat(option.price) || 0) : "",
                option.quantity
            )
        );

        var item =
            container.querySelector('[data-option-id="' + optionId + '"]') ||
            container.lastElementChild;
        return wireAdditionalOptionRow(item, {
            matchedValue: matchedValue,
            forceMode: options.forceMode || "",
            formatPriceOnInput: !!options.formatPriceOnInput,
        });
    }

    function loadAdditionalOptionRows(container, options, opts) {
        if (!container || !Array.isArray(options) || !options.length) return;
        var extra = opts || {};
        options.forEach(function (option, idx) {
            if (!(option && option.name)) return;
            appendAdditionalOptionRow(container, {
                optionId: "opt_" + Date.now() + "_" + idx,
                option: option,
                formatPriceOnInput: !!extra.formatPriceOnInput,
            });
        });
    }

    function readAdditionalOptionRowsFromUI() {
        var rows = [];
        document.querySelectorAll(".additional-option-item").forEach(function (item) {
            var priceInput = item.querySelector("[data-option-price]");
            var nameInput = item.querySelector("[data-option-name]");
            var quantityInput = item.querySelector("[data-option-quantity]");
            var categoryOptionSelect = item.querySelector("[data-category-option-select]");
            var price = parsePrice(priceInput.value);
            var quantity = parseInt(quantityInput.value, 10) || 1;
            var name = "";
            if (
                categoryOptionSelect &&
                categoryOptionSelect.style.display !== "none" &&
                categoryOptionSelect.value &&
                categoryOptionSelect.value !== ""
            ) {
                var parts = categoryOptionSelect.value.split("|");
                if (parts.length >= 2) {
                    name = parts[0] + " > " + parts[1];
                }
            } else if (nameInput && nameInput.style.display !== "none" && nameInput.value) {
                name = nameInput.value;
            }
            if (name && price > 0) {
                rows.push({ name: name, price: price, quantity: quantity });
            }
        });
        return rows;
    }

    ns.configure = configure;
    ns.getAllOptionsHtml = getAllOptionsHtml;
    ns.setOptionMode = setOptionMode;
    ns.findMatchedValue = findMatchedValue;
    ns.renderAdditionalOptionRowHtml = renderAdditionalOptionRowHtml;
    ns.wireAdditionalOptionRow = wireAdditionalOptionRow;
    ns.appendAdditionalOptionRow = appendAdditionalOptionRow;
    ns.loadAdditionalOptionRows = loadAdditionalOptionRows;
    ns.readAdditionalOptionRowsFromUI = readAdditionalOptionRowsFromUI;
})(WdCalculatorAdditionalOptionsUI);

window.WdCalculatorAdditionalOptionsUI = WdCalculatorAdditionalOptionsUI;
