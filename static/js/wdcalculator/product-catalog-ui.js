/**
 * WDCalculator product catalog legacy UI.
 * Depends on shared.js (escapeHtml, formatNumber).
 * Host keeps products state and bootstrap orchestration.
 */
var WdCalculatorProductCatalogUI = window.WdCalculatorProductCatalogUI || {};

(function (ns) {
    var getProducts = function () {
        return [];
    };
    var setProducts = function () {};
    var getCalculateEstimate = function () {
        return function () {};
    };
    var updateBaseProductSelectOptions = function () {};
    var ensureBaseComponentsUI = function () {};

    /**
     * @param {{
     *   getProducts?: () => Array<object>,
     *   setProducts?: (products: Array<object>) => void,
     *   getCalculateEstimate?: () => function,
     *   updateBaseProductSelectOptions?: () => void,
     *   ensureBaseComponentsUI?: () => void
     * }} opts
     */
    function configure(opts) {
        if (opts && typeof opts.getProducts === "function") {
            getProducts = opts.getProducts;
        }
        if (opts && typeof opts.setProducts === "function") {
            setProducts = opts.setProducts;
        }
        if (opts && typeof opts.getCalculateEstimate === "function") {
            getCalculateEstimate = opts.getCalculateEstimate;
        }
        if (opts && typeof opts.updateBaseProductSelectOptions === "function") {
            updateBaseProductSelectOptions = opts.updateBaseProductSelectOptions;
        }
        if (opts && typeof opts.ensureBaseComponentsUI === "function") {
            ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
        }
    }

    function syncBaseComponentsAfterProductsLoad() {
        if (!document.getElementById("baseComponentsContainer")) return;
        updateBaseProductSelectOptions();
        if (document.querySelectorAll(".base-component-row").length === 0) {
            ensureBaseComponentsUI();
        }
    }

    function loadProducts() {
        return fetch("/api/wdcalculator/products")
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    setProducts(data.products);
                    ns.updateProductSelect();
                    syncBaseComponentsAfterProductsLoad();
                    return data.products;
                }
                return null;
            })
            .catch(function (error) {
                console.error("Error loading products:", error);
                return null;
            });
    }

    function updateProductSelect() {
        var select = document.getElementById("productSelect");
        if (!select) return;
        select.innerHTML = '<option value="">제품을 선택하세요</option>';
        (getProducts() || []).forEach(function (product) {
            var option = document.createElement("option");
            option.value = product.id;
            option.textContent = product.name;
            select.appendChild(option);
        });
    }

    function showProductInfo(product) {
        var infoDiv = document.getElementById("productInfo");
        var contentDiv = document.getElementById("productInfoContent");

        if (!infoDiv || !contentDiv) {
            console.warn("제품 정보 표시 요소를 찾을 수 없습니다.");
            return;
        }

        if (!product) {
            console.warn("제품 정보가 없습니다.");
            infoDiv.style.display = "none";
            return;
        }

        var infoHtml = "<div><strong>" + escapeHtml(product.name || "") + "</strong></div>";
        infoHtml += "<div>가격 옵션: " + (product.pricing_type === "1m" ? "1m" : "30cm") + "</div>";

        if (product.pricing_type === "1m") {
            infoHtml += "<div>1m 비용: " + formatNumber(product.price_1m || 0) + "원</div>";
        } else {
            infoHtml += "<div>30cm 비용: " + formatNumber(product.price_30cm || 0) + "원</div>";
            infoHtml += "<div>1cm 비용: " + formatNumber(product.price_1cm || 0) + "원</div>";
        }

        if (product.additional_options && product.additional_options.length > 0) {
            infoHtml += '<div class="mt-2"><strong>사용 가능한 추가 옵션:</strong></div>';
            product.additional_options.forEach(function (option) {
                infoHtml +=
                    "<div>- " +
                    escapeHtml(option.name || "") +
                    ": " +
                    formatNumber(option.price || 0) +
                    "원</div>";
            });
            infoHtml +=
                '<div class="mt-1"><small class="text-muted">※ 견적 계산 시 드롭다운에서 선택하거나 직접 입력할 수 있습니다.</small></div>';
        }

        contentDiv.innerHTML = infoHtml;
        infoDiv.style.display = "block";
    }

    function handleProductSelectChange(event) {
        var target = event && event.currentTarget ? event.currentTarget : this;
        var productId = parseInt(target.value);
        var product = (getProducts() || []).find(function (item) {
            return item.id === productId;
        });

        document.getElementById("additionalOptionsContainer").innerHTML = "";

        if (product) {
            ns.showProductInfo(product);
        } else {
            document.getElementById("productInfo").style.display = "none";
            document.getElementById("baseEstimateSection").style.display = "none";
        }

        var calculateEstimate = getCalculateEstimate();
        if (typeof calculateEstimate === "function") {
            calculateEstimate();
        }
    }

    function bindProductSelect() {
        var productSelect = document.getElementById("productSelect");
        if (!productSelect) return;
        productSelect.addEventListener("change", handleProductSelectChange);
    }

    ns.configure = configure;
    ns.loadProducts = loadProducts;
    ns.updateProductSelect = updateProductSelect;
    ns.showProductInfo = showProductInfo;
    ns.handleProductSelectChange = handleProductSelectChange;
    ns.bindProductSelect = bindProductSelect;
})(WdCalculatorProductCatalogUI);

window.WdCalculatorProductCatalogUI = WdCalculatorProductCatalogUI;
