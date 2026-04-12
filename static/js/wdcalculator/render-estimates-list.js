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

        function renderEstimatesList() {
            var estimates = getEstimates() || [];
            var container = documentRef.getElementById("estimatesListContainer");

            if (estimates.length === 0) {
                container.innerHTML = '<p class="text-muted text-center mb-0">추가된 견적이 없습니다.</p>';
                return;
            }

            var html = '<div class="row g-3">';
            estimates.forEach(function (estimate, index) {
                var optionsDetailHtml = buildOptionsDetailHtml(estimate);
                var estimateIdStr = escapeHtml(String(estimate.id));
                var displayNameEscaped = escapeHtml(
                    estimate.displayName ||
                        (estimate.productName || "") + " " + formatNumber(estimate.widthMm) + "mm"
                );

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
                        <div class="card-body">
                            <div class="mb-3 estimate-card-item">
                                <span class="estimate-header-base" style="color: #0d6efd !important; font-weight: 800 !important; font-size: 1.08rem !important; display: block !important; margin-bottom: 0.25rem !important;">기본 견적:</span>
                                <div class="estimate-price mb-1" style="font-size: 1.32rem !important; font-weight: 700 !important; color: #212529 !important;">${formatNumber(estimate.basePrice)}원</div>
                                <div class="estimate-detail-base" style="color: #0d7a3d !important; font-weight: 700 !important; font-size: 1.02rem !important; line-height: 1.5 !important; margin-top: 0.25rem !important;">${displayNameEscaped}</div>
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
                        </div>
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
    })(WdCalculatorRenderEstimatesList);

    window.WdCalculatorRenderEstimatesList = WdCalculatorRenderEstimatesList;
})();
