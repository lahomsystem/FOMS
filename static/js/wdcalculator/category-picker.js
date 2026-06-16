/**
 * WDCalculator 카테고리 2단 선택 피커 (PC + 모바일 공통).
 *
 * 목적: 제품 / 추가옵션 / 비고 드랍다운을 "카테고리만 먼저 보이고 → 카테고리 클릭 시
 *       해당 옵션이 다운슬라이드(아코디언)로 펼쳐져 선택" 되게 만든다.
 *
 * 설계: 기존 native <select>(.base-product-select / .category-option-select / .note-select)를
 *       데이터·계약·이벤트 소스로 그대로 유지(시각적으로만 숨김)하고, 그 위에 커스텀
 *       트리거 버튼 + 카테고리 아코디언 패널을 덧입힌다. 옵션 선택 시 select.value를 설정하고
 *       bubbling change/input 이벤트를 디스패치 → 기존 핸들러(재계산/상태)가 그대로 동작.
 *
 * fail-safe: enhance 중 예외가 나면 native select를 다시 노출(.wd-cat-src 제거)해 기능 유지.
 * native <select>는 OS 피커라 카테고리 접기가 불가 → 커스텀 컴포넌트 필요.
 */
(function () {
    "use strict";

    var ENHANCED_ATTR = "data-wd-cat-enhanced";
    var TARGET_SELECTOR =
        "select.base-product-select, select.category-option-select, select.note-select";

    var overlay = null;
    var PANEL_MARGIN = 8;
    var PANEL_GAP = 4;
    var PANEL_MIN_HEIGHT = 120;
    var PANEL_PREFERRED_MAX = 420;

    function isMobile() {
        return !!(window.matchMedia && window.matchMedia("(max-width: 991.98px)").matches);
    }

    function selectIsHidden(select) {
        if (!select) return true;
        if (select.classList && select.classList.contains("d-none")) return true;
        return select.style && select.style.display === "none";
    }

    function currentOption(select) {
        var idx = select.selectedIndex;
        if (idx == null || idx < 0) return null;
        return select.options[idx] || null;
    }

    function triggerLabelText(select) {
        var opt = currentOption(select);
        if (opt && opt.value !== "") {
            var parent = opt.parentNode;
            if (parent && parent.tagName === "OPTGROUP" && parent.label) {
                return parent.label + " > " + (opt.textContent || "");
            }
            return opt.textContent || "";
        }
        var first = select.options && select.options[0];
        return (first && first.textContent) || "선택하세요";
    }

    function updateTrigger(select) {
        var trigger = select.__wdCatTrigger;
        if (!trigger) return;
        var labelEl = trigger.querySelector(".wd-cat-trigger__label");
        var opt = currentOption(select);
        var hasValue = !!(opt && opt.value !== "");
        if (labelEl) labelEl.textContent = triggerLabelText(select);
        trigger.classList.toggle("wd-cat-trigger--placeholder", !hasValue);
    }

    function mirrorVisibility(select) {
        var trigger = select.__wdCatTrigger;
        if (!trigger) return;
        trigger.style.display = selectIsHidden(select) ? "none" : "";
    }

    function buildModel(select) {
        var top = [];
        var groups = [];
        var kids = select.children || [];
        for (var i = 0; i < kids.length; i++) {
            var node = kids[i];
            if (node.tagName === "OPTGROUP") {
                var opts = [];
                var gopts = node.querySelectorAll("option");
                for (var j = 0; j < gopts.length; j++) {
                    opts.push({ value: gopts[j].value, text: gopts[j].textContent || "" });
                }
                if (opts.length) {
                    groups.push({ label: node.getAttribute("label") || "", options: opts });
                }
            } else if (node.tagName === "OPTION") {
                top.push({ value: node.value, text: node.textContent || "" });
            }
        }
        return { top: top, groups: groups };
    }

    function titleFor(select) {
        if (select.classList.contains("base-product-select")) return "제품 선택";
        if (select.classList.contains("category-option-select")) return "카테고리 > 옵션 선택";
        if (select.classList.contains("note-select")) return "비고 선택";
        return "선택";
    }

    function selectValue(select, value) {
        select.value = value;
        try {
            select.dispatchEvent(new Event("input", { bubbles: true }));
        } catch (e1) {
            /* older engines: ignore */
        }
        try {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        } catch (e2) {
            /* older engines: ignore */
        }
        updateTrigger(select);
    }

    function makeOptionRow(text, isSelected, onClick) {
        var row = document.createElement("button");
        row.type = "button";
        row.className = "wd-cat-opt" + (isSelected ? " is-selected" : "");
        row.textContent = text;
        row.addEventListener("click", onClick);
        return row;
    }

    function ensureOverlay() {
        if (overlay) return overlay;
        var backdrop = document.createElement("div");
        backdrop.className = "wd-cat-backdrop";
        backdrop.addEventListener("click", closePanel);

        var panel = document.createElement("div");
        panel.className = "wd-cat-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "true");

        var head = document.createElement("div");
        head.className = "wd-cat-panel__head";
        var titleEl = document.createElement("span");
        titleEl.className = "wd-cat-panel__title";
        var closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "wd-cat-panel__close";
        closeBtn.setAttribute("aria-label", "닫기");
        closeBtn.textContent = "\u2715";
        closeBtn.addEventListener("click", closePanel);
        head.appendChild(titleEl);
        head.appendChild(closeBtn);

        var body = document.createElement("div");
        body.className = "wd-cat-panel__body";

        panel.appendChild(head);
        panel.appendChild(body);
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);

        overlay = {
            backdrop: backdrop,
            panel: panel,
            body: body,
            titleEl: titleEl,
            currentSelect: null,
            currentTrigger: null,
        };

        window.addEventListener("resize", function () {
            if (!overlay || !overlay.currentSelect) return;
            overlay.panel.classList.toggle("wd-cat-panel--sheet", isMobile());
            overlay.panel.classList.toggle("wd-cat-panel--dropdown", !isMobile());
            positionPanel();
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") closePanel();
        });
        return overlay;
    }

    function getScrollParents(el) {
        var parents = [];
        var node = el && el.parentElement;
        while (node && node !== document.documentElement) {
            var style = window.getComputedStyle(node);
            var overflowY = style.overflowY;
            var overflowX = style.overflowX;
            if (
                /(auto|scroll|overlay)/.test(overflowY) ||
                /(auto|scroll|overlay)/.test(overflowX)
            ) {
                parents.push(node);
            }
            node = node.parentElement;
        }
        parents.push(window);
        return parents;
    }

    function bindScrollListeners(trigger) {
        unbindScrollListeners();
        if (!overlay || !trigger) return;
        overlay._scrollParents = getScrollParents(trigger);
        overlay._onScrollReposition = function () {
            positionPanel();
        };
        for (var i = 0; i < overlay._scrollParents.length; i++) {
            overlay._scrollParents[i].addEventListener(
                "scroll",
                overlay._onScrollReposition,
                { passive: true }
            );
        }
    }

    function unbindScrollListeners() {
        if (!overlay || !overlay._scrollParents || !overlay._onScrollReposition) return;
        for (var i = 0; i < overlay._scrollParents.length; i++) {
            overlay._scrollParents[i].removeEventListener(
                "scroll",
                overlay._onScrollReposition
            );
        }
        overlay._scrollParents = null;
        overlay._onScrollReposition = null;
    }

    function expandGroup(group, list, open) {
        group.classList.toggle("is-open", open);
        list.style.maxHeight = open ? list.scrollHeight + "px" : "0px";
        if (overlay && overlay.currentSelect) {
            window.requestAnimationFrame(positionPanel);
        }
    }

    function openPanel(select, trigger) {
        var ov = ensureOverlay();
        ov.currentSelect = select;
        ov.currentTrigger = trigger;
        ov.titleEl.textContent = trigger.getAttribute("data-wd-cat-title") || "선택";

        var model = buildModel(select);
        var current = select.value;
        var body = ov.body;
        body.innerHTML = "";

        model.top.forEach(function (o) {
            var row = makeOptionRow(o.text, o.value === current, function () {
                selectValue(select, o.value);
                closePanel();
            });
            if (o.value === "") row.classList.add("wd-cat-opt--placeholder");
            body.appendChild(row);
        });

        model.groups.forEach(function (g) {
            var hasCurrent = g.options.some(function (o) {
                return o.value === current;
            });
            var group = document.createElement("div");
            group.className = "wd-cat-group";

            var header = document.createElement("button");
            header.type = "button";
            header.className = "wd-cat-group__head";
            header.innerHTML =
                '<span class="wd-cat-group__name"></span>' +
                '<span class="wd-cat-group__meta">' +
                '<span class="wd-cat-group__count"></span>' +
                '<span class="wd-cat-group__chev">\u25be</span></span>';
            header.querySelector(".wd-cat-group__name").textContent = g.label;
            header.querySelector(".wd-cat-group__count").textContent = g.options.length + "개";

            var list = document.createElement("div");
            list.className = "wd-cat-group__list";
            g.options.forEach(function (o) {
                list.appendChild(
                    makeOptionRow(o.text, o.value === current, function () {
                        selectValue(select, o.value);
                        closePanel();
                    })
                );
            });

            header.addEventListener("click", function () {
                expandGroup(group, list, !group.classList.contains("is-open"));
            });

            group.appendChild(header);
            group.appendChild(list);
            body.appendChild(group);
            expandGroup(group, list, hasCurrent);
        });

        ov.backdrop.classList.add("is-open");
        ov.panel.classList.add("is-open");
        ov.panel.classList.toggle("wd-cat-panel--sheet", isMobile());
        ov.panel.classList.toggle("wd-cat-panel--dropdown", !isMobile());
        document.body.classList.add("wd-cat-open");
        bindScrollListeners(trigger);
        positionPanel();

        // 레이아웃 확정 후 열린 그룹 높이 재계산(초기 scrollHeight 보정)
        var openLists = ov.panel.querySelectorAll(".wd-cat-group.is-open .wd-cat-group__list");
        for (var k = 0; k < openLists.length; k++) {
            openLists[k].style.maxHeight = openLists[k].scrollHeight + "px";
        }
        window.requestAnimationFrame(positionPanel);
    }

    function positionPanel() {
        if (!overlay || !overlay.currentTrigger) return;
        var panel = overlay.panel;
        if (isMobile()) {
            panel.style.left = "";
            panel.style.top = "";
            panel.style.width = "";
            panel.style.maxHeight = "";
            panel.classList.remove("wd-cat-panel--above");
            return;
        }
        var r = overlay.currentTrigger.getBoundingClientRect();
        var width = Math.max(r.width, 260);
        var left = Math.min(r.left, window.innerWidth - width - PANEL_MARGIN);
        left = Math.max(PANEL_MARGIN, left);

        var viewportH = window.innerHeight;
        var preferredMax = Math.min(viewportH * 0.6, PANEL_PREFERRED_MAX);
        var spaceBelow = viewportH - r.bottom - PANEL_GAP - PANEL_MARGIN;
        var spaceAbove = r.top - PANEL_GAP - PANEL_MARGIN;
        var placeAbove =
            spaceBelow < PANEL_MIN_HEIGHT && spaceAbove > spaceBelow ||
            (spaceAbove > spaceBelow && spaceBelow < preferredMax * 0.45);
        var available = placeAbove ? spaceAbove : spaceBelow;
        var maxHeight = Math.min(preferredMax, Math.max(0, available));
        var top;

        if (placeAbove) {
            top = r.top - PANEL_GAP - maxHeight;
            if (top < PANEL_MARGIN) {
                maxHeight = Math.min(preferredMax, r.top - PANEL_GAP - PANEL_MARGIN);
                top = PANEL_MARGIN;
            }
        } else {
            top = r.bottom + PANEL_GAP;
            if (top + maxHeight > viewportH - PANEL_MARGIN) {
                maxHeight = viewportH - PANEL_MARGIN - top;
            }
            if (maxHeight < PANEL_MIN_HEIGHT && spaceAbove > spaceBelow) {
                placeAbove = true;
                maxHeight = Math.min(preferredMax, spaceAbove);
                top = Math.max(PANEL_MARGIN, r.top - PANEL_GAP - maxHeight);
            }
        }

        panel.style.width = width + "px";
        panel.style.left = left + "px";
        panel.style.top = top + "px";
        panel.style.maxHeight = Math.max(0, maxHeight) + "px";
        panel.classList.toggle("wd-cat-panel--above", placeAbove);
    }

    function closePanel() {
        if (!overlay) return;
        unbindScrollListeners();
        overlay.backdrop.classList.remove("is-open");
        overlay.panel.classList.remove("is-open");
        overlay.panel.classList.remove("wd-cat-panel--above");
        document.body.classList.remove("wd-cat-open");
        overlay.currentSelect = null;
        overlay.currentTrigger = null;
    }

    function enhance(select) {
        if (!select || select.getAttribute(ENHANCED_ATTR) === "1") return;
        try {
            select.setAttribute(ENHANCED_ATTR, "1");
            select.classList.add("wd-cat-src");

            var trigger = document.createElement("button");
            trigger.type = "button";
            trigger.className = "wd-cat-trigger";
            trigger.setAttribute("data-wd-cat-title", titleFor(select));
            trigger.innerHTML =
                '<span class="wd-cat-trigger__label"></span>' +
                '<span class="wd-cat-trigger__caret">\u25be</span>';
            select.parentNode.insertBefore(trigger, select);
            select.__wdCatTrigger = trigger;

            trigger.addEventListener("click", function (e) {
                e.preventDefault();
                openPanel(select, trigger);
            });
            select.addEventListener("change", function () {
                updateTrigger(select);
            });

            updateTrigger(select);
            mirrorVisibility(select);

            // 불러오기/직접 토글로 select가 숨겨질 때(.d-none 또는 style.display=none) 트리거도 동기화
            var mo = new MutationObserver(function () {
                mirrorVisibility(select);
            });
            mo.observe(select, { attributes: true, attributeFilter: ["style", "class"] });
        } catch (err) {
            select.classList.remove("wd-cat-src");
            if (window.console && console.warn) {
                console.warn("[wd-cat-picker] enhance failed; native select 유지", err);
            }
        }
    }

    function enhanceAll(root) {
        var scope = root && root.querySelectorAll ? root : document;
        var list = scope.querySelectorAll(TARGET_SELECTOR);
        for (var i = 0; i < list.length; i++) enhance(list[i]);
    }

    function watch() {
        enhanceAll(document);
        var mo = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (!node || node.nodeType !== 1) continue;
                    if (node.matches && node.matches(TARGET_SELECTOR)) enhance(node);
                    if (node.querySelectorAll) enhanceAll(node);
                }
            }
        });
        mo.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", watch);
    } else {
        watch();
    }

    window.WdCalculatorCategoryPicker = { enhance: enhance, enhanceAll: enhanceAll };
})();
