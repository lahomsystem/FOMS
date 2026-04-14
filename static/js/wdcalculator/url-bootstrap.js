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
            var saveBtn = documentRef.getElementById("saveEstimateBtn");
            var saveBtnContainer = saveBtn ? saveBtn.parentElement : null;
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

        function initUrlBootstrap() {
            var urlParams = new URLSearchParams(windowRef.location.search);
            var estimateIdFromUrl = urlParams.get("estimate_id");
            var orderIdFromUrl = urlParams.get("order_id");

            ensureBackToOrderButton(orderIdFromUrl);

            if (!estimateIdFromUrl) {
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
        ns.initUrlBootstrap = initUrlBootstrap;
    })(WdCalculatorUrlBootstrap);

    window.WdCalculatorUrlBootstrap = WdCalculatorUrlBootstrap;
})();
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

        function initUrlBootstrap() {
            var urlParams = new URLSearchParams(windowRef.location.search);
            var estimateIdFromUrl = urlParams.get("estimate_id");
            var orderIdFromUrl = urlParams.get("order_id");

            ensureBackToOrderButton(orderIdFromUrl);

            if (!estimateIdFromUrl) {
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
        ns.initUrlBootstrap = initUrlBootstrap;
    })(WdCalculatorUrlBootstrap);

    window.WdCalculatorUrlBootstrap = WdCalculatorUrlBootstrap;
})();
