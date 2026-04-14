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
