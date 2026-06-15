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
        var base = Date.now();
        var idx = 0;
        state.selected.forEach(function (payload) {
            ui.appendAdditionalOptionRow(container, {
                optionId: "opt_" + base + "_" + idx++,
                option: { name: payload.name, price: payload.price, quantity: 1 },
                matchedValue: payload.matchedValue,
                forceMode: "select",
                formatPriceOnInput: false,
            });
        });
    }

    /**
     * 일괄 추가 후 현재 견적을 즉시 재계산해 라이브 표시(견적 결과 카드 가격/모바일 FAB #finalPrice)를 갱신.
     * 행 입력 시 동작하는 표준 경로(calculateEstimate)와 동일하게 맞춘다.
     * (calculateTotalEstimates는 저장 견적이 없을 때 현재 요약을 0원으로 리셋하므로 호출하지 않음)
     */
    function triggerRecalc() {
        var orch = window.WdCalculatorCurrentEstimateOrchestration;
        if (orch && typeof orch.calculateEstimate === "function") {
            try {
                orch.calculateEstimate();
            } catch (e) {
                // calculateEstimate 내부에서 처리되지 못한 예외는 무음 억제하지 않고 로깅
                if (window.console && console.error) {
                    console.error("[multi-add-picker] 재계산 실패", e);
                }
            }
        }
    }

    /**
     * 견적을 편집 중이면(editingEstimateId 존재) 완료 버튼을 누르기 전에도
     * 일괄 추가한 옵션/비고가 진행중 견적 카드에 즉시 반영되도록 한다.
     * - 현재 폼 → estimates 배열의 편집 대상 항목 갱신(updateExistingEstimate)
     * - 해당 카드만 in-place 재렌더(refreshEstimateCard) → 모바일 인라인 에디터 무손상
     * 편집 중이 아니면(신규 작성) 카드가 아직 없으므로 아무 동작 안 함.
     */
    function syncEditingEstimateCard() {
        var editIdState = window.WdCalculatorEditingEstimateId;
        var estState = window.WdCalculatorEstimatesState;
        var addEst = window.WdCalculatorAddEstimate;
        var orch = window.WdCalculatorCurrentEstimateOrchestration;
        var renderer = window.WdCalculatorRenderEstimatesList;
        if (!editIdState || typeof editIdState.getEditingEstimateId !== "function") return;
        var editingId = editIdState.getEditingEstimateId();
        if (!editingId) return;
        if (!orch || typeof orch.collectCurrentEstimate !== "function") return;
        if (!estState || typeof estState.getEstimates !== "function") return;
        if (!addEst || typeof addEst.updateExistingEstimate !== "function") return;
        if (!renderer || typeof renderer.refreshEstimateCard !== "function") return;

        var estimate = orch.collectCurrentEstimate();
        if (!estimate) return;
        var estimates = estState.getEstimates();
        if (!Array.isArray(estimates)) return;

        var index = -1;
        for (var i = 0; i < estimates.length; i++) {
            if (String(estimates[i].id) === String(editingId)) {
                index = i;
                break;
            }
        }
        if (index === -1) return;

        addEst.updateExistingEstimate(estimates, index, estimate);
        renderer.refreshEstimateCard(editingId);
    }

    var editingCardSyncTimer = null;
    function scheduleEditingCardSync() {
        if (editingCardSyncTimer) {
            clearTimeout(editingCardSyncTimer);
        }
        editingCardSyncTimer = setTimeout(function () {
            editingCardSyncTimer = null;
            syncEditingEstimateCard();
        }, 150);
    }

    /**
     * 편집 중 진행중 견적 카드를 "완료" 전에도 항상 최신화.
     * 피커 추가뿐 아니라 옵션/비고 행 직접입력·직접입력 행·행 삭제 등 모든 변경 경로를 포괄하도록
     * 옵션/비고 컨테이너의 input·change·childList 변화를 debounce로 syncEditingEstimateCard에 연결.
     * (편집 중이 아니면 syncEditingEstimateCard가 즉시 반환 → 유휴 비용 거의 없음)
     */
    var liveCardSyncInitialized = false;
    function initLiveCardSync() {
        if (liveCardSyncInitialized) return; // 중복 등록 방지
        liveCardSyncInitialized = true;

        // capturing 단계: scheduleEditingCardSync만 호출하고 stopPropagation 안 함 → 기존 핸들러 무영향
        var onFormMutate = function (e) {
            var t = e && e.target;
            if (!t || typeof t.closest !== "function") return;
            if (t.closest("#additionalOptionsContainer") || t.closest("#notesContainer")) {
                scheduleEditingCardSync();
            }
        };
        document.addEventListener("input", onFormMutate, true);
        document.addEventListener("change", onFormMutate, true);

        // 행 추가/삭제는 컨테이너 직접 자식 변화이므로 subtree 불필요.
        // (subtree:true면 mobile-enhance가 .note-item 내부에 세그먼트 삽입 시 불필요 재발화)
        if (window.MutationObserver) {
            ["additionalOptionsContainer", "notesContainer"].forEach(function (id) {
                var el = document.getElementById(id);
                if (el) {
                    new MutationObserver(scheduleEditingCardSync).observe(el, {
                        childList: true,
                    });
                }
            });
        }
    }

    /**
     * 비고는 가격에 영향이 없어 calculateEstimate로는 갱신되지 않으므로,
     * 결과 카드의 비고 표시(#notesDisplay)를 현재 입력값으로 즉시 동기화한다.
     */
    function refreshNotesDisplay() {
        var notesUi = window.WdCalculatorNotesUI;
        var section = document.getElementById("notesDisplaySection");
        var display = document.getElementById("notesDisplay");
        if (!notesUi || typeof notesUi.collectNotes !== "function" || !section || !display) return;
        var notes = notesUi.collectNotes();
        if (notes && notes.trim()) {
            display.textContent = notes;
            section.style.display = "block";
        } else {
            section.style.display = "none";
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
        groups.forEach(function (g) {
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
            // 초기 로딩 시 모든 카테고리는 접힌 상태(사용자가 탭해서 펼침)
            expandGroup(groupEl, list, false);
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
            } else {
                // 검색어를 비우면 초기 상태(모두 접힘)로 복원
                expandGroup(group, list, false);
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
            // 빈 직접입력 비고 한 행 추가 (전역 addNoteItem 사용)
            if (typeof window.addNoteItem === "function") {
                window.addNoteItem("input");
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
        return true;
    }

    function confirm() {
        if (!state.selected || state.selected.size === 0) return;
        var mode = state.mode;
        if (mode === "options") {
            commitOptions();
        } else if (mode === "notes") {
            commitNotes();
            refreshNotesDisplay();
        }
        triggerRecalc();
        syncEditingEstimateCard();
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

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initLiveCardSync);
    } else {
        initLiveCardSync();
    }
})();
