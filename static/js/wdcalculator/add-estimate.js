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
                if (oldWidthMm !== newWidthMm) {
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
            } else {
                estimate.id = generateEstimateId();
                estimates.push(estimate);
            }

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
