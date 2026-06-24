/* WDCalculator canonical chunk: estimate-lifecycle */
/* --- included: sidebar-estimates.js --- */
(function () {
    function fallbackFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    function initWdCalculatorSidebarEstimates(options) {
        var config = options || {};
        var loadEstimateToForm = config.loadEstimateToForm;
        var formatNumber = config.formatNumber || window.formatNumber || fallbackFormatNumber;
        var fetchImpl = config.fetchImpl || window.fetch.bind(window);
        var confirmImpl = config.confirmImpl || window.confirm.bind(window);
        var alertImpl = config.alertImpl || window.alert.bind(window);
        var matchMediaImpl = config.matchMediaImpl || window.matchMedia.bind(window);
        var documentRef = config.documentRef || document;

        var sidebarSearchInput = documentRef.getElementById("sidebarSearchInput");
        var sidebarSearchBtn = documentRef.getElementById("sidebarSearchBtn");
        var refreshEstimatesBtn = documentRef.getElementById("refreshEstimatesBtn");
        var savedEstimatesList = documentRef.getElementById("savedEstimatesList");
        var savedEstimatesLoading = documentRef.getElementById("savedEstimatesLoading");
        var noSavedEstimates = documentRef.getElementById("noSavedEstimates");

        function getSearchQuery() {
            return sidebarSearchInput ? sidebarSearchInput.value : "";
        }

        function createIconButton(buttonClassName, title, iconClassName) {
            var button = documentRef.createElement("button");
            button.type = "button";
            button.className = buttonClassName;
            button.title = title;
            var icon = documentRef.createElement("i");
            icon.className = iconClassName;
            button.appendChild(icon);
            return button;
        }

        function parseApiResponse(response) {
            return response
                .json()
                .catch(function () {
                    return {};
                })
                .then(function (data) {
                    if (!response.ok) {
                        throw new Error(data.message || data.error || ("HTTP " + response.status));
                    }
                    return data;
                });
        }

        function buildSidebarEstimateItem(est, totalPrice, productNameStr) {
            var item = documentRef.createElement("div");
            item.className = "list-group-item list-group-item-action p-3 border-bottom saved-estimate-row";
            item.setAttribute("data-estimate-id", String(est.id));

            var dateStr = est.created_at
                ? new Date(est.created_at).toLocaleDateString()
                : "";

            var header = documentRef.createElement("div");
            header.className = "d-flex justify-content-between align-items-start mb-1";

            var title = documentRef.createElement("h6");
            title.className = "mb-0 fw-bold text-truncate saved-estimate-customer-name";
            title.style.maxWidth = "140px";
            title.textContent = est.customer_name || "";

            var date = documentRef.createElement("small");
            date.className = "text-muted";
            date.textContent = dateStr;

            header.appendChild(title);
            header.appendChild(date);

            var productSummary = documentRef.createElement("p");
            productSummary.className = "mb-1 small text-dark";
            productSummary.textContent = productNameStr;

            var unitMetaRow = null;
            if (
                window.WdCalculatorUnitPriceMeta &&
                typeof window.WdCalculatorUnitPriceMeta.isUnitPriceMetaVisible === "function" &&
                window.WdCalculatorUnitPriceMeta.isUnitPriceMetaVisible() &&
                typeof window.WdCalculatorUnitPriceMeta.deriveSavedEstimateUnitSummary === "function"
            ) {
                var productsForMeta =
                    window.WdCalculatorProductsState &&
                    typeof window.WdCalculatorProductsState.getProducts === "function"
                        ? window.WdCalculatorProductsState.getProducts()
                        : [];
                unitMetaRow = documentRef.createElement("div");
                unitMetaRow.className = "saved-estimate-unit-meta small text-muted mt-1";
                var sum = window.WdCalculatorUnitPriceMeta.deriveSavedEstimateUnitSummary(
                    est,
                    productsForMeta,
                    formatNumber
                );
                window.WdCalculatorUnitPriceMeta.fillElementWithLines(unitMetaRow, sum, {
                    fallbackText: "단가 정보 없음",
                });
            }

            var footer = documentRef.createElement("div");
            footer.className = "d-flex justify-content-between align-items-center mt-2";

            var price = documentRef.createElement("span");
            price.className = "fw-bold text-primary";
            price.textContent = formatNumber(totalPrice) + "원";

            var actions = documentRef.createElement("div");
            actions.className = "d-flex gap-1";

            var loadBtn = createIconButton(
                "btn btn-xs btn-outline-primary load-estimate-btn",
                "불러오기",
                "fas fa-folder-open"
            );
            loadBtn.setAttribute("data-id", String(est.id));

            var matchBtn = createIconButton(
                "btn btn-xs btn-outline-success match-order-btn",
                "주문 매칭",
                "fas fa-link"
            );
            matchBtn.setAttribute("data-estimate-id", String(est.id));
            matchBtn.setAttribute("data-customer-name", est.customer_name || "");

            var deleteBtn = createIconButton(
                "btn btn-xs btn-outline-danger delete-estimate-btn",
                "삭제",
                "fas fa-trash-alt"
            );
            deleteBtn.setAttribute("data-id", String(est.id));

            actions.appendChild(loadBtn);
            actions.appendChild(matchBtn);
            actions.appendChild(deleteBtn);
            footer.appendChild(price);
            footer.appendChild(actions);

            item.appendChild(header);
            item.appendChild(productSummary);
            if (unitMetaRow) {
                item.appendChild(unitMetaRow);
            }
            item.appendChild(footer);

            loadBtn.addEventListener("click", function (event) {
                event.stopPropagation();
                if (
                    confirmImpl(
                        "'" +
                            (est.customer_name || "") +
                            "' 님의 견적을 불러오시겠습니까?\n현재 작성 중인 내용은 사라질 수 있습니다."
                    )
                ) {
                    loadEstimateToForm(est);
                }
            });

            deleteBtn.addEventListener("click", function (event) {
                event.stopPropagation();
                if (
                    confirmImpl(
                        "'" +
                            (est.customer_name || "") +
                            "' 님의 견적을 삭제하시겠습니까?\n\n⚠️ 삭제된 견적은 복구할 수 없습니다."
                    )
                ) {
                    deleteEstimate(est.id);
                }
            });

            return item;
        }

        function loadSidebarEstimates(searchQuery) {
            if (searchQuery === undefined) {
                searchQuery = "";
            }
            if (!savedEstimatesList) {
                return Promise.resolve();
            }

            if (savedEstimatesLoading) {
                savedEstimatesLoading.style.display = "block";
            }
            savedEstimatesList.innerHTML = "";
            if (noSavedEstimates) {
                noSavedEstimates.style.display = "none";
            }

            var url = "/api/wdcalculator/search-estimates?_t=" + Date.now();
            if (searchQuery) {
                url += "&customer_name=" + encodeURIComponent(searchQuery);
            }

            return fetchImpl(url)
                .then(parseApiResponse)
                .then(function (data) {
                    if (savedEstimatesLoading) {
                        savedEstimatesLoading.style.display = "none";
                    }

                    if (data.success && Array.isArray(data.estimates) && data.estimates.length > 0) {
                        data.estimates.forEach(function (est) {
                            var totalPrice = 0;
                            var productNames = [];

                            if (est.estimate_data) {
                                if (est.estimate_data.totalPrice) {
                                    totalPrice = est.estimate_data.totalPrice;
                                }
                                if (
                                    est.estimate_data.estimates &&
                                    Array.isArray(est.estimate_data.estimates)
                                ) {
                                    productNames = est.estimate_data.estimates.map(function (estimate) {
                                        return (
                                            estimate.displayName ||
                                            estimate.productName ||
                                            (estimate.product ? estimate.product.name : "알 수 없음")
                                        );
                                    });
                                }
                            }

                            var productNameStr = productNames.length > 0
                                ? (
                                    productNames.length > 1
                                        ? productNames[0] + " 외 " + (productNames.length - 1) + "건"
                                        : productNames[0]
                                )
                                : "제품 정보 없음";
                            var item = buildSidebarEstimateItem(est, totalPrice, productNameStr);
                            savedEstimatesList.appendChild(item);
                        });

                        var listItems = savedEstimatesList.querySelectorAll(".list-group-item");
                        var moreWrap = documentRef.getElementById("savedEstimatesMoreWrap");
                        var listContainer = documentRef.getElementById("savedEstimatesListContainer");
                        var MOBILE_BREAKPOINT = 576;
                        var VISIBLE_COUNT_MOBILE = 1;
                        var hiddenClass = "saved-estimate-item--hidden-mobile";
                        var expandedClass = "saved-estimates-list--expanded";
                        var collapseBarId = "savedEstimatesCollapseBar";

                        function ensureCollapseBar() {
                            if (!listContainer) {
                                return null;
                            }

                            var collapseBar = documentRef.getElementById(collapseBarId);
                            if (!collapseBar) {
                                collapseBar = documentRef.createElement("div");
                                collapseBar.id = collapseBarId;
                                collapseBar.className = "text-center mt-2";
                                collapseBar.innerHTML =
                                    '<button type="button" class="btn btn-sm btn-outline-secondary" id="savedEstimatesCollapseBtn">접기</button>';
                                listContainer.appendChild(collapseBar);
                                var collapseBtn = collapseBar.querySelector("#savedEstimatesCollapseBtn");
                                if (collapseBtn) {
                                    collapseBtn.addEventListener("click", function () {
                                        savedEstimatesList.classList.remove(expandedClass);
                                        Array.prototype.forEach.call(listItems, function (item, index) {
                                            if (index >= VISIBLE_COUNT_MOBILE) {
                                                item.classList.add(hiddenClass);
                                            }
                                        });
                                        collapseBar.style.display = "none";
                                        if (moreWrap) {
                                            moreWrap.style.display = "";
                                        }
                                    });
                                }
                            }
                            return collapseBar;
                        }

                        function applyMobileListState() {
                            var isMobile = !!(matchMediaImpl && matchMediaImpl("(max-width: " + MOBILE_BREAKPOINT + "px)").matches);

                            Array.prototype.forEach.call(listItems, function (item, index) {
                                if (isMobile && index >= VISIBLE_COUNT_MOBILE && !savedEstimatesList.classList.contains(expandedClass)) {
                                    item.classList.add(hiddenClass);
                                } else {
                                    item.classList.remove(hiddenClass);
                                }
                            });

                            var shouldShowMore = isMobile && listItems.length > VISIBLE_COUNT_MOBILE;
                            if (moreWrap) {
                                moreWrap.style.display = shouldShowMore && !savedEstimatesList.classList.contains(expandedClass)
                                    ? ""
                                    : "none";
                            }

                            var collapseBar = ensureCollapseBar();
                            if (collapseBar) {
                                collapseBar.style.display = savedEstimatesList.classList.contains(expandedClass) ? "" : "none";
                            }
                        }

                        applyMobileListState();

                        if (moreWrap) {
                            moreWrap.onclick = function () {
                                savedEstimatesList.classList.add(expandedClass);
                                Array.prototype.forEach.call(listItems, function (item) {
                                    item.classList.remove(hiddenClass);
                                });
                                moreWrap.style.display = "none";
                                var collapseBar = ensureCollapseBar();
                                if (collapseBar) {
                                    collapseBar.style.display = "";
                                }
                            };
                        }
                    } else if (noSavedEstimates) {
                        noSavedEstimates.style.display = "block";
                    }

                    return data;
                })
                .catch(function (error) {
                    if (savedEstimatesLoading) {
                        savedEstimatesLoading.style.display = "none";
                    }
                    if (savedEstimatesList) {
                        savedEstimatesList.innerHTML =
                            '<div class="text-danger small">저장된 견적을 불러오지 못했습니다.</div>';
                    }
                    alertImpl(error.message || "저장된 견적을 불러오지 못했습니다.");
                    return null;
                });
        }

        function deleteEstimate(estimateId) {
            return fetchImpl("/api/wdcalculator/estimate/" + estimateId, {
                method: "DELETE",
            })
                .then(parseApiResponse)
                .then(function (data) {
                    if (data.success) {
                        return loadSidebarEstimates(getSearchQuery()).then(function () {
                            return data;
                        });
                    }
                    alertImpl(data.message || "견적 삭제 중 오류가 발생했습니다.");
                    return data;
                })
                .catch(function (error) {
                    alertImpl(error.message || "견적 삭제 중 오류가 발생했습니다.");
                    return null;
                });
        }

        function bindSidebarEvents() {
            if (sidebarSearchBtn) {
                sidebarSearchBtn.addEventListener("click", function () {
                    loadSidebarEstimates(getSearchQuery());
                });
            }

            if (sidebarSearchInput) {
                sidebarSearchInput.addEventListener("keydown", function (event) {
                    if (event.key === "Enter") {
                        event.preventDefault();
                        loadSidebarEstimates(getSearchQuery());
                    }
                });
            }

            if (refreshEstimatesBtn) {
                refreshEstimatesBtn.addEventListener("click", function () {
                    loadSidebarEstimates(getSearchQuery());
                });
            }
        }

        bindSidebarEvents();

        window.loadSidebarEstimates = loadSidebarEstimates;
        window.deleteEstimate = deleteEstimate;
        window.initWdCalculatorSidebarEstimates = initWdCalculatorSidebarEstimates;

        return {
            loadSidebarEstimates: loadSidebarEstimates,
            deleteEstimate: deleteEstimate,
        };
    }

    window.initWdCalculatorSidebarEstimates = initWdCalculatorSidebarEstimates;
})();

/* --- included: search-results-load.js --- */
(function () {
    function fallbackFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    var WdCalculatorSearchResultsLoad = window.WdCalculatorSearchResultsLoad || {};

    (function (ns) {
        var loadEstimateToForm = function () {};
        var formatNumber = window.formatNumber || fallbackFormatNumber;
        var fetchImpl = window.fetch ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};
        var documentRef = document;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
        }

        function displaySearchResults(estimates) {
            var container = documentRef.getElementById("searchResultsList");
            var resultsDiv = documentRef.getElementById("searchResults");

            if (estimates.length === 0) {
                container.innerHTML = '<p class="text-muted">검색 결과가 없습니다.</p>';
                resultsDiv.style.display = "block";
                return;
            }

            var html = '<div class="list-group">';
            estimates.forEach(function (estimate) {
                var estimateData = estimate.estimate_data;
                var totalPrice = estimateData.totalPrice || 0;
                var basePrice = estimateData.basePrice || 0;
                var additionalPrice = estimateData.additionalPrice || 0;

                html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6 class="mb-1">${estimate.customer_name}</h6>
                            <small class="text-muted">생성일: ${estimate.created_at}</small>
                            <div class="mt-2">
                                <small>기본 견적: ${formatNumber(basePrice)}원</small><br>
                                <small>추가 옵션: ${formatNumber(additionalPrice)}원</small><br>
                                <strong>총 견적: ${formatNumber(totalPrice)}원</strong>
                            </div>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-primary load-estimate-btn" data-estimate-id="${estimate.id}">
                                <i class="fas fa-download"></i> 불러오기
                            </button>
                            <button class="btn btn-sm btn-success match-order-btn mt-1" data-estimate-id="${estimate.id}" data-customer-name="${estimate.customer_name}">
                                <i class="fas fa-link"></i> 주문 매칭
                            </button>
                        </div>
                    </div>
                </div>
            `;
            });
            html += "</div>";

            container.innerHTML = html;
            resultsDiv.style.display = "block";
        }

        function handleSearchEstimateButtonClick() {
            var searchCustomerNameInput = documentRef.getElementById("searchCustomerName");
            if (!searchCustomerNameInput) {
                console.error("searchCustomerName element not found");
                return null;
            }

            var customerName = searchCustomerNameInput.value.trim();
            if (!customerName) {
                alertImpl("고객명을 입력해주세요.");
                return null;
            }

            return fetchImpl(
                "/api/wdcalculator/search-estimates?customer_name=" +
                    encodeURIComponent(customerName)
            )
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.success) {
                        ns.displaySearchResults(data.estimates);
                    } else {
                        alertImpl(data.message || "검색 중 오류가 발생했습니다.");
                    }
                    return data;
                })
                .catch(function (error) {
                    console.error("Error:", error);
                    alertImpl("검색 중 오류가 발생했습니다.");
                    return null;
                });
        }

        function bindSearchEstimateButton() {
            var searchEstimateBtn = documentRef.getElementById("searchEstimateBtn");
            if (searchEstimateBtn) {
                searchEstimateBtn.addEventListener("click", handleSearchEstimateButtonClick);
            }
        }

        function handleLoadEstimateButtonClick(event) {
            var trigger = event && event.target && event.target.closest
                ? event.target.closest(".load-estimate-btn")
                : null;
            if (!trigger) return null;

            var estimateId = parseInt(trigger.dataset.estimateId);
            var searchCustomerNameInput = documentRef.getElementById("searchCustomerName");
            var customerName = searchCustomerNameInput ? searchCustomerNameInput.value.trim() : "";

            return fetchImpl(
                "/api/wdcalculator/search-estimates?customer_name=" +
                    encodeURIComponent(customerName)
            )
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.success) {
                        var estimate = data.estimates.find(function (est) {
                            return est.id === estimateId;
                        });
                        if (estimate) {
                            loadEstimateToForm(estimate);
                        } else {
                            alertImpl("견적을 찾을 수 없습니다.");
                        }
                    }
                    return data;
                })
                .catch(function (error) {
                    console.error("Error:", error);
                    alertImpl("견적을 불러오는 중 오류가 발생했습니다.");
                    return null;
                });
        }

        function bindLoadEstimateButtons() {
            documentRef.addEventListener("click", handleLoadEstimateButtonClick);
        }

        function initSearchResultsLoadBridge() {
            bindSearchEstimateButton();
            bindLoadEstimateButtons();
        }

        ns.configure = configure;
        ns.displaySearchResults = displaySearchResults;
        ns.handleSearchEstimateButtonClick = handleSearchEstimateButtonClick;
        ns.bindSearchEstimateButton = bindSearchEstimateButton;
        ns.handleLoadEstimateButtonClick = handleLoadEstimateButtonClick;
        ns.bindLoadEstimateButtons = bindLoadEstimateButtons;
        ns.initSearchResultsLoadBridge = initSearchResultsLoadBridge;
    })(WdCalculatorSearchResultsLoad);

    window.WdCalculatorSearchResultsLoad = WdCalculatorSearchResultsLoad;
})();

/* --- included: render-estimates-list.js --- */
(function () {
    function fallbackFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    function fallbackEscapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function fallbackFormatNotesText(notes) {
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

    var WdCalculatorRenderEstimatesList = window.WdCalculatorRenderEstimatesList || {};

    (function (ns) {
        var getEstimates = function () {
            return [];
        };
        var formatNumber = window.formatNumber || fallbackFormatNumber;
        var escapeHtml = window.escapeHtml || fallbackEscapeHtml;
        var formatNotesText = fallbackFormatNotesText;
        var onRenderComplete = function () {};
        var documentRef = document;
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };
        var getProducts = function () {
            var st = window.WdCalculatorProductsState;
            return st && typeof st.getProducts === "function" ? st.getProducts() : [];
        };

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.escapeHtml === "function") {
                escapeHtml = opts.escapeHtml;
            }
            if (typeof opts.formatNotesText === "function") {
                formatNotesText = opts.formatNotesText;
            }
            if (typeof opts.onRenderComplete === "function") {
                onRenderComplete = opts.onRenderComplete;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
        }

        function buildEstimateUnitPriceMetaHtml(estimate) {
            var up = window.WdCalculatorUnitPriceMeta;
            if (!up || typeof up.isUnitPriceMetaVisible !== "function" || !up.isUnitPriceMetaVisible()) {
                return "";
            }
            if (typeof up.deriveEstimateUnitPriceSummary !== "function") {
                return "";
            }
            var summary = up.deriveEstimateUnitPriceSummary(estimate, getProducts(), formatNumber);
            if (summary.isEmpty) {
                return '<div class="wd-estimate-unit-meta text-muted small mt-1">단가 정보 없음</div>';
            }
            if (summary.lines.length === 1) {
                return (
                    '<div class="wd-estimate-unit-meta small mt-1">' +
                    escapeHtml(summary.lines[0]) +
                    "</div>"
                );
            }
            return (
                '<div class="wd-estimate-unit-meta small mt-1">' +
                summary.lines
                    .map(function (ln) {
                        return '<span class="wd-unit-price-chip">' + escapeHtml(ln) + "</span>";
                    })
                    .join(" ") +
                "</div>"
            );
        }

        function buildOptionsDetailHtml(estimate) {
            if (!estimate.options || estimate.options.length === 0) {
                return "없음";
            }

            return estimate.options
                .map(function (opt) {
                    var amount = (opt.price || 0) * (opt.quantity || 1);
                    return (
                        '<div style="color: #0d7a3d !important; font-weight: 700 !important; font-size: 1.02rem !important; line-height: 1.6 !important;">' +
                        escapeHtml(opt.name) +
                        " × " +
                        opt.quantity +
                        " (" +
                        formatNumber(amount) +
                        "원)</div>"
                    );
                })
                .join("");
        }

        function buildNotesHtml(estimate) {
            if (!estimate.notes) {
                return "";
            }

            return `
                            <div class="mb-3 estimate-card-item">
                                <span class="estimate-header-notes" style="color: #0d6efd !important; font-weight: 800 !important; font-size: 1.08rem !important; display: block !important; margin-bottom: 0.25rem !important;">비고:</span>
                                <div class="estimate-detail-notes" style="margin-top: 0.25rem !important;">
                                    ${formatNotesText(estimate.notes)
                                        .split("\n")
                                        .filter(function (line) {
                                            return line.trim();
                                        })
                                        .map(function (line) {
                                            return `<div style="color: #0d7a3d !important; font-weight: 700 !important; font-size: 1.02rem !important; line-height: 1.6 !important;">${escapeHtml(line.trim())}</div>`;
                                        })
                                        .join("")}
                                </div>
                            </div>
                            `;
        }

        function applyForcedStyles(container) {
            container.querySelectorAll(".estimate-header-base").forEach(function (el) {
                el.style.setProperty("color", "#0d6efd", "important");
                el.style.setProperty("font-weight", "800", "important");
                el.style.setProperty("font-size", "1.08rem", "important");
                el.style.setProperty("display", "block", "important");
                el.style.setProperty("margin-bottom", "0.25rem", "important");
            });

            container.querySelectorAll(".estimate-header-options").forEach(function (el) {
                el.style.setProperty("color", "#0d6efd", "important");
                el.style.setProperty("font-weight", "800", "important");
                el.style.setProperty("font-size", "1.08rem", "important");
                el.style.setProperty("display", "block", "important");
                el.style.setProperty("margin-bottom", "0.25rem", "important");
            });

            container.querySelectorAll(".estimate-header-notes").forEach(function (el) {
                el.style.setProperty("color", "#0d6efd", "important");
                el.style.setProperty("font-weight", "800", "important");
                el.style.setProperty("font-size", "1.08rem", "important");
                el.style.setProperty("display", "block", "important");
                el.style.setProperty("margin-bottom", "0.25rem", "important");
            });

            container.querySelectorAll(".estimate-detail-base").forEach(function (el) {
                el.style.setProperty("color", "#0d7a3d", "important");
                el.style.setProperty("font-weight", "700", "important");
                el.style.setProperty("font-size", "1.02rem", "important");
                el.style.setProperty("line-height", "1.5", "important");
                el.style.setProperty("margin-top", "0.25rem", "important");
            });

            container.querySelectorAll(".estimate-detail-options").forEach(function (el) {
                el.querySelectorAll("div").forEach(function (divEl) {
                    divEl.style.setProperty("color", "#0d7a3d", "important");
                    divEl.style.setProperty("font-weight", "700", "important");
                    divEl.style.setProperty("font-size", "1.02rem", "important");
                    divEl.style.setProperty("line-height", "1.6", "important");
                });
            });

            container.querySelectorAll(".estimate-detail-notes").forEach(function (el) {
                el.style.setProperty("margin-top", "0.25rem", "important");
                el.querySelectorAll("div").forEach(function (divEl) {
                    divEl.style.setProperty("color", "#0d7a3d", "important");
                    divEl.style.setProperty("font-weight", "700", "important");
                    divEl.style.setProperty("font-size", "1.02rem", "important");
                    divEl.style.setProperty("line-height", "1.6", "important");
                });
            });

            container.querySelectorAll(".estimate-price").forEach(function (el) {
                el.style.setProperty("font-size", "1.32rem", "important");
                el.style.setProperty("font-weight", "700", "important");
                el.style.setProperty("color", "#212529", "important");
            });

            container.querySelectorAll(".estimate-total-price").forEach(function (el) {
                el.style.setProperty("font-size", "1.56rem", "important");
                el.style.setProperty("font-weight", "800", "important");
                el.style.setProperty("color", "#0d6efd", "important");
            });
        }

        /**
         * 견적 카드의 card-body 내부 HTML을 생성한다.
         * renderEstimatesList(전체 렌더)와 refreshEstimateCard(단일 카드 in-place 갱신)가 공유.
         */
        function buildEstimateCardBodyHtml(estimate, displayNameEscaped) {
            var optionsDetailHtml = buildOptionsDetailHtml(estimate);
            return `
                            <div class="mb-3 estimate-card-item">
                                <span class="estimate-header-base" style="color: #0d6efd !important; font-weight: 800 !important; font-size: 1.08rem !important; display: block !important; margin-bottom: 0.25rem !important;">기본 견적:</span>
                                <div class="estimate-price mb-1" style="font-size: 1.32rem !important; font-weight: 700 !important; color: #212529 !important;">${formatNumber(estimate.basePrice)}원</div>
                                <div class="estimate-detail-base" style="color: #0d7a3d !important; font-weight: 700 !important; font-size: 1.02rem !important; line-height: 1.5 !important; margin-top: 0.25rem !important;">${displayNameEscaped}</div>
                                ${buildEstimateUnitPriceMetaHtml(estimate)}
                            </div>
                            <div class="mb-3 estimate-card-item">
                                <span class="estimate-header-options" style="color: #0d6efd !important; font-weight: 800 !important; font-size: 1.08rem !important; display: block !important; margin-bottom: 0.25rem !important;">추가 옵션 합계:</span>
                                <div class="estimate-price mb-1" style="font-size: 1.32rem !important; font-weight: 700 !important; color: #212529 !important;">${formatNumber(estimate.additionalPrice)}원</div>
                                <div class="estimate-detail-options" style="margin-top: 0.25rem !important;">${optionsDetailHtml}</div>
                            </div>
                            ${buildNotesHtml(estimate)}
                            <hr class="my-3">
                            <div class="mt-3">
                                <small class="text-muted d-block mb-1" style="font-size: 1.05rem !important;">총견적:</small>
                                <div class="estimate-total-price" style="font-size: 1.56rem !important; font-weight: 800 !important; color: #0d6efd !important; margin-top: 0.5rem !important;">${formatNumber(estimate.totalPrice)}원</div>
                            </div>
            `;
        }

        function estimateDisplayNameEscaped(estimate) {
            return escapeHtml(
                estimate.displayName ||
                    (estimate.productName || "") + " " + formatNumber(estimate.widthMm) + "mm"
            );
        }

        /**
         * 편집 중인 단일 견적 카드의 card-body만 in-place로 다시 그린다.
         * estimatesListContainer 전체 innerHTML을 건드리지 않으므로 모바일 인라인 에디터(도킹된 폼)를
         * 파괴하지 않는다 → 완료 전에도 옵션/비고 추가가 카드에 실시간 반영.
         * @param {string|number} estimateId
         * @returns {boolean} 갱신 성공 여부
         */
        function refreshEstimateCard(estimateId) {
            var estimates = getEstimates() || [];
            var estimate = null;
            for (var i = 0; i < estimates.length; i++) {
                if (String(estimates[i].id) === String(estimateId)) {
                    estimate = estimates[i];
                    break;
                }
            }
            if (!estimate) return false;

            var container = documentRef.getElementById("estimatesListContainer");
            if (!container) return false;

            var cards = container.querySelectorAll(".card[data-estimate-id]");
            var card = null;
            for (var j = 0; j < cards.length; j++) {
                if (String(cards[j].getAttribute("data-estimate-id")) === String(estimateId)) {
                    card = cards[j];
                    break;
                }
            }
            if (!card) return false;

            var body = card.querySelector(".card-body");
            if (!body) return false;

            body.innerHTML = buildEstimateCardBodyHtml(estimate, estimateDisplayNameEscaped(estimate));
            applyForcedStyles(card);
            // 전체 합계(저장 견적 기준)도 함께 갱신 (현재 요약/리스트 DOM은 건드리지 않음)
            onRenderComplete();
            return true;
        }

        function renderEstimatesList() {
            var estimates = getEstimates() || [];
            var container = documentRef.getElementById("estimatesListContainer");

            if (estimates.length === 0) {
                container.innerHTML = '<p class="text-muted text-center mb-0">추가된 견적이 없습니다.</p>';
                return;
            }

            var html = '<div class="row g-3">';
            estimates.forEach(function (estimate, index) {
                var estimateIdStr = escapeHtml(String(estimate.id));
                var displayNameEscaped = estimateDisplayNameEscaped(estimate);

                html += `
                <div class="col-md-6 col-lg-3">
                    <div class="card h-100" data-estimate-id="${estimateIdStr}">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <div class="d-flex align-items-center gap-2" style="min-width: 0;">
                                <strong style="white-space: nowrap;">견적 ${index + 1}</strong>
                                <span class="text-muted" style="white-space: nowrap;">·</span>
                                <span class="estimate-display-name fw-bold text-truncate" style="max-width: 180px;" title="${displayNameEscaped}">${displayNameEscaped}</span>
                                <button class="btn btn-sm btn-link p-0 text-primary edit-estimate-name-btn" data-estimate-id="${estimateIdStr}" title="이름 수정">
                                    <i class="fas fa-pen"></i>
                                </button>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary edit-estimate-btn" data-estimate-id="${estimateIdStr}" title="수정">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn btn-sm btn-outline-danger delete-estimate-btn" data-estimate-id="${estimateIdStr}" title="삭제">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                        <div class="card-body">${buildEstimateCardBodyHtml(estimate, displayNameEscaped)}</div>
                    </div>
                </div>
            `;
            });

            if (estimates.length > 0) {
                if (estimates.length === 2) {
                    html += '<div class="w-100 d-none d-lg-block"></div>';
                }

                var colClass = "col-md-12";
                if (estimates.length === 1) {
                    colClass = "col-md-6 col-lg-3";
                } else if (estimates.length === 2) {
                    colClass = "col-md-12 col-lg-6";
                } else if (estimates.length === 3) {
                    colClass = "col-md-12 col-lg-9";
                } else {
                    colClass = "col-md-12 col-lg-12";
                }

                if (estimates.length === 1) {
                    html += `
                    <div class="${colClass} mt-3" id="totalEstimatesSummary">
                        <div class="card border-primary">
                            <div class="card-header bg-primary text-white">
                                <h5 class="mb-0"><i class="fas fa-calculator"></i> 전체 견적 총 합계</h5>
                            </div>
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <span>기본 견적 총합:</span>
                                    <strong id="totalAllBasePrice">0원</strong>
                                </div>
                                <div class="d-flex justify-content-between align-items-center mb-3">
                                    <span>추가 옵션 총합:</span>
                                    <strong id="totalAllAdditionalPrice">0원</strong>
                                </div>
                                <hr>
                                <div class="card bg-light final-summary-card text-center mt-3">
                                    <div class="card-body">
                                        <h6 class="card-title mb-3">최종 견적</h6>
                                        <div class="final-price-display mb-2" id="totalAllFinalPrice">0원</div>
                                        <small class="text-muted" id="totalAllCouponInfo">쿠폰가 미적용</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                } else {
                    html += `
                    <div class="${colClass} mt-3" id="totalEstimatesSummary">
                        <div class="card border-primary">
                            <div class="card-header bg-primary text-white">
                                <h5 class="mb-0"><i class="fas fa-calculator"></i> 전체 견적 총 합계</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <div class="d-flex justify-content-between align-items-center mb-2">
                                            <span>기본 견적 총합:</span>
                                            <strong id="totalAllBasePrice">0원</strong>
                                        </div>
                                        <div class="d-flex justify-content-between align-items-center mb-2">
                                            <span>추가 옵션 총합:</span>
                                            <strong id="totalAllAdditionalPrice">0원</strong>
                                        </div>
                                        <hr>
                                        <div class="d-flex justify-content-between align-items-center">
                                            <span class="h5 mb-0">총 견적 합계:</span>
                                            <strong class="h4 text-primary mb-0" id="totalAllPrice">0원</strong>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="card bg-light final-summary-card text-center">
                                            <div class="card-body">
                                                <h6 class="card-title mb-3">최종 견적</h6>
                                                <div class="final-price-display mb-2" id="totalAllFinalPrice">0원</div>
                                                <small class="text-muted" id="totalAllCouponInfo">쿠폰가 미적용</small>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                }
            }

            html += "</div>";
            container.innerHTML = html;

            setTimeoutImpl(function () {
                applyForcedStyles(container);
            }, 10);

            var saveBtnInList = documentRef.getElementById("saveEstimateBtn");
            if (saveBtnInList) {
                saveBtnInList.style.display =
                    estimates.length > 0 ? "block" : saveBtnInList.style.display;
            }

            onRenderComplete();
        }

        ns.configure = configure;
        ns.renderEstimatesList = renderEstimatesList;
        ns.refreshEstimateCard = refreshEstimateCard;
    })(WdCalculatorRenderEstimatesList);

    window.WdCalculatorRenderEstimatesList = WdCalculatorRenderEstimatesList;
})();

/* --- included: reset-input-form-keep-customer.js --- */
(function () {
    var WdCalculatorResetInputFormKeepCustomer = window.WdCalculatorResetInputFormKeepCustomer || {};

    (function (ns) {
        var setEditingEstimateId = function () {};
        var setCurrentDatabaseEstimateId = function () {};
        var getEstimatesLength = function () {
            return 0;
        };
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var recalculate = function () {};
        var defaultCouponValue = 11000;
        var documentRef = document;
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.getEstimatesLength === "function") {
                getEstimatesLength = opts.getEstimatesLength;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (typeof opts.recalculate === "function") {
                recalculate = opts.recalculate;
            }
            if (typeof opts.defaultCouponValue === "number") {
                defaultCouponValue = opts.defaultCouponValue;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
        }

        function readCustomerName() {
            var customerNameEl = documentRef.getElementById("customerName");
            return customerNameEl && customerNameEl.value ? customerNameEl.value.trim() : "";
        }

        function restoreCustomerName(customerName) {
            try {
                var customerNameInput = documentRef.getElementById("customerName");
                if (customerNameInput && customerName) {
                    customerNameInput.value = customerName;
                }
            } catch (error) {
                consoleRef.error("Error restoring customer name:", error);
            }
        }

        function resetInputFormKeepCustomerName() {
            try {
                var customerName = readCustomerName();

                setEditingEstimateId(null);

                try {
                    ensureBaseComponentsUI(null);
                } catch (error) {
                    consoleRef.error("Error resetting base components:", error);
                }

                try {
                    var additionalOptionsContainer = documentRef.getElementById("additionalOptionsContainer");
                    if (additionalOptionsContainer) {
                        additionalOptionsContainer.innerHTML = "";
                    }
                } catch (error) {
                    consoleRef.error("Error resetting additional options:", error);
                }

                try {
                    resetNotesToEmpty();
                } catch (error) {
                    consoleRef.error("Error resetting notes:", error);
                }

                try {
                    var productInfo = documentRef.getElementById("productInfo");
                    if (productInfo) {
                        productInfo.style.display = "none";
                    }
                    var baseEstimateSection = documentRef.getElementById("baseEstimateSection");
                    if (baseEstimateSection) {
                        baseEstimateSection.style.display = "none";
                    }
                } catch (error) {
                    consoleRef.error("Error hiding estimate sections:", error);
                }

                try {
                    [
                        "totalBasePrice",
                        "totalAdditionalPrice",
                        "totalPrice",
                        "finalPrice",
                        "baseEstimateDetail",
                        "additionalOptionsDetail",
                    ].forEach(function (id) {
                        try {
                            var el = documentRef.getElementById(id);
                            if (el) {
                                if (id.indexOf("Detail") >= 0) {
                                    el.textContent = "";
                                } else {
                                    el.textContent = "0원";
                                }
                            }
                        } catch (error) {
                            consoleRef.error("Error resetting " + id + ":", error);
                        }
                    });
                } catch (error) {
                    consoleRef.error("Error resetting price elements:", error);
                }

                try {
                    var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
                    if (addEstimateBtn) {
                        addEstimateBtn.innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                        addEstimateBtn.style.display = "none";
                    }

                    var saveEstimateBtn = documentRef.getElementById("saveEstimateBtn");
                    if (saveEstimateBtn && getEstimatesLength() === 0) {
                        saveEstimateBtn.style.display = "none";
                    }
                } catch (error) {
                    consoleRef.error("Error resetting buttons:", error);
                }

                restoreCustomerName(customerName);

                try {
                    recalculate();
                } catch (error) {
                    consoleRef.error("Error in calculateEstimate/calculateTotalEstimates:", error);
                }
            } catch (error) {
                consoleRef.error("Critical error in resetInputFormKeepCustomerName:", error);
                try {
                    var customerName = readCustomerName();
                    var customerNameInput = documentRef.getElementById("customerName");
                    if (customerNameInput && customerName) {
                        customerNameInput.value = customerName;
                    }
                } catch (restoreError) {
                    consoleRef.error("Error restoring customer name in error handler:", restoreError);
                }
            }
        }

        function resetInputFormToNewEstimate() {
            try {
                setEditingEstimateId(null);
                try {
                    setCurrentDatabaseEstimateId(null);
                } catch (e1) {
                    consoleRef.error("Error clearing database estimate id:", e1);
                }

                try {
                    var cn = documentRef.getElementById("customerName");
                    if (cn) {
                        cn.value = "";
                    }
                } catch (e2) {
                    consoleRef.error("Error clearing customer name:", e2);
                }

                try {
                    var headerTitle = documentRef.querySelector(".header-primary h6");
                    if (headerTitle) {
                        headerTitle.innerHTML = '<i class="fas fa-edit me-2"></i>견적 정보 입력';
                    }
                } catch (e3) {
                    consoleRef.error("Error restoring default header:", e3);
                }

                try {
                    var resetBtn = documentRef.getElementById("resetEstimateBtn");
                    if (resetBtn && resetBtn.parentNode) {
                        resetBtn.parentNode.removeChild(resetBtn);
                    }
                } catch (e4) {
                    consoleRef.error("Error removing reset estimate button:", e4);
                }

                try {
                    var couponInput = documentRef.getElementById("globalCouponValue");
                    if (couponInput) {
                        couponInput.value = String(defaultCouponValue);
                    }
                    var shippingCostInput = documentRef.getElementById("shippingCost");
                    if (shippingCostInput) {
                        shippingCostInput.value = "0";
                    }
                    var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
                    if (shippingIncludedCheckbox) {
                        shippingIncludedCheckbox.checked = true;
                    }
                } catch (e5) {
                    consoleRef.error("Error restoring coupon/shipping defaults:", e5);
                }

                try {
                    ensureBaseComponentsUI(null);
                } catch (error) {
                    consoleRef.error("Error resetting base components:", error);
                }

                try {
                    var additionalOptionsContainer = documentRef.getElementById("additionalOptionsContainer");
                    if (additionalOptionsContainer) {
                        additionalOptionsContainer.innerHTML = "";
                    }
                } catch (error) {
                    consoleRef.error("Error resetting additional options:", error);
                }

                try {
                    resetNotesToEmpty();
                } catch (error) {
                    consoleRef.error("Error resetting notes:", error);
                }

                try {
                    var productInfo = documentRef.getElementById("productInfo");
                    if (productInfo) {
                        productInfo.style.display = "none";
                    }
                    var baseEstimateSection = documentRef.getElementById("baseEstimateSection");
                    if (baseEstimateSection) {
                        baseEstimateSection.style.display = "none";
                    }
                } catch (error) {
                    consoleRef.error("Error hiding estimate sections:", error);
                }

                try {
                    [
                        "totalBasePrice",
                        "totalAdditionalPrice",
                        "totalPrice",
                        "finalPrice",
                        "baseEstimateDetail",
                        "additionalOptionsDetail",
                    ].forEach(function (id) {
                        try {
                            var el = documentRef.getElementById(id);
                            if (el) {
                                if (id.indexOf("Detail") >= 0) {
                                    el.textContent = "";
                                } else {
                                    el.textContent = "0원";
                                }
                            }
                        } catch (error) {
                            consoleRef.error("Error resetting " + id + ":", error);
                        }
                    });
                    var unitMeta = documentRef.getElementById("currentQuoteUnitPriceMeta");
                    if (unitMeta) {
                        unitMeta.textContent = "";
                        unitMeta.classList.add("text-muted");
                    }
                } catch (error) {
                    consoleRef.error("Error resetting price elements:", error);
                }

                try {
                    var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
                    if (addEstimateBtn) {
                        addEstimateBtn.innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                        addEstimateBtn.style.display = "none";
                    }

                    var saveEstimateBtn = documentRef.getElementById("saveEstimateBtn");
                    if (saveEstimateBtn && getEstimatesLength() === 0) {
                        saveEstimateBtn.style.display = "none";
                    }
                } catch (error) {
                    consoleRef.error("Error resetting buttons:", error);
                }

                try {
                    recalculate();
                } catch (error) {
                    consoleRef.error("Error in calculateEstimate/calculateTotalEstimates:", error);
                }
            } catch (error) {
                consoleRef.error("Critical error in resetInputFormToNewEstimate:", error);
            }
        }

        ns.configure = configure;
        ns.resetInputFormKeepCustomerName = resetInputFormKeepCustomerName;
        ns.resetInputFormToNewEstimate = resetInputFormToNewEstimate;
    })(WdCalculatorResetInputFormKeepCustomer);

    window.WdCalculatorResetInputFormKeepCustomer = WdCalculatorResetInputFormKeepCustomer;
})();

/* --- included: load-estimate-to-input-form.js --- */
(function () {
    var WdCalculatorLoadEstimateToInputForm = window.WdCalculatorLoadEstimateToInputForm || {};

    (function (ns) {
        var setLoadingState = function () {};
        var getEditingEstimateId = function () {
            return null;
        };
        var getEstimates = function () {
            return [];
        };
        var normalizeId = function (value) {
            return value;
        };
        var isSameId = function (left, right) {
            return left === right;
        };
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var loadAdditionalOptionRows = function () {};
        var loadNotes = function () {};
        var setEditingEstimateId = function () {};
        var calculateEstimate = function () {};
        var documentRef = document;
        var consoleRef = window.console || console;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};

        function configure(options) {
            var opts = options || {};
            if (typeof opts.setLoadingState === "function") {
                setLoadingState = opts.setLoadingState;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.normalizeId === "function") {
                normalizeId = opts.normalizeId;
            }
            if (typeof opts.isSameId === "function") {
                isSameId = opts.isSameId;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (typeof opts.loadAdditionalOptionRows === "function") {
                loadAdditionalOptionRows = opts.loadAdditionalOptionRows;
            }
            if (typeof opts.loadNotes === "function") {
                loadNotes = opts.loadNotes;
            }
            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
        }

        function buildLegacyBaseComponents(estimate) {
            var legacy = [];
            if (estimate.manualPricing) {
                legacy.push({
                    mode: "manual",
                    widthMm: estimate.widthMm || 0,
                    manualPricing: estimate.manualPricing,
                });
            } else if (estimate.productId) {
                legacy.push({
                    mode: "select",
                    widthMm: estimate.widthMm || 0,
                    productId: estimate.productId,
                });
            } else {
                legacy.push({ mode: "select" });
            }
            return legacy;
        }

        function loadEstimateToInputForm(estimateId) {
            setLoadingState(true);

            try {
                var editingEstimateId = getEditingEstimateId();
                var estimates = getEstimates() || [];

                if (editingEstimateId) {
                    var currentEstimate = estimates.find(function (est) {
                        return isSameId(est.id, editingEstimateId);
                    });
                    if (currentEstimate) {
                        var hasChanges = confirmImpl(
                            "현재 수정 중인 견적이 있습니다. 다른 견적을 불러오시겠습니까?\n(현재 수정 내용은 저장되지 않습니다)"
                        );
                        if (!hasChanges) {
                            return;
                        }
                    }
                }

                var normalizedId = normalizeId(estimateId);
                if (!normalizedId) {
                    consoleRef.error("Invalid estimate ID");
                    alertImpl("잘못된 견적 ID입니다.");
                    return;
                }

                var estimate = estimates.find(function (est) {
                    return isSameId(est.id, normalizedId);
                });
                if (!estimate) {
                    consoleRef.error("견적을 찾을 수 없습니다.");
                    consoleRef.error("Requested ID:", normalizedId);
                    consoleRef.error(
                        "Available IDs:",
                        estimates.map(function (item) {
                            return item.id;
                        })
                    );
                    alertImpl("견적을 찾을 수 없습니다. (ID: " + normalizedId + ")");
                    return;
                }

                documentRef.getElementById("additionalOptionsContainer").innerHTML = "";
                resetNotesToEmpty();

                if (estimate.baseComponents && Array.isArray(estimate.baseComponents) && estimate.baseComponents.length > 0) {
                    ensureBaseComponentsUI(estimate.baseComponents);
                } else {
                    ensureBaseComponentsUI(buildLegacyBaseComponents(estimate));
                }

                var container = documentRef.getElementById("additionalOptionsContainer");
                loadAdditionalOptionRows(container, estimate.options, {
                    formatPriceOnInput: true,
                });
                loadNotes(estimate.notes || "");

                setEditingEstimateId(estimate.id);

                var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
                addEstimateBtn.innerHTML = '<i class="fas fa-save"></i> 견적 수정 적용';
                addEstimateBtn.style.display = "block";

                var isBuilderMobile =
                    documentRef.body &&
                    documentRef.body.classList &&
                    documentRef.body.classList.contains("wd-builder");
                if (!isBuilderMobile) {
                    var scrollTarget =
                        documentRef.getElementById("baseComponentsContainer") ||
                        documentRef.getElementById("customerName") ||
                        documentRef.querySelector(".header-primary");
                    if (scrollTarget && typeof scrollTarget.scrollIntoView === "function") {
                        scrollTarget.scrollIntoView({ behavior: "smooth", block: "center" });
                    }
                }

                calculateEstimate();
            } catch (error) {
                consoleRef.error("Error in loadEstimateToInputForm:", error);
                alertImpl("견적을 불러오는 중 오류가 발생했습니다: " + (error.message || error));
            } finally {
                setLoadingState(false);
            }
        }

        ns.configure = configure;
        ns.loadEstimateToInputForm = loadEstimateToInputForm;
    })(WdCalculatorLoadEstimateToInputForm);

    window.WdCalculatorLoadEstimateToInputForm = WdCalculatorLoadEstimateToInputForm;
})();

/* --- included: load-saved-estimate-to-form.js --- */
(function () {
    var WdCalculatorLoadSavedEstimateToForm = window.WdCalculatorLoadSavedEstimateToForm || {};

    (function (ns) {
        var setCurrentDatabaseEstimateId = function () {};
        var setEstimates = function () {};
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var formatNumber = function (value) {
            return String(value || 0);
        };
        var renderEstimatesList = function () {};
        var ensureBaseComponentsUI = function () {};
        var calculateEstimate = function () {};
        var resetNotesToEmpty = function () {};
        var documentRef = document;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var reloadImpl = function () {
            if (window.location && typeof window.location.reload === "function") {
                window.location.reload();
            }
        };

        function configure(options) {
            var opts = options || {};
            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.reloadImpl === "function") {
                reloadImpl = opts.reloadImpl;
            }
        }

        function ensureResetEstimateButton() {
            var resetBtn = documentRef.getElementById("resetEstimateBtn");
            if (resetBtn) {
                return resetBtn;
            }

            var btnContainer = documentRef.querySelector(".header-primary");
            resetBtn = documentRef.createElement("button");
            resetBtn.id = "resetEstimateBtn";
            resetBtn.className = "btn btn-sm btn-light float-end";
            resetBtn.innerHTML = '<i class="fas fa-undo"></i> 새 견적 작성';
            resetBtn.onclick = function () {
                if (confirmImpl("현재 작성/수정 중인 내용을 초기화하고 새 견적을 작성하시겠습니까?")) {
                    reloadImpl();
                }
            };
            if (btnContainer && typeof btnContainer.appendChild === "function") {
                btnContainer.appendChild(resetBtn);
            }
            return resetBtn;
        }

        function hydrateEstimateItems(estimateData) {
            var globalNotes = estimateData.notes || "";
            return estimateData.estimates.map(function (est) {
                var newId = est.id ? String(est.id) : generateEstimateId();
                return {
                    id: newId,
                    productId: est.productId,
                    productName: est.productName,
                    displayName: est.displayName || ((est.productName || "") + " " + formatNumber(est.widthMm) + "mm"),
                    widthMm: est.widthMm,
                    basePrice: est.basePrice,
                    options: est.options || [],
                    additionalPrice: est.additionalPrice || 0,
                    totalPrice: est.totalPrice || 0,
                    baseComponents: est.baseComponents || null,
                    notes: est.notes || globalNotes,
                };
            });
        }

        function loadEstimateToForm(estimate) {
            setCurrentDatabaseEstimateId(estimate.id);

            var estimateData = estimate.estimate_data || {};
            var displayCustomerName =
                estimate.customer_name != null ? estimate.customer_name : estimate.customerName;
            if (displayCustomerName != null) {
                displayCustomerName = String(displayCustomerName);
            } else {
                displayCustomerName = "";
            }

            var headerTitle = documentRef.querySelector(".header-primary h6");
            if (headerTitle) {
                headerTitle.innerHTML =
                    '<i class="fas fa-edit me-2"></i>견적 수정: ' +
                    displayCustomerName +
                    ' <span class="badge bg-warning text-dark ms-2">수정모드</span>';
            }

            ensureResetEstimateButton();

            var customerNameEl = documentRef.getElementById("customerName");
            if (customerNameEl) {
                customerNameEl.value = displayCustomerName;
            }

            var couponInput = documentRef.getElementById("globalCouponValue");
            if (couponInput) {
                couponInput.value = estimateData.coupon_discount || 0;
            }

            var shippingCostInput = documentRef.getElementById("shippingCost");
            if (shippingCostInput) {
                shippingCostInput.value = estimateData.shipping_cost || 0;
            }

            var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
            if (shippingIncludedCheckbox) {
                shippingIncludedCheckbox.checked =
                    estimateData.shipping_included !== undefined ? estimateData.shipping_included : true;
            }

            resetNotesToEmpty();
            setEstimates([]);

            if (estimateData.estimates && estimateData.estimates.length > 0) {
                setEstimates(hydrateEstimateItems(estimateData));
                renderEstimatesList();

                var saveBtnAfterLoad = documentRef.getElementById("saveEstimateBtn");
                if (saveBtnAfterLoad) {
                    saveBtnAfterLoad.style.display = "block";
                }

                ensureBaseComponentsUI();
                documentRef.getElementById("additionalOptionsContainer").innerHTML = "";
                documentRef.getElementById("productInfo").style.display = "none";
                documentRef.getElementById("baseEstimateSection").style.display = "none";
                documentRef.getElementById("addEstimateBtn").innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                documentRef.getElementById("addEstimateBtn").style.display = "none";
                calculateEstimate();
            }
        }

        ns.configure = configure;
        ns.loadEstimateToForm = loadEstimateToForm;
    })(WdCalculatorLoadSavedEstimateToForm);

    window.WdCalculatorLoadSavedEstimateToForm = WdCalculatorLoadSavedEstimateToForm;
})();
/* --- included: save-estimate.js --- */
(function () {
    var WdCalculatorSaveEstimate = window.WdCalculatorSaveEstimate || {};

    (function (ns) {
        var getCurrentDatabaseEstimateId = function () {
            return null;
        };
        var setCurrentDatabaseEstimateId = function () {};
        var getEstimates = function () {
            return [];
        };
        var collectCurrentEstimate = function () {
            return null;
        };
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var collectNotes = function () {
            return "";
        };
        var getCouponValue = function () {
            return 0;
        };
        var resolveAggregateTotals = function () {
            return {
                totalBasePrice: 0,
                totalAdditionalPrice: 0,
                totalPrice: 0,
            };
        };
        var refreshAfterSave = function () {};
        var documentRef = document;
        var fetchImpl = typeof window.fetch === "function" ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };
        var alertImpl = typeof window.alert === "function" ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getCurrentDatabaseEstimateId === "function") {
                getCurrentDatabaseEstimateId = opts.getCurrentDatabaseEstimateId;
            }
            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.collectCurrentEstimate === "function") {
                collectCurrentEstimate = opts.collectCurrentEstimate;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
            }
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.resolveAggregateTotals === "function") {
                resolveAggregateTotals = opts.resolveAggregateTotals;
            }
            if (typeof opts.refreshAfterSave === "function") {
                refreshAfterSave = opts.refreshAfterSave;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
        }

        function readShippingState() {
            var shippingCostInput = documentRef.getElementById("shippingCost");
            var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
            return {
                shippingCost: shippingCostInput ? parseFloat(shippingCostInput.value) || 0 : 0,
                shippingIncluded: shippingIncludedCheckbox ? shippingIncludedCheckbox.checked : true,
            };
        }

        function buildEstimatesToSave() {
            var estimatesToSave = getEstimates();
            if (estimatesToSave.length > 0) {
                return estimatesToSave;
            }

            var currentEstimate = collectCurrentEstimate();
            if (!currentEstimate) {
                alertImpl("저장할 견적이 없습니다. 먼저 견적을 계산해주세요.");
                return null;
            }
            currentEstimate.id = generateEstimateId();
            return [currentEstimate];
        }

        function buildEstimateData(estimatesToSave, notes, couponValue, shippingCost, shippingIncluded) {
            var aggSave = resolveAggregateTotals(estimatesToSave, couponValue, shippingCost, shippingIncluded);
            var couponDiscount = couponValue > 0 ? couponValue : 0;
            return {
                estimates: estimatesToSave,
                totalBasePrice: aggSave.totalBasePrice,
                totalAdditionalPrice: aggSave.totalAdditionalPrice,
                totalPrice: aggSave.totalPrice,
                coupon_discount: couponDiscount,
                shipping_cost: shippingCost,
                shipping_included: shippingIncluded,
                notes: notes,
            };
        }

        function restoreSaveButton(buttonEl, originalText) {
            buttonEl.disabled = false;
            buttonEl.innerHTML = originalText;
        }

        function readOrderIdFromUrl() {
            try {
                var search = window.location && window.location.search ? window.location.search : "";
                return new URLSearchParams(search).get("order_id") || "";
            } catch (error) {
                return "";
            }
        }

        function handleSaveEstimate(buttonEl) {
            var customerNameEl = documentRef.getElementById("customerName");
            var customerName = customerNameEl ? customerNameEl.value.trim() : "";
            if (!customerName) {
                alertImpl("고객명을 입력해주세요.");
                return Promise.resolve(null);
            }

            var estimatesToSave = buildEstimatesToSave();
            if (!estimatesToSave) {
                return Promise.resolve(null);
            }

            var notes = collectNotes();
            var couponValue = getCouponValue();
            var shippingState = readShippingState();
            var estimateData;
            try {
                estimateData = buildEstimateData(
                    estimatesToSave,
                    notes,
                    couponValue,
                    shippingState.shippingCost,
                    shippingState.shippingIncluded
                );
            } catch (error) {
                consoleRef.error(error);
                alertImpl(error.message || String(error));
                return Promise.resolve(null);
            }

            var originalText = buttonEl.innerHTML;
            buttonEl.disabled = true;
            buttonEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';

            var orderIdFromUrl = readOrderIdFromUrl();
            var payload = {
                estimate_id: getCurrentDatabaseEstimateId(),
                customer_name: customerName,
                estimate_data: estimateData,
            };
            if (orderIdFromUrl) {
                payload.order_id = orderIdFromUrl;
                payload.estimate_data.order_id = orderIdFromUrl;
            }

            return fetchImpl("/api/wdcalculator/save-estimate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    restoreSaveButton(buttonEl, originalText);

                    if (data.success) {
                        alertImpl(data.message);

                        if (orderIdFromUrl && data.estimate_id) {
                            setCurrentDatabaseEstimateId(data.estimate_id);
                            return data;
                        }
                        refreshAfterSave(data.estimate_id || null);
                        return data;
                    }

                    alertImpl(data.message || "견적 저장 중 오류가 발생했습니다.");
                    return data;
                })
                .catch(function (error) {
                    restoreSaveButton(buttonEl, originalText);
                    consoleRef.error("Error:", error);
                    alertImpl("견적 저장 중 오류가 발생했습니다.");
                    return null;
                });
        }

        function initSaveEstimateButton() {
            var saveEstimateBtn = documentRef.getElementById("saveEstimateBtn");
            if (!saveEstimateBtn) {
                if (consoleRef && typeof consoleRef.warn === "function") {
                    consoleRef.warn("saveEstimateBtn element not found");
                }
                return null;
            }

            var newSaveBtn = saveEstimateBtn.cloneNode(true);
            saveEstimateBtn.parentNode.replaceChild(newSaveBtn, saveEstimateBtn);
            newSaveBtn.addEventListener("click", function () {
                handleSaveEstimate(newSaveBtn);
            });
            return newSaveBtn;
        }

        ns.configure = configure;
        ns.buildEstimateData = buildEstimateData;
        ns.handleSaveEstimate = handleSaveEstimate;
        ns.initSaveEstimateButton = initSaveEstimateButton;
    })(WdCalculatorSaveEstimate);

    window.WdCalculatorSaveEstimate = WdCalculatorSaveEstimate;
})();

/* --- included: add-estimate.js --- */
(function () {
    var WdCalculatorAddEstimate = window.WdCalculatorAddEstimate || {};

    (function (ns) {
        var getEditingEstimateId = function () {
            return null;
        };
        var setEditingEstimateId = function () {};
        var getEstimates = function () {
            return [];
        };
        var collectCurrentEstimate = function () {
            return null;
        };
        var normalizeId = function (value) {
            return value;
        };
        var isSameId = function (left, right) {
            return String(left) === String(right);
        };
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var renderEstimatesList = function () {};
        var resetInputFormKeepCustomerName = function () {};
        var resetInputFormToNewEstimate = function () {};
        var documentRef = document;
        var alertImpl = typeof window.alert === "function" ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.collectCurrentEstimate === "function") {
                collectCurrentEstimate = opts.collectCurrentEstimate;
            }
            if (typeof opts.normalizeId === "function") {
                normalizeId = opts.normalizeId;
            }
            if (typeof opts.isSameId === "function") {
                isSameId = opts.isSameId;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
        }

        function getBaseComponents(estimate) {
            return estimate && Array.isArray(estimate.baseComponents) ? estimate.baseComponents : [];
        }

        function compareEstimateIdentity(existingEstimate, nextEstimate) {
            var productChanged = false;
            var widthChanged = false;
            var oldBaseComponents = getBaseComponents(existingEstimate);
            var newBaseComponents = getBaseComponents(nextEstimate);

            if (oldBaseComponents.length !== newBaseComponents.length) {
                productChanged = true;
                return {
                    productChanged: productChanged,
                    widthChanged: widthChanged,
                };
            }

            for (var i = 0; i < oldBaseComponents.length; i += 1) {
                var oldComp = oldBaseComponents[i];
                var newComp = newBaseComponents[i];
                var oldProductId = (oldComp && oldComp.productId) || null;
                var newProductId = (newComp && newComp.productId) || null;

                if (oldProductId !== newProductId) {
                    productChanged = true;
                    break;
                }

                if ((oldComp && oldComp.mode) !== (newComp && newComp.mode)) {
                    productChanged = true;
                    break;
                }

                var oldWidthMm = Number(oldComp && oldComp.widthMm) || 0;
                var newWidthMm = Number(newComp && newComp.widthMm) || 0;
                var oldWidthInput = String((oldComp && oldComp.widthInput) || "").trim();
                var newWidthInput = String((newComp && newComp.widthInput) || "").trim();
                if (oldWidthMm !== newWidthMm || oldWidthInput !== newWidthInput) {
                    widthChanged = true;
                }
            }

            return {
                productChanged: productChanged,
                widthChanged: widthChanged,
            };
        }

        function updateExistingEstimate(estimates, index, nextEstimate) {
            var originalId = estimates[index].id;
            var existingEstimate = estimates[index];
            var comparison = compareEstimateIdentity(existingEstimate, nextEstimate);

            if (comparison.productChanged || comparison.widthChanged) {
                if (consoleRef && typeof consoleRef.log === "function") {
                    consoleRef.log("제품 또는 가로 길이 변경 감지 - 최신 제품 이름으로 업데이트");
                }
                estimates[index] = Object.assign({}, nextEstimate, {
                    id: originalId,
                    productName: nextEstimate.productName,
                    displayName: nextEstimate.displayName,
                });
                return estimates[index];
            }

            estimates[index] = Object.assign({}, nextEstimate, {
                id: originalId,
                displayName: existingEstimate.displayName || nextEstimate.displayName,
            });
            return estimates[index];
        }

        function handleAddEstimate(buttonEl) {
            var estimate = collectCurrentEstimate();
            if (!estimate) {
                alertImpl("견적 정보를 입력해주세요.");
                return false;
            }

            var estimates = getEstimates();
            var normalizedEditingId = normalizeId(getEditingEstimateId());

            if (normalizedEditingId) {
                var index = estimates.findIndex(function (item) {
                    return isSameId(item.id, normalizedEditingId);
                });

                if (index === -1) {
                    if (consoleRef && typeof consoleRef.error === "function") {
                        consoleRef.error("견적을 찾을 수 없습니다.");
                        consoleRef.error("editingEstimateId:", normalizedEditingId);
                        consoleRef.error(
                            "Available IDs:",
                            estimates.map(function (item) {
                                return item.id;
                            })
                        );
                    }
                    alertImpl("수정할 견적을 찾을 수 없습니다.");
                    return false;
                }

                updateExistingEstimate(estimates, index, estimate);
                setEditingEstimateId(null);
                if (buttonEl) {
                    buttonEl.innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                }
                renderEstimatesList();
                /* 저장(견적 저장) 전까지 고객명·DB 견적 ID·수정모드 헤더 유지 — 완전 리셋은 refreshAfterSave만 */
                resetInputFormKeepCustomerName();
                return true;
            }

            estimate.id = generateEstimateId();
            estimates.push(estimate);

            renderEstimatesList();
            resetInputFormKeepCustomerName();
            return true;
        }

        function bindFollowUpSaveButtonVisibility(buttonEl) {
            var originalAddEstimate = buttonEl.onclick;
            buttonEl.addEventListener("click", function () {
                if (originalAddEstimate) {
                    originalAddEstimate.call(this);
                }

                if ((getEstimates() || []).length > 0) {
                    var saveBtn = documentRef.getElementById("saveEstimateBtn");
                    if (saveBtn) {
                        saveBtn.style.display = "block";
                    }
                }
            });
        }

        function initAddEstimateButton() {
            var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
            if (!addEstimateBtn) {
                return null;
            }

            addEstimateBtn.addEventListener("click", function () {
                handleAddEstimate(addEstimateBtn);
            });
            bindFollowUpSaveButtonVisibility(addEstimateBtn);
            return addEstimateBtn;
        }

        ns.compareEstimateIdentity = compareEstimateIdentity;
        ns.configure = configure;
        ns.handleAddEstimate = handleAddEstimate;
        ns.initAddEstimateButton = initAddEstimateButton;
        ns.updateExistingEstimate = updateExistingEstimate;
    })(WdCalculatorAddEstimate);

    window.WdCalculatorAddEstimate = WdCalculatorAddEstimate;
})();

/* --- included: estimate-list-events.js --- */
(function () {
    function fallbackFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    var WdCalculatorEstimateListEvents = window.WdCalculatorEstimateListEvents || {};

    (function (ns) {
        var getLoadingState = function () {
            return false;
        };
        var getEstimates = function () {
            return [];
        };
        var setEstimates = function () {};
        var getEditingEstimateId = function () {
            return null;
        };
        var setEditingEstimateId = function () {};
        var loadEstimateToInputForm = function () {};
        var renderEstimatesList = function () {};
        var formatNumber = window.formatNumber || fallbackFormatNumber;
        var normalizeId =
            window.normalizeId ||
            function (value) {
                return value;
            };
        var isSameId =
            window.isSameId ||
            function (left, right) {
                return String(left) === String(right);
            };
        var documentRef = document;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var consoleRef = window.console || console;
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getLoadingState === "function") {
                getLoadingState = opts.getLoadingState;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.loadEstimateToInputForm === "function") {
                loadEstimateToInputForm = opts.loadEstimateToInputForm;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.normalizeId === "function") {
                normalizeId = opts.normalizeId;
            }
            if (typeof opts.isSameId === "function") {
                isSameId = opts.isSameId;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
        }

        function cleanupInlineNameEdit(context) {
            if (!context.isEditing) {
                return;
            }

            context.isEditing = false;

            try {
                if (context.input && context.input.parentNode) {
                    context.input.remove();
                }
                if (context.saveBtn && context.saveBtn.parentNode) {
                    context.saveBtn.remove();
                }
                if (context.cancelBtn && context.cancelBtn.parentNode) {
                    context.cancelBtn.remove();
                }
                if (context.nameSpan) {
                    context.nameSpan.style.display = "";
                }
                if (context.editNameBtn) {
                    context.editNameBtn.style.display = "";
                }
            } catch (error) {
                consoleRef.error("Error in cleanup:", error);
            }
        }

        function commitInlineNameEdit(context) {
            if (context.isCommitting || !context.isEditing) {
                cleanupInlineNameEdit(context);
                return;
            }

            context.isCommitting = true;

            try {
                if (!context.input || !context.input.parentNode) {
                    cleanupInlineNameEdit(context);
                    return;
                }

                var newName = (context.input.value || "").trim();
                if (!newName) {
                    cleanupInlineNameEdit(context);
                    return;
                }

                context.estimates[context.index].displayName = newName;
                cleanupInlineNameEdit(context);

                setTimeoutImpl(function () {
                    try {
                        renderEstimatesList();
                    } catch (error) {
                        consoleRef.error("Error in renderEstimatesList after commit:", error);
                    }
                    context.isCommitting = false;
                }, 10);
            } catch (error) {
                consoleRef.error("Error in commit:", error);
                cleanupInlineNameEdit(context);
                context.isCommitting = false;
            }
        }

        function openDisplayNameEditor(editNameBtn, estimates, index) {
            var cardEl = editNameBtn.closest(".card");
            var nameSpan = cardEl ? cardEl.querySelector(".estimate-display-name") : null;
            if (!cardEl || !nameSpan) {
                return;
            }

            if (cardEl.querySelector(".estimate-display-name-input")) {
                return;
            }

            var estimate = estimates[index];
            var currentName =
                estimate.displayName ||
                ((estimate.productName || "") + " " + formatNumber(estimate.widthMm) + "mm");

            var input = documentRef.createElement("input");
            input.type = "text";
            input.value = currentName;
            input.className = "form-control form-control-sm estimate-display-name-input";
            input.style.maxWidth = "220px";
            input.style.display = "inline-block";

            var saveBtn = documentRef.createElement("button");
            saveBtn.type = "button";
            saveBtn.className = "btn btn-sm btn-link p-0 text-success ms-1 estimate-display-name-save-btn";
            saveBtn.innerHTML = '<i class="fas fa-check"></i>';
            saveBtn.title = "저장";

            var cancelBtn = documentRef.createElement("button");
            cancelBtn.type = "button";
            cancelBtn.className = "btn btn-sm btn-link p-0 text-danger ms-1 estimate-display-name-cancel-btn";
            cancelBtn.innerHTML = '<i class="fas fa-times"></i>';
            cancelBtn.title = "취소";

            nameSpan.style.display = "none";
            editNameBtn.style.display = "none";

            nameSpan.insertAdjacentElement("afterend", cancelBtn);
            nameSpan.insertAdjacentElement("afterend", saveBtn);
            nameSpan.insertAdjacentElement("afterend", input);

            var context = {
                cancelBtn: cancelBtn,
                editNameBtn: editNameBtn,
                estimates: estimates,
                index: index,
                input: input,
                isCommitting: false,
                isEditing: true,
                nameSpan: nameSpan,
                saveBtn: saveBtn,
            };

            saveBtn.addEventListener("click", function (event) {
                event.stopPropagation();
                event.preventDefault();
                commitInlineNameEdit(context);
            });

            cancelBtn.addEventListener("click", function (event) {
                event.stopPropagation();
                event.preventDefault();
                cleanupInlineNameEdit(context);
            });

            input.addEventListener("keydown", function (event) {
                if (!context.isEditing) {
                    return;
                }
                if (event.key === "Enter") {
                    event.preventDefault();
                    commitInlineNameEdit(context);
                } else if (event.key === "Escape") {
                    event.preventDefault();
                    cleanupInlineNameEdit(context);
                }
            });

            input.addEventListener("blur", function () {
                if (context.isEditing && !context.isCommitting) {
                    setTimeoutImpl(function () {
                        if (context.isEditing && !context.isCommitting) {
                            commitInlineNameEdit(context);
                        }
                    }, 200);
                }
            });

            setTimeoutImpl(function () {
                if (input && input.parentNode) {
                    if (typeof input.focus === "function") {
                        input.focus();
                    }
                    if (typeof input.select === "function") {
                        input.select();
                    }
                }
            }, 0);
        }

        function deleteEstimate(deleteBtn) {
            if (
                !confirmImpl("이 견적을 삭제하시겠습니까?\n\n⚠️ 삭제된 견적은 복구할 수 없습니다.")
            ) {
                return;
            }

            var estimateId = normalizeId(deleteBtn.dataset.estimateId);
            if (!estimateId) {
                return;
            }

            var estimates = getEstimates() || [];
            var nextEstimates = estimates.filter(function (estimate) {
                return !isSameId(estimate.id, estimateId);
            });
            setEstimates(nextEstimates);

            if (isSameId(getEditingEstimateId(), estimateId)) {
                setEditingEstimateId(null);
                var addBtn = documentRef.getElementById("addEstimateBtn");
                if (addBtn) {
                    addBtn.innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                }
            }

            renderEstimatesList();
        }

        function handleEstimateListClick(event) {
            var container = documentRef.getElementById("estimatesListContainer");
            if (!container || !container.contains(event.target)) {
                return;
            }

            if (getLoadingState()) {
                return;
            }

            var editBtn = event.target.closest(".edit-estimate-btn");
            if (editBtn) {
                event.stopPropagation();
                event.preventDefault();
                loadEstimateToInputForm(editBtn.dataset.estimateId);
                return;
            }

            var editNameBtn = event.target.closest(".edit-estimate-name-btn");
            if (editNameBtn) {
                event.stopPropagation();
                event.preventDefault();

                var estimateId = normalizeId(editNameBtn.dataset.estimateId);
                if (!estimateId) {
                    return;
                }

                var estimates = getEstimates() || [];
                var index = estimates.findIndex(function (estimate) {
                    return isSameId(estimate.id, estimateId);
                });
                if (index === -1) {
                    return;
                }

                openDisplayNameEditor(editNameBtn, estimates, index);
                return;
            }

            var deleteBtn = event.target.closest(".delete-estimate-btn");
            if (deleteBtn) {
                event.stopPropagation();
                event.preventDefault();
                deleteEstimate(deleteBtn);
                return;
            }

            var card = event.target.closest(".card[data-estimate-id]");
            if (card && !event.target.closest("button")) {
                loadEstimateToInputForm(card.dataset.estimateId);
            }
        }

        function initEstimateListEvents() {
            if (!documentRef || typeof documentRef.addEventListener !== "function") {
                return;
            }
            documentRef.addEventListener("click", handleEstimateListClick);
        }

        ns.commitInlineNameEdit = commitInlineNameEdit;
        ns.configure = configure;
        ns.deleteEstimate = deleteEstimate;
        ns.handleEstimateListClick = handleEstimateListClick;
        ns.initEstimateListEvents = initEstimateListEvents;
        ns.openDisplayNameEditor = openDisplayNameEditor;
    })(WdCalculatorEstimateListEvents);

    window.WdCalculatorEstimateListEvents = WdCalculatorEstimateListEvents;
})();

/* --- included: refresh-after-save.js --- */
(function () {
    var WdCalculatorRefreshAfterSave = window.WdCalculatorRefreshAfterSave || {};

    (function (ns) {
        var setEstimates = function () {};
        var resetInputFormKeepCustomerName = function () {};
        var resetInputFormToNewEstimate = function () {};
        var renderEstimatesList = function () {};
        var loadSidebarEstimates = function () {
            return Promise.resolve();
        };
        var documentRef = document;
        var consoleRef = window.console || console;
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };

        function configure(options) {
            var opts = options || {};
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.loadSidebarEstimates === "function") {
                loadSidebarEstimates = opts.loadSidebarEstimates;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
        }

        function clearLocalEstimates() {
            setEstimates([]);
        }

        function clearSavedRowHighlight(savedRow, badge) {
            if (!savedRow) {
                return;
            }
            savedRow.style.boxShadow = "";
            savedRow.style.borderColor = "";
            if (badge && typeof badge.remove === "function") {
                badge.remove();
            }
        }

        function stripEstimateIdFromUrl() {
            try {
                var w = documentRef.defaultView;
                if (!w || !w.location || !w.history || typeof w.history.replaceState !== "function") {
                    return;
                }
                var url = new URL(w.location.href);
                if (!url.searchParams.has("estimate_id")) {
                    return;
                }
                url.searchParams.delete("estimate_id");
                var next = url.pathname + (url.search ? url.search : "") + (url.hash || "");
                w.history.replaceState({}, w.document && w.document.title ? w.document.title : "", next);
            } catch (error) {
                consoleRef.error("stripEstimateIdFromUrl:", error);
            }
        }

        function highlightSavedSidebarRow(savedId) {
            if (!savedId) {
                return;
            }
            var sidebarList = documentRef.getElementById("savedEstimatesList");
            if (!sidebarList) {
                return;
            }
            var savedRow = sidebarList.querySelector('.saved-estimate-row[data-estimate-id="' + savedId + '"]');
            if (!savedRow) {
                return;
            }

            savedRow.style.transition = "box-shadow 0.3s, border-color 0.3s";
            savedRow.style.boxShadow = "0 0 0 3px #28a745aa";
            savedRow.style.borderColor = "#28a745";

            var badge = documentRef.createElement("span");
            badge.className = "badge bg-success ms-1";
            badge.textContent = "저장 완료";
            badge.style.cssText = "font-size:0.7rem;vertical-align:middle;";

            var nameEl = savedRow.querySelector(".saved-estimate-customer-name");
            if (nameEl) {
                nameEl.appendChild(badge);
                setTimeoutImpl(function () {
                    clearSavedRowHighlight(savedRow, badge);
                }, 3000);
            } else {
                setTimeoutImpl(function () {
                    clearSavedRowHighlight(savedRow);
                }, 3000);
            }
        }

        function refreshAfterSave(savedId) {
            try {
                clearLocalEstimates();
                resetInputFormToNewEstimate();
                stripEstimateIdFromUrl();

                setTimeoutImpl(function () {
                    try {
                        renderEstimatesList();
                    } catch (error) {
                        consoleRef.error("Error in renderEstimatesList during refresh:", error);
                    }

                    setTimeoutImpl(function () {
                        try {
                            loadSidebarEstimates()
                                .then(function () {
                                    if (!savedId) {
                                        return;
                                    }
                                    highlightSavedSidebarRow(savedId);
                                })
                                .catch(function () {
                                    return loadSidebarEstimates();
                                });
                        } catch (error) {
                            consoleRef.error("Error in loadSidebarEstimates during refresh:", error);
                        }
                    }, 200);
                }, 50);
            } catch (error) {
                consoleRef.error("Error in refreshAfterSave:", error);
                try {
                    clearLocalEstimates();
                    try {
                        resetInputFormToNewEstimate();
                    } catch (resetErr) {
                        consoleRef.error("Error in resetInputFormToNewEstimate (fallback):", resetErr);
                    }
                    stripEstimateIdFromUrl();
                    renderEstimatesList();
                    setTimeoutImpl(function () {
                        loadSidebarEstimates();
                    }, 300);
                } catch (fallbackError) {
                    consoleRef.error("Error in fallback refresh:", fallbackError);
                }
            }
        }

        ns.configure = configure;
        ns.highlightSavedSidebarRow = highlightSavedSidebarRow;
        ns.refreshAfterSave = refreshAfterSave;
    })(WdCalculatorRefreshAfterSave);

    window.WdCalculatorRefreshAfterSave = WdCalculatorRefreshAfterSave;
})();
/* --- included: estimate-mutation-bridge.js --- */
(function () {
    var WdCalculatorEstimateMutationBridge = window.WdCalculatorEstimateMutationBridge || {};

    (function (ns) {
        var resetFormModule = null;
        var loadInputModule = null;
        var loadSavedModule = null;
        var addEstimateModule = null;
        var listEventsModule = null;
        var saveEstimateModule = null;

        var setEditingEstimateId = function () {};
        var getEstimatesLength = function () {
            return 0;
        };
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var recalculate = function () {};

        var setLoadingState = function () {};
        var getEditingEstimateId = function () {
            return null;
        };
        var getEstimates = function () {
            return [];
        };
        var normalizeId = function (value) {
            return value;
        };
        var isSameId = function (left, right) {
            return left === right;
        };
        var loadAdditionalOptionRows = function () {};
        var loadNotes = function () {};
        var calculateEstimate = function () {};

        var setCurrentDatabaseEstimateId = function () {};
        var setEstimates = function () {};
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var formatNumber = function (num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        };
        var renderEstimatesList = function () {};
        var reloadImpl = function () {};

        var collectCurrentEstimate = function () {
            return null;
        };
        var resetInputFormKeepCustomerName = function () {};
        var resetInputFormToNewEstimate = function () {};
        var getLoadingState = function () {
            return false;
        };
        var loadEstimateToInputForm = function () {};
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };

        var getCurrentDatabaseEstimateId = function () {
            return null;
        };
        var collectNotes = function () {
            return "";
        };
        var getCouponValue = function () {
            return 0;
        };
        var resolveAggregateTotals = function () {
            return {
                totalBasePrice: 0,
                totalAdditionalPrice: 0,
                totalPrice: 0,
            };
        };
        var refreshAfterSave = function () {};

        var documentRef = document;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;
        var fetchImpl = typeof window.fetch === "function" ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };

        function configure(options) {
            var opts = options || {};

            if (opts.resetFormModule) {
                resetFormModule = opts.resetFormModule;
            }
            if (opts.loadInputModule) {
                loadInputModule = opts.loadInputModule;
            }
            if (opts.loadSavedModule) {
                loadSavedModule = opts.loadSavedModule;
            }
            if (opts.addEstimateModule) {
                addEstimateModule = opts.addEstimateModule;
            }
            if (opts.listEventsModule) {
                listEventsModule = opts.listEventsModule;
            }
            if (opts.saveEstimateModule) {
                saveEstimateModule = opts.saveEstimateModule;
            }

            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.getEstimatesLength === "function") {
                getEstimatesLength = opts.getEstimatesLength;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (typeof opts.recalculate === "function") {
                recalculate = opts.recalculate;
            }

            if (typeof opts.setLoadingState === "function") {
                setLoadingState = opts.setLoadingState;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.normalizeId === "function") {
                normalizeId = opts.normalizeId;
            }
            if (typeof opts.isSameId === "function") {
                isSameId = opts.isSameId;
            }
            if (typeof opts.loadAdditionalOptionRows === "function") {
                loadAdditionalOptionRows = opts.loadAdditionalOptionRows;
            }
            if (typeof opts.loadNotes === "function") {
                loadNotes = opts.loadNotes;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }

            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.reloadImpl === "function") {
                reloadImpl = opts.reloadImpl;
            }

            if (typeof opts.collectCurrentEstimate === "function") {
                collectCurrentEstimate = opts.collectCurrentEstimate;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (typeof opts.getLoadingState === "function") {
                getLoadingState = opts.getLoadingState;
            }
            if (typeof opts.loadEstimateToInputForm === "function") {
                loadEstimateToInputForm = opts.loadEstimateToInputForm;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }

            if (typeof opts.getCurrentDatabaseEstimateId === "function") {
                getCurrentDatabaseEstimateId = opts.getCurrentDatabaseEstimateId;
            }
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.resolveAggregateTotals === "function") {
                resolveAggregateTotals = opts.resolveAggregateTotals;
            }
            if (typeof opts.refreshAfterSave === "function") {
                refreshAfterSave = opts.refreshAfterSave;
            }

            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initEstimateMutationBridge() {
            requireMethod(
                resetFormModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires resetFormModule.configure"
            )({
                setEditingEstimateId: setEditingEstimateId,
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                getEstimatesLength: getEstimatesLength,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                recalculate: recalculate,
                defaultCouponValue: 11000,
                documentRef: documentRef,
                consoleRef: consoleRef,
            });

            requireMethod(
                loadInputModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires loadInputModule.configure"
            )({
                setLoadingState: setLoadingState,
                getEditingEstimateId: getEditingEstimateId,
                getEstimates: getEstimates,
                normalizeId: normalizeId,
                isSameId: isSameId,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                loadAdditionalOptionRows: loadAdditionalOptionRows,
                loadNotes: loadNotes,
                setEditingEstimateId: setEditingEstimateId,
                calculateEstimate: calculateEstimate,
                documentRef: documentRef,
                consoleRef: consoleRef,
                confirmImpl: confirmImpl,
                alertImpl: alertImpl,
            });

            requireMethod(
                loadSavedModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires loadSavedModule.configure"
            )({
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                setEstimates: setEstimates,
                generateEstimateId: generateEstimateId,
                formatNumber: formatNumber,
                renderEstimatesList: renderEstimatesList,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                calculateEstimate: calculateEstimate,
                resetNotesToEmpty: resetNotesToEmpty,
                documentRef: documentRef,
                confirmImpl: confirmImpl,
                reloadImpl: reloadImpl,
            });

            requireMethod(
                addEstimateModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires addEstimateModule.configure"
            )({
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                normalizeId: normalizeId,
                isSameId: isSameId,
                generateEstimateId: generateEstimateId,
                renderEstimatesList: renderEstimatesList,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                resetInputFormToNewEstimate: resetInputFormToNewEstimate,
                documentRef: documentRef,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
            });
            requireMethod(
                addEstimateModule,
                "initAddEstimateButton",
                "WdCalculatorEstimateMutationBridge requires addEstimateModule.initAddEstimateButton"
            )();

            requireMethod(
                listEventsModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires listEventsModule.configure"
            )({
                getLoadingState: getLoadingState,
                getEstimates: getEstimates,
                setEstimates: setEstimates,
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                loadEstimateToInputForm: loadEstimateToInputForm,
                renderEstimatesList: renderEstimatesList,
                formatNumber: formatNumber,
                normalizeId: normalizeId,
                isSameId: isSameId,
                documentRef: documentRef,
                confirmImpl: confirmImpl,
                consoleRef: consoleRef,
                setTimeoutImpl: setTimeoutImpl,
            });
            requireMethod(
                listEventsModule,
                "initEstimateListEvents",
                "WdCalculatorEstimateMutationBridge requires listEventsModule.initEstimateListEvents"
            )();

            requireMethod(
                saveEstimateModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires saveEstimateModule.configure"
            )({
                getCurrentDatabaseEstimateId: getCurrentDatabaseEstimateId,
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                generateEstimateId: generateEstimateId,
                collectNotes: collectNotes,
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                refreshAfterSave: refreshAfterSave,
                documentRef: documentRef,
                fetchImpl: fetchImpl,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
            });
            requireMethod(
                saveEstimateModule,
                "initSaveEstimateButton",
                "WdCalculatorEstimateMutationBridge requires saveEstimateModule.initSaveEstimateButton"
            )();
        }

        ns.configure = configure;
        ns.initEstimateMutationBridge = initEstimateMutationBridge;
    })(WdCalculatorEstimateMutationBridge);

    window.WdCalculatorEstimateMutationBridge = WdCalculatorEstimateMutationBridge;
})();

/* --- included: url-bootstrap.js --- */
(function () {
    var WdCalculatorUrlBootstrap = window.WdCalculatorUrlBootstrap || {};

    (function (ns) {
        var getProducts = function () {
            return [];
        };
        var loadEstimateToForm = function () {};
        var loadSidebarEstimates = function () {};
        var fetchImpl = window.fetch ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};
        var documentRef = document;
        var windowRef = window;
        var consoleRef = window.console || console;
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };
        var setIntervalImpl = window.setInterval ? window.setInterval.bind(window) : function () {
            return 1;
        };
        var clearIntervalImpl = window.clearInterval ? window.clearInterval.bind(window) : function () {};

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.loadSidebarEstimates === "function") {
                loadSidebarEstimates = opts.loadSidebarEstimates;
            }
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
            if (typeof opts.setIntervalImpl === "function") {
                setIntervalImpl = opts.setIntervalImpl;
            }
            if (typeof opts.clearIntervalImpl === "function") {
                clearIntervalImpl = opts.clearIntervalImpl;
            }
        }

        function ensureBackToOrderButton(orderIdFromUrl) {
            if (!orderIdFromUrl) return;
            var saveBtnContainer = documentRef.getElementById("saveEstimateBtn")
                ? documentRef.getElementById("saveEstimateBtn").parentElement
                : null;
            if (saveBtnContainer) {
                var backToOrderBtn = documentRef.getElementById("backToOrderBtn");
                if (!backToOrderBtn) {
                    backToOrderBtn = documentRef.createElement("a");
                    backToOrderBtn.id = "backToOrderBtn";
                    backToOrderBtn.className = "btn btn-secondary ms-2";
                    backToOrderBtn.href = "/edit/" + orderIdFromUrl;
                    backToOrderBtn.innerHTML = '<i class="fas fa-arrow-left"></i> 주문으로 돌아가기';
                    saveBtnContainer.appendChild(backToOrderBtn);
                }
            }
        }

        function loadEstimateFromUrl(estimateIdFromUrl) {
            consoleRef.log("견적 로드 시작, ID:", estimateIdFromUrl);
            return fetchImpl("/api/wdcalculator/estimate/" + estimateIdFromUrl)
                .then(function (response) {
                    consoleRef.log("API 응답 상태:", response.status, response.statusText);
                    if (!response.ok) {
                        throw new Error("HTTP " + response.status + ": " + response.statusText);
                    }
                    return response.json();
                })
                .then(function (data) {
                    consoleRef.log("API 응답 데이터:", data);
                    if (data.success && data.estimate) {
                        consoleRef.log("견적 로드 성공:", data.estimate);
                        if ((getProducts() || []).length === 0) {
                            consoleRef.warn("제품 목록이 아직 로드되지 않았습니다. 잠시 대기 후 재시도합니다.");
                            setTimeoutImpl(function () {
                                if ((getProducts() || []).length > 0) {
                                    loadEstimateToForm(data.estimate);
                                    setTimeoutImpl(function () {
                                        loadSidebarEstimates();
                                    }, 500);
                                } else {
                                    alertImpl("제품 목록을 불러올 수 없어 견적을 로드할 수 없습니다. 페이지를 새로고침해주세요.");
                                }
                            }, 1000);
                        } else {
                            loadEstimateToForm(data.estimate);
                            setTimeoutImpl(function () {
                                loadSidebarEstimates();
                            }, 500);
                        }
                    } else {
                        consoleRef.error("견적 로드 실패:", data);
                        alertImpl("견적을 불러오는 중 오류가 발생했습니다: " + (data.message || "알 수 없는 오류"));
                    }
                    return data;
                })
                .catch(function (error) {
                    consoleRef.error("견적 로드 중 오류:", error);
                    alertImpl("견적을 불러오는 중 오류가 발생했습니다: " + error.message);
                    return null;
                });
        }

        function setCustomerNameFromExternal(customerName) {
            var name = String(customerName || "").trim();
            var customerNameInput = documentRef.getElementById("customerName");
            if (customerNameInput && customerNameInput.value !== name) {
                customerNameInput.value = name;
                if (typeof customerNameInput.dispatchEvent === "function") {
                    var inputEvent = typeof Event === "function" ? new Event("input", { bubbles: true }) : { type: "input" };
                    var changeEvent = typeof Event === "function" ? new Event("change", { bubbles: true }) : { type: "change" };
                    customerNameInput.dispatchEvent(inputEvent);
                    customerNameInput.dispatchEvent(changeEvent);
                }
            }
        }

        function initEmbeddedBridge() {
            if (!windowRef || windowRef.__wdcEmbeddedBridgeBound || typeof windowRef.addEventListener !== "function") {
                return;
            }
            windowRef.__wdcEmbeddedBridgeBound = true;
            windowRef.addEventListener("message", function (event) {
                if (event.origin !== windowRef.location.origin) {
                    return;
                }
                var data = event.data || {};
                if (data.type === "foms:wdc:set-customer-name") {
                    setCustomerNameFromExternal(data.customerName);
                }
            });
        }

        function initUrlBootstrap() {
            var urlParams = new URLSearchParams(windowRef.location.search);
            var estimateIdFromUrl = urlParams.get("estimate_id");
            var orderIdFromUrl = urlParams.get("order_id");
            var customerNameFromUrl = urlParams.get("customer_name");

            setCustomerNameFromExternal(customerNameFromUrl);
            initEmbeddedBridge();
            ensureBackToOrderButton(orderIdFromUrl);

            if (!estimateIdFromUrl) {
                loadSidebarEstimates("");
                return;
            }

            consoleRef.log("URL에서 견적 ID 발견:", estimateIdFromUrl);

            if ((getProducts() || []).length > 0) {
                loadEstimateFromUrl(estimateIdFromUrl);
            } else {
                var checkProductsLoaded = setIntervalImpl(function () {
                    if ((getProducts() || []).length > 0) {
                        clearIntervalImpl(checkProductsLoaded);
                        loadEstimateFromUrl(estimateIdFromUrl);
                    }
                }, 100);

                setTimeoutImpl(function () {
                    clearIntervalImpl(checkProductsLoaded);
                    if ((getProducts() || []).length === 0) {
                        consoleRef.warn("제품 목록 로드를 기다리는 중 시간 초과. 견적 로드를 시도합니다.");
                        loadEstimateFromUrl(estimateIdFromUrl);
                    }
                }, 5000);
            }
        }

        ns.configure = configure;
        ns.ensureBackToOrderButton = ensureBackToOrderButton;
        ns.loadEstimateFromUrl = loadEstimateFromUrl;
        ns.setCustomerNameFromExternal = setCustomerNameFromExternal;
        ns.initEmbeddedBridge = initEmbeddedBridge;
        ns.initUrlBootstrap = initUrlBootstrap;
    })(WdCalculatorUrlBootstrap);

    window.WdCalculatorUrlBootstrap = WdCalculatorUrlBootstrap;
})();

/* --- included: order-match-ui.js --- */
/**
 * WDCalculator order-match legacy UI.
 * Host keeps search-result rendering and page bootstrap orchestration.
 */
var WdCalculatorOrderMatchUI = window.WdCalculatorOrderMatchUI || {};

(function (ns) {
    function showOrderSelectionModal(estimateId, orders) {
        var html = '<div class="modal fade" id="orderSelectionModal" tabindex="-1">';
        html += '<div class="modal-dialog modal-lg modal-fullscreen-md-down"><div class="modal-content">';
        html += '<div class="modal-header"><h5 class="modal-title">주문 선택</h5>';
        html += '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>';
        html += '<div class="modal-body"><div class="list-group">';

        orders.forEach(function (order) {
            html +=
                '\n                <button type="button" class="list-group-item list-group-item-action select-order-btn" ' +
                '\n                        data-estimate-id="' +
                estimateId +
                '" data-order-id="' +
                order.id +
                '">' +
                '\n                    <div class="d-flex justify-content-between">' +
                "\n                        <div>" +
                "\n                            <strong>주문 #" +
                order.id +
                "</strong><br>" +
                "\n                            <small>고객명: " +
                order.customer_name +
                "</small><br>" +
                "\n                            <small>전화번호: " +
                order.phone +
                "</small><br>" +
                "\n                            <small>제품: " +
                order.product +
                "</small><br>" +
                "\n                            <small>상태: " +
                order.status +
                "</small>" +
                "\n                        </div>" +
                "\n                    </div>" +
                "\n                </button>\n            ";
        });

        html += "</div></div></div></div></div>";

        var existingModal = document.getElementById("orderSelectionModal");
        if (existingModal) {
            existingModal.remove();
        }

        document.body.insertAdjacentHTML("beforeend", html);
        var modalElement = document.getElementById("orderSelectionModal");
        var modal = new bootstrap.Modal(modalElement);
        modal.show();

        modalElement.querySelectorAll(".select-order-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var estId = parseInt(this.dataset.estimateId);
                var ordId = parseInt(this.dataset.orderId);
                ns.matchEstimateToOrder(estId, ordId);
                modal.hide();
            });
        });
    }

    function matchEstimateToOrder(estimateId, orderId) {
        return fetch("/api/wdcalculator/match-order", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                estimate_id: estimateId,
                order_id: orderId,
            }),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    alert("견적과 주문이 매칭되었습니다.");
                } else {
                    alert(data.message || "매칭 중 오류가 발생했습니다.");
                }
                return data;
            })
            .catch(function (error) {
                console.error("Error:", error);
                alert("매칭 중 오류가 발생했습니다.");
                return null;
            });
    }

    function handleMatchOrderButtonClick(event) {
        var trigger = event && event.target && event.target.closest
            ? event.target.closest(".match-order-btn")
            : null;
        if (!trigger) return;

        var estimateId = parseInt(trigger.dataset.estimateId);
        var customerName = trigger.dataset.customerName;

        return fetch("/api/wdcalculator/search-orders?customer_name=" + encodeURIComponent(customerName))
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    if (data.orders.length === 0) {
                        alert("해당 고객명의 주문이 없습니다.");
                        return data;
                    }

                    if (data.orders.length === 1) {
                        return ns.matchEstimateToOrder(estimateId, data.orders[0].id);
                    }

                    ns.showOrderSelectionModal(estimateId, data.orders);
                    return data;
                }

                alert(data.message || "주문 검색 중 오류가 발생했습니다.");
                return data;
            })
            .catch(function (error) {
                console.error("Error:", error);
                alert("주문 검색 중 오류가 발생했습니다.");
                return null;
            });
    }

    function bindOrderMatchButtons() {
        document.addEventListener("click", handleMatchOrderButtonClick);
    }

    ns.showOrderSelectionModal = showOrderSelectionModal;
    ns.matchEstimateToOrder = matchEstimateToOrder;
    ns.handleMatchOrderButtonClick = handleMatchOrderButtonClick;
    ns.bindOrderMatchButtons = bindOrderMatchButtons;
})(WdCalculatorOrderMatchUI);

window.WdCalculatorOrderMatchUI = WdCalculatorOrderMatchUI;

/* --- included: loading-state.js --- */
(function () {
    var WdCalculatorLoadingState = window.WdCalculatorLoadingState || {};

    (function (ns) {
        var isLoadingEstimate = false;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                isLoadingEstimate = Boolean(opts.initialValue);
            }
        }

        function getLoadingState() {
            return isLoadingEstimate;
        }

        function setLoadingState(nextLoadingState) {
            isLoadingEstimate = Boolean(nextLoadingState);
            return isLoadingEstimate;
        }

        ns.configure = configure;
        ns.getLoadingState = getLoadingState;
        ns.setLoadingState = setLoadingState;
    })(WdCalculatorLoadingState);

    window.WdCalculatorLoadingState = WdCalculatorLoadingState;
})();
/* --- included: current-database-estimate-id.js --- */
(function () {
    var WdCalculatorCurrentDatabaseEstimateId =
        window.WdCalculatorCurrentDatabaseEstimateId || {};

    (function (ns) {
        var currentDatabaseEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                currentDatabaseEstimateId = opts.initialValue;
            }
        }

        function getCurrentDatabaseEstimateId() {
            return currentDatabaseEstimateId;
        }

        function setCurrentDatabaseEstimateId(nextDatabaseEstimateId) {
            currentDatabaseEstimateId = nextDatabaseEstimateId;
            return currentDatabaseEstimateId;
        }

        ns.configure = configure;
        ns.getCurrentDatabaseEstimateId = getCurrentDatabaseEstimateId;
        ns.setCurrentDatabaseEstimateId = setCurrentDatabaseEstimateId;
    })(WdCalculatorCurrentDatabaseEstimateId);

    window.WdCalculatorCurrentDatabaseEstimateId = WdCalculatorCurrentDatabaseEstimateId;
})();

/* --- included: products-state.js --- */
(function () {
    var WdCalculatorProductsState = window.WdCalculatorProductsState || {};

    (function (ns) {
        var products = [];

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialProducts")) {
                products = Array.isArray(opts.initialProducts) ? opts.initialProducts : [];
            }
        }

        function getProducts() {
            return products;
        }

        function setProducts(nextProducts) {
            products = Array.isArray(nextProducts) ? nextProducts : [];
            return products;
        }

        ns.configure = configure;
        ns.getProducts = getProducts;
        ns.setProducts = setProducts;
    })(WdCalculatorProductsState);

    window.WdCalculatorProductsState = WdCalculatorProductsState;
})();

/* --- included: editing-estimate-id.js --- */
(function () {
    var WdCalculatorEditingEstimateId = window.WdCalculatorEditingEstimateId || {};

    (function (ns) {
        var editingEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                editingEstimateId = opts.initialValue;
            }
        }

        function getEditingEstimateId() {
            return editingEstimateId;
        }

        function setEditingEstimateId(nextEditingEstimateId) {
            editingEstimateId = nextEditingEstimateId;
            return editingEstimateId;
        }

        ns.configure = configure;
        ns.getEditingEstimateId = getEditingEstimateId;
        ns.setEditingEstimateId = setEditingEstimateId;
    })(WdCalculatorEditingEstimateId);

    window.WdCalculatorEditingEstimateId = WdCalculatorEditingEstimateId;
})();

/* --- included: estimates-state.js --- */
(function () {
    var WdCalculatorEstimatesState = window.WdCalculatorEstimatesState || {};

    (function (ns) {
        var estimates = [];

        function normalizeEstimates(nextEstimates) {
            return Array.isArray(nextEstimates) ? nextEstimates : [];
        }

        function replaceEstimates(nextEstimates) {
            var normalizedEstimates = normalizeEstimates(nextEstimates);
            estimates.length = 0;
            Array.prototype.push.apply(estimates, normalizedEstimates);
            return estimates;
        }

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialEstimates")) {
                replaceEstimates(opts.initialEstimates);
            }
        }

        function getEstimates() {
            return estimates;
        }

        function getEstimatesLength() {
            return estimates.length;
        }

        function setEstimates(nextEstimates) {
            return replaceEstimates(nextEstimates);
        }

        ns.configure = configure;
        ns.getEstimates = getEstimates;
        ns.getEstimatesLength = getEstimatesLength;
        ns.setEstimates = setEstimates;
    })(WdCalculatorEstimatesState);

    window.WdCalculatorEstimatesState = WdCalculatorEstimatesState;
})();
