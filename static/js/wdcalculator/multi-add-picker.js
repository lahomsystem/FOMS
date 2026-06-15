/**
 * WDCalculator 복수선택 일괄 추가 피커 (PC 모달 + 모바일 바텀시트 공통).
 *
 * 목적: 추가옵션·비고를 "한 줄씩 1:1"로 추가하던 방식을 대체.
 *       카테고리 아코디언에서 여러 옵션을 체크박스로 복수 선택한 뒤 "추가"로 한 번에 행 생성.
 *
 * 설계: 기존 단일 추가 경로(appendAdditionalOptionRow / addNoteItem)와 데이터 계약을 그대로 재사용.
 *       이 모듈은 "입력 수단"만 일괄화하며, 생성된 행은 기존과 동일하게 편집/삭제/직접입력 가능.
 *       category-picker.js(단일 select 강화)와 충돌하지 않도록 별도 wd-madd-* 네임스페이스 사용.
 *
 * 데이터 출처:
 *   - 옵션: window.wdCalculatorCategories = [{ name, options: [{ name, price }] }]
 *   - 비고: window.notesCategories (= wdNotesCategories) = [{ name, options: [{ name }] }]
 *
 * 의존: WdCalculatorAdditionalOptionsUI.appendAdditionalOptionRow, WdCalculatorNotesUI.addNotesBulk.
 * fail-safe: 의존 모듈이 없으면 open* 호출 시 false 반환 → 호출측이 기존 단일 추가로 폴백.
 */
(function () {
    "use strict";

    var overlay = null;
    var state = {
        mode: null, // "options" | "notes"
        selected: null, // Map<key, payload>
    };

    function isMobile() {
        return !!(window.matchMedia && window.matchMedia("(max-width: 991.98px)").matches);
    }

    function escapeHtmlSafe(value) {
        if (typeof window.escapeHtml === "function") {
            return window.escapeHtml(value);
        }
        var div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function formatNumberSafe(value) {
        if (typeof window.formatNumber === "function") {
            return window.formatNumber(value);
        }
        return Math.round(Number(value) || 0).toLocaleString("ko-KR");
    }

    /* ---- 데이터 모델 빌드 ---- */

    function buildOptionsModel() {
        var groups = [];
        var categories = window.wdCalculatorCategories || [];
        categories.forEach(function (category) {
            if (!(category && Array.isArray(category.options) && category.options.length)) return;
            var items = [];
            category.options.forEach(function (option) {
                if (!(option && option.name && option.price !== undefined)) return;
                var key = category.name + "|" + option.name + "|" + option.price;
                items.push({
                    key: key,
                    label: option.name,
                    meta: formatNumberSafe(option.price) + "원",
                    payload: {
                        // select.value 인코딩(category|name|price)을 그대로 matchedValue로 사용
                        matchedValue: key,
                        name: category.name + " > " + option.name,
                        price: Math.max(0, parseFloat(option.price) || 0),
                    },
                });
            });
            if (items.length) groups.push({ label: category.name, items: items });
        });
        return groups;
    }

    function buildNotesModel() {
        var groups = [];
        var categories = window.notesCategories || window.wdNotesCategories || [];
        categories.forEach(function (category) {
            if (!(category && Array.isArray(category.options) && category.options.length)) return;
            var items = [];
            category.options.forEach(function (option) {
                if (!(option && option.name)) return;
                var value = category.name + " > " + option.name;
                items.push({
                    key: value,
                    label: option.name,
                    meta: "",
                    payload: { value: value },
                });
            });
            if (items.length) groups.push({ label: category.name, items: items });
        });
        return groups;
    }

    /* ---- 커밋(일괄 추가) ---- */

    function commitOptions() {
        var ui = window.WdCalculatorAdditionalOptionsUI;
        var container = document.getElementById("additionalOptionsContainer");
        if (!ui || typeof ui.appendAdditionalOptionRow !== "function" || !container) return;
        var lastItem = null;
        var base = Date.now();
        var idx = 0;
        state.selected.forEach(function (payload) {
            lastItem = ui.appendAdditionalOptionRow(container, {
                optionId: "opt_" + base + "_" + idx++,
                option: { name: payload.name, price: payload.price, quantity: 1 },
                matchedValue: payload.matchedValue,
                forceMode: "select",
                formatPriceOnInput: false,
            });
        });
        // 행 추가만으로는 재계산이 트리거되지 않으므로 마지막 행의 가격 input에 input 이벤트 디스패치.
        if (lastItem) {
            var priceInput = lastItem.querySelector("[data-option-price]");
            if (priceInput) {
                try {
                    priceInput.dispatchEvent(new Event("input", { bubbles: true }));
                } catch (e) {
                    /* older engines: ignore */
                }
            }
        }
    }

    function commitNotes() {
        var notesUi = window.WdCalculatorNotesUI;
        if (!notesUi || typeof notesUi.addNotesBulk !== "function") return;
        var values = [];
        state.selected.forEach(function (payload) {
            values.push(payload.value);
        });
        notesUi.addNotesBulk(values);
    }

    /* ---- 오버레이 DOM ---- */

    function ensureOverlay() {
        if (overlay) return overlay;

        var backdrop = document.createElement("div");
        backdrop.className = "wd-madd-backdrop";
        backdrop.addEventListener("click", close);

        var panel = document.createElement("div");
        panel.className = "wd-madd-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "true");

        var head = document.createElement("div");
        head.className = "wd-madd-panel__head";
        var titleEl = document.createElement("span");
        titleEl.className = "wd-madd-panel__title";
        var closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "wd-madd-panel__close";
        closeBtn.setAttribute("aria-label", "닫기");
        closeBtn.textContent = "✕";
        closeBtn.addEventListener("click", close);
        head.appendChild(titleEl);
        head.appendChild(closeBtn);

        var searchWrap = document.createElement("div");
        searchWrap.className = "wd-madd-panel__search";
        var searchInput = document.createElement("input");
        searchInput.type = "text";
        searchInput.className = "wd-madd-search-input";
        searchInput.setAttribute("placeholder", "검색…");
        searchInput.addEventListener("input", function () {
            applyFilter(searchInput.value);
        });
        searchWrap.appendChild(searchInput);

        var body = document.createElement("div");
        body.className = "wd-madd-panel__body";

        var footer = document.createElement("div");
        footer.className = "wd-madd-panel__foot";
        var manualBtn = document.createElement("button");
        manualBtn.type = "button";
        manualBtn.className = "wd-madd-btn wd-madd-btn--ghost";
        manualBtn.textContent = "직접입력 행";
        manualBtn.addEventListener("click", function () {
            addManualRow();
            close();
        });
        var addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "wd-madd-btn wd-madd-btn--primary";
        addBtn.addEventListener("click", confirm);
        footer.appendChild(manualBtn);
        footer.appendChild(addBtn);

        panel.appendChild(head);
        panel.appendChild(searchWrap);
        panel.appendChild(body);
        panel.appendChild(footer);
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);

        overlay = {
            backdrop: backdrop,
            panel: panel,
            titleEl: titleEl,
            searchInput: searchInput,
            body: body,
            addBtn: addBtn,
        };

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && overlay && overlay.panel.classList.contains("is-open")) {
                close();
            }
        });
        return overlay;
    }

    function makeCheckRow(item) {
        var row = document.createElement("label");
        row.className = "wd-madd-opt";
        row.setAttribute("data-search", (item.label + " " + item.meta).toLowerCase());

        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "wd-madd-opt__cb";
        cb.checked = state.selected.has(item.key);

        var text = document.createElement("span");
        text.className = "wd-madd-opt__label";
        text.textContent = item.label;

        var meta = document.createElement("span");
        meta.className = "wd-madd-opt__meta";
        meta.textContent = item.meta || "";

        cb.addEventListener("change", function () {
            if (cb.checked) {
                state.selected.set(item.key, item.payload);
                row.classList.add("is-checked");
            } else {
                state.selected.delete(item.key);
                row.classList.remove("is-checked");
            }
            updateFooter();
        });

        if (cb.checked) row.classList.add("is-checked");
        row.appendChild(cb);
        row.appendChild(text);
        row.appendChild(meta);
        return row;
    }

    function expandGroup(groupEl, listEl, open) {
        groupEl.classList.toggle("is-open", open);
        listEl.style.maxHeight = open ? listEl.scrollHeight + "px" : "0px";
    }

    function renderGroups(groups) {
        var body = overlay.body;
        body.innerHTML = "";
        if (!groups.length) {
            var empty = document.createElement("div");
            empty.className = "wd-madd-empty";
            empty.textContent = "등록된 항목이 없습니다. 제품 설정에서 추가하세요.";
            body.appendChild(empty);
            return;
        }
        groups.forEach(function (g, gi) {
            var groupEl = document.createElement("div");
            groupEl.className = "wd-madd-group";

            var header = document.createElement("button");
            header.type = "button";
            header.className = "wd-madd-group__head";
            header.innerHTML =
                '<span class="wd-madd-group__name"></span>' +
                '<span class="wd-madd-group__meta">' +
                '<span class="wd-madd-group__count"></span>' +
                '<span class="wd-madd-group__chev">▾</span></span>';
            header.querySelector(".wd-madd-group__name").textContent = g.label;
            header.querySelector(".wd-madd-group__count").textContent = g.items.length + "개";

            var list = document.createElement("div");
            list.className = "wd-madd-group__list";
            g.items.forEach(function (item) {
                list.appendChild(makeCheckRow(item));
            });

            header.addEventListener("click", function () {
                expandGroup(groupEl, list, !groupEl.classList.contains("is-open"));
            });

            groupEl.appendChild(header);
            groupEl.appendChild(list);
            body.appendChild(groupEl);
            // 첫 그룹은 펼쳐서 보여줌(빈 화면 방지)
            expandGroup(groupEl, list, gi === 0);
        });
    }

    function applyFilter(query) {
        if (!overlay) return;
        var q = (query || "").trim().toLowerCase();
        var groups = overlay.body.querySelectorAll(".wd-madd-group");
        for (var i = 0; i < groups.length; i++) {
            var group = groups[i];
            var rows = group.querySelectorAll(".wd-madd-opt");
            var visibleCount = 0;
            for (var j = 0; j < rows.length; j++) {
                var match = !q || rows[j].getAttribute("data-search").indexOf(q) !== -1;
                rows[j].style.display = match ? "" : "none";
                if (match) visibleCount++;
            }
            group.style.display = visibleCount ? "" : "none";
            var list = group.querySelector(".wd-madd-group__list");
            if (q) {
                // 검색 중엔 매칭 그룹을 모두 펼침
                expandGroup(group, list, visibleCount > 0);
            }
        }
    }

    function updateFooter() {
        if (!overlay) return;
        var n = state.selected.size;
        overlay.addBtn.textContent = n > 0 ? "추가 (" + n + ")" : "추가";
        overlay.addBtn.disabled = n === 0;
    }

    function addManualRow() {
        if (state.mode === "options") {
            var ui = window.WdCalculatorAdditionalOptionsUI;
            var container = document.getElementById("additionalOptionsContainer");
            if (ui && typeof ui.appendAdditionalOptionRow === "function" && container) {
                ui.appendAdditionalOptionRow(container, { forceMode: "input", formatPriceOnInput: false });
            }
        } else if (state.mode === "notes") {
            var notesUi = window.WdCalculatorNotesUI;
            if (notesUi && typeof notesUi.addNotesBulk === "function") {
                // 빈 직접입력 비고 한 행 추가
                if (typeof window.addNoteItem === "function") {
                    window.addNoteItem("input");
                }
            }
        }
    }

    function open(mode, title) {
        // 이미 열려 있으면 재초기화 방지(빠른 더블클릭 시 선택 소실 차단)
        if (overlay && overlay.panel.classList.contains("is-open")) {
            return true;
        }
        // 의존 가드: 일괄 추가가 불가능하면 false 반환 → 호출측 폴백
        if (mode === "options") {
            if (!window.WdCalculatorAdditionalOptionsUI || !document.getElementById("additionalOptionsContainer")) {
                return false;
            }
        } else if (mode === "notes") {
            var notesUi = window.WdCalculatorNotesUI;
            if (!notesUi || typeof notesUi.addNotesBulk !== "function") {
                return false;
            }
        } else {
            return false;
        }

        var ov = ensureOverlay();
        state.mode = mode;
        state.selected = new Map();
        ov.titleEl.textContent = title;
        ov.searchInput.value = "";

        var groups = mode === "options" ? buildOptionsModel() : buildNotesModel();
        renderGroups(groups);
        updateFooter();

        ov.backdrop.classList.add("is-open");
        ov.panel.classList.add("is-open");
        ov.panel.classList.toggle("wd-madd-panel--sheet", isMobile());
        ov.panel.classList.toggle("wd-madd-panel--modal", !isMobile());
        document.body.classList.add("wd-madd-open");

        // 레이아웃 확정 후 열린 그룹 높이 보정
        var openLists = ov.panel.querySelectorAll(".wd-madd-group.is-open .wd-madd-group__list");
        for (var k = 0; k < openLists.length; k++) {
            openLists[k].style.maxHeight = openLists[k].scrollHeight + "px";
        }
        return true;
    }

    function confirm() {
        if (!state.selected || state.selected.size === 0) return;
        var mode = state.mode;
        if (mode === "options") {
            commitOptions();
        } else if (mode === "notes") {
            commitNotes();
        }
        close();
    }

    function close() {
        if (!overlay) return;
        overlay.backdrop.classList.remove("is-open");
        overlay.panel.classList.remove("is-open");
        document.body.classList.remove("wd-madd-open");
        state.mode = null;
        state.selected = null;
    }

    window.WdCalculatorMultiAddPicker = {
        openOptions: function () {
            return open("options", "추가 옵션 선택");
        },
        openNotes: function () {
            return open("notes", "비고 선택");
        },
        close: close,
    };
})();
