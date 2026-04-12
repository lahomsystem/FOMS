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
