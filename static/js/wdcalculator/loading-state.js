(function () {
    var WdCalculatorLoadingState = window.WdCalculatorLoadingState || {};

    (function (ns) {
        var isLoadingEstimate = false;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                isLoadingEstimate = Boolean(opts.initialValue);
            }
        }

        function getLoadingState() {
            return isLoadingEstimate;
        }

        function setLoadingState(nextLoadingState) {
            isLoadingEstimate = Boolean(nextLoadingState);
            return isLoadingEstimate;
        }

        ns.configure = configure;
        ns.getLoadingState = getLoadingState;
        ns.setLoadingState = setLoadingState;
    })(WdCalculatorLoadingState);

    window.WdCalculatorLoadingState = WdCalculatorLoadingState;
})();
