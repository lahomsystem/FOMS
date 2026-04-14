(function () {
    var WdCalculatorResetInputFormKeepCustomer = window.WdCalculatorResetInputFormKeepCustomer || {};

    (function (ns) {
        var setEditingEstimateId = function () {};
        var getEstimatesLength = function () {
            return 0;
        };
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var recalculate = function () {};
        var documentRef = document;
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
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

        ns.configure = configure;
        ns.resetInputFormKeepCustomerName = resetInputFormKeepCustomerName;
    })(WdCalculatorResetInputFormKeepCustomer);

    window.WdCalculatorResetInputFormKeepCustomer = WdCalculatorResetInputFormKeepCustomer;
})();
