/* W5-B3 primary-form.js — canonical chunk (merge of 7 modules; do not split without run record). */

/* --- included: notes-ui.js --- */
/**
 * WDCalculator notes UI — state, render, and events for the notes cluster.
 * Relies on wdcalculator_scripts_config.html for wdNotesCategories and on shared.js for escapeHtml.
 * Globals notesList / notesCategories are shared with the inline calculator orchestration script.
 */
var notesList = [];
var notesCategories = typeof notesCategories !== "undefined" ? notesCategories : [];

function loadNotesCategories() {
    notesCategories = wdNotesCategories || [];
}

function setNoteMode(selectEl, textareaEl, mode) {
    if (mode === "select") {
        selectEl.style.setProperty("display", "block", "important");
        selectEl.classList.remove("d-none");
        textareaEl.style.setProperty("display", "none", "important");
        textareaEl.classList.add("d-none");
    } else {
        selectEl.style.setProperty("display", "none", "important");
        selectEl.classList.add("d-none");
        textareaEl.style.setProperty("display", "block", "important");
        textareaEl.classList.remove("d-none");
    }
}

function createNotesSelectOptions() {
    // 카테고리는 optgroup 헤더로, 옵션 줄은 옵션명만 짧게.
    // value는 '카테고리 > 옵션명' 인코딩을 유지(loadNotes/collectNotes/renderNoteItem 매칭 근거).
    let optionsHtml = '<option value="">저장된 비고 선택</option>';
    if (notesCategories && Array.isArray(notesCategories)) {
        notesCategories.forEach((category) => {
            if (category && category.options && Array.isArray(category.options)) {
                let groupHtml = "";
                category.options.forEach((option) => {
                    if (option && option.name) {
                        const value = `${category.name} > ${option.name}`;
                        groupHtml += `<option value="${escapeHtml(value)}">${escapeHtml(option.name)}</option>`;
                    }
                });
                if (groupHtml) {
                    optionsHtml += `<optgroup label="${escapeHtml(category.name)}">${groupHtml}</optgroup>`;
                }
            }
        });
    }
    return optionsHtml;
}

function addNoteItem(type) {
    type = type || "select";
    var index = notesList.length;
    notesList.push({ type: type, value: "" });
    renderNoteItem(index);
}

function removeNoteItem(index) {
    if (notesList.length <= 1) {
        return;
    }
    notesList.splice(index, 1);
    renderAllNotes();
}

function toggleNoteType(index) {
    if (index >= 0 && index < notesList.length) {
        var currentType = notesList[index].type;
        var currentValue = notesList[index].value;
        notesList[index].type = currentType === "select" ? "input" : "select";
        notesList[index].value = currentValue;
        renderNoteItem(index);
    }
}

function renderNoteItem(index) {
    const container = document.getElementById("notesContainer");
    if (!container) return;

    const note = notesList[index];
    if (!note) return;

    const noteId = `note-item-${index}`;

    let noteItem = document.getElementById(noteId);
    if (noteItem) {
        noteItem.remove();
    }

    let optionValue = "";
    if (note.value && note.type === "select") {
        if (wdNotesCategories && Array.isArray(wdNotesCategories)) {
            for (const category of wdNotesCategories) {
                if (category && category.options && Array.isArray(category.options)) {
                    for (const option of category.options) {
                        if (option && option.name) {
                            const fullValue = `${category.name} > ${option.name}`;
                            if (fullValue === note.value) {
                                optionValue = fullValue;
                                break;
                            }
                        }
                    }
                    if (optionValue) break;
                }
            }
        }
    }

    let finalIsSelect = note.type === "select";
    if (finalIsSelect && note.value && !optionValue) {
        const isActuallyOption = checkIfOptionExists(note.value);
        if (!isActuallyOption) {
            notesList[index].type = "input";
            finalIsSelect = false;
        }
    }

    noteItem = document.createElement("div");
    noteItem.className = "note-item mb-2";
    noteItem.id = noteId;
    noteItem.setAttribute("data-note-index", index);

    noteItem.innerHTML = `
            <div class="d-flex gap-2 align-items-start">
                <button type="button" class="btn btn-sm btn-outline-secondary toggle-note-type" data-note-index="${index}" title="${finalIsSelect ? "직접입력" : "옵션 선택"}">
                    <i class="fas ${finalIsSelect ? "fa-keyboard" : "fa-list"}"></i>
                </button>
                <select class="form-select flex-grow-1 note-select" data-note-index="${index}">
                    ${createNotesSelectOptions()}
                </select>
                <textarea class="form-control note-input" rows="2" placeholder="비고를 직접 입력하세요" data-note-index="${index}"></textarea>
                <button type="button" class="btn btn-sm btn-outline-danger remove-note" data-note-index="${index}" title="삭제" ${notesList.length <= 1 ? "disabled" : ""}>
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

    container.appendChild(noteItem);

    const select = noteItem.querySelector(".note-select");
    const textarea = noteItem.querySelector(".note-input");

    setNoteMode(select, textarea, finalIsSelect ? "select" : "input");

    if (finalIsSelect && select) {
        select.value = optionValue || "";
    } else if (textarea) {
        textarea.value = note.value || "";
    }

    attachNoteItemEvents(noteItem, index);
}

function attachNoteItemEvents(noteItem, index) {
    var toggleBtn = noteItem.querySelector(".toggle-note-type");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleNoteType(index);
        });
    }

    var removeBtn = noteItem.querySelector(".remove-note");
    if (removeBtn) {
        removeBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            removeNoteItem(index);
        });
    }

    var select = noteItem.querySelector(".note-select");
    if (select) {
        select.addEventListener("change", function () {
            if (index >= 0 && index < notesList.length) {
                notesList[index].value = this.value;
                notesList[index].type = "select";
            }
        });
    }

    var textarea = noteItem.querySelector(".note-input");
    if (textarea) {
        textarea.addEventListener("input", function () {
            if (index >= 0 && index < notesList.length) {
                notesList[index].value = this.value;
                notesList[index].type = "input";
            }
        });

        textarea.addEventListener("blur", function () {
            var formatted = formatNumbersInText(this.value);
            if (formatted !== this.value) {
                this.value = formatted;
                if (index >= 0 && index < notesList.length) {
                    notesList[index].value = formatted;
                }
            }
        });
    }
}

function renderAllNotes() {
    var container = document.getElementById("notesContainer");
    if (!container) return;

    container.innerHTML = "";

    if (notesList.length === 0) {
        addNoteItem("select");
        return;
    }

    notesList.forEach(function (_note, index) {
        renderNoteItem(index);
    });
}

function collectNotes() {
    return notesList
        .map(function (item) {
            return item.value;
        })
        .filter(function (v) {
            return v && v.trim();
        })
        .join("\n");
}

function loadNotes(notesString) {
    if (!notesString || !notesString.trim()) {
        notesList = [{ type: "select", value: "" }];
        renderAllNotes();
        return;
    }

    if (!notesCategories || notesCategories.length === 0) {
        loadNotesCategories();
        if (!notesCategories || notesCategories.length === 0) {
            setTimeout(function () {
                loadNotesCategories();
                if (notesCategories && notesCategories.length > 0) {
                    loadNotes(notesString);
                }
            }, 100);
            return;
        }
    }

    var lines = notesString.split("\n").filter(function (v) {
        return v.trim();
    });

    if (lines.length === 0) {
        notesList = [{ type: "select", value: "" }];
        renderAllNotes();
        return;
    }

    notesList = lines.map(function (value) {
        value = value.trim();
        var isOption = checkIfOptionExists(value);
        return {
            type: isOption ? "select" : "input",
            value: value,
        };
    });

    renderAllNotes();
}

function checkIfOptionExists(value) {
    if (!value || !notesCategories) {
        return false;
    }

    for (var i = 0; i < notesCategories.length; i++) {
        var category = notesCategories[i];
        if (category && category.options && Array.isArray(category.options)) {
            for (var j = 0; j < category.options.length; j++) {
                var option = category.options[j];
                if (option && option.name) {
                    var optionValue = category.name + " > " + option.name;
                    if (optionValue === value) {
                        return true;
                    }
                }
            }
        }
    }
    return false;
}

function formatNumbersInText(text) {
    return text.replace(/\d{4,}/g, function (match) {
        var num = Number(match);
        return Number.isFinite(num) ? num.toLocaleString("ko-KR") : match;
    });
}

function formatNotesText(notes) {
    if (!notes || !notes.trim()) {
        return "";
    }
    return notes
        .split("\n")
        .map(function (line) {
            return line.trim();
        })
        .join("\n");
}

function resetNotesToEmpty() {
    notesList = [{ type: "select", value: "" }];
    renderAllNotes();
}

function initNotesUi() {
    loadNotesCategories();

    var btnAddNote = document.getElementById("btnAddNote");
    if (btnAddNote) {
        btnAddNote.addEventListener("click", function () {
            addNoteItem("select");
        });
    }

    notesList = [{ type: "select", value: "" }];
    renderAllNotes();
}

window.WdCalculatorNotesUI = {
    initNotesUi: initNotesUi,
    resetNotesToEmpty: resetNotesToEmpty,
    loadNotesCategories: loadNotesCategories,
    collectNotes: collectNotes,
    loadNotes: loadNotes,
    formatNotesText: formatNotesText,
    formatNumbersInText: formatNumbersInText,
    renderAllNotes: renderAllNotes,
};

/* --- included: base-components-ui.js --- */
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
        // 카테고리별 optgroup으로 묶고, 카테고리 → 제품명 순으로 정렬해 노출한다.
        // 카테고리가 없는 제품은 그룹 없이 평평하게 먼저 노출(하위호환 + 계약 보존).
        var html = '<option value="">제품을 선택하세요</option>';
        var products = (getProducts() || []).filter(function (p) {
            return !!p;
        });
        var grouped = {};
        var uncategorized = [];

        function byName(a, b) {
            return String(a.name || "").localeCompare(String(b.name || ""), "ko");
        }
        function optionHtml(p) {
            var optionValue = escapeHtml(String(p.id != null ? p.id : ""));
            return '<option value="' + optionValue + '">' + escapeHtml(p.name || "") + "</option>";
        }

        products.forEach(function (p) {
            var category = p.category != null ? String(p.category).trim() : "";
            if (!category) {
                uncategorized.push(p);
                return;
            }
            if (!grouped[category]) {
                grouped[category] = [];
            }
            grouped[category].push(p);
        });

        uncategorized.sort(byName).forEach(function (p) {
            html += optionHtml(p);
        });
        Object.keys(grouped)
            .sort(function (a, b) {
                return a.localeCompare(b, "ko");
            })
            .forEach(function (category) {
                html += '<optgroup label="' + escapeHtml(category) + '">';
                grouped[category].sort(byName).forEach(function (p) {
                    html += optionHtml(p);
                });
                html += "</optgroup>";
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
            '">\n                                    </div>\n                                </div>\n                                \n                            </div>\n                        </div>\n\n                        <!-- 가로 (직접: 마지막 / 선택: 제품 다음) -->\n                        <div class="col-6 col-md-3 base-width-col">\n                            <label class="form-label small mb-1">가로(mm)</label>\n                            <input type="number" class="form-control form-control-sm base-width-input" min="0" step="1" placeholder="예: 4470" value="' +
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

/* --- included: coupon-display-helpers.js --- */
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

/* --- included: additional-options-ui.js --- */
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
        // 카테고리는 optgroup 헤더로 한 번만 노출하고, 옵션 줄은 '옵션명 (가격원)'으로 짧게.
        // value는 'category|name|price' 인코딩을 그대로 유지(선택 시 이름/가격 분해에 사용).
        var html = '<option value="">카테고리 > 옵션을 선택하세요</option>';
        var categories = getCategories() || [];
        categories.forEach(function (category) {
            if (!(category && Array.isArray(category.options) && category.options.length)) return;
            var groupHtml = "";
            category.options.forEach(function (option) {
                if (!(option && option.name && option.price !== undefined)) return;
                groupHtml +=
                    '<option value="' +
                    category.name +
                    "|" +
                    option.name +
                    "|" +
                    option.price +
                    '">' +
                    option.name +
                    " (" +
                    formatNumber(option.price) +
                    "원)</option>";
            });
            if (groupHtml) {
                html += '<optgroup label="' + category.name + '">' + groupHtml + "</optgroup>";
            }
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

/* --- included: add-option-button.js --- */
(function () {
    var WdCalculatorAddOptionButton = window.WdCalculatorAddOptionButton || {};

    (function (ns) {
        var documentRef = typeof document !== "undefined" ? document : null;
        var appendAdditionalOptionRow = function () {};

        function configure(options) {
            var opts = options || {};
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.appendAdditionalOptionRow === "function") {
                appendAdditionalOptionRow = opts.appendAdditionalOptionRow;
            }
        }

        function handleAddOptionButtonClick() {
            var container = documentRef.getElementById("additionalOptionsContainer");
            appendAdditionalOptionRow(container, {
                forceMode: "select",
                formatPriceOnInput: false,
            });
        }

        function initAddOptionButton() {
            var addOptionBtn = documentRef.getElementById("addOptionBtn");
            if (!addOptionBtn) {
                return;
            }
            addOptionBtn.addEventListener("click", handleAddOptionButtonClick);
        }

        ns.configure = configure;
        ns.handleAddOptionButtonClick = handleAddOptionButtonClick;
        ns.initAddOptionButton = initAddOptionButton;
    })(WdCalculatorAddOptionButton);

    window.WdCalculatorAddOptionButton = WdCalculatorAddOptionButton;
})();

/* --- included: calculate-button.js --- */
(function () {
    var WdCalculatorCalculateButton = window.WdCalculatorCalculateButton || {};

    (function (ns) {
        var documentRef = typeof document !== "undefined" ? document : null;
        var calculateEstimate = function () {};

        function configure(options) {
            var opts = options || {};
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
        }

        function handleCalculateButtonClick() {
            calculateEstimate();
        }

        function initCalculateButton() {
            var calculateBtn = documentRef.getElementById("calculateBtn");
            if (!calculateBtn) {
                return;
            }
            calculateBtn.addEventListener("click", handleCalculateButtonClick);
        }

        ns.configure = configure;
        ns.handleCalculateButtonClick = handleCalculateButtonClick;
        ns.initCalculateButton = initCalculateButton;
    })(WdCalculatorCalculateButton);

    window.WdCalculatorCalculateButton = WdCalculatorCalculateButton;
})();

/* --- included: product-catalog-ui.js --- */
/**
 * WDCalculator product catalog legacy UI.
 * Depends on shared.js (escapeHtml, formatNumber).
 * Host keeps products state and bootstrap orchestration.
 */
var WdCalculatorProductCatalogUI = window.WdCalculatorProductCatalogUI || {};

(function (ns) {
    var getProducts = function () {
        return [];
    };
    var setProducts = function () {};
    var getCalculateEstimate = function () {
        return function () {};
    };
    var updateBaseProductSelectOptions = function () {};
    var ensureBaseComponentsUI = function () {};

    /**
     * @param {{
     *   getProducts?: () => Array<object>,
     *   setProducts?: (products: Array<object>) => void,
     *   getCalculateEstimate?: () => function,
     *   updateBaseProductSelectOptions?: () => void,
     *   ensureBaseComponentsUI?: () => void
     * }} opts
     */
    function configure(opts) {
        if (opts && typeof opts.getProducts === "function") {
            getProducts = opts.getProducts;
        }
        if (opts && typeof opts.setProducts === "function") {
            setProducts = opts.setProducts;
        }
        if (opts && typeof opts.getCalculateEstimate === "function") {
            getCalculateEstimate = opts.getCalculateEstimate;
        }
        if (opts && typeof opts.updateBaseProductSelectOptions === "function") {
            updateBaseProductSelectOptions = opts.updateBaseProductSelectOptions;
        }
        if (opts && typeof opts.ensureBaseComponentsUI === "function") {
            ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
        }
    }

    function syncBaseComponentsAfterProductsLoad() {
        if (!document.getElementById("baseComponentsContainer")) return;
        updateBaseProductSelectOptions();
        if (document.querySelectorAll(".base-component-row").length === 0) {
            ensureBaseComponentsUI();
        }
    }

    function loadProducts() {
        return fetch("/api/wdcalculator/products")
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    setProducts(data.products);
                    ns.updateProductSelect();
                    syncBaseComponentsAfterProductsLoad();
                    return data.products;
                }
                return null;
            })
            .catch(function (error) {
                console.error("Error loading products:", error);
                return null;
            });
    }

    function updateProductSelect() {
        var select = document.getElementById("productSelect");
        if (!select) return;
        select.innerHTML = '<option value="">제품을 선택하세요</option>';
        (getProducts() || []).forEach(function (product) {
            var option = document.createElement("option");
            option.value = product.id;
            option.textContent = product.name;
            select.appendChild(option);
        });
    }

    function showProductInfo(product) {
        var infoDiv = document.getElementById("productInfo");
        var contentDiv = document.getElementById("productInfoContent");

        if (!infoDiv || !contentDiv) {
            console.warn("제품 정보 표시 요소를 찾을 수 없습니다.");
            return;
        }

        if (!product) {
            console.warn("제품 정보가 없습니다.");
            infoDiv.style.display = "none";
            return;
        }

        var infoHtml = "<div><strong>" + escapeHtml(product.name || "") + "</strong></div>";
        infoHtml += "<div>가격 옵션: " + (product.pricing_type === "1m" ? "1m" : "30cm") + "</div>";

        if (product.pricing_type === "1m") {
            infoHtml += "<div>1m 비용: " + formatNumber(product.price_1m || 0) + "원</div>";
        } else {
            infoHtml += "<div>30cm 비용: " + formatNumber(product.price_30cm || 0) + "원</div>";
            infoHtml += "<div>1cm 비용: " + formatNumber(product.price_1cm || 0) + "원</div>";
        }

        if (product.additional_options && product.additional_options.length > 0) {
            infoHtml += '<div class="mt-2"><strong>사용 가능한 추가 옵션:</strong></div>';
            product.additional_options.forEach(function (option) {
                infoHtml +=
                    "<div>- " +
                    escapeHtml(option.name || "") +
                    ": " +
                    formatNumber(option.price || 0) +
                    "원</div>";
            });
            infoHtml +=
                '<div class="mt-1"><small class="text-muted">※ 견적 계산 시 드롭다운에서 선택하거나 직접 입력할 수 있습니다.</small></div>';
        }

        contentDiv.innerHTML = infoHtml;
        infoDiv.style.display = "block";
    }

    function handleProductSelectChange(event) {
        var target = event && event.currentTarget ? event.currentTarget : this;
        var productId = parseInt(target.value);
        var product = (getProducts() || []).find(function (item) {
            return item.id === productId;
        });

        document.getElementById("additionalOptionsContainer").innerHTML = "";

        if (product) {
            ns.showProductInfo(product);
        } else {
            document.getElementById("productInfo").style.display = "none";
            document.getElementById("baseEstimateSection").style.display = "none";
        }

        var calculateEstimate = getCalculateEstimate();
        if (typeof calculateEstimate === "function") {
            calculateEstimate();
        }
    }

    function bindProductSelect() {
        var productSelect = document.getElementById("productSelect");
        if (!productSelect) return;
        productSelect.addEventListener("change", handleProductSelectChange);
    }

    ns.configure = configure;
    ns.loadProducts = loadProducts;
    ns.updateProductSelect = updateProductSelect;
    ns.showProductInfo = showProductInfo;
    ns.handleProductSelectChange = handleProductSelectChange;
    ns.bindProductSelect = bindProductSelect;
})(WdCalculatorProductCatalogUI);

window.WdCalculatorProductCatalogUI = WdCalculatorProductCatalogUI;
