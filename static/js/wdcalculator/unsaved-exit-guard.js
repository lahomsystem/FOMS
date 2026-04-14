(function () {
    var WdCalculatorUnsavedExitGuard = window.WdCalculatorUnsavedExitGuard || {};

    (function (ns) {
        var getEstimates = function () {
            return [];
        };
        var message = "작성 중인 견적이 저장되지 않았습니다. 페이지를 떠나면 내용이 사라집니다.";
        var windowRef = window;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.message === "string" && opts.message) {
                message = opts.message;
            }
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
        }

        function handleBeforeUnload(event) {
            if ((getEstimates() || []).length > 0) {
                if (event && typeof event.preventDefault === "function") {
                    event.preventDefault();
                }
                if (event) {
                    event.returnValue = message;
                }
            }
        }

        function initUnsavedExitGuard() {
            windowRef.addEventListener("beforeunload", handleBeforeUnload);
        }

        ns.configure = configure;
        ns.handleBeforeUnload = handleBeforeUnload;
        ns.initUnsavedExitGuard = initUnsavedExitGuard;
    })(WdCalculatorUnsavedExitGuard);

    window.WdCalculatorUnsavedExitGuard = WdCalculatorUnsavedExitGuard;
})();
