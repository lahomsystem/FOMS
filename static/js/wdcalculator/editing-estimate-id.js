(function () {
    var WdCalculatorEditingEstimateId = window.WdCalculatorEditingEstimateId || {};

    (function (ns) {
        var editingEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (Object.prototype.hasOwnProperty.call(opts, "initialValue")) {
                editingEstimateId = opts.initialValue;
            }
        }

        function getEditingEstimateId() {
            return editingEstimateId;
        }

        function setEditingEstimateId(nextEditingEstimateId) {
            editingEstimateId = nextEditingEstimateId;
            return editingEstimateId;
        }

        ns.configure = configure;
        ns.getEditingEstimateId = getEditingEstimateId;
        ns.setEditingEstimateId = setEditingEstimateId;
    })(WdCalculatorEditingEstimateId);

    window.WdCalculatorEditingEstimateId = WdCalculatorEditingEstimateId;
})();
