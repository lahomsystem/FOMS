(function () {
    "use strict";

    var state = window.__WD_CALCULATOR_ENTRY_STATE || { status: "idle", promise: null };
    state.callbacks = state.callbacks || (window.WdCalculatorEntry && window.WdCalculatorEntry._callbacks) || [];
    window.__WD_CALCULATOR_ENTRY_STATE = state;

    function flushCallbacks(error) {
        var pending = state.callbacks.splice(0, state.callbacks.length);
        pending.forEach(function (callback) {
            if (typeof callback !== "function") return;
            callback(error || null);
        });
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            if (!src) {
                resolve();
                return;
            }

            var selector = 'script[data-wdcalculator-chunk="' + src.replace(/"/g, '\\"') + '"]';
            var existingScript = document.querySelector(selector);
            if (existingScript && existingScript.getAttribute("data-loaded") === "1") {
                resolve();
                return;
            }

            var script = existingScript || document.createElement("script");
            script.async = false;
            script.setAttribute("data-wdcalculator-chunk", src);
            script.addEventListener("load", function () {
                script.setAttribute("data-loaded", "1");
                resolve();
            }, { once: true });
            script.addEventListener("error", function () {
                reject(new Error("Failed to load WDCalculator chunk: " + src));
            }, { once: true });

            if (!existingScript) {
                script.src = src;
                document.head.appendChild(script);
            }
        });
    }

    function loadScripts(urls) {
        return Promise.all(urls.map(loadScript));
    }

    function start() {
        if (state.promise) {
            return state.promise;
        }

        var urls = Array.isArray(window.WD_CALCULATOR_CHUNK_URLS)
            ? window.WD_CALCULATOR_CHUNK_URLS.slice()
            : [];

        state.status = "loading";
        state.promise = loadScripts(urls)
            .then(function () {
                state.status = "ready";
                window.__WD_CALCULATOR_CHUNKS_READY = true;
                flushCallbacks();
                window.dispatchEvent(new CustomEvent("wdcalculator:chunks-ready"));
            })
            .catch(function (error) {
                state.status = "error";
                state.error = error;
                console.error(error);
                flushCallbacks(error);
            });

        return state.promise;
    }

    window.WdCalculatorEntry = {
        ready: function (callback) {
            if (state.status === "ready") {
                callback(null);
                return;
            }
            if (state.status === "error") {
                callback(state.error || new Error("WDCalculator chunks failed to load"));
                return;
            }
            state.callbacks.push(callback);
            start();
        },
        start: start
    };

    start();
})();
