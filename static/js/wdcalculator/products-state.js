(function () {
    var WdCalculatorProductsState = window.WdCalculatorProductsState || {};

    (function (ns) {
        var products = [];

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialProducts")) {
                products = Array.isArray(opts.initialProducts) ? opts.initialProducts : [];
            }
        }

        function getProducts() {
            return products;
        }

        function setProducts(nextProducts) {
            products = Array.isArray(nextProducts) ? nextProducts : [];
            return products;
        }

        ns.configure = configure;
        ns.getProducts = getProducts;
        ns.setProducts = setProducts;
    })(WdCalculatorProductsState);

    window.WdCalculatorProductsState = WdCalculatorProductsState;
})();
