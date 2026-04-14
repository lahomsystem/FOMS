(function () {
    var WdCalculatorLayoutSyncWiring = window.WdCalculatorLayoutSyncWiring || {};

    (function (ns) {
        var windowRef = typeof window !== "undefined" ? window : null;
        var requestLayoutSync =
            typeof window !== "undefined" && typeof window.requestWdCalculatorLayoutSync === "function"
                ? window.requestWdCalculatorLayoutSync
                : function () {};

        function configure(options) {
            var opts = options || {};
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
            if (typeof opts.requestLayoutSync === "function") {
                requestLayoutSync = opts.requestLayoutSync;
            }
        }

        function initLayoutSyncWiring() {
            if (!windowRef || typeof windowRef.addEventListener !== "function") {
                return;
            }
            windowRef.addEventListener("resize", requestLayoutSync);
            windowRef.addEventListener("load", requestLayoutSync);
            requestLayoutSync();
        }

        ns.configure = configure;
        ns.initLayoutSyncWiring = initLayoutSyncWiring;
    })(WdCalculatorLayoutSyncWiring);

    window.WdCalculatorLayoutSyncWiring = WdCalculatorLayoutSyncWiring;
})();
