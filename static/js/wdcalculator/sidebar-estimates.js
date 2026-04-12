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
                        if (moreWrap) {
                            moreWrap.classList.add("d-none");
                        }
                        savedEstimatesList.classList.remove(expandedClass);
                        var oldCollapseBar = documentRef.getElementById(collapseBarId);
                        if (oldCollapseBar) {
                            oldCollapseBar.remove();
                        }
                        if (listItems.length > VISIBLE_COUNT_MOBILE && moreWrap && listContainer) {
                            var applyCollapse = function () {
                                for (var i = VISIBLE_COUNT_MOBILE; i < listItems.length; i += 1) {
                                    listItems[i].classList.add(hiddenClass);
                                }
                                savedEstimatesList.classList.remove(expandedClass);
                                var bar = documentRef.getElementById(collapseBarId);
                                if (bar) {
                                    bar.remove();
                                }
                                var collapseBtn = documentRef.getElementById("savedEstimatesToggleBtn");
                                if (collapseBtn) {
                                    collapseBtn.textContent =
                                        "더보기 (" + (listItems.length - VISIBLE_COUNT_MOBILE) + "건)";
                                }
                            };
                            var applyExpand = function () {
                                for (var i = VISIBLE_COUNT_MOBILE; i < listItems.length; i += 1) {
                                    listItems[i].classList.remove(hiddenClass);
                                }
                                savedEstimatesList.classList.add(expandedClass);
                                var bar = documentRef.createElement("div");
                                bar.id = collapseBarId;
                                bar.className =
                                    "text-center py-2 border-bottom bg-light saved-estimates-collapse-bar";
                                bar.innerHTML =
                                    '<button type="button" class="btn btn-sm btn-outline-secondary saved-estimates-more-btn" id="savedEstimatesCollapseBtn">줄이기</button>';
                                listContainer.insertBefore(bar, savedEstimatesList);
                                bar.querySelector("#savedEstimatesCollapseBtn").addEventListener("click", applyCollapse);
                                var toggleBtn = documentRef.getElementById("savedEstimatesToggleBtn");
                                if (toggleBtn) {
                                    toggleBtn.textContent = "줄이기";
                                }
                            };
                            if (matchMediaImpl("(max-width: " + MOBILE_BREAKPOINT + "px)").matches) {
                                applyCollapse();
                                moreWrap.classList.remove("d-none");
                                moreWrap.setAttribute("aria-hidden", "false");
                                moreWrap.innerHTML =
                                    '<button type="button" class="btn btn-sm btn-outline-secondary saved-estimates-more-btn" id="savedEstimatesToggleBtn">더보기 (' +
                                    (listItems.length - VISIBLE_COUNT_MOBILE) +
                                    "건)</button>";
                                moreWrap
                                    .querySelector("#savedEstimatesToggleBtn")
                                    .addEventListener("click", function () {
                                        if (savedEstimatesList.classList.contains(expandedClass)) {
                                            applyCollapse();
                                        } else {
                                            applyExpand();
                                        }
                                    });
                            }
                        }
                    } else if (noSavedEstimates) {
                        noSavedEstimates.style.display = "block";
                    }
                })
                .catch(function (error) {
                    console.error("Error loading estimates:", error);
                    if (savedEstimatesLoading) {
                        savedEstimatesLoading.style.display = "none";
                    }
                    var errorMessage = documentRef.createElement("div");
                    errorMessage.className = "text-center text-danger py-3";
                    errorMessage.textContent = "목록을 불러오는 중 오류가 발생했습니다.";
                    savedEstimatesList.innerHTML = "";
                    savedEstimatesList.appendChild(errorMessage);
                });
        }

        function deleteEstimate(id) {
            return fetchImpl("/api/wdcalculator/estimate/" + id, {
                method: "DELETE",
            })
                .then(parseApiResponse)
                .then(function (data) {
                    if (data.success) {
                        return loadSidebarEstimates(getSearchQuery());
                    }
                    alertImpl(data.message || "삭제 실패");
                    return null;
                })
                .catch(function (error) {
                    console.error("Error deleting estimate:", error);
                    alertImpl(error.message || "삭제 중 오류가 발생했습니다.");
                    return null;
                });
        }

        if (sidebarSearchBtn && sidebarSearchInput) {
            sidebarSearchBtn.addEventListener("click", function () {
                loadSidebarEstimates(sidebarSearchInput.value);
            });
        }

        if (sidebarSearchInput) {
            sidebarSearchInput.addEventListener("keyup", function (event) {
                if (event.key === "Enter") {
                    loadSidebarEstimates(sidebarSearchInput.value);
                }
            });
        }

        if (refreshEstimatesBtn) {
            refreshEstimatesBtn.addEventListener("click", function () {
                if (sidebarSearchInput) {
                    sidebarSearchInput.value = "";
                }
                loadSidebarEstimates();
            });
        }

        loadSidebarEstimates();

        return {
            loadSidebarEstimates: loadSidebarEstimates,
            deleteEstimate: deleteEstimate,
        };
    }

    window.initWdCalculatorSidebarEstimates = initWdCalculatorSidebarEstimates;
})();
