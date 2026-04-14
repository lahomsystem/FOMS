(function () {
    var WdCalculatorRefreshAfterSave = window.WdCalculatorRefreshAfterSave || {};

    (function (ns) {
        var setEstimates = function () {};
        var resetInputFormKeepCustomerName = function () {};
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
                resetInputFormKeepCustomerName();

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
