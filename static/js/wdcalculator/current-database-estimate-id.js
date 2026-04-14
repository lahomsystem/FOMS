(function () {
    var WdCalculatorCurrentDatabaseEstimateId =
        window.WdCalculatorCurrentDatabaseEstimateId || {};

    (function (ns) {
        var currentDatabaseEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                currentDatabaseEstimateId = opts.initialValue;
            }
        }

        function getCurrentDatabaseEstimateId() {
            return currentDatabaseEstimateId;
        }

        function setCurrentDatabaseEstimateId(nextDatabaseEstimateId) {
            currentDatabaseEstimateId = nextDatabaseEstimateId;
            return currentDatabaseEstimateId;
        }

        ns.configure = configure;
        ns.getCurrentDatabaseEstimateId = getCurrentDatabaseEstimateId;
        ns.setCurrentDatabaseEstimateId = setCurrentDatabaseEstimateId;
    })(WdCalculatorCurrentDatabaseEstimateId);

    window.WdCalculatorCurrentDatabaseEstimateId = WdCalculatorCurrentDatabaseEstimateId;
})();
