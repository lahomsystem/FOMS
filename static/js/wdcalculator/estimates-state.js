(function () {
    var WdCalculatorEstimatesState = window.WdCalculatorEstimatesState || {};

    (function (ns) {
        var estimates = [];

        function normalizeEstimates(nextEstimates) {
            return Array.isArray(nextEstimates) ? nextEstimates : [];
        }

        function replaceEstimates(nextEstimates) {
            var normalizedEstimates = normalizeEstimates(nextEstimates);
            estimates.length = 0;
            Array.prototype.push.apply(estimates, normalizedEstimates);
            return estimates;
        }

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialEstimates")) {
                replaceEstimates(opts.initialEstimates);
            }
        }

        function getEstimates() {
            return estimates;
        }

        function getEstimatesLength() {
            return estimates.length;
        }

        function setEstimates(nextEstimates) {
            return replaceEstimates(nextEstimates);
        }

        ns.configure = configure;
        ns.getEstimates = getEstimates;
        ns.getEstimatesLength = getEstimatesLength;
        ns.setEstimates = setEstimates;
    })(WdCalculatorEstimatesState);

    window.WdCalculatorEstimatesState = WdCalculatorEstimatesState;
})();
