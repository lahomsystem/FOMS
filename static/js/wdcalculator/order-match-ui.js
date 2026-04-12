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
